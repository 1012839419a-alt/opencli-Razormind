"""Local administrator and request identity endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.schemas.common import ApiResponse
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.local_auth import (
    hash_password,
    issue_local_token,
    load_password_hash,
    login_attempt_limiter,
    password_change_required,
    persist_password_hash,
    verify_password,
)


class LocalLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=6, max_length=255)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[dict])
async def local_login(body: LocalLoginRequest, request: Request) -> ApiResponse:
    client_id = request.client.host if request.client else "unknown"
    login_attempt_limiter.check(client_id)
    settings = get_settings()
    password_hash = load_password_hash(
        settings.local_admin_password_hash,
        settings.local_auth_state_path,
    )
    if body.username != settings.local_admin_username or not verify_password(
        body.password, password_hash
    ):
        login_attempt_limiter.record_failure(client_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

    login_attempt_limiter.reset(client_id)

    return ApiResponse.ok(
        {
            "access_token": issue_local_token(settings.local_admin_username, settings.secret_key),
            "token_type": "bearer",
            # Kept as the public response field for frontend compatibility. It
            # now reflects durable first-login state, not a public password.
            "using_default_password": password_change_required(
                settings.local_auth_state_path
            ),
        }
    )


@router.post("/password", response_model=ApiResponse[dict])
async def change_local_password(
    body: ChangePasswordRequest,
    identity: Annotated[RequestIdentity, Depends(get_request_identity)],
) -> ApiResponse:
    if identity.auth_method != "local":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅本地管理员可以修改本地密码")
    settings = get_settings()
    password_hash = load_password_hash(
        settings.local_admin_password_hash,
        settings.local_auth_state_path,
    )
    if not verify_password(body.current_password, password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前密码错误")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与当前密码相同")
    persist_password_hash(hash_password(body.new_password), settings.local_auth_state_path)
    return ApiResponse.ok({"message": "密码已更新"})


@router.get("/me", response_model=ApiResponse[dict])
async def read_identity(
    identity: Annotated[RequestIdentity, Depends(get_request_identity)],
) -> ApiResponse:
    return ApiResponse.ok(
        {
            "subject": identity.subject,
            "email": identity.email,
            "name": identity.name,
            "username": identity.username,
            "picture": identity.picture,
            "is_platform_admin": identity.is_platform_admin,
            "auth_method": identity.auth_method,
        }
    )
