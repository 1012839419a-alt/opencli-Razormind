import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.models.browser import BrowserCapabilityInvocation, BrowserInstance
from backend.schemas.browser import (
    BrowserInstanceConfigUpdate,
    BrowserInstanceCreate,
    BrowserRuntimeBundleCreate,
    RuntimeBundleManifest,
    SlotRuntimeReport,
)
from backend.services import (
    browser_capability_service,
    browser_service,
    plugin_registry_service,
)


def manifest() -> RuntimeBundleManifest:
    return RuntimeBundleManifest.model_validate(
        {
            "name": "opencli-bridge",
            "version": "1.8.5",
            "components": [
                {
                    "kind": "extension",
                    "id": "bridge",
                    "version": "1.8.5",
                    "path": "extensions/bridge",
                    "required": True,
                    "capabilities": ["page.read"],
                },
                {
                    "kind": "script",
                    "id": "page-actions",
                    "version": "1.8.5",
                    "path": "scripts/page-actions",
                    "required": True,
                    "capabilities": [],
                },
                {
                    "kind": "opencli_plugin",
                    "id": "browser-tools",
                    "version": "1.8.5",
                    "path": "plugins/browser-tools",
                    "required": True,
                    "capabilities": [],
                },
            ],
            "capabilities": [
                {
                    "name": "page.read",
                    "component_id": "bridge",
                    "action": "page.read",
                    "runtime": "opentabs",
                    "args_schema": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                    "allowed_hosts": ["example.com"],
                    "risk": "low",
                    "required_gate": None,
                }
            ],
            "act_pack_ids": ["search-research/google-search-serp"],
        }
    )


async def create_bundle(db_session, bundle_manifest: RuntimeBundleManifest | None = None):
    bundle = await browser_service.create_runtime_bundle(
        db_session,
        BrowserRuntimeBundleCreate(manifest=bundle_manifest or manifest()),
    )
    await db_session.commit()
    return bundle


def healthy_report(**overrides) -> SlotRuntimeReport:
    data = {
        "loaded_bundle_name": "opencli-bridge",
        "loaded_bundle_version": "1.8.5",
        "loaded_components": [
            {"kind": "extension", "id": "bridge", "version": "1.8.5", "healthy": True},
            {"kind": "script", "id": "page-actions", "version": "1.8.5", "healthy": True},
            {"kind": "opencli_plugin", "id": "browser-tools", "version": "1.8.5", "healthy": True},
        ],
        "capabilities": ["page.read"],
        "self_check": {"ok": True},
    }
    data.update(overrides)
    return SlotRuntimeReport.model_validate(data)


@pytest.mark.asyncio
async def test_matching_loaded_report_is_ready_and_persists_slot_config(db_session):
    bundle = await create_bundle(db_session)
    instance = await browser_service.create_browser_instance(
        db_session,
        BrowserInstanceCreate(
            endpoint="http://agent:19823",
            profile_name="operator-a",
            runtime_bundle_id=bundle.id,
            startup_pages=["https://example.com"],
            network_policy={"mode": "direct"},
            resource_class="medium",
        ),
    )

    deployment = await browser_service.report_runtime_deployment(
        db_session, instance, healthy_report()
    )

    assert deployment.state == "READY"
    assert instance.runtime_bundle_id == bundle.id
    assert instance.startup_pages == ["https://example.com"]
    assert instance.network_policy == {"mode": "direct"}


@pytest.mark.asyncio
async def test_two_slots_with_the_same_bundle_report_the_same_ready_runtime(db_session):
    bundle = await create_bundle(db_session)
    slots = [
        await browser_service.create_browser_instance(
            db_session,
            BrowserInstanceCreate(
                endpoint=f"http://agent-ready-{index}:19823",
                profile_name=f"operator-ready-{index}",
                runtime_bundle_id=bundle.id,
            ),
        )
        for index in (1, 2)
    ]

    deployments = [
        await browser_service.report_runtime_deployment(db_session, slot, healthy_report())
        for slot in slots
    ]

    assert [deployment.state for deployment in deployments] == ["READY", "READY"]
    assert deployments[0].loaded_components == deployments[1].loaded_components
    assert deployments[0].self_check["capabilities"] == ["page.read"]


