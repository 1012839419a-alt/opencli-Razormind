import json

import pytest

from backend.security.question_bank_body_limit import (
    MAX_QUESTION_BANK_MULTIPART_BYTES,
    QuestionBankBodyLimitMiddleware,
)


def _scope(*, path: str, content_length: int | None = None) -> dict:
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("ascii")))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }


@pytest.mark.asyncio
async def test_declared_oversize_question_bank_body_is_rejected_before_inner_app():
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    sent = []

    async def receive():
        raise AssertionError("oversize request body must not be read")

    async def send(message):
        sent.append(message)

    middleware = QuestionBankBodyLimitMiddleware(inner)
    await middleware(
        _scope(
            path="/api/v1/workflows/runs/question-bank",
            content_length=MAX_QUESTION_BANK_MULTIPART_BYTES + 1,
        ),
        receive,
        send,
    )

    assert called is False
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"] == "QUESTION_BANK_RUN_TOO_LARGE"


@pytest.mark.asyncio
async def test_chunked_oversize_question_bank_body_is_stopped_before_handler_completes():
    completed = False

    async def inner(scope, receive, send):
        nonlocal completed
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        completed = True

    chunks = iter(
        [
            {
                "type": "http.request",
                "body": b"x" * MAX_QUESTION_BANK_MULTIPART_BYTES,
                "more_body": True,
            },
            {"type": "http.request", "body": b"x", "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    middleware = QuestionBankBodyLimitMiddleware(inner)
    await middleware(
        _scope(path="/api/v1/workspaces/w/projects/p/workflows/f/runs/question-bank"),
        receive,
        send,
    )

    assert completed is False
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_non_question_bank_route_is_not_limited_by_specialized_middleware():
    completed = False

    async def inner(scope, receive, send):
        nonlocal completed
        completed = True
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = QuestionBankBodyLimitMiddleware(inner)
    await middleware(
        _scope(path="/api/v1/workflows/runs", content_length=10**9),
        receive,
        send,
    )

    assert completed is True
    assert sent[0]["status"] == 204
