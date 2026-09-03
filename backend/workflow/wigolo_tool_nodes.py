"""Wigolo capabilities exposed through the existing Canvas node catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.schemas.workflow import (
    WorkflowCapabilityVersionPin,
    WorkflowToolCapability,
    WorkflowToolCapabilityExecutor,
    WorkflowToolCapabilityPort,
)

WIGOLO_EXECUTOR_MODE = "wigolo_embedded"
WIGOLO_PACKAGE_VERSION = "0.2.1"
WIGOLO_UPSTREAM_COMMIT = "b3ccf92be3ac15ce3ad5a439be11777d992996a3"
WIGOLO_RUNTIME_MISSING = "wigolo_embedded_runtime_binding"


@dataclass(frozen=True)
class WigoloCapabilitySpec:
    name: str
    label: str
    description: str
    icon: str
    input_type: str
    output_type: str
    category: str
    kind: str
    capability: str
    parameters: tuple[dict[str, Any], ...]

    @property
    def tool_id(self) -> str:
        return f"tool.wigolo.{self.name.replace('_', '-')}"


WIGOLO_CAPABILITY_SPECS = (
    WigoloCapabilitySpec(
        "fetch",
        "Wigolo Fetch",
        "Fetch one URL with local caching and optional browser rendering.",
        "Globe2",
        "url",
        "page",
        "source",
        "source",
        "fetch",
        ({"name": "url", "label": "URL", "type": "string", "required": True},),
    ),
    WigoloCapabilitySpec(
        "search",
        "Wigolo Search",
        "Search the web with cached evidence, citations, and explainable ranking.",
        "Search",
        "query",
        "searchResult[]",
        "source",
        "source",
        "fetch",
        ({"name": "query", "label": "查询 / Query", "type": "string", "required": True},),
    ),
    WigoloCapabilitySpec(
        "crawl",
        "Wigolo Crawl",
        "Crawl a site from one seed URL and persist the discovered pages locally.",
        "Network",
        "url",
        "page[]",
        "source",
        "source",
        "fetch",
        ({"name": "url", "label": "起始 URL / Seed URL", "type": "string", "required": True},),
    ),
    WigoloCapabilitySpec(
        "cache",
        "Wigolo Cache",
        "Search and manage content already stored in Wigolo's local cache.",
        "Database",
        "query",
        "cachedPage[]",
        "processing",
        "action",
        "store",
        ({"name": "query", "label": "查询 / Query", "type": "string", "required": False},),
    ),
    WigoloCapabilitySpec(
        "extract",
        "Wigolo Extract",
        "Extract structured data from a URL or raw HTML.",
        "ScanText",
        "page",
        "structuredData",
        "processing",
        "action",
        "normalize",
        ({"name": "url", "label": "URL", "type": "string", "required": False},),
    ),
    WigoloCapabilitySpec(
        "find_similar",
        "Wigolo Find Similar",
        "Find related pages from a URL or concept using local and web signals.",
        "Sparkles",
        "page",
        "searchResult[]",
        "source",
        "source",
        "fetch",
        (
            {"name": "url", "label": "URL", "type": "string", "required": False},
            {"name": "concept", "label": "概念 / Concept", "type": "string", "required": False},
        ),
    ),
    WigoloCapabilitySpec(
        "research",
        "Wigolo Research",
        "Research a complex question and return a cited report or structured brief.",
        "BookOpen",
        "question",
        "researchReport",
        "processing",
        "agent",
        "summarize",
        ({"name": "question", "label": "研究问题 / Question", "type": "string", "required": True},),
    ),
    WigoloCapabilitySpec(
        "agent",
        "Wigolo Agent",
        "Plan and execute multi-source data gathering from a natural-language prompt.",
        "Bot",
        "prompt",
        "researchResult",
        "processing",
        "agent",
        "summarize",
        ({"name": "prompt", "label": "任务 / Prompt", "type": "string", "required": True},),
    ),
    WigoloCapabilitySpec(
        "diff",
        "Wigolo Diff",
        "Compare two pages or markdown values and return a structured diff.",
        "GitCompare",
        "documentPair",
        "diff",
        "processing",
        "action",
        "normalize",
        (
            {"name": "old", "label": "旧内容 / Old", "type": "object", "required": True},
            {"name": "new", "label": "新内容 / New", "type": "object", "required": True},
        ),
    ),
    WigoloCapabilitySpec(
        "watch",
        "Wigolo Watch",
        "Create and manage lazy URL change watches backed by Wigolo's local cache.",
        "Bell",
        "watchCommand",
        "watchResult",
        "processing",
        "action",
        "store",
        (
            {
                "name": "action",
                "label": "操作 / Action",
                "type": "select",
                "required": True,
                "default": "list",
                "options": ["create", "list", "check", "pause", "resume", "delete"],
            },
            {"name": "url", "label": "URL", "type": "string", "required": False},
        ),
    ),
)

WIGOLO_TOOL_IDS = frozenset(spec.tool_id for spec in WIGOLO_CAPABILITY_SPECS)


def wigolo_tool_capabilities() -> list[WorkflowToolCapability]:
    version_pin = WorkflowCapabilityVersionPin(
        package="@repo/wigolo",
        packageVersion=WIGOLO_PACKAGE_VERSION,
        capabilityVersion=WIGOLO_PACKAGE_VERSION,
        provenance="verified",
    )
    return [
        WorkflowToolCapability(
            id=spec.tool_id,
            label=spec.label,
            description=spec.description,
            status="blocked",
            provider="wigolo",
            inputPorts=[WorkflowToolCapabilityPort(name="in", type=spec.input_type)],
            outputPorts=[WorkflowToolCapabilityPort(name="out", type=spec.output_type)],
            executor=WorkflowToolCapabilityExecutor(
                mode=WIGOLO_EXECUTOR_MODE,
                description="Calls the embedded @repo/wigolo capability in the host process.",
                params={"tool": spec.name},
            ),
            versionPin=version_pin,
            tags=["tool", "wigolo", "web-intelligence", spec.name],
            manifest={
                "schema": f"tool-capability.wigolo-{spec.name.replace('_', '-')}.v1",
                "runtime": {"binding": "workflow.external-tool.capability"},
                "resources": ["wigolo_embedded_runtime", "wigolo_data_dir", "run_trace"],
                "permissions": ["runtime_tool_call", "canFetchNetwork"],
                "upstream": {
                    "repository": "https://github.com/2233admin/wigolo",
                    "version": WIGOLO_PACKAGE_VERSION,
                    "commit": WIGOLO_UPSTREAM_COMMIT,
                },
                "readiness": {
                    "status": "blocked",
                    "missingReasons": [WIGOLO_RUNTIME_MISSING],
                },
                "canvas": {"node": True},
                "nodeCatalog": {
                    "id": spec.tool_id,
                    "authority": "backend",
                    "origin": "tool-capability",
                    "category": spec.category,
                    "kind": spec.kind,
                    "capability": spec.capability,
                },
                "presentation": {
                    "icon": spec.icon,
                    "parameters": list(spec.parameters),
                },
            },
        )
        for spec in WIGOLO_CAPABILITY_SPECS
    ]
