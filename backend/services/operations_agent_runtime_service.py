"""Dispatch Operations Agent runs through the existing edge-runtime protocol."""

import asyncio
import logging
from typing import Any, cast

from pydantic import JsonValue, ValidationError
from sqlalchemy import select, update

from backend.database import AsyncSessionLocal
from backend.models.operations_agent import (
    AgentPermissionProfile,
    AgentProfileMode,
    OperationsAgentRun,
    PublishedOperationsAgentVersion,
)
from backend.schemas.operations_agent import (
    agent_contract_from_model_configuration,
    agent_runtime_binding_from_model_configuration,
    validate_agent_contract_payload,
)
from backend.ws_agent_manager import send_agent_task

logger = logging.getLogger(__name__)

# ponytail: process-local dispatch ownership; move this run_id map to a durable
# broker if Operations Agent runs must survive API process loss mid-flight.
_ACTIVE_DISPATCHES: dict[str, asyncio.Task[None]] = {}


def schedule_operations_agent_run(run_id: str) -> None:
    task = asyncio.create_task(dispatch_operations_agent_run(run_id))
    _ACTIVE_DISPATCHES[run_id] = task
    task.add_done_callback(lambda completed: _forget_dispatch(run_id, completed))


def cancel_operations_agent_run(run_id: str) -> None:
    task = _ACTIVE_DISPATCHES.get(run_id)
    if task is not None:
        task.cancel()




def _forget_dispatch(run_id: str, task: asyncio.Task[None]) -> None:
    if _ACTIVE_DISPATCHES.get(run_id) is task:
        _ACTIVE_DISPATCHES.pop(run_id, None)


async def dispatch_operations_agent_run(run_id: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            claimed = await session.execute(
                update(OperationsAgentRun)
                .where(OperationsAgentRun.id == run_id)
                .where(OperationsAgentRun.status == "queued")
                .values(status="running")
            )
            await session.commit()
            if getattr(claimed, "rowcount", 0) != 1:
                return

        async with AsyncSessionLocal() as session:
            run = await session.get(OperationsAgentRun, run_id)
            if run is None:
                return
            version = await session.scalar(
                select(PublishedOperationsAgentVersion)
                .where(
                    PublishedOperationsAgentVersion.operations_agent_id == run.operations_agent_id
                )
                .where(PublishedOperationsAgentVersion.version == run.published_version)
            )
            if version is None:
                await _fail_run(run_id, "Published Agent Version is missing")
                return
            profile = await session.scalar(
                select(AgentPermissionProfile)
                .where(AgentPermissionProfile.operations_agent_id == run.operations_agent_id)
                .where(AgentPermissionProfile.version == run.profile_version)
            )
            if profile is None:
                await _fail_run(run_id, "Pinned Agent Permission Profile is missing")
                return
            if profile.mode == AgentProfileMode.LOW_RISK_AUTOMATIC:
                await _fail_run(
                    run_id,
                    "Automatic Operations Agent runs require the governed action gateway",
                )
                return
            try:
                binding = agent_runtime_binding_from_model_configuration(
                    version.model_configuration
                )
                contract = agent_contract_from_model_configuration(version.model_configuration)
            except ValidationError:
                await _fail_run(run_id, "Published Operations Agent configuration is invalid")
                return
            if binding is None:
                await _fail_run(run_id, "Published Agent Version has no Runtime Binding")
                return

            runtime_input = cast(dict[str, Any], run.input_payload)
            runtime_config = dict(binding.config)
            configured_timeout = runtime_config.get("timeout_seconds")
            if (
                not isinstance(configured_timeout, (int, float))
                or isinstance(configured_timeout, bool)
                or configured_timeout < binding.dispatch_timeout_seconds
            ):
                # The edge runtime must not expire before the governed outer
                # deep-run profile. Binding validation supplies the hard
                # ceiling; this fills/raises the inner timeout to that profile.
                runtime_config["timeout_seconds"] = binding.dispatch_timeout_seconds
            runtime_config["permission_mode"] = profile.mode

        state_contract_error: str | None = None

        async def on_event(event: dict[str, Any]) -> None:
            nonlocal state_contract_error
            if event.get("type") != "state":
                return
            state = event.get("state")
            if not isinstance(state, dict):
                state_contract_error = "Runtime state event must contain an object"
                return
            if contract is not None:
                try:
                    validate_agent_contract_payload(
                        contract,
                        "state_schema",
                        cast(dict[str, JsonValue], state),
                    )
                except ValueError as exc:
                    state_contract_error = str(exc)
                    return
            await _persist_state(run_id, state)

        terminal = await send_agent_task(
            binding.agent_url,
            {
                "runtime": binding.runtime,
                "workflow": binding.workflow,
                "instructions": version.instructions,
                "input": runtime_input,
                "config": runtime_config,
                "session_id": None,
            },
            on_event,
            timeout=float(binding.dispatch_timeout_seconds),
        )

        if state_contract_error is not None:
            await _fail_run(
                run_id,
                f"Runtime state violates AgentContractV1: {state_contract_error}",
            )
            return
        if terminal.get("type") == "error":
            await _fail_run(run_id, str(terminal.get("message") or "Runtime failed"))
            return
        if terminal.get("type") != "done":
            await _fail_run(run_id, "Runtime returned no terminal done/error event")
            return
        output = terminal.get("result") or {}
        if not isinstance(output, dict):
            await _fail_run(run_id, "Runtime output must be an object")
            return
        if contract is not None:
            try:
                validate_agent_contract_payload(
                    contract,
                    "output_schema",
                    cast(dict[str, JsonValue], output),
                )
            except ValueError as exc:
                await _fail_run(
                    run_id,
                    f"Runtime output violates AgentContractV1: {exc}",
                )
                return
        await _complete_run(run_id, output)
    except Exception as exc:
        logger.exception("Operations Agent run dispatch failed | run_id=%s", run_id)
        await _fail_run(run_id, str(exc))


async def _persist_state(run_id: str, state: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(OperationsAgentRun)
            .where(OperationsAgentRun.id == run_id)
            .where(OperationsAgentRun.status == "running")
            .values(state_payload=state)
        )
        await session.commit()


async def _complete_run(run_id: str, output: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(OperationsAgentRun)
            .where(OperationsAgentRun.id == run_id)
            .where(OperationsAgentRun.status == "running")
            .values(
                output_payload=output,
                error_message=None,
                status="completed",
            )
        )
        await session.commit()


async def _fail_run(run_id: str, message: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(OperationsAgentRun)
            .where(OperationsAgentRun.id == run_id)
            .where(OperationsAgentRun.status.in_(("queued", "running")))
            .values(error_message=message[:4000], status="failed")
        )
        await session.commit()
