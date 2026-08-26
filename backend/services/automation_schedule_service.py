"""Durable Automation-to-Operations-Agent scheduling and run lineage."""

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend import ws_agent_manager
from backend.automation_schedule import automation_fire_times
from backend.database import AsyncSessionLocal, commit_session, queue_after_commit
from backend.models.automation import Automation
from backend.models.edge_node import EdgeNode
from backend.models.operations_agent import (
    AgentPermissionProfile,
    AgentProfileMode,
    OperationsAgentIdentity,
    OperationsAgentRun,
    PublishedOperationsAgentVersion,
)
from backend.schemas.operations_agent import (
    agent_contract_from_model_configuration,
    agent_runtime_binding_from_model_configuration,
    validate_agent_contract_payload,
)
from backend.services.operations_agent_runtime_service import schedule_operations_agent_run

logger = logging.getLogger(__name__)


class AutomationBindingError(ValueError):
    """The persisted Automation binding cannot safely produce a run."""


def automation_snapshot(automation: Automation) -> dict[str, Any]:
    """Freeze every mutable Automation execution field into run lineage."""
    return {
        "id": automation.id,
        "revision": automation.revision,
        "name": automation.name,
        "prompt": automation.prompt,
        "precheck": automation.precheck,
        "executor": automation.executor,
        "schedule": automation.schedule,
        "timezone": automation.timezone,
        "session_mode": automation.session_mode,
        "approval_mode": automation.approval_mode,
        "project": automation.project,
        "enabled": automation.enabled,
        "operations_agent_id": automation.operations_agent_id,
        "operations_agent_version": automation.operations_agent_version,
    }


def automation_run_input(
    automation: Automation,
    *,
    scheduled_for: datetime | None,
) -> dict[str, Any]:
    snapshot = automation_snapshot(automation)
    return {
        "automation": snapshot,
        "prompt": automation.prompt,
        "scheduled_for": scheduled_for.astimezone(UTC).isoformat() if scheduled_for else None,
    }


async def validate_automation_binding(
    session: AsyncSession,
    automation: Automation,
    *,
    scheduled_for: datetime | None = None,
    require_online: bool = False,
) -> tuple[OperationsAgentIdentity, PublishedOperationsAgentVersion, AgentPermissionProfile]:
    """Resolve and validate the exact Agent/version/profile/runtime contract."""
    if automation.operations_agent_id is None or automation.operations_agent_version is None:
        raise AutomationBindingError("Automation requires a pinned Operations Agent version")

    agent = await session.scalar(
        select(OperationsAgentIdentity).where(
            OperationsAgentIdentity.id == automation.operations_agent_id,
            OperationsAgentIdentity.workspace_id == automation.workspace_id,
        )
    )
    if agent is None:
        raise AutomationBindingError("Bound Operations Agent must belong to Automation Workspace")
    if agent.disabled:
        raise AutomationBindingError("Bound Operations Agent is disabled")

    version = await session.scalar(
        select(PublishedOperationsAgentVersion).where(
            PublishedOperationsAgentVersion.operations_agent_id == agent.id,
            PublishedOperationsAgentVersion.version == automation.operations_agent_version,
        )
    )
    if version is None:
        raise AutomationBindingError("Bound Operations Agent version is not published")

    profile = await session.scalar(
        select(AgentPermissionProfile).where(
            AgentPermissionProfile.operations_agent_id == agent.id,
            AgentPermissionProfile.version == agent.current_profile_version,
        )
    )
    if profile is None:
        raise AutomationBindingError("Bound Operations Agent profile is missing")
    if profile.mode == AgentProfileMode.LOW_RISK_AUTOMATIC:
        raise AutomationBindingError("Automation cannot bind a Low-Risk Automatic profile")
    if profile.mode != automation.approval_mode:
        raise AutomationBindingError(
            "Automation approval_mode must match the bound Operations Agent profile"
        )

    try:
        binding = agent_runtime_binding_from_model_configuration(version.model_configuration)
        contract = agent_contract_from_model_configuration(version.model_configuration)
    except ValidationError as exc:
        raise AutomationBindingError("Bound Operations Agent contract is invalid") from exc
    if binding is None:
        raise AutomationBindingError("Bound Operations Agent version has no Runtime Binding")

    node = await session.scalar(select(EdgeNode).where(EdgeNode.url == binding.agent_url))
    if node is None or node.protocol != "ws" or binding.runtime not in (node.runtimes or []):
        raise AutomationBindingError(
            "Bound Operations Agent Runtime is not advertised by its Fleet node"
        )
    if require_online and (
        node.status != "online"
        or not ws_agent_manager.is_connected(binding.agent_url)
    ):
        raise AutomationBindingError("Bound Operations Agent Runtime is not connected")

    if contract is not None:
        try:
            validate_agent_contract_payload(
                contract,
                "input_schema",
                automation_run_input(automation, scheduled_for=scheduled_for),
            )
            validate_agent_contract_payload(contract, "state_schema", {})
        except ValueError as exc:
            raise AutomationBindingError(
                f"Automation payload is incompatible with bound AgentContractV1: {exc}"
            ) from exc
    return agent, version, profile


