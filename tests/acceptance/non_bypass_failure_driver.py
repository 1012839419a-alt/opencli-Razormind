#!/usr/bin/env python3
"""In-network public-API driver for the first #37 failure scenario."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from backend.database import AsyncSessionLocal
from backend.models.studio import StudioWorkspace
from tests.acceptance.non_bypass_vertical import graph as _base_graph


def _data(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise RuntimeError(f"{response.status_code}: {response.text[:300]}")
    value = response.json()
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
        raise RuntimeError("public API did not return a data object")
    return value["data"]


def _post(
    client: httpx.Client,
    base: str,
    path: str,
    body: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    return _data(client.post(base + path, json=body, headers=headers))


def _get(client: httpx.Client, base: str, path: str, headers: dict[str, str]) -> dict[str, Any]:
    return _data(client.get(base + path, headers=headers))


def _post_published_run(
    client: httpx.Client,
    base: str,
    path: str,
    body: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while True:
        response = client.post(base + path, json=body, headers=headers)
        if not (
            response.status_code == 409
            and "Workflow must be published before API execution" in response.text
            and time.monotonic() < deadline
        ):
            return _data(response)
        time.sleep(0.5)


async def _seed(workspace_id: str, slug: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(StudioWorkspace(id=workspace_id, name="Failure proof", slug=slug))
        await session.commit()

def _graph() -> dict[str, Any]:
    return _base_graph()


def _coordination(name: str) -> Path:
    root = Path("/proof-artifacts/coordination")
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def _failure_result(
    *,
    scenario: str,
    run: str,
    fault: str,
    command_id: str,
    attempt_id: str,
    workflow_run_id: str,
    hashes: dict[str, Any],
    collection: dict[str, Any],
    materialization: dict[str, Any],
    mutation_status: str = "none",
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "run": run,
        "fault": fault,
        "actuator": {
            "name": "proof-iii-actuator",
            "invocationHash": hashlib.sha256(command_id.encode()).hexdigest(),
        },
        "correlation": {
            "commandId": command_id,
            "attemptId": attempt_id,
            "workflowRunId": workflow_run_id,
            "hashes": hashes,
        },
        "collection": collection,
        "materialization": materialization,
        "graph": {
            "pin": None,
            "sequence": None,
            "readBlocker": "none",
            "mutationStatus": mutation_status,
        },
        "delivery": {
            "state": "none",
            "outcome": "none",
            "attemptCount": 0,
            "receiptHash": None,
            "reconciliation": "none",
        },
        "redactionProfile": "failure-v1",
        "timing": {"startedAt": 0, "completedAt": 1, "deadlineSeconds": 360},
        "governanceReference": {
            "artifactId": "pending",
            "keyId": "pending",
            "trustRootFingerprint": "pending",
        },
        "authority": "authenticated-scoped-public-api",
    }


def admin_crash(run: str, scenario: str = "admin-crash") -> dict[str, Any]:
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    primary = "http://proof-admin:8000/api/v1"
    control = "http://proof-admin-control:8000/api/v1"
    with httpx.Client(timeout=60) as client:
        workspace = _post(client, primary, "/platform/workspaces", {"name": "Failure proof",
        "slug": run, "first_admin_subject": "bootstrap-admin",
        "first_admin_email": "bootstrap@proof.invalid",
        "first_admin_display_name": "Proof bootstrap"},
        bootstrap)
        workspace_id = workspace["id"]
        _post(client, primary, f"/workspaces/{workspace_id}/members", {"subject": "proof-proposer",
        "email": "proof-proposer@proof.invalid", "display_name": "proof-proposer",
        "role": "operator"},
        bootstrap)
        asyncio.run(_seed(workspace_id, run))
        boot = _post(client, primary, f"/workspaces/{workspace_id}/projects/bootstrap",
        {"project": {"name": "Failure proof", "slug": run}, "workflow": {"name": "Failure proof",
        "graph": _graph()}}, bootstrap)
        project, workflow = boot["project"], boot["primary_workflow"]
        route = (
            f"/workspaces/{workspace_id}/projects/{project['id']}/"
            f"workflows/{workflow['id']}/runs"
        )
        validation = _post(client, primary, route.rsplit("/runs", 1)[0] + "/draft/validation-runs",
        {}, proposer)
        if not validation.get("valid"):
            raise RuntimeError("public workflow validation failed")
        _post(client, primary, route.rsplit("/runs", 1)[0] + "/versions",
        {"reason": "failure proof", "expectedRevision": 1, "validationRunId": validation["runId"]},
        proposer)
        workflow_run = _post_published_run(client, primary, route, {"inputs": {},
        "responseMode": "async", "user": "proof-proposer", "requestId": run, "idempotencyKey": run},
        proposer)
        run_id = workflow_run["runId"]
        collections = f"{route}/{run_id}/iii-collections"
        if scenario == "no-report":
            signal = _coordination(f"{run}.submitted")
            signal.write_text(json.dumps({"route": collections}), encoding="utf-8")
            release = _coordination(f"{run}.resume")
            deadline = time.monotonic() + 90
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            if not release.exists():
                raise RuntimeError("orchestrator did not arm report-drop gate")
        submission = _post(client, primary, collections, {"version": "v1", "idempotencyKey": run,
        "nodeId": "opencli-source", "collection": {"site": "bilibili", "command": "search",
        "args": {"keyword": "vertical-proof"}, "sourceBindingId": "proof-binding",
        "sourceBindingRevisionId": "proof-binding-v1", "sourceBindingRevisionNumber": 1}}, proposer)
        command_id, attempt_id = submission["commandId"], submission["attemptId"]
        if scenario == "admin-crash":
            signal = _coordination(f"{run}.submitted")
            signal.write_text(json.dumps({"commandId": command_id, "attemptId": attempt_id,
            "route": collections}), encoding="utf-8")
            release = _coordination(f"{run}.resume")
            deadline = time.monotonic() + 90
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            if not release.exists():
                raise RuntimeError("orchestrator did not complete the admin crash gate")
        if scenario == "admin-crash":
            deadline = time.monotonic() + 30
            while True:
                try:
                    _post(client, control, f"{collections}/{command_id}/resume",
                    {"idempotencyKey": run}, proposer)
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.5)
            status = _get(client, control, f"{collections}/{command_id}", proposer)
        else:
            deadline = time.monotonic() + 45
            status = {}
            while time.monotonic() < deadline:
                status = _get(client, primary, f"{collections}/{command_id}", proposer)
                if status.get("state") in {"missing_report", "completed", "report_missing"}:
                    break
                time.sleep(0.5)
        materialization: dict[str, Any] | None = None
        if scenario in {"no-report", "signed-zero"}:
            materialization = _post(client, primary, f"{collections}/{command_id}/materialize", {},
            proposer)
            batch_id = materialization["batchId"]
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                materialization = _get(client, primary,
                f"{route}/{run_id}/evidence-batches/v1/{batch_id}/status", proposer)
                if (
                    scenario != "signed-zero"
                    or materialization.get("materializationStatus") == "completed_empty"
                ):
                    break
                time.sleep(0.5)
    hashes = {"submission": submission["payloadSha256"]}

    for item in status.get("evidenceReferences", []):
        if item.get("hash"):
            hashes[item.get("kind", "public")] = item["hash"]
    if scenario == "no-report":
        if (
            materialization is None
            or materialization.get("materializationStatus") != "indeterminate"
        ):
            raise RuntimeError(
                "scoped materialization did not expose indeterminate missing report"
            )
        return _failure_result(
            scenario="no-report",
            run=run,
            fault="expected-key-report-dropped",
            command_id=command_id,
            attempt_id=attempt_id,
            workflow_run_id=run_id,
            hashes=hashes,
            collection={
                "blockingStage": "callback_missing",
                "recoveryAction": "recover",
                "sideEffectUncertainty": True,
            },
            materialization={
                "status": "indeterminate",
                "blocker": "missing_report",
                "recoveryAction": "recover",
                "manifestHash": None,
                "reconciliationRevision": materialization["reconciliationRevision"],
                "pageSnapshotAsOf": materialization.get("pageSnapshotAsOf"),
            },
        )
    if scenario == "signed-zero":
        if (
            materialization is None
            or materialization.get("materializationStatus") != "completed_empty"
        ):
            raise RuntimeError(
                "signed zero scoped materialization did not complete empty: "
                + json.dumps(materialization, sort_keys=True)
            )
        return _failure_result(
            scenario="signed-zero",
            run=run,
            fault="pinned-zero-fixture",
            command_id=command_id,
            attempt_id=attempt_id,
            workflow_run_id=run_id,
            hashes=hashes,
            collection={
                "blockingStage": "none",
                "recoveryAction": "none",
                "sideEffectUncertainty": False,
            },
            materialization={
                "status": "completed_empty",
                "blocker": "none",
                "recoveryAction": "none",
                "manifestHash": None,
                "reconciliationRevision": materialization["reconciliationRevision"],
                "pageSnapshotAsOf": materialization.get("pageSnapshotAsOf"),
            },
        )
    return _failure_result(
        scenario="admin-crash",
        run=run,
        fault="primary-admin-crash",
        command_id=command_id,
        attempt_id=attempt_id,
        workflow_run_id=run_id,
        hashes=hashes,
        collection={
            "blockingStage": "none",
            "recoveryAction": "resume",
            "sideEffectUncertainty": True,
        },
        materialization={
            "status": "unknown",
            "blocker": "none",
            "recoveryAction": "none",
            "manifestHash": None,
            "reconciliationRevision": None,
            "pageSnapshotAsOf": None,
        },
    )
def crash_after_ingest(run: str) -> dict[str, Any]:
    """Prove report loss only after a public ingress receipt is observable."""
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    primary = "http://proof-admin:8000/api/v1"
    with httpx.Client(timeout=60) as client:
        workspace = _post(client, primary, "/platform/workspaces", {"name": "Crash after ingest",
        "slug": run, "first_admin_subject": "bootstrap-admin",
        "first_admin_email": "bootstrap@proof.invalid",
        "first_admin_display_name": "Proof bootstrap"},
        bootstrap)
        workspace_id = workspace["id"]
        _post(client, primary, f"/workspaces/{workspace_id}/members", {"subject": "proof-proposer",
        "email": "proof-proposer@proof.invalid", "display_name": "proof-proposer",
        "role": "operator"},
        bootstrap)
        asyncio.run(_seed(workspace_id, run))
        boot = _post(client, primary, f"/workspaces/{workspace_id}/projects/bootstrap",
        {"project": {"name": "Crash after ingest", "slug": run},
        "workflow": {"name": "Crash after ingest",
        "graph": _graph()}}, bootstrap)
        route = (
            f"/workspaces/{workspace_id}/projects/{boot['project']['id']}/"
            f"workflows/{boot['primary_workflow']['id']}/runs"
        )
        validation = _post(client, primary, route.rsplit("/runs", 1)[0] + "/draft/validation-runs",
        {}, proposer)
        if not validation.get("valid"):
            raise RuntimeError("public workflow validation failed")
        _post(client, primary, route.rsplit("/runs", 1)[0] + "/versions",
        {"reason": "crash after ingest", "expectedRevision": 1,
        "validationRunId": validation["runId"]},
        proposer)
        workflow_run = _post_published_run(client, primary, route, {"inputs": {},
        "responseMode": "async", "user": "proof-proposer", "requestId": run, "idempotencyKey": run},
        proposer)
        collections = f"{route}/{workflow_run['runId']}/iii-collections"
        _coordination(f"{run}.arm-report-hold").write_text(json.dumps({"route": collections}),
        encoding="utf-8")
        _wait_coordination(run, "report-hold-armed")
        submission = _post(client, primary, collections, {"version": "v1", "idempotencyKey": run,
        "nodeId": "opencli-source", "collection": {"site": "bilibili", "command": "search",
        "args": {"keyword": "vertical-proof"}, "sourceBindingId": "proof-binding",
        "sourceBindingRevisionId": "proof-binding-v1", "sourceBindingRevisionNumber": 1}}, proposer)
        command_id, attempt_id = submission["commandId"], submission["attemptId"]
        deadline = time.monotonic() + 60
        status: dict[str, Any] = {}
        receipt_hash = None
        while time.monotonic() < deadline:
            status = _get(client, primary, f"{collections}/{command_id}", proposer)
            receipt_hash = next((item.get("hash") for item in status.get("evidenceReferences",
            []) if item.get("kind") == "ingress_receipt" and item.get("hash")), None)
            if receipt_hash:
                break
            time.sleep(0.5)
        if not receipt_hash:
            raise RuntimeError("public status did not expose ingress receipt hash")
        _coordination(f"{run}.ingress-observed").write_text(
            json.dumps({"receiptHash": receipt_hash}), encoding="utf-8"
        )
        _wait_coordination(run, "collector-stopped")
        materialized = _post(client, primary, f"{collections}/{command_id}/materialize", {},
        proposer)
        materialization = _get(client, primary,
        f"{route}/{workflow_run['runId']}/evidence-batches/v1/{materialized['batchId']}/status",
        proposer)
    if materialization.get("materializationStatus") != "indeterminate":
        raise RuntimeError("public materialization was not indeterminate after collector stop")
    return _failure_result(
        scenario="crash-after-ingest",
        run=run,
        fault="collector-stopped-after-ingress",
        command_id=command_id,
        attempt_id=attempt_id,
        workflow_run_id=workflow_run["runId"],
        hashes={
            "submission": submission["payloadSha256"],
            "ingress_receipt": receipt_hash,
        },
        collection={
            "blockingStage": "callback_missing",
            "recoveryAction": "recover",
            "sideEffectUncertainty": True,
        },
        materialization={
            "status": "indeterminate",
            "blocker": "missing_report",
            "recoveryAction": "recover",
            "manifestHash": None,
            "reconciliationRevision": materialization["reconciliationRevision"],
            "pageSnapshotAsOf": materialization.get("pageSnapshotAsOf"),
        },
    )


def _wait_coordination(run: str, name: str) -> None:
    release = _coordination(f"{run}.{name}")
    deadline = time.monotonic() + 90
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    if not release.exists():
        raise RuntimeError(f"orchestrator did not acknowledge {name}")


def iii_unreachable(run: str) -> dict[str, Any]:
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    primary = "http://proof-admin:8000/api/v1"
    with httpx.Client(timeout=60) as client:
        workspace = _post(client, primary, "/platform/workspaces", {"name": "III unreachable",
        "slug": run, "first_admin_subject": "bootstrap-admin",
        "first_admin_email": "bootstrap@proof.invalid",
        "first_admin_display_name": "Proof bootstrap"},
        bootstrap)
        workspace_id = workspace["id"]
        _post(client, primary, f"/workspaces/{workspace_id}/members", {"subject": "proof-proposer",
        "email": "proof-proposer@proof.invalid", "display_name": "proof-proposer",
        "role": "operator"},
        bootstrap)
        asyncio.run(_seed(workspace_id, run))
        boot = _post(client, primary, f"/workspaces/{workspace_id}/projects/bootstrap",
        {"project": {"name": "III unreachable", "slug": run},
        "workflow": {"name": "III unreachable",
        "graph": _graph()}}, bootstrap)
        route = (
            f"/workspaces/{workspace_id}/projects/{boot['project']['id']}/"
            f"workflows/{boot['primary_workflow']['id']}/runs"
        )
        validation = _post(client, primary, route.rsplit("/runs", 1)[0] + "/draft/validation-runs",
        {}, proposer)
        if not validation.get("valid"):
            raise RuntimeError("public workflow validation failed")
        _post(client, primary, route.rsplit("/runs", 1)[0] + "/versions",
        {"reason": "III unreachable", "expectedRevision": 1,
        "validationRunId": validation["runId"]},
        proposer)
        workflow_run = _post_published_run(client, primary, route, {"inputs": {},
        "responseMode": "async", "user": "proof-proposer", "requestId": run, "idempotencyKey": run},
        proposer)
        collections = f"{route}/{workflow_run['runId']}/iii-collections"
        _coordination(f"{run}.iii-ready").write_text(json.dumps({"route": collections}),
        encoding="utf-8")
        release = _coordination(f"{run}.iii-release")
        deadline = time.monotonic() + 60
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not release.exists():
            raise RuntimeError("orchestrator did not arm the real III path gate")
        submission = _post(client, primary, collections, {"version": "v1", "idempotencyKey": run,
        "nodeId": "opencli-source", "collection": {"site": "bilibili", "command": "search",
        "args": {"keyword": "vertical-proof"}, "sourceBindingId": "proof-binding",
        "sourceBindingRevisionId": "proof-binding-v1", "sourceBindingRevisionNumber": 1}}, proposer)
        command_id, attempt_id = submission["commandId"], submission["attemptId"]
        deadline = time.monotonic() + 30
        status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            status = _get(client, primary, f"{collections}/{command_id}", proposer)
            if status.get("state") == "bridge_unavailable":
                break
            time.sleep(0.5)
    if status.get("state") != "bridge_unavailable":
        raise RuntimeError("public collection status did not prove real III bridge unavailability")
    return _failure_result(
        scenario="iii-unreachable",
        run=run,
        fault="primary-to-iii-disconnected",
        command_id=command_id,
        attempt_id=attempt_id,
        workflow_run_id=workflow_run["runId"],
        hashes={"submission": submission["payloadSha256"]},
        collection={
            "blockingStage": "bridge_unavailable",
            "recoveryAction": "retry",
            "sideEffectUncertainty": True,
        },
        materialization={
            "status": "unknown",
            "blocker": "none",
            "recoveryAction": "none",
            "manifestHash": None,
            "reconciliationRevision": None,
            "pageSnapshotAsOf": None,
        },
        mutation_status="unchanged",
    )


def public_setup(client: httpx.Client, run: str) -> dict[str, Any]:
    """Create one public workspace/run used by the four isolated loss commands."""
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    primary = "http://proof-admin:8000/api/v1"
    workspace = _post(client, primary, "/platform/workspaces", {"name": "ODP loss proof",
    "slug": run, "first_admin_subject": "bootstrap-admin",
    "first_admin_email": "bootstrap@proof.invalid", "first_admin_display_name": "Proof bootstrap"},
    bootstrap)
    workspace_id = workspace["id"]
    _post(client, primary, f"/workspaces/{workspace_id}/members", {"subject": "proof-proposer",
    "email": "proof-proposer@proof.invalid", "display_name": "proof-proposer", "role": "operator"},
    bootstrap)
    asyncio.run(_seed(workspace_id, run))
    boot = _post(client, primary, f"/workspaces/{workspace_id}/projects/bootstrap",
    {"project": {"name": "ODP loss proof", "slug": run}, "workflow": {"name": "ODP loss proof",
    "graph": _graph()}}, bootstrap)
    route = (
        f"/workspaces/{workspace_id}/projects/{boot['project']['id']}/"
        f"workflows/{boot['primary_workflow']['id']}/runs"
    )
    validation = _post(client, primary, route.rsplit("/runs", 1)[0] + "/draft/validation-runs", {},
    proposer)
    if not validation.get("valid"):
        raise RuntimeError("public workflow validation failed")
    _post(client, primary, route.rsplit("/runs", 1)[0] + "/versions", {"reason": "ODP loss proof",
    "expectedRevision": 1, "validationRunId": validation["runId"]}, proposer)
    workflow_run = _post_published_run(client, primary, route, {"inputs": {},
    "responseMode": "async", "user": "proof-proposer", "requestId": run, "idempotencyKey": run},
    proposer)
    return {"primary": primary, "proposer": proposer, "route": route,
    "runId": workflow_run["runId"],
    "collections": f"{route}/{workflow_run['runId']}/iii-collections"}


def public_disposable_run(
    client: httpx.Client, setup: dict[str, Any], request_id: str
) -> dict[str, Any]:
    workflow_run = _post_published_run(
        client,
        setup["primary"],
        setup["route"],
        {
            "inputs": {},
            "responseMode": "async",
            "user": "proof-proposer",
            "requestId": request_id,
            "idempotencyKey": request_id,
        },
        setup["proposer"],
    )
    return {
        **setup,
        "runId": workflow_run["runId"],
        "collections": f"{setup['route']}/{workflow_run['runId']}/iii-collections",
    }


def public_submit(
    client: httpx.Client,
    setup: dict[str, Any],
    *,
    source_id: str,
    site: str,
    command: str,
    idempotency_key: str | None = None,
    stable_odp_source_id: str | None = None,
) -> dict[str, Any]:
    collection: dict[str, Any] = {
        "site": site,
        "command": command,
        "args": {"keyword": source_id},
    }
    if stable_odp_source_id is None:
        collection.update(
            {
                "sourceBindingId": source_id,
                "sourceBindingRevisionId": f"{source_id}-v1",
                "sourceBindingRevisionNumber": 1,
            }
        )
    else:
        collection["sourceId"] = stable_odp_source_id
    return _post(
        client,
        setup["primary"],
        setup["collections"],
        {
            "version": "v1",
            "idempotencyKey": idempotency_key or source_id,
            "nodeId": "opencli-source",
            "collection": collection,
        },
        setup["proposer"],
    )


def public_status(client: httpx.Client, setup: dict[str, Any], command_id: str) -> dict[str, Any]:
    return _get(client, setup["primary"], f"{setup['collections']}/{command_id}", setup["proposer"])


def public_materialize(client: httpx.Client, setup: dict[str, Any], command_id: str, *,
recover: bool = False) -> dict[str, Any]:
    action = "recover" if recover else "materialize"
    batch = _post(client, setup["primary"], f"{setup['collections']}/{command_id}/{action}", {},
    setup["proposer"])
    return _get(client, setup["primary"],
    f"{setup['route']}/{setup['runId']}/evidence-batches/v1/{batch['batchId']}/status",
    setup["proposer"])


def public_recover(client: httpx.Client, setup: dict[str, Any], command_id: str) -> dict[str, Any]:
    return public_materialize(client, setup, command_id, recover=True)


def _arm_gateway(client: httpx.Client, name: str, armed: bool) -> None:
    controls = {
        "http-schema-mutator": "http://proof-odp-http-gateway:8040",
        "ingest-redis-cut": "http://proof-odp-ingest-redis-gateway:8081",
        "ingest-redis-payload-mutator": "http://proof-odp-ingest-redis-mutator:8084",
        "store-pg-cut": "http://proof-odp-store-pg-gateway:8082",
        "store-redis-committed-xadd": "http://proof-odp-store-redis-gateway:8083",
    }
    response = client.post(f"{controls[name]}/_gate/{name}/arm", json={"armed": armed},
    headers={"X-API-Token": os.environ["API_AUTH_TOKEN"]})
    if response.status_code != 200:
        raise RuntimeError(f"authenticated gateway arm failed: {response.status_code}")


def _public_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",",
    ":")).encode()).hexdigest()


def _wait_for_ingress_receipt(
    client: httpx.Client, setup: dict[str, Any], command_id: str, *, timeout: int = 90
) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = public_status(client, setup, command_id)
        for reference in last.get("evidenceReferences", []):
            if (
                reference.get("kind") == "ingress_receipt"
                and isinstance(reference.get("hash"), str)
                and len(reference["hash"]) == 64
            ):
                return last, reference["hash"]
        time.sleep(0.5)
    raise RuntimeError(
        "authenticated public status never exposed an ingress-receipt reference: "
        + json.dumps(last, sort_keys=True)
    )


def _wait_for_materialization(
    client: httpx.Client,
    setup: dict[str, Any],
    command_id: str,
    *,
    predicate: Any,
    timeout: int = 180,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    result = public_materialize(client, setup, command_id)
    while not predicate(result) and time.monotonic() < deadline:
        time.sleep(2)
        result = public_recover(client, setup, command_id)
    if not predicate(result):
        raise RuntimeError(
            "authenticated materialization did not settle as required: "
            + json.dumps(result, sort_keys=True)
        )
    return result


def _completed_exact(value: dict[str, Any]) -> bool:
    counts = value.get("counts")
    return (
        value.get("materializationStatus") == "completed"
        and isinstance(counts, dict)
        and counts.get("record_present") == 1
        and counts.get("unknown") == 0
    )


def duplicate_dlq(run: str) -> dict[str, Any]:
    """Prove replay, duplicate ingress, durable DLQ, and unknown retention publicly."""
    stable_source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"proof-duplicate/{run}"))
    keyword = f"duplicate-{hashlib.sha256(run.encode()).hexdigest()[:16]}"
    hashes: dict[str, str] = {}
    with httpx.Client(timeout=60) as client:
        first_setup = public_setup(client, run)
        first = public_submit(
            client,
            first_setup,
            source_id=keyword,
            stable_odp_source_id=stable_source_id,
            site="github",
            command="issues",
            idempotency_key="same-admin-replay",
        )
        if first.get("created") is not True:
            raise RuntimeError("initial authenticated Admin submission was not created")
        replay = public_submit(
            client,
            first_setup,
            source_id=keyword,
            stable_odp_source_id=stable_source_id,
            site="github",
            command="issues",
            idempotency_key="same-admin-replay",
        )
        if (
            replay.get("created") is not False
            or any(replay.get(name) != first.get(name) for name in ("commandId", "attemptId", "payloadSha256"))
        ):
            raise RuntimeError("identical authenticated replay minted a different collection intent")
        first_status, first_receipt = _wait_for_ingress_receipt(
            client, first_setup, first["commandId"]
        )
        first_exact = _wait_for_materialization(
            client, first_setup, first["commandId"], predicate=_completed_exact
        )
        hashes.update(
            {
                "replay_initial": _public_hash(first),
                "replay_same_intent": _public_hash(replay),
                "replay_status": _public_hash(first_status),
                "replay_receipt": first_receipt,
                "replay_exact": _public_hash(first_exact),
            }
        )

        duplicate_setup = public_disposable_run(client, first_setup, f"{run}-duplicate")
        duplicate = public_submit(
            client,
            duplicate_setup,
            source_id=keyword,
            stable_odp_source_id=stable_source_id,
            site="github",
            command="issues",
            idempotency_key="second-disposable-command",
        )
        duplicate_status, duplicate_receipt = _wait_for_ingress_receipt(
            client, duplicate_setup, duplicate["commandId"]
        )
        duplicate_exact = _wait_for_materialization(
            client, duplicate_setup, duplicate["commandId"], predicate=_completed_exact
        )
        hashes.update(
            {
                "duplicate_submission": _public_hash(duplicate),
                "duplicate_status": _public_hash(duplicate_status),
                "duplicate_signed_receipt": duplicate_receipt,
                "duplicate_exact_presence": _public_hash(duplicate_exact),
            }
        )

        dlq_setup = public_disposable_run(client, first_setup, f"{run}-dlq")
        _arm_gateway(client, "ingest-redis-payload-mutator", True)
        try:
            dlq = public_submit(
                client,
                dlq_setup,
                source_id="poison",
                stable_odp_source_id=str(uuid.uuid4()),
                site="reddit",
                command="posts",
                idempotency_key="retained-dlq",
            )
            dlq_status, dlq_receipt = _wait_for_ingress_receipt(
                client, dlq_setup, dlq["commandId"]
            )
        finally:
            _arm_gateway(client, "ingest-redis-payload-mutator", False)
        retained_dlq = _wait_for_materialization(
            client,
            dlq_setup,
            dlq["commandId"],
            predicate=lambda value: (
                value.get("materializationStatus") == "partial"
                and value.get("counts", {}).get("dlq") == 1
                and value.get("counts", {}).get("unknown") == 0
            ),
        )
        hashes.update(
            {
                "retained_dlq_submission": _public_hash(dlq),
                "retained_dlq_status": _public_hash(dlq_status),
                "retained_dlq_receipt": dlq_receipt,
                "retained_dlq_materialization": _public_hash(retained_dlq),
            }
        )

        unknown_setup = public_disposable_run(client, first_setup, f"{run}-unknown")
        _arm_gateway(client, "store-pg-cut", True)
        try:
            unknown = public_submit(
                client,
                unknown_setup,
                source_id="unknown",
                stable_odp_source_id=str(uuid.uuid4()),
                site="youtube",
                command="videos",
                idempotency_key="absent-retention",
            )
            unknown_status, unknown_receipt = _wait_for_ingress_receipt(
                client, unknown_setup, unknown["commandId"]
            )
            unknown_retention = _wait_for_materialization(
                client,
                unknown_setup,
                unknown["commandId"],
                predicate=lambda value: (
                    value.get("materializationStatus") == "indeterminate"
                    and value.get("counts", {}).get("unknown") == 1
                ),
                timeout=60,
            )
        finally:
            _arm_gateway(client, "store-pg-cut", False)
        hashes.update(
            {
                "unknown_submission": _public_hash(unknown),
                "unknown_status": _public_hash(unknown_status),
                "unknown_receipt": unknown_receipt,
                "unknown_retention_materialization": _public_hash(unknown_retention),
            }
        )

    return {
        "scenario": "duplicate-dlq",
        "run": run,
        "fault": "duplicate-ingress-retained-dlq-unknown-retention",
        "actuator": {
            "name": "proof-iii-actuator",
            "invocationHash": hashlib.sha256(duplicate["commandId"].encode()).hexdigest(),
        },
        "correlation": {
            "commandId": duplicate["commandId"],
            "attemptId": duplicate["attemptId"],
            "workflowRunId": duplicate_setup["runId"],
            "hashes": hashes,
        },
        "collection": {
            "blockingStage": "duplicate",
            "recoveryAction": "recover",
            "sideEffectUncertainty": True,
        },
        "materialization": {
            "status": "indeterminate",
            "blocker": "unknown_retention",
            "recoveryAction": "recover",
            "manifestHash": None,
            "reconciliationRevision": unknown_retention["reconciliationRevision"],
            "pageSnapshotAsOf": unknown_retention.get("pageSnapshotAsOf"),
        },
        "graph": {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "none"},
        "delivery": {
            "state": "none",
            "outcome": "none",
            "attemptCount": 0,
            "receiptHash": None,
            "reconciliation": "none",
        },
        "redactionProfile": "failure-v1",
        "timing": {"startedAt": 0, "completedAt": 1, "deadlineSeconds": 360},
        "governanceReference": {
            "artifactId": "pending",
            "keyId": "pending",
            "trustRootFingerprint": "pending",
        },
        "authority": "authenticated-scoped-public-api",
    }


def _storage_loss_source_id(run: str, index: int, source: str) -> str:
    """Keep public source-binding identifiers within the API's 36-byte bound."""
    run_digest = hashlib.sha256(run.encode()).hexdigest()[:16]
    return f"loss-{index}-{source[:8]}-{run_digest}"


