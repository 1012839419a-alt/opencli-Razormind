from backend.workflow.capability_projection import build_workflow_capabilities
from backend.workflow.tool_capabilities import list_workflow_tool_capabilities
from backend.workflow.wigolo_tool_nodes import (
    WIGOLO_EXECUTOR_MODE,
    WIGOLO_RUNTIME_MISSING,
    WIGOLO_TOOL_IDS,
)


def test_wigolo_tools_use_the_existing_backend_node_catalog():
    registry = {
        tool.id: tool
        for tool in list_workflow_tool_capabilities().tools
        if tool.provider == "wigolo"
    }
    catalog = {item.id: item for item in build_workflow_capabilities().catalog}

    assert set(registry) == WIGOLO_TOOL_IDS
    assert WIGOLO_TOOL_IDS <= catalog.keys()

    for tool_id, tool in registry.items():
        projected = catalog[tool_id]
        assert tool.status == "blocked"
        assert tool.executor.mode == WIGOLO_EXECUTOR_MODE
        assert tool.manifest["canvas"] == {"node": True}
        assert tool.manifest["nodeCatalog"]["authority"] == "backend"
        assert tool.manifest["readiness"]["missingReasons"] == [WIGOLO_RUNTIME_MISSING]
        assert projected.status == "blocked"
        assert projected.backendAvailable is False
        assert projected.manifest["toolCapability"]["id"] == tool_id
