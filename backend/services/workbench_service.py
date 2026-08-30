"""Safe orchestration for persisted, inspect-only coding workbench turns."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.models.edge_node import EdgeNode
from backend.models.operations_agent import (
    AgentPermissionProfile,
    AgentProfileMode,
    OperationsAgentIdentity,
    PublishedOperationsAgentVersion,
)
from backend.models.workbench import (
    WorkbenchProposal,
    WorkbenchRepository,
    WorkbenchThread,
    WorkbenchTurn,
    WorkbenchTurnEvent,
)
from backend.schemas.operations_agent import agent_runtime_binding_from_model_configuration
from backend.schemas.workbench import (
    WorkbenchEventRead,
    WorkbenchProposalRead,
    WorkbenchRuntimeRead,
    WorkbenchTestEvidence,
    WorkbenchThreadRead,
    WorkbenchTurnCreate,
    WorkbenchTurnOutput,
    WorkbenchTurnRead,
)
from backend.ws_agent_manager import is_connected, send_agent_task

MAX_EVENT_PAYLOAD_BYTES = 16_384
MAX_TEXT_BYTES = 8_192
CODING_RUNTIME_TYPES = frozenset({"codex", "pi"})
MAX_DIFF_BYTES = 524_288
MAX_TESTS = 100
MAX_TERMINAL_RESULT_BYTES = MAX_DIFF_BYTES + (MAX_TESTS * 12_000)
MAX_FILES = 1_000
SENSITIVE_KEY_PARTS = ("authorization", "credential", "password", "secret", "token", "api_key")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)\b(authorization|credential|password|secret|token|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)"
)
FENCED_JSON_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
RUNTIME_EVENT_TYPES = frozenset({"started", "text", "tool_call", "tool_result", "state"})
TERMINAL_EVENT_TYPES = frozenset({"done", "error", "cancelled"})
_ACTIVE_DISPATCHES: dict[str, asyncio.Task[None]] = {}


class WorkbenchError(RuntimeError):
    status_code = 409


class WorkbenchNotFoundError(WorkbenchError):
    status_code = 404


class WorkbenchGitError(WorkbenchError):
    status_code = 422


def schedule_workbench_turn(turn_id: str) -> None:
    task = asyncio.create_task(dispatch_workbench_turn(turn_id))
    _ACTIVE_DISPATCHES[turn_id] = task
    task.add_done_callback(lambda finished: _forget_dispatch(turn_id, finished))


def cancel_scheduled_workbench_turn(turn_id: str) -> None:
    task = _ACTIVE_DISPATCHES.get(turn_id)
    if task is not None:
        task.cancel()


def _forget_dispatch(turn_id: str, task: asyncio.Task[None]) -> None:
    if _ACTIVE_DISPATCHES.get(turn_id) is task:
        _ACTIVE_DISPATCHES.pop(turn_id, None)


async def reconcile_repositories(session: AsyncSession, workspace_id: str) -> None:
    """Reconcile only the authorized workspace's server-owned configuration."""

    configured = {
        item.name: item
        for item in get_settings().workbench_repositories
        if item.workspace_id == workspace_id
    }
    if not configured:
        return
    existing = {
        repository.name: repository
        for repository in await session.scalars(
            select(WorkbenchRepository)
            .where(WorkbenchRepository.workspace_id == workspace_id)
            .with_for_update()
        )
    }
    for name, configuration in configured.items():
        repository = existing.pop(name, None)
        values = {
            "repository_path": configuration.repository_path,
            "base_ref": configuration.base_ref,
            "worktree_root": configuration.worktree_root,
            "execution_node_url": configuration.execution_node_url,
            "shared_filesystem_id": configuration.shared_filesystem_id,
            "active": configuration.active,
        }
        if repository is None:
            session.add(
                WorkbenchRepository(
                    workspace_id=workspace_id,
                    name=name,
                    **values,
                )
            )
            continue
        for field, value in values.items():
            setattr(repository, field, value)
    for repository in existing.values():
        repository.active = False
    await session.flush()


async def list_repositories(session: AsyncSession, workspace_id: str) -> list[WorkbenchRepository]:
    await reconcile_repositories(session, workspace_id)
    return list(
        await session.scalars(
            select(WorkbenchRepository)
            .where(WorkbenchRepository.workspace_id == workspace_id)
            .where(WorkbenchRepository.active.is_(True))
            .order_by(WorkbenchRepository.name)
        )
    )


