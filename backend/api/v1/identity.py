"""Local administrator and request identity endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.schemas.common import ApiResponse
from backend.security.identity import RequestIdentity, get_request_identity
from backend.security.local_auth import (
    hash_password,
    issue_local_token,
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
async def local_login(body: LocalLoginRequest) -> ApiResponse:
    settings = get_settings()
    if body.username != settings.local_admin_username or not verify_password(
        body.password, settings.local_admin_password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

    return ApiResponse.ok(
        {
            "access_token": issue_local_token(settings.local_admin_username, settings.secret_key),
            "token_type": "bearer",
            "using_default_password": verify_password(
                "admin", settings.local_admin_password_hash
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
    if not verify_password(body.current_password, settings.local_admin_password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前密码错误")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与当前密码相同")
    persist_password_hash(hash_password(body.new_password))
    get_settings.cache_clear()
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
