from __future__ import annotations

import hashlib
import importlib.util
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = ROOT / "tests/acceptance/non_bypass_failure_matrix.py"
spec = importlib.util.spec_from_file_location("non_bypass_failure_matrix", HARNESS_PATH)
assert spec and spec.loader
harness = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = harness
spec.loader.exec_module(harness)


class ComposeLoader(yaml.SafeLoader):
    pass


def _compose_tag(loader, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return loader.construct_sequence(node)


ComposeLoader.add_constructor("!override", _compose_tag)
ComposeLoader.add_constructor("!reset", _compose_tag)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def public_facts(scenario: str) -> dict:
    collection = {
        "blockingStage": "bridge_unavailable",
        "recoveryAction": "retry",
        "sideEffectUncertainty": True,
    }
    materialization = {
        "status": "unknown",
        "blocker": "none",
        "recoveryAction": "none",
        "manifestHash": None,
        "reconciliationRevision": None,
        "pageSnapshotAsOf": None,
    }
    graph = {
        "pin": None,
        "sequence": None,
        "readBlocker": "none",
        "mutationStatus": "none",
    }
    delivery = {
        "state": "none",
        "outcome": "none",
        "attemptCount": 0,
        "receiptHash": None,
        "reconciliation": "none",
    }
    if scenario == "admin-crash":
        collection = {
            "blockingStage": "none",
            "recoveryAction": "resume",
            "sideEffectUncertainty": True,
        }
    elif scenario == "signed-zero":
        collection = {
            "blockingStage": "none",
            "recoveryAction": "none",
            "sideEffectUncertainty": False,
        }
        materialization["status"] = "completed_empty"
    elif scenario in {"no-report", "crash-after-ingest"}:
        collection = {
            "blockingStage": "callback_missing",
            "recoveryAction": "recover",
            "sideEffectUncertainty": True,
        }
        materialization.update(
            status="indeterminate",
            blocker="missing_report",
            recoveryAction="recover",
        )
    elif scenario == "duplicate-dlq":
        collection = {
            "blockingStage": "duplicate",
            "recoveryAction": "recover",
            "sideEffectUncertainty": False,
        }
        materialization.update(
            status="completed",
            blocker="retained_dlq",
            recoveryAction="recover",
            manifestHash=_hash("manifest"),
            reconciliationRevision=1,
        )
    elif scenario == "query-page-race":
        collection = {
            "blockingStage": "none",
            "recoveryAction": "recover",
            "sideEffectUncertainty": False,
        }
        materialization.update(
            status="completed",
            recoveryAction="recover",
            manifestHash=_hash("manifest"),
            reconciliationRevision=1,
            pageSnapshotAsOf="2026-08-30T00:00:00Z",
        )
    elif scenario == "graph-stale-auth-cas-retract":
        collection = {
            "blockingStage": "none",
            "recoveryAction": "recover",
            "sideEffectUncertainty": False,
        }
        materialization.update(
            status="completed",
            recoveryAction="recover",
            manifestHash=_hash("manifest"),
            reconciliationRevision=1,
        )
        graph = {
            "pin": _hash("retracted-pin"),
            "sequence": 7,
            "readBlocker": "retract",
            "mutationStatus": "re_review_required",
        }
    elif scenario == "amendment-decision-conflict":
        collection = {
            "blockingStage": "none",
            "recoveryAction": "recover",
            "sideEffectUncertainty": False,
        }
        materialization.update(
            status="completed",
            recoveryAction="recover",
            manifestHash=_hash("amendment"),
            reconciliationRevision=2,
        )
        graph = {
            "pin": _hash("new-pin"),
            "sequence": 8,
            "readBlocker": "stale_manifest",
            "mutationStatus": "re_review_required",
        }
    elif scenario == "receiver-recovery":
        collection = {
            "blockingStage": "none",
            "recoveryAction": "recover",
            "sideEffectUncertainty": False,
        }
        materialization.update(
            status="completed",
            recoveryAction="recover",
            manifestHash=_hash("receiver"),
            reconciliationRevision=1,
        )
        graph = {
            "pin": _hash("receiver-pin"),
            "sequence": 3,
            "readBlocker": "none",
            "mutationStatus": "none",
        }
        delivery = {
            "state": "settled",
            "outcome": "accepted",
            "attemptCount": 3,
            "receiptHash": _hash("receiver-receipt"),
            "reconciliation": "signed_accepted",
        }
    elif scenario == "cancel-before-dispatch":
        delivery = {
            "state": "cancelled",
            "outcome": "none",
            "attemptCount": 0,
            "receiptHash": None,
            "reconciliation": "none",
        }
    elif scenario == "cancel-in-flight":
        delivery = {
            "state": "unknown",
            "outcome": "unknown",
            "attemptCount": 1,
            "receiptHash": None,
            "reconciliation": "unknown",
        }
    return {
        "scenario": scenario,
        "run": f"run-{scenario}",
        "fault": scenario,
        "actuator": {
            "name": "proof-iii-actuator",
            "invocationHash": _hash(f"actor-{scenario}"),
        },
        "correlation": {
            "commandId": "command",
            "attemptId": "attempt",
            "workflowRunId": "workflow",
            "hashes": {"public": _hash(scenario)},
        },
        "collection": collection,
        "materialization": materialization,
        "graph": graph,
        "delivery": delivery,
        "redactionProfile": "failure-v1",
        "timing": {
            "startedAt": 1,
            "completedAt": 2,
            "deadlineSeconds": 360,
        },
        "governanceReference": {
            "artifactId": f"artifact-{scenario}",
            "keyId": "key-1",
            "trustRootFingerprint": _hash("trust"),
        },
        "authority": "authenticated-scoped-public-api",
    }


@pytest.mark.parametrize("scenario", sorted(harness.SCENARIOS))
def test_every_matrix_row_normalizes_only_authenticated_public_facts(scenario: str):
    result = harness.normalize_public_facts(public_facts(scenario))
    assert result["schemaVersion"] == "ScenarioResultV1"
    assert result["forbiddenFacts"] == {
        "adminCreatedFallback": False,
        "lateEffectAbsenceClaim": False,
        "containerAuthority": False,
        "pageFinality": False,
    }


def test_internal_control_state_and_terminal_page_inference_are_rejected():
    facts = public_facts("query-page-race")
    facts["gateState"] = "released"
    rejection = (
        harness.PublicFactRejectedError
        if hasattr(harness, "PublicFactRejectedError")
        else harness.PublicFactRejected
    )
    with pytest.raises(rejection):
        harness.normalize_public_facts(facts)


def test_fixture_is_pinned_and_has_only_one_zero_and_hundred_operations():
    fixture = ROOT / "tests/acceptance/fixtures/opencli-failure-proof"
    recorded = (
        ROOT / "tests/acceptance/fixtures/opencli-failure-proof.sha256"
    ).read_text().split()[0]
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == recorded
    assert (
        "hundred" in fixture.read_text()
        and "zero" in fixture.read_text()
        and "one" in fixture.read_text()
    )


def test_overlay_has_no_host_ports_and_internal_fault_network():
    compose = yaml.load(
        (ROOT / "docker-compose.non-bypass-failure.yml").read_text(),
        Loader=ComposeLoader,
    )
    assert compose["networks"]["proof-fault"]["internal"] is True
    assert all("ports" not in service for service in compose["services"].values())
    assert {
        "proof-fault-gateway",
        "proof-iii-actuator",
        "proof-odp-query-pg-gate",
        "proof-governance",
        "proof-admin-control",
        "proof-odp-ingest-redis-mutator",
    } <= set(compose["services"])
    assert compose["services"]["proof-odp-ingest"]["environment"]["ODP_REDIS_URL"].startswith(
        "redis://proof-odp-ingest-redis-mutator:"
    )
    assert (
        compose["services"]["proof-odp-ingest-redis-mutator"]["environment"]["GATEWAY_MODE"]
        == "ingest-redis-payload-mutator"
    )


def test_callback_relay_routes_only_the_three_real_callback_paths(monkeypatch):
    relay_path = ROOT / "tests/acceptance/fault_tools/callback_relay.py"
    relay_spec = importlib.util.spec_from_file_location("callback_relay", relay_path)
    assert relay_spec and relay_spec.loader
    relay = importlib.util.module_from_spec(relay_spec)
    sys.modules[relay_spec.name] = relay
    relay_spec.loader.exec_module(relay)
    calls: list[str] = []

    def proxied(url: str, **kwargs):
        calls.append(url)
        import httpx
        assert kwargs["headers"] == {
            "authorization": "Bearer collector-fleet-token",
            "x-iii-bridge-token": "collector-bridge-token",
            "content-type": "application/json",
        }
        return httpx.Response(
            202,
            content=b'{"data":{}}',
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(relay.httpx, "post", proxied)
    client = TestClient(relay.app)
    response = client.post(
        "/api/v1/iii-collections/lifecycle",
        content=b"{}",
        headers={
            "authorization": "Bearer collector-fleet-token",
            "x-iii-bridge-token": "collector-bridge-token",
        },
    )
    assert response.status_code == 202
    assert "collector-fleet-token" not in response.text
    assert "collector-bridge-token" not in response.text
    assert calls == ["http://proof-admin:8000/api/v1/iii-collections/lifecycle"]
    assert client.post("/not-an-allowlisted-callback", content=b"{}").status_code == 404


def test_receipt_gate_counts_the_real_held_callback(monkeypatch):
    relay_path = ROOT / "tests/acceptance/fault_tools/callback_relay.py"
    relay_spec = importlib.util.spec_from_file_location("callback_relay_counter", relay_path)
    assert relay_spec and relay_spec.loader
    relay = importlib.util.module_from_spec(relay_spec)
    sys.modules[relay_spec.name] = relay
    relay_spec.loader.exec_module(relay)
    monkeypatch.setenv("API_AUTH_TOKEN", "gate-token")
    monkeypatch.setattr(
        relay.httpx,
        "post",
        lambda *_args, **_kwargs: __import__("httpx").Response(
            202, content=b'{"data":{}}', headers={"content-type": "application/json"}
        ),
    )
    with TestClient(relay.app) as client:
        headers = {"X-API-Token": "gate-token"}
        assert client.post("/_gate/receipt", json={"mode": "hold"}, headers=headers).status_code == 200
        with ThreadPoolExecutor(max_workers=1) as executor:
            callback = executor.submit(
                client.post,
                "/api/v1/iii-collections/ingress-receipts",
                content=b"{}",
            )
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                held = client.get("/_gate/receipt-held", headers=headers).json()
                if held["count"] == 1:
                    break
            assert held == {"count": 1}
            assert client.post("/_gate/receipt", json={"mode": "forward"}, headers=headers).status_code == 200
            assert callback.result(timeout=2).status_code == 202

@pytest.mark.parametrize("scenario", ["admin-crash", "no-report"])
def test_failure_driver_main_prints_its_fact_document(monkeypatch, capsys, scenario):
    driver_path = ROOT / "tests/acceptance/non_bypass_failure_driver.py"
    driver_spec = importlib.util.spec_from_file_location(
        f"failure_driver_main_{scenario}", driver_path
    )
    assert driver_spec and driver_spec.loader
    driver = importlib.util.module_from_spec(driver_spec)
    sys.modules[driver_spec.name] = driver
    driver_spec.loader.exec_module(driver)
    monkeypatch.setattr(
        driver,
        "admin_crash",
        lambda run, scenario: {"run": run, "scenario": scenario},
    )
    monkeypatch.setattr(sys, "argv", ["driver", "--scenario", scenario, "--run", "r1"])
    assert driver.main() == 0
    assert __import__("json").loads(capsys.readouterr().out) == {"run": "r1", "scenario": scenario}


def test_failure_runner_writes_selected_release_before_waiting():
    source = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(encoding="utf-8")
    gate_section = source[source.index('signal_name = "iii-ready"'):]
    release = 'f"{ledger.project}.{release_name}").write_text'
    assert gate_section.index(release) < gate_section.index("process.communicate(timeout=120)")



def test_published_run_retries_only_the_documented_visibility_409(monkeypatch):
    driver_path = ROOT / "tests/acceptance/non_bypass_failure_driver.py"
    driver_spec = importlib.util.spec_from_file_location("failure_driver_retry", driver_path)
    assert driver_spec and driver_spec.loader
    driver = importlib.util.module_from_spec(driver_spec)
    sys.modules[driver_spec.name] = driver
    driver_spec.loader.exec_module(driver)
    import httpx

    responses = iter([
        httpx.Response(409, text="Workflow must be published before API execution"),
        httpx.Response(200, json={"data": {"runId": "run-1"}}),
    ])

    class Client:
        def post(self, *_args, **_kwargs):
            return next(responses)

    monkeypatch.setattr(driver.time, "monotonic", lambda: 0)
    monkeypatch.setattr(driver.time, "sleep", lambda _seconds: None)
    assert driver._post_published_run(
        Client(),
        "http://api",
        "/run",
        {"idempotencyKey": "same"},
        {},
    ) == {"runId": "run-1"}


def test_crash_after_ingest_uses_isolated_two_phase_orchestration():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(encoding="utf-8")
    assert "def crash_after_ingest(" in driver
    assert all(
        name in driver
        for name in ("arm-report-hold", "ingress-observed", "collector-stopped")
    )
    assert "def _facts_from_crash_after_ingest(" in runner
    assert '"stop", "proof-collector"' in runner
    assert '{"mode":"hold"}' in runner


@pytest.mark.parametrize(
    ("scenario", "handler"),
    [
        ("admin-crash", "admin_crash"), ("no-report", "admin_crash"),
        ("signed-zero", "admin_crash"), ("iii-unreachable", "iii_unreachable"),
        ("crash-after-ingest", "crash_after_ingest"),
        ("ingest-redis-store-loss", "ingest_redis_store_loss"),
    ],
)
def test_failure_driver_dispatches_every_implemented_scenario(
    monkeypatch,
    capsys,
    scenario,
    handler,
):
    driver_path = ROOT / "tests/acceptance/non_bypass_failure_driver.py"
    driver_spec = importlib.util.spec_from_file_location(f"failure_driver_{scenario}", driver_path)
    assert driver_spec and driver_spec.loader
    driver = importlib.util.module_from_spec(driver_spec)
    sys.modules[driver_spec.name] = driver
    driver_spec.loader.exec_module(driver)
    monkeypatch.setattr(
        driver,
        "admin_crash",
        lambda run, name: {"handler": "admin_crash", "scenario": name},
    )
    monkeypatch.setattr(
        driver,
        "iii_unreachable",
        lambda run: {
            "handler": "iii_unreachable",
            "scenario": "iii-unreachable",
        },
    )
    monkeypatch.setattr(
        driver,
        "ingest_redis_store_loss",
        lambda run: {
            "handler": "ingest_redis_store_loss",
            "scenario": "ingest-redis-store-loss",
        },
    )
    monkeypatch.setattr(
        driver,
        "crash_after_ingest",
        lambda run: {
            "handler": "crash_after_ingest",
            "scenario": "crash-after-ingest",
        },
    )
    monkeypatch.setattr(sys, "argv", ["driver", "--scenario", scenario, "--run", "r1"])
    assert driver.main() == 0
    assert __import__("json").loads(capsys.readouterr().out)["handler"] == handler


def test_failure_overlay_routes_all_odp_writers_through_named_fault_gateways():
    compose = yaml.load(
        (ROOT / "docker-compose.non-bypass-failure.yml").read_text(),
        Loader=ComposeLoader,
    )
    services = compose["services"]
    assert {
        "proof-odp-http-gateway",
        "proof-odp-ingest-redis-gateway",
        "proof-odp-ingest-redis-mutator",
        "proof-odp-store-pg-gateway",
        "proof-odp-store-redis-gateway",
    } <= set(services)
    assert (
        services["proof-collector"]["environment"]["ODP_INGEST_URL"]
        == "http://proof-odp-http-gateway:8040"
    )
    assert (
        services["proof-bridge"]["environment"]["ODP_INGEST_URL"]
        == "http://proof-odp-http-gateway:8040"
    )
    assert (
        services["proof-odp-ingest"]["environment"]["ODP_REDIS_URL"]
        == "redis://proof-odp-ingest-redis-mutator:6379/2"
    )
    assert (
        services["proof-odp-store"]["environment"]["ODP_REDIS_URL"]
        == "redis://proof-odp-store-redis-gateway:6379/2"
    )
    assert (
        "@proof-odp-store-pg-gateway:5432/"
        in services["proof-odp-store"]["environment"]["ODP_DATABASE_URL"]
    )


def test_storage_loss_row_uses_public_helpers_and_single_scenario_runner_selection():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(encoding="utf-8")
    assert all(
        f"def {name}(" in driver
        for name in (
            "public_setup",
            "public_submit",
            "public_status",
            "public_materialize",
            "public_recover",
            "ingest_redis_store_loss",
        )
    )
    assert "store-redis-committed-xadd" in driver and "store-commit-ready" in driver
    assert 'parser.add_argument("--scenario", choices=SCENARIO_ORDER)' in runner
    assert "selected = (scenario,) if scenario else SCENARIO_ORDER" in runner


def test_duplicate_dlq_row_binds_replay_duplicate_and_retention_public_outcomes():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(encoding="utf-8")
    assert all(
        f"def {name}(" in driver
        for name in (
            "duplicate_dlq",
            "_wait_for_ingress_receipt",
            "_wait_for_materialization",
            "public_disposable_run",
        )
    )
    assert "ingest-redis-payload-mutator" in driver
    assert '"duplicate-dlq"' in driver
    assert all(
        name in driver
        for name in (
            "replay_same_intent",
            "duplicate_signed_receipt",
            "retained_dlq_materialization",
            "unknown_retention_materialization",
        )
    )
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(encoding="utf-8")
    assert '"duplicate-dlq"' in runner



def test_query_page_race_uses_real_iii_and_scoped_public_reconciliation_only():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(encoding="utf-8")
    actuator = (ROOT / "tests/acceptance/fault_tools/proof_iii_actuator.py").read_text(
        encoding="utf-8"
    )
    compose = yaml.load(
        (ROOT / "docker-compose.non-bypass-failure.yml").read_text(),
        Loader=ComposeLoader,
    )

    assert all(
        name in driver
        for name in (
            "def query_page_race(",
            "_wait_for_expected_key_report",
            "_wait_for_held_receipts",
            "_actuate_correlated_ingress",
            "_wait_for_query_page_gate",
            "collection_before_actor",
            "original_ingress_receipt",
            "materialization_after_recover",
            "record_present",
        )
    )
    assert '"query-page-race"' in runner
    assert "communicate(timeout=360)" in runner
    assert "odp.ingest::batch" in actuator
    assert "admin_collection" in actuator
    assert "actor credential denied" in actuator
    assert "PROOF_III_BRIDGE_URL" not in actuator
    assert compose["services"]["proof-iii-actuator"]["environment"]["PROOF_III_URL"] == (
        "ws://proof-iii:49134"
    )
    assert compose["services"]["proof-odp-query"]["environment"]["ODP_QUERY_DATABASE_URL"].startswith(
        "postgresql://proof:proof@proof-odp-query-pg-gate:"
    )


def test_failure_driver_dispatches_query_page_race(monkeypatch, capsys):
    driver = _failure_driver_module()
    monkeypatch.setattr(
        driver, "query_page_race", lambda run: {"handler": "query_page_race", "run": run}
    )
    monkeypatch.setattr(
        sys, "argv", ["driver", "--scenario", "query-page-race", "--run", "r1"]
    )

    assert driver.main() == 0
    assert __import__("json").loads(capsys.readouterr().out) == {
        "handler": "query_page_race",
        "run": "r1",
    }

def test_graph_stale_auth_cas_retract_uses_public_graph_boundaries():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(
        encoding="utf-8"
    )
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(
        encoding="utf-8"
    )

    assert all(
        name in driver
        for name in (
            "def graph_stale_auth_cas_retract(",
            "proof-reviewer",
            "wrong-capability verification",
            "stale reviewer retraction",
            "pinned_reference_mismatch",
            "reviewer legal retraction",
            "graph_final_authenticated_read_two",
            '"readBlocker": "retract"',
            '"mutationStatus": "re_review_required"',
        )
    )
    assert "AsyncSessionLocal" not in driver
    assert "StudioWorkspace" not in driver
    assert '"graph-stale-auth-cas-retract"' in runner
    assert "communicate(timeout=360)" in runner


def test_failure_driver_dispatches_graph_stale_auth_cas_retract(monkeypatch, capsys):
    driver = _failure_driver_module()
    monkeypatch.setattr(
        driver,
        "graph_stale_auth_cas_retract",
        lambda run: {"handler": "graph-stale-auth-cas-retract", "run": run},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["driver", "--scenario", "graph-stale-auth-cas-retract", "--run", "r1"],
    )

    assert driver.main() == 0
    assert __import__("json").loads(capsys.readouterr().out) == {
        "handler": "graph-stale-auth-cas-retract",
        "run": "r1",
    }


def test_amendment_decision_conflict_uses_public_duplicate_recovery_and_bindings():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(
        encoding="utf-8"
    )
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(
        encoding="utf-8"
    )

    assert all(
        name in driver
        for name in (
            "def amendment_decision_conflict(",
            "_fixture_one_event_id",
            "amendment_duplicate",
            "signed_duplicate_receipt",
            "materialization_n_plus_one",
            "manifest_superseded",
            "supersedesEventId",
            "old_blocked_pin_conflict",
            "changed_decision_replay_conflict",
            '"readBlocker": "stale_manifest"',
            '"mutationStatus": "re_review_required"',
        )
    )
    assert "AsyncSessionLocal" not in driver
    assert "StudioWorkspace" not in driver
    assert '"amendment-decision-conflict"' in runner
    assert "communicate(timeout=360)" in runner


def test_failure_driver_dispatches_amendment_decision_conflict(monkeypatch, capsys):
    driver = _failure_driver_module()
    monkeypatch.setattr(
        driver,
        "amendment_decision_conflict",
        lambda run: {"handler": "amendment-decision-conflict", "run": run},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["driver", "--scenario", "amendment-decision-conflict", "--run", "r1"],
    )

    assert driver.main() == 0
    assert __import__("json").loads(capsys.readouterr().out) == {
        "handler": "amendment-decision-conflict",
        "run": "r1",
    }


def test_receiver_recovery_driver_uses_public_attempts_and_signed_reconciliation():
    driver = (ROOT / "tests/acceptance/non_bypass_failure_driver.py").read_text(
        encoding="utf-8"
    )

    assert all(
        value in driver
        for value in (
            "def receiver_recovery(",
            "corrupt_mac",
            "withhold_response",
            "replace_with_503",
            "receiver-restart-ready",
            "/reconcile",
            '"state": "settled"',
            '"attemptCount": 3',
            "signed_{outcome}",
        )
    )
    assert "AsyncSessionLocal" not in driver
    assert "proof-controlled-receiver:8000" not in driver


def test_receiver_recovery_overlay_isolates_real_receiver_behind_tls_proxy():
    base = yaml.load(
        (ROOT / "docker-compose.non-bypass-acceptance.yml").read_text(encoding="utf-8"),
        Loader=ComposeLoader,
    )
    overlay = yaml.load(
        (ROOT / "docker-compose.non-bypass-failure.yml").read_text(encoding="utf-8"),
        Loader=ComposeLoader,
    )
    services = overlay["services"]
    proxy = services["proof-delivery-proxy"]

    assert proxy["networks"]["proof-failure-receiver"]["ipv4_address"] == (
        "${PROOF_RECEIVER_IP:-1.1.1.1}"
    )
    assert set(proxy["networks"]) == {
        "proof-failure-receiver",
        "proof-receiver-backend",
        "proof-fault",
    }
    assert services["proof-controlled-receiver"]["networks"] == [
        "proof-receiver-backend",
        "proof-receiver-db",
    ]
    assert services["proof-receiver-postgres"]["networks"] == ["proof-receiver-db"]
    assert "proof-receiver-backend" not in services["proof-admin"]["networks"]
    assert "proof-receiver-db" not in services["proof-admin-control"]["networks"]
    assert base["services"]["proof-controlled-receiver"]["networks"] == {
        "proof-receiver": {"ipv4_address": "8.8.8.8"}
    }


def test_receiver_recovery_runner_restarts_only_delivery_boundary():
    runner = (ROOT / "scripts/run_non_bypass_failure_matrix.py").read_text(
        encoding="utf-8"
    )

    assert '"receiver-recovery"' in runner
    assert "def _facts_from_receiver_recovery(" in runner
    assert '"restart",\n        "proof-delivery-proxy", "proof-controlled-receiver"' in runner
    assert "proof-receiver-postgres" not in runner.split(
        "def _facts_from_receiver_recovery(", 1
    )[1].split("def _facts_from_driver(", 1)[0]


def test_failure_driver_dispatches_receiver_recovery(monkeypatch, capsys):
    driver = _failure_driver_module()
    monkeypatch.setattr(
        driver, "receiver_recovery", lambda run: {"handler": "receiver-recovery", "run": run}
    )
    monkeypatch.setattr(
        sys, "argv", ["driver", "--scenario", "receiver-recovery", "--run", "r1"]
    )

    assert driver.main() == 0
    assert __import__("json").loads(capsys.readouterr().out) == {
        "handler": "receiver-recovery",
        "run": "r1",
    }


def _runner_module():
    path = ROOT / "scripts/run_non_bypass_failure_matrix.py"
    spec = importlib.util.spec_from_file_location("failure_runner_catalog", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def _failure_driver_module():
    path = ROOT / "tests/acceptance/non_bypass_failure_driver.py"
    spec = importlib.util.spec_from_file_location("non_bypass_failure_driver", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_storage_loss_source_binding_id_fits_public_api_bound():
    driver = _failure_driver_module()
    source_id = driver._storage_loss_source_id("run-" + "x" * 128, 3, "store-redis-committed-xadd")
    assert len(source_id) <= 33
    assert len(f"{source_id}-v1") <= 36


def test_catalog_build_occurs_once_before_multiple_fresh_rows(monkeypatch, tmp_path):
    runner = _runner_module()
    calls: list[str] = []
    monkeypatch.setattr(runner, "SCENARIO_ORDER", ("first", "second"))
    monkeypatch.setattr(runner, "_build_catalog", lambda *_args: calls.append("build") or {"digest": "catalog", "fixtureDigest": "fixture", "imageIds": {}})
    monkeypatch.setattr(runner, "_make_secrets", lambda _ledger: {})
    monkeypatch.setattr(runner, "_make_identities", lambda *_args: None)
    monkeypatch.setattr(runner, "_configure_failure_receiver", lambda *_args: None)
    monkeypatch.setattr(runner, "_fixture_digest", lambda: "fixture")
    monkeypatch.setattr(runner, "_admit", lambda ledger, *_args: calls.append(f"admit:{ledger.scenario}") or {})
    monkeypatch.setattr(runner, "_compose", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(runner, "_facts_from_driver", lambda ledger, *_args: {"run": ledger.project})
    monkeypatch.setattr(runner, "_govern", lambda _ledger, result, _now: result)
    monkeypatch.setattr(runner, "_cleanup", lambda *_args: None)
    runner.run_matrix(tmp_path, compose_file=ROOT / "docker-compose.non-bypass-acceptance.yml", overlay_file=ROOT / "docker-compose.non-bypass-failure.yml")
    assert calls == ["build", "admit:first", "admit:second"]

def test_catalog_uses_buildx_loaded_images_not_legacy_builder():
    runner = _runner_module()
    commands = runner._catalog_build_commands(
        {
            name: f"opencli-proof-{name}:catalog"
            for name in runner.CATALOG_NAMES
        },
        root_cache_bust="catalog",
    )
    assert len(commands) == 6
    assert all(command[:4] == ["docker", "buildx", "build", "--load"] for _, command in commands)
    root_command = dict(commands)["root"]
    assert ("--build-arg", "PROOF_CATALOG_DIGEST=catalog") in zip(
        root_command, root_command[1:]
    )


def test_per_row_admission_only_configs_and_inspects_prebuilt_catalog(monkeypatch, tmp_path):
    runner = _runner_module()
    ledger = runner.ScenarioLedger("first", "project", tmp_path, tmp_path)
    compose_calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(runner, "_compose", lambda _ledger, _env, _base, _overlay, *args, **_kwargs: compose_calls.append(args) or "pinned\nroot")
    monkeypatch.setattr(runner, "_inspect_images", lambda *_args, **_kwargs: {"pinned": "sha256:pinned", "root": "sha256:root"})
    monkeypatch.setattr(runner, "_fixture_digest", lambda: "fixture")
    monkeypatch.setattr(runner, "PINNED_III", "pinned")
    runner._admit(ledger, {}, ROOT / "docker-compose.non-bypass-acceptance.yml", ROOT / "docker-compose.non-bypass-failure.yml", {"fixtureDigest": "fixture", "digest": "catalog", "imageIds": {"pinned": "sha256:pinned", "root": "sha256:root"}})
    assert compose_calls == [("config", "--quiet"), ("config", "--images")]
