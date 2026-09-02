# Brownfield Capability Baseline

This companion prevents downstream work from confusing existing foundations with planned work. GitHub state is recorded as observed on 2026-08-24; implementation must recheck current upstream state before relying on an open item.

## Verified merged foundations

| Contract area | Evidence | What may be reused |
|---|---|---|
| Acquisition architecture | [PR #3](https://github.com/2233admin/opencli-Razormind/pull/3), [PR #4](https://github.com/2233admin/opencli-Razormind/pull/4) | Thin-channel/thick-runner model, retries, limits, cursoring, credentials, Crawl4AI, RSS, MCP |
| Cleaning and provenance | [PR #41](https://github.com/2233admin/opencli-Razormind/pull/41) | Versioned native data operators, graph execution, provenance, fail-closed behavior |
| OpenCLI acquisition and deduplication | [PR #42](https://github.com/2233admin/opencli-Razormind/pull/42) | Thick fetch contract, catalog-driven matching, storage-level deduplication proof |
| Governed sources and Agent control | [PR #45](https://github.com/2233admin/opencli-Razormind/pull/45) | Source bindings, proposal/revision control path, capability reconciliation |
| Governed workflow authoring | [PR #46](https://github.com/2233admin/opencli-Razormind/pull/46), [PR #48](https://github.com/2233admin/opencli-Razormind/pull/48) | Backend-authoritative sources, workflow authoring, real-source templates, partial-success semantics |
| Certified capability nodes | [PR #49](https://github.com/2233admin/opencli-Razormind/pull/49) | Version pins, typed ports, readiness, permissions, stale/forged ID rejection |
| Search and feed nodes | [PR #50](https://github.com/2233admin/opencli-Razormind/pull/50) | Governed SearXNG and RSSHub projections over existing executors |
| Local distribution | [PR #53](https://github.com/2233admin/opencli-Razormind/pull/53) | Public images, installers, authenticated login smoke, loopback browser surface |
| Agent-facing runtime evidence | [PR #58](https://github.com/2233admin/opencli-Razormind/pull/58) | HTTP/MCP demand, compile, lifecycle and trace surfaces; preview-versus-runtime boundary |
| Trigger-scoped execution | [PR #60](https://github.com/2233admin/opencli-Razormind/pull/60) | Authoritative compilation of the active trigger graph while retaining parked design nodes |

## Open or partial work

| Gap | Evidence | Contract relevance |
|---|---|---|
| Durable Project-centered product model | [Issue #15](https://github.com/2233admin/opencli-Razormind/issues/15) | Supports CAP-1 and CAP-8, but its external-delivery platform scope and Agent Dock direction are not automatically authoritative |
| L1 acquisition nodes and per-source lineage | [Issue #38](https://github.com/2233admin/opencli-Razormind/issues/38) | Supports CAP-2, CAP-3, and multi-Agent revision safety |
| Schema-drift sensing and adapter self-healing | [Issue #31](https://github.com/2233admin/opencli-Razormind/issues/31) | Supports sustained CAP-2 reliability; existing control machinery lacks complete channel signals |
| Unified plugin center | [Issue #25](https://github.com/2233admin/opencli-Razormind/issues/25) | Supports CAP-6 productization without multiplying top-level product areas |
| Durable observable Agent runs | [PR #70](https://github.com/2233admin/opencli-Razormind/pull/70) | Supports CAP-1 and CAP-8 but remains open and notes a dedicated test gap |
| External Agent runtime adapters | [PR #74](https://github.com/2233admin/opencli-Razormind/pull/74) | Supports runtime interoperability but remains open and one real provider path was blocked by billing |

## Directional precedence

1. The current user direction and this SPEC define the product boundary.
2. Merged, verified runtime contracts define the reusable technical baseline.
3. Open Issues and PRs are design evidence or candidate work, not shipped capability.
4. Issue #15 remains useful for persistent projects, revisions, workflow versions, and Agent governance, but its broad external-delivery platform identity is superseded by the local Deep Research upstream boundary.

## Observed portability failure

On 2026-08-24, the currently connected backend contained the migrated `gaojixing-doubao-evidence` project shell, one primary workflow, published version `v1`, six persisted runs, and 76 events. All six runs were failed or blocked, while the project Data Workbench reported zero records, zero fields, and zero sources. The frontend was also connected to a Docker backend launched from a different checkout with a different Fleet token. This proves partial object transfer, not a complete, compatible project migration, and is the brownfield motivation for CAP-9.