async def create_bound_automation_run(
    session: AsyncSession,
    automation: Automation,
    *,
    trigger_type: str,
    started_by_user_id: str,
    scheduled_for: datetime | None = None,
) -> tuple[OperationsAgentRun, bool]:
    """Create one pinned run, deduplicating scheduled occurrences in the DB."""
    agent, version, profile = await validate_automation_binding(
        session,
        automation,
        scheduled_for=scheduled_for,
        require_online=trigger_type == "manual",
    )
    normalized_fire = (
        scheduled_for.astimezone(UTC).replace(second=0, microsecond=0)
        if scheduled_for is not None
        else None
    )
    trigger_reference = (
        f"automation:{automation.id}:{normalized_fire.strftime('%Y%m%dT%H%MZ')}"
        if normalized_fire is not None
        else None
    )
    run = OperationsAgentRun(
        workspace_id=automation.workspace_id,
        operations_agent_id=agent.id,
        published_version=version.version,
        profile_version=profile.version,
        trigger_type=trigger_type,
        trigger_reference=trigger_reference,
        automation_id=automation.id,
        automation_revision=automation.revision,
        automation_snapshot=automation_snapshot(automation),
        scheduled_for=normalized_fire,
        schedule_timezone=automation.timezone,
        target_resource_type="automation",
        target_resource_id=automation.id,
        input_payload=automation_run_input(automation, scheduled_for=normalized_fire),
        state_payload={},
        status="queued",
        started_by_user_id=started_by_user_id,
    )

    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        if normalized_fire is None:
            raise
        existing = await session.scalar(
            select(OperationsAgentRun).where(
                OperationsAgentRun.automation_id == automation.id,
                OperationsAgentRun.scheduled_for == normalized_fire,
            )
        )
        if existing is None:
            raise
        return existing, False

    if trigger_type == "manual":
        queue_after_commit(
            session,
            lambda run_id=run.id: schedule_operations_agent_run(run_id),
        )
    return run, True


async def create_failed_scheduled_automation_run(
    session: AsyncSession,
    automation: Automation,
    *,
    scheduled_for: datetime,
    error_message: str,
) -> tuple[OperationsAgentRun | None, bool]:
    """Persist a terminal occurrence when a previously enabled binding drifts."""
    if automation.operations_agent_id is None or automation.operations_agent_version is None:
        return None, False
    agent = await session.scalar(
        select(OperationsAgentIdentity).where(
            OperationsAgentIdentity.id == automation.operations_agent_id,
            OperationsAgentIdentity.workspace_id == automation.workspace_id,
        )
    )
    if agent is None:
        return None, False

    normalized_fire = scheduled_for.astimezone(UTC).replace(second=0, microsecond=0)
    run = OperationsAgentRun(
        workspace_id=automation.workspace_id,
        operations_agent_id=agent.id,
        published_version=automation.operations_agent_version,
        profile_version=agent.current_profile_version,
        trigger_type="scheduled",
        trigger_reference=(
            f"automation:{automation.id}:{normalized_fire.strftime('%Y%m%dT%H%MZ')}"
        ),
        automation_id=automation.id,
        automation_revision=automation.revision,
        automation_snapshot=automation_snapshot(automation),
        scheduled_for=normalized_fire,
        schedule_timezone=automation.timezone,
        target_resource_type="automation",
        target_resource_id=automation.id,
        input_payload=automation_run_input(
            automation,
            scheduled_for=normalized_fire,
        ),
        state_payload={},
        output_payload=None,
        error_message=error_message[:4000],
        status="failed",
        started_by_user_id=automation.created_by_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(OperationsAgentRun).where(
                OperationsAgentRun.automation_id == automation.id,
                OperationsAgentRun.scheduled_for == normalized_fire,
            )
        )
        if existing is None:
            raise
        return existing, False
    return run, True


