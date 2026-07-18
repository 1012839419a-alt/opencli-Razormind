"""Resolve browser-worker capacity and profile/session runtime resources."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.browser_pool import get_pool
from backend.models.browser import (
    BrowserBinding,
)
from backend.models.browser import (
    ProfileBinding as ProfileBindingRow,
)
from backend.models.browser import (
    SessionSnapshot as SessionSnapshotRow,
)
from backend.schemas.workflow import (
    CompiledWorkflowNode,
    WorkflowFleetCapabilityMatchResponse,
    WorkflowOpenCLIHDATraceDispatch,
    WorkflowRunBlockReason,
    WorkflowRuntimeResourceRequirement,
    WorkflowRuntimeResourceResolution,
)
from backend.workflow.block_reasons import (
    MISSING_ADAPTER_RESOURCE,
    MISSING_BROWSER_RESOURCE,
    MISSING_COOKIE_JAR,
    MISSING_OPENCLI_COMMAND,
    MISSING_PROFILE_BINDING,
    MISSING_SAVED_DATA_SOURCE,
    MISSING_SESSION_SNAPSHOT,
    MISSING_SOURCE_CREDENTIAL,
    MISSING_WORKER_CAPACITY,
    MUTATION_MODE_UNSUPPORTED,
    PROFILE_LOCK_CONTENDED,
)
from backend.workflow.opencli_adapter_nodes import resolve_opencli_adapter_node


@dataclass(frozen=True)
class ProfileBinding:
    """A saved site/profile reference shared by browser workers."""

    binding_id: str
    site: str
    browser_endpoint: str
    profile_id: str | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    """An immutable, shareable read-only browser session snapshot."""

    snapshot_id: str
    profile_binding_id: str
    created_at: datetime
    blob_uri: str | None = None


@dataclass(frozen=True)
class ProfileLock:
    """A lease granting one worker exclusive profile mutation access."""

    lock_id: str
    profile_binding_id: str
    worker_slot_id: str
    acquired_at: datetime


class ProfileLockManager:
    """Process-local lock manager used by local browser-worker execution."""

    def __init__(self) -> None:
        self._locks: dict[str, ProfileLock] = {}
        self._guard = asyncio.Lock()

    async def acquire(
        self,
        profile_binding_id: str,
        worker_slot_id: str,
    ) -> ProfileLock | None:
        async with self._guard:
            if profile_binding_id in self._locks:
                return None
            lock = ProfileLock(
                lock_id=str(uuid.uuid4()),
                profile_binding_id=profile_binding_id,
                worker_slot_id=worker_slot_id,
                acquired_at=datetime.now(UTC),
            )
            self._locks[profile_binding_id] = lock
            return lock

    async def release(self, lock_id: str) -> bool:
        async with self._guard:
            profile_binding_id = next(
                (
                    binding_id
                    for binding_id, lock in self._locks.items()
                    if lock.lock_id == lock_id
                ),
                None,
            )
            if profile_binding_id is None:
                return False
            del self._locks[profile_binding_id]
            return True

    def get(self, profile_binding_id: str) -> ProfileLock | None:
        return self._locks.get(profile_binding_id)


class SessionSnapshotStore:
    """In-memory index for snapshot references shared by read-only workers."""

    def __init__(self) -> None:
        self._snapshots: dict[str, SessionSnapshot] = {}

    def publish(
        self,
        profile_binding_id: str,
        *,
        snapshot_id: str | None = None,
        blob_uri: str | None = None,
    ) -> SessionSnapshot:
        snapshot = SessionSnapshot(
            snapshot_id=snapshot_id or str(uuid.uuid4()),
            profile_binding_id=profile_binding_id,
            created_at=datetime.now(UTC),
            blob_uri=blob_uri,
        )
        self._snapshots[profile_binding_id] = snapshot
        return snapshot

    def get(self, profile_binding_id: str) -> SessionSnapshot | None:
        return self._snapshots.get(profile_binding_id)


profile_locks = ProfileLockManager()
session_snapshots = SessionSnapshotStore()


def resolve_runtime_resources(
    dispatch: WorkflowOpenCLIHDATraceDispatch,
    node: CompiledWorkflowNode,
    match: WorkflowFleetCapabilityMatchResponse | None,
) -> tuple[WorkflowRuntimeResourceRequirement, WorkflowRuntimeResourceResolution]:
    """Resolve compiled OpenCLI metadata without exposing profile secrets."""
    adapter_node_id = _read_string(node.params.get("opencliAdapterNodeId"))
    adapter_node = resolve_opencli_adapter_node(adapter_node_id) if adapter_node_id else None
    mutation_mode = "write" if adapter_node and adapter_node.access == "write" else "read"
    requirement = WorkflowRuntimeResourceRequirement(
        nodeId=dispatch.nodeId,
        sourceGroup=dispatch.sourceGroup,
        site=dispatch.site,
        mutationMode=mutation_mode,
        requestedCapability=f"opencli.{dispatch.site}.{dispatch.command or 'unresolved'}",
        adapterNodeId=adapter_node_id,
    )

    if not dispatch.command:
        return requirement, _blocked(
            MISSING_OPENCLI_COMMAND,
            "OpenCLI command could not be resolved from runtime metadata.",
            requirement,
        )
    if adapter_node_id and adapter_node is None:
        return requirement, _blocked(
            MISSING_ADAPTER_RESOURCE,
            f'OpenCLI adapter capability "{adapter_node_id}" is not registered.',
            requirement,
        )
    if match is None:
        return requirement, WorkflowRuntimeResourceResolution(
            status="resolved",
            adapterNodeId=adapter_node_id or (node.adapter.id if node.adapter else None),
            command=dispatch.command,
            workerSlotId="iii:collector-opencli",
            concurrencyLimit=1,
        )
    if (
        not adapter_node_id
        and node.adapter is not None
        and node.adapter.provider == "opencli"
        and not match.matched
    ):
        return requirement, WorkflowRuntimeResourceResolution(
            status="resolved",
            adapterNodeId=node.adapter.id,
            command=dispatch.command,
            workerSlotId="iii:collector-opencli",
            concurrencyLimit=1,
        )
    if not match.matched or match.selected is None:
        code = _block_code(match.missing, mutation_mode=mutation_mode)
        return requirement, _blocked(
            code,
            _block_message(code, dispatch.site),
            requirement,
            missing=match.missing,
        )

    selected = match.selected
    profile_binding_id = None
    session_snapshot_id = None
    lock_id = None
    if match.requiresSiteBinding:
        profile_binding_id = _resource_id("profile-binding", dispatch.site, selected.endpoint)
        if mutation_mode == "write":
            lock_id = _resource_id("profile-lock", dispatch.site, selected.endpoint)
        else:
            session_snapshot_id = _resource_id(
                "session-snapshot", dispatch.site, selected.endpoint
            )
    return requirement, WorkflowRuntimeResourceResolution(
        status="resolved",
        adapterNodeId=match.adapterNodeId or adapter_node_id,
        command=match.command or dispatch.command,
        workerSlotId=selected.endpoint,
        profileBindingId=profile_binding_id,
        sessionSnapshotId=session_snapshot_id,
        lockId=lock_id,
        concurrencyLimit=1,
    )


async def resolve_runtime_resources_from_db(
    session: AsyncSession,
    requirement: WorkflowRuntimeResourceRequirement,
    *,
    worker_slot_id: str | None = None,
) -> WorkflowRuntimeResourceResolution:
    """Resolve registered profile and snapshot resources against the control plane."""
    if requirement.mutationMode not in {"read", "write"}:
        return _blocked(
            MUTATION_MODE_UNSUPPORTED,
            f"Unsupported browser mutation mode: {requirement.mutationMode!r}.",
            requirement,
        )

    profile_row = (
        await session.execute(
            select(ProfileBindingRow).where(
                ProfileBindingRow.site == requirement.site,
                ProfileBindingRow.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    browser_row = None
    if profile_row is None:
        browser_row = (
            await session.execute(
                select(BrowserBinding).where(BrowserBinding.site == requirement.site)
            )
        ).scalar_one_or_none()
    if profile_row is None and browser_row is None:
        return _blocked(
            MISSING_PROFILE_BINDING,
            f'No browser profile binding is available for "{requirement.site}".',
            requirement,
        )

    pool = _read_pool()
    endpoint = worker_slot_id or (
        profile_row.browser_endpoint if profile_row is not None else browser_row.browser_endpoint
    )
    if pool is None or endpoint not in pool.endpoints:
        return _blocked(
            MISSING_WORKER_CAPACITY,
            "No registered browser-worker slot satisfies the requirement.",
            requirement,
            endpoint=endpoint,
        )

    profile_binding_id = profile_row.id if profile_row is not None else browser_row.id
    if requirement.mutationMode == "write":
        lock = await profile_locks.acquire(profile_binding_id, endpoint)
        if lock is None:
            return _blocked(
                PROFILE_LOCK_CONTENDED,
                f'The browser profile lock for "{requirement.site}" is already held.',
                requirement,
                profileBindingId=profile_binding_id,
            )
        return WorkflowRuntimeResourceResolution(
            status="resolved",
            workerSlotId=endpoint,
            profileBindingId=profile_binding_id,
            lockId=lock.lock_id,
        )

    snapshot = (
        await session.execute(
            select(SessionSnapshotRow)
            .where(SessionSnapshotRow.profile_binding_id == profile_binding_id)
            .order_by(SessionSnapshotRow.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return _blocked(
            MISSING_SESSION_SNAPSHOT,
            f'No shareable browser session snapshot is available for "{requirement.site}".',
            requirement,
            profileBindingId=profile_binding_id,
        )
    return WorkflowRuntimeResourceResolution(
        status="resolved",
        workerSlotId=endpoint,
        profileBindingId=profile_binding_id,
        sessionSnapshotId=snapshot.snapshot_id,
    )


@asynccontextmanager
async def profile_mutation_lock(
    profile_binding_id: str,
    worker_slot_id: str,
) -> AsyncIterator[ProfileLock]:
    """Hold an exclusive profile mutation lock for the context lifetime."""
    lock = await profile_locks.acquire(profile_binding_id, worker_slot_id)
    if lock is None:
        raise RuntimeError("profile lock is already held")
    try:
        yield lock
    finally:
        await profile_locks.release(lock.lock_id)


def _blocked(
    code: str,
    message: str,
    requirement: WorkflowRuntimeResourceRequirement,
    *,
    missing: list[str] | None = None,
    **details: Any,
) -> WorkflowRuntimeResourceResolution:
    return WorkflowRuntimeResourceResolution(
        status="blocked",
        adapterNodeId=requirement.adapterNodeId,
        blockReason=WorkflowRunBlockReason(
            code=code,
            message=message,
            source="workflow_runtime_resources",
            details={
                "nodeId": requirement.nodeId,
                "sourceGroup": requirement.sourceGroup,
                "site": requirement.site,
                "mutationMode": requirement.mutationMode,
                "requestedCapability": requirement.requestedCapability,
                "adapterNodeId": requirement.adapterNodeId,
                "missing": missing or [],
                **details,
            },
        ),
    )


def _block_code(missing: list[str], *, mutation_mode: str) -> str:
    if "opencli_adapter_node" in missing:
        return MISSING_ADAPTER_RESOURCE
    if any(value.startswith("site_binding:") for value in missing):
        return MISSING_PROFILE_BINDING
    if "profile_lock" in missing and mutation_mode == "write":
        return PROFILE_LOCK_CONTENDED
    if "session_snapshot" in missing:
        return MISSING_SESSION_SNAPSHOT
    return MISSING_WORKER_CAPACITY


def _block_message(code: str, site: str) -> str:
    if code == MISSING_ADAPTER_RESOURCE:
        return "OpenCLI adapter capability is unavailable in the registered catalog."
    if code == MISSING_PROFILE_BINDING:
        return f'No browser profile/site binding is available for "{site}".'
    if code == MISSING_SESSION_SNAPSHOT:
        return f'No shareable browser session snapshot is available for "{site}".'
    if code == PROFILE_LOCK_CONTENDED:
        return f'The browser profile lock for "{site}" is already held.'
    return "No connected worker slot currently has capacity for this OpenCLI task."


def _resource_id(kind: str, site: str, endpoint: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"opencli-admin/runtime-resource/{kind}/{site}/{endpoint}",
        )
    )


def _read_pool():
    try:
        return get_pool()
    except RuntimeError:
        return None


def _read_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# ---------------------------------------------------------------------------
# Structured source/resource resolution
#
# The functions below give the Canvas source-materialization path a stable,
# code-stable way to project runtime resources without exposing secrets or
# requiring user-supplied cookie/profile material. They never decrypt anything
# (auth keeps that behind ``AuthManager``); they only confirm whether a saved
# resource exists and report a structured ``WorkflowRunBlockReason`` when it
# does not, so the Canvas UI can show a concrete, non-secret blocked reason.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceResourceRequirement:
    """What a Canvas source node needs from the runtime resource surface.

    ``channel_type`` always identifies which DataSource runner the node will
    use; ``site`` is the opencli-style site key when known; ``source_id`` is
    the saved DataSource row id when known; ``required_credentials`` and
    ``required_browser`` mirror what the channel declared it needs, so the
    resolver can return a single blocked reason instead of cascading ones.
    """

    node_id: str
    channel_type: str
    site: str | None = None
    source_id: str | None = None
    required_credentials: tuple[str, ...] = ()
    required_browser: tuple[str, ...] = ()
    auth_kind: str | None = None
    session_affinity: bool = False


@dataclass(frozen=True)
class SourceResourceResolution:
    """Structured resolution outcome for a Canvas source node.

    ``status`` is ``"resolved"`` when every required resource exists and
    ``"blocked"`` otherwise. ``block_reason`` carries the same
    ``WorkflowRunBlockReason`` shape used elsewhere in the run pipeline, so
    Canvas consumers do not need a parallel projection.
    """

    status: Literal["resolved", "blocked"]
    source_id: str | None = None
    credential_keys: tuple[str, ...] = ()
    has_cookie_jar: bool = False
    has_browser_binding: bool = False
    has_profile_binding: bool = False
    block_reason: WorkflowRunBlockReason | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "sourceId": self.source_id,
            "credentialKeys": list(self.credential_keys),
            "hasCookieJar": self.has_cookie_jar,
            "hasBrowserBinding": self.has_browser_binding,
            "hasProfileBinding": self.has_profile_binding,
            "blockReason": (
                self.block_reason.model_dump() if self.block_reason is not None else None
            ),
        }


def build_source_resource_requirement(
    node_id: str,
    *,
    channel_type: str,
    site: str | None = None,
    source_id: str | None = None,
    required_credentials: Sequence[str] | None = None,
    required_browser: Sequence[str] | None = None,
    auth_kind: str | None = None,
    session_affinity: bool = False,
) -> SourceResourceRequirement:
    """Build a typed requirement from raw Canvas / projection metadata."""
    return SourceResourceRequirement(
        node_id=node_id,
        channel_type=channel_type,
        site=_read_string(site) if site else None,
        source_id=_read_string(source_id) if source_id else None,
        required_credentials=tuple(
            value
            for value in (required_credentials or [])
            if isinstance(value, str) and value
        ),
        required_browser=tuple(
            value
            for value in (required_browser or [])
            if isinstance(value, str) and value
        ),
        auth_kind=auth_kind,
        session_affinity=bool(session_affinity),
    )


async def resolve_source_resources(
    session: AsyncSession,
    requirement: SourceResourceRequirement,
) -> SourceResourceResolution:
    """Resolve whether the required runtime resources exist for a source node.

    This intentionally does **not** return the secrets or cookie payloads
    themselves; it only confirms presence. The actual decryption path remains
    inside ``AuthManager`` / channel runners, and never flows through Canvas
    node params.

    Order of resolution (cheapest first so a single DB hit answers most cases):

    1. Validate the channel type is registered (otherwise no resource exists).
    2. Look up a saved DataSource row by ``source_id`` if provided; otherwise
       pick the first enabled row for ``channel_type`` so Canvas can still
       show a meaningful blocked reason.
    3. Check that every required credential key is present in
       ``source_credentials`` for that source row (plain key listing, never
       decrypted).
    4. When the channel declares browser/session affinity, verify that
       ``browser_bindings`` / ``profile_bindings`` exist for the resolved
       ``site`` or source row, and that a cookie jar entry exists for the
       declared domain when ``auth_kind == "cookie"``.

    The first failed check produces the blocked reason; later checks are
    skipped so the operator sees one concrete reason at a time.
    """

    from backend.channels.registry import get_channel, list_channel_types
    from backend.models.source import DataSource

    if requirement.channel_type not in list_channel_types():
        return _blocked_resource(
            requirement,
            code=MISSING_SAVED_DATA_SOURCE,
            message=(
                f"Source node '{requirement.node_id}' references unknown "
                f"channel_type={requirement.channel_type!r}; no saved "
                "DataSource can satisfy it."
            ),
            channel_type=requirement.channel_type,
            requiredConfig=[],
        )

    try:
        channel = get_channel(requirement.channel_type)
    except KeyError:
        return _blocked_resource(
            requirement,
            code=MISSING_SAVED_DATA_SOURCE,
            message=(
                f"Channel '{requirement.channel_type}' is registered but has "
                "no implementation to resolve against."
            ),
            channel_type=requirement.channel_type,
            requiredConfig=[],
        )

    source_row = await _resolve_data_source_row(session, requirement)
    if source_row is None:
        return _blocked_resource(
            requirement,
            code=MISSING_SAVED_DATA_SOURCE,
            message=(
                f"No saved DataSource row matches channel_type="
                f"{requirement.channel_type!r} for node '{requirement.node_id}'."
            ),
            channel_type=requirement.channel_type,
            requiredConfig=[],
        )

    required_keys = list(requirement.required_credentials)
    present_keys = await _credential_keys_for_source(session, source_row.id)
    missing_keys = [key for key in required_keys if key not in present_keys]
    if missing_keys:
        return _blocked_resource(
            requirement,
            code=MISSING_SOURCE_CREDENTIAL,
            message=(
                f"Source node '{requirement.node_id}' requires saved "
                f"credentials {missing_keys!r} on DataSource "
                f"{source_row.id!r}; they are not configured."
            ),
            bindingId=source_row.id,
            requiredCredentialKey=missing_keys[0],
            missing=missing_keys,
        )

    has_cookie_jar = False
    has_browser_binding = False
    has_profile_binding = False

    if channel.capabilities.session_affinity or requirement.session_affinity:
        binding_site = requirement.site or _infer_site(source_row)
        if binding_site is None:
            return _blocked_resource(
                requirement,
                code=MISSING_BROWSER_RESOURCE,
                message=(
                    f"Channel '{requirement.channel_type}' declares browser "
                    "session affinity, but node "
                    f"'{requirement.node_id}' has no resolvable site key."
                ),
                site=None,
                resourceKind="site_binding",
            )
        has_browser_binding = await _has_browser_binding(session, binding_site)
        has_profile_binding = await _has_profile_binding(session, binding_site)
        if not (has_browser_binding or has_profile_binding):
            return _blocked_resource(
                requirement,
                code=MISSING_BROWSER_RESOURCE,
                message=(
                    f"Channel '{requirement.channel_type}' declares browser "
                    f"session affinity, but no profile/binding exists for "
                    f"site {binding_site!r}."
                ),
                site=binding_site,
                resourceKind="profile_binding",
            )

    if requirement.auth_kind == "cookie" or requirement.site:
        cookie_domain = requirement.site or _infer_site(source_row)
        if cookie_domain:
            has_cookie_jar = await _has_cookie_jar(session, cookie_domain)
            if not has_cookie_jar:
                return _blocked_resource(
                    requirement,
                    code=MISSING_COOKIE_JAR,
                    message=(
                        f"Source node '{requirement.node_id}' declared "
                        f"auth_kind=cookie, but no encrypted cookie jar "
                        f"entry exists for domain {cookie_domain!r}."
                    ),
                    domain=cookie_domain,
                    credentialKind="cookie",
                )

    return SourceResourceResolution(
        status="resolved",
        source_id=source_row.id,
        credential_keys=tuple(present_keys),
        has_cookie_jar=has_cookie_jar,
        has_browser_binding=has_browser_binding,
        has_profile_binding=has_profile_binding,
    )


async def _resolve_data_source_row(
    session: AsyncSession, requirement: SourceResourceRequirement
):
    from backend.models.source import DataSource

    if requirement.source_id:
        return await session.get(DataSource, requirement.source_id)
    result = await session.execute(
        select(DataSource)
        .where(
            DataSource.channel_type == requirement.channel_type,
            DataSource.enabled.is_(True),
        )
        .order_by(DataSource.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _credential_keys_for_source(session: AsyncSession, source_id: str) -> list[str]:
    from backend.models.source_credential import SourceCredential

    result = await session.execute(
        select(SourceCredential.key_name).where(SourceCredential.source_id == source_id)
    )
    return [row for row in result.scalars().all() if row]


async def _has_browser_binding(session: AsyncSession, site: str) -> bool:
    result = await session.execute(
        select(BrowserBinding.id).where(BrowserBinding.site == site).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _has_profile_binding(session: AsyncSession, site: str) -> bool:
    result = await session.execute(
        select(ProfileBindingRow.id)
        .where(ProfileBindingRow.site == site, ProfileBindingRow.active.is_(True))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _has_cookie_jar(session: AsyncSession, domain: str) -> bool:
    from backend.models.cookie_jar import CookieJarEntry

    result = await session.execute(
        select(CookieJarEntry.cookie_name)
        .where(CookieJarEntry.domain == domain)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _infer_site(source_row) -> str | None:
    config = getattr(source_row, "channel_config", None) or {}
    if not isinstance(config, dict):
        return None
    site = config.get("site")
    if isinstance(site, str) and site.strip():
        return site.strip()
    domain = config.get("domain")
    if isinstance(domain, str) and domain.strip():
        return domain.strip()
    return None


def _blocked_resource(
    requirement: SourceResourceRequirement,
    *,
    code: str,
    message: str,
    **details: Any,
) -> SourceResourceResolution:
    block_reason = WorkflowRunBlockReason(
        code=code,
        message=message,
        source="workflow_source_resource_resolver",
        details={
            "nodeId": requirement.node_id,
            "channelType": requirement.channel_type,
            "site": requirement.site,
            "sourceId": requirement.source_id,
            **{key: value for key, value in details.items() if value is not None},
        },
    )
    return SourceResourceResolution(
        status="blocked",
        source_id=requirement.source_id,
        block_reason=block_reason,
    )


__all__ = [
    "ProfileBinding",
    "ProfileLock",
    "ProfileLockManager",
    "SessionSnapshot",
    "SessionSnapshotStore",
    "SourceResourceRequirement",
    "SourceResourceResolution",
    "build_source_resource_requirement",
    "profile_locks",
    "profile_mutation_lock",
    "resolve_runtime_resources",
    "resolve_runtime_resources_from_db",
    "resolve_source_resources",
    "session_snapshots",
]
