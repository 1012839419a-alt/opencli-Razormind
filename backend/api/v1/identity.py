"""OIDC/bootstrap identity and local appliance-owner authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.database import commit_session, get_db, rollback_session
from backend.schemas.common import ApiResponse
from backend.schemas.local_auth import (
    AuthIdentity,
    LocalAuthStatus,
    LocalLogin,
    LocalOwnerSetup,
    LogoutResult,
)
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.local_auth import (
    SESSION_COOKIE_NAME,
    DeviceClaimUnavailable,
    InvalidDeviceClaim,
    InvalidLocalCredentials,
    LocalOwnerAlreadyInitialized,
    LocalSessionGrant,
    LocalSessionIdentity,
    authenticate_local_owner,
    claim_local_owner,
    create_local_session,
    device_claim_available,
    local_auth_initialized,
    revoke_local_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=ApiResponse[LocalAuthStatus])
async def read_auth_status(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    settings = get_settings()
    initialized = await local_auth_initialized(db)
    return ApiResponse.ok(
        LocalAuthStatus(
            initialized=initialized,
            claim_available=device_claim_available(settings),
            oidc_enabled=bool(settings.oidc_issuer and settings.oidc_audience),
            local_login_enabled=initialized,
            recovery_enabled=bool(settings.bootstrap_admin_token),
        )
    )


@router.post(
    "/setup",
    response_model=ApiResponse[AuthIdentity],
    status_code=status.HTTP_201_CREATED,
)
async def setup_local_owner(
    body: LocalOwnerSetup,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    settings = get_settings()
    try:
        identity = await claim_local_owner(
            db,
            claim_code=body.claim_code,
            username=body.username,
            display_name=body.display_name,
            password=body.password.get_secret_value(),
            settings=settings,
        )
        grant = await create_local_session(
            db,
            identity=identity,
            remember_device=body.remember_device,
            settings=settings,
        )
        # The browser can follow the 201 immediately; persist both owner and
        # session before exposing the cookie to avoid a first-request race.
        await commit_session(db)
    except LocalOwnerAlreadyInitialized as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Local owner is already initialized") from exc
    except DeviceClaimUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Device claim is not configured",
        ) from exc
    except InvalidDeviceClaim as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device claim code") from exc
    except IntegrityError as exc:
        # The unique singleton key is the final arbiter for concurrent setup
        # requests; translate the losing transaction into the same stable 409.
        await rollback_session(db)
        raise HTTPException(status.HTTP_409_CONFLICT, "Local owner is already initialized") from exc

    _set_session_cookie(response, request, grant, body.remember_device, settings)
    return ApiResponse.ok(_auth_identity(identity))


@router.post("/login", response_model=ApiResponse[AuthIdentity])
async def login_local_owner(
    body: LocalLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    settings = get_settings()
    try:
        identity = await authenticate_local_owner(
            db,
            username=body.username,
            password=body.password.get_secret_value(),
            settings=settings,
        )
    except InvalidLocalCredentials as exc:
        # Failed-attempt/lockout changes must survive the 401. The shared DB
        # dependency rolls back when an endpoint raises, so commit this narrow
        # authentication transaction before returning the uniform failure.
        await commit_session(db)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid username or password",
        ) from exc

    grant = await create_local_session(
        db,
        identity=identity,
        remember_device=body.remember_device,
        settings=settings,
    )
    await commit_session(db)
    _set_session_cookie(response, request, grant, body.remember_device, settings)
    return ApiResponse.ok(_auth_identity(identity))


@router.post("/logout", response_model=ApiResponse[LogoutResult])
async def logout_local_owner(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    settings = get_settings()
    await revoke_local_session(db, request.cookies.get(SESSION_COOKIE_NAME, ""))
    # Persist revocation before the response deletes the browser cookie so a
    # captured token cannot win a post-logout request race.
    await commit_session(db)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=_session_cookie_secure(request, settings),
        httponly=True,
        samesite="lax",
    )
    return ApiResponse.ok(LogoutResult())


@router.get("/me", response_model=ApiResponse[AuthIdentity])
async def read_identity(
    identity: Annotated[RequestIdentity, Depends(get_request_identity)],
) -> ApiResponse:
    return ApiResponse.ok(_auth_identity(identity))


def _set_session_cookie(
    response: Response,
    request: Request,
    grant: LocalSessionGrant,
    remember_device: bool,
    settings: Settings,
) -> None:
    max_age = None
    if remember_device:
        max_age = max(60, settings.local_remember_session_ttl_seconds)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        grant.token,
        max_age=max_age,
        path="/",
        secure=_session_cookie_secure(request, settings),
        httponly=True,
        samesite="lax",
    )


def _session_cookie_secure(request: Request, settings: Settings) -> bool:
    """Honor direct HTTPS and explicit TLS-terminating proxy deployments."""
    return settings.local_session_cookie_secure or request.url.scheme == "https"


def _auth_identity(identity: RequestIdentity | LocalSessionIdentity) -> AuthIdentity:
    if isinstance(identity, RequestIdentity):
        return AuthIdentity(
            subject=identity.subject,
            email=identity.email,
            name=identity.name,
            username=identity.username,
            picture=identity.picture,
            is_platform_admin=identity.is_platform_admin,
            auth_method=identity.auth_method,
        )
    return AuthIdentity(
        subject=identity.subject,
        email=identity.email,
        name=identity.name,
        username=identity.username,
        picture=None,
        is_platform_admin=True,
        auth_method="local",
    )
