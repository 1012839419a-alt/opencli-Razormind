"""OpenCLI Admin Tool Capability registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.schemas.workflow import (
    WorkflowCapabilityVersionPin,
    WorkflowToolCapabilitiesResponse,
    WorkflowToolCapability,
    WorkflowToolCapabilityExecutor,
    WorkflowToolCapabilityPort,
)
from backend.workflow.bbx_tool_nodes import BBX_EXECUTOR_MODE, BBX_TOOL_CAPABILITY_ID
from backend.workflow.gaojixing_certification import (
    GAOJIXING_BATCH_CERTIFY_EXECUTOR,
    GAOJIXING_BATCH_CERTIFY_TOOL_ID,
)
from backend.workflow.gaojixing_doubao import (
    GAOJIXING_DOUBAO_BATCH_EXECUTOR,
    GAOJIXING_DOUBAO_BATCH_TOOL_ID,
    GAOJIXING_FEISHU_WEBHOOK_ENV,
)
from backend.workflow.joyai_vl_executor import (
    JOYAI_VL_INTERACTION_EXECUTOR,
    JOYAI_VL_TOOL_CAPABILITY_ID,
)
from backend.workflow.kats_runtime import kats_tool_capabilities
from backend.workflow.native_intelligence_executor import (
    NATIVE_INTELLIGENCE_ACTIONS,
    NATIVE_INTELLIGENCE_EXECUTOR,
    native_intelligence_action_manifest,
)
from backend.workflow.opentabs_tool_nodes import (
    OPENTABS_EXECUTOR_MODE,
    OPENTABS_TOOL_CAPABILITY_ID,
)
from backend.workflow.realtime_market_executor import OKX_MARKET_TICKER_SNAPSHOT_EXECUTOR
from backend.workflow.situation_awareness import (
    SITUATION_AWARENESS_EXECUTOR,
    SITUATION_AWARENESS_TOOL_CAPABILITY_ID,
)
from backend.workflow.swarm_simulation import (
    SWARM_SIMULATION_EXECUTOR,
    SWARM_SIMULATION_TOOL_CAPABILITY_ID,
)

WORKFLOW_TOOL_PACKAGE = "opencli-admin"
WORKFLOW_TOOL_PACKAGE_VERSION = "0.1.0"
ALLOWED_AUTHORITATIVE_PROVENANCE = {"built-in", "verified"}


@dataclass(frozen=True)
class WorkflowCapabilityPinIssue:
    code: str
    message: str


def validate_workflow_tool_capability_version_pin(
    tool_id: str,
    version_pin: Any,
    *,
    require_pin: bool = True,
) -> WorkflowCapabilityPinIssue | None:
    """Validate a node pin against the installed Tool Capability registry.

    ``require_pin=True`` is the persistence-grade contract: authoritative
    Plans must carry an explicit pin. Compile/run callers pass
    ``require_pin=False`` — an absent pin adopts the registry's current
    version, and only an explicit mismatch is an error."""

    tool = resolve_workflow_tool_capability(tool_id)
    if tool is not None and tool.versionPin is None:
        # Registry entry declares no pinned version (e.g. native intelligence
        # tools) — pin enforcement does not apply to this capability.
        return None
    if tool is not None and version_pin is None and not require_pin:
        return None
    if tool is None:
        return WorkflowCapabilityPinIssue(
            code="unknown_tool_capability",
            message=f'Tool Capability "{tool_id}" is not installed in the registry.',
        )
    if not isinstance(version_pin, dict):
        return WorkflowCapabilityPinIssue(
            code="unpinned_tool_capability",
            message=(
                "must pin the exact package and capability version for "
                f'Tool Capability "{tool_id}".'
            ),
        )

    provenance = version_pin.get("provenance")
    if provenance not in ALLOWED_AUTHORITATIVE_PROVENANCE:
        return WorkflowCapabilityPinIssue(
            code="disallowed_tool_capability_provenance",
            message=(
                f'Tool Capability "{tool_id}" uses provenance {provenance!r}; '
                "authoritative definitions allow only built-in or verified packages."
            ),
        )

    try:
        submitted = WorkflowCapabilityVersionPin.model_validate(version_pin)
    except ValidationError:
        return WorkflowCapabilityPinIssue(
            code="invalid_tool_capability_version_pin",
            message=f'Tool Capability "{tool_id}" has an incomplete version pin.',
        )

    expected = tool.versionPin
    if submitted != expected:
        return WorkflowCapabilityPinIssue(
            code="tool_capability_version_pin_mismatch",
            message=(
                f'Tool Capability "{tool_id}" version pin does not match the '
                "installed registry entry."
            ),
        )
    return None


def _version_pin(capability_version: str = "1.0.0") -> WorkflowCapabilityVersionPin:
    return WorkflowCapabilityVersionPin(
        package=WORKFLOW_TOOL_PACKAGE,
        packageVersion=WORKFLOW_TOOL_PACKAGE_VERSION,
        capabilityVersion=capability_version,
        provenance="built-in",
    )


def list_workflow_tool_capabilities() -> WorkflowToolCapabilitiesResponse:
    """Return registered OpenCLI Admin tool capabilities."""

    return WorkflowToolCapabilitiesResponse(tools=_tool_capabilities())


def resolve_workflow_tool_capability(tool_id: str) -> WorkflowToolCapability | None:
    """Resolve a tool capability by id."""

    return next((tool for tool in _tool_capabilities() if tool.id == tool_id), None)


def _tool_capabilities() -> list[WorkflowToolCapability]:
    return [
        WorkflowToolCapability(
            id=BBX_TOOL_CAPABILITY_ID,
            label="BBX Browser Bridge Tool",
            description=(
                "Invokes a Browser Bridge method through the local bbx CLI "
                "against the user's current authenticated browser."
            ),
            status="runnable",
            provider="bbx",
            inputPorts=[WorkflowToolCapabilityPort(name="in", type="unknown")],
            outputPorts=[WorkflowToolCapabilityPort(name="out", type="unknown")],
            executor=WorkflowToolCapabilityExecutor(
                mode=BBX_EXECUTOR_MODE,
                description="Calls bbx call [--tab <tabId>] <method> <paramsJson>.",
            ),
            tags=["tool", "browser", "bbx", "browser-bridge", "authenticated-session"],
            manifest={
                "schema": "tool-capability.bbx-call.v1",
                "runtime": {"binding": "workflow.external-tool.capability"},
                "resources": ["bbx_daemon", "browser_bridge_extension"],
                "permissions": [
                    "canFetchNetwork",
                    "write:canMutateExternalSites",
                    "bbx_browser_access",
                ],
                "trace": {
                    "events": [
                        "tool_call_started",
                        "partial:outputItemCount",
                        "tool_call_completed",
                        "completed",
                    ]
                },
            },
        ),
        WorkflowToolCapability(
            id=OPENTABS_TOOL_CAPABILITY_ID,
            label="OpenTabs Browser Tool",
            description=(
                "Invokes a tool discovered from the local OpenTabs server "
                "against the user's authenticated browser tabs."
            ),
            status="runnable",
            provider="opentabs",
            inputPorts=[WorkflowToolCapabilityPort(name="in", type="unknown")],
            outputPorts=[WorkflowToolCapabilityPort(name="out", type="unknown")],
            executor=WorkflowToolCapabilityExecutor(
                mode=OPENTABS_EXECUTOR_MODE,
                description="Calls OpenTabs POST /tools/{name}/call.",
            ),
            tags=["tool", "browser", "opentabs", "authenticated-session"],
            manifest={
                "schema": "tool-capability.opentabs-call.v1",
                "runtime": {"binding": "workflow.external-tool.capability"},
                "resources": ["opentabs_local_server", "browser_extension"],
                "permissions": [
                    "canFetchNetwork",
                    "write:canMutateExternalSites",
                    "opentabs_tool_permission",
                ],
                "trace": {
                    "events": [
                        "tool_call_started",
                        "partial:outputItemCount",
                        "tool_call_completed",
                        "completed",
                    ]
                },
            },
        ),
        WorkflowToolCapability(
            id="tool.search.fixture",
            label="Fixture Search Tool",
            description=(
                "Deterministic fixture-backed search capability for imported "
                "external-runtime Tool nodes during Canvas review."
            ),
            status="runnable",
            provider="opencli-admin",
            inputPorts=[WorkflowToolCapabilityPort(name="in", type="unknown")],
            outputPorts=[WorkflowToolCapabilityPort(name="out", type="unknown")],
            executor=WorkflowToolCapabilityExecutor(
                mode="fixture",
                description="Reads fixture output from node params.",
            ),
            versionPin=_version_pin(),
            tags=["tool", "fixture", "external-runtime", "review"],
            manifest={
                "schema": "tool-capability.fixture-search.v1",
                "runtime": {"binding": "workflow.external-tool.capability"},
                "permissions": ["canvas_review_required"],
                "trace": {
                    "events": [
                        "tool_call_started",
                        "partial:outputItemCount",
                        "tool_call_completed",
                        "completed",
                    ]
                },
            },
        ),
        _realtime_tool(
            id="tool.realtime.stream.subscribe",
            label="Realtime Stream Subscribe",
            description=(
                "Tool capability for live/replay stream acquisition. It emits "
                "event[] for market data, web events, social feeds, or sensor-like sources."
            ),
            input_type="trigger",
            output_type="event[]",
            tags=["tool", "realtime", "stream", "subscribe", "replay"],
            schema="tool-capability.realtime-stream-subscribe.v1",
            resources=["stream_adapter", "offset_checkpoint", "run_trace"],
            executor=WorkflowToolCapabilityExecutor(
                mode=OKX_MARKET_TICKER_SNAPSHOT_EXECUTOR,
                description=(
                    "Collects one real OKX public ticker snapshot for the first "
                    "runtime acquisition loop; WS smoke covers live subscribe."
                ),
                params={"provider": "okx", "channel": "tickers", "instId": "ETH-USDT-SWAP"},
            ),
        ),
        _realtime_tool(
            id="tool.realtime.event.normalize",
            label="Realtime Event Normalize",
            description=(
                "Tool capability for normalizing raw stream payloads into event.v1 "
                "while preserving event-time, source, raw payload, and lineage."
            ),
            input_type="event[]",
            output_type="event[]",
            tags=["tool", "realtime", "event", "normalize"],
            schema="tool-capability.realtime-event-normalize.v1",
            resources=["event_schema_registry"],
        ),
        _realtime_tool(
            id="tool.realtime.window.rolling",
            label="Realtime Rolling Window",
            description=(
                "Tool capability for event-time rolling windows, watermark handling, "
                "dedupe boundary, and replayable window aggregation."
            ),
            input_type="event[]",
            output_type="window[]",
            tags=["tool", "realtime", "window", "watermark", "dedupe"],
            schema="tool-capability.realtime-window-rolling.v1",
            resources=["window_state", "watermark_clock", "checkpoint_store"],
        ),
        _realtime_tool(
            id="tool.realtime.state.cache",
            label="Realtime State Cache",
            description=(
                "Tool capability for incremental state snapshots used by realtime "
                "feature computation and replay."
            ),
            input_type="window[]",
            output_type="stateSnapshot[]",
            tags=["tool", "realtime", "state", "cache", "checkpoint"],
            schema="tool-capability.realtime-state-cache.v1",
            resources=["state_store", "checkpoint_store"],
        ),
        _realtime_tool(
            id="tool.realtime.feature.compute",
            label="Realtime Feature Compute",
            description=(
                "Tool capability for incremental quant and situation-awareness features "
                "such as count, rate, volatility, spread, severity, or momentum."
            ),
            input_type="stateSnapshot[]",
            output_type="feature[]",
            tags=["tool", "realtime", "feature", "quant", "situation"],
            schema="tool-capability.realtime-feature-compute.v1",
            resources=["feature_registry"],
        ),
        _realtime_tool(
            id="tool.realtime.signal.emit",
            label="Realtime Signal Emit",
            description=(
                "Tool capability for producing traceable signal[] outputs. It emits "
                "signals for review/automation and must not directly place orders."
            ),
            input_type="feature[]",
            output_type="signal[]",
            tags=["tool", "realtime", "signal", "alert", "quant"],
            schema="tool-capability.realtime-signal-emit.v1",
            resources=["signal_policy", "run_trace"],
        ),
        _realtime_tool(
            id=JOYAI_VL_TOOL_CAPABILITY_ID,
            label="JoyAI VL Interaction",
            description=(
                "Vision-language interaction over video/image media via a "
                "self-hosted JoyAI-VL-Interaction deployment (JD open source, "
                "8B, vLLM-Omni serving). Can send direct video or a bounded "
                "ffmpeg-sampled frame set for fast OCR/content understanding; "
                "emits the model's interaction reply as event[]."
            ),
            input_type="event[]",
            output_type="event[]",
            tags=["tool", "realtime", "vision", "vl", "interaction", "joyai"],
            schema="tool-capability.vl-interaction.v1",
            resources=["media_reference", "run_trace"],
            executor=WorkflowToolCapabilityExecutor(
                mode=JOYAI_VL_INTERACTION_EXECUTOR,
                description=(
                    "POSTs one chat-completions interaction turn to the "
                    "JOYAI_VL_URL vLLM-Omni endpoint; unconfigured endpoint "
                    "degrades to an error event, never a run crash."
                ),
                params={"model": "JoyAI-VL-Interaction-Preview"},
            ),
        ),
        _realtime_tool(
            id=SITUATION_AWARENESS_TOOL_CAPABILITY_ID,
            label="近 30 天事态感知",
            description=(
                "对上游多平台证据执行严格时间窗口、URL/内容去重、互动强度、"
                "主题聚合、基线对比和规则型异常检测，输出带限制说明的研究简报。"
            ),
            input_type="recordCandidate[]",
            output_type="situationReport[]",
            tags=[
                "tool",
                "intelligence",
                "research",
                "last30days",
                "situation-awareness",
            ],
            schema="tool-capability.situation-awareness.v1",
            resources=["run_trace", "evidence_items"],
            executor=WorkflowToolCapabilityExecutor(
                mode=SITUATION_AWARENESS_EXECUTOR,
                description=(
                    "Runs the built-in deterministic recent-window analysis. "
                    "Collection remains an upstream workflow concern."
                ),
                params={
                    "provider": "opencli-native",
                    "windowDays": 30,
                    "baselineDays": 30,
                    "includeUnknownDates": False,
                    "topK": 10,
                },
            ),
            catalog={
                "id": SITUATION_AWARENESS_TOOL_CAPABILITY_ID,
                "category": "processing",
                "icon": "Radar",
            },
        ),
        _realtime_tool(
            id=SWARM_SIMULATION_TOOL_CAPABILITY_ID,
            label="群体智能推演",
            description=(
                "把事态报告或种子材料转换为显式标注的群体推演。默认本地确定性 provider "
                "可离线验证；MiroFish provider 通过私有 sidecar 暴露完整生命周期操作面。"
            ),
            input_type="situationReport[]",
            output_type="swarmForecast[]",
            tags=["tool", "simulation", "swarm", "forecast", "mirofish"],
            schema="tool-capability.swarm-simulation.v1",
            resources=[
                "run_trace",
                "simulation_provider",
                "simulation_artifacts",
            ],
            executor=WorkflowToolCapabilityExecutor(
                mode=SWARM_SIMULATION_EXECUTOR,
                description=(
                    "Runs the built-in deterministic provider or one bounded "
                    "lifecycle operation per invocation against a private MiroFish sidecar."
                ),
                params={
                    "provider": "local",
                    "agentCount": 12,
                    "maxRounds": 8,
                    "platforms": ["twitter", "reddit"],
                    "enableGraphMemoryUpdate": False,
                },
            ),
            catalog={
                "id": SWARM_SIMULATION_TOOL_CAPABILITY_ID,
                "category": "processing",
                "icon": "Network",
            },
        ),
        _realtime_tool(
            id=GAOJIXING_DOUBAO_BATCH_TOOL_ID,
            label="豆包证据批次采集",
            description=(
                "按规范2.2审计离线夹具或现有项目归档，并提供不提交问句的"
                "Hermes只读预检。"
            ),
            input_type="batchRequest[]",
            output_type="gaojixingBatchResult[]",
            tags=["tool", "gaojixing", "doubao", "evidence", "batch"],
            schema="tool-capability.gaojixing-doubao-batch.v1",
            resources=["gaojixing_question_bank", "doubao_session", "evidence_store"],
            executor=WorkflowToolCapabilityExecutor(
                mode=GAOJIXING_DOUBAO_BATCH_EXECUTOR,
                description=(
                    "Runs offline_fixture, project_archive, or the non-mutating "
                    "live_preflight; it does not perform a new Doubao search."
                ),
                params={
                    "sourceMode": "offline_fixture",
                    "fixtureId": "gaojixing-doubao-offline-v1",
                    "feishuWebhookEnv": GAOJIXING_FEISHU_WEBHOOK_ENV,
                },
            ),
            manifest_extra={
                "execution": {
                    "sourceModes": [
                        "offline_fixture",
                        "project_archive",
                        "live_preflight",
                    ],
                    "newSearchEnabled": False,
                }
            },
        ),
        _realtime_tool(
            id=GAOJIXING_BATCH_CERTIFY_TOOL_ID,
            label="批次终审与交付",
            description=(
                "对规范2.2 raw、Markdown、进度、页面模块及截图引用、路径和哈希"
                "做结构核验；不做视觉或OCR内容鉴真。"
            ),
            input_type="gaojixingBatchResult[]",
            output_type="certificationReport[]",
            tags=["tool", "gaojixing", "certification", "evidence"],
            schema="tool-capability.gaojixing-batch-certification.v1",
            resources=["gaojixing_project_root", "gaojixing_question_bank"],
            executor=WorkflowToolCapabilityExecutor(
                mode=GAOJIXING_BATCH_CERTIFY_EXECUTOR,
                description=(
                    "Structurally certifies an upstream fixture batch or a real规范2.2 "
                    "project directory without visual or OCR authentication."
                ),
                params={
                    "sourceMode": "offline_fixture",
                    "fixtureId": "gaojixing-doubao-offline-v1",
                },
            ),
        ),
        *[_native_intelligence_tool(action) for action in NATIVE_INTELLIGENCE_ACTIONS],
        *kats_tool_capabilities(),
    ]


def _native_intelligence_tool(action) -> WorkflowToolCapability:
    manifest = native_intelligence_action_manifest(action)
    readiness = manifest["readiness"]
    return WorkflowToolCapability(
        id=action.tool_id,
        label=action.label,
        description=(
            f"Deterministic, offline native intelligence action: {action.name}. "
            "Uses the durable IntelligenceSession aggregate and emits Workflow run trace events."
        ),
        status=readiness["status"],
        provider="opencli-admin",
        inputPorts=[WorkflowToolCapabilityPort(name="in", type=action.input_type)],
        outputPorts=[WorkflowToolCapabilityPort(name="out", type=action.output_type)],
        executor=WorkflowToolCapabilityExecutor(
            mode=NATIVE_INTELLIGENCE_EXECUTOR,
            description="Dispatches one certified native lifecycle action.",
            params={"action": action.name},
        ),
        tags=["tool", "intelligence", "native", "offline", *action.name.split(".")],
        manifest=manifest,
    )


def _realtime_tool(
    *,
    id: str,
    label: str,
    description: str,
    input_type: str,
    output_type: str,
    tags: list[str],
    schema: str,
    resources: list[str],
    executor: WorkflowToolCapabilityExecutor | None = None,
    catalog: dict[str, str] | None = None,
    manifest_extra: dict[str, Any] | None = None,
) -> WorkflowToolCapability:
    return WorkflowToolCapability(
        id=id,
        label=label,
        description=description,
        status="runnable",
        provider="opencli-admin",
        inputPorts=[WorkflowToolCapabilityPort(name="in", type=input_type)],
        outputPorts=[WorkflowToolCapabilityPort(name="out", type=output_type)],
        executor=executor
        or WorkflowToolCapabilityExecutor(
            mode="fixture",
            description="Registered tool capability; concrete executor is bound by runtime policy.",
        ),
        versionPin=_version_pin(),
        tags=tags,
        manifest={
            "schema": schema,
            "runtime": {"binding": "workflow.external-tool.capability"},
            "resources": resources,
            "permissions": ["runtime_tool_call"],
            "trace": {
                "events": [
                    "tool_call_started",
                    "partial:outputItemCount",
                    "tool_call_completed",
                    "completed",
                ]
            },
            "canvas": {"node": catalog is not None},
            **(manifest_extra or {}),
            **(
                {
                    "nodeCatalog": {
                        "id": catalog["id"],
                        "authority": "backend",
                        "origin": "tool-capability",
                        "category": catalog["category"],
                        "kind": "action",
                        "capability": "store",
                    },
                    "presentation": {"icon": catalog["icon"]},
                }
                if catalog is not None
                else {}
            ),
        },
    )
