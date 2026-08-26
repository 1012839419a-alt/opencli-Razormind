from types import SimpleNamespace

import pytest

from backend.channels.base import ChannelResult
from backend.workflow import gaojixing_runtime as runtime
from backend.workflow.gaojixing_runtime import (
    GAOJIXING_CAPABILITY_ID,
    GaojixingReadinessError,
    build_question_package,
    capture_live_doubao,
    map_capture_item,
)
from backend.workflow.opencli_hda_tracer import (
    _execute_gaojixing_source,
    _record_lineage_envelope,
    _store_record_sink_outputs,
)


def test_question_package_uses_runtime_question_and_stable_digest():
    first = build_question_package(
        node_params={"question": "configured", "sourceGroup": "research"},
        adapter_config={"site_session": "persistent"},
        runtime_payload={"question": "runtime"},
    )
    second = build_question_package(
        node_params={"question": "other", "sourceGroup": "research"},
        adapter_config={"site_session": "persistent"},
        runtime_payload={"question": "runtime"},
    )

    assert first.question == "runtime"
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_question_package_requires_effective_question():
    with pytest.raises(GaojixingReadinessError) as error:
        build_question_package(node_params={}, adapter_config={}, runtime_payload={})

    assert error.value.code == "gaojixing_question_required"


@pytest.mark.asyncio
async def test_capture_fails_closed_when_capability_missing(monkeypatch):
    package = build_question_package(
        node_params={"question": "q"}, adapter_config={}, runtime_payload={}
    )

    async def should_not_probe(self, _config):
        raise AssertionError("session probe must not run for a missing capability")

    monkeypatch.setattr(runtime.DoubaoResearchChannel, "health_check", should_not_probe)
    with pytest.raises(GaojixingReadinessError) as error:
        await capture_live_doubao(
            package=package,
            node_params={"capabilityId": "missing.capture"},
            adapter_config={},
            network_allowed=True,
        )

    assert error.value.code == "gaojixing_capability_missing"

@pytest.mark.asyncio
async def test_capture_uses_live_channel_after_health_probe(monkeypatch):
    package = build_question_package(
        node_params={"question": "q"}, adapter_config={}, runtime_payload={}
    )
    calls = []

    async def healthy(self, _config):
        calls.append("health")
        return True

    async def collect(self, config, parameters):
        calls.append((config["question"], parameters["question"]))
        return ChannelResult.ok(
            [{"content": "answer", "citations": [], "conversation_url": ""}]
        )

    monkeypatch.setattr(runtime.DoubaoResearchChannel, "health_check", healthy)
    monkeypatch.setattr(runtime.DoubaoResearchChannel, "collect", collect)
    result = await capture_live_doubao(
        package=package,
        node_params={},
        adapter_config={"capabilityId": GAOJIXING_CAPABILITY_ID},
        network_allowed=True,
    )

    assert result.success
    assert calls == ["health", ("q", "q")]


def test_capture_mapping_keeps_package_and_independent_evidence():
    package = build_question_package(
        node_params={"question": "q"}, adapter_config={}, runtime_payload={}
    )
    mapped = map_capture_item(
        {
            "content": "answer https://example.test/source",
            "citations": [{"url": "https://example.test/source"}],
            "citation_capture": "answer_url_extraction",
            "conversation_url": "https://www.doubao.com/chat/123",
        },
        package=package,
        workflow_id="wf",
        run_id="run",
        node_id="source",
        artifact_id="artifact",
    )

    evidence = mapped["gaojixing"]["evidence"]
    assert mapped["packageDigest"] == package.digest
    assert evidence["answer"]["artifactId"] == "artifact"
    assert evidence["citations"]["verified"] is False
    assert evidence["conversation"]["status"] == "captured"


class _Emitter:
    def __init__(self):
        self.events = []

    def emit(self, node, event_type, **kwargs):
        self.events.append((node.id, event_type, kwargs))


@pytest.mark.asyncio
async def test_hda_live_source_branch_maps_capture_output(monkeypatch):
    node = SimpleNamespace(
        id="gaojixing-source",
        kind="source",
        adapter=None,
        depends_on=[],
        params={"question": "configured", "sourceGroup": "gaojixing"},
        runtime={
            "binding": {
                "binding_id": "workflow.source.fetch",
                "input": {
                    "channelType": "doubao_research",
                    "liveMode": "live",
                    "adapterConfig": {"capabilityId": GAOJIXING_CAPABILITY_ID},
                },
            }
        },
    )
    body = SimpleNamespace(
        input=SimpleNamespace(payload={"question": "runtime"}),
        project=SimpleNamespace(
            id="workflow",
            agentPermissions=SimpleNamespace(canFetchNetwork=True),
        ),
    )
    emitter = _Emitter()
    outputs = {}

    async def fake_capture(**kwargs):
        assert kwargs["package"].question == "runtime"
        return ChannelResult.ok(
            [
                {
                    "content": "answer",
                    "citations": [{"url": "https://example.test"}],
                    "conversation_url": "https://www.doubao.com/chat/123",
                }
            ]
        )

    monkeypatch.setattr(
        "backend.workflow.opencli_hda_tracer.capture_live_doubao", fake_capture
    )
    await _execute_gaojixing_source(
        node,
        body=body,
        run_id="run",
        workflow_id="workflow",
        trace_id="trace",
        outputs_by_node=outputs,
        emitter=emitter,
        session=None,
    )

    item = outputs["gaojixing-source"][0]
    raw = item["raw"]
    assert raw["gaojixing"]["mode"] == "live"
    assert raw["gaojixing"]["evidence"]["packageDigest"] == raw["packageDigest"]
    assert item["lineage"][0]["artifact"] == "gaojixing.capture"
    assert [event[1] for event in emitter.events] == ["partial", "completed"]


