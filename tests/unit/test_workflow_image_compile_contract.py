from backend.schemas.workflow import WorkflowProject, WorkflowProjectNode
from backend.workflow.capability_projection import _catalog_capabilities
from backend.workflow.compiler import _node_port_contracts, compile_workflow_project
from backend.workflow.node_registry import resolve_node_origin


def _ports(node: WorkflowProjectNode) -> tuple[list[tuple], list[tuple]]:
    contracts = _node_port_contracts(node)
    assert contracts is not None
    inputs, outputs = contracts
    return (
        [(port.id, port.type, port.required) for port in inputs],
        [(port.id, port.type, port.required) for port in outputs],
    )


def test_image_generation_catalog_and_ports_are_backend_owned() -> None:
    node = WorkflowProjectNode(
        id="generate",
        kind="media",
        capability="generate",
        params={"canvasSnapshotId": "snapshot-v1"},
        ui={"catalogId": "media.image-generation"},
    )

    assert resolve_node_origin(node).kind == "node_library"
    assert _ports(node) == (
        [("prompt", "text", False), ("assets", "mediaAsset[]", False)],
        [("assets", "mediaAsset[]", True), ("generation", "mediaGenerationResult", True)],
    )


def test_image_asset_catalog_emits_only_durable_platform_assets() -> None:
    node = WorkflowProjectNode(
        id="assets",
        kind="media",
        capability="fetch",
        params={"assetIds": ["asset-1"]},
        ui={"catalogId": "media.image-asset"},
    )

    assert resolve_node_origin(node).kind == "node_library"
    assert _ports(node) == ([], [("assets", "mediaAsset[]", True)])


def test_platform_image_asset_node_does_not_require_an_adapter() -> None:
    project = WorkflowProject.model_validate(
        {
            "id": "asset-workflow",
            "name": "Asset workflow",
            "profile": "intelligence",
            "nodes": [
                {
                    "id": "assets",
                    "kind": "media",
                    "capability": "fetch",
                    "params": {"assetIds": ["asset-1"]},
                    "ui": {"catalogId": "media.image-asset"},
                }
            ],
        }
    )

    result = compile_workflow_project(project)

    assert result.valid is True
    assert result.errors == []


def test_image_generation_capability_reports_remaining_runtime_gates() -> None:
    capability = next(
        item for item in _catalog_capabilities() if item.id == "media.image-generation"
    )

    assert capability.status == "blocked"
    assert capability.backendAvailable is False
    assert capability.missing == [
        "published_version_run_binding",
        "durable_dispatch_reconciliation",
        "attested_image_runtime",
    ]
