"""Stable identities and checkpoint helpers for asynchronous workflow nodes.

The sidecar adapter owns submission and reconciliation. This module owns only
the platform identity that makes those operations retry-safe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageGenerationExecutionKey:
    run_id: str
    node_id: str
    attempt: int
    idempotency_key: str
    job_id: str

    def as_details(self) -> dict[str, object]:
        return {
            "runId": self.run_id,
            "nodeId": self.node_id,
            "attempt": self.attempt,
            "idempotencyKey": self.idempotency_key,
            "jobId": self.job_id,
        }


def image_generation_execution_key(
    run_id: str,
    node_id: str,
    attempt: int,
) -> ImageGenerationExecutionKey:
    """Return the unique platform identity for one node execution attempt."""

    if attempt < 1:
        raise ValueError("attempt must be at least 1")
    identity = f"opencli-admin/workflow-run/{run_id}/node/{node_id}/attempt/{attempt}"
    return ImageGenerationExecutionKey(
        run_id=run_id,
        node_id=node_id,
        attempt=attempt,
        idempotency_key=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{identity}/idempotency")),
        job_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{identity}/job")),
    )


__all__ = ["ImageGenerationExecutionKey", "image_generation_execution_key"]
