from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tests/acceptance/fault_tools/odp_fault_gateways.py"
spec = importlib.util.spec_from_file_location("odp_fault_gateways", PATH)
assert spec and spec.loader
gateways = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gateways
spec.loader.exec_module(gateways)


def test_http_mutator_forwards_unchanged_bytes_until_armed(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "control-token")
    client = TestClient(gateways.app)
    payload = b'{"schema_version":1,"command_id":"fixed"}'
    plain = client.post("/http/ingest", content=payload, headers={"X-API-Token": "control-token"})
    assert plain.status_code == 200 and plain.content == payload
    assert b"control-token" not in plain.content
    assert client.post("/_gate/http-schema-mutator/arm", json={"armed": True}, headers={"X-API-Token": "control-token"}).status_code == 200
    mutated = client.post("/http/ingest", content=payload, headers={"X-API-Token": "control-token"})
    assert mutated.content == b'{"schema_version":999,"command_id":"fixed"}'


def test_resp_buffer_forwards_fragmented_commands_and_identifies_only_committed_xadd():
    command = b"*3\r\n$4\r\nXADD\r\n$20\r\nodp.record.committed\r\n$1\r\n*\r\n"
    buffer = gateways.RespCommandBuffer()
    assert buffer.feed(command[:11]) == []
    assert buffer.feed(command[11:]) == [command]
    assert gateways._is_committed_xadd(command)
    assert not gateways._is_committed_xadd(b"*2\r\n$4\r\nXACK\r\n$3\r\nkey\r\n")


def test_cut_modes_arm_only_after_explicit_control(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "control-token")
    client = TestClient(gateways.app)
    for name in ("ingest-redis-cut", "store-pg-cut", "store-redis-committed-xadd"):
        gateways.STATES[name].armed = False
        assert client.post(f"/_gate/{name}/arm", json={"armed": True}, headers={"X-API-Token": "control-token"}).json() == {"armed": True}
        assert gateways.STATES[name].armed is True
    forbidden = client.post("/_gate/store-pg-cut/arm", json={"armed": False}, headers={"X-API-Token": "wrong"})
    assert forbidden.status_code == 401
    assert b"control-token" not in forbidden.content
