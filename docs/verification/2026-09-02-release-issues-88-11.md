# Release issues #88 and #11 verification

Date: 2026-09-02

Repository: `2233admin/opencli-Razormind`

## Decision

Neither issue is closed by the evidence currently available. This worktree
contains a report-only closeout, not a release or backend implementation
change. No candidate image was promoted, no public release was created, and no
GitHub issue or comment was edited.

## Issue #88: arm64, promotion, and public installers

Issue: [#88](https://github.com/2233admin/opencli-Razormind/issues/88)

Remote status observed: **open**. The issue body still has all three scope
checklists unchecked and the page exposes no acceptance-result comment or
linked release evidence.

### Evidence that exists

- [PR #87](https://github.com/2233admin/opencli-Razormind/pull/87) is closed and
  merged. Its summary reports candidate multi-architecture manifests, recovery
  behavior, and the following local verification: 134 Python tests, 27
  frontend auth/restart checks, 6 Playwright tests, production build,
  TypeScript, ESLint, Ruff, Compose, and script/YAML parsing.
- The PR handoff cites successful CI runs
  [33420106600](https://github.com/2233admin/opencli-Razormind/actions/runs/33420106600)
  and
  [33467760460](https://github.com/2233admin/opencli-Razormind/actions/runs/33467760460).
  These are PR #87 integration checks, not #88 acceptance evidence: neither
  establishes a native arm64 runner, a controlled promotion failure, or clean
  downloaded-release installer E2E.
- The merged PR explicitly says that the immutable v0.4.1 release does not
  include its recovery behavior and that a separately authorized release is
  required. It also says the privileged Docker daemon restart was not run
  locally; only the CI gate was added.
- The merged commit
  [`2de34ccf`](https://github.com/2233admin/opencli-Razormind/commit/2de34ccf8e68799f062f29523f381655d531718f)
  contains candidate-image verification and candidate-to-release promotion
  workflow scaffolding.
- [The release workflow history](https://github.com/2233admin/opencli-Razormind/actions/workflows/release.yml)
  shows only two historical release runs, v0.4.1 and v0.4.0.
- [Latest release](https://github.com/2233admin/opencli-Razormind/releases/latest)
  is still v0.4.1, tag [`153b4f8`](https://github.com/2233admin/opencli-Razormind/commit/153b4f835f323d035b5e55f664f725b8011f9b54),
  released 2026-08-03. Its seven assets include the compose files,
  `.env.docker.example`, and both installers. There is no post-#87 public
  release.

### Missing acceptance evidence

1. A native Linux arm64 runner must run entrypoint and health/recovery checks
   for all five published variants. The current local Windows host cannot
   produce this evidence.
2. A controlled candidate-promotion failure must prove coordinated rollback or
   a documented deterministic fail-safe state. The promotion job has not run
   from this worktree, and no failure/rollback evidence is attached to #88.
3. Clean release-gate environments must download the vended release assets,
   then execute both installers through secret generation, Compose startup,
   login/health verification, and reboot/recovery. No such run is available.
4. A new authorized release must be created only after those gates pass. v0.4.1
   must not be described as containing the #87 recovery behavior.

## Issue #11: 5090 backend handoff

Issue:
[#11](https://github.com/2233admin/opencli-Razormind/issues/11)

Remote status observed: **open**. The issue asks 5090 to push a dedicated
branch, provide the backend/migration/test handoff, report commands and
results, and state that compatibility runtime validation is simulated rather
than live Dify/n8n worker execution.

The issue has one handoff comment claiming:

> Pushed: branch `feat/workflow-persistence-closed-loop`, commit
> `c326a2ace5882d226f1753bf65df0560b33209af`.

The commit is publicly viewable:
[`c326a2a`](https://github.com/2233admin/opencli-Razormind/commit/c326a2ace5882d226f1753bf65df0560b33209af).
It is titled `feat: workflow persistence closed loop, Dify/n8n import,
recursive packages`, has parent `6e09973`, and changes 16 backend/schema/service
and integration-test files. However, the named branch URL
[`feat/workflow-persistence-closed-loop`](https://github.com/2233admin/opencli-Razormind/tree/feat/workflow-persistence-closed-loop)
currently returns 404, and the public branch index does not list it. No PR
link or newer issue comment supplies a replacement branch, merge commit, or
fresh CI result. Therefore the handoff is **partially evidenced by the commit
object, but not proven as a current remote branch/PR delivery**, and #11
cannot be marked complete from this worktree.

The commit page and issue handoff also preserve the important limitation:
compatibility execution is simulated shape/provenance validation, not live
Dify/n8n worker dispatch. That limitation must remain explicit in any
closeout.

## Local baseline and checks

Commands run in this worktree:

```text
git status --short --branch
## 2233admin/razormind-release-ops

git rev-parse HEAD
02342ae3cbeb642a0e2d032aec45f92b695339a0

git rev-parse origin/main
2de34ccf8e68799f062f29523f381655d531718f

git merge-base HEAD origin/main
851aef2db7581c1baafd951192702047659074a2

git rev-list --left-right --count HEAD...origin/main
32 1

git merge-base --is-ancestor 4d4ef84 HEAD
exit 0
```

The baseline check required by the 5090 coordination document passes, but this
worktree is not descended from the current `origin/main` PR #87 merge. The
current local `.github/workflows/release.yml` still publishes versioned and
`latest` image tags directly; it has no native arm64 job, no candidate
promotion/rollback gate, and no downloaded-asset installer E2E job. The
candidate/promotion helpers exist only on `origin/main` at `2de34ccf` and were
not copied here because doing so would mix an incomplete pre-#87 release
workflow with the wrong application baseline.

## External blockers and next actions

- A maintainer must authorize or run the post-#87 release from the merged
  `origin/main` baseline, with access to a native Linux arm64 runner and clean
  installer environments.
- The release run must retain candidate manifests, attach arm64/installer/
  promotion-failure evidence to #88, and publish only after all gates pass.
- A maintainer or 5090 must restore a current dedicated branch or PR for
  `c326a2a`, rebase it against the intended current main, and update #11 with
  exact branch/PR/CI links and test results.
- This report does not close or comment on either issue because the required
  external actions and evidence are not available to this worker.
