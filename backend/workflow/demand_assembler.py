"""Assemble collection needs into reviewable WorkflowProject patches.

The assembler parses a natural-language user need into structured intents via
``intent_parser``, then projects those intents onto real backend
source/channel/schedule capabilities.

Design constraints (kept identical to the legacy path):
- Never emit raw executor definitions or OpenCLI payloads; only assemble
  packaged OpenCLI Admin nodes from the existing catalog.
- For sites that map to ``channel=opencli``, emit native source/normalize/
  merge/accept/sink nodes (the legacy ``_native_first_loop_operations``
  behaviour).
- For sites that map to a real but blocked channel (``web_scraper`` /
  ``api`` / ``rss`` / ``cli`` / ``skill`` / ``crawl4ai``), still emit a
  placeholder ``intelligence.source.channel.<type>`` source node plus a
  ``request_missing_capability`` patch operation. The placeholder is visible
  in the canvas so the operator can resolve the resource gap, not invisible.
- When the parser finds a frequency hint, attach a Cron Schedule node to the
  patch so the request to "每小时" / "每 5 分钟" routes to a real schedule
  trigger.
"""

from __future__ import annotations

from typing import Any

from backend.schemas.workflow import (
    WorkflowAdapterBinding,
    WorkflowDemandDraftRequest,
    WorkflowPatchOperation,
    WorkflowPatchResponse,
    WorkflowProject,
    WorkflowProjectEdge,
    WorkflowProjectNode,
)
from backend.workflow.capability_projection import (
    CHANNEL_BLOCKED_REASONS,
    CHANNEL_DEFAULT_PARAMS,
    CHANNEL_LABELS,
    CHANNEL_REQUIRED_CONFIG,
)
from backend.workflow.intent_parser import (
    ParsedNeed,
    SourceIntent,
    parse_collection_need,
)
from backend.workflow.patcher import preview_workflow_patch


def draft_workflow_demand(body: WorkflowDemandDraftRequest) -> WorkflowPatchResponse:
    """Translate a user collection need into reviewable native-node patches."""

    parsed = parse_collection_need(body.text)
    if not parsed.has_recognised_source:
        return preview_workflow_patch(
            body.project,
            [
                WorkflowPatchOperation(
                    op="request_missing_capability",
                    capability="collection.source.intent_mapping",
                    reason=(
                        "No existing Canvas source capability matched this collection need. "
                        "Add a real source/channel mapping before assembling runnable nodes."
                    ),
                )
            ],
        )

    return _assemble_operations(body.project, parsed, body.text, body.locale)


# ── Operation assembly ──────────────────────────────────────────────────────


