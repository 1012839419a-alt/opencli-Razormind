## Why

Gaojixing is currently represented by adjacent research/channel and workflow surfaces, but the repository does not yet define one attributable business chain from a live question to an accepted business outcome. The existing Doubao channel can invoke `opencli doubao ask`, extract answer URLs, and best-effort capture a conversation URL; its focused tests use mocked adapter output. The collection audit also identifies a broader gap: raw acquisition, normalization, evidence, enrichment, and delivery are not one durable lineage contract, and delivery transport success is not the business outcome.

Without a strict contract, a fixture or mock can look like a live result, a changed question can be mistaken for the configured question, a citation can be detached from the answer that produced it, and an HTTP 202/send result can be reported as business success without destination acknowledgement.

## What Changes

- Define Gaojixing as a real business workflow chain: publish a live-capable Doubao/chat capability, resolve an authenticated session, execute an immutable question package, capture answer/citation/conversation evidence, normalize and record it, and report transport and business outcomes separately.
- Snapshot the exact question package at execution time and compute a stable digest over its canonical representation; downstream artifacts and events reference that snapshot rather than mutable source configuration.
- Define evidence objects for the raw answer, extracted citations, and conversation reference, with explicit capture status and no claim that a citation was verified merely because a URL was extracted.
- Carry one lineage identity through collect, normalize, record, evidence, and delivery projections so an operator can reconstruct the chain.
- Require capability readiness and live-session/network gates before a run may claim live execution. Fixture and mock paths remain explicitly labeled and cannot satisfy live acceptance.
- Separate delivery transport state (attempted/accepted/failed/unknown) from business outcome (confirmed/unconfirmed/failed/unknown), requiring a destination ACK or equivalent documented confirmation for `confirmed`.
- Fail closed for missing capability publication, unauthenticated or unverified session, unavailable network, missing answer, malformed evidence, lineage mismatch, or absent destination confirmation; never downgrade to fixture/mock success.

## Capabilities

### New Capabilities

- `gaojixing-live-business-chain`: A live-capable, evidence-bearing Gaojixing question workflow with immutable package identity, end-to-end lineage, explicit fixture separation, and fail-closed business acceptance.

### Modified Capabilities

- Existing `doubao_research` collection SHALL remain usable, but its answer/citation/conversation fields SHALL be mapped into the Gaojixing evidence and lineage contract when used by this chain.
- Existing normalize/record/evidence and delivery projections SHALL preserve Gaojixing package, run, and artifact lineage and expose transport versus business outcome separately.
- Existing capability catalogs/readiness projections SHALL distinguish published, configured, authenticated, network-allowed, executable, and live-accepted states; a catalog entry alone SHALL NOT imply live readiness.

## Impact

- Backend capability publication/readiness, Doubao/OpenCLI adapter invocation, question-package persistence, canonical digesting, evidence and lineage models, normalization/record sinks, run events, and delivery/outcome projections.
- Authentication/session binding, network policy, and destination acknowledgement adapters.
- Focused contract and integration verification, including explicit fixture/mock tests that cannot pass live acceptance gates.
- No frontend or backend implementation is included in this read-only proposal.

## External Prerequisites for Live Acceptance

A live acceptance run is possible only when all of the following are true:

1. The Gaojixing/Doubao capability is published by the runtime capability catalog with an executable adapter and an explicit live (not fixture/mock) mode.
2. An authenticated Doubao browser/OpenCLI session is available to the worker, with the required site/session binding and a session health check that passes immediately before execution.
3. The worker has permitted network access to Doubao and any destination/citation endpoint required by the chosen question package; no SSRF or domain-policy block is active.
4. The configured destination is reachable and returns a documented acknowledgement tied to the delivery idempotency key (or an equivalent durable business confirmation).
5. The acceptance operator has a concrete immutable question package and permission to run it; no missing or guessed credentials, capability, evidence, or destination result may be substituted.

These prerequisites are not proven by the repository's mocked unit tests or by a local fixture run. A run lacking any prerequisite MUST remain blocked/unknown and MUST NOT be reported as live business success.

## Non-Goals

- This change does not claim that the current repository already has a Gaojixing capability publication, authenticated live session, public network access, or destination ACK.
- This change does not define a new AI provider, bypass captcha or login controls, or infer capacity, quota, token usage, citation validity, or business success.
- This change does not replace the general collection-lineage envelope; it defines the Gaojixing contract and its required use of that lineage.
- This change does not make fixture/mock execution a fallback for live execution, nor does it turn a transport response into business confirmation.
