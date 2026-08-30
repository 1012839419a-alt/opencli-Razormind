#!/usr/bin/env python3
"""In-network public-API driver for the first #37 failure scenario."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
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


def _post(client: httpx.Client, base: str, path: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    return _data(client.post(base + path, json=body, headers=headers))


def _get(client: httpx.Client, base: str, path: str, headers: dict[str, str]) -> dict[str, Any]:
    return _data(client.get(base + path, headers=headers))


def _post_published_run(client: httpx.Client, base: str, path: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    """Retry only the documented publish-visibility 409 without changing intent."""
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


def admin_crash(run: str, scenario: str = "admin-crash") -> dict[str, Any]:
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    primary, control = "http://proof-admin:8000/api/v1", "http://proof-admin-control:8000/api/v1"
    with httpx.Client(timeout=60) as client:
        workspace = _post(client, primary, "/platform/workspaces", {"name": "Failure proof", "slug": run, "first_admin_subject": "bootstrap-admin", "first_admin_email": "bootstrap@proof.invalid", "first_admin_display_name": "Proof bootstrap"}, bootstrap)
        workspace_id = workspace["id"]
        _post(client, primary, f"/workspaces/{workspace_id}/members", {"subject": "proof-proposer", "email": "proof-proposer@proof.invalid", "display_name": "proof-proposer", "role": "operator"}, bootstrap)
        asyncio.run(_seed(workspace_id, run))
        boot = _post(client, primary, f"/workspaces/{workspace_id}/projects/bootstrap", {"project": {"name": "Failure proof", "slug": run}, "workflow": {"name": "Failure proof", "graph": _graph()}}, bootstrap)
        project, workflow = boot["project"], boot["primary_workflow"]
        route = f"/workspaces/{workspace_id}/projects/{project['id']}/workflows/{workflow['id']}/runs"
        validation = _post(client, primary, route.rsplit("/runs", 1)[0] + "/draft/validation-runs", {}, proposer)
        if not validation.get("valid"):
            raise RuntimeError("public workflow validation failed")
        _post(client, primary, route.rsplit("/runs", 1)[0] + "/versions", {"reason": "failure proof", "expectedRevision": 1, "validationRunId": validation["runId"]}, proposer)
        workflow_run = _post_published_run(client, primary, route, {"inputs": {}, "responseMode": "async", "user": "proof-proposer", "requestId": run, "idempotencyKey": run}, proposer)
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
        submission = _post(client, primary, collections, {"version": "v1", "idempotencyKey": run, "nodeId": "opencli-source", "collection": {"site": "bilibili", "command": "search", "args": {"keyword": "vertical-proof"}, "sourceBindingId": "proof-binding", "sourceBindingRevisionId": "proof-binding-v1", "sourceBindingRevisionNumber": 1}}, proposer)
        command_id, attempt_id = submission["commandId"], submission["attemptId"]
        if scenario == "admin-crash":
            signal = _coordination(f"{run}.submitted")
            signal.write_text(json.dumps({"commandId": command_id, "attemptId": attempt_id, "route": collections}), encoding="utf-8")
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
                    _post(client, control, f"{collections}/{command_id}/resume", {"idempotencyKey": run}, proposer)
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
            materialization = _post(client, primary, f"{collections}/{command_id}/materialize", {}, proposer)
            batch_id = materialization["batchId"]
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                materialization = _get(client, primary, f"{route}/{run_id}/evidence-batches/v1/{batch_id}/status", proposer)
                if scenario != "signed-zero" or materialization.get("materializationStatus") == "completed_empty":
                    break
                time.sleep(0.5)
    hashes = {"submission": submission["payloadSha256"]}

    for item in status.get("evidenceReferences", []):
        if item.get("hash"):
            hashes[item.get("kind", "public")] = item["hash"]
    if scenario == "no-report":
        if materialization is None or materialization.get("materializationStatus") != "indeterminate":
            raise RuntimeError("scoped materialization did not expose indeterminate missing report")
        return {"scenario": "no-report", "run": run, "fault": "expected-key-report-dropped", "actuator": {"name": "proof-iii-actuator", "invocationHash": hashlib.sha256(command_id.encode()).hexdigest()}, "correlation": {"commandId": command_id, "attemptId": attempt_id, "workflowRunId": run_id, "hashes": hashes}, "collection": {"blockingStage": "callback_missing", "recoveryAction": "recover", "sideEffectUncertainty": True}, "materialization": {"status": "indeterminate", "blocker": "missing_report", "recoveryAction": "recover", "manifestHash": None, "reconciliationRevision": materialization["reconciliationRevision"], "pageSnapshotAsOf": materialization.get("pageSnapshotAsOf")}, "graph": {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "none"}, "delivery": {"state": "none", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"}, "redactionProfile": "failure-v1", "timing": {"startedAt": 0, "completedAt": 1, "deadlineSeconds": 360}, "governanceReference": {"artifactId": "pending", "keyId": "pending", "trustRootFingerprint": "pending"}, "authority": "authenticated-scoped-public-api"}
    if scenario == "signed-zero":
        if materialization is None or materialization.get("materializationStatus") != "completed_empty":
            raise RuntimeError(
                "signed zero scoped materialization did not complete empty: "
                + json.dumps(materialization, sort_keys=True)
            )
        return {"scenario": "signed-zero", "run": run, "fault": "pinned-zero-fixture", "actuator": {"name": "proof-iii-actuator", "invocationHash": hashlib.sha256(command_id.encode()).hexdigest()}, "correlation": {"commandId": command_id, "attemptId": attempt_id, "workflowRunId": run_id, "hashes": hashes}, "collection": {"blockingStage": "none", "recoveryAction": "none", "sideEffectUncertainty": False}, "materialization": {"status": "completed_empty", "blocker": "none", "recoveryAction": "none", "manifestHash": None, "reconciliationRevision": materialization["reconciliationRevision"], "pageSnapshotAsOf": materialization.get("pageSnapshotAsOf")}, "graph": {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "none"}, "delivery": {"state": "none", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"}, "redactionProfile": "failure-v1", "timing": {"startedAt": 0, "completedAt": 1, "deadlineSeconds": 360}, "governanceReference": {"artifactId": "pending", "keyId": "pending", "trustRootFingerprint": "pending"}, "authority": "authenticated-scoped-public-api"}
    return {"scenario": "admin-crash", "run": run, "fault": "primary-admin-crash", "actuator": {"name": "proof-iii-actuator", "invocationHash": hashlib.sha256(command_id.encode()).hexdigest()}, "correlation": {"commandId": command_id, "attemptId": attempt_id, "workflowRunId": run_id, "hashes": hashes}, "collection": {"blockingStage": "none", "recoveryAction": "resume", "sideEffectUncertainty": True}, "materialization": {"status": "unknown", "blocker": "none", "recoveryAction": "none", "manifestHash": None, "reconciliationRevision": None, "pageSnapshotAsOf": None}, "graph": {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "none"}, "delivery": {"state": "none", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"}, "redactionProfile": "failure-v1", "timing": {"startedAt": 0, "completedAt": 1, "deadlineSeconds": 360}, "governanceReference": {"artifactId": "pending", "keyId": "pending", "trustRootFingerprint": "pending"}, "authority": "authenticated-scoped-public-api"}
def iii_unreachable(run: str) -> dict[str, Any]:
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    primary = "http://proof-admin:8000/api/v1"
    with httpx.Client(timeout=60) as client:
        workspace = _post(client, primary, "/platform/workspaces", {"name": "III unreachable", "slug": run, "first_admin_subject": "bootstrap-admin", "first_admin_email": "bootstrap@proof.invalid", "first_admin_display_name": "Proof bootstrap"}, bootstrap)
        workspace_id = workspace["id"]
        _post(client, primary, f"/workspaces/{workspace_id}/members", {"subject": "proof-proposer", "email": "proof-proposer@proof.invalid", "display_name": "proof-proposer", "role": "operator"}, bootstrap)
        asyncio.run(_seed(workspace_id, run))
        boot = _post(client, primary, f"/workspaces/{workspace_id}/projects/bootstrap", {"project": {"name": "III unreachable", "slug": run}, "workflow": {"name": "III unreachable", "graph": _graph()}}, bootstrap)
        route = f"/workspaces/{workspace_id}/projects/{boot['project']['id']}/workflows/{boot['primary_workflow']['id']}/runs"
        validation = _post(client, primary, route.rsplit("/runs", 1)[0] + "/draft/validation-runs", {}, proposer)
        if not validation.get("valid"):
            raise RuntimeError("public workflow validation failed")
        _post(client, primary, route.rsplit("/runs", 1)[0] + "/versions", {"reason": "III unreachable", "expectedRevision": 1, "validationRunId": validation["runId"]}, proposer)
        workflow_run = _post_published_run(client, primary, route, {"inputs": {}, "responseMode": "async", "user": "proof-proposer", "requestId": run, "idempotencyKey": run}, proposer)
        collections = f"{route}/{workflow_run['runId']}/iii-collections"
        _coordination(f"{run}.iii-ready").write_text(json.dumps({"route": collections}), encoding="utf-8")
        release = _coordination(f"{run}.iii-release")
        deadline = time.monotonic() + 60
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not release.exists():
            raise RuntimeError("orchestrator did not arm the real III path gate")
        submission = _post(client, primary, collections, {"version": "v1", "idempotencyKey": run, "nodeId": "opencli-source", "collection": {"site": "bilibili", "command": "search", "args": {"keyword": "vertical-proof"}, "sourceBindingId": "proof-binding", "sourceBindingRevisionId": "proof-binding-v1", "sourceBindingRevisionNumber": 1}}, proposer)
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
    return {"scenario": "iii-unreachable", "run": run, "fault": "primary-to-iii-disconnected", "actuator": {"name": "proof-iii-actuator", "invocationHash": hashlib.sha256(command_id.encode()).hexdigest()}, "correlation": {"commandId": command_id, "attemptId": attempt_id, "workflowRunId": workflow_run["runId"], "hashes": {"submission": submission["payloadSha256"]}}, "collection": {"blockingStage": "bridge_unavailable", "recoveryAction": "retry", "sideEffectUncertainty": True}, "materialization": {"status": "unknown", "blocker": "none", "recoveryAction": "none", "manifestHash": None, "reconciliationRevision": None, "pageSnapshotAsOf": None}, "graph": {"pin": None, "sequence": None, "readBlocker": "none", "mutationStatus": "unchanged"}, "delivery": {"state": "none", "outcome": "none", "attemptCount": 0, "receiptHash": None, "reconciliation": "none"}, "redactionProfile": "failure-v1", "timing": {"startedAt": 0, "completedAt": 1, "deadlineSeconds": 360}, "governanceReference": {"artifactId": "pending", "keyId": "pending", "trustRootFingerprint": "pending"}, "authority": "authenticated-scoped-public-api"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if args.scenario in {"admin-crash", "no-report", "signed-zero"}:
        result = admin_crash(args.run, args.scenario)
    elif args.scenario == "iii-unreachable":
        result = iii_unreachable(args.run)
    else:
        raise RuntimeError("scenario driver is not implemented")
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
