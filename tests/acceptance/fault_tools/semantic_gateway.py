#!/usr/bin/env python3
"""Internal-only semantic gateway used by the #37 Compose overlay.

It exposes named gates instead of packet-level mock transports.  Gate state is
intentionally process-local control state and is never emitted as proof.
"""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request

ALLOWLIST = frozenset({"iii", "callback", "ingest", "redis", "store", "notification", "tls", "resp", "page"})
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)


def _gate(name: str) -> asyncio.Event:
    if name not in ALLOWLIST:
        raise HTTPException(404, "unknown semantic gate")
    return _events[name]


@app.post("/gates/{name}/hold")
async def hold(name: str) -> dict[str, str]:
    _gate(name).clear()
    return {"status": "held"}


@app.post("/gates/{name}/release")
async def release(name: str) -> dict[str, str]:
    _gate(name).set()
    return {"status": "released"}


@app.post("/gates/{name}/wait")
async def wait(name: str, request: Request) -> dict[str, str]:
    timeout = float(request.query_params.get("timeout", "30"))
    if timeout <= 0 or timeout > 30:
        raise HTTPException(422, "gate timeout must be between zero and thirty seconds")
    try:
        await asyncio.wait_for(_gate(name).wait(), timeout)
    except TimeoutError as exc:
        raise HTTPException(504, "semantic gate timed out") from exc
    return {"status": "released"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "scope": os.environ.get("PROOF_SCENARIO", "unbound")}
