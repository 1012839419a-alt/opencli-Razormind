## 1. Contract

- [x] 1.1 Define the Gaojixing live business chain and its immutable question-package snapshot/digest.
- [x] 1.2 Define answer, citation, and conversation evidence capture states and provenance.
- [x] 1.3 Define normalize → record → evidence lineage and separate delivery transport from business outcome.
- [x] 1.4 Define fixture/mock separation, live prerequisites, and fail-closed blockers.

## 2. Capability and execution

- [ ] 2.1 Publish Gaojixing/Doubao as a capability only when its executable adapter and declared live mode are available; expose publication, configuration, authentication, network, and executable readiness separately.
- [ ] 2.2 Resolve and health-check the authenticated Doubao/OpenCLI session immediately before execution; bind the session identity and scope to the run without persisting secrets.
- [ ] 2.3 Persist the canonical question package snapshot and deterministic digest before dispatch, and use that snapshot for the prompt, evidence, lineage, replay, and audit views.
- [ ] 2.4 Capture the raw answer, extracted citations, conversation reference, adapter/request metadata, and capture status as separate evidence objects; preserve unknown or unavailable fields as unknown/null.
- [ ] 2.5 Reject empty/malformed answers, missing required evidence, capability/session/network blockers, or question-package digest mismatches without creating a live-success result.

## 3. Normalize, record, and delivery

- [ ] 3.1 Route the accepted live answer through the shared normalize and dedupe boundary, retaining package digest, run/execution, worker/runtime, source/binding, and raw-artifact references.
- [ ] 3.2 Persist a normalized record and its evidence links so every record can be traced back to the exact question, answer artifact, citation capture, conversation reference, and execution lineage.
- [ ] 3.3 Add delivery attempt state that records transport outcome independently from business outcome, with idempotent delivery identity and retry lineage.
- [ ] 3.4 Mark business outcome `confirmed` only from a documented destination ACK/equivalent confirmation tied to the delivery attempt; otherwise expose `unconfirmed` or `unknown` even when transport is accepted.
- [ ] 3.5 Ensure delivery failure, timeout, mixed outcomes, and missing ACK are visible as partial/blocked states and never silently promoted to completed business success.

## 4. Fixture and mock boundaries

- [ ] 4.1 Label every fixture/mock run and artifact with its mode and provenance; prevent fixture/mock evidence from satisfying live acceptance.
- [ ] 4.2 Remove or reject implicit fixture/mock fallback when a live capability, session, network, answer, or destination ACK is unavailable.
- [ ] 4.3 Provide explicit fixture-only contract coverage for deterministic package digests, evidence shape, lineage propagation, and transport/business outcome separation without calling live services.

## 5. Verification and live acceptance

- [ ] 5.1 Verify capability publication/readiness reports precise blockers for missing adapter, authentication, session health, or network permission.
- [ ] 5.2 Verify a live run stores one immutable question snapshot/digest and carries it through answer, citation, conversation, normalized record, evidence, and delivery projections.
- [ ] 5.3 Verify a changed source question after dispatch cannot alter the run's snapshot or digest and cannot mix evidence from another run.
- [ ] 5.4 Verify fixture/mock output is visibly non-live and cannot produce live business acceptance.
- [ ] 5.5 Verify transport accepted without destination ACK remains unconfirmed/unknown, while a matching destination ACK produces confirmed business outcome.
- [ ] 5.6 Verify timeout, captcha, unauthenticated session, network denial, empty answer, malformed citation/conversation capture, lineage mismatch, and destination failure all fail closed with actionable typed state.
- [ ] 5.7 Run focused contract/integration checks and a live acceptance only after all external prerequisites in proposal.md are supplied; no live claim may be based on mocks or fixtures.