async def list_runtimes(session: AsyncSession, workspace_id: str) -> list[WorkbenchRuntimeRead]:
    agents = list(
        await session.scalars(
            select(OperationsAgentIdentity)
            .where(OperationsAgentIdentity.workspace_id == workspace_id)
            .where(OperationsAgentIdentity.disabled.is_(False))
            .where(OperationsAgentIdentity.current_published_version.is_not(None))
            .order_by(OperationsAgentIdentity.name)
        )
    )
    runtimes: list[WorkbenchRuntimeRead] = []
    for agent in agents:
        version = await session.scalar(
            select(PublishedOperationsAgentVersion)
            .where(PublishedOperationsAgentVersion.operations_agent_id == agent.id)
            .where(PublishedOperationsAgentVersion.version == agent.current_published_version)
        )
        if version is None:
            continue
        try:
            binding = agent_runtime_binding_from_model_configuration(version.model_configuration)
        except ValidationError:
            continue
        if (
            binding is None
            or binding.runtime not in CODING_RUNTIME_TYPES
            or not _binding_has_workbench_affinity(binding)
        ):
            continue
        profile = await session.scalar(
            select(AgentPermissionProfile)
            .where(AgentPermissionProfile.operations_agent_id == agent.id)
            .where(AgentPermissionProfile.version == agent.current_profile_version)
        )
        if profile is None or profile.mode != AgentProfileMode.SUGGEST_CHANGES:
            continue
        readiness, reason_code, reason = await _runtime_fleet_readiness(session, binding)
        runtimes.append(
            WorkbenchRuntimeRead(
                id=agent.id,
                name=agent.name,
                published_version=version.version,
                runtime_type=binding.runtime,
                readiness=readiness,
                reason_code=reason_code,
                reason=reason,
            )
        )
    return runtimes


async def get_repository(
    session: AsyncSession, workspace_id: str, repository_id: str
) -> WorkbenchRepository:
    repository = await session.scalar(
        select(WorkbenchRepository)
        .where(WorkbenchRepository.id == repository_id)
        .where(WorkbenchRepository.workspace_id == workspace_id)
        .where(WorkbenchRepository.active.is_(True))
    )
    if repository is None:
        raise WorkbenchNotFoundError("Workbench repository not found")
    return repository


async def create_turn(
    session: AsyncSession,
    *,
    thread: WorkbenchThread,
    body: WorkbenchTurnCreate,
    user_id: str,
) -> WorkbenchTurn:
    """Create an idempotent turn and its controller-owned isolated worktree."""

    existing = await session.scalar(
        select(WorkbenchTurn)
        .where(WorkbenchTurn.thread_id == thread.id)
        .where(WorkbenchTurn.request_id == body.request_id)
    )
    if existing is not None:
        return existing

    await reconcile_repositories(session, thread.workspace_id)

    repository = await get_repository(session, thread.workspace_id, thread.repository_id)
    agent, version, profile, runtime = await _select_runtime(
        session,
        workspace_id=thread.workspace_id,
        runtime_id=body.runtime_id,
    )
    if profile.mode != AgentProfileMode.SUGGEST_CHANGES:
        raise WorkbenchError("Coding runtime must use the suggest_changes permission profile")
    _require_repository_runtime_affinity(repository, runtime)
    await _require_runtime_fleet_ready(session, runtime)

    sequence_query = select(func.max(WorkbenchTurn.sequence)).where(
        WorkbenchTurn.thread_id == thread.id
    )
    sequence = int((await session.scalar(sequence_query)) or 0) + 1
    turn_id = str(uuid.uuid4())
    base_sha = await _resolve_base_sha(repository)
    worktree_path = await _create_worktree(repository, base_sha, turn_id)
    turn = WorkbenchTurn(
        id=turn_id,
        thread_id=thread.id,
        workspace_id=thread.workspace_id,
        sequence=sequence,
        request_id=body.request_id,
        requirement=body.requirement,
        operations_agent_id=agent.id,
        published_version=version.version,
        profile_version=profile.version,
        runtime_type=runtime.runtime,
        workflow=runtime.workflow,
        base_sha=base_sha,
        worktree_path=worktree_path,
        status="queued",
    )
    session.add(turn)
    await session.flush()
    return turn


async def get_thread(
    session: AsyncSession, workspace_id: str, thread_id: str, *, lock: bool = False
) -> WorkbenchThread:
    query = (
        select(WorkbenchThread)
        .where(WorkbenchThread.id == thread_id)
        .where(WorkbenchThread.workspace_id == workspace_id)
        .options(selectinload(WorkbenchThread.turns).selectinload(WorkbenchTurn.proposal))
    )
    if lock:
        query = query.with_for_update()
    thread = await session.scalar(query)
    if thread is None:
        raise WorkbenchNotFoundError("Workbench thread not found")
    return thread


