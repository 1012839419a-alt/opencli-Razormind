from backend.workflow.capability_projection import build_workflow_capabilities
from backend.workflow.tool_capabilities import list_workflow_tool_capabilities


def test_tool_capability_catalog_projection_is_explicit_and_executable(monkeypatch):
    registry = list_workflow_tool_capabilities()
    fixture = next(tool for tool in registry.tools if tool.id == "tool.search.fixture")
    projected = fixture.model_copy(
        update={
            "id": "tool.osint.metasearch",
            "label": "OSINT Metasearch",
            "manifest": {
                **fixture.manifest,
                "canvas": {"node": True},
                "nodeCatalog": {
                    "id": "tool.osint.metasearch",
                    "authority": "backend",
                    "origin": "tool-capability",
                    "category": "processing",
                    "kind": "action",
                    "capability": "store",
                },
                "presentation": {"icon": "Search"},
            },
        },
        deep=True,
    )
    hidden = fixture.model_copy(update={"id": "tool.osint.hidden"}, deep=True)
    response = registry.model_copy(update={"tools": [projected, hidden]})
    monkeypatch.setattr(
        "backend.workflow.capability_projection.list_workflow_tool_capabilities",
        lambda: response,
    )

    capabilities = build_workflow_capabilities()
    catalog = {item.id: item for item in capabilities.catalog}
    resources = {item.id: item for item in capabilities.resources}

    assert "tool.osint.metasearch" in catalog
    assert "tool.osint.hidden" not in catalog
    item = catalog["tool.osint.metasearch"]
    assert item.status == "runnable"
    assert item.backendAvailable is True
    assert item.kind == "action"
    assert item.capability == "store"
    assert item.runtimeBinding == "workflow.external-tool.capability"
    assert item.manifest["toolCapability"]["id"] == "tool.osint.metasearch"
    assert item.manifest["toolCapability"]["executor"]["mode"] == "fixture"
    assert [field["name"] for field in item.manifest["presentation"]["parameters"][:2]] == [
        "toolCapability",
        "toolParams",
    ]
    assert item.manifest["presentation"]["parameters"][0]["default"]["versionPin"] == {
        "package": "opencli-admin",
        "packageVersion": "0.1.0",
        "capabilityVersion": "1.0.0",
        "provenance": "built-in",
    }
    assert "resource.tool-capability.tool.osint.metasearch" in resources
    assert "resource.tool-capability.tool.osint.hidden" in resources