def ingest_redis_store_loss(run: str) -> dict[str, Any]:
    """Exercise four real loss seams while preserving only public API facts."""
    cases = (
        ("http-schema-mutator", "http-schema-mutator", "bilibili", "search"),
        ("ingest-redis-cut", "ingest-redis-cut", "youtube", "videos"),
        ("store-pg-cut", "store-pg-cut", "github", "issues"),
        ("store-redis-committed-xadd", "store-redis-committed-xadd", "reddit", "posts"),
    )
    observations: dict[str, dict[str, Any]] = {}
    with httpx.Client(timeout=60) as client:
        setup = public_setup(client, run)
        for index, (gateway, source, site, command) in enumerate(cases):
            source_id = _storage_loss_source_id(run, index, source)
            if gateway == "store-redis-committed-xadd":
                marker = Path("/proof-artifacts/gateway-coordination/store-commit-ready")
                marker.unlink(missing_ok=True)
                time.sleep(1)
            _arm_gateway(client, gateway, True)
            try:
                submission = public_submit(client, setup, source_id=source_id, site=site,
                command=command)
                command_id = submission["commandId"]
                status = public_status(client, setup, command_id)
                if gateway == "store-redis-committed-xadd":
                    deadline = time.monotonic() + 60
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(0.2)
                    if not marker.exists():
                        raise RuntimeError("store commit did not make notification loss eligible")
                public_materialize(client, setup, command_id)
            finally:
                _arm_gateway(client, gateway, False)
            recovered = public_recover(client, setup, command_id)
            if not isinstance(recovered.get("reconciliationRevision"),
            int) or not recovered.get("materializationStatus"):
                raise RuntimeError("public recovery did not expose outcome and revision")
            observations[gateway] = {"submission": submission, "status": status,
            "materialization": recovered, "commandId": command_id,
            "attemptId": submission["attemptId"]}
    final = observations["store-redis-committed-xadd"]
    hashes = {
        f"{name}_status": _public_hash(value["status"])
        for name, value in observations.items()
    } | {
        f"{name}_materialization": _public_hash(value["materialization"])
        for name, value in observations.items()
    }
    final_status = final["materialization"]
    status = final_status.get("materializationStatus")
    normalized = status if status in {"indeterminate", "completed_empty", "rejected", "unknown",
    "completed"} else "unknown"
    return {"scenario": "ingest-redis-store-loss", "run": run,
    "fault": "ingest-redis-store-notification-loss", "actuator": {"name": "proof-iii-actuator",
    "invocationHash": hashlib.sha256(final["commandId"].encode()).hexdigest()},
    "correlation": {"commandId": final["commandId"], "attemptId": final["attemptId"],
    "workflowRunId": setup["runId"], "hashes": hashes},
    "collection": {"blockingStage": "ingress_unknown", "recoveryAction": "recover",
    "sideEffectUncertainty": True}, "materialization": {"status": normalized, "blocker": "none",
    "recoveryAction": "recover", "manifestHash": None,
    "reconciliationRevision": final_status["reconciliationRevision"],
    "pageSnapshotAsOf": final_status.get("pageSnapshotAsOf")}, "graph": {"pin": None,
    "sequence": None,
    "readBlocker": "none", "mutationStatus": "none"}, "delivery": {"state": "none",
    "outcome": "none",
    "attemptCount": 0, "receiptHash": None, "reconciliation": "none"},
    "redactionProfile": "failure-v1", "timing": {"startedAt": 0, "completedAt": 1,
    "deadlineSeconds": 360}, "governanceReference": {"artifactId": "pending", "keyId": "pending",
    "trustRootFingerprint": "pending"}, "authority": "authenticated-scoped-public-api"}
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if args.scenario in {"admin-crash", "no-report", "signed-zero"}:
        result = admin_crash(args.run, args.scenario)
    elif args.scenario == "iii-unreachable":
        result = iii_unreachable(args.run)
    elif args.scenario == "crash-after-ingest":
        result = crash_after_ingest(args.run)
    elif args.scenario == "ingest-redis-store-loss":
        result = ingest_redis_store_loss(args.run)
    elif args.scenario == "duplicate-dlq":
        result = duplicate_dlq(args.run)
    else:
        raise RuntimeError("scenario driver is not implemented")
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