async def list_threads(session: AsyncSession, workspace_id: str) -> list[WorkbenchThread]:
    return list(
        await session.scalars(
            select(WorkbenchThread)
            .where(WorkbenchThread.workspace_id == workspace_id)
            .options(selectinload(WorkbenchThread.turns).selectinload(WorkbenchTurn.proposal))
            .order_by(WorkbenchThread.updated_at.desc())
        )
    )


async def get_turn(
    session: AsyncSession,
    *,
    workspace_id: str,
    thread_id: str,
    turn_id: str,
    lock: bool = False,
) -> WorkbenchTurn:
    query = (
        select(WorkbenchTurn)
        .join(WorkbenchThread)
        .where(WorkbenchTurn.id == turn_id)
        .where(WorkbenchTurn.thread_id == thread_id)
        .where(WorkbenchThread.workspace_id == workspace_id)
        .options(selectinload(WorkbenchTurn.proposal))
    )
    if lock:
        query = query.with_for_update()
    turn = await session.scalar(query)
    if turn is None:
        raise WorkbenchNotFoundError("Workbench turn not found")
    return turn


async def list_turn_events(
    session: AsyncSession,
    *,
    turn: WorkbenchTurn,
    after_sequence: int = 0,
    limit: int = 500,
) -> list[WorkbenchTurnEvent]:
    return list(
        await session.scalars(
            select(WorkbenchTurnEvent)
            .where(WorkbenchTurnEvent.turn_id == turn.id)
            .where(WorkbenchTurnEvent.sequence > after_sequence)
            .order_by(WorkbenchTurnEvent.sequence)
            .limit(limit)
        )
    )


async def cancel_turn(
    session: AsyncSession,
    *,
    turn: WorkbenchTurn,
    user_id: str,
) -> WorkbenchTurn:
    """Persist cancellation before best-effort runtime cancellation."""

    if turn.status in {"applied", "failed", "cancelled", "proposed"}:
        return turn
    turn.status = "cancelled"
    turn.cancelled_by_user_id = user_id
    turn.error_message = None
    await append_turn_event(
        session,
        turn=turn,
        event_type="cancelled",
        payload={"message": "Cancelled by operator"},
    )
    return turn


async def confirm_proposal(
    session: AsyncSession,
    *,
    workspace_id: str,
    thread_id: str,
    proposal_id: str,
    user_id: str,
) -> WorkbenchProposal:
    proposal = await session.scalar(
        select(WorkbenchProposal)
        .join(WorkbenchTurn)
        .join(WorkbenchThread)
        .where(WorkbenchProposal.id == proposal_id)
        .where(WorkbenchTurn.thread_id == thread_id)
        .where(WorkbenchThread.workspace_id == workspace_id)
        .options(selectinload(WorkbenchProposal.turn))
        .with_for_update()
    )
    if proposal is None:
        raise WorkbenchNotFoundError("Workbench proposal not found")
    if proposal.status != "pending_confirmation":
        return proposal

    await reconcile_repositories(session, workspace_id)
    repository = await get_repository(session, workspace_id, proposal.repository_id)
    try:
        target_sha = await _checked_target_sha(repository)
        if target_sha == proposal.checkpoint_sha:
            await _require_clean_target(repository)
            return await _persist_applied_proposal(session, proposal, user_id)
        if target_sha != proposal.base_sha:
            raise WorkbenchError(
                "Configured target ref no longer points to the proposal base SHA; "
                "regenerate the proposal before applying"
            )
        await _require_clean_target(repository)
    except WorkbenchError as exc:
        await _record_confirmation_problem(session, proposal, str(exc), terminal=False)
        raise

    try:
        await _git(
            repository.repository_path,
            "merge",
            "--ff-only",
            proposal.checkpoint_sha,
        )
        await _require_clean_target(repository)
    except WorkbenchGitError as exc:
        message = _bounded_text(
            f"Controller checkpoint could not fast-forward the configured target ref: {exc}",
            4_000,
        )
        await _record_confirmation_problem(session, proposal, message, terminal=True)
        raise WorkbenchError(message) from exc
    except WorkbenchError as exc:
        await _record_confirmation_problem(session, proposal, str(exc), terminal=False)
        raise

    return await _persist_applied_proposal(session, proposal, user_id)


