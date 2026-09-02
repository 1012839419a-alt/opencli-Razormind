"""Token-authenticated API-owned WS dispatch for durable scheduled Agent runs."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.operations_agent import (
    OperationsAgentRun,
    PublishedOperationsAgentVersion,
)
from backend.schemas.common import ApiResponse
from backend.schemas.operations_agent import (
    OperationsAgentRunRead,
    agent_contract_from_model_configuration,
    agent_runtime_binding_from_model_configuration,
)
from backend.security.internal_service import require_internal_service_token
from backend.services.agent_runtime_selection import (
    RuntimeSelectionError,
    select_agent_runtime,
)
from backend.services.operations_agent_runtime_service import schedule_operations_agent_run

router = APIRouter(
    prefix="/internal/operations-agent-runs",
    tags=["internal-operations-agent-runs"],
)


@router.post(
    "/{run_id}/dispatch",
    response_model=ApiResponse[OperationsAgentRunRead],
    dependencies=[Depends(require_internal_service_token)],
)
async def dispatch_scheduled_agent_run(run_id: str) -> ApiResponse:
    async with AsyncSessionLocal() as session:
        run = await session.get(OperationsAgentRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Operations Agent Run not found")
        if run.trigger_type != "scheduled":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Internal durable dispatch accepts scheduled runs only",
            )
        if run.status != "queued":
            return ApiResponse.ok(OperationsAgentRunRead.model_validate(run))
        version = await session.scalar(
            select(PublishedOperationsAgentVersion).where(
                PublishedOperationsAgentVersion.operations_agent_id
                == run.operations_agent_id,
                PublishedOperationsAgentVersion.version == run.published_version,
            )
        )
        if version is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Published Operations Agent version is missing",
            )
        try:
            binding = agent_runtime_binding_from_model_configuration(
                version.model_configuration
            )
            contract = agent_contract_from_model_configuration(version.model_configuration)
        except ValidationError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Published Operations Agent contract or runtime binding is invalid",
            ) from exc
        if binding is None or contract is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Published Operations Agent requires contract and runtime binding",
            )
        try:
            run.execution_binding = await select_agent_runtime(
                session,
                contract=contract,
                binding=binding,
            )
        except RuntimeSelectionError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(exc),
            ) from exc
        await session.commit()
        queued_response = OperationsAgentRunRead.model_validate(run)

    schedule_operations_agent_run(run_id)
    return ApiResponse.ok(queued_response)