@pytest.mark.asyncio
async def test_record_sink_persists_gaojixing_refs_and_collection_lineage(monkeypatch):
    package = build_question_package(
        node_params={"question": "q"}, adapter_config={}, runtime_payload={}
    )
    raw = map_capture_item(
        {
            "content": "answer",
            "citations": [{"url": "https://example.test/source"}],
            "conversation_url": "https://www.doubao.com/chat/123",
        },
        package=package,
        workflow_id="workflow",
        run_id="run",
        node_id="source",
        artifact_id="artifact",
    )
    source_node = SimpleNamespace(
        id="source",
        kind="source",
        adapter=None,
        depends_on=[],
        params={"sourceGroup": "gaojixing"},
        runtime={
            "binding": {
                "input": {"channelType": "doubao_research"},
                "binding_id": "workflow.source.fetch",
            }
        },
    )
    sink_node = SimpleNamespace(
        id="sink",
        kind="sink",
        adapter=None,
        depends_on=["source"],
        params={},
        runtime={"binding": {"binding_id": "workflow.record-sink.records", "input": {}}},
    )

    class _Session:
        async def flush(self):
            return None

    captured = {}

    async def fake_materialize(*args, **kwargs):
        return "source-id", "task-id"

    async def fake_store(*args, **kwargs):
        captured["lineage"] = kwargs["lineage"]
        return [SimpleNamespace(id="record-id")], 0

    monkeypatch.setattr(
        "backend.workflow.opencli_hda_tracer._materialize_source_task",
        fake_materialize,
    )
    monkeypatch.setattr("backend.workflow.opencli_hda_tracer.store_records", fake_store)
    stored, skipped = await _store_record_sink_outputs(
        sink_node,
        [{"raw": raw, "lineage": [{"artifact": "gaojixing.capture", "nodeId": "source"}]}],
        run_id="run",
        workflow_id="workflow",
        target="records",
        session=_Session(),
        runtime_nodes_by_id={"source": source_node},
        materialized_source_tasks={},
    )

    assert skipped == 0
    assert stored[0]["recordId"] == "record-id"
    assert stored[0]["raw"]["packageDigest"] == package.digest
    assert stored[0]["normalizedData"]["packageDigest"] == package.digest
    artifact_refs = captured["lineage"]["artifact_refs"]
    assert artifact_refs[1]["artifactId"] == "artifact"
    assert artifact_refs[1]["packageDigest"] == package.digest
    assert captured["lineage"]["collection_run_id"] == "run"


@pytest.mark.asyncio
async def test_gaojixing_delivery_distinguishes_transport_from_business_ack(monkeypatch):
    from backend.notifiers.base import NotificationSendResult
    from backend.workflow.webhook_delivery import execute_workflow_webhook_delivery

    package = build_question_package(
        node_params={"question": "q"}, adapter_config={}, runtime_payload={}
    )
    raw = map_capture_item(
        {"content": "answer", "citations": [], "conversation_url": ""},
        package=package,
        workflow_id="workflow",
        run_id="run",
        node_id="source",
        artifact_id="artifact",
    )
    captured = {}

    class _Notifier:
        async def send(self, config, payload):
            captured["payload"] = payload
            return NotificationSendResult(success=True, response_data=None)

    monkeypatch.setattr(
        "backend.workflow.webhook_delivery.get_notifier",
        lambda _kind: _Notifier(),
    )
    result = await execute_workflow_webhook_delivery(
        {"target": "business", "config": {"url": "https://example.test/hook"}},
        [{"raw": raw, "lineage": [{"nodeId": "source"}]}],
        workflow_id="workflow",
        run_id="run",
        node_id="notify",
    )

    assert result["transportStatus"] == "accepted"
    assert result["businessOutcome"] == "unconfirmed"
    assert result["ackEvidence"] is None
    assert result["packageDigest"] == package.digest
    assert captured["payload"].delivery_id == result["deliveryAttemptId"]
