from copy import deepcopy

import httpx
import pytest

from backend.schemas.workflow import WorkflowProject, WorkflowProjectNode
from backend.workflow.capability_projection import build_workflow_capabilities
from backend.workflow.compiler import compile_workflow_project
from backend.workflow.kats_runtime import (
    KATS_CAPABILITY_SPECS,
    KATS_COMMIT,
    KATS_CONTRACT_VERSION,
    KATS_EXECUTOR_MODE,
    KATS_NAME,
    KATS_TOOL_IDS,
    KATS_VERSION,
    execute_kats_operation,
)
from backend.workflow.opencli_hda_tracer import _resolved_kats_params
from backend.workflow.runtime_registry import resolve_runtime_metadata
from backend.workflow.tool_capabilities import list_workflow_tool_capabilities


def _projected_node(tool_id: str) -> WorkflowProjectNode:
    capability = next(
        row for row in build_workflow_capabilities().catalog if row.id == tool_id
    )
    params = {
        parameter["name"]: deepcopy(parameter["default"])
        for parameter in capability.manifest["presentation"]["parameters"]
        if "default" in parameter
    }
    return WorkflowProjectNode.model_validate(
        {
            "id": "kats-node",
            "kind": capability.kind,
            "capability": capability.capability,
            "params": params,
            "ui": {"catalogId": capability.id},
        }
    )


def test_kats_feature_families_are_canvas_visible_and_runtime_bound():
    tools = {
        tool.id: tool
        for tool in list_workflow_tool_capabilities().tools
        if tool.id in KATS_TOOL_IDS
    }
    catalog = {
        row.id: row
        for row in build_workflow_capabilities().catalog
        if row.id in KATS_TOOL_IDS
    }

    assert set(tools) == KATS_TOOL_IDS
    assert set(catalog) == KATS_TOOL_IDS
    assert {spec.operation for spec in KATS_CAPABILITY_SPECS} == {
        "forecast",
        "detect",
        "features",
        "decompose",
        "backtest",
        "tune",
        "simulate",
        "advanced",
    }
    assert all(tool.executor.mode == KATS_EXECUTOR_MODE for tool in tools.values())
    assert all(row.status == "runnable" for row in catalog.values())
    assert all(row.backendAvailable for row in catalog.values())


def test_projected_kats_fields_reach_runtime_tool_params():
    node = _projected_node("tool.timeseries.kats.forecast")
    node.params["algorithm"] = "theta"
    node.params["steps"] = 24
    node.params["operation"] = "advanced"
    node.params["toolParams"] = {"operation": "advanced"}
    project = WorkflowProject.model_validate(
        {
            "id": "kats-workflow",
            "name": "Kats workflow",
            "profile": "intelligence",
            "nodes": [node.model_dump(mode="json")],
            "edges": [],
            "adapters": [],
        }
    )

    compiled = compile_workflow_project(project)
    metadata = resolve_runtime_metadata(node, None)

    assert compiled.valid is True
    binding_input = metadata["binding"]["input"]
    assert binding_input["executorMode"] == KATS_EXECUTOR_MODE
    assert binding_input["executorParams"]["operation"] == "forecast"
    assert binding_input["toolParams"]["operation"] == "advanced"
    assert binding_input["toolParams"]["algorithm"] == "theta"
    assert binding_input["toolParams"]["steps"] == 24
    operation, runtime_params = _resolved_kats_params(binding_input)
    assert operation == "forecast"
    assert runtime_params["operation"] == "forecast"


@pytest.mark.asyncio
async def test_kats_client_rejects_unpinned_runtime(monkeypatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "contractVersion": KATS_CONTRACT_VERSION,
                "engine": {
                    "name": KATS_NAME,
                    "version": KATS_VERSION,
                    "commit": "unexpected",
                },
                "result": {},
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    with pytest.raises(RuntimeError, match="pinned engine identity"):
        await execute_kats_operation("forecast", [], {})

    assert KATS_COMMIT != "unexpected"