async def claim_scheduled_automation_run(
    automation_id: str,
    scheduled_for: datetime,
) -> tuple[OperationsAgentRun | None, bool]:
    """Lock/recheck one enabled Automation and durably claim its occurrence."""
    normalized_fire = scheduled_for.astimezone(UTC).replace(second=0, microsecond=0)
    async with AsyncSessionLocal() as session:
        automation = await session.scalar(
            select(Automation).where(Automation.id == automation_id).with_for_update()
        )
        if automation is None or not automation.enabled:
            return None, False
        current_occurrences = automation_fire_times(
            automation.schedule,
            automation.timezone,
            normalized_fire - timedelta(seconds=1),
            normalized_fire,
        )
        if normalized_fire not in current_occurrences:
            logger.info(
                "Skipping stale Automation occurrence automation_id=%s scheduled_for=%s",
                automation_id,
                normalized_fire.isoformat(),
            )
            return None, False
        try:
            run, created = await create_bound_automation_run(
                session,
                automation,
                trigger_type="scheduled",
                started_by_user_id=automation.created_by_user_id,
                scheduled_for=normalized_fire,
            )
        except AutomationBindingError as exc:
            run, created = await create_failed_scheduled_automation_run(
                session,
                automation,
                scheduled_for=normalized_fire,
                error_message=str(exc),
            )
            if run is None:
                logger.error(
                    "Automation occurrence could not persist binding failure "
                    "automation_id=%s scheduled_for=%s: %s",
                    automation_id,
                    normalized_fire.isoformat(),
                    exc,
                )
                return None, False
            logger.warning(
                "Automation occurrence persisted binding failure automation_id=%s "
                "run_id=%s scheduled_for=%s: %s",
                automation_id,
                run.id,
                normalized_fire.isoformat(),
                exc,
            )
        await commit_session(session)

    if created:
        logger.info(
            "Scheduled Automation claimed automation_id=%s run_id=%s scheduled_for=%s "
            "trigger_reference=%s revision=%s agent_id=%s agent_version=%s profile_version=%s",
            automation_id,
            run.id,
            normalized_fire.isoformat(),
            run.trigger_reference,
            run.automation_revision,
            run.operations_agent_id,
            run.published_version,
            run.profile_version,
        )
    else:
        logger.info(
            "Scheduled Automation occurrence already claimed automation_id=%s "
            "run_id=%s scheduled_for=%s",
            automation_id,
            run.id,
            normalized_fire.isoformat(),
        )
    return run, created


async def dispatch_due_automations(
    window_start: datetime,
    window_end: datetime,
) -> list[OperationsAgentRun]:
    """Find due enabled Automations and claim every distinct occurrence once."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Automation.id, Automation.schedule, Automation.timezone).where(
                    Automation.enabled.is_(True)
                )
            )
        ).all()

    claimed: list[OperationsAgentRun] = []
    for automation_id, schedule, timezone_name in rows:
        for scheduled_for in automation_fire_times(
            schedule,
            timezone_name,
            window_start,
            window_end,
        ):
            run, created = await claim_scheduled_automation_run(automation_id, scheduled_for)
            if run is not None and created:
                claimed.append(run)
    return claimed
