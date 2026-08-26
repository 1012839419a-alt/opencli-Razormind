"""First-party Agent Starter installation for Workspace automations."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.automation import Automation
from backend.schemas.automation import (
    StarterInstallationPreview,
    StarterInstallationResult,
    StarterPreviewItem,
)


@dataclass(frozen=True)
class StarterDefinition:
    key: str
    name: str
    prompt: str
    schedule: str
    precheck: str | None = None
    executor: str = "codex"
    timezone: str = "UTC"
    session_mode: str = "fresh"
    approval_mode: str = "suggest_changes"

    def project(self) -> dict[str, str]:
        return {
            "starter_key": self.key,
            "lineage": "first-party-agent-starter",
        }


STARTER_DEFINITIONS: tuple[StarterDefinition, ...] = (
    StarterDefinition(
        key="daily-run-brief",
        name="运行简报 Agent",
        prompt="Prepare a concise daily run brief from the latest workspace activity and open work.",
        schedule="daily@09:00",
    ),
    StarterDefinition(
        key="weekly-system-review",
        name="系统回顾 Agent",
        prompt="Review the workspace system state, summarize trends, and identify actionable improvements.",
        schedule="weekly@09:00",
    ),
    StarterDefinition(
        key="anomaly-follow-up",
        name="异常跟进 Agent",
        prompt="Review unresolved anomalies, gather evidence, and propose the next safe follow-up actions.",
        schedule="weekdays@09:00",
    ),
)

STARTER_KEYS: tuple[str, ...] = tuple(
    definition.key for definition in STARTER_DEFINITIONS
)
AGENT_STARTERS = STARTER_DEFINITIONS



def _preview(
    workspace_id: str,
    installed_by_key: dict[str, Automation],
) -> StarterInstallationPreview:
    starters = [
        StarterPreviewItem(
            key=definition.key,
            name=definition.name,
            installed=definition.key in installed_by_key,
            automation_id=(
                installed_by_key[definition.key].id
                if definition.key in installed_by_key
                else None
            ),
        )
        for definition in STARTER_DEFINITIONS
    ]
    installed_count = sum(item.installed for item in starters)
    return StarterInstallationPreview(
        workspace_id=workspace_id,
        starters=starters,
        missing_count=len(starters) - installed_count,
        installed_count=installed_count,
    )


async def preview_starter_installation(
    session: AsyncSession,
    *,
    workspace_id: str,
) -> StarterInstallationPreview:
    rows = (
        await session.scalars(
            select(Automation).where(
                Automation.workspace_id == workspace_id,
                Automation.starter_key.in_(STARTER_KEYS),
            )
        )
    ).all()
    return _preview(workspace_id, {row.starter_key: row for row in rows if row.starter_key})


async def install_starters(
    session: AsyncSession,
    *,
    workspace_id: str,
    created_by_user_id: str,
) -> StarterInstallationResult:
    """Install missing starters atomically and return the resulting inventory.

    A nested transaction keeps a failed pack installation from leaving a partial
    set of rows behind. The unique workspace/starter key constraint is the final
    guard against duplicate rows when requests race.
    """

    async with session.begin_nested():
        rows = (
            await session.scalars(
                select(Automation)
                .where(
                    Automation.workspace_id == workspace_id,
                    Automation.starter_key.in_(STARTER_KEYS),
                )
                .with_for_update()
            )
        ).all()
        installed_by_key = {row.starter_key: row for row in rows if row.starter_key}
        skipped_count = len(installed_by_key)
        created_count = 0
        for definition in STARTER_DEFINITIONS:
            if definition.key in installed_by_key:
                continue
            row = Automation(
                workspace_id=workspace_id,
                starter_key=definition.key,
                name=definition.name,
                prompt=definition.prompt,
                precheck=definition.precheck,
                executor=definition.executor,
                schedule=definition.schedule,
                timezone=definition.timezone,
                session_mode=definition.session_mode,
                approval_mode=definition.approval_mode,
                project=definition.project(),
                enabled=False,
                created_by_user_id=created_by_user_id,
            )
            session.add(row)
            await session.flush()
            installed_by_key[definition.key] = row
            created_count += 1

    preview = _preview(workspace_id, installed_by_key)
    return StarterInstallationResult(
        **preview.model_dump(),
        created_count=created_count,
        skipped_count=skipped_count,
    )