@pytest.mark.asyncio
async def test_optional_component_capabilities_are_omitted_when_component_is_absent(db_session):
    manifest_payload = manifest().model_dump()
    manifest_payload["components"][1]["required"] = False
    manifest_payload["capabilities"].append(
        {
            "name": "page.optional",
            "component_id": "page-actions",
            "action": "page.optional",
            "runtime": "opentabs",
            "args_schema": {"type": "object"},
            "allowed_hosts": [],
            "risk": "low",
            "required_gate": None,
        }
    )
    bundle = await create_bundle(db_session, RuntimeBundleManifest.model_validate(manifest_payload))
    instance = BrowserInstance(
        endpoint="http://agent-optional:19823",
        profile_name="operator-optional",
        runtime_bundle_id=bundle.id,
    )
    db_session.add(instance)
    await db_session.flush()
    report = healthy_report(
        loaded_components=[
            component
            for component in healthy_report().model_dump()["loaded_components"]
            if component["id"] != "page-actions"
        ]
    )

    deployment = await browser_service.report_runtime_deployment(db_session, instance, report)

    assert deployment.state == "READY"


@pytest.mark.asyncio
async def test_unknown_component_and_required_extension_failure_are_not_ready(db_session):
    bundle = await create_bundle(db_session)
    instance = BrowserInstance(
        endpoint="http://agent:19824",
        profile_name="operator-b",
        runtime_bundle_id=bundle.id,
    )
    db_session.add(instance)
    await db_session.flush()

    drift = await browser_service.report_runtime_deployment(
        db_session,
        instance,
        healthy_report(
            loaded_components=[
                {"kind": "extension", "id": "bridge", "version": "1.8.5", "healthy": True},
                {"kind": "extension", "id": "foreign", "version": "1", "healthy": True},
            ]
        ),
    )
    assert drift.state == "CONFIG_DRIFT"

    failed = await browser_service.report_runtime_deployment(
        db_session,
        instance,
        healthy_report(
            loaded_components=[
                {"kind": "extension", "id": "bridge", "version": "1.8.5", "healthy": False},
                {"kind": "script", "id": "page-actions", "version": "1.8.5", "healthy": True},
                {
                    "kind": "opencli_plugin",
                    "id": "browser-tools",
                    "version": "1.8.5",
                    "healthy": True,
                },
            ]
        ),
    )
    assert failed.state == "EXTENSION_FAILED"


@pytest.mark.asyncio
async def test_invoke_unready_slot_fails_closed_and_is_audited(db_session):
    bundle = await create_bundle(db_session)
    instance = BrowserInstance(
        endpoint="http://agent:19825",
        profile_name="operator-c",
        runtime_bundle_id=bundle.id,
    )
    db_session.add(instance)
    await db_session.flush()

    with pytest.raises(browser_service.BrowserRuntimeError) as excinfo:
        await browser_capability_service.invoke_capability(
            db_session,
            instance,
            "page.read",
            {"url": "https://example.com"},
            None,
        )

    assert excinfo.value.code == "slot_not_ready"
    invocation = (await db_session.execute(select(BrowserCapabilityInvocation))).scalar_one()
    assert invocation.error["code"] == "slot_not_ready"


@pytest.mark.asyncio
async def test_profile_cannot_be_assigned_to_two_slots(db_session):
    await browser_service.create_browser_instance(
        db_session,
        BrowserInstanceCreate(endpoint="http://agent:19826", profile_name="exclusive"),
    )

    with pytest.raises(browser_service.BrowserRuntimeError) as excinfo:
        await browser_service.create_browser_instance(
            db_session,
            BrowserInstanceCreate(endpoint="http://agent:19827", profile_name="exclusive"),
        )

    assert excinfo.value.code == "profile_in_use"


