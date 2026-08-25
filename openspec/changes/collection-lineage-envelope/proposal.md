## Why

The collection audit found two execution planes whose provenance stops at different boundaries: scheduled collection runs do not carry SourceBinding revisions or credential scope into persisted outputs, while durable acquisition artifacts are not connected to normalized records, enrichment, or delivery. As a result, operators cannot prove which source revision, binding, execution, worker/runtime, or artifact produced a record or notification, and old records have no safe compatibility contract.

## What Changes

- Define one immutable collection-lineage envelope for every persisted collection execution and every downstream output or attempt.
- Propagate source, binding, account/credential, project scope, run/execution, worker/runtime, trace, and artifact references through collection tasks, task runs, acquisition executions, normalized records, enrichment results, and notification/delivery logs.
- Specify nullable lineage fields and read behavior for records created before this contract.
- Give notification and delivery attempts their own lineage and idempotency references without inventing quota, capacity, or identifiers.
- Explicitly bound this P0-1 change: acquisition raw results are lineage-bearing inputs until they are normalized into records; raw results are not themselves asserted to be records, evidence, enriched outputs, or delivered items.

## Capabilities

### New Capabilities

- `collection-lineage-envelope`: An immutable, nullable-compatible provenance contract that links collection source and execution context to records, artifacts, enrichment, trace events, and delivery attempts.

### Modified Capabilities

- Existing scheduled collection and durable acquisition persistence SHALL reference the common lineage contract.
- Existing record, artifact, enrichment, trace, and notification projections SHALL preserve lineage when they are derived from a collection execution.

## Impact

- Backend collection, acquisition, pipeline, artifact, enrichment, trace, and notification persistence models and their serializers.
- Worker/runtime adapters and execution boundaries that construct or forward lineage.
- Migrations and compatibility reads for pre-existing records.
- Focused contract and integration verification for scheduled and durable acquisition paths.

## Non-Goals

- This change does not define durable schedule occurrence leases, cancellation/lease-loss semantics, stage partial-success state machines, or restart reconciliation (P0-2/P0-3 and later slices).
- This change does not normalize acquisition raw items or make them enter the record/evidence/AI/delivery path; it defines the boundary and lineage needed by that later slice.
- This change does not infer provider quota, capacity, token usage, cost, or timing when the provider did not return documented evidence.
- This change does not synthesize missing source, binding, worker, runtime, trace, artifact, run, or execution IDs.
