"""Browser Space ownership, lease and safe execution boundary.

The HTTP layer authenticates a request and supplies its owner identity. This module
does not implement CDP or duplicate runtime authorization; its executor seam calls
the existing capability service once that sibling slice is present.
"""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.browser import BrowserBinding, BrowserInstance
from backend.models.browser_space import (
    BrowserSpace,
    BrowserSpaceEvent,
    BrowserSpaceEventKind,
    BrowserSpaceStatus,
    BrowserSpaceTask,
    BrowserSpaceTaskStatus,
)
from backend.models.identity import User, Workspace, WorkspaceMembership
from backend.models.operations_agent import OperationsAgentIdentity

MAX_PAYLOAD_BYTES = 64 * 1024
_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled"})
_SENSITIVE_KEYS = (
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "endpoint",
    "agent_url",
    "profile",
    "token",
)


class BrowserSpaceServiceError(Exception):
    def __init__(self, code: str, status_code: int, message: str | None = None):
        super().__init__(message or code)
        self.code = code
        self.status_code = status_code


BrowserSpaceExecutor = Callable[
    [BrowserSpace, str, dict[str, Any]], Awaitable[Mapping[str, Any] | dict[str, Any]]
]
BrowserSpaceCanceller = Callable[[BrowserSpaceTask], Awaitable[None]]
OwnerAuthorizer = Callable[[BrowserSpace], Awaitable[None] | None]


def _error(code: str, status_code: int, message: str | None = None) -> BrowserSpaceServiceError:
    return BrowserSpaceServiceError(code, status_code, message)


def _now() -> datetime:
    return datetime.now(UTC)


def _bounded_redacted(value: Any) -> dict[str, Any]:
    sanitized = _redact(value)
    try:
        encoded = json.dumps(sanitized, ensure_ascii=True, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        sanitized = {"redacted": True, "reason": "unsupported_payload"}
        encoded = json.dumps(sanitized).encode()
    if len(encoded) > MAX_PAYLOAD_BYTES:
        return {"truncated": True, "reason": "result_too_large"}
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(fragment in lowered for fragment in _SENSITIVE_KEYS) or "html" in lowered:
                output[key_text] = "[redacted]"
            else:
                output[key_text] = _redact(item)
        return output
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value.encode()) > MAX_PAYLOAD_BYTES:
        return "[truncated]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return "[redacted]"


async def _require_workspace(db: AsyncSession, workspace_id: str) -> Workspace:
    workspace = await db.scalar(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.active.is_(True))
    )
    if workspace is None:
        raise _error("workspace_not_found", 404)
    return workspace


async def _validate_owner(
    db: AsyncSession, workspace_id: str, owner_type: str, owner_id: str
) -> None:
    if owner_type not in {"operator", "runtime_agent"} or not owner_id.strip():
        raise _error("invalid_owner", 422)
    if owner_type == "runtime_agent":
        owner = await db.scalar(
            select(OperationsAgentIdentity.id).where(
                OperationsAgentIdentity.id == owner_id,
                OperationsAgentIdentity.workspace_id == workspace_id,
                OperationsAgentIdentity.disabled.is_(False),
            )
        )
        if owner is None:
            raise _error("owner_not_authorized", 403)
        return
    owner = await db.scalar(
        select(User.id)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            User.disabled.is_(False),
            or_(User.id == owner_id, User.subject == owner_id),
        )
    )
    if owner is None:
        raise _error("owner_not_authorized", 403)


async def _require_space(
    db: AsyncSession, workspace_id: str, space_id: str, *, lock: bool = False
) -> BrowserSpace:
    statement = select(BrowserSpace).where(
        BrowserSpace.id == space_id, BrowserSpace.workspace_id == workspace_id
    )
    if lock:
        statement = statement.with_for_update()
    space = await db.scalar(statement)
    if space is None:
        raise _error("browser_space_not_found", 404)
    return space


async def _authorize(space: BrowserSpace, authorizer: OwnerAuthorizer | None) -> None:
    if authorizer is None:
        return
    result = authorizer(space)
    if inspect.isawaitable(result):
        await result


