## Purpose

Define Gaojixing as an attributable live business workflow rather than an unqualified channel demo: an immutable question package is executed through a published and ready Doubao/chat capability, its answer and evidence enter the shared data chain, and delivery is accepted only when the business destination confirms the outcome.

## ADDED Requirements

### Requirement: Live capability readiness is explicit and fail-closed
A Gaojixing run claiming live execution SHALL require a published capability with an executable adapter, an explicitly live mode, a valid authenticated session binding, a passing session health check, and permitted network access. Capability publication, configuration, authentication, session health, network permission, and executable readiness SHALL be represented as distinct states. A catalog entry or configured channel alone SHALL NOT imply live readiness.

#### Scenario: Capability is published but not executable
- **WHEN** the catalog contains Gaojixing/Doubao metadata but no executable adapter or live mode
- **THEN** the run is blocked with a precise capability-readiness reason
- **AND** it does not invoke a fixture/mock adapter or report live success.

#### Scenario: Authenticated session or network is unavailable
- **WHEN** the adapter is published but the required session health check or network policy check fails
- **THEN** the run remains blocked or retryable according to the typed failure
- **AND** no answer, evidence, record, or business-success projection is fabricated from the missing prerequisite.

### Requirement: Execution uses an immutable question-package snapshot and digest
Before dispatch, Gaojixing SHALL persist the exact question package used for the run, including the effective question and relevant execution options, as an immutable snapshot. It SHALL compute a deterministic digest from a canonical representation of that snapshot. Prompt construction, evidence, lineage, replay, and audit projections SHALL reference the same snapshot and digest; mutable source configuration SHALL NOT replace it after dispatch.

#### Scenario: Runtime parameters override configured question
- **WHEN** a run supplies a runtime question that differs from the source's configured question
- **THEN** the snapshot contains the effective runtime question and its canonical digest
- **AND** the adapter, answer evidence, and downstream record all reference that snapshot rather than the stale source value.

#### Scenario: Source changes after dispatch
- **WHEN** the source question is edited after a run snapshot has been persisted
- **THEN** the in-flight or replayed run continues to reference its original snapshot and digest
- **AND** evidence from the edited source cannot be attached to that run.

### Requirement: Answer, citation, and conversation evidence are independently attributable
A live response SHALL capture the raw assistant answer as an evidence artifact and SHALL represent citation extraction and conversation capture as separate evidence projections linked to the same package digest, run/execution, and answer artifact. Each projection SHALL expose capture status and source metadata. Extracting a URL from answer text SHALL NOT assert that the citation is externally verified, and a missing conversation reference SHALL remain unknown rather than being guessed.

#### Scenario: Answer contains citations and a conversation URL
- **WHEN** a live Doubao response returns assistant text, one or more URLs, and a conversation reference
- **THEN** the raw answer, ordered de-duplicated citation list, and conversation evidence are persisted with the same run and package digest
- **AND** citation capture identifies answer-text extraction separately from any future citation verification.

#### Scenario: Conversation status lookup fails
- **WHEN** the answer is captured but the conversation status lookup fails or returns no conversation id
- **THEN** answer evidence remains attributable and citation capture may remain available
- **AND** conversation evidence is recorded as unavailable/unknown without inventing a URL or failing closed solely because this optional reference was not established.

### Requirement: Accepted live answers cross the normalize-to-record-to-evidence lineage
A successfully captured live answer SHALL cross the shared normalize and dedupe boundary before it is represented as a normalized business record. The normalized record, raw answer artifact, citation and conversation evidence, enrichment/trace projections, and any delivery attempt SHALL retain the package snapshot/digest and originating run/execution lineage, including established source/binding and worker/runtime references. A raw response alone SHALL NOT be treated as a record or delivered business item.

#### Scenario: Live answer becomes a stored record
- **WHEN** a captured answer is accepted by normalization
- **THEN** the resulting record links to the exact question-package digest, raw answer artifact, citation/conversation evidence, and execution lineage
- **AND** deduplication does not discard the ability to trace the record to that run and artifact.

#### Scenario: Normalization rejects the answer
- **WHEN** the raw answer cannot satisfy the normalizer or evidence contract
- **THEN** it remains a raw failed/unaccepted artifact with its lineage and typed reason
- **AND** no normalized record, enrichment success, or delivery business outcome is created.

