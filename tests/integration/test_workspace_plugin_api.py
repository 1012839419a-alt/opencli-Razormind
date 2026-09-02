from __future__ import annotations

from pathlib import Path

from backend.main import app
from backend.models.identity import User, Workspace, WorkspaceMembership, WorkspaceRole
from backend.models.studio import (
    StudioProject,
    StudioWorkflow,
    StudioWorkflowDraft,
    StudioWorkspace,
)
from backend.security.identity import RequestIdentity, get_request_identity

FIXTURE = Path(__file__).parents[1] / "fixtures" / "dify_plugins" / "tool_manifest.yaml"


async def _workspace(db_session, *, name: str, subject: str, role: WorkspaceRole) -> Workspace:
    user = User(subject=subject, display_name=subject)
    workspace = Workspace(name=name, slug=name.lower().replace(" ", "-"))
    db_session.add_all([user, workspace])
    await db_session.flush()
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role))
    await db_session.flush()
    return workspace


def _identity(subject: str) -> RequestIdentity:
    return RequestIdentity(subject=subject, auth_method="test")


async def test_workspace_plugin_installation_isolated_and_lifecycle_is_authorized(
    client, db_session
):
    owner_workspace = await _workspace(
        db_session, name="Owner", subject="owner", role=WorkspaceRole.ADMIN
    )
    other_workspace = await _workspace(
        db_session, name="Other", subject="other", role=WorkspaceRole.VIEWER
    )
    app.dependency_overrides[get_request_identity] = lambda: _identity("owner")

    imported = await client.post(
        f"/api/v1/workspaces/{owner_workspace.id}/plugins/import/dify",
        files={"file": ("manifest.yaml", FIXTURE.read_bytes(), "text/yaml")},
    )
    assert imported.status_code == 201
    installation = imported.json()["data"]
    assert installation["workspaceId"] == owner_workspace.id
    assert installation["enabled"] is False
    assert installation["runtimeStatus"] == "BLOCKED"

    owner_listing = await client.get(f"/api/v1/workspaces/{owner_workspace.id}/plugins")
    assert owner_listing.status_code == 200
    assert any(row["id"] == installation["id"] for row in owner_listing.json()["data"])
    global_listing = await client.get("/api/v1/plugins")
    assert global_listing.status_code == 200
    assert all(row["id"] != installation["id"] for row in global_listing.json()["data"])

    capability_listing = await client.get(
        f"/api/v1/workspaces/{owner_workspace.id}/plugins/capabilities"
    )
    assert capability_listing.status_code == 200
    plugin_node = next(
        node
        for node in capability_listing.json()["data"]["nodes"]
        if node["origin"] == "plugin"
    )
    assert plugin_node["installationId"] == installation["id"]
    assert plugin_node["pluginVersion"] == installation["version"]

    app.dependency_overrides[get_request_identity] = lambda: _identity("other")
    other_listing = await client.get(f"/api/v1/workspaces/{other_workspace.id}/plugins")
    assert other_listing.status_code == 200
    assert all(row["id"] != installation["id"] for row in other_listing.json()["data"])
    denied_import = await client.post(
        f"/api/v1/workspaces/{other_workspace.id}/plugins/import/dify",
        files={"file": ("manifest.yaml", FIXTURE.read_bytes(), "text/yaml")},
    )
    assert denied_import.status_code == 403

    app.dependency_overrides[get_request_identity] = lambda: _identity("owner")
    cross_workspace_detail = await client.get(
        f"/api/v1/workspaces/{other_workspace.id}/plugins/{installation['id']}"
    )
    assert cross_workspace_detail.status_code == 403

    enabled = await client.patch(
        f"/api/v1/workspaces/{owner_workspace.id}/plugins/{installation['id']}",
        json={"enabled": True, "grantedPermissions": ["tool"]},
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["enabled"] is True
    assert enabled.json()["data"]["grantedPermissions"] == ["tool"]
    assert any(
        blocker["code"] == "plugin_permission_not_granted"
        for blocker in enabled.json()["data"]["blockers"]
    )
    assert enabled.json()["data"]["runtimeStatus"] == "BLOCKED"
    assert all(
        blocker["code"] != "plugin_disabled"
        for blocker in enabled.json()["data"]["blockers"]
    )

    legacy_workspace = StudioWorkspace(name="Owner Studio", slug=owner_workspace.slug)
    db_session.add(legacy_workspace)
    await db_session.flush()
    project = StudioProject(
        workspace_id=legacy_workspace.id,
        name="Referenced project",
        slug="referenced-project",
        created_by_user_id="owner",
    )
    db_session.add(project)
    await db_session.flush()
    workflow = StudioWorkflow(project_id=project.id, name="Workflow")
    db_session.add(workflow)
    await db_session.flush()
    db_session.add(
        StudioWorkflowDraft(
            workflow_id=workflow.id,
            graph={
                "nodes": [
                    {
                        "pluginProviderKey": installation["providerKey"],
                        "pluginVersion": installation["version"],
                    }
                ]
            },
            updated_by_user_id="owner",
        )
    )
    await db_session.flush()
    blocked_delete = await client.delete(
        f"/api/v1/workspaces/{owner_workspace.id}/plugins/{installation['id']}"
    )
    assert blocked_delete.status_code == 409
    assert blocked_delete.json()["detail"]["code"] == "plugin_installation_in_use"

    invalid_permission = await client.patch(
        f"/api/v1/workspaces/{owner_workspace.id}/plugins/{installation['id']}",
        json={"grantedPermissions": ["not-declared"]},
    )
    assert invalid_permission.status_code == 422
    assert invalid_permission.json()["detail"]["code"] == "plugin_permission_not_declared"
