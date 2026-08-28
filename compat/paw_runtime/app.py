from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

try:
    from .engine import (
        CONTRACT_VERSION,
        MAX_INPUT_CHARS,
        MAX_TOKENS,
        PawRuntime,
        PawRuntimeError,
    )
except ImportError:  # uvicorn runs app.py as a top-level module in the image.
    from engine import (
        CONTRACT_VERSION,
        MAX_INPUT_CHARS,
        MAX_TOKENS,
        PawRuntime,
        PawRuntimeError,
    )

MAX_REQUEST_BYTES = MAX_INPUT_CHARS * 12 + 1_024


class EnrichRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    programId: str = Field(min_length=1, max_length=128)
    input: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    maxTokens: int = Field(default=128, ge=1, le=MAX_TOKENS)


class RequestByteLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_length = dict(scope.get("headers", [])).get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self.max_bytes:
                    await _request_too_large(self.max_bytes)(scope, receive, send)
                    return
            except ValueError:
                pass

        messages: list[Message] = []
        received_bytes = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            received_bytes += len(message.get("body", b""))
            if received_bytes > self.max_bytes:
                await _request_too_large(self.max_bytes)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay, send)


def _request_too_large(max_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "request.too_large",
                "message": "The request body exceeds the configured request limit.",
                "details": {"maxBytes": max_bytes},
            }
        },
    )


def create_app(
    runtime: PawRuntime | None = None,
    *,
    max_request_bytes: int = MAX_REQUEST_BYTES,
) -> FastAPI:
    paw_runtime = runtime or PawRuntime()
    application = FastAPI(
        title="OpenCLI PAW Runtime",
        version="0.4.4",
        docs_url=None,
        redoc_url=None,
    )
    application.add_middleware(RequestByteLimitMiddleware, max_bytes=max_request_bytes)

    @application.exception_handler(PawRuntimeError)
    async def handle_runtime_error(_request: Request, error: PawRuntimeError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message, "details": {}}},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request.invalid",
                    "message": "The request does not match the PAW runtime contract.",
                    "details": {
                        "issues": [
                            {
                                "path": "/".join(str(part) for part in issue["loc"]),
                                "type": issue["type"],
                            }
                            for issue in error.errors()
                        ]
                    },
                }
            },
        )

    @application.get("/health")
    async def health() -> JSONResponse:
        ready = paw_runtime.is_ready()
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "not_ready",
                "ready": ready,
                "offline": True,
                "contractVersion": CONTRACT_VERSION,
                "program": paw_runtime.identity(),
            },
        )

    @application.post("/v1/enrich")
    async def enrich(request: EnrichRequest) -> dict[str, Any]:
        enrichment = await paw_runtime.enrich_async(
            request.programId, request.input, request.maxTokens
        )
        return {
            "contractVersion": CONTRACT_VERSION,
            "programId": paw_runtime.program_id,
            "enrichment": enrichment,
        }

    return application


app = create_app()
