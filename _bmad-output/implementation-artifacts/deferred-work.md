- source_spec: `D:\projects\opencli-Razormind-gjx-live\_bmad-output\implementation-artifacts\spec-feishu-bitable-record-delivery.md`
  summary: Reposting an identical workflow run ID can conflict on regenerated event timestamps instead of returning or resuming the stored run.
  evidence: A second identical POST for `run-gaojixing-feishu` raised `WorkflowRunEventConflictError` on the first queued event because its canonical payload differed; this behavior predates the Feishu sink and belongs to workflow-run idempotency infrastructure.
- source_spec: `D:\projects\opencli-Razormind-gjx-live\_bmad-output\implementation-artifacts\spec-feishu-bitable-record-delivery.md`
  summary: Repository-wide Ruff is not currently a usable clean gate because the baseline contains extensive unrelated lint debt.
  evidence: `uv run ruff check backend tests` reported 1,704 pre-existing findings across unrelated modules, while the complete Feishu changed-file set passes Ruff cleanly.
