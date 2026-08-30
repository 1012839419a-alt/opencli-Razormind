#!/usr/bin/env python3
"""Drive the isolated proof only through Admin's public scoped HTTP APIs."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from typing import Any

import httpx

from backend.database import AsyncSessionLocal
from backend.models.studio import StudioWorkspace

BASE = "http://proof-admin:8000/api/v1"


def data(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise RuntimeError(f"{response.status_code} {response.request.url}: {response.text[:600]}")
    value = response.json()
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
        raise RuntimeError(f"Admin response has no data object: {response.text[:300]}")
    return value["data"]


def post(client: httpx.Client, path: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    return data(client.post(f"{BASE}{path}", json=body, headers=headers))


def get(client: httpx.Client, path: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return data(client.get(f"{BASE}{path}", headers=headers))
def wait_for_materialization(
    client: httpx.Client,
    route: str,
    command_id: str,
    attempt_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    deadline = time.monotonic() + 90
    last: dict[str, Any] | None = None
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.post(f"{BASE}{route}/{command_id}/materialize", headers=headers)
        if response.status_code == 200:
            last = data(response)
            last_status = get(client, f"{route}/{command_id}", headers)
            if last.get("materializationStatus") == "completed" and last.get("researchGraphManifestRef"):
                return last
        time.sleep(1)
    raise RuntimeError(
        "materialization stage timed out: "
        + json.dumps(
            {
                "commandId": command_id,
                "attemptId": attempt_id,
                "verticalStatus": last_status,
                "materialization": last,
            },
            sort_keys=True,
        )
    )


async def seed_studio_workspace(workspace_id: str, slug: str) -> None:
    """The Studio workspace is bootstrap identity state, not a workflow fact."""
    async with AsyncSessionLocal() as session:
        session.add(StudioWorkspace(id=workspace_id, name="Non-bypass proof", slug=slug))
        await session.commit()


def graph() -> dict[str, Any]:
    return {
        "id": "proof-workflow",
        "name": "Non-bypass vertical proof",
        "profile": "intelligence",
        "version": 1,
        "nodes": [
            {
                "id": "opencli-source",
                "kind": "source",
                "capability": "fetch",
                "adapter": "proof-opencli",
                "params": {"limit": 1},
                "sourceAnchor": {"kind": "url", "label": "Bilibili", "href": "https://www.bilibili.com/"},
            },
            {"id": "normalize-proof", "kind": "agent", "capability": "normalize", "params": {"language": "en"}},
            {"id": "proof-inbox", "kind": "inbox", "capability": "store", "params": {"queue": "proof"}},
        ],
        "edges": [
            {"id": "proof-source-normalize", "source": "opencli-source", "target": "normalize-proof", "sourcePort": "records", "targetPort": "records"},
            {"id": "proof-normalize-inbox", "source": "normalize-proof", "target": "proof-inbox", "sourcePort": "records", "targetPort": "records"},
        ],
        "adapters": [{"id": "proof-opencli", "type": "source", "provider": "bilibili", "mode": "live", "config": {"command": "search"}}],
        "agentPermissions": {"canFetchNetwork": True, "canSendNotifications": False, "canWriteInbox": True, "allowedDomains": ["bilibili.com"]},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    fleet = {"X-API-Token": os.environ["API_AUTH_TOKEN"]}
    bootstrap = {**fleet, "Authorization": f"Bearer {os.environ['BOOTSTRAP_ADMIN_TOKEN']}"}
    proposer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_PROPOSER_JWT']}"}
    reviewer = {**fleet, "Authorization": f"Bearer {os.environ['PROOF_REVIEWER_JWT']}"}
    with httpx.Client(timeout=60) as client:
        workspace = post(client, "/platform/workspaces", {
            "name": "Non-bypass proof",
            "slug": args.run,
            "first_admin_subject": "bootstrap-admin",
            "first_admin_email": "bootstrap@proof.invalid",
            "first_admin_display_name": "Proof bootstrap",
        }, bootstrap)
        workspace_id = workspace["id"]
        for subject, role in (("proof-proposer", "operator"), ("proof-reviewer", "maintainer")):
            post(client, f"/workspaces/{workspace_id}/members", {
                "subject": subject,
                "email": f"{subject}@proof.invalid",
                "display_name": subject,
                "role": role,
            }, bootstrap)
        asyncio.run(seed_studio_workspace(workspace_id, args.run))
        bootstrap_result = post(client, f"/workspaces/{workspace_id}/projects/bootstrap", {
            "project": {"name": "Non-bypass proof", "slug": args.run},
            "workflow": {"name": "Non-bypass proof", "graph": graph()},
        }, bootstrap)
        project = bootstrap_result["project"]
        workflow = bootstrap_result["primary_workflow"]
        route = f"/workspaces/{workspace_id}/projects/{project['id']}/workflows/{workflow['id']}/runs"
        validation = post(client, route.rsplit("/runs", 1)[0] + "/draft/validation-runs", {}, proposer)
        if not validation.get("valid"):
            raise RuntimeError(f"workflow validation failed: {json.dumps(validation, sort_keys=True)}")
        post(client, route.rsplit("/runs", 1)[0] + "/versions", {
            "reason": "isolated proof", "expectedRevision": 1, "validationRunId": validation["runId"],
        }, proposer)
        run = post(client, route, {
            "inputs": {}, "responseMode": "async", "user": "proof-proposer",
            "requestId": args.run, "idempotencyKey": args.run,
        }, proposer)
        run_id = run["runId"]
        collection_route = f"{route}/{run_id}/iii-collections"
        submission = post(client, collection_route, {
            "version": "v1", "idempotencyKey": args.run, "nodeId": "opencli-source",
            "collection": {
                "site": "bilibili", "command": "search", "args": {"keyword": "vertical-proof"},
                "sourceBindingId": "proof-binding", "sourceBindingRevisionId": "proof-binding-v1", "sourceBindingRevisionNumber": 1,
            },
        }, proposer)
        command_id, attempt_id = submission["commandId"], submission["attemptId"]
        materialization = wait_for_materialization(client, collection_route, command_id, attempt_id, proposer)
        manifest_ref = materialization["researchGraphManifestRef"]
        if manifest_ref.get("materializationStatus") != "completed":
            raise RuntimeError("only completed materialization can enter ResearchGraph")
        # The remainder is deliberately scoped and identity-bound: no database
        # reads or reconstructed manifest references are permitted.
        graph_route = f"{route}/{run_id}/research-graph-v2"
        state = get(client, graph_route, proposer)
        claim_id = f"claim-{args.run}"
        claim_hash = __import__("hashlib").sha256(args.run.encode()).hexdigest()
        proposed = post(client, graph_route + "/mutations", {
            "idempotencyKey": f"{args.run}-propose", "action": "propose", "expectedSequence": state["sequence"],
            "expectedRevision": state["researchRevisionId"], "nodeId": "opencli-source",
            "claimId": claim_id, "claimContentHash": claim_hash, "manifestRefs": [manifest_ref],
        }, proposer)
        verified = post(client, graph_route + "/mutations", {
            "idempotencyKey": f"{args.run}-verify", "action": "verify", "expectedSequence": proposed["sequence"],
            "expectedRevision": proposed["researchRevisionId"], "nodeId": "opencli-source",
            "claimId": claim_id, "claimContentHash": claim_hash, "manifestRefs": [manifest_ref],
        }, reviewer)
        pinned = post(client, graph_route + "/mutations", {
            "idempotencyKey": f"{args.run}-pin",
            "action": "pin",
            "expectedSequence": verified["sequence"],
            "expectedRevision": verified["researchRevisionId"],
            "nodeId": "opencli-source",
            "manifestRefs": [manifest_ref],
        }, reviewer)
        target = post(client, f"{route}/{run_id}/delivery-targets", {
            "receiverIdentity": "controlled-receiver-proof",
            "endpointIdentity": "receiver-channel-proof",
            "credentialReference": "credential-reference-proof",
        }, reviewer)
        decision = post(client, f"{route}/{run_id}/delivery-authorizations", {
            "version": "v1",
            "operationId": f"delivery-{args.run}",
            "idempotencyKey": f"{args.run}-delivery",
            "nodeId": "opencli-source",
            "targetId": target["targetId"],
            "pinnedReference": {
                "sequence": pinned["pinnedFold"]["sequence"],
                "researchRevisionId": pinned["pinnedFold"]["researchRevisionId"],
                "manifestSetHash": pinned["pinnedFold"]["manifestSetHash"],
            },
            "selectedClaimIds": [claim_id],
        }, reviewer)
        execution = post(
            client,
            f"{route}/{run_id}/delivery-executions",
            {"decisionId": decision["decisionId"]},
            reviewer,
        )
        if execution.get("outcome") != "accepted" or not execution.get("attempts"):
            raise RuntimeError(f"delivery execution did not reach accepted: {execution}")
        final_attempt = execution["attempts"][-1]
        if final_attempt.get("receipt") != "verified":
            raise RuntimeError(f"delivery receipt was not verified: {execution}")
        vertical_status = get(client, f"{collection_route}/{command_id}", proposer)
        references = vertical_status["evidenceReferences"]
        lifecycle = [item["reference"] for item in references if item["kind"] == "lifecycle"]
        report_ref = next(item["reference"] for item in references if item["kind"] == "expected_key_report")
        ingress_ref = next(item["reference"] for item in references if item["kind"] == "ingress_receipt")
        print(json.dumps({
            "schemaVersion": "NonBypassHappyVerticalProofV1",
            "run": args.run,
            "image": "iiidev/iii:0.19.4@sha256:14ed48b463d8a2e0d3583512acf106b3514f406c5e9965a5854710ff936e1e86",
            "topology": {
                "fixtureDigest": os.environ["PROOF_FIXTURE_DIGEST"],
                "iiiCliPath": "/opt/iii/iii",
                "iiiUrl": "ws://proof-iii:49134",
                "relay": "three-fixed-callback-paths",
            },
            "command": {"id": command_id, "runId": args.run},
            "attempt": {"id": attempt_id, "commandId": command_id},
            "lifecycleHashes": lifecycle,
            "reportHash": report_ref,
            "ingressReceiptHash": ingress_ref,
            "researchGraphManifestRef": manifest_ref,
            "pin": pinned["pinnedFold"],
            "decision": decision,
            "execution": execution,
            "receiverReceipt": final_attempt,
            "redactionProfile": materialization.get("redactionProfileVersion"),
        }, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