### Requirement: Delivery transport and business outcome are separate
Every Gaojixing delivery SHALL persist an idempotent delivery-attempt identity and separate transport status from business outcome. Transport status SHALL describe what the client/provider reported (for example attempted, accepted, failed, or unknown). Business outcome SHALL be confirmed only by a documented destination ACK or equivalent durable confirmation tied to that delivery attempt; transport acceptance, HTTP 202, enqueue success, or lack of an error SHALL not by itself mean business success.

#### Scenario: Destination accepts transport but does not acknowledge business effect
- **WHEN** the delivery provider accepts a request but no destination ACK or equivalent confirmation is received
- **THEN** transport is recorded as accepted (or the provider's precise status)
- **AND** business outcome remains unconfirmed or unknown and the run is not reported as completed business success.

#### Scenario: Destination ACK arrives
- **WHEN** a destination returns a documented acknowledgement tied to the delivery idempotency key and record/package lineage
- **THEN** the delivery attempt records the ACK evidence and business outcome confirmed
- **AND** retries remain linked to the same delivery identity rather than creating a second business outcome.

### Requirement: Fixture and mock execution cannot satisfy live acceptance
Fixture and mock adapters, responses, sessions, citations, conversation URLs, records, and delivery outcomes SHALL be explicitly labeled with their non-live mode and provenance. They SHALL be usable for deterministic contract verification but SHALL NOT satisfy a live capability/session/network gate or produce a live business-accepted outcome. A live path SHALL NOT silently fall back to fixture/mock behavior.

#### Scenario: Fixture is used for deterministic verification
- **WHEN** a test or preview runs Gaojixing with fixture/mock input
- **THEN** every resulting artifact and projection is marked fixture/mock with its source provenance
- **AND** the run is excluded from live-acceptance reporting and cannot be counted as a live business outcome.

#### Scenario: Live dependency disappears
- **WHEN** a live run loses capability readiness, session, network, or destination access
- **THEN** it fails or remains explicitly unknown/blocked with a typed reason
- **AND** it does not substitute fixture/mock output to reach a successful terminal state.

### Requirement: Gaojixing fails closed on missing or contradictory evidence
The chain SHALL fail closed when a required live prerequisite, answer, package digest, lineage reference, or delivery confirmation is missing or contradictory. It SHALL preserve partial evidence and typed failure/unknown state for diagnosis, but SHALL NOT infer citations, conversation identity, lineage, provider capacity, transport success, or business outcome from timestamps, nearby records, payload hashes unrelated to the package, or configured defaults.

#### Scenario: Evidence belongs to another package or run
- **WHEN** an answer, citation, conversation, record, or delivery event has a package digest or run lineage that does not match the current execution
- **THEN** the projection is rejected or quarantined with a lineage-mismatch reason
- **AND** the current run cannot claim live business acceptance.

#### Scenario: Required answer is empty or malformed
- **WHEN** the live adapter returns no assistant text or an unparseable response
- **THEN** collection terminates with an actionable typed failure
- **AND** no empty answer is normalized, recorded, delivered, or reported as a successful business result.

### Requirement: Live acceptance exposes external prerequisites and honest terminal state
The Gaojixing acceptance surface SHALL state whether capability publication, authenticated session health, network access, and destination ACK prerequisites were actually observed for the run. It SHALL distinguish completed-live, blocked, failed, partial, unconfirmed, unknown, and fixture/mock outcomes. Repository tests or local fixtures SHALL NOT be presented as proof that external live prerequisites were met.

#### Scenario: All live prerequisites and destination confirmation are present
- **WHEN** the published live capability, authenticated healthy session, permitted network, captured evidence, normalized lineage, and matching destination ACK are all observed
- **THEN** the run may be reported as completed live business success
- **AND** the acceptance record retains the prerequisite observations and evidence references.

#### Scenario: An external prerequisite is absent
- **WHEN** any required live prerequisite is unavailable or not observed
- **THEN** the acceptance result identifies the exact missing prerequisite and remains blocked, failed, partial, unconfirmed, or unknown as appropriate
- **AND** it MUST NOT be upgraded to completed live business success by a mock, fixture, transport response, or inferred state.