@pytest.mark.asyncio
async def test_capability_gate_fail_closed_then_records_full_lineage(db_session, monkeypatch):
    manifest_payload = manifest().model_dump()
    manifest_payload["capabilities"][0]["risk"] = "high"
    manifest_payload["capabilities"][0]["required_gate"] = "operator-approval"
    bundle = await create_bundle(db_session, RuntimeBundleManifest.model_validate(manifest_payload))
    instance = BrowserInstance(
        endpoint="http://agent:19828",
        agent_url="http://agent:19828",
        agent_protocol="http",
        profile_name="operator-gated",
        runtime_bundle_id=bundle.id,
    )
    db_session.add(instance)
    await db_session.flush()
    await browser_service.report_runtime_deployment(db_session, instance, healthy_report())

    async def dispatch(_, __, args):
        return {
            "result": {"title": "Example"},
            "page_before": {"url": args["url"]},
            "page_after": {"url": args["url"], "title": "Example"},
        }

    monkeypatch.setattr(browser_capability_service, "_dispatch_capability", dispatch)

    with pytest.raises(browser_service.BrowserRuntimeError) as excinfo:
        await browser_capability_service.invoke_capability(
            db_session,
            instance,
            "page.read",
            {"url": "https://example.com"},
            None,
        )
    assert excinfo.value.code == "gate_not_satisfied"

    with pytest.raises(browser_service.BrowserRuntimeError) as excinfo:
        await browser_capability_service.invoke_capability(
            db_session,
            instance,
            "page.read",
            {"url": "https://example.com"},
            "operator-approval",
        )
    assert excinfo.value.code == "gate_not_satisfied"

    invocation = await browser_capability_service.invoke_capability(
        db_session,
        instance,
        "page.read",
        {"url": "https://example.com"},
        "operator-approval",
        gate_authorized=True,
    )

    assert invocation.output_payload == {
        "result": {"title": "Example"},
        "page_before": {"url": "https://example.com"},
        "page_after": {"url": "https://example.com", "title": "Example"},
    }
    assert invocation.desired_bundle_version == "1.8.5"
    assert invocation.loaded_bundle_version == "1.8.5"
    assert {item["id"] for item in invocation.component_versions} == {
        "bridge",
        "page-actions",
        "browser-tools",
    }
    assert invocation.risk == "high"
    assert invocation.gate == "operator-approval"
    assert invocation.page_before == {"url": "https://example.com"}
    assert invocation.page_after == {
        "url": "https://example.com",
        "title": "Example",
    }


@pytest.mark.asyncio
async def test_bundle_is_projected_as_a_read_only_runtime_plugin(db_session):
    bundle = await create_bundle(db_session)
    instance = await browser_service.create_browser_instance(
        db_session,
        BrowserInstanceCreate(
            endpoint="http://agent:19829",
            profile_name="operator-plugin",
            runtime_bundle_id=bundle.id,
        ),
    )

    before_report = await plugin_registry_service.list_plugin_installations(db_session)
    plugin_before = next(
        item for item in before_report if item.id == f"browser-runtime:{bundle.id}"
    )
    assert plugin_before.runtime_status == "BLOCKED"
    assert plugin_before.plugin_types == ["browser_runtime", "endpoint"]
    assert plugin_before.permissions["components"][0]["id"] == "bridge"

    await browser_service.report_runtime_deployment(db_session, instance, healthy_report())
    after_report = await plugin_registry_service.list_plugin_installations(db_session)
    plugin_after = next(item for item in after_report if item.id == f"browser-runtime:{bundle.id}")
    assert plugin_after.runtime_status == "READY"
    assert plugin_after.capabilities[0].key == "page.read"


