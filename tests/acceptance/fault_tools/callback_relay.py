#!/usr/bin/env python3
"""Three-route callback relay with a scenario-local primary/control switch.

Only the fixed III callback routes are proxied. Switch state is gate control,
never a proof input; callers obtain evidence from scoped Admin reads.
"""
from __future__ import annotations
import asyncio

import os
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

CALLBACKS = frozenset({
    "/api/v1/iii-collections/lifecycle",
    "/api/v1/iii-collections/expected-key-reports",
    "/api/v1/iii-collections/ingress-receipts",
})
UPSTREAMS = {
    "primary": os.environ.get("PROOF_PRIMARY_ADMIN", "http://proof-admin:8000"),
    "control": os.environ.get("PROOF_CONTROL_ADMIN", "http://proof-admin-control:8000"),
}
active: Literal["primary", "control"] = "primary"
report_mode: Literal["forward", "drop", "hold"] = "forward"
report_release = asyncio.Event()
report_diagnostic: dict[str, str | int] = {"status": "not-called"}
report_release.set()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Switch(BaseModel):
    upstream: Literal["primary", "control"]




class ReportMode(BaseModel):
    mode: Literal["forward", "drop", "hold"]


@app.post("/_gate/report")
async def set_report_mode(body: ReportMode, x_api_token: str | None = Header(default=None)) -> dict[str, str]:
    if x_api_token != os.environ.get("API_AUTH_TOKEN"):
        raise HTTPException(401, "gate credential denied")
    global report_mode
    report_mode = body.mode
    if body.mode == "hold":
        report_release.clear()
    else:
        report_release.set()
    return {"status": "updated"}


@app.get("/_gate/report-diagnostics")
async def get_report_diagnostics(x_api_token: str | None = Header(default=None)) -> dict[str, str | int]:
    if x_api_token != os.environ.get("API_AUTH_TOKEN"):
        raise HTTPException(401, "gate credential denied")
    return dict(report_diagnostic)


@app.post("/_gate/callback-upstream")
async def switch(body: Switch, x_api_token: str | None = Header(default=None)) -> dict[str, str]:
    if x_api_token != os.environ.get("API_AUTH_TOKEN"):
        raise HTTPException(401, "gate credential denied")
    global active
    active = body.upstream
    return {"status": "updated"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["POST"])
async def callback(path: str, request: Request) -> Response:
    route = "/" + path
    if route not in CALLBACKS:
        raise HTTPException(404, "callback route is not allowlisted")
    if route == "/api/v1/iii-collections/expected-key-reports":
        if report_mode == "drop":
            return Response(status_code=202, content=b'{"data":{"accepted":true}}', media_type="application/json")
        if report_mode == "hold":
            try:
                await asyncio.wait_for(report_release.wait(), 30)
            except TimeoutError as exc:
                raise HTTPException(504, "report gate timed out") from exc
    body = await request.body()
    headers = {"X-III-Bridge-Token": request.headers.get("x-iii-bridge-token", "")}
    try:
        response = httpx.post(UPSTREAMS[active] + route, content=body, headers=headers, timeout=30)
        if route == "/api/v1/iii-collections/expected-key-reports":
            report_diagnostic.clear()
            report_diagnostic.update(status=response.status_code, body=response.text[:512])
    except httpx.HTTPError as exc:
        raise HTTPException(502, "selected callback upstream is unavailable") from exc
    return Response(
        status_code=response.status_code,
        content=response.content,
        media_type=response.headers.get("content-type", "application/json"),
    )
