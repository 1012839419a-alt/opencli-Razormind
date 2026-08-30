import asyncio
import re
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.browser_pool import LocalBrowserPool, get_pool
from backend.config import get_settings
from backend.database import get_db
from backend.schemas.common import ApiResponse

router = APIRouter(prefix="/workers", tags=["workers"])


def _inspect_workers() -> tuple[dict, dict]:
    from backend.worker.celery_app import celery_app

    inspect = celery_app.control.inspect(timeout=3)
    return inspect.stats() or {}, inspect.active() or {}


def _local_active_pipeline_tasks() -> int:
    from backend.executor import get_executor
    from backend.executor.local import LocalExecutor

    executor = get_executor()
    return executor.active_pipeline_tasks if isinstance(executor, LocalExecutor) else 0


@router.get("", response_model=ApiResponse[list[dict]])
async def list_workers(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    """Return execution resources for the configured task executor."""
    settings = get_settings()
    if settings.task_executor == "local":
        return ApiResponse.ok(
            [
                {
                    "id": "local",
                    "worker_id": "local",
                    "hostname": "local",
                    "status": "online",
                    "active_tasks": _local_active_pipeline_tasks(),
                    "last_heartbeat": None,
                    "concurrency": settings.local_max_concurrent_pipelines,
                    "celery_version": None,
                }
            ]
        )

    try:
        stats, active = await asyncio.to_thread(_inspect_workers)
        workers = []
        for worker_id, info in stats.items():
            active_tasks = len(active.get(worker_id, []))
            workers.append(
                {
                    "id": worker_id,
                    "worker_id": worker_id,
                    "hostname": info.get("hostname", worker_id),
                    "status": "online",
                    "active_tasks": active_tasks,
                    "last_heartbeat": None,
                    "concurrency": info.get("pool", {}).get("max-concurrency"),
                    "celery_version": info.get("versions", {}).get("celery"),
                }
            )
        return ApiResponse.ok(workers)
    except Exception:
        return ApiResponse.ok([])


def _novnc_port(cdp_url: str, base_port: int) -> int:
    """Derive the noVNC web-UI port from a CDP endpoint URL.

    Naming convention: agent → 1, agent-2 → 2, agent-N → N.
    noVNC port = base_port + (N - 1).
    """
    hostname = urlparse(cdp_url).hostname or ""
    m = re.match(r"^agent(?:-(\d+))?$", hostname)
    n = int(m.group(1)) if (m and m.group(1)) else 1
    return base_port + (n - 1)


def _container_status(hostname: str) -> str:
    """Return Docker container status string, or 'unknown' if unavailable."""
    try:
        import docker  # type: ignore[import]

        client = docker.from_env()
        return client.containers.get(hostname).status
    except Exception:
        return "unknown"


@router.get("/chrome-pool", response_model=ApiResponse[dict])
async def chrome_pool_status(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    """Return pool availability together with persisted desired and loaded runtime facts."""
    from backend.models.browser import (
        BrowserInstance,
        BrowserRuntimeBundle,
        BrowserRuntimeDeployment,
    )

    pool = get_pool()
    base_port = get_settings().novnc_base_port
    instances = {
        item.endpoint: item for item in (await db.execute(select(BrowserInstance))).scalars().all()
    }
    bundles = {
        item.id: item for item in (await db.execute(select(BrowserRuntimeBundle))).scalars().all()
    }
    deployments = {
        item.browser_instance_id: item
        for item in (await db.execute(select(BrowserRuntimeDeployment))).scalars().all()
    }
    endpoints = []
    for endpoint in pool.endpoints:
        instance = instances.get(endpoint)
        deployment = deployments.get(instance.id) if instance else None
        endpoints.append(
            {
                "url": endpoint,
                "available": pool.available_for(endpoint),
                "novnc_port": _novnc_port(endpoint, base_port),
                "container_status": _container_status(urlparse(endpoint).hostname or ""),
                "mode": pool.get_mode(endpoint),
                "agent_url": (
                    pool.get_agent_url(endpoint) if isinstance(pool, LocalBrowserPool) else None
                ),
                "agent_protocol": (
                    pool.get_agent_protocol(endpoint)
                    if isinstance(pool, LocalBrowserPool)
                    else None
                ),
                "profile_kind": pool.get_profile_kind(endpoint),
                "profile_name": pool.get_profile_name(endpoint),
                "runtime_status": pool.runtime_status(endpoint),
                "runtime_bundle_id": instance.runtime_bundle_id if instance else None,
                "runtime_bundle_name": (
                    bundles[instance.runtime_bundle_id].name
                    if instance and instance.runtime_bundle_id in bundles
                    else None
                ),
                "runtime_bundle_version": (
                    bundles[instance.runtime_bundle_id].version
                    if instance and instance.runtime_bundle_id in bundles
                    else None
                ),
                "resource_class": instance.resource_class if instance else None,
                "startup_pages": instance.startup_pages if instance else [],
                "network_policy": instance.network_policy if instance else {},
                "loaded_bundle_name": (deployment.loaded_bundle_name if deployment else None),
                "loaded_bundle_version": (deployment.loaded_bundle_version if deployment else None),
                "runtime_diagnostics": deployment.diagnostics if deployment else [],
            }
        )
    return ApiResponse.ok(
        {"endpoints": endpoints, "total": pool.total, "available": pool.available}
    )


class EndpointModeUpdate(BaseModel):
    mode: Literal["bridge", "cdp"]


@router.patch("/chrome-pool/{endpoint_b64}/mode", response_model=ApiResponse[dict])
async def update_endpoint_mode(
    endpoint_b64: str,
    body: EndpointModeUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Update the connection mode (bridge/cdp) for an agent pool endpoint."""
    import base64

    from backend.models.browser import BrowserInstance

    try:
        padded = endpoint_b64 + "=" * (-len(endpoint_b64) % 4)
        endpoint = base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid endpoint encoding")

    pool = get_pool()
    if endpoint not in pool.endpoints:
        raise HTTPException(status_code=404, detail=f"Endpoint {endpoint!r} not in pool")

    # Update in-memory pool
    pool.set_mode(endpoint, body.mode)

    # Persist to DB
    result = await db.execute(select(BrowserInstance).where(BrowserInstance.endpoint == endpoint))
    inst = result.scalar_one_or_none()
    if inst:
        inst.mode = body.mode
    else:
        inst = BrowserInstance(endpoint=endpoint, mode=body.mode, label="", profile_name=endpoint)
        db.add(inst)
    await db.commit()

    return ApiResponse.ok({"endpoint": endpoint, "mode": body.mode})


@router.get("/celery-stats", response_model=ApiResponse[dict])
async def celery_stats() -> ApiResponse:
    """Query live Celery worker stats via inspect."""
    try:
        stats, active = await asyncio.to_thread(_inspect_workers)
        return ApiResponse.ok({"stats": stats, "active": active})
    except Exception as exc:
        return ApiResponse.ok({"error": str(exc), "stats": {}, "active": {}})
