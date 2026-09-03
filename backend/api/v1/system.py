"""System-level configuration and deployment status endpoints."""

from __future__ import annotations

import os
import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.schemas.common import ApiResponse

router = APIRouter(prefix="/system", tags=["system"])


def _resolve_env_path() -> str:
    if explicit := os.environ.get("ENV_FILE_PATH"):
        return explicit
    for candidate in [
        "/app/.env",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
    ]:
        if os.path.exists(candidate):
            return candidate
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")


def _update_env_file(key: str, value: str) -> None:
    path = _resolve_env_path()
    try:
        with open(path, encoding="utf-8") as env_file:
            content = env_file.read()
    except FileNotFoundError:
        content = ""
    new_line = f"{key}={value}"
    pattern = rf"^{re.escape(key)}=.*$"
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    with open(path, "w", encoding="utf-8") as env_file:
        env_file.write(content)


class ConfigPatch(BaseModel):
    collection_mode: Literal["local", "agent"] | None = None
    collection_orchestrator: Literal["admin", "iii"] | None = None
    local_max_concurrent_pipelines: int | None = Field(default=None, ge=1, le=64)
    opencli_timeout: int | None = Field(default=None, ge=1, le=3600)
    default_timezone: str | None = Field(default=None, min_length=1, max_length=64)
    public_url: str | None = Field(default=None, max_length=2048)
    fleet_network_provider: Literal["lan", "netbird", "wireguard", "ssh", "custom"] | None = None
    netbird_mode: Literal["off", "host", "docker"] | None = None
    opencli_cdp_endpoint: str | None = Field(default=None, min_length=1, max_length=2048)
    agent_pool_endpoints: str | None = Field(default=None, max_length=8192)
    llm_request_timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    llm_max_concurrency: int | None = Field(default=None, ge=1, le=64)
    control_mode: Literal["advisory", "automatic"] | None = None
    control_kill_switch: bool | None = None


def _system_payload() -> dict:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "debug": settings.debug,
        "collection_mode": settings.collection_mode,
        "collection_orchestrator": settings.collection_orchestrator,
        "task_executor": settings.task_executor,
        "local_max_concurrent_pipelines": settings.local_max_concurrent_pipelines,
        "opencli_timeout": settings.opencli_timeout,
        "default_timezone": settings.default_timezone,
        "public_url": settings.public_url,
        "fleet_network_provider": settings.fleet_network_provider,
        "netbird_mode": settings.netbird_mode,
        "opencli_cdp_endpoint": settings.opencli_cdp_endpoint,
        "agent_pool_endpoints": [
            endpoint.strip()
            for endpoint in settings.agent_pool_endpoints.split(",")
            if endpoint.strip()
        ],
        "effective_cdp_endpoints": settings.cdp_endpoints,
        "llm_request_timeout_seconds": settings.llm_request_timeout_seconds,
        "llm_max_concurrency": settings.llm_max_concurrency,
        "control_mode": settings.control_mode,
        "control_kill_switch": settings.control_kill_switch,
        "image_tag": settings.image_tag,
        "runtime_revision": settings.opencli_runtime_revision,
        "database_kind": "sqlite" if settings.is_sqlite else "postgresql",
        "api_auth_configured": bool(settings.api_auth_token),
        "oidc_configured": bool(os.getenv("OIDC_ISSUER") and os.getenv("OIDC_AUDIENCE")),
        "smtp_configured": bool(settings.smtp_host and settings.smtp_from),
        "credential_encryption_configured": bool(settings.credential_encryption_key),
    }


@router.get("/config", response_model=ApiResponse[dict])
async def get_config() -> ApiResponse:
    return ApiResponse.ok(_system_payload())


@router.patch("/config", response_model=ApiResponse[dict])
async def update_config(body: ConfigPatch) -> ApiResponse:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return ApiResponse.ok(_system_payload())

    for key, value in updates.items():
        env_key = key.upper()
        env_value = str(value).lower() if isinstance(value, bool) else str(value)
        _update_env_file(env_key, env_value)
        os.environ[env_key] = env_value
    get_settings.cache_clear()
    return ApiResponse.ok(_system_payload())
