"""Token-authenticated Automation scheduler boundary for Celery workers."""

from datetime import timedelta

from fastapi import APIRouter, Depends

from backend.schemas.automation import (
    AutomationSchedulerTickRequest,
    AutomationSchedulerTickResult,
)
from backend.schemas.common import ApiResponse
from backend.security.internal_service import require_internal_service_token
from backend.services.automation_schedule_service import dispatch_due_automations
from backend.services.scheduled_run_recovery import list_queued_scheduled_run_ids

router = APIRouter(prefix="/internal/automations", tags=["internal-automations"])


@router.post(
    "/scheduler/tick",
    response_model=ApiResponse[AutomationSchedulerTickResult],
    dependencies=[Depends(require_internal_service_token)],
)
async def automation_scheduler_tick(body: AutomationSchedulerTickRequest) -> ApiResponse:
    runs = await dispatch_due_automations(
        body.fired_at - timedelta(seconds=90),
        body.fired_at,
    )
    return ApiResponse.ok(
        AutomationSchedulerTickResult(
            run_ids=[run.id for run in runs],
            occurrence_references=[run.trigger_reference or "" for run in runs],
            queued_run_ids=await list_queued_scheduled_run_ids(),
        )
    )
