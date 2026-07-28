"""Deterministic, evidence-linked operators for bounded research workflows."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from typing import Any

RESEARCH_PACK_ID = "builtin.research"
RESEARCH_PACK_VERSION = "1.0.0"

_Executor = Callable[
    [list[dict[str, Any]], dict[str, Any]],
    tuple[list[dict[str, Any]], dict[str, Any], list[str]],
]

RESEARCH_OPERATOR_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "operatorId": "research.claim-project",
        "kind": "refine",
        "packId": RESEARCH_PACK_ID,
        "packVersion": RESEARCH_PACK_VERSION,
        "label": "Research claim projection",
        "description": "Project source candidates into stable evidence-linked claims.",
        "configKeys": [
            "claimKeyField",
            "statementField",
            "evidenceIdField",
            "stanceField",
            "dimensionField",
        ],
    },
    {
        "operatorId": "research.coverage-audit",
        "kind": "evaluate",
        "packId": RESEARCH_PACK_ID,
        "packVersion": RESEARCH_PACK_VERSION,
        "label": "Research coverage audit",
        "description": "Audit required dimensions and emit a bounded continuation decision.",
        "configKeys": [
            "requiredDimensions",
            "iteration",
            "maxIterations",
            "additionalCollectionCount",
            "maxAdditionalCollections",
        ],
    },
    {
        "operatorId": "research.counter-thesis",
        "kind": "generate",
        "packId": RESEARCH_PACK_ID,
        "packVersion": RESEARCH_PACK_VERSION,
        "label": "Research counter thesis",
        "description": "Materialize traceable counter-evidence without dropping claims.",
        "configKeys": [],
    },
    {
        "operatorId": "research.scenario-simulate",
        "kind": "generate",
        "packId": RESEARCH_PACK_ID,
        "packVersion": RESEARCH_PACK_VERSION,
        "label": "Research scenario simulation",
        "description": "Score bounded scenarios against evidence-linked claim dimensions.",
        "configKeys": ["scenarios"],
    },
    {
        "operatorId": "research.revision-diff",
        "kind": "evaluate",
        "packId": RESEARCH_PACK_ID,
        "packVersion": RESEARCH_PACK_VERSION,
        "label": "Research revision diff",
        "description": "Compare current claims with a prior revision deterministically.",
        "configKeys": ["previousClaims", "previousScenarios"],
    },
    {
        "operatorId": "research.publish-gate",
        "kind": "filter",
        "packId": RESEARCH_PACK_ID,
        "packVersion": RESEARCH_PACK_VERSION,
        "label": "Research publish gate",
        "description": "Release only complete, evidence-linked research revisions.",
        "configKeys": [],
    },
)


def _claim_project(items: list[dict[str, Any]], config: dict[str, Any]):
    claim_key_field = _field_name(config, "claimKeyField", "claimKey")
    statement_field = _field_name(config, "statementField", "statement")
    evidence_id_field = _field_name(config, "evidenceIdField", "evidenceId")
    stance_field = _field_name(config, "stanceField", "stance")
    dimension_field = _field_name(config, "dimensionField", "dimension")
    groups: dict[str, list[tuple[int, dict[str, Any], str]]] = {}
    rejected: list[str] = []
    for index, item in enumerate(items):
        statement = _text(item, statement_field) or _text(item, "content") or _text(item, "title")
        if not statement:
            _reject(rejected, item)
            continue
        key = _text(item, claim_key_field) or statement.casefold()
        groups.setdefault(key, []).append((index, item, statement))

    output: list[dict[str, Any]] = []
    unverified = 0
    for key in sorted(groups):
        rows = groups[key]
        statements = sorted({_clean_text(row[2]) for row in rows})
        statement = statements[0]
        supporting: set[str] = set()
        contradicting: set[str] = set()
        qualifying: set[str] = set()
        dimensions: set[str] = set()
        evidence_refs: dict[str, dict[str, Any]] = {}
        for index, item, _ in rows:
            evidence_id = _text(item, evidence_id_field) or _evidence_id(item, index)
            stance = (_text(item, stance_field) or "support").casefold()
            if evidence_id:
                reference = _evidence_ref(item, evidence_id)
                evidence_refs[_canonical(reference)] = reference
                if stance in {"contradict", "contradicting", "oppose", "opposing"}:
                    contradicting.add(evidence_id)
                elif stance in {"qualify", "qualifying", "caveat"}:
                    qualifying.add(evidence_id)
                else:
                    supporting.add(evidence_id)
            dimensions.update(_dimensions(_value(item, dimension_field)))
        evidence_ids = supporting | contradicting | qualifying
        disposition = _disposition(supporting, contradicting, qualifying)
        unverified += not evidence_ids
        claim_id = f"claim-{_digest({'key': key, 'statement': statement})[:20]}"
        claim = {
            "claimId": claim_id,
            "statement": statement,
            "disposition": disposition,
            "verificationStatus": "verified" if evidence_ids else "unverified",
            "supportingEvidenceIds": sorted(supporting),
            "contradictingEvidenceIds": sorted(contradicting),
            "qualifyingEvidenceIds": sorted(qualifying),
            "evidenceIds": sorted(evidence_ids),
            "dimensions": sorted(dimensions),
            "evidenceRefs": sorted(evidence_refs.values(), key=_canonical),
        }
        representative = min(rows, key=lambda row: (_candidate_id(row[1]), row[0]))[1]
        normalized = _normalized(representative)
        normalized.update({"researchType": "claim", "claim": claim})
        output.append(_with_normalized(representative, normalized, candidate_id=claim_id))
    return (
        output,
        {
            "claimCount": len(output),
            "unverifiedClaimCount": unverified,
            "rejectedInputCount": len(items) - sum(len(rows) for rows in groups.values()),
        },
        rejected,
    )


def _coverage_audit(items: list[dict[str, Any]], config: dict[str, Any]):
    claims = [claim for item in items if (claim := _claim(item))]
    claim_set_hash = _claim_set_hash(claims)
    semantic_claim_set_hash = _semantic_claim_set_hash(claims)
    required = _string_list(config.get("requiredDimensions", []), "requiredDimensions")
    iteration = _bounded_int(config, "iteration", 1, minimum=1, maximum=5)
    max_iterations = _bounded_int(config, "maxIterations", 2, minimum=1, maximum=5)
    additional = _bounded_int(config, "additionalCollectionCount", 0, minimum=0, maximum=3)
    max_additional = _bounded_int(config, "maxAdditionalCollections", 1, minimum=0, maximum=3)
    if iteration > max_iterations:
        raise ValueError("iteration must not exceed maxIterations")
    if additional > max_additional:
        raise ValueError("additionalCollectionCount must not exceed maxAdditionalCollections")
    covered = sorted(
        {dimension for item in items for dimension in _verified_claim_dimensions(item)}
    )
    gaps = sorted(set(required) - set(covered))
    if not gaps:
        decision, stop_reason = "finalize", "coverage_satisfied"
    elif iteration >= max_iterations:
        decision, stop_reason = "stop_incomplete", "max_iterations_reached"
    elif additional >= max_additional:
        decision, stop_reason = "stop_incomplete", "max_additional_collections_reached"
    else:
        decision, stop_reason = "collect_more", None
    continuation_proposal = (
        {
            "proposalId": (
                "collect-more-"
                + _digest(
                    {
                        "claimSetHash": claim_set_hash,
                        "gaps": gaps,
                        "iteration": iteration,
                        "additionalCollectionCount": additional,
                    }
                )[:20]
            ),
            "action": "collect_more",
            "gaps": gaps,
            "nextIteration": iteration + 1,
            "nextAdditionalCollectionCount": additional + 1,
        }
        if decision == "collect_more"
        else None
    )
    report = {
        "claimSetHash": claim_set_hash,
        "semanticClaimSetHash": semantic_claim_set_hash,
        "requiredDimensions": sorted(set(required)),
        "coveredDimensions": covered,
        "gaps": gaps,
        "satisfied": not gaps,
        "decision": decision,
        "stopReason": stop_reason,
        "iteration": iteration,
        "maxIterations": max_iterations,
        "additionalCollectionCount": additional,
        "maxAdditionalCollections": max_additional,
        "continuationProposal": continuation_proposal,
    }
    if items:
        output = []
        for item in items:
            normalized = _normalized(item)
            normalized["coverageReport"] = copy.deepcopy(report)
            output.append(_with_normalized(item, normalized))
    else:
        output = []
    return (
        output,
        {
            "coverageSatisfied": report["satisfied"],
            "coveredDimensionCount": len(covered),
            "gapCount": len(gaps),
            "decision": decision,
            "stopReason": stop_reason,
            "coverageReport": copy.deepcopy(report),
        },
        [],
    )


def _counter_thesis(items: list[dict[str, Any]], _config: dict[str, Any]):
    output = copy.deepcopy(items)
    generated: list[dict[str, Any]] = []
    for item in items:
        claim = _claim(item)
        if not claim:
            continue
        contradicting = _strings(claim.get("contradictingEvidenceIds"))
        qualifying = _strings(claim.get("qualifyingEvidenceIds"))
        evidence_ids = sorted(set(contradicting + qualifying))
        if not evidence_ids:
            continue
        claim_id = str(claim["claimId"])
        counter_id = f"counter-{_digest({'claimId': claim_id, 'evidenceIds': evidence_ids})[:20]}"
        statement = (
            f"Evidence contradicts or qualifies claim: {claim.get('statement', '')}"
        ).strip()
        counter = {
            "counterThesisId": counter_id,
            "targetClaimIds": [claim_id],
            "statement": statement,
            "contradictingEvidenceIds": contradicting,
            "qualifyingEvidenceIds": qualifying,
            "evidenceIds": evidence_ids,
        }
        normalized = {"researchType": "counterThesis", "counterThesis": counter}
        generated.append(
            _with_normalized(item, normalized, candidate_id=counter["counterThesisId"])
        )
    output.extend(sorted(generated, key=lambda item: str(item.get("candidateId", ""))))
    return output, {"counterThesisCount": len(generated)}, []


def _scenario_simulate(items: list[dict[str, Any]], config: dict[str, Any]):
    scenarios = config.get("scenarios")
    if not items and scenarios is None:
        return (
            [],
            {
                "scenarioCount": 0,
                "scenarioSetHash": _scenario_set_hash([]),
                "uncoveredDriverCount": 0,
            },
            [],
        )
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 8:
        raise ValueError("scenarios must contain between 1 and 8 objects")
    claims = [claim for item in items if (claim := _claim(item))]
    output = copy.deepcopy(items)
    generated: list[dict[str, Any]] = []
    for raw in scenarios:
        if not isinstance(raw, dict):
            raise ValueError("scenarios entries must be objects")
        scenario_id = raw.get("scenarioId")
        label = raw.get("label")
        prior = raw.get("priorScore", 0.5)
        drivers = raw.get("drivers", [])
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError("scenarioId must be a non-empty string")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("scenario label must be a non-empty string")
        if not isinstance(prior, int | float) or isinstance(prior, bool) or not 0 <= prior <= 1:
            raise ValueError("priorScore must be a number between 0 and 1")
        if not isinstance(drivers, list) or not 1 <= len(drivers) <= 12:
            raise ValueError("scenario drivers must contain between 1 and 12 objects")

        contributions: list[dict[str, Any]] = []
        evidence_ids: set[str] = set()
        evidence_refs: dict[str, dict[str, Any]] = {}
        uncovered: list[str] = []
        score = float(prior)
        for driver in drivers:
            if not isinstance(driver, dict):
                raise ValueError("scenario drivers must be objects")
            dimension = driver.get("dimension")
            weight = driver.get("weight")
            if not isinstance(dimension, str) or not dimension.strip():
                raise ValueError("scenario driver dimension must be a non-empty string")
            if (
                not isinstance(weight, int | float)
                or isinstance(weight, bool)
                or not -1 <= weight <= 1
            ):
                raise ValueError("scenario driver weight must be between -1 and 1")
            dimension = _clean_text(dimension)
            matched = [
                claim for claim in claims if dimension in _strings(claim.get("dimensions"))
            ]
            if not matched:
                uncovered.append(dimension)
                observed = 0.0
            else:
                observed = sum(_disposition_score(claim) for claim in matched) / len(matched)
                for claim in matched:
                    evidence_ids.update(_strings(claim.get("evidenceIds")))
                    for reference in claim.get("evidenceRefs", []):
                        if isinstance(reference, dict):
                            evidence_refs[_canonical(reference)] = copy.deepcopy(reference)
            contribution = float(weight) * observed
            score += contribution
            contributions.append(
                {
                    "dimension": dimension,
                    "weight": float(weight),
                    "observed": observed,
                    "contribution": contribution,
                }
            )

        scenario = {
            "scenarioId": scenario_id.strip(),
            "label": label.strip(),
            "priorScore": float(prior),
            "score": min(1.0, max(0.0, score)),
            "drivers": contributions,
            "uncoveredDrivers": sorted(set(uncovered)),
            "assumptions": _string_list(raw.get("assumptions", []), "assumptions"),
            "invalidationSignals": _string_list(
                raw.get("invalidationSignals", []), "invalidationSignals"
            ),
            "evidenceIds": sorted(evidence_ids),
            "evidenceRefs": sorted(evidence_refs.values(), key=_canonical),
        }
        generated.append(
            _with_normalized(
                items[0] if items else {},
                {"researchType": "scenario", "researchScenario": scenario},
                candidate_id=f"scenario-{_digest(scenario)[:20]}",
            )
        )
    output.extend(generated)
    scenario_set_hash = _scenario_set_hash(
        [item["normalizedData"]["researchScenario"] for item in generated]
    )
    return (
        output,
        {
            "scenarioCount": len(generated),
            "scenarioSetHash": scenario_set_hash,
            "uncoveredDriverCount": sum(
                len(item["normalizedData"]["researchScenario"]["uncoveredDrivers"])
                for item in generated
            ),
        },
        [],
    )


def _revision_diff(items: list[dict[str, Any]], config: dict[str, Any]):
    previous_raw = config.get("previousClaims", [])
    if not isinstance(previous_raw, list) or any(
        not isinstance(item, dict) for item in previous_raw
    ):
        raise ValueError("previousClaims must be a list of objects")
    previous_scenarios_raw = config.get("previousScenarios", [])
    if not isinstance(previous_scenarios_raw, list) or any(
        not isinstance(item, dict) for item in previous_scenarios_raw
    ):
        raise ValueError("previousScenarios must be a list of objects")
    current = {claim["claimId"]: claim for item in items if (claim := _claim(item))}
    current_scenarios = {
        scenario["scenarioId"]: scenario
        for item in items
        if (scenario := _scenario(item))
    }
    previous: dict[str, dict[str, Any]] = {}
    for item in previous_raw:
        claim = _claim(item) or item
        claim_id = claim.get("claimId")
        if not isinstance(claim_id, str) or not claim_id:
            raise ValueError("previousClaims entries require claimId")
        previous[claim_id] = copy.deepcopy(claim)
    previous_scenarios: dict[str, dict[str, Any]] = {}
    for scenario in previous_scenarios_raw:
        scenario_id = scenario.get("scenarioId")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("previousScenarios entries require scenarioId")
        previous_scenarios[scenario_id] = copy.deepcopy(scenario)
    added = [copy.deepcopy(current[key]) for key in sorted(set(current) - set(previous))]
    removed = [copy.deepcopy(previous[key]) for key in sorted(set(previous) - set(current))]
    changed = [
        {
            "claimId": key,
            "before": copy.deepcopy(previous[key]),
            "after": copy.deepcopy(current[key]),
        }
        for key in sorted(set(current) & set(previous))
        if _canonical(previous[key]) != _canonical(current[key])
    ]
    revision = {
        "claimSetHash": _claim_set_hash(list(current.values())),
        "scenarioSetHash": _scenario_set_hash(list(current_scenarios.values())),
        "added": added,
        "changed": changed,
        "removed": removed,
        "currentClaims": [copy.deepcopy(current[key]) for key in sorted(current)],
        "currentScenarios": [
            copy.deepcopy(current_scenarios[key]) for key in sorted(current_scenarios)
        ],
        "changedScenarioIds": sorted(
            key
            for key in set(current_scenarios) | set(previous_scenarios)
            if _canonical(current_scenarios.get(key)) != _canonical(previous_scenarios.get(key))
        ),
        "evidenceIds": sorted(
            {
                evidence
                for claim in current.values()
                for evidence in _strings(claim.get("evidenceIds"))
            }
        ),
    }
    if not items and not previous and not previous_scenarios:
        return (
            [],
            {
                "addedClaimCount": 0,
                "changedClaimCount": 0,
                "removedClaimCount": 0,
            },
            [],
        )
    candidate_id = f"revision-{_digest(revision)[:20]}"
    output = copy.deepcopy(items)
    output.append(
        {
            "candidateId": candidate_id,
            "contentHash": _digest(revision),
            "normalizedData": {"researchType": "revision", "researchRevision": revision},
            "lineage": copy.deepcopy(items[0].get("lineage", [])) if items else [],
        }
    )
    return (
        output,
        {
            "revisionId": candidate_id,
            "claimSetHash": revision["claimSetHash"],
            "scenarioSetHash": revision["scenarioSetHash"],
            "addedClaimCount": len(added),
            "changedClaimCount": len(changed),
            "removedClaimCount": len(removed),
            "changedScenarioCount": len(revision["changedScenarioIds"]),
            "researchRevision": copy.deepcopy(revision),
        },
        [],
    )


def _publish_gate(items: list[dict[str, Any]], _config: dict[str, Any]):
    normalized_items = [_normalized(item) for item in items]
    claims = [claim for item in items if (claim := _claim(item))]
    reports = [
        normalized.get("coverageReport")
        for normalized in normalized_items
        if isinstance(normalized.get("coverageReport"), dict)
    ]
    revisions = [
        normalized.get("researchRevision")
        for normalized in normalized_items
        if isinstance(normalized.get("researchRevision"), dict)
    ]
    counters = [
        normalized.get("counterThesis")
        for normalized in normalized_items
        if isinstance(normalized.get("counterThesis"), dict)
    ]
    scenarios = [
        normalized.get("researchScenario")
        for normalized in normalized_items
        if isinstance(normalized.get("researchScenario"), dict)
    ]
    claim_set_hash = _claim_set_hash(claims)
    scenario_set_hash = _scenario_set_hash(scenarios)
    unverified = [
        claim
        for claim in claims
        if claim.get("verificationStatus") != "verified"
        or not _strings(claim.get("evidenceIds"))
        or not _has_one_to_one_bound_evidence_refs(claim)
    ]
    counters_without_evidence = [
        counter
        for counter in counters
        if not _strings(counter.get("evidenceIds"))
    ]
    scenarios_without_evidence = [
        scenario
        for scenario in scenarios
        if not _strings(scenario.get("evidenceIds"))
        or not _has_one_to_one_bound_evidence_refs(scenario)
    ]
    coverage_satisfied = any(
        report.get("satisfied") is True
        and report.get("decision") == "finalize"
        and report.get("claimSetHash") == claim_set_hash
        for report in reports
    )
    matching_revisions = [
        revision
        for revision in revisions
        if revision.get("claimSetHash") == claim_set_hash
        and revision.get("scenarioSetHash") == scenario_set_hash
    ]
    reasons: list[str] = []
    if not claims:
        reasons.append("missing_claims")
    if unverified:
        reasons.append("unverified_claims")
    if not coverage_satisfied:
        reasons.append("coverage_not_satisfied")
    if counters_without_evidence:
        reasons.append("untraceable_counter_thesis")
    if scenarios_without_evidence:
        reasons.append("untraceable_scenario")
    if not matching_revisions:
        reasons.append("missing_revision")
    publish_allowed = not reasons
    metrics = {
        "publishAllowed": publish_allowed,
        "gateReasons": reasons,
        "claimCount": len(claims),
        "unverifiedClaimCount": len(unverified),
        "coverageSatisfied": coverage_satisfied,
        "counterThesisCount": len(counters),
        "scenarioCount": len(scenarios),
        "revisionCount": len(matching_revisions),
        "rejectedInputCount": 0 if publish_allowed else len(items),
    }
    if publish_allowed:
        return copy.deepcopy(items), metrics, []
    rejected: list[str] = []
    for item in items:
        _reject(rejected, item)
    return [], metrics, rejected


def _normalized(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("normalizedData")
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _with_normalized(
    item: dict[str, Any], normalized: dict[str, Any], *, candidate_id: str | None = None
) -> dict[str, Any]:
    updated = copy.deepcopy(item)
    updated["normalizedData"] = normalized
    updated["contentHash"] = _digest(normalized)
    if candidate_id is not None:
        updated["candidateId"] = candidate_id
    return updated


def _claim(item: dict[str, Any]) -> dict[str, Any] | None:
    normalized = item.get("normalizedData")
    claim = normalized.get("claim") if isinstance(normalized, dict) else None
    return claim if isinstance(claim, dict) and isinstance(claim.get("claimId"), str) else None


def _scenario(item: dict[str, Any]) -> dict[str, Any] | None:
    normalized = item.get("normalizedData")
    scenario = normalized.get("researchScenario") if isinstance(normalized, dict) else None
    return (
        scenario
        if isinstance(scenario, dict) and isinstance(scenario.get("scenarioId"), str)
        else None
    )


def _value(item: dict[str, Any], field: str) -> Any:
    normalized = item.get("normalizedData")
    if isinstance(normalized, dict) and field in normalized:
        return normalized[field]
    raw = item.get("raw")
    if isinstance(raw, dict) and field in raw:
        return raw[field]
    return item.get(field)


def _text(item: dict[str, Any], field: str) -> str | None:
    value = _value(item, field)
    return _clean_text(value) if isinstance(value, str) and value.strip() else None


def _evidence_id(item: dict[str, Any], _index: int) -> str | None:
    for key in ("itemKey", "candidateId", "contentHash"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _evidence_ref(item: dict[str, Any], evidence_id: str) -> dict[str, Any]:
    normalized = item.get("normalizedData")
    existing = normalized.get("evidenceRef") if isinstance(normalized, dict) else None
    reference = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    reference["evidenceId"] = evidence_id
    reference["itemKey"] = (
        reference.get("itemKey")
        or item.get("candidateId")
        or item.get("contentHash")
        or evidence_id
    )
    url = _text(item, "url")
    if url and "url" not in reference:
        reference["url"] = url
    return reference


def _has_one_to_one_bound_evidence_refs(artifact: dict[str, Any]) -> bool:
    evidence_ids = set(_strings(artifact.get("evidenceIds")))
    references = artifact.get("evidenceRefs")
    required = {"evidenceId", "itemKey", "batchId", "runId", "nodeId", "manifestUri"}
    if (
        not isinstance(references, list)
        or len(references) != len(evidence_ids)
        or any(
            not isinstance(reference, dict)
            or not required <= reference.keys()
            or not all(
                isinstance(reference[key], str) and reference[key]
                for key in required
            )
            for reference in references
        )
    ):
        return False
    reference_ids = [
        str(reference["evidenceId"])
        for reference in references
    ]
    return (
        set(reference_ids) == evidence_ids
        and len(set(reference_ids)) == len(references)
    )


def _claim_set_hash(claims: list[dict[str, Any]]) -> str:
    ordered = sorted(
        (copy.deepcopy(claim) for claim in claims),
        key=lambda claim: str(claim.get("claimId", "")),
    )
    return _digest(ordered)


def _semantic_claim_set_hash(claims: list[dict[str, Any]]) -> str:
    return _digest(
        sorted(
            (
                {
                    "claimId": claim.get("claimId"),
                    "statement": claim.get("statement"),
                    "disposition": claim.get("disposition"),
                    "verificationStatus": claim.get("verificationStatus"),
                    "dimensions": _strings(claim.get("dimensions")),
                    "evidenceIds": _strings(claim.get("evidenceIds")),
                }
                for claim in claims
            ),
            key=lambda claim: str(claim.get("claimId", "")),
        )
    )


def _scenario_set_hash(scenarios: list[dict[str, Any]]) -> str:
    ordered = sorted(
        (copy.deepcopy(scenario) for scenario in scenarios),
        key=lambda scenario: str(scenario.get("scenarioId", "")),
    )
    return _digest(ordered)


def _candidate_id(item: dict[str, Any]) -> str:
    value = item.get("candidateId")
    return value if isinstance(value, str) else ""


def _verified_claim_dimensions(item: dict[str, Any]) -> list[str]:
    claim = _claim(item)
    if not claim or claim.get("verificationStatus") == "unverified":
        return []
    return _strings(claim.get("dimensions"))


def _disposition(supporting: set[str], contradicting: set[str], qualifying: set[str]) -> str:
    if not supporting and not contradicting and not qualifying:
        return "unverified"
    if contradicting and (supporting or qualifying):
        return "mixed"
    if contradicting:
        return "contradicted"
    return "supported"


def _disposition_score(claim: dict[str, Any]) -> float:
    return {
        "supported": 1.0,
        "mixed": 0.0,
        "contradicted": -1.0,
        "unverified": 0.0,
    }.get(str(claim.get("disposition")), 0.0)


def _dimensions(value: Any) -> set[str]:
    if isinstance(value, str) and value.strip():
        return {_clean_text(value)}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return {_clean_text(item) for item in value if item.strip()}
    if value is None:
        return set()
    raise ValueError("dimension must be a string or list of strings")


def _field_name(config: dict[str, Any], key: str, default: str) -> str:
    value = config.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _bounded_int(
    config: dict[str, Any], key: str, default: int, *, minimum: int, maximum: int
) -> int:
    value = config.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{key} must be an integer between {minimum} and {maximum}")
    return value


def _string_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return sorted({_clean_text(item) for item in value})


def _strings(value: Any) -> list[str]:
    return (
        sorted({item for item in value if isinstance(item, str) and item})
        if isinstance(value, list)
        else []
    )


def _reject(rejected: list[str], item: dict[str, Any]) -> None:
    candidate_id = item.get("candidateId")
    if isinstance(candidate_id, str) and candidate_id:
        rejected.append(candidate_id)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


RESEARCH_EXECUTORS: dict[tuple[str, str], _Executor] = {
    ("research.claim-project", RESEARCH_PACK_VERSION): _claim_project,
    ("research.coverage-audit", RESEARCH_PACK_VERSION): _coverage_audit,
    ("research.counter-thesis", RESEARCH_PACK_VERSION): _counter_thesis,
    ("research.scenario-simulate", RESEARCH_PACK_VERSION): _scenario_simulate,
    ("research.revision-diff", RESEARCH_PACK_VERSION): _revision_diff,
    ("research.publish-gate", RESEARCH_PACK_VERSION): _publish_gate,
}

__all__ = [
    "RESEARCH_EXECUTORS",
    "RESEARCH_OPERATOR_DEFINITIONS",
    "RESEARCH_PACK_ID",
    "RESEARCH_PACK_VERSION",
]