async def create_space(
    db: AsyncSession,
    *,
    workspace_id: str,
    browser_instance_id: str,
    owner_type: str,
    owner_id: str,
    granted_capabilities: list[str],
    binding_id: str | None = None,
) -> BrowserSpace:
    """Reserve an existing instance once, atomically, for a Workspace owner."""

    await _require_workspace(db, workspace_id)
    await _validate_owner(db, workspace_id, owner_type, owner_id)
    capabilities = _validate_capabilities(granted_capabilities)
    instance = await db.get(BrowserInstance, browser_instance_id)
    if instance is None:
        raise _error("browser_instance_not_found", 404)
    if binding_id is not None:
        binding = await db.get(BrowserBinding, binding_id)
        if binding is None or binding.browser_endpoint != instance.endpoint:
            raise _error("browser_binding_not_found", 404)
    row = BrowserSpace(
        workspace_id=workspace_id,
        browser_instance_id=browser_instance_id,
        binding_id=binding_id,
        owner_type=owner_type,
        owner_id=owner_id,
        granted_capabilities=capabilities,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError as exc:
        raise _error("browser_instance_in_use", 409) from exc
    await db.commit()
    return row


async def get_space(
    db: AsyncSession, *, workspace_id: str, space_id: str, authorizer: OwnerAuthorizer | None = None
) -> BrowserSpace:
    space = await _require_space(db, workspace_id, space_id)
    await _authorize(space, authorizer)
    return space


async def list_spaces(
    db: AsyncSession,
    *,
    workspace_id: str,
    limit: int = 20,
    authorizer: OwnerAuthorizer | None = None,
) -> list[BrowserSpace]:
    await _require_workspace(db, workspace_id)
    if not 1 <= limit <= 100:
        raise _error("invalid_limit", 422)
    rows = list(
        (
            await db.execute(
                select(BrowserSpace)
                .where(BrowserSpace.workspace_id == workspace_id)
                .order_by(BrowserSpace.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    if authorizer is not None:
        authorized: list[BrowserSpace] = []
        for row in rows:
            try:
                await _authorize(row, authorizer)
            except BrowserSpaceServiceError:
                continue
            authorized.append(row)
        return authorized
    return rows


async def submit_task(
    db: AsyncSession,
    *,
    workspace_id: str,
    space_id: str,
    request_id: str,
    capability: str,
    args: dict[str, Any],
    authorizer: OwnerAuthorizer | None = None,
    executor: BrowserSpaceExecutor | None = None,
) -> BrowserSpaceTask:
    """Persist the idempotent queued lease before optionally running it."""

    if (
        not request_id.strip()
        or len(request_id) > 64
        or not capability.strip()
        or len(capability) > 255
    ):
        raise _error("invalid_task_request", 422)
    if not isinstance(args, dict):
        raise _error("invalid_capability_args", 422)
    space = await _require_space(db, workspace_id, space_id, lock=True)
    await _authorize(space, authorizer)
    if space.status == BrowserSpaceStatus.CLOSED.value:
        raise _error("browser_space_closed", 409)
    if capability not in space.granted_capabilities:
        raise _error("capability_not_granted", 422)
    existing = await db.scalar(
        select(BrowserSpaceTask).where(
            BrowserSpaceTask.space_id == space_id, BrowserSpaceTask.request_id == request_id
        )
    )
    if existing is not None:
        return existing
    task = BrowserSpaceTask(
        space_id=space_id,
        workspace_id=workspace_id,
        request_id=request_id,
        operation_id=str(uuid.uuid4()),
        capability=capability,
        # Persist safe diagnostics only; original validated args are used just for this invocation.
        args=_bounded_redacted(args),
    )
    try:
        async with db.begin_nested():
            db.add(task)
            await db.flush()
            await _append_event(
                db,
                space,
                task.id,
                BrowserSpaceEventKind.QUEUED.value,
                {"capability": capability},
            )
        await db.commit()
    except IntegrityError as exc:
        existing = await db.scalar(
            select(BrowserSpaceTask).where(
                BrowserSpaceTask.space_id == space_id, BrowserSpaceTask.request_id == request_id
            )
        )
        if existing is not None:
            return existing
        raise _error("space_task_in_progress", 409) from exc
    if executor is not None:
        return await execute_task(db, task_id=task.id, executor=executor, invocation_args=args)
    return task


async def execute_task(
    db: AsyncSession,
    *,
    task_id: str,
    executor: BrowserSpaceExecutor,
    invocation_args: dict[str, Any] | None = None,
) -> BrowserSpaceTask:
    """Run a queued task without retaining a DB transaction across the runtime call."""

    task = await db.get(BrowserSpaceTask, task_id)
    if task is None:
        raise _error("browser_space_task_not_found", 404)
    if task.status in _TERMINAL_TASK_STATUSES:
        return task
    space = await _require_space(db, task.workspace_id, task.space_id, lock=True)
    if task.status != BrowserSpaceTaskStatus.QUEUED.value:
        raise _error("space_task_in_progress", 409)
    task.status = BrowserSpaceTaskStatus.RUNNING.value
    task.started_at = _now()
    space.status = BrowserSpaceStatus.RUNNING.value
    await _append_event(
        db, space, task.id, BrowserSpaceEventKind.STARTED.value, {"capability": task.capability}
    )
    await db.commit()
    args = deepcopy(invocation_args if invocation_args is not None else task.args)
    try:
        result = await executor(space, task.capability, args)
    except Exception as exc:  # Runtime typed errors retain only their stable public code.
        code = getattr(exc, "code", "browser_runtime_failed")
        return await _finish_task_failure(db, task.id, str(code)[:64], str(exc))
    return await _finish_task_success(db, task.id, result)


async def _finish_task_success(
    db: AsyncSession, task_id: str, result: Mapping[str, Any] | dict[str, Any]
) -> BrowserSpaceTask:
    task = await db.get(BrowserSpaceTask, task_id)
    if task is None:
        raise _error("browser_space_task_not_found", 404)
    space = await _require_space(db, task.workspace_id, task.space_id, lock=True)
    if task.status == BrowserSpaceTaskStatus.CANCELLED.value:
        return task
    task.status = BrowserSpaceTaskStatus.COMPLETED.value
    task.result = _bounded_redacted(result)
    task.finished_at = _now()
    space.status = BrowserSpaceStatus.IDLE.value
    await _append_event(db, space, task.id, BrowserSpaceEventKind.COMPLETED.value, task.result)
    await db.commit()
    return task


async def _finish_task_failure(
    db: AsyncSession, task_id: str, code: str, message: str
) -> BrowserSpaceTask:
    task = await db.get(BrowserSpaceTask, task_id)
    if task is None:
        raise _error("browser_space_task_not_found", 404)
    space = await _require_space(db, task.workspace_id, task.space_id, lock=True)
    if task.status == BrowserSpaceTaskStatus.CANCELLED.value:
        return task
    task.status = BrowserSpaceTaskStatus.FAILED.value
    task.error_code = code[:64]
    # Runtime messages often contain headers or target URLs. Preserve the
    # stable code but never persist the raw exception text.
    task.error_message = "Browser capability invocation failed"
    task.finished_at = _now()
    space.status = BrowserSpaceStatus.ERROR.value
    space.last_error_code = task.error_code
    await _append_event(
        db,
        space,
        task.id,
        BrowserSpaceEventKind.FAILED.value,
        {"code": task.error_code, "message": task.error_message},
    )
    await db.commit()
    return task


async def cancel_space_task(
    db: AsyncSession,
    *,
    workspace_id: str,
    space_id: str,
    authorizer: OwnerAuthorizer | None = None,
    canceller: BrowserSpaceCanceller | None = None,
) -> BrowserSpaceTask | None:
    """Request cancellation, wait for executor cleanup, then publish cancelled."""

    space = await _require_space(db, workspace_id, space_id, lock=True)
    await _authorize(space, authorizer)
    task = await db.scalar(
        select(BrowserSpaceTask).where(
            BrowserSpaceTask.space_id == space.id,
            BrowserSpaceTask.status.in_(("queued", "running")),
        )
    )
    if task is None:
        return await db.scalar(
            select(BrowserSpaceTask)
            .where(BrowserSpaceTask.space_id == space.id)
            .order_by(BrowserSpaceTask.created_at.desc())
            .limit(1)
        )
    await _append_event(db, space, task.id, BrowserSpaceEventKind.CANCEL_REQUESTED.value, {})
    await db.commit()
    if canceller is not None:
        await canceller(task)
    task = await db.get(BrowserSpaceTask, task.id)
    space = await _require_space(db, workspace_id, space_id, lock=True)
    if task is None or task.status in _TERMINAL_TASK_STATUSES:
        return task
    task.status = BrowserSpaceTaskStatus.CANCELLED.value
    task.finished_at = _now()
    space.status = BrowserSpaceStatus.IDLE.value
    await _append_event(db, space, task.id, BrowserSpaceEventKind.CANCELLED.value, {})
    await db.commit()
    return task


async def close_space(
    db: AsyncSession,
    *,
    workspace_id: str,
    space_id: str,
    authorizer: OwnerAuthorizer | None = None,
    canceller: BrowserSpaceCanceller | None = None,
) -> BrowserSpace:
    space = await _require_space(db, workspace_id, space_id)
    await _authorize(space, authorizer)
    if space.status == BrowserSpaceStatus.CLOSED.value:
        return space
    await cancel_space_task(
        db, workspace_id=workspace_id, space_id=space_id, authorizer=authorizer, canceller=canceller
    )
    space = await _require_space(db, workspace_id, space_id, lock=True)
    space.status = BrowserSpaceStatus.CLOSED.value
    await _append_event(db, space, None, BrowserSpaceEventKind.CLOSED.value, {})
    await db.commit()
    return space


async def list_events(
    db: AsyncSession,
    *,
    workspace_id: str,
    space_id: str,
    after_sequence: int = 0,
    limit: int = 100,
    authorizer: OwnerAuthorizer | None = None,
) -> list[BrowserSpaceEvent]:
    if after_sequence < 0 or not 1 <= limit <= 100:
        raise _error("invalid_event_cursor", 422)
    space = await _require_space(db, workspace_id, space_id)
    await _authorize(space, authorizer)
    return list(
        (
            await db.execute(
                select(BrowserSpaceEvent)
                .where(
                    BrowserSpaceEvent.space_id == space_id,
                    BrowserSpaceEvent.sequence > after_sequence,
                )
                .order_by(BrowserSpaceEvent.sequence.asc())
                .limit(limit)
            )
        ).scalars()
    )


async def _append_event(
    db: AsyncSession, space: BrowserSpace, task_id: str | None, kind: str, payload: Any
) -> BrowserSpaceEvent:
    # The row lock makes the revision a per-space monotonically increasing sequence.
    space.revision += 1
    event = BrowserSpaceEvent(
        space_id=space.id,
        task_id=task_id,
        sequence=space.revision,
        kind=kind,
        payload=_bounded_redacted(payload),
    )
    db.add(event)
    await db.flush()
    return event


def _validate_capabilities(capabilities: list[str]) -> list[str]:
    if not isinstance(capabilities, list) or not capabilities:
        raise _error("invalid_granted_capabilities", 422)
    normalized = list(
        dict.fromkeys(
            item.strip() for item in capabilities if isinstance(item, str) and item.strip()
        )
    )
    if len(normalized) != len(capabilities) or any(len(item) > 255 for item in normalized):
        raise _error("invalid_granted_capabilities", 422)
    return normalized


def task_response(task: BrowserSpaceTask) -> dict[str, Any]:
    """Safe router-facing response projection; deliberately excludes raw args."""

    return {
        "space_id": task.space_id,
        "task_id": task.id,
        "operation_id": task.operation_id,
        "status": task.status,
        "result": _bounded_redacted(task.result) if task.result is not None else None,
        "error": {"code": task.error_code, "message": task.error_message}
        if task.error_code
        else None,
    }
