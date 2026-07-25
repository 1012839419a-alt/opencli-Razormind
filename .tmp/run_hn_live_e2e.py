import asyncio
import json
from uuid import uuid4

import httpx

from tests.integration.test_workflow_opencli_hda_trace_api import (
    _multi_source_opencli_hda_project,
)


def build_project() -> dict:
    project = _multi_source_opencli_hda_project()
    package = project["nodes"][0]
    package["topicCollapse"]["nodeCount"] = 6
    internals = package["internals"]
    for source in internals["nodes"][1:3]:
        source["params"].update(
            {
                "site": "hn-live-case",
                "command": "top",
                "args": {"limit": 2},
                "opencliAdapterNodeId": "opencli.adapter.hn-live-case.top",
            }
        )
    internals["nodes"][-1] = {
        "id": "accept-records",
        "kind": "control",
        "capability": "accept",
        "params": {
            "mode": "automatic_with_review",
            "schema": "record.v1",
            "dedupe": "required",
            "lineageRequired": True,
            "minQuality": 0,
        },
        "ui": {"catalogId": "intelligence.control.record-acceptance"},
    }
    internals["nodes"].append(
        {
            "id": "record-sink",
            "kind": "sink",
            "capability": "store",
            "params": {
                "target": "records",
                "writeMode": "append",
                "preserveLineage": True,
            },
            "ui": {"catalogId": "intelligence.sink.records"},
        }
    )
    internals["edges"][-1].update(
        {
            "id": "normalize-accept",
            "target": "accept-records",
            "sourcePort": "out",
            "targetPort": "candidates",
        }
    )
    internals["edges"].append(
        {
            "id": "accept-sink",
            "source": "accept-records",
            "target": "record-sink",
            "sourcePort": "records",
            "targetPort": "records",
        }
    )
    return project


async def main() -> None:
    suffix = uuid4().hex[:8]
    run_id = f"run-hn-live-e2e-{suffix}"
    trace_id = f"trace-hn-live-e2e-{suffix}"
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8035", timeout=60) as client:
        catalog_response = await client.get(
            "/api/v1/workflows/opencli-adapter-nodes",
            params={"refresh": "true"},
        )
        catalog_response.raise_for_status()
        catalog = catalog_response.json()["data"]["nodes"]
        adapter = next(
            node
            for node in catalog
            if node["id"] == "opencli.adapter.hn-live-case.top"
        )

        run_response = await client.post(
            "/api/v1/workflows/runs",
            json={
                "project": build_project(),
                "packageNodeId": "multi-source-opencli",
                "runId": run_id,
                "traceId": trace_id,
            },
        )
        run_response.raise_for_status()
        run = run_response.json()["data"]

        events_response = await client.get(f"/api/v1/workflows/runs/{run_id}/events")
        events_response.raise_for_status()
        events = events_response.json()["data"]
        source_dispatches = [
            event["details"]["agentDispatch"]
            for event in events
            if event["eventType"] == "partial"
            and event["nodeId"]
            in {
                "multi-source-opencli::source-bilibili",
                "multi-source-opencli::source-xiaohongshu",
            }
        ]
        normalize = next(
            event["details"]
            for event in events
            if event["eventType"] == "partial"
            and event["nodeId"] == "multi-source-opencli::internal-normalize"
        )
        sink = next(
            event["details"]
            for event in events
            if event["eventType"] == "partial"
            and event["nodeId"] == "multi-source-opencli::record-sink"
        )
        records = []
        for ref in sink["storedRefs"]:
            record_response = await client.get(f"/api/v1/records/{ref['recordId']}")
            record_response.raise_for_status()
            record = record_response.json()["data"]
            normalized = record["normalized_data"]
            records.append(
                {
                    "recordId": ref["recordId"],
                    "title": normalized.get("title"),
                    "url": normalized.get("url"),
                    "sourceNodeId": ref["lineage"][0]["nodeId"],
                    "artifact": ref["lineage"][0]["artifact"],
                }
            )

    print(
        json.dumps(
            {
                "adapter": {
                    "id": adapter["id"],
                    "status": adapter["status"],
                    "browser": adapter["browser"],
                    "site": adapter["site"],
                    "command": adapter["command"],
                },
                "run": {
                    "runId": run_id,
                    "traceId": trace_id,
                    "status": run["status"],
                    "valid": run["valid"],
                },
                "sourceDispatches": source_dispatches,
                "normalizeInputItemCount": normalize["inputItemCount"],
                "sink": {
                    "inputRecordCount": sink["inputRecordCount"],
                    "storedRecordCount": sink["storedRecordCount"],
                },
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
