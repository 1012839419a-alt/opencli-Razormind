"""Bound question-bank multipart requests before Starlette spools them to disk."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

MAX_QUESTION_BANK_MULTIPART_BYTES = 6 * 1024 * 1024

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[dict[str, Any], ASGIReceive, ASGISend], Awaitable[None]]


class _QuestionBankBodyTooLargeError(Exception):
    pass


def _is_question_bank_run(scope: dict[str, Any]) -> bool:
    path = str(scope.get("path") or "")
    return (
        scope.get("type") == "http"
        and scope.get("method") == "POST"
        and path.startswith("/api/v1/")
        and path.endswith("/runs/question-bank")
    )


def _declared_content_length(scope: dict[str, Any]) -> int | None:
    for name, value in scope.get("headers") or ():
        if name.lower() != b"content-length":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


async def _send_too_large(send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
    body = json.dumps(
        {
            "success": False,
            "error": "QUESTION_BANK_RUN_TOO_LARGE",
            "message": "The question bank multipart request exceeds the 6 MiB limit.",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class QuestionBankBodyLimitMiddleware:
    """Reject oversized managed question-bank uploads before multipart parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int = MAX_QUESTION_BANK_MULTIPART_BYTES,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if not _is_question_bank_run(scope):
            await self.app(scope, receive, send)
            return

        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > self.max_bytes:
            await _send_too_large(send)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body") or b"")
                if received_bytes > self.max_bytes:
                    raise _QuestionBankBodyTooLargeError
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _QuestionBankBodyTooLargeError:
            if response_started:
                raise
            await _send_too_large(send)
