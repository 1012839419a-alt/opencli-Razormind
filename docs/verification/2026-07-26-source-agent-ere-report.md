# Source/Binding + Global Agent Engineering Readiness & Evidence (ERE)

Date: 2026-07-26

Integration baseline: `origin/main` at `8da964cf533297407786d353fe08dc6e6118f80c`

Integration branch: `codex/source-agent-integration`

## Outcome

The two backend seams identified after the architecture consolidation are now
implemented together:

1. Workspace-owned `Source` and immutable `SourceRevision`, with Project-owned
   `SourceBinding` and immutable `SourceBindingRevision` that pins an exact
   Source revision.
2. One Agent Control registry and execution service for all four existing chat
   write actions, with Workspace/RBAC rechecks, explicit confirmation,
   versioned `OperationsWorkItem` evidence, target-version conflict detection,
   and legacy Proposal compatibility.

Legacy `DataSource` and `FeedProvider` behavior remains unchanged. No new
frontend Source editor was introduced; the 12 new operations are recorded under
the existing `studio.sources` capability projection.

## ORCA / 5090 execution evidence

| Lane | ORCA task | Agent | Branch | Worker commit | Worker evidence |
| --- | --- | --- | --- | --- | --- |
| Source/Binding V1 | `task_cc2686e426db` | Claude | `source-binding-v1` | `c4aa92e6b7d8321f8eab65a93d46c89c0cf62f93` | 8/8 focused API and migration-head tests |
| Global Agent Control V1 | `task_cd679bec801a` | Codex | `global-agent-control-v1` | `2ab91e1` | 40 focused tests plus targeted mypy and ruff |

Both lanes ran in isolated clean worktrees on the saved ORCA environment
`5090` (`ws://100.80.105.128:6768`) from the same `origin/main` baseline. The
dirty 5090 `main` worktree and the dirty local root worktree were not modified.

The first 5090 Codex terminal hit the host's known Windows
`CreateProcessAsUserW failed: 5` sandbox error. ORCA reset the dispatch and
restarted Codex in the same isolated worktree with its supported
no-sandbox execution mode; the recovered task then completed normally.

## Integrated changes

- Added four Source/Binding models, schemas, scoped routers, model/router
  registration, and one Alembic migration.
- Added an Agent Control action registry/service and routed chat confirmations
  through it instead of direct service mutations.
- Added or extended regression coverage for:
  - Workspace ownership and cross-Workspace rejection.
  - Immutable Source revisions.
  - Exact SourceBinding revision pins and explicit re-pinning.
  - Viewer denial and cross-Workspace confirmation denial.
  - Proposal attribution/versioning and dispatch-failure evidence.
  - Stale target-version rejection without mutation.
  - Migration-head and legacy-database upgrade compatibility.
- Updated the capability exposure ledger from 193 to 205 OpenAPI operations and
  verified the existing generated catalog remains current.
- Updated the consolidated architecture document to the new single Alembic head
  `f3g4h5i6j7k8`.

## Verification evidence

| Check | Result |
| --- | --- |
| Related Source/Agent/capability tests | 50 passed |
| Added stale proposal conflict test | 1 passed |
| Legacy migration and single-head tests | 6 passed |
| Ruff on new Source/Agent files and tests | Passed |
| Mypy on six affected backend modules | Passed |
| Capability catalog generator `--check` | Passed |
| Fresh SQLite migration upgrade → downgrade → upgrade | Passed; current head `f3g4h5i6j7k8` |
| Full non-live/non-Postgres suite, excluding DNS-affected RSS files | 2489 passed, 3 skipped, 48 deselected |
| Existing 8030 frontend process | HTTP 200; running from `D:\projects\opencli-admin-wt-unified-3002\frontend` |

The first complete non-live run reported 2491 passed and 12 failed. Two failures
were stale assertions for the previous migration head and were fixed. The other
10 failures came from this machine resolving `example.com` to the reserved
benchmark address `198.18.1.6`, which the production SSRF guard correctly
rejects. The same RSS success test fails identically on the unmodified main
worktree, proving this is a local test-environment dependency rather than an
integration regression. The SSRF protection was not weakened.

The ECC pre-push hook also invokes the first `pytest` on `PATH`, currently a
Python 3.10 x-cmd installation, even though this repository requires Python
3.13. That hook fails while importing `enum.StrEnum`; the same tests pass under
the repository's locked uv environment. This is a development-system routing
bug, not an application failure, and should be fixed in the shared hook by
running the repository-declared test command.

## Readiness decision

Ready for review and PR. The integrated backend behavior, migration chain,
capability ledger, and affected test surfaces are verified.

Residual work is deliberately bounded:

- Legacy mutable targets (`DataSource`, schedule, provider) are still globally
  modeled, so Agent Control V1 enforces Workspace isolation at proposal and
  confirmation boundaries rather than through target-row ownership.
- MCP/SDK adapters can now reuse Agent Control but are not added in this slice.
- A Source/Binding frontend editor remains a later Studio task; this slice only
  establishes the backend contract and capability projection.
- RSS channel tests should eventually stub DNS/SSRF resolution so workstation
  DNS policy cannot decide their result.
- The shared ECC pre-push Python runner should use `uv run --extra dev pytest`
  instead of an unqualified global `pytest`.
