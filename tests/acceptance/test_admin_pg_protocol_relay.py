from __future__ import annotations

import pytest
from tests.acceptance.fault_tools import admin_pg_protocol_relay as relay


def _startup() -> bytes:
    return (8).to_bytes(4, "big") + (196608).to_bytes(4, "big")


def _frontend(message_type: bytes, body: bytes) -> bytes:
    return message_type + (len(body) + 4).to_bytes(4, "big") + body


def _backend(message_type: bytes, body: bytes) -> bytes:
    return _frontend(message_type, body)


def _parse(name: bytes, sql: bytes) -> relay.FrontendFrame:
    body = name + b"\0" + sql + b"\0"
    return relay.FrontendFrame(_frontend(b"P", body), b"P", body, name, sql)


def _bind(name: bytes, value: bytes) -> relay.FrontendFrame:
    body = b"\0" + name + b"\0" + value
    return relay.FrontendFrame(_frontend(b"B", body), b"B", body, name)


CLAIM = (
    b"SELECT delivery_executions.id FROM delivery_executions "
    b"WHERE delivery_executions.decision_id = $1::UUID FOR UPDATE"
)
RESERVE = (
    b"UPDATE delivery_executions SET state=$1::VARCHAR, lease_token=$2::VARCHAR, "
    b"lease_acquired_at=$3::TIMESTAMP WITH TIME ZONE, send_started_at=$4::TIMESTAMP "
    b"WITH TIME ZONE, reserved_attempt_number=$5::INTEGER WHERE delivery_executions.id = $6::UUID"
)
LOCKED_READ = (
    b"SELECT delivery_executions.id FROM delivery_executions "
    b"WHERE delivery_executions.id = $1::UUID FOR UPDATE"
)

def test_relay_arm_requires_the_authenticated_token(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "relay-token")

    with pytest.raises(relay.HTTPException) as denied:
        relay._authorize("wrong-token")

    assert denied.value.status_code == 401
    relay._authorize("relay-token")




def test_frontend_frames_accept_fragmented_and_coalesced_messages():
    frames = relay.FrontendFrames()
    parse = _frontend(b"P", b"claim\0" + CLAIM + b"\0")
    commit = _frontend(b"Q", b"COMMIT\0")

    assert frames.feed(_startup()[:3]) == []
    assert len(frames.feed(_startup()[3:] + parse[:7])) == 1
    parsed = frames.feed(parse[7:] + commit)

    assert [(frame.message_type, frame.statement_name, frame.sql) for frame in parsed] == [
        (b"P", b"claim", CLAIM),
        (b"Q", b"", b"COMMIT"),
    ]


def test_backend_frames_accept_fragmented_and_coalesced_messages():
    frames = relay.BackendFrames()
    commit = _backend(b"C", b"COMMIT\0")
    ready = _backend(b"Z", b"I")

    assert frames.feed(commit[:4]) == []
    parsed = frames.feed(commit[4:] + ready)

    assert [(frame.message_type, frame.body) for frame in parsed] == [
        (b"C", b"COMMIT\0"),
        (b"Z", b"I"),
    ]


def test_connection_flow_holds_only_post_commit_locked_execution_read():
    flow = relay.ConnectionFlow()

    assert flow.should_hold(_parse(b"claim", CLAIM)) is False
    assert flow.stage == "await_reservation"
    assert flow.should_hold(_parse(b"reserve", RESERVE)) is False
    assert flow.should_hold(_bind(b"reserve", b"pending")) is False
    assert flow.stage == "await_reservation"
    assert flow.should_hold(_bind(b"reserve", b"reserved")) is False
    assert flow.stage == "await_commit"
    assert flow.should_hold(
        relay.FrontendFrame(_frontend(b"Q", b"COMMIT\0"), b"Q", b"COMMIT\0", sql=b"COMMIT")
    ) is False
    assert flow.stage == "await_commit_success"

    # Interleaved backend traffic cannot open the gate until PostgreSQL confirms COMMIT.
    flow.observe_backend(relay.BackendFrame(_backend(b"D", b"payload"), b"D", b"payload"))
    assert flow.stage == "await_commit_success"
    flow.observe_backend(relay.BackendFrame(_backend(b"C", b"COMMIT\0"), b"C", b"COMMIT\0"))
    flow.observe_backend(relay.BackendFrame(_backend(b"Z", b"I"), b"Z", b"I"))
    assert flow.stage == "await_locked_read"

    assert flow.should_hold(_parse(b"locked", LOCKED_READ)) is True
    assert flow.stage == "held"


def test_interleaved_connection_does_not_inherit_armed_flow_state():
    first = relay.ConnectionFlow()
    second = relay.ConnectionFlow()

    assert first.should_hold(_parse(b"claim", CLAIM)) is False
    assert second.should_hold(_parse(b"locked", LOCKED_READ)) is False
    assert second.stage == "await_claim"
