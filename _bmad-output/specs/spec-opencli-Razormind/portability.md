# Project and Workflow Portability Contract

CAP-9 defines portable work as a governed product contract, not database copying.

## Package boundary

A portable package must carry enough stable information to reconstruct the selected project or workflow without environment-owned secrets:

- package schema version, producer version, export time, and integrity manifest;
- project and workflow identity required by the selected transfer profile;
- mutable draft revisions and immutable published workflow versions;
- node, edge, trigger, typed-port, capability, plugin, and version-pin references;
- source definitions, connection requirements, policies, and automation references as non-secret descriptors;
- declared optional payload classes such as records, evidence, artifacts, and run history when the selected profile includes them.

Passwords, API keys, cookies, bearer tokens, reusable session credentials, host-specific paths, and active execution grants are never portable payloads.

## Required package profiles

### Workflow Package

The reusable-design profile contains:

- selected workflow identity, mutable draft revisions, and immutable published versions;
- graph structure, node parameters, triggers, typed ports, and validation metadata;
- plugin, capability, adapter, schema, and version-pin dependency manifest;
- source and connection requirements as non-secret descriptors;
- automation definitions in an inactive state when they are selected for export.

It does not contain collected records, evidence, artifacts, or execution history. Import may create a new project, attach to a selected project, or create a reviewed new workflow revision according to the explicit collision plan.

### Full Project Package

The complete-state profile contains:

- project identity, metadata, policies, memberships or role requirements, and all selected workflows;
- workflow drafts, immutable published versions, inactive automation definitions, and dependency manifests;
- source definitions and destination-side connection requirements without credentials;
- collected records, raw snapshots or artifact references and payloads, evidence units, claim/citation relationships, and lineage;
- workflow runs, events, checkpoints, errors, recovery state, costs, timestamps, and audit provenance;
- package-local integrity references that prove every included record, artifact, evidence edge, and run-history object was transferred or explicitly excluded.

The full profile must preserve historical truth without activating old schedules, replaying external effects, or treating destination credentials and execution resources as transferable state.

## Import lifecycle

1. **Inspect:** Read the package without mutating authoritative state; verify integrity, schema, and producer compatibility.
2. **Preflight:** Report supported objects, blocked objects, missing capabilities/plugins, stale pins, unresolved connections, policy conflicts, and expected data volume.
3. **Plan:** Let the operator choose the required package profile, destination workspace/project, collision behavior, included payload classes allowed by that profile, and local connection mappings.
4. **Apply:** Import transactionally; failure must not leave a runnable half-project or overwrite an existing project silently.
5. **Validate:** Compile imported workflows and verify references without activating automations or creating external side effects.
6. **Activate:** Publishing or enabling imported automations remains a separate governed action.
7. **Audit:** Persist package identity, operator, decisions, mappings, warnings, result, and rollback or recovery status.

## Settings ownership

Settings owns the authoritative surfaces for:

- package export and import;
- migration history and audit results;
- compatibility and dependency reports;
- plugin/capability installation and version repair;
- connection and credential remapping;
- backup, restore, and retention policy.

Project and workflow pages may offer contextual actions such as “Export this workflow” or “Resolve imported dependency,” but those actions deep-link to the same Settings-owned operation and state.

## Safety and compatibility invariants

- Import is dry-run/preflight first and fail-closed on unknown schema or unsafe capability.
- Stable IDs are preserved where they identify portable history; local collisions are resolved explicitly and recorded.
- Reimport is idempotent or produces a reviewed new revision; it never creates silent duplicates.
- Missing plugins, sources, or connections leave the import visible but non-runnable rather than fabricating readiness.
- Connection mappings reference destination-owned credentials; packages never contain reusable secrets.
- Cross-version transforms are deterministic, versioned, and covered by fixture-based compatibility tests.
- Historical evidence retains its original source, time, workflow version, and package provenance when included.
- Full Project Package import is complete only when its manifest accounts for every selected record, evidence edge, artifact, and run-history object; silent omission is failure.
- Workflow Package and Full Project Package use distinct schema/profile identifiers and conformance tests; one cannot be mislabeled as the other.

## Minimum conformance demonstrations

### Workflow Package

On instance A, export a published workflow that uses at least one plugin capability and one credentialed source reference. On a clean instance B with neither dependency configured, import preflight must identify both gaps without creating a runnable workflow. After installing the capability and mapping a destination-owned connection through Settings, the imported workflow must compile, preserve its graph and published-version identity, and complete a real run. Reimporting the same package must not duplicate the workflow or silently overwrite a newer local revision.

### Full Project Package

On instance A, export a project containing multiple workflow versions, at least one completed and one failed run, records, raw evidence, claim relationships, and run events. Import it into a clean instance B. The manifest reconciliation must account for every selected object; historical runs must remain non-executable history, citations must traverse to the transferred source evidence, automations must remain inactive, and no credential may be present. After destination dependencies are repaired in Settings, a new run must append new history without changing imported records, evidence, versions, or run events.