@pytest.mark.asyncio
async def test_reassigning_a_bundle_requires_slot_restart(db_session):
    first = await create_bundle(db_session)
    next_manifest = manifest().model_dump()
    next_manifest["version"] = "1.8.6"
    second = await create_bundle(db_session, RuntimeBundleManifest.model_validate(next_manifest))
    instance = await browser_service.create_browser_instance(
        db_session,
        BrowserInstanceCreate(
            endpoint="http://agent:19830",
            profile_name="operator-reassign",
            runtime_bundle_id=first.id,
        ),
    )
    await browser_service.report_runtime_deployment(db_session, instance, healthy_report())

    await browser_service.update_browser_instance(
        db_session,
        instance,
        BrowserInstanceConfigUpdate(runtime_bundle_id=second.id),
    )

    deployment = await browser_service.get_runtime_deployment(db_session, instance.id)
    assert deployment is not None
    assert deployment.state == "RESTART_REQUIRED"


@pytest.mark.asyncio
async def test_assigned_bundle_version_cannot_be_edited_in_place(db_session):
    bundle = await create_bundle(db_session)
    await browser_service.create_browser_instance(
        db_session,
        BrowserInstanceCreate(
            endpoint="http://agent-immutable:19823",
            profile_name="operator-immutable",
            runtime_bundle_id=bundle.id,
        ),
    )

    with pytest.raises(browser_service.BrowserRuntimeError) as excinfo:
        await browser_service.update_runtime_bundle(
            db_session,
            bundle,
            BrowserRuntimeBundleCreate(
                manifest=manifest(),
                trust_level="reviewed",
                source="replacement",
            ),
        )

    assert excinfo.value.code == "bundle_in_use"


def _resolver() -> Path:
    return Path(__file__).parents[2] / "scripts" / "resolve-browser-runtime-bundle.mjs"


def test_bundle_resolver_loads_only_manifest_allowlisted_extensions(tmp_path):
    root = tmp_path / "bundles"
    bundle = root / "research-default" / "4"
    bridge = bundle / "extensions" / "bridge"
    script_host = bundle / "extensions" / "script-host"
    bridge.mkdir(parents=True)
    script_host.mkdir(parents=True)
    (bridge / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "Bridge", "version": "0.1.0"}),
        encoding="utf-8",
    )
    (script_host / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "Script Host", "version": "1.2.0"}),
        encoding="utf-8",
    )
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "name": "research-default",
                "version": "4",
                "components": [
                    {
                        "kind": "extension",
                        "id": "bridge",
                        "version": "0.1.0",
                        "path": "extensions/bridge",
                        "required": True,
                    },
                    {
                        "kind": "extension",
                        "id": "script-host",
                        "version": "1.2.0",
                        "path": "extensions/script-host",
                        "required": True,
                    },
                ],
                "capabilities": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["node", str(_resolver()), str(bundle / "manifest.json"), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(bridge.resolve()), str(script_host.resolve())]

    report_result = subprocess.run(
        [
            "node",
            str(_resolver()),
            str(bundle / "manifest.json"),
            str(root),
            "--report",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    report = SlotRuntimeReport.model_validate_json(report_result.stdout)
    assert report.loaded_bundle_name == "research-default"
    assert {component.id for component in report.loaded_components} == {
        "bridge",
        "script-host",
    }
    assert report.self_check == {"ok": True, "phase": "launcher-resolver"}


def test_bundle_resolver_rejects_component_version_drift(tmp_path):
    root = tmp_path / "bundles"
    bundle = root / "research-default" / "4"
    bridge = bundle / "extensions" / "bridge"
    bridge.mkdir(parents=True)
    (bridge / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "Bridge", "version": "0.1.0"}),
        encoding="utf-8",
    )
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "name": "research-default",
                "version": "4",
                "components": [
                    {
                        "kind": "extension",
                        "id": "bridge",
                        "version": "9.9.9",
                        "path": "extensions/bridge",
                        "required": True,
                    }
                ],
                "capabilities": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["node", str(_resolver()), str(bundle / "manifest.json"), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert "expected version 9.9.9, found 0.1.0" in result.stderr
