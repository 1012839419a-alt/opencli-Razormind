from __future__ import annotations

import importlib.util
import json
import sys
import threading
import tempfile
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
    payload = b'{"batch_id":"batch-fixed","context":{"attempt":"a1"},"events":[{"schema_version":1,"event_id":"event-1","context":{"event":"keep"}},{"schema_version":2,"event_id":"event-2"}]}'
    plain = client.post("/ingest", content=payload, headers={"Authorization": "Bearer real-token", "Content-Type": "application/json"})
    assert plain.status_code == 207 and plain.content == b'{"upstream":"real"}'
    assert seen == {"path": "/ingest", "body": payload, "authorization": "Bearer real-token"}
    assert client.post("/_gate/http-schema-mutator/arm", json={"armed": True}, headers={"X-API-Token": "control-token"}).status_code == 200
    mutated = client.post("/ingest", content=payload, headers={"Authorization": "Bearer real-token", "Content-Type": "application/json"})
    assert mutated.status_code == 207
    assert json.loads(seen["body"]) == {"batch_id": "batch-fixed", "context": {"attempt": "a1"}, "events": [{"schema_version": 999, "event_id": "event-1", "context": {"event": "keep"}}, {"schema_version": 2, "event_id": "event-2"}]}
    upstream.shutdown()


def test_resp_buffer_forwards_fragmented_commands_and_identifies_only_committed_xadd():
    command = b"*3\r\n$4\r\nXADD\r\n$20\r\nodp.record.committed\r\n$1\r\n*\r\n"
    buffer = gateways.RespCommandBuffer()
    assert buffer.feed(command[:11]) == []
    assert buffer.feed(command[11:]) == [command]
    assert gateways._is_committed_xadd(command)
    assert not gateways._is_committed_xadd(b"*2\r\n$4\r\nXACK\r\n$3\r\nkey\r\n")



def _startup() -> bytes:
    return (8).to_bytes(4, "big") + (196608).to_bytes(4, "big")


def _frontend(kind: bytes, body: bytes) -> bytes:
    return kind + (len(body) + 4).to_bytes(4, "big") + body


def _backend(kind: bytes, body: bytes) -> bytes:
    return kind + (len(body) + 4).to_bytes(4, "big") + body


def test_store_redis_filter_requires_successful_commit_from_same_fragmented_relay(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / "commit-ready"
        monkeypatch.setenv("COMMIT_MARKER_PATH", str(marker))
        redis = gateways.GatewayState("store-redis-committed-xadd", armed=True)
        first, second = gateways.PostgresCommitObserver(), gateways.PostgresCommitObserver()
        first.feed_frontend(_startup()[:3])
        first.feed_frontend(_startup()[3:] + _frontend(b"P", b"stmt\0COMMIT\0"))
        second.feed_frontend(_startup() + _frontend(b"Q", b"SELECT 'Z'\0"))
        second.feed_backend(_backend(b"Z", b"I"))
        assert not marker.exists() and not gateways._redis_filter_enabled(redis)
        first.feed_backend(_backend(b"E", b"error") + _backend(b"Z", b"E"))
        assert not marker.exists()
        first.feed_frontend(_frontend(b"Q", b"COMMIT\0"))
        ready = _backend(b"Z", b"I")
        first.feed_backend(ready[:3])
        assert not marker.exists()
        first.feed_backend(ready[3:])
        assert marker.exists() and gateways._redis_filter_enabled(redis)
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
