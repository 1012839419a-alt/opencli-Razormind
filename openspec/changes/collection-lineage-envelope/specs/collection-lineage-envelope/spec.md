## Purpose

Define the immutable provenance envelope carried by collection executions and their persisted derivatives, while preserving safe reads of records created before the envelope exists.

## ADDED Requirements

### Requirement: Collection lineage is represented by one immutable envelope
Every collection execution that creates or processes persisted collection output SHALL expose one immutable lineage envelope. The envelope SHALL carry references, when established by the owning system, to the source revision, source binding revision, account and credential revision, project/scope binding, execution, run, worker, runtime, trace, and artifact. A consumer MAY add a derived reference only by preserving the originating envelope; it SHALL NOT mutate the originating values.

#### Scenario: Scheduled collection constructs an attributable envelope
- **WHEN** a scheduled collection is created from a SourceBinding revision with account, credential, and project scope
- **THEN** the CollectionTask and TaskRun carry the same source, binding, account/credential, and scope references
- **AND** the execution and run references are carried into downstream lineage projections
- **AND** no field is populated from an unrelated source or binding.

#### Scenario: Durable acquisition carries the envelope across execution
- **WHEN** an AcquisitionExecution dispatches work to an agent, browser, OpenCLI, or another worker runtime
- **THEN** the worker handoff and resulting artifact references carry the originating envelope
- **AND** the execution remains attributable to the source and binding revision that authorized it.

### Requirement: Persisted records retain collection lineage
A normalized or stored collection record derived from a collection execution SHALL retain references to the originating source, binding, account/credential, scope, execution/run, worker/runtime, trace, and artifact envelope. Record identity or deduplication SHALL NOT discard lineage when multiple projections refer to the same stored record.

#### Scenario: Record preserves scheduled-run provenance
- **WHEN** a scheduled collection item is normalized and stored
- **THEN** the persisted record references the source revision, binding revision, execution/run, worker/runtime, trace, and raw artifact associated with that item
- **AND** a reader can distinguish the record's collection lineage from unrelated records.

#### Scenario: Record preserves durable-acquisition provenance
- **WHEN** a durable acquisition item has crossed the normalization boundary and is stored as a record
- **THEN** the record references the acquisition execution and its artifact through the same lineage envelope shape
- **AND** the lineage does not depend on parsing an unstructured log message.

### Requirement: Enrichment and trace projections preserve lineage
Every persisted enrichment result or enrichment attempt and every persisted collection trace event associated with a record or execution SHALL retain the originating envelope, including the relevant execution/run and worker/runtime references. Trace references SHALL identify the trace context actually used; the system SHALL NOT manufacture trace identity when none was established.

#### Scenario: Enrichment is attributable to its collection
- **WHEN** an AI or other enrichment processor handles a normalized record
- **THEN** its result or attempt references the record's originating lineage and artifact
- **AND** the enrichment projection does not replace collection provenance with only a model/provider reference.

#### Scenario: Worker trace remains tied to runtime
- **WHEN** a worker emits a collection trace event for queueing, execution, artifact production, or handoff
- **THEN** the event carries the originating run/execution and worker/runtime references
- **AND** a trace event from one execution cannot be attached to another execution by position or timestamp alone.

### Requirement: Notification and delivery attempts retain originating lineage
Each notification or delivery attempt derived from collection output SHALL retain the originating collection envelope and SHALL expose the delivery attempt identity supplied by the existing delivery/idempotency contract. Retries and mixed outcomes SHALL remain linked to the same source, binding, execution/run, worker/runtime, trace, artifact, and record lineage.

#### Scenario: Notification references the collected record
- **WHEN** a normalized record triggers a notification or external delivery
- **THEN** the notification log and delivery attempt reference the record and its complete available collection lineage
- **AND** the delivery projection does not become attributable only to a destination or recipient.

