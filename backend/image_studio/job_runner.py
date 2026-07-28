"""Database-agnostic orchestration for one image-generation job.

The runner owns the critical boundary between an InvokeAI queue completion and
an OpenCLI job completion: a queue item is not successful until every output
has been streamed into the platform asset store.  Database writes and storage
are injected as protocols so workers can supply transactional implementations
without coupling this module to SQLAlchemy or a concrete object store.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from backend.image_studio.adapter import InvokeJobBinding, InvokeQueueState

JobStatus = Literal[
    "queued",
    "submitted",
    "running",
    "ingesting",
    "succeeded",
    "blocked",
    "failed",
    "cancelled",
    "timed_out",
]


class ImageGenerationJobRecord(Protocol):
    id: str
    workspace_id: str
    project_id: str
    workflow_id: str
    node_id: str
    run_id: str
    attempt: int
    snapshot_id: str
    idempotency_key: str
    status: str
    invoke_batch_id: str | None
    invoke_queue_item_id: str | None
    invoke_session_id: str | None
    output_asset_ids: Sequence[str]
    error_code: str | None


class CanvasSnapshotRecord(Protocol):
    id: str
    workspace_id: str
    project_id: str
    workflow_id: str
    node_id: str
    executable_graph: Mapping[str, Any]


class ImageGenerationAdapter(Protocol):
    async def submit(
        self,
        binding: InvokeJobBinding,
        *,
        executable_graph: Mapping[str, Any],
        batch_data=(),
        runs: int = 1,
        prepend: bool = False,
    ) -> InvokeJobBinding: ...

    async def reconcile(
        self,
        binding: InvokeJobBinding,
        *,
        event_hint: Mapping[str, Any] | None = None,
    ) -> InvokeQueueState: ...

    async def cancel(self, binding: InvokeJobBinding) -> InvokeQueueState: ...

    def stream_image(self, image_name: str) -> AsyncIterator[bytes]: ...


class AssetIngestor(Protocol):
    async def __call__(
        self,
        *,
        workspace_id: str,
        project_id: str,
        job_id: str,
        image_name: str,
        chunks: AsyncIterator[bytes],
        provenance: Mapping[str, Any],
    ) -> str: ...


class JobCheckpoint(Protocol):
    async def __call__(self, result: JobRunnerResult) -> None: ...


@dataclass(frozen=True, slots=True)
class JobRunnerResult:
    """A complete set of fields the caller can persist atomically."""

    status: JobStatus
    invoke_batch_id: str | None = None
    invoke_queue_item_id: str | None = None
    invoke_session_id: str | None = None
    output_asset_ids: tuple[str, ...] = ()
    error_code: str | None = None
    error_detail: str | None = None

    def to_updates(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "invoke_batch_id": self.invoke_batch_id,
            "invoke_queue_item_id": self.invoke_queue_item_id,
            "invoke_session_id": self.invoke_session_id,
            "output_asset_ids": list(self.output_asset_ids),
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


class ImageGenerationJobRunner:
    def __init__(
        self,
        adapter: ImageGenerationAdapter,
        *,
        asset_ingestor: AssetIngestor,
        checkpoint: JobCheckpoint,
    ) -> None:
        self._adapter = adapter
        self._asset_ingestor = asset_ingestor
        self._checkpoint = checkpoint

    @staticmethod
    def binding_for(job: ImageGenerationJobRecord) -> InvokeJobBinding:
        return InvokeJobBinding(
            run_id=job.run_id,
            node_id=job.node_id,
            attempt=job.attempt,
            idempotency_key=job.idempotency_key,
            queue_item_id=job.invoke_queue_item_id,
            batch_id=job.invoke_batch_id,
            session_id=job.invoke_session_id,
        )

    async def submit(
        self,
        job: ImageGenerationJobRecord,
        snapshot: CanvasSnapshotRecord,
    ) -> JobRunnerResult:
        _validate_snapshot_scope(job, snapshot)
        binding = await self._adapter.submit(
            self.binding_for(job),
            executable_graph=snapshot.executable_graph,
        )
        return _result_from_binding(
            binding,
            status="submitted",
            output_asset_ids=job.output_asset_ids,
        )

    async def reconcile(
        self,
        job: ImageGenerationJobRecord,
        *,
        event_hint: Mapping[str, Any] | None = None,
    ) -> JobRunnerResult:
        binding = self.binding_for(job)
        try:
            state = await self._adapter.reconcile(binding, event_hint=event_hint)
        except Exception:
            # Transport adapters are required to sanitize their exceptions.  We
            # intentionally expose no exception text here as a second boundary.
            return _result_from_binding(
                binding,
                status="failed",
                output_asset_ids=job.output_asset_ids,
                error_code="invoke-reconcile-failed",
                error_detail="Image runtime reconciliation failed",
            )
        if state.status == "completed":
            return await self._ingest_outputs(job, binding, state)
        if state.status == "queued":
            return _result_from_binding(
                binding, status="submitted", output_asset_ids=job.output_asset_ids
            )
        if state.status == "running":
            return _result_from_binding(
                binding, status="running", output_asset_ids=job.output_asset_ids
            )
        if state.status == "cancelled":
            return _result_from_binding(
                binding, status="cancelled", output_asset_ids=job.output_asset_ids
            )
        if state.status == "blocked":
            return _result_from_binding(
                binding,
                status="blocked",
                output_asset_ids=job.output_asset_ids,
                error_code="invoke-runtime-blocked",
                error_detail="Image runtime cannot resolve the queue item",
            )
        return _result_from_binding(
            binding,
            status="failed",
            output_asset_ids=job.output_asset_ids,
            error_code="invoke-generation-failed",
            error_detail="Image generation failed",
        )

    async def retry_ingest(self, job: ImageGenerationJobRecord) -> JobRunnerResult:
        if job.invoke_queue_item_id is None:
            raise ValueError("retryable ingest requires an existing Invoke queue item")
        if job.error_code != "retryable-ingest":
            raise ValueError("job is not in a retryable ingest failure")
        # Reconciliation proves the original queue item is still completed.  It
        # never calls submit, so a storage retry cannot generate another image.
        return await self.reconcile(job, event_hint={"reason": "retry-ingest"})

    async def cancel(self, job: ImageGenerationJobRecord) -> JobRunnerResult:
        binding = self.binding_for(job)
        try:
            state = await self._adapter.cancel(binding)
        except Exception:
            return _result_from_binding(
                binding,
                status="failed",
                output_asset_ids=job.output_asset_ids,
                error_code="invoke-cancel-failed",
                error_detail="Image runtime cancellation failed",
            )
        status: JobStatus = "cancelled" if state.status == "cancelled" else "failed"
        return _result_from_binding(
            binding,
            status=status,
            output_asset_ids=job.output_asset_ids,
            error_code=None if status == "cancelled" else "invoke-cancel-not-confirmed",
            error_detail=(
                None
                if status == "cancelled"
                else "Image runtime did not confirm cancellation"
            ),
        )

    async def _ingest_outputs(
        self,
        job: ImageGenerationJobRecord,
        binding: InvokeJobBinding,
        state: InvokeQueueState,
    ) -> JobRunnerResult:
        existing_asset_ids = tuple(str(asset_id) for asset_id in job.output_asset_ids)
        if not state.image_names:
            return _result_from_binding(
                binding,
                status="failed",
                output_asset_ids=existing_asset_ids,
                error_code="invoke-no-output",
                error_detail="Image runtime completed without image outputs",
            )
        if len(existing_asset_ids) > len(state.image_names):
            return _result_from_binding(
                binding,
                status="failed",
                output_asset_ids=existing_asset_ids,
                error_code="asset-output-mismatch",
                error_detail="Stored assets do not match image runtime outputs",
            )

        ingesting = _result_from_binding(
            binding,
            status="ingesting",
            output_asset_ids=existing_asset_ids,
        )
        # This checkpoint is intentionally before the first download.  Worker or
        # process loss therefore resumes at ingest instead of generation.
        await self._checkpoint(ingesting)

        asset_ids = list(existing_asset_ids)
        for image_name in state.image_names[len(asset_ids) :]:
            try:
                asset_id = await self._asset_ingestor(
                    workspace_id=job.workspace_id,
                    project_id=job.project_id,
                    job_id=job.id,
                    image_name=image_name,
                    chunks=self._adapter.stream_image(image_name),
                    provenance={
                        "kind": "invokeai-generation",
                        "jobId": job.id,
                        "snapshotId": job.snapshot_id,
                        "imageName": image_name,
                    },
                )
                if not isinstance(asset_id, str) or not asset_id.strip():
                    raise ValueError("asset ingestor returned no asset identifier")
                asset_ids.append(asset_id.strip())
            except Exception:
                # Storage exception messages frequently contain signed URLs or
                # access keys.  Do not copy them into DB/API-visible job fields.
                return _result_from_binding(
                    binding,
                    status="failed",
                    output_asset_ids=asset_ids,
                    error_code="retryable-ingest",
                    error_detail="Generated image asset import failed and can be retried",
                )

        return _result_from_binding(
            binding,
            status="succeeded",
            output_asset_ids=asset_ids,
        )


def _validate_snapshot_scope(
    job: ImageGenerationJobRecord, snapshot: CanvasSnapshotRecord
) -> None:
    fields = ("workspace_id", "project_id", "workflow_id", "node_id")
    if job.snapshot_id != snapshot.id or any(
        getattr(job, field) != getattr(snapshot, field) for field in fields
    ):
        raise ValueError("Canvas snapshot does not belong to the image generation job")


def _result_from_binding(
    binding: InvokeJobBinding,
    *,
    status: JobStatus,
    output_asset_ids: Sequence[str],
    error_code: str | None = None,
    error_detail: str | None = None,
) -> JobRunnerResult:
    return JobRunnerResult(
        status=status,
        invoke_batch_id=binding.batch_id,
        invoke_queue_item_id=binding.queue_item_id,
        invoke_session_id=binding.session_id,
        output_asset_ids=tuple(str(asset_id) for asset_id in output_asset_ids),
        error_code=error_code,
        error_detail=error_detail,
    )
