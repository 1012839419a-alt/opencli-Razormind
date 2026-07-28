"""Stable platform semantics over InvokeAI's pinned queue API."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from backend.image_studio.invoke_client import InvokeAIClient, InvokeAIClientError

PlatformQueueStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled", "blocked"
]


@dataclass(frozen=True, slots=True)
class InvokeJobBinding:
    """One durable OpenCLI attempt mapped to one Invoke queue item."""

    run_id: str
    node_id: str
    attempt: int
    idempotency_key: str
    queue_item_id: str | None = None
    batch_id: str | None = None
    session_id: str | None = None

    @classmethod
    def create(cls, run_id: str, node_id: str, attempt: int) -> InvokeJobBinding:
        if not run_id or not node_id:
            raise ValueError("run_id and node_id are required")
        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        identity = f"{run_id}\x1f{node_id}\x1f{attempt}".encode()
        digest = hashlib.sha256(identity).hexdigest()
        return cls(run_id, node_id, attempt, f"opencli-image:{digest}")

    def with_submission(
        self,
        *,
        queue_item_id: str,
        batch_id: str | None = None,
        session_id: str | None = None,
    ) -> InvokeJobBinding:
        if self.queue_item_id is not None and self.queue_item_id != queue_item_id:
            raise ValueError("binding is already attached to a different queue item")
        return replace(
            self,
            queue_item_id=str(queue_item_id),
            batch_id=str(batch_id) if batch_id is not None else None,
            session_id=str(session_id) if session_id is not None else None,
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "nodeId": self.node_id,
            "attempt": self.attempt,
            "idempotencyKey": self.idempotency_key,
            "queueItemId": self.queue_item_id,
            "batchId": self.batch_id,
            "sessionId": self.session_id,
        }


@dataclass(frozen=True, slots=True)
class InvokeQueueState:
    status: PlatformQueueStatus
    raw_status: str
    image_names: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rawStatus": self.raw_status,
            "imageNames": list(self.image_names),
            "error": self.error,
        }


class InvokeAIAdapter:
    """Compiles graph batches and reconciles queue state via REST.

    Socket events are accepted only as wake-up hints.  ``reconcile`` always
    reads the queue item over REST before returning a state transition.
    """

    def __init__(self, client: InvokeAIClient) -> None:
        self._client = client

    async def submit(
        self,
        binding: InvokeJobBinding,
        *,
        executable_graph: Mapping[str, Any],
        batch_data: Sequence[Sequence[Mapping[str, Any]]] = (),
        runs: int = 1,
        prepend: bool = False,
    ) -> InvokeJobBinding:
        if binding.queue_item_id is not None:
            return binding
        payload = self.compile_batch(
            executable_graph=executable_graph,
            batch_data=batch_data,
            runs=runs,
            prepend=prepend,
        )
        response = await self._client.enqueue_batch(
            payload, idempotency_key=binding.idempotency_key
        )
        queue_item_id = _queue_item_id(response)
        if queue_item_id is None:
            raise InvokeAIClientError(
                "InvokeAI enqueue_batch returned no queue item identifier",
                operation="enqueue_batch",
            )
        return binding.with_submission(
            queue_item_id=queue_item_id,
            batch_id=_nested_string(response, "batch", "batch_id")
            or _optional_string(response.get("batch_id")),
            session_id=_optional_string(response.get("session_id")),
        )

    @staticmethod
    def compile_batch(
        *,
        executable_graph: Mapping[str, Any],
        batch_data: Sequence[Sequence[Mapping[str, Any]]] = (),
        runs: int = 1,
        prepend: bool = False,
    ) -> dict[str, Any]:
        if not executable_graph:
            raise ValueError("executable_graph must not be empty")
        if runs < 1:
            raise ValueError("runs must be at least 1")
        return {
            "batch": {
                "graph": copy.deepcopy(dict(executable_graph)),
                "data": copy.deepcopy(
                    [[dict(field) for field in group] for group in batch_data]
                ),
                "runs": runs,
            },
            "prepend": bool(prepend),
        }

    async def reconcile(
        self,
        binding: InvokeJobBinding,
        *,
        event_hint: Mapping[str, Any] | None = None,
    ) -> InvokeQueueState:
        del event_hint  # Explicitly non-authoritative; it is only a wake-up signal.
        if binding.queue_item_id is None:
            return InvokeQueueState("blocked", "not_submitted", error="job is not submitted")
        payload = await self._client.get_queue_item(binding.queue_item_id)
        raw_status = str(payload.get("status") or "unknown").strip().lower()
        return InvokeQueueState(
            status=_platform_status(raw_status),
            raw_status=raw_status,
            image_names=_image_names(payload),
            error=_error_message(payload),
        )

    async def cancel(self, binding: InvokeJobBinding) -> InvokeQueueState:
        if binding.queue_item_id is None:
            return InvokeQueueState("cancelled", "not_submitted")
        payload = await self._client.cancel_queue_item(binding.queue_item_id)
        raw_status = str(payload.get("status") or "canceled").strip().lower()
        return InvokeQueueState(
            status=_platform_status(raw_status),
            raw_status=raw_status,
            image_names=_image_names(payload),
            error=_error_message(payload),
        )

    def stream_image(self, image_name: str) -> AsyncIterator[bytes]:
        return self._client.stream_image(image_name)


def _queue_item_id(payload: Mapping[str, Any]) -> str | None:
    direct = payload.get("item_id") or payload.get("queue_item_id")
    if direct is not None:
        return str(direct)
    item_ids = payload.get("item_ids")
    if isinstance(item_ids, list) and item_ids:
        return str(item_ids[0])
    queue_items = payload.get("queue_items")
    if isinstance(queue_items, list) and queue_items and isinstance(queue_items[0], Mapping):
        nested = queue_items[0].get("item_id")
        return str(nested) if nested is not None else None
    return None


def _nested_string(payload: Mapping[str, Any], key: str, nested_key: str) -> str | None:
    nested = payload.get(key)
    if not isinstance(nested, Mapping):
        return None
    return _optional_string(nested.get(nested_key))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _platform_status(status: str) -> PlatformQueueStatus:
    if status in {"pending", "queued", "enqueued"}:
        return "queued"
    if status in {"in_progress", "running"}:
        return "running"
    if status in {"completed", "succeeded"}:
        return "completed"
    if status in {"canceled", "cancelled"}:
        return "cancelled"
    if status in {"failed", "error"}:
        return "failed"
    return "blocked"


def _image_names(payload: Mapping[str, Any]) -> tuple[str, ...]:
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        return ()
    names: list[str] = []
    for output in outputs:
        if not isinstance(output, Mapping):
            continue
        candidate = output.get("image_name")
        image = output.get("image")
        if candidate is None and isinstance(image, Mapping):
            candidate = image.get("image_name")
        if isinstance(candidate, str) and candidate and candidate not in names:
            names.append(candidate)
    return tuple(names)


def _error_message(payload: Mapping[str, Any]) -> str | None:
    error = payload.get("error") or payload.get("error_message")
    if isinstance(error, Mapping):
        error = error.get("message") or error.get("detail") or error.get("code")
    return _optional_string(error)
