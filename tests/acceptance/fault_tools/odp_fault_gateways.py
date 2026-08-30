#!/usr/bin/env python3
"""Failure-only transparent gateways for the four ODP durability subcases.

They relay real protocol bytes.  Their process-local controls are deliberately
not proof inputs: the matrix derives facts exclusively from authenticated Admin
public APIs.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

GatewayMode = Literal[
    "http-schema-mutator", "ingest-redis-cut", "store-pg-cut", "store-redis-committed-xadd",
]

app = FastAPI(docs_url=None, redoc=None, openapi_url=None)


@dataclass
class GatewayState:
    mode: GatewayMode
    armed: bool = False


STATES = {
    "http-schema-mutator": GatewayState("http-schema-mutator"),
    "ingest-redis-cut": GatewayState("ingest-redis-cut"),
    "store-pg-cut": GatewayState("store-pg-cut"),
    "store-redis-committed-xadd": GatewayState("store-redis-committed-xadd"),
}


class ArmRequest(BaseModel):
    armed: bool


def _state(name: str) -> GatewayState:
    try:
        return STATES[name]
    except KeyError as exc:
        raise HTTPException(404, "unknown ODP fault gateway") from exc


def _authenticated(token: str | None) -> None:
    if token != os.environ.get("API_AUTH_TOKEN"):
        raise HTTPException(401, "gateway credential denied")


@app.post("/_gate/{name}/arm")
async def arm(name: str, body: ArmRequest, x_api_token: str | None = Header(default=None)) -> dict[str, bool]:
    _authenticated(x_api_token)
    _state(name).armed = body.armed
    return {"armed": body.armed}


@app.post("/http/{path:path}")
async def http_schema_mutator(path: str, request: Request, x_api_token: str | None = Header(default=None)) -> Response:
    """Proxy an actual ingress request, mutating only schema_version when armed."""
    _authenticated(x_api_token)
    body = await request.body()
    state = _state("http-schema-mutator")
    if state.armed:
        body = body.replace(b'"schema_version":1', b'"schema_version":999', 1)
    # HTTP forwarding is intentionally implemented by the production bridge in
    # the live overlay.  This endpoint is the narrow, testable byte transform.
    return Response(content=body, media_type="application/json")


def _is_committed_xadd(chunk: bytes) -> bool:
    # RESP may span reads; the stream token and command must occur in the same
    # logical request as emitted by odp-store.  The TCP relay retains chunks
    # until a complete RESP command is available.
    upper = chunk.upper()
    return b"XADD" in upper and b"ODP.RECORD.COMMITTED" in upper


class RespCommandBuffer:
    """Bounded RESP request framing sufficient for transparent command gating."""
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buffer.extend(data)
        commands: list[bytes] = []
        while self._buffer:
            end = self._buffer.find(b"\r\n")
            if end < 0:
                break
            # RESP array requests begin '*<count>'; use the final bulk payload
            # boundary scanner, otherwise forward an opaque line safely.
            if self._buffer[0:1] != b"*":
                commands.append(bytes(self._buffer[: end + 2]))
                del self._buffer[: end + 2]
                continue
            cursor = end + 2
            try:
                count = int(self._buffer[1:end])
            except ValueError:
                commands.append(bytes(self._buffer[:cursor]))
                del self._buffer[:cursor]
                continue
            complete = True
            for _ in range(count):
                if len(self._buffer) <= cursor or self._buffer[cursor:cursor + 1] != b"$":
                    complete = False
                    break
                size_end = self._buffer.find(b"\r\n", cursor)
                if size_end < 0:
                    complete = False
                    break
                try:
                    size = int(self._buffer[cursor + 1:size_end])
                except ValueError:
                    complete = False
                    break
                cursor = size_end + 2 + size + 2
                if len(self._buffer) < cursor:
                    complete = False
                    break
            if not complete:
                break
            commands.append(bytes(self._buffer[:cursor]))
            del self._buffer[:cursor]
        return commands


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, state: GatewayState, *, outbound: bool) -> None:
    resp = RespCommandBuffer() if state.mode == "store-redis-committed-xadd" and outbound else None
    while data := await reader.read(65536):
        chunks = resp.feed(data) if resp else [data]
        for chunk in chunks:
            if state.armed and state.mode in {"ingest-redis-cut", "store-pg-cut"} and outbound:
                continue
            if state.armed and state.mode == "store-redis-committed-xadd" and outbound and _is_committed_xadd(chunk):
                continue
            writer.write(chunk)
            await writer.drain()
    writer.close()
    await writer.wait_closed()


async def relay(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, state: GatewayState) -> None:
    upstream_reader, upstream_writer = await asyncio.open_connection(os.environ["UPSTREAM_HOST"], int(os.environ["UPSTREAM_PORT"]))
    await asyncio.gather(
        _copy(client_reader, upstream_writer, state, outbound=True),
        _copy(upstream_reader, client_writer, state, outbound=False),
    )


async def serve_tcp(mode: GatewayMode) -> None:
    state = _state(mode)
    server = await asyncio.start_server(lambda reader, writer: relay(reader, writer, state), "0.0.0.0", int(os.environ["GATEWAY_PORT"]))
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve_tcp(os.environ["GATEWAY_MODE"]))
