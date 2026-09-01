"""Unified plugin registry and Dify metadata intake endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.v1.dify_imports import get_dify_graphon_client
from backend.database import get_db
from backend.plugins.capability_catalog import build_plugin_node_catalog
from backend.plugins.dify_package import MAX_COMPRESSED_BYTES, DifyPackageError
from backend.schemas.common import ApiResponse
from backend.schemas.plugin import (
    PluginInstallationRead,
    PluginInstallationUpdate,
    PluginNodeCatalogRead,
)
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.workspace_rbac import (
    WorkspacePermission,
    get_workspace_access,
    require_permission,
)
from backend.services.plugin_registry_service import (
    PluginRegistryError,
    delete_plugin_installation,
    get_plugin_installation,
    import_dify_plugin,
    list_plugin_installations,
    update_plugin_installation,
)
from backend.workflow.dify_graphon_client import DifyGraphonClient

router = APIRouter(prefix="/plugins", tags=["plugins"])
workspace_router = APIRouter(prefix="/workspaces", tags=["plugins"])


def require_platform_admin(
    identity: RequestIdentity = Depends(get_request_identity),
) -> RequestIdentity:
    if not identity.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform Admin required")
    return identity


@router.get("", response_model=ApiResponse[list[PluginInstallationRead]])
async def list_plugins(
    db: AsyncSession = Depends(get_db),
    graphon_client: DifyGraphonClient = Depends(get_dify_graphon_client),
) -> ApiResponse[list[PluginInstallationRead]]:
    return ApiResponse.ok(
        await list_plugin_installations(
            db,
            dify_runtime_ready=await graphon_client.is_healthy(),
        )
    )


@router.get("/capabilities", response_model=ApiResponse[PluginNodeCatalogRead])
async def list_plugin_capabilities(
    db: AsyncSession = Depends(get_db),
    graphon_client: DifyGraphonClient = Depends(get_dify_graphon_client),
) -> ApiResponse[PluginNodeCatalogRead]:
    """Return the backend-authoritative node capability catalog."""

    installations = await list_plugin_installations(
        db,
        dify_runtime_ready=await graphon_client.is_healthy(),
    )
    return ApiResponse.ok(build_plugin_node_catalog(installations))


@router.get("/{installation_id}", response_model=ApiResponse[PluginInstallationRead])
async def get_plugin(
    installation_id: str,
    db: AsyncSession = Depends(get_db),
    graphon_client: DifyGraphonClient = Depends(get_dify_graphon_client),
) -> ApiResponse[PluginInstallationRead]:
    installation = await get_plugin_installation(
        db,
        installation_id,
        dify_runtime_ready=await graphon_client.is_healthy(),
    )
    if installation is None:
        raise _registry_http_error(
            PluginRegistryError(
                "plugin_installation_not_found",
                "Plugin installation not found.",
                status_code=404,
            )
        )
    return ApiResponse.ok(installation)


@router.post(
    "/import/dify",
    response_model=ApiResponse[PluginInstallationRead],
    status_code=201,
)
async def import_dify_plugin_file(
    file: UploadFile = File(...),
    identity: RequestIdentity = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PluginInstallationRead]:
    del identity
    filename = file.filename or "manifest.yaml"
    content = await file.read(MAX_COMPRESSED_BYTES + 1)
    if len(content) > MAX_COMPRESSED_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "dify_plugin_package_too_large",
                "message": "The uploaded plugin package exceeds the 50 MiB compressed limit.",
            },
        )
    try:
        installation = await import_dify_plugin(db, filename=filename, content=content)
    except DifyPackageError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except PluginRegistryError as exc:
        raise _registry_http_error(exc) from exc
    return ApiResponse.ok(installation)


@router.delete("/{installation_id}", response_model=ApiResponse[None])
async def delete_plugin(
    installation_id: str,
    identity: RequestIdentity = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    del identity
    try:
        await delete_plugin_installation(db, installation_id)
    except PluginRegistryError as exc:
        raise _registry_http_error(exc) from exc
    return ApiResponse.ok(None)


@workspace_router.get(
    "/{workspace_id}/plugins",
    response_model=ApiResponse[list[PluginInstallationRead]],
)
async def list_workspace_plugins(
    workspace_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
    graphon_client: DifyGraphonClient = Depends(get_dify_graphon_client),
) -> ApiResponse[list[PluginInstallationRead]]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    return ApiResponse.ok(
        await list_plugin_installations(
            db,
            workspace_id=workspace_id,
            dify_runtime_ready=await graphon_client.is_healthy(),
        )
    )


@workspace_router.get(
    "/{workspace_id}/plugins/capabilities",
    response_model=ApiResponse[PluginNodeCatalogRead],
)
async def list_workspace_plugin_capabilities(
    workspace_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
    graphon_client: DifyGraphonClient = Depends(get_dify_graphon_client),
) -> ApiResponse[PluginNodeCatalogRead]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    installations = await list_plugin_installations(
        db,
        workspace_id=workspace_id,
        dify_runtime_ready=await graphon_client.is_healthy(),
    )
    return ApiResponse.ok(build_plugin_node_catalog(installations))


@workspace_router.get(
    "/{workspace_id}/plugins/{installation_id}",
    response_model=ApiResponse[PluginInstallationRead],
)
async def get_workspace_plugin(
    workspace_id: str,
    installation_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
    graphon_client: DifyGraphonClient = Depends(get_dify_graphon_client),
) -> ApiResponse[PluginInstallationRead]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.READ)
    installation = await get_plugin_installation(
        db,
        installation_id,
        workspace_id=workspace_id,
        dify_runtime_ready=await graphon_client.is_healthy(),
    )
    if installation is None:
        raise _registry_http_error(
            PluginRegistryError(
                "plugin_installation_not_found",
                "Plugin installation not found.",
                status_code=404,
            )
        )
    return ApiResponse.ok(installation)


@workspace_router.post(
    "/{workspace_id}/plugins/import/dify",
    response_model=ApiResponse[PluginInstallationRead],
    status_code=status.HTTP_201_CREATED,
)
async def import_workspace_dify_plugin_file(
    workspace_id: str,
    file: UploadFile = File(...),
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PluginInstallationRead]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.MANAGE_CONFIGURATION)
    filename = file.filename or "manifest.yaml"
    content = await file.read(MAX_COMPRESSED_BYTES + 1)
    if len(content) > MAX_COMPRESSED_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "dify_plugin_package_too_large",
                "message": "The uploaded plugin package exceeds the 50 MiB compressed limit.",
            },
        )
    try:
        installation = await import_dify_plugin(
            db, filename=filename, content=content, workspace_id=workspace_id
        )
    except DifyPackageError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except PluginRegistryError as exc:
        raise _registry_http_error(exc) from exc
    return ApiResponse.ok(installation)


@workspace_router.patch(
    "/{workspace_id}/plugins/{installation_id}",
    response_model=ApiResponse[PluginInstallationRead],
)
async def update_workspace_plugin(
    workspace_id: str,
    installation_id: str,
    payload: PluginInstallationUpdate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PluginInstallationRead]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.MANAGE_CONFIGURATION)
    try:
        installation = await update_plugin_installation(
            db,
            installation_id,
            workspace_id=workspace_id,
            enabled=payload.enabled,
            granted_permissions=payload.granted_permissions,
        )
    except PluginRegistryError as exc:
        raise _registry_http_error(exc) from exc
    return ApiResponse.ok(installation)


@workspace_router.delete(
    "/{workspace_id}/plugins/{installation_id}",
    response_model=ApiResponse[None],
)
async def delete_workspace_plugin(
    workspace_id: str,
    installation_id: str,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    access = await get_workspace_access(db, workspace_id, identity)
    require_permission(access, WorkspacePermission.MANAGE_CONFIGURATION)
    try:
        await delete_plugin_installation(db, installation_id, workspace_id=workspace_id)
    except PluginRegistryError as exc:
        raise _registry_http_error(exc) from exc
    return ApiResponse.ok(None)


def _registry_http_error(error: PluginRegistryError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )
