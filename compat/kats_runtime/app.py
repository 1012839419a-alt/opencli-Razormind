from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from engine import CONTRACT_VERSION, KatsOperationError, KatsRuntime

MAX_REQUEST_BYTES = 8 * 1024 * 1024


class ExecuteRequest(BaseModel):
    operation: str = Field(min_length=1)
    inputItems: list[dict[str, Any]] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


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
    runtime: KatsRuntime = None,
    *,
    max_request_bytes: int = MAX_REQUEST_BYTES,
) -> FastAPI:
    kats_runtime = runtime or KatsRuntime()
    application = FastAPI(
        title="OpenCLI Kats Runtime",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    application.add_middleware(
        RequestByteLimitMiddleware,
        max_bytes=max_request_bytes,
    )

    @application.exception_handler(KatsOperationError)
    async def handle_operation_error(
        _request: Request, error: KatsOperationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request.invalid",
                    "message": "The request does not match the Kats runtime contract.",
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
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "contractVersion": CONTRACT_VERSION,
            "engine": kats_runtime.identity(),
            "capabilities": kats_runtime.capabilities(),
        }

    @application.post("/v1/execute")
    async def execute(request: ExecuteRequest) -> dict[str, Any]:
        return {
            "contractVersion": CONTRACT_VERSION,
            "engine": kats_runtime.identity(),
            "result": kats_runtime.execute(
                request.operation,
                request.inputItems,
                request.params,
            ),
        }

    return application


app = create_app()
