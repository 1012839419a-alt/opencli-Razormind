"""Tests for backend/workflow/runtime_resources.py — source resource resolver."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.auth import crypto
from backend.models.browser import BrowserBinding, ProfileBinding
from backend.models.cookie_jar import CookieJarEntry
from backend.models.source import DataSource
from backend.models.source_credential import SourceCredential
from backend.workflow.block_reasons import (
    MISSING_BROWSER_RESOURCE,
    MISSING_COOKIE_JAR,
    MISSING_SAVED_DATA_SOURCE,
    MISSING_SOURCE_CREDENTIAL,
)
from backend.workflow.runtime_resources import (
    SourceResourceRequirement,
    build_source_resource_requirement,
    resolve_source_resources,
)


def _stub_channel(session_affinity: bool = False, auth_kind: str = "none"):
    from backend.channels.base import Capabilities

    capabilities = Capabilities(session_affinity=session_affinity, auth_kind=auth_kind)
    channel = AsyncMock()
    channel.capabilities = capabilities
    return channel


def _patch_channels(monkeypatch, session_affinity: bool = False, auth_kind: str = "none"):
    channel = _stub_channel(session_affinity=session_affinity, auth_kind=auth_kind)
    monkeypatch.setattr(
        "backend.channels.registry.get_channel", lambda _name: channel
    )
    monkeypatch.setattr(
        "backend.channels.registry.list_channel_types",
        lambda: ["opencli", "api", "rss", "web_scraper"],
    )


async def _make_source(
    session,
    *,
    channel_type: str,
    name: str = "src",
    site: str | None = None,
    enabled: bool = True,
) -> DataSource:
    config: dict[str, Any] = {}
    if site is not None:
        config["site"] = site
    source = DataSource(
        name=name, channel_type=channel_type, channel_config=config, enabled=enabled
    )
    session.add(source)
    await session.flush()
    await session.refresh(source)
    return source


async def _add_credential(session, *, source_id: str, key_name: str) -> None:
    session.add(
        SourceCredential(
            source_id=source_id,
            key_name=key_name,
            ciphertext=crypto.encrypt("placeholder"),
        )
    )
    await session.flush()


def test_build_source_resource_requirement_normalises_blanks() -> None:
    requirement = build_source_resource_requirement(
        "node-1",
        channel_type="opencli",
        site="  ",
        source_id="  src-id  ",
        required_credentials=["", "  api_key  ", "x"],
        session_affinity=True,
    )
    assert requirement.site is None
    assert requirement.source_id == "src-id"
    assert requirement.required_credentials == ("  api_key  ", "x")
    assert requirement.session_affinity is True


async def test_resolve_source_resources_blocks_when_no_datasource(db_session, monkeypatch) -> None:
    _patch_channels(monkeypatch)
    requirement = SourceResourceRequirement(node_id="n1", channel_type="opencli")

    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "blocked"
    assert resolution.block_reason is not None
    assert resolution.block_reason.code == MISSING_SAVED_DATA_SOURCE
    assert resolution.block_reason.details["nodeId"] == "n1"
    assert resolution.block_reason.details["channelType"] == "opencli"


async def test_resolve_source_resources_blocks_when_credentials_missing(
    db_session, monkeypatch
) -> None:
    _patch_channels(monkeypatch, auth_kind="bearer")
    source = await _make_source(db_session, channel_type="api", name="api-source")
    requirement = SourceResourceRequirement(
        node_id="n2",
        channel_type="api",
        source_id=source.id,
        required_credentials=("bearer_token",),
        auth_kind="bearer",
    )

    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "blocked"
    assert resolution.block_reason is not None
    assert resolution.block_reason.code == MISSING_SOURCE_CREDENTIAL
    assert resolution.block_reason.details["requiredCredentialKey"] == "bearer_token"
    assert resolution.block_reason.details["missing"] == ["bearer_token"]


async def test_resolve_source_resources_blocks_when_browser_resource_missing(
    db_session, monkeypatch
) -> None:
    _patch_channels(monkeypatch, session_affinity=True, auth_kind="session")
    source = await _make_source(db_session, channel_type="opencli", site="xiaohongshu.com")
    requirement = SourceResourceRequirement(
        node_id="n3",
        channel_type="opencli",
        source_id=source.id,
        site="xiaohongshu.com",
        session_affinity=True,
        auth_kind="session",
    )

    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "blocked"
    assert resolution.block_reason is not None
    assert resolution.block_reason.code == MISSING_BROWSER_RESOURCE
    assert resolution.block_reason.details["site"] == "xiaohongshu.com"
    assert resolution.has_browser_binding is False
    assert resolution.has_profile_binding is False


async def test_resolve_source_resources_blocks_when_cookie_jar_missing(
    db_session, monkeypatch
) -> None:
    _patch_channels(monkeypatch)
    source = await _make_source(db_session, channel_type="web_scraper", site="example.com")
    requirement = SourceResourceRequirement(
        node_id="n4",
        channel_type="web_scraper",
        source_id=source.id,
        site="example.com",
        auth_kind="cookie",
    )

    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "blocked"
    assert resolution.block_reason is not None
    assert resolution.block_reason.code == MISSING_COOKIE_JAR
    assert resolution.block_reason.details["domain"] == "example.com"
    assert resolution.block_reason.details["credentialKind"] == "cookie"


async def test_resolve_source_resources_resolves_when_all_resources_present(
    db_session, monkeypatch
) -> None:
    _patch_channels(monkeypatch, session_affinity=True, auth_kind="bearer")
    source = await _make_source(db_session, channel_type="opencli", site="bilibili.com")
    await _add_credential(db_session, source_id=source.id, key_name="bearer_token")
    db_session.add(
        ProfileBinding(
            profile_id="profile-1",
            site="bilibili.com",
            browser_endpoint="http://chrome:9222",
            mutation_mode="read",
            active=True,
        )
    )
    db_session.add(
        BrowserBinding(browser_endpoint="http://chrome:9222", site="bilibili.com")
    )
    db_session.add(
        CookieJarEntry(
            domain="bilibili.com",
            cookie_name="auth",
            ciphertext=crypto.encrypt('{"value": "x"}'),
        )
    )
    await db_session.flush()

    requirement = SourceResourceRequirement(
        node_id="n5",
        channel_type="opencli",
        source_id=source.id,
        site="bilibili.com",
        required_credentials=("bearer_token",),
        auth_kind="bearer",
        session_affinity=True,
    )

    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "resolved"
    assert resolution.source_id == source.id
    assert "bearer_token" in resolution.credential_keys
    assert resolution.has_browser_binding is True
    assert resolution.has_profile_binding is True
    assert resolution.has_cookie_jar is True
    assert resolution.block_reason is None


async def test_resolve_source_resources_prefers_first_short_circuit(
    db_session, monkeypatch
) -> None:
    """If credentials AND browser resources are both missing, only the first
    ordered reason (credentials) is reported so the operator fixes one gap at
    a time."""
    _patch_channels(monkeypatch, session_affinity=True, auth_kind="bearer")
    source = await _make_source(db_session, channel_type="opencli", site="xhs.com")
    requirement = SourceResourceRequirement(
        node_id="n6",
        channel_type="opencli",
        source_id=source.id,
        site="xhs.com",
        required_credentials=("bearer_token",),
        auth_kind="bearer",
        session_affinity=True,
    )

    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "blocked"
    assert resolution.block_reason is not None
    assert resolution.block_reason.code == MISSING_SOURCE_CREDENTIAL


async def test_resolve_source_resources_blocks_unknown_channel(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.channels.registry.list_channel_types",
        lambda: ["api", "rss"],
    )

    requirement = SourceResourceRequirement(
        node_id="n7", channel_type="opencli", site="anywhere.com"
    )
    resolution = await resolve_source_resources(db_session, requirement)

    assert resolution.status == "blocked"
    assert resolution.block_reason is not None
    assert resolution.block_reason.code == MISSING_SAVED_DATA_SOURCE


async def test_source_resource_resolution_to_payload_round_trip() -> None:
    from backend.workflow.block_reasons import MISSING_SAVED_DATA_SOURCE
    from backend.workflow.runtime_resources import SourceResourceResolution

    from backend.schemas.workflow import WorkflowRunBlockReason

    reason = WorkflowRunBlockReason(
        code=MISSING_SAVED_DATA_SOURCE,
        message="missing",
        source="test",
        details={"nodeId": "n"},
    )
    resolution = SourceResourceResolution(
        status="blocked", source_id="src", block_reason=reason
    )
    payload = resolution.to_payload()
    assert payload["status"] == "blocked"
    assert payload["sourceId"] == "src"
    assert payload["blockReason"]["code"] == MISSING_SAVED_DATA_SOURCE