"""PTT acceptance for the importable A-share premarket research snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE = (
    Path(__file__).parents[2]
    / "frontend"
    / "lib"
    / "workflow"
    / "fixtures"
    / "workflow-a-share-premarket-research.json"
)


@pytest.mark.asyncio
async def test_a_share_premarket_snapshot_runs_through_generic_research_loop(client):
    project = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    compiled = await client.post("/api/v1/workflows/compile", json={"project": project})

    assert compiled.status_code == 200
    assert compiled.json()["data"]["valid"] is True

    run = await client.post(
        "/api/v1/workflows/runs",
        json={
            "project": project,
            "runId": "run-a-share-premarket-ptt",
            "traceId": "trace-a-share-premarket-ptt",
        },
    )
    assert run.status_code == 202
    assert run.json()["data"]["status"] == "completed"

    ledger_response = await client.get(
        "/api/v1/workflows/runs/run-a-share-premarket-ptt/research-ledger"
    )
    assert ledger_response.status_code == 200
    entry = ledger_response.json()["data"]["entries"][0]
    assert entry["researchStatus"] == "final"
    assert entry["gaps"] == []
    assert entry["publishAllowed"] is True
    assert len(entry["evidenceRefs"]) == 4
    assert {
        reference["url"].split("/")[2]
        for reference in entry["evidenceRefs"]
    } == {"www.sse.com.cn", "www.szse.cn", "www.stats.gov.cn"}

    events = (
        await client.get(
            "/api/v1/workflows/runs/run-a-share-premarket-ptt/events"
        )
    ).json()["data"]
    partials = {
        event["nodeId"]: event["details"]["metrics"]
        for event in events
        if event["eventType"] == "partial" and "metrics" in event["details"]
    }
    assert partials["research-claim"]["claimCount"] == 4
    assert partials["research-scenario"]["scenarioCount"] == 2
    assert partials["research-publish-gate"]["publishAllowed"] is True
