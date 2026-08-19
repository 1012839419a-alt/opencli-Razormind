"""Schemas for the single-owner appliance login flow."""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field, SecretStr, field_validator

_CROCKFORD_CODE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{10}$")


def normalize_username(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not normalized or any(not (char.isalnum() or char in "._-@") for char in normalized):
        raise ValueError("username may only contain letters, numbers, '.', '_', '-' or '@'")
    return normalized


class LocalAuthStatus(BaseModel):
    initialized: bool
    claim_available: bool
    oidc_enabled: bool
    local_login_enabled: bool
    recovery_enabled: bool


class LocalOwnerSetup(BaseModel):
    claim_code: str
    username: str = Field(min_length=3, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    password: SecretStr = Field(min_length=10, max_length=128)
    remember_device: bool = False

    @field_validator("claim_code", mode="before")
    @classmethod
    def validate_claim_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("claim_code must be a string")
        normalized = value.strip().upper()
        if not _CROCKFORD_CODE.fullmatch(normalized):
            raise ValueError("claim_code must be 10 Crockford Base32 characters")
        return normalized

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("username must be a string")
        return normalize_username(value)

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("display_name must be a string")
        return value.strip() or None


class LocalLogin(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)
    remember_device: bool = False

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("username must be a string")
        return normalize_username(value)


class AuthIdentity(BaseModel):
    subject: str
    email: str | None = None
    name: str | None = None
    username: str | None = None
    picture: str | None = None
    is_platform_admin: bool
    auth_method: str


class LogoutResult(BaseModel):
    signed_out: bool = True
