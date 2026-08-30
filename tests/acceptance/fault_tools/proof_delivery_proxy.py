"""Authenticated failure proxy for the controlled-receiver delivery boundary.

The proxy is the only receiver endpoint visible to Admin in failure proofs.  It
always forwards the request to the isolated TLS receiver before withholding or
replacing its response, so public execution/reconciliation APIs—not proxy
state—remain the only proof facts.
"""
from __future__ import annotations

import asyncio
import os
from enum import StrEnum

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel


class DeliveryProxyMode(StrEnum):
    PASS_THROUGH = "pass_through"
    CORRUPT_MAC = "corrupt_mac"
    WITHHOLD_RESPONSE = "withhold_response"
    REPLACE_WITH_503 = "replace_with_503"


class ModeRequest(BaseModel):
    mode: DeliveryProxyMode


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_mode = DeliveryProxyMode.PASS_THROUGH


def _configured_token() -> str:
    token = os.environ.get("API_AUTH_TOKEN")
    if not token:
        raise RuntimeError("API_AUTH_TOKEN is required")
    return token


def _upstream_url(path: str) -> str:
    base = os.environ.get("PROOF_RECEIVER_BACKEND_URL")
    if not base:
        raise RuntimeError("PROOF_RECEIVER_BACKEND_URL is required")
    return base.rstrip("/") + path


def _forward_headers(request: Request) -> dict[str, str]:
    corrupt_mac = (
        _mode is DeliveryProxyMode.CORRUPT_MAC
        and request.url.path.endswith("/deliver")
    )
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in {"host", "content-length"}
        and (not corrupt_mac or name.lower() != "x-controlled-receiver-mac")
    }
    if corrupt_mac:
        headers["X-Controlled-Receiver-Mac"] = "sha256=corrupted-by-proof-proxy"
    return headers


async def _forward(request: Request, path: str) -> httpx.Response:
    body = await request.body()
    verify = os.environ.get("SSL_CERT_FILE", "/run/proof/ca.pem")
    async with httpx.AsyncClient(verify=verify, timeout=10) as client:
        return await client.request(
            request.method,
            _upstream_url(path),
            content=body,
            headers=_forward_headers(request),
        )


@app.post("/_gate/delivery")
async def set_mode(
    body: ModeRequest, x_api_token: str | None = Header(default=None)
) -> dict[str, str]:
    if x_api_token != _configured_token():
        raise HTTPException(401, "delivery proxy credential denied")
    global _mode
    _mode = body.mode
    return {"status": "configured"}


@app.api_route(
    "/api/v1/controlled-receiver/v2/{action}", methods=["POST"], include_in_schema=False
)
async def proxy_delivery(action: str, request: Request) -> Response:
    if action not in {"deliver", "status"}:
        raise HTTPException(404, "receiver action is unavailable")
    response = await _forward(request, f"/api/v1/controlled-receiver/v2/{action}")
    if action == "deliver":
        if _mode is DeliveryProxyMode.WITHHOLD_RESPONSE:
            await asyncio.sleep(31)
        elif _mode is DeliveryProxyMode.REPLACE_WITH_503:
            return Response(status_code=503)
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers={
            name: value
            for name, value in response.headers.items()
            if name.lower() in {"content-type", "content-length"}
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
