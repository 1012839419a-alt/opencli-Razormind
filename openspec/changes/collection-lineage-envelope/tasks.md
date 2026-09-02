## 1. Contract

- [x] 1.1 Define the immutable collection-lineage envelope and propagation points.
- [x] 1.2 Define backward-compatible null behavior for records predating the envelope.
- [x] 1.3 Define notification/delivery lineage and the acquisition raw-result normalization boundary.
- [x] 1.4 Explicitly prohibit invented quota, capacity, cost, and identifiers.

## 2. Backend

- [ ] 2.1 Add the canonical lineage envelope and persistence/serialization contract for source, binding, account/credential, project scope, run/execution, worker/runtime, trace, and artifact references.
- [ ] 2.2 Thread one envelope through scheduled `CollectionTask`/`TaskRun` and durable `AcquisitionExecution` creation and worker handoff without replacing caller-owned identifiers.
- [ ] 2.3 Add nullable lineage references to normalized records, artifact references, enrichment results, trace events, and notification/delivery attempts; preserve nulls for legacy rows.
- [ ] 2.4 Ensure notification and delivery retries retain the originating lineage and use only IDs established by the existing idempotency contract.
- [ ] 2.5 Mark acquisition raw results as pre-normalization inputs and prevent them from being represented as normalized records, evidence, enrichment, or delivery solely by carrying an envelope.
- [ ] 2.6 Add migrations and compatibility serializers/readers for the selected persistence models.

## 3. Verification

- [ ] 3.1 Verify a scheduled run preserves source/binding/account/credential/project scope, run/execution, worker/runtime, trace, and artifact lineage through record, enrichment, and notification projections.
- [ ] 3.2 Verify a durable acquisition execution preserves the same lineage through worker/runtime and artifact boundaries, with no invented IDs or quota values.
- [ ] 3.3 Verify pre-envelope records deserialize and project with null lineage without failing or being relabeled as newly attributable.
- [ ] 3.4 Verify notification mixed outcomes and retries retain originating lineage and delivery identity.
- [ ] 3.5 Verify raw acquisition output remains explicitly pre-normalization until a later normalization contract is implemented.
- [ ] 3.6 Run the repository's focused backend contract/integration checks and strict OpenSpec validation for this change.