def _assemble_operations(
    project: WorkflowProject,
    parsed: ParsedNeed,
    demand_text: str,
    locale: str | None,
) -> WorkflowPatchResponse:
    operations: list[WorkflowPatchOperation] = []

    used_node_ids = {node.id for node in project.nodes}
    used_edge_ids = {edge.id for edge in project.edges}
    used_adapter_ids = {adapter.id for adapter in project.adapters}

    opencli_sources: list[SourceIntent] = []
    blocked_sources: list[SourceIntent] = []
    for intent in parsed.sources:
        if intent.channel == "opencli":
            opencli_sources.append(intent)
        else:
            blocked_sources.append(intent)

    normalize_ids: list[str] = []

    # Native opencli path — fan out through normalize → merge → accept → sink.
    for index, intent in enumerate(opencli_sources):
        source_slug = intent.site
        adapter_id = _unique_id(used_adapter_ids, f"opencli-{source_slug}")
        if adapter_id not in {adapter.id for adapter in project.adapters}:
            operations.append(
                WorkflowPatchOperation(
                    op="add_adapter",
                    adapter=WorkflowAdapterBinding(
                        id=adapter_id,
                        type="source",
                        provider="opencli",
                        mode="live",
                        config={"channel": "opencli"},
                    ),
                )
            )

        source_id = _unique_id(used_node_ids, f"source-{source_slug}")
        normalize_id = _unique_id(used_node_ids, f"normalize-{source_slug}")
        normalize_ids.append(normalize_id)
        args = _args_for_opencli_source(intent, parsed)
        operations.extend(
            [
                WorkflowPatchOperation(
                    op="add_node",
                    node=WorkflowProjectNode(
                        id=source_id,
                        kind="source",
                        capability="fetch",
                        adapter=adapter_id,
                        params={
                            "site": intent.site,
                            "command": _command_for_kind(intent.kind),
                            "sourceGroup": intent.source_group,
                            "args": args,
                            "demand": {
                                "text": demand_text,
                                "locale": locale,
                                "topic": parsed.topic,
                                "kind": intent.kind,
                                "source": "ai_plan_draft",
                            },
                        },
                        ui={
                            "catalogId": "intelligence.source.opencli-slot",
                            "label": intent.label,
                            "position": {"x": 180, "y": 180 + index * 120},
                        },
                    ),
                ),
                WorkflowPatchOperation(
                    op="add_node",
                    node=WorkflowProjectNode(
                        id=normalize_id,
                        kind="agent",
                        capability="normalize",
                        params={"language": locale or "zh-CN", "preserveSourceRefs": True},
                        ui={
                            "catalogId": "intelligence.processing.normalize",
                            "label": f"Normalize {intent.label}",
                            "position": {"x": 440, "y": 180 + index * 120},
                        },
                    ),
                ),
                WorkflowPatchOperation(
                    op="connect_nodes",
                    edge=WorkflowProjectEdge(
                        id=_unique_id(used_edge_ids, f"e-{source_id}-{normalize_id}"),
                        source=source_id,
                        target=normalize_id,
                        sourcePort="out",
                        targetPort="in",
                    ),
                ),
            ]
        )

    # Non-opencli site projection — emit a placeholder source node flagged with
    # the channel's existing blocked reason so the operator can fix the gap.
    for index, intent in enumerate(blocked_sources):
        source_slug = intent.site
        adapter_id = _unique_id(used_adapter_ids, f"channel-{intent.channel}-{source_slug}")
        if adapter_id not in {adapter.id for adapter in project.adapters}:
            operations.append(
                WorkflowPatchOperation(
                    op="add_adapter",
                    adapter=WorkflowAdapterBinding(
                        id=adapter_id,
                        type="source",
                        provider=intent.channel,
                        mode="live",
                        config={
                            "channel": intent.channel,
                            "site": intent.site,
                            **CHANNEL_DEFAULT_PARAMS.get(intent.channel, {}),
                        },
                    ),
                )
            )

        source_id = _unique_id(used_node_ids, f"source-{source_slug}")
        label = CHANNEL_LABELS.get(intent.channel, intent.channel.title())
        operations.append(
            WorkflowPatchOperation(
                op="add_node",
                node=WorkflowProjectNode(
                    id=source_id,
                    kind="source",
                    capability="fetch",
                    adapter=adapter_id,
                    params={
                        "channelType": intent.channel,
                        "site": intent.site,
                        "args": CHANNEL_DEFAULT_PARAMS.get(intent.channel, {}),
                        "demand": {
                            "text": demand_text,
                            "locale": locale,
                            "topic": parsed.topic,
                            "kind": intent.kind,
                            "source": "ai_plan_draft",
                            "blockedReason": CHANNEL_BLOCKED_REASONS.get(intent.channel),
                            "requiredConfig": CHANNEL_REQUIRED_CONFIG.get(intent.channel, []),
                        },
                    },
                    ui={
                        "catalogId": f"intelligence.source.channel.{intent.channel}",
                        "label": f"{label} ({intent.site})",
                        "position": {"x": 180, "y": 180 + (len(opencli_sources) + index) * 120},
                    },
                    proposalState="draft",
                ),
            )
        )
        operations.append(
            WorkflowPatchOperation(
                op="request_missing_capability",
                capability=f"channel.{intent.channel}.config",
                reason=CHANNEL_BLOCKED_REASONS.get(
                    intent.channel,
                    f"{label} channel config required before this source can run.",
                ),
            )
        )

    # Only build the native collect+accept tail when at least one opencli
    # source is present. Blocked-only need still keeps its placeholder so the
    # canvas is reviewable but not silently miscompiled.
    if opencli_sources:
        merge_id = _unique_id(used_node_ids, "merge-candidates")
        accept_id = _unique_id(used_node_ids, "accept-records")
        sink_id = _unique_id(used_node_ids, "record-sink")
        operations.extend(
            [
                WorkflowPatchOperation(
                    op="add_node",
                    node=WorkflowProjectNode(
                        id=merge_id,
                        kind="flow",
                        capability="merge",
                        params={
                            "strategy": "concat",
                            "preserveLineage": True,
                            "inputType": "recordCandidate[]",
                            "outputType": "recordCandidate[]",
                        },
                        ui={
                            "catalogId": "intelligence.flow.merge",
                            "label": "Merge Candidates",
                            "position": {"x": 700, "y": 240},
                        },
                    ),
                ),
                WorkflowPatchOperation(
                    op="add_node",
                    node=WorkflowProjectNode(
                        id=accept_id,
                        kind="control",
                        capability="accept",
                        params={
                            "mode": "automatic_with_review",
                            "schema": "record.v1",
                            "dedupe": "required",
                            "lineageRequired": True,
                            "minQuality": 0,
                        },
                        ui={
                            "catalogId": "intelligence.control.record-acceptance",
                            "label": "Record Acceptance",
                            "position": {"x": 960, "y": 240},
                        },
                    ),
                ),
                WorkflowPatchOperation(
                    op="add_node",
                    node=WorkflowProjectNode(
                        id=sink_id,
                        kind="sink",
                        capability="store",
                        params={
                            "target": "records",
                            "writeMode": "append",
                            "preserveLineage": True,
                        },
                        ui={
                            "catalogId": "intelligence.sink.records",
                            "label": "Records",
                            "position": {"x": 1220, "y": 240},
                        },
                    ),
                ),
            ]
        )
        for index, normalize_id in enumerate(normalize_ids, start=1):
            operations.append(
                WorkflowPatchOperation(
                    op="connect_nodes",
                    edge=WorkflowProjectEdge(
                        id=_unique_id(used_edge_ids, f"e-{normalize_id}-{merge_id}"),
                        source=normalize_id,
                        target=merge_id,
                        sourcePort="out",
                        targetPort=f"in{index}",
                    ),
                )
            )
        operations.extend(
            [
                WorkflowPatchOperation(
                    op="connect_nodes",
                    edge=WorkflowProjectEdge(
                        id=_unique_id(used_edge_ids, f"e-{merge_id}-{accept_id}"),
                        source=merge_id,
                        target=accept_id,
                        sourcePort="out",
                        targetPort="candidates",
                    ),
                ),
                WorkflowPatchOperation(
                    op="connect_nodes",
                    edge=WorkflowProjectEdge(
                        id=_unique_id(used_edge_ids, f"e-{accept_id}-{sink_id}"),
                        source=accept_id,
                        target=sink_id,
                        sourcePort="records",
                        targetPort="records",
                    ),
                ),
            ]
        )

    # Frequency hint → attach a Cron Schedule node at the head of the graph so
    # the operator can see the request expressed as a real schedule trigger.
    if parsed.frequency and parsed.frequency_hint:
        schedule_id = _unique_id(used_node_ids, "schedule-cron")
        # Wire the schedule to the first source node we just created
        # (opencli or blocked) — schedule is always at the front door.
        first_source_id = (
            f"source-{opencli_sources[0].site}"
            if opencli_sources
            else f"source-{blocked_sources[0].site}"
            if blocked_sources
            else None
        )
        operations.append(
            WorkflowPatchOperation(
                op="add_node",
                node=WorkflowProjectNode(
                    id=schedule_id,
                    kind="schedule",
                    capability="trigger",
                    params={
                        "frequency": parsed.frequency,
                        **parsed.frequency_hint,
                    },
                    ui={
                        "catalogId": "intelligence.schedule.cron",
                        "label": f"Cron {parsed.frequency}",
                        "position": {"x": -40, "y": 220},
                    },
                )
            )
        )
        if first_source_id:
            operations.append(
                WorkflowPatchOperation(
                    op="connect_nodes",
                    edge=WorkflowProjectEdge(
                        id=_unique_id(used_edge_ids, f"e-{schedule_id}-{first_source_id}"),
                        source=schedule_id,
                        target=first_source_id,
                        sourcePort="out",
                        targetPort="in",
                    ),
                )
            )

    return preview_workflow_patch(project, operations)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _args_for_opencli_source(intent: SourceIntent, parsed: ParsedNeed) -> dict[str, Any]:
    args: dict[str, Any] = {"keyword": parsed.topic, "topic": parsed.topic}
    if parsed.kind:
        args["kind"] = parsed.kind
    return args


def _command_for_kind(kind: str | None) -> str:
    if kind in {"hot-search", "news", "finance", "tech"}:
        return "search"
    if kind in {"tweet", "article"}:
        return "list"
    return "search"


def _unique_id(used: set[str], base: str) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
