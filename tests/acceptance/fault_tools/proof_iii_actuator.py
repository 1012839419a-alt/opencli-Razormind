#!/usr/bin/env python3
"""Acceptance-only III bridge caller for 101st/102nd correlated records.

The actuator neither synthesizes callbacks nor writes a database.  Its response
is deliberately not a certificate input: only the public Admin boundary may be
normalized by the failure driver.
"""
from __future__ import annotations

import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class IngressRequest(BaseModel):
    phase: Literal["pre_snapshot_101", "late_102"]
    command_id: str = Field(min_length=1, max_length=256)
    attempt_id: str = Field(min_length=1, max_length=256)
    task_id: str = Field(min_length=1, max_length=256)
    trace_id: str = Field(min_length=1, max_length=256)
    expected_key: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=1, max_length=256)


@app.post("/actuate/ingress")
async def ingress(body: IngressRequest) -> dict[str, str]:
    bridge = os.environ.get("PROOF_III_BRIDGE_URL")
    token = os.environ.get("API_AUTH_TOKEN")
    if not bridge or not token:
        raise HTTPException(503, "real bridge identity is unavailable")
    payload = body.model_dump()
    try:
        response = httpx.post(
            bridge.rstrip("/") + "/api/v1/proof/iii-ingress",
            json=payload,
            headers={"X-API-Token": token, "Idempotency-Key": body.idempotency_key},
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "real bridge call failed") from exc
    # Do not propagate actor response/control state into a proof artifact.
    return {"status": "submitted"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