async def _persist_applied_proposal(
    session: AsyncSession,
    proposal: WorkbenchProposal,
    user_id: str,
) -> WorkbenchProposal:
    """Atomically persist the applied checkpoint after its target state is verified."""

    proposal.status = "applied"
    proposal.confirmed_by_user_id = user_id
    proposal.confirmed_at = datetime.now(UTC)
    proposal.error_message = None
    proposal.turn.status = "applied"
    proposal.turn.error_message = None
    await append_turn_event(
        session,
        turn=proposal.turn,
        event_type="done",
        payload={
            "proposalId": proposal.id,
            "status": "applied",
            "checkpointSha": proposal.checkpoint_sha,
        },
    )
    await session.commit()
    return proposal


async def _record_confirmation_problem(
    session: AsyncSession,
    proposal: WorkbenchProposal,
    message: str,
    *,
    terminal: bool,
) -> None:
    """Persist confirmation evidence before reporting the conflict to the caller."""

    bounded = _bounded_text(message, 4_000)
    proposal.error_message = bounded
    if terminal:
        proposal.status = "failed"
        proposal.turn.status = "failed"
        proposal.turn.error_message = bounded
    await append_turn_event(
        session,
        turn=proposal.turn,
        event_type="error",
        payload={
            "proposalId": proposal.id,
            "message": bounded,
            "terminal": terminal,
        },
    )
    await session.commit()


async def dispatch_workbench_turn(turn_id: str) -> None:
    """Dispatch a queued turn through the existing registered runtime protocol."""

    try:
        async with AsyncSessionLocal() as session:
            claimed = await session.execute(
                update(WorkbenchTurn)
                .where(WorkbenchTurn.id == turn_id)
                .where(WorkbenchTurn.status == "queued")
                .values(status="running")
            )
            await session.commit()
            if getattr(claimed, "rowcount", 0) != 1:
                return

        async with AsyncSessionLocal() as session:
            turn = await session.get(WorkbenchTurn, turn_id)
            if turn is None or turn.status != "running":
                return
            agent, version, profile, binding = await _pinned_runtime(session, turn)
            if agent.disabled:
                raise WorkbenchError("Pinned Operations Agent is disabled")
            if profile.mode != AgentProfileMode.SUGGEST_CHANGES:
                raise WorkbenchError(
                    "Pinned Operations Agent is no longer authorized for proposals"
                )
            thread = await session.get(WorkbenchThread, turn.thread_id)
            if thread is None:
                raise WorkbenchNotFoundError("Workbench thread not found")
            await reconcile_repositories(session, turn.workspace_id)
            repository = await get_repository(session, turn.workspace_id, thread.repository_id)
            _require_repository_runtime_affinity(repository, binding)
            await _require_runtime_fleet_ready(session, binding)
            instructions = _workbench_instructions(version.instructions)
            runtime_config = {
                "cwd": turn.worktree_path,
                "timeout_seconds": binding.dispatch_timeout_seconds,
            }
            configured_timeout = binding.config.get("timeout_seconds")
            if (
                isinstance(configured_timeout, (int, float))
                and not isinstance(configured_timeout, bool)
                and configured_timeout > binding.dispatch_timeout_seconds
            ):
                runtime_config["timeout_seconds"] = configured_timeout

        async def on_event(event: dict[str, Any]) -> None:
            event_type = event.get("type")
            if event_type not in RUNTIME_EVENT_TYPES:
                return
            async with AsyncSessionLocal() as event_session:
                current = await event_session.get(WorkbenchTurn, turn_id, with_for_update=True)
                if current is None or current.status != "running":
                    return
                await append_turn_event(
                    event_session,
                    turn=current,
                    event_type=event_type,
                    payload=event,
                )
                await event_session.commit()

        terminal = await send_agent_task(
            binding.agent_url,
            {
                "runtime": binding.runtime,
                "workflow": binding.workflow,
                "instructions": instructions,
                "input": {"message": turn.requirement},
                "config": runtime_config,
                "session_id": None,
            },
            on_event,
            timeout=float(binding.dispatch_timeout_seconds),
        )
        if terminal.get("type") == "error":
            raise WorkbenchError(
                _bounded_text(str(terminal.get("message") or "Runtime failed"), 4_000)
            )
        if terminal.get("type") != "done":
            raise WorkbenchError("Runtime returned no terminal done/error event")
        await _create_proposal(turn_id, terminal)
    except asyncio.CancelledError:
        return
    except Exception as exc:
        await _fail_turn(turn_id, str(exc))


