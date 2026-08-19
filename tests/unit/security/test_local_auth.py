from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.models import (
    LocalAuthSession,
    LocalCredential,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.security.local_auth import (
    InvalidLocalCredentials,
    LocalOwnerAlreadyInitialized,
    authenticate_local_owner,
    claim_local_owner,
    create_local_session,
    get_local_session_identity,
    revoke_local_session,
    utcnow,
)

CLAIM_CODE = "01ARZ3NDEK"


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        device_claim_code=CLAIM_CODE,
        local_login_max_failures=2,
        local_login_lock_seconds=300,
        **overrides,
    )


def test_local_session_cookie_secure_defaults_off_and_accepts_proxy_override():
    assert _settings().local_session_cookie_secure is False
    assert _settings(local_session_cookie_secure=True).local_session_cookie_secure is True


@pytest.mark.asyncio
async def test_claim_creates_one_owner_default_workspace_and_opaque_session(db_session):
    settings = _settings()
    identity = await claim_local_owner(
        db_session,
        claim_code=CLAIM_CODE.lower(),
        username=" Owner ",
        display_name="设备管理员",
        password="correct horse battery staple",
        settings=settings,
    )
    grant = await create_local_session(
        db_session,
        identity=identity,
        remember_device=False,
        settings=settings,
    )

    credential = await db_session.scalar(select(LocalCredential))
    workspace = await db_session.scalar(select(Workspace))
    membership = await db_session.scalar(select(WorkspaceMembership))
    stored_session = await db_session.scalar(select(LocalAuthSession))

    assert identity.subject == "local:owner"
    assert credential is not None
    assert credential.username == "owner"
    assert credential.password_hash.startswith("$bcrypt-sha256$")
    assert workspace is not None and (workspace.name, workspace.slug) == ("我的空间", "my-space")
    assert membership is not None and membership.role == WorkspaceRole.ADMIN
    assert stored_session is not None
    assert grant.token != stored_session.token_hash
    assert len(stored_session.token_hash) == 64
    assert (await get_local_session_identity(db_session, grant.token)).username == "owner"

    assert await revoke_local_session(db_session, grant.token) is True
    assert await get_local_session_identity(db_session, grant.token) is None

    with pytest.raises(LocalOwnerAlreadyInitialized):
        await claim_local_owner(
            db_session,
            claim_code=CLAIM_CODE,
            username="second",
            display_name=None,
            password="another long password",
            settings=settings,
        )


@pytest.mark.asyncio
async def test_password_failures_lock_owner_and_expired_session_is_rejected(db_session):
    settings = _settings()
    identity = await claim_local_owner(
        db_session,
        claim_code=CLAIM_CODE,
        username="owner",
        display_name=None,
        password="correct horse battery staple",
        settings=settings,
    )

    for _ in range(2):
        with pytest.raises(InvalidLocalCredentials):
            await authenticate_local_owner(
                db_session,
                username="owner",
                password="wrong password",
                settings=settings,
            )

    credential = await db_session.scalar(select(LocalCredential))
    assert credential is not None
    assert credential.failed_attempts == 2
    assert credential.locked_until is not None
    with pytest.raises(InvalidLocalCredentials):
        await authenticate_local_owner(
            db_session,
            username="owner",
            password="correct horse battery staple",
            settings=settings,
        )

    grant = await create_local_session(
        db_session,
        identity=identity,
        remember_device=False,
        settings=settings,
    )
    stored_session = await db_session.scalar(select(LocalAuthSession))
    stored_session.expires_at = utcnow() - timedelta(seconds=1)
    await db_session.flush()
    assert await get_local_session_identity(db_session, grant.token) is None
