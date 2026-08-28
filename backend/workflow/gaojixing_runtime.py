"""Gaojixing live Doubao source contract for WorkflowProject runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from backend.channels.base import ChannelResult
from backend.channels.doubao_research_channel import DoubaoResearchChannel

GAOJIXING_CAPABILITY_ID = "chat-ai.capture"
GAOJIXING_CHANNEL_TYPE = "doubao_research"
GAOJIXING_LIVE_MODE = "live"
GAOJIXING_FIXTURE_MODE = "fixture"
GAOJIXING_MOCK_MODE = "mock"
GAOJIXING_EXECUTION_MODES = frozenset(
    {GAOJIXING_LIVE_MODE, GAOJIXING_FIXTURE_MODE, GAOJIXING_MOCK_MODE}
)
GAOJIXING_PACKAGE_SCHEMA = "gaojixing.question-package.v1"
GAOJIXING_EVIDENCE_SCHEMA = "gaojixing.capture-evidence.v1"


class GaojixingReadinessError(RuntimeError):
    """Typed fail-closed blocker for a live Gaojixing source."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class GaojixingQuestionPackage:
    schema: str
    question: str
    options: Mapping[str, Any]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "question": self.question,
            "options": _thaw_json(self.options),
            "digest": self.digest,
        }


def build_question_package(
    *,
    node_params: dict[str, Any],
    adapter_config: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> GaojixingQuestionPackage:
    """Resolve the effective question once and hash its canonical snapshot."""

    question = (
        _string(runtime_payload.get("question"))
        or _string(runtime_payload.get("query"))
        or _string(node_params.get("question"))
    )
    if question is None:
        question = _string(adapter_config.get("question"))
    if question is None:
        raise GaojixingReadinessError(
            "gaojixing_question_required",
            (
                "A live Gaojixing run requires an effective question in run input, "
                "node params, or adapter config."
            ),
            details={"required": "question"},
        )

    option_keys = (
        "extract_citations",
        "capture_conversation_url",
        "site_session",
        "settle_seconds",
        "capabilityId",
        "sourceGroup",
    )
    options = {
        key: value
        for key in option_keys
        for value in [
            _json_safe(runtime_payload.get(key, node_params.get(key, adapter_config.get(key))))
        ]
        if value is not None
    }
    canonical = {"schema": GAOJIXING_PACKAGE_SCHEMA, "question": question, "options": options}
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return GaojixingQuestionPackage(
        schema=GAOJIXING_PACKAGE_SCHEMA,
        question=question,
        options=_freeze_json(options),
        digest=hashlib.sha256(encoded).hexdigest(),
    )


async def capture_live_doubao(
    *,
    package: GaojixingQuestionPackage,
    node_params: dict[str, Any],
    adapter_config: dict[str, Any],
    network_allowed: bool,
) -> ChannelResult:
    """Preflight and execute the existing Doubao channel; never use fixtures."""

    capability_id = (
        _string(node_params.get("capabilityId"))
        or _string(adapter_config.get("capabilityId"))
        or GAOJIXING_CAPABILITY_ID
    )
    if capability_id not in {GAOJIXING_CAPABILITY_ID, "doubao.ask"}:
        raise GaojixingReadinessError(
            "gaojixing_capability_missing",
            f'Live Gaojixing capability "{capability_id}" is not registered.',
            details={"capabilityId": capability_id},
        )
    if (
        node_params.get("capabilityAvailable") is False
        or adapter_config.get("capabilityAvailable") is False
    ):
        raise GaojixingReadinessError(
            "gaojixing_capability_missing",
            "The live Gaojixing chat-ai.capture/Doubao capability is unavailable.",
            details={"capabilityId": capability_id},
        )
    _raise_configured_readiness_blocker(adapter_config)
    if not network_allowed:
        raise GaojixingReadinessError(
            "gaojixing_network_denied",
            "Live Gaojixing capture requires workflow network permission.",
            details={"requiredPermission": "canFetchNetwork"},
        )

    channel = DoubaoResearchChannel()
    healthy = await channel.health_check(adapter_config)
    if not healthy:
        readiness_code = await channel.readiness_code(adapter_config)
        raise GaojixingReadinessError(
            f"gaojixing_{readiness_code or 'session_unavailable'}",
            _readiness_message(readiness_code),
            details={"site": "doubao", "session": adapter_config.get("site_session", "persistent")},
        )

    config = {
        **adapter_config,
        "question": package.question,
        "site_session": adapter_config.get("site_session", "persistent"),
        "extract_citations": adapter_config.get("extract_citations", True),
        "capture_conversation_url": adapter_config.get("capture_conversation_url", True),
    }
    return await channel.collect(config, {"question": package.question})


def map_capture_item(
    item: dict[str, Any],
    *,
    package: GaojixingQuestionPackage,
    workflow_id: str,
    run_id: str,
    node_id: str,
    artifact_id: str,
    mode: str = GAOJIXING_LIVE_MODE,
    provenance: str | None = None,
) -> dict[str, Any]:
    """Attach separate answer/citation/conversation evidence to one raw item."""
    if mode not in GAOJIXING_EXECUTION_MODES:
        raise ValueError(f"Unsupported Gaojixing execution mode: {mode}")
    provenance = provenance or (
        "opencli:doubao" if mode == GAOJIXING_LIVE_MODE else f"{mode}:unspecified"
    )

    answer = _string(item.get("content"))
    citations = item.get("citations") if isinstance(item.get("citations"), list) else []
    conversation_url = _string(item.get("conversation_url"))
    evidence = {
        "schema": GAOJIXING_EVIDENCE_SCHEMA,
        "mode": mode,
        "provenance": provenance,
        "packageDigest": package.digest,
        "runId": run_id,
        "workflowId": workflow_id,
        "nodeId": node_id,
        "answer": {
            "status": "captured" if answer else "unavailable",
            "artifactId": artifact_id,
            "text": answer,
        },
        "citations": {
            "status": "captured" if citations else "empty",
            "capture": item.get("citation_capture", "answer_url_extraction"),
            "verified": False,
            "items": citations,
        },
        "conversation": {
            "status": "captured" if conversation_url else "unknown",
            "url": conversation_url,
        },
    }
    mapped = {
        **item,
        "gaojixing": {
            "mode": mode,
            "provenance": provenance,
            "capabilityId": GAOJIXING_CAPABILITY_ID,
            "package": package.to_dict(),
            "artifactId": artifact_id,
            "evidence": evidence,
        },
        "packageDigest": package.digest,
        "questionPackage": package.to_dict(),
        "mode": mode,
        "provenance": provenance,
        "answerArtifactId": artifact_id,
    }
    if conversation_url:
        mapped["dedupe"] = {
            "type": "source-identity",
            "field": "conversation_url",
            "value": conversation_url,
            "status": "unique",
        }
    return mapped


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return str(value)


def _raise_configured_readiness_blocker(adapter_config: dict[str, Any]) -> None:
    if adapter_config.get("adapterAvailable") is False:
        raise GaojixingReadinessError(
            "gaojixing_adapter_missing",
            "The Doubao OpenCLI adapter is unavailable.",
            details={"requiredAdapter": "opencli:doubao"},
        )
    if (
        adapter_config.get("authenticated") is False
        or adapter_config.get("authenticationAvailable") is False
    ):
        raise GaojixingReadinessError(
            "gaojixing_authentication_required",
            "The configured Doubao session is not authenticated.",
            details={"site": "doubao"},
        )
    if adapter_config.get("sessionAvailable") is False:
        raise GaojixingReadinessError(
            "gaojixing_session_unavailable",
            "The configured Doubao OpenCLI session is unavailable.",
            details={"site": "doubao", "session": adapter_config.get("site_session", "persistent")},
        )


def _readiness_message(code: str | None) -> str:
    messages = {
        "adapter_missing": "The Doubao OpenCLI adapter is unavailable.",
        "authentication_required": "The configured Doubao session is not authenticated.",
        "captcha_challenge": "The Doubao session is blocked by a CAPTCHA challenge.",
    }
    return messages.get(
        code or "",
        "The Doubao OpenCLI session is unavailable or not logged in.",
    )


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return deepcopy(value)


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return deepcopy(value)


__all__ = [
    "GAOJIXING_CAPABILITY_ID",
    "GAOJIXING_CHANNEL_TYPE",
    "GAOJIXING_EVIDENCE_SCHEMA",
    "GAOJIXING_LIVE_MODE",
    "GAOJIXING_EXECUTION_MODES",
    "GAOJIXING_FIXTURE_MODE",
    "GaojixingQuestionPackage",
    "GaojixingReadinessError",
    "build_question_package",
    "capture_live_doubao",
    "GAOJIXING_MOCK_MODE",
    "map_capture_item",
]