async def _create_proposal(turn_id: str, terminal: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as session:
        turn = await session.get(WorkbenchTurn, turn_id, with_for_update=True)
        if turn is None or turn.status != "running":
            return
        thread = await session.get(WorkbenchThread, turn.thread_id)
        if thread is None:
            raise WorkbenchNotFoundError("Workbench thread not found")
        repository = await get_repository(session, turn.workspace_id, thread.repository_id)

        result = _terminal_result(terminal)
        patch = result.get("patch")
        if isinstance(patch, str) and patch:
            await _git(
                turn.worktree_path, "apply", "--index", "--whitespace=nowarn", input_text=patch
            )
        await _git(turn.worktree_path, "add", "-A")
        if (
            await _git_exit_code(turn.worktree_path, "diff", "--cached", "--quiet", turn.base_sha)
            == 0
        ):
            raise WorkbenchError("Runtime completed without a patch proposal")
        await _git(turn.worktree_path, "diff", "--cached", "--check", turn.base_sha)
        raw_diff = await _git(
            turn.worktree_path,
            "diff",
            "--cached",
            "--binary",
            turn.base_sha,
            preserve_output=True,
        )
        modified_files = [
            path
            for path in (
                await _git(turn.worktree_path, "diff", "--cached", "--name-only", turn.base_sha)
            ).splitlines()
            if path
        ]
        if len(raw_diff.encode("utf-8")) > MAX_DIFF_BYTES:
            raise WorkbenchError("Proposal diff exceeds the configured output limit")
        if len(modified_files) > MAX_FILES:
            raise WorkbenchError("Proposal modifies too many files")
        tree_sha = await _git(turn.worktree_path, "write-tree")
        checkpoint_sha = await _git(
            turn.worktree_path,
            "commit-tree",
            tree_sha,
            "-p",
            turn.base_sha,
            "-m",
            "OpenCLI Workbench proposal",
            env={
                "GIT_AUTHOR_NAME": "OpenCLI Workbench",
                "GIT_AUTHOR_EMAIL": "workbench@localhost",
                "GIT_COMMITTER_NAME": "OpenCLI Workbench",
                "GIT_COMMITTER_EMAIL": "workbench@localhost",
            },
        )
        tests = _test_evidence(result.get("tests"))
        public_diff = _bounded_text(_redact(raw_diff, text_limit=MAX_DIFF_BYTES), MAX_DIFF_BYTES)
        proposal = WorkbenchProposal(
            workspace_id=turn.workspace_id,
            repository_id=repository.id,
            turn_id=turn.id,
            base_sha=turn.base_sha,
            checkpoint_sha=checkpoint_sha,
            diff=public_diff,
            modified_files=modified_files,
            tests=[test.model_dump(mode="json") for test in tests],
        )
        session.add(proposal)
        await session.flush()
        await _git(
            repository.repository_path,
            "update-ref",
            f"refs/workbench/proposals/{proposal.id}",
            checkpoint_sha,
        )
        turn.proposal = proposal
        turn.status = "proposed"
        turn.output = {
            "modifiedFiles": modified_files,
            "tests": [test.model_dump(mode="json") for test in tests],
            "diff": public_diff,
            "proposalId": proposal.id,
        }
        await append_turn_event(
            session,
            turn=turn,
            event_type="proposal",
            payload={
                "proposalId": proposal.id,
                "modifiedFiles": modified_files,
                "tests": [test.model_dump(mode="json") for test in tests],
                "diff": public_diff,
            },
        )
        await session.commit()


async def _fail_turn(turn_id: str, message: str) -> None:
    async with AsyncSessionLocal() as session:
        turn = await session.get(WorkbenchTurn, turn_id, with_for_update=True)
        if turn is None or turn.status in {"cancelled", "applied", "proposed", "failed"}:
            return
        turn.status = "failed"
        turn.error_message = _bounded_text(message, 4_000)
        await append_turn_event(
            session,
            turn=turn,
            event_type="error",
            payload={"message": turn.error_message},
        )
        await session.commit()


async def append_turn_event(
    session: AsyncSession,
    *,
    turn: WorkbenchTurn,
    event_type: str,
    payload: dict[str, Any],
) -> WorkbenchTurnEvent:
    """Append exactly one redacted event using the server-owned per-turn counter."""

    if event_type not in {*RUNTIME_EVENT_TYPES, *TERMINAL_EVENT_TYPES, "proposal"}:
        raise WorkbenchError(f"Unsupported Workbench event type: {event_type}")
    sequence = turn.next_event_sequence
    event = WorkbenchTurnEvent(
        turn_id=turn.id,
        event_id=str(uuid.uuid4()),
        sequence=sequence,
        event_type=event_type,
        payload=_bounded_payload(payload),
    )
    session.add(event)
    turn.next_event_sequence = sequence + 1
    await session.flush()
    return event


async def _select_runtime(
    session: AsyncSession, *, workspace_id: str, runtime_id: str
) -> tuple[
    OperationsAgentIdentity,
    PublishedOperationsAgentVersion,
    AgentPermissionProfile,
    Any,
]:
    agent = await session.scalar(
        select(OperationsAgentIdentity)
        .where(OperationsAgentIdentity.id == runtime_id)
        .where(OperationsAgentIdentity.workspace_id == workspace_id)
        .where(OperationsAgentIdentity.disabled.is_(False))
    )
    if agent is None or agent.current_published_version is None:
        raise WorkbenchNotFoundError("Registered coding runtime not found")
    version = await session.scalar(
        select(PublishedOperationsAgentVersion)
        .where(PublishedOperationsAgentVersion.operations_agent_id == agent.id)
        .where(PublishedOperationsAgentVersion.version == agent.current_published_version)
    )
    profile = await session.scalar(
        select(AgentPermissionProfile)
        .where(AgentPermissionProfile.operations_agent_id == agent.id)
        .where(AgentPermissionProfile.version == agent.current_profile_version)
    )
    if version is None or profile is None:
        raise WorkbenchError("Registered coding runtime is missing its pinned version or profile")
    try:
        binding = agent_runtime_binding_from_model_configuration(version.model_configuration)
    except ValidationError as exc:
        raise WorkbenchError("Registered coding runtime binding is invalid") from exc
    if binding is None:
        raise WorkbenchError("Registered coding runtime has no runtime binding")
    return agent, version, profile, binding


async def _pinned_runtime(
    session: AsyncSession, turn: WorkbenchTurn
) -> tuple[OperationsAgentIdentity, PublishedOperationsAgentVersion, AgentPermissionProfile, Any]:
    agent = await session.get(OperationsAgentIdentity, turn.operations_agent_id)
    if agent is None or agent.workspace_id != turn.workspace_id:
        raise WorkbenchError("Pinned Operations Agent is missing")
    version = await session.scalar(
        select(PublishedOperationsAgentVersion)
        .where(PublishedOperationsAgentVersion.operations_agent_id == agent.id)
        .where(PublishedOperationsAgentVersion.version == turn.published_version)
    )
    profile = await session.scalar(
        select(AgentPermissionProfile)
        .where(AgentPermissionProfile.operations_agent_id == agent.id)
        .where(AgentPermissionProfile.version == turn.profile_version)
    )
    if version is None or profile is None:
        raise WorkbenchError("Pinned Operations Agent version or profile is missing")
    try:
        binding = agent_runtime_binding_from_model_configuration(version.model_configuration)
    except ValidationError as exc:
        raise WorkbenchError("Pinned Operations Agent runtime binding is invalid") from exc
    if binding is None or binding.runtime != turn.runtime_type or binding.workflow != turn.workflow:
        raise WorkbenchError("Pinned Operations Agent runtime binding changed or is unavailable")
    return agent, version, profile, binding


def _binding_has_workbench_affinity(binding: Any) -> bool:
    execution_node_url = getattr(binding, "execution_node_url", None)
    shared_filesystem_id = getattr(binding, "shared_filesystem_id", None)
    return bool(
        execution_node_url
        and shared_filesystem_id
        and execution_node_url == getattr(binding, "agent_url", None)
    )


def _require_repository_runtime_affinity(repository: WorkbenchRepository, binding: Any) -> None:
    runtime_type = getattr(binding, "runtime", "")
    if runtime_type not in CODING_RUNTIME_TYPES:
        raise WorkbenchError(
            f"Runtime {runtime_type!r} is not a supported Workbench coding adapter"
        )
    if not _binding_has_workbench_affinity(binding):
        raise WorkbenchError(
            "Coding runtime lacks an explicit execution-node/shared-filesystem affinity"
        )
    if repository.execution_node_url != binding.execution_node_url:
        raise WorkbenchError(
            "Repository mapping is bound to a different execution node than the selected runtime"
        )
    if repository.shared_filesystem_id != binding.shared_filesystem_id:
        raise WorkbenchError(
            "Repository mapping and selected runtime do not share a configured filesystem"
        )


async def _runtime_fleet_readiness(
    session: AsyncSession,
    binding: Any,
) -> tuple[str, str | None, str | None]:
    agent_url = getattr(binding, "agent_url", "")
    runtime = getattr(binding, "runtime", "")
    node = await session.scalar(select(EdgeNode).where(EdgeNode.url == agent_url))
    if node is None:
        return "blocked", "node_not_registered", "Execution node is not registered"
    if node.status != "online":
        return "blocked", "node_offline", "Execution node is offline"
    if node.protocol != "ws":
        return "blocked", "reverse_ws_required", "Execution node has no reverse WS channel"
    if runtime not in (node.runtimes or []):
        return "blocked", "runtime_unavailable", f"Runtime {runtime!r} is not published by the node"
    if not is_connected(agent_url):
        return "blocked", "node_disconnected", "Execution node reverse WS is disconnected"
    return "ready", None, None


async def _require_runtime_fleet_ready(session: AsyncSession, binding: Any) -> None:
    readiness, reason_code, reason = await _runtime_fleet_readiness(session, binding)
    if readiness != "ready":
        raise WorkbenchError(f"Coding runtime is not ready ({reason_code}): {reason}")


async def _checked_target_sha(repository: WorkbenchRepository) -> str:
    checked_ref = await _git(
        repository.repository_path,
        "symbolic-ref",
        "--quiet",
        "HEAD",
    )
    if checked_ref != repository.base_ref:
        raise WorkbenchError(
            "Configured target ref is not checked out; refusing to operate on a different ref"
        )
    ref_sha = await _git(
        repository.repository_path,
        "rev-parse",
        "--verify",
        f"{repository.base_ref}^{{commit}}",
    )
    head_sha = await _git(repository.repository_path, "rev-parse", "HEAD")
    if head_sha != ref_sha:
        raise WorkbenchError("Checked-out target ref does not resolve to its current HEAD SHA")
    return head_sha


async def _require_clean_target(repository: WorkbenchRepository) -> None:
    if (
        await _git_exit_code(repository.repository_path, "diff", "--quiet") != 0
        or await _git_exit_code(repository.repository_path, "diff", "--cached", "--quiet") != 0
    ):
        raise WorkbenchError("Target repository has local changes; refusing to apply proposal")


async def _resolve_base_sha(repository: WorkbenchRepository) -> str:
    base_sha = await _checked_target_sha(repository)
    await _require_clean_target(repository)
    return base_sha


async def _create_worktree(repository: WorkbenchRepository, base_sha: str, turn_id: str) -> str:
    root = Path(repository.worktree_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    worktree = (root / turn_id).resolve()
    if root not in worktree.parents:
        raise WorkbenchError("Server worktree mapping escapes its configured root")
    if worktree.exists():
        raise WorkbenchError("Controller worktree path already exists")
    await _git(repository.repository_path, "worktree", "add", "--detach", str(worktree), base_sha)
    return str(worktree)


async def _git(
    cwd: str,
    *args: str,
    preserve_output: bool = False,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    result_code, stdout, stderr = await _git_result(cwd, *args, input_text=input_text, env=env)
    if result_code != 0:
        raise WorkbenchGitError(_bounded_text(stderr or stdout or "Git command failed", 4_000))
    return stdout if preserve_output else stdout.strip()


async def _git_exit_code(cwd: str, *args: str) -> int:
    result_code, _, _ = await _git_result(cwd, *args)
    return result_code


async def _git_result(
    cwd: str,
    *args: str,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        cwd,
        *args,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **(env or {})},
    )
    stdout, stderr = await process.communicate(
        None if input_text is None else input_text.encode("utf-8")
    )
    return (
        process.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _terminal_result(terminal: dict[str, Any]) -> dict[str, Any]:
    """Return only bounded, validated proposal fields from an adapter terminal."""

    raw_result = terminal.get("result")
    result = raw_result if isinstance(raw_result, dict) else terminal
    if not isinstance(result, dict):
        return {}
    decoded = _final_json_object(result.get("text"))
    patch = result.get("patch")
    if not isinstance(patch, str) and decoded is not None:
        patch = decoded.get("patch")
    if isinstance(patch, str) and len(patch.encode("utf-8")) > MAX_DIFF_BYTES:
        raise WorkbenchError("Runtime patch exceeds the configured output limit")

    tests = result.get("tests")
    if not isinstance(tests, list) and decoded is not None:
        tests = decoded.get("tests")
    return {
        **({"patch": patch} if isinstance(patch, str) and patch else {}),
        "tests": [test.model_dump(mode="json") for test in _test_evidence(tests)],
    }


def _final_json_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_TERMINAL_RESULT_BYTES:
        return None
    text = value.strip()
    if not text:
        return None
    candidates = [text, *(match.group(1) for match in FENCED_JSON_PATTERN.finditer(text))]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            return decoded
    for match in re.finditer(r"\{", text):
        try:
            decoded, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


def _test_evidence(value: Any) -> list[WorkbenchTestEvidence]:
    if not isinstance(value, list):
        return []
    evidence: list[WorkbenchTestEvidence] = []
    for item in value[:MAX_TESTS]:
        if not isinstance(item, dict):
            continue
        command = item.get("command")
        outcome = item.get("outcome")
        if not isinstance(command, str) or outcome not in {"passed", "failed", "unknown"}:
            continue
        evidence.append(
            WorkbenchTestEvidence(
                command=_bounded_text(_redact(command), 2_000),
                outcome=outcome,
                summary=_bounded_text(_redact(item.get("summary", "")), 8_000),
            )
        )
    return evidence


def _workbench_instructions(published_instructions: str) -> str:
    return (
        f"{published_instructions}\n\n"
        "You are executing a governed Workbench task. Work only in the supplied controller-owned "
        "isolated Git worktree. Inspect and propose a patch; "
        "never apply changes outside that worktree. "
        "When finished, return a JSON object with optional `patch` (unified diff) and `tests` "
        "([{command,outcome,summary}]); do not claim target application."
    ).strip()


def _bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = _redact(payload)
    serialized = json.dumps(redacted, ensure_ascii=False, default=str)
    if len(serialized.encode("utf-8")) <= MAX_EVENT_PAYLOAD_BYTES:
        return redacted if isinstance(redacted, dict) else {"value": redacted}
    return {"truncated": True, "preview": _bounded_text(serialized, MAX_EVENT_PAYLOAD_BYTES)}


def _redact(value: Any, *, key: str | None = None, text_limit: int = MAX_TEXT_BYTES) -> Any:
    if key is not None and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _redact(item_value, key=str(item_key), text_limit=text_limit)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, text_limit=text_limit) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, text_limit=text_limit) for item in value]
    if isinstance(value, str):
        return _bounded_text(SENSITIVE_TEXT_PATTERN.sub(r"\1\2[REDACTED]", value), text_limit)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _bounded_text(str(value), text_limit)


