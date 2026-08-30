from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tests/acceptance/fault_tools/odp_fault_gateways.py"
spec = importlib.util.spec_from_file_location("odp_fault_gateways", PATH)
assert spec and spec.loader
gateways = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gateways
spec.loader.exec_module(gateways)


def test_http_mutator_forwards_to_real_upstream_and_preserves_context(monkeypatch):
    seen: dict[str, object] = {}

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.update(path=self.path, body=body, authorization=self.headers.get("Authorization"))
            self.send_response(207)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"upstream":"real"}')

        def log_message(self, *_args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("API_AUTH_TOKEN", "control-token")
    monkeypatch.setenv("HTTP_UPSTREAM_URL", f"http://127.0.0.1:{upstream.server_port}")
    gateways.STATES["http-schema-mutator"].armed = False
    client = TestClient(gateways.app)
    payload = b'{"schema_version":1,"command_id":"fixed","context":{"attempt":"a1"}}'
    plain = client.post("/http/ingest", content=payload, headers={"Authorization": "Bearer real-token", "Content-Type": "application/json"})
    assert plain.status_code == 207 and plain.content == b'{"upstream":"real"}'
    assert seen == {"path": "/ingest", "body": payload, "authorization": "Bearer real-token"}
    assert client.post("/_gate/http-schema-mutator/arm", json={"armed": True}, headers={"X-API-Token": "control-token"}).status_code == 200
    mutated = client.post("/http/ingest", content=payload, headers={"Authorization": "Bearer real-token", "Content-Type": "application/json"})
    assert mutated.status_code == 207
    assert json.loads(seen["body"]) == {"schema_version": 999, "command_id": "fixed", "context": {"attempt": "a1"}}
    upstream.shutdown()


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