#### Scenario: Retry keeps lineage and delivery identity
- **WHEN** a delivery attempt is retried after a timeout or provider failure
- **THEN** the retry retains the originating envelope and record reference
- **AND** it uses the existing delivery-attempt/idempotency identity rules
- **AND** it does not create a synthetic collection run or claim success merely because a retry was scheduled.

### Requirement: Legacy records are backward-compatible and nullable
Lineage fields SHALL be nullable for records, artifacts, enrichment results, trace events, and notification rows created before this contract or created by a path that did not establish a given reference. Compatibility readers SHALL return null for unavailable lineage rather than guessing, rejecting, or relabeling the historical row. New writes SHALL populate every reference that is genuinely available at the boundary that creates the row.

#### Scenario: Historical record remains readable
- **WHEN** a reader loads a record created before collection lineage was persisted
- **THEN** the record loads successfully with unavailable lineage fields represented as null
- **AND** the system does not infer a source revision, execution, worker, runtime, trace, or artifact from timestamps or nearby rows.

#### Scenario: Partially attributable new output remains explicit
- **WHEN** a new output has a valid run and source reference but no worker runtime or artifact reference was established
- **THEN** the persisted projection retains the known references and stores the unavailable references as null
- **AND** it does not block compatibility solely because optional provenance is absent.

### Requirement: The envelope does not invent identifiers or capacity facts
The lineage contract SHALL use only identifiers and provider usage facts established by the source, execution, worker, runtime, trace, artifact, record, or delivery subsystem. It SHALL NOT invent run IDs, execution IDs, worker/runtime IDs, trace IDs, artifact IDs, delivery IDs, quota, capacity, token usage, cost, or other measurements. Unknown or unavailable values SHALL remain null or explicitly unknown according to the owning subsystem's existing representation.

#### Scenario: Missing identifier stays missing
- **WHEN** an acquisition response has no provider request ID or artifact ID
- **THEN** the lineage envelope leaves that reference null/unknown
- **AND** it does not hash unrelated payload data or assign a locally generated surrogate as the provider identifier.

#### Scenario: No quota is inferred
- **WHEN** a provider returns collection output without documented quota or capacity usage
- **THEN** the collection lineage projection records no quota or capacity claim
- **AND** it does not derive one from item count, elapsed time, retry count, or configured limits.

### Requirement: Acquisition raw results have an explicit pre-normalization boundary
An acquisition raw result SHALL be treated as a lineage-bearing input/artifact envelope until a separate normalization operation produces a normalized record. Carrying collection lineage on a raw result SHALL NOT by itself make that result a record, evidence item, enriched output, deduplicated item, or notification input. Raw results that cannot be normalized SHALL remain raw with their lineage and failure/unknown status available to the acquisition boundary.

#### Scenario: Raw result is not silently promoted
- **WHEN** an AcquisitionExecution returns a raw item with a source, execution, worker, runtime, trace, and artifact envelope
- **THEN** the system may persist that raw item and its lineage as an acquisition result
- **AND** it SHALL NOT represent the raw item as a normalized record, evidence, enrichment result, or delivered item until normalization explicitly succeeds.

#### Scenario: Normalization creates the downstream link
- **WHEN** a later normalization operation accepts an acquisition raw item
- **THEN** it creates or updates a normalized record while preserving the raw item's originating envelope and artifact reference
- **AND** downstream enrichment and notification lineage begin from that normalized record rather than from an implicit raw-result shortcut.

### Requirement: Lineage propagation does not weaken authorization boundaries
Lineage propagation SHALL preserve the source, binding, account, credential, and project scope selected by the authorizing execution. A consumer SHALL NOT broaden scope, substitute a credential revision, or use lineage metadata as permission to access an artifact or record.

#### Scenario: Revoked or mismatched binding is not repaired by propagation
- **WHEN** a worker receives an envelope whose binding or credential revision is no longer authorized
- **THEN** the worker follows the existing authorization and revocation behavior
- **AND** it SHALL NOT replace the reference with a current revision merely to produce attributable output.