def _bounded_text(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore") + "…[truncated]"


def event_read(event: WorkbenchTurnEvent) -> WorkbenchEventRead:
    return WorkbenchEventRead(
        id=event.event_id,
        sequence=event.sequence,
        event_type=event.event_type,
        payload=event.payload,
        created_at=event.created_at,
    )


def proposal_read(proposal: WorkbenchProposal) -> WorkbenchProposalRead:
    return WorkbenchProposalRead(
        id=proposal.id,
        status=proposal.status,
        base_sha=proposal.base_sha,
        checkpoint_sha=proposal.checkpoint_sha,
        diff=proposal.diff,
        modified_files=proposal.modified_files,
        tests=[WorkbenchTestEvidence.model_validate(test) for test in proposal.tests],
        error_message=proposal.error_message,
        confirmed_at=proposal.confirmed_at,
    )


def turn_read(turn: WorkbenchTurn) -> WorkbenchTurnRead:
    output = None
    if turn.output is not None:
        proposal = proposal_read(turn.proposal) if turn.proposal is not None else None
        output = WorkbenchTurnOutput(
            modified_files=list(turn.output.get("modifiedFiles", [])),
            tests=[
                WorkbenchTestEvidence.model_validate(test) for test in turn.output.get("tests", [])
            ],
            diff=str(turn.output.get("diff", "")),
            proposal=proposal,
        )
    return WorkbenchTurnRead(
        id=turn.id,
        sequence=turn.sequence,
        request_id=turn.request_id,
        requirement=turn.requirement,
        runtime_id=turn.operations_agent_id,
        published_version=turn.published_version,
        runtime_type=turn.runtime_type,
        status=turn.status,
        base_sha=turn.base_sha,
        output=output,
        error_message=turn.error_message,
        created_at=turn.created_at,
        updated_at=turn.updated_at,
    )


def thread_read(thread: WorkbenchThread) -> WorkbenchThreadRead:
    return WorkbenchThreadRead(
        id=thread.id,
        repository_id=thread.repository_id,
        title=thread.title,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        turns=[turn_read(turn) for turn in thread.turns],
    )
