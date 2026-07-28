"""Narrow, private HTTP client for the pinned InvokeAI sidecar.

There is deliberately no generic ``request`` or ``proxy`` method.  Adding a
sidecar operation requires adding a named method and a contract test so the
browser-facing application can never accidentally become a transparent
InvokeAI gateway.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

ALLOWED_INVOKE_OPERATIONS = frozenset(
    {
        "enqueue_batch",
        "get_queue_item",
        "cancel_queue_item",
        "stream_image",
        "list_models",
        "list_missing_models",
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_BEARER = re.compile(r"(?i)\bbearer\s+[^\s;,]+")


@dataclass(frozen=True, slots=True)
class InvokeAIConnection:
    """Server-only connection material for one fixed sidecar."""

    base_url: str = field(repr=False)
    jwt: str | None = field(default=None, repr=False)
    timeout_seconds: float = field(default=60.0, repr=False)

    def __post_init__(self) -> None:
        normalized = self.base_url.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("InvokeAI base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("InvokeAI base_url must not contain credentials, query, or fragment")
        if self.timeout_seconds <= 0:
            raise ValueError("InvokeAI timeout_seconds must be positive")
        object.__setattr__(self, "base_url", normalized)

    def __repr__(self) -> str:
        return "InvokeAIConnection(<private sidecar>)"


class InvokeAIClientError(RuntimeError):
    """Sanitized sidecar failure safe to pass to platform service code."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.retryable = retryable


class InvokeAIClient:
    """Allowlisted InvokeAI API operations used by the platform adapter."""

    def __init__(
        self,
        connection: InvokeAIConnection,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.connection = connection
        self._transport = transport

    async def enqueue_batch(
        self,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        return await self._json_operation(
            "enqueue_batch",
            "POST",
            "/api/v1/queue/default/enqueue_batch",
            json=dict(payload),
            extra_headers={"Idempotency-Key": idempotency_key},
        )

    async def get_queue_item(self, queue_item_id: str) -> dict[str, Any]:
        item_id = _checked_identifier(queue_item_id, "queue_item_id")
        return await self._json_operation(
            "get_queue_item",
            "GET",
            f"/api/v1/queue/default/i/{item_id}",
        )

    async def cancel_queue_item(self, queue_item_id: str) -> dict[str, Any]:
        item_id = _checked_identifier(queue_item_id, "queue_item_id")
        return await self._json_operation(
            "cancel_queue_item",
            "PUT",
            f"/api/v1/queue/default/i/{item_id}/cancel",
        )

    async def list_models(self) -> dict[str, Any]:
        return await self._json_operation("list_models", "GET", "/api/v2/models/")

    async def list_missing_models(self) -> dict[str, Any]:
        return await self._json_operation(
            "list_missing_models", "GET", "/api/v2/models/missing"
        )

    async def stream_image(self, image_name: str) -> AsyncIterator[bytes]:
        safe_name = _checked_identifier(image_name, "image_name")
        operation = "stream_image"
        try:
            async with self._client() as client:
                async with client.stream(
                    "GET",
                    f"/api/v1/images/i/{safe_name}/full",
                    headers=self._headers(),
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                        raise self._http_error(operation, response.status_code, body)
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except InvokeAIClientError:
            raise
        except httpx.TimeoutException as exc:
            raise self._transport_error(operation, exc, retryable=True) from None
        except httpx.HTTPError as exc:
            raise self._transport_error(operation, exc, retryable=True) from None

    async def _json_operation(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        json: object | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        # Defense in depth: internal refactors cannot silently create a fifth
        # outbound operation without updating the audited allowlist.
        if operation not in ALLOWED_INVOKE_OPERATIONS:
            raise ValueError(f"unsupported InvokeAI operation: {operation}")
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        try:
            async with self._client() as client:
                response = await client.request(method, path, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise self._transport_error(operation, exc, retryable=True) from None
        except httpx.HTTPError as exc:
            raise self._transport_error(operation, exc, retryable=True) from None

        if response.status_code >= 400:
            raise self._http_error(operation, response.status_code, response.text[:1000])
        try:
            payload = response.json()
        except ValueError:
            raise InvokeAIClientError(
                f"InvokeAI {operation} returned invalid JSON",
                operation=operation,
                status_code=response.status_code,
            ) from None
        if not isinstance(payload, dict):
            raise InvokeAIClientError(
                f"InvokeAI {operation} returned a non-object response",
                operation=operation,
                status_code=response.status_code,
            )
        return _sanitize_payload(payload, self.connection)

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": self.connection.base_url,
            "timeout": self.connection.timeout_seconds,
            "follow_redirects": False,
            "trust_env": False,
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    def _headers(self) -> dict[str, str]:
        if not self.connection.jwt:
            return {}
        return {"Authorization": f"Bearer {self.connection.jwt}"}

    def _http_error(self, operation: str, status_code: int, body: str) -> InvokeAIClientError:
        safe_body = _sanitize_text(body, self.connection)
        suffix = f": {safe_body}" if safe_body else ""
        return InvokeAIClientError(
            f"InvokeAI {operation} failed ({status_code}){suffix}",
            operation=operation,
            status_code=status_code,
            retryable=status_code >= 500 or status_code == 429,
        )

    def _transport_error(
        self, operation: str, exc: BaseException, *, retryable: bool
    ) -> InvokeAIClientError:
        return InvokeAIClientError(
            f"InvokeAI {operation} transport failed: "
            f"{_sanitize_text(str(exc), self.connection)}",
            operation=operation,
            retryable=retryable,
        )


def _checked_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} contains unsupported characters")
    return value


def _sanitize_text(value: str, connection: InvokeAIConnection) -> str:
    safe = value.replace(connection.base_url, "<private-sidecar>")
    if connection.jwt:
        safe = safe.replace(connection.jwt, "***REDACTED***")
    return _BEARER.sub("***REDACTED***", safe)


def _sanitize_payload(value: Any, connection: InvokeAIConnection) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value, connection)
    if isinstance(value, list):
        return [_sanitize_payload(item, connection) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item, connection) for key, item in value.items()}
    return value
