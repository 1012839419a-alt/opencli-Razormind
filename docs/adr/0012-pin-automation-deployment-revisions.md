# Pin enabled Automations to Deployment Revisions

An enabled Automation pins immutable Agent Deployment Revisions instead of silently following later Runtime or permission changes. Administrators explicitly upgrade and re-enable an Automation, preserving reproducible and auditable behavior; emergency suspension and permission revocation override pinned revisions immediately because safety takes precedence over reproducibility.

## Observable runtime contract

- `schedule` accepts exactly `hourly`, `daily@HH:MM`, `weekdays@HH:MM`, or
  `weekly@HH:MM`. `weekly` means Monday. Evaluation uses the Automation's IANA
  `timezone`: nonexistent DST wall-clock minutes are skipped, while the two
  folds of an ambiguous minute are distinct UTC occurrences.
- An enabled Automation explicitly pins one enabled, published Operations Agent
  version. Its permission profile must be `observe_only` or `suggest_changes`
  and match the Automation approval mode; `low_risk_automatic`, incompatible
  Agent contracts, and Runtimes not advertised by the bound Fleet node are
  rejected.
- **Run Now** uses that persisted Agent/version binding rather than choosing an
  Agent implicitly. It performs a live Fleet precheck and rejects an offline or
  disconnected binding before creating a queued Run.
- Each scheduled occurrence is unique by `(automation_id, scheduled_for)` and
  persists `trigger_type=scheduled`, a deterministic `trigger_reference`,
  `scheduled_for`, schedule timezone, the Automation revision and full snapshot,
  and pinned Agent/profile/version lineage. Repeated scheduler and worker scans
  reuse the same occurrence.
- A structurally invalid due binding produces one terminal failed occurrence
  with the binding error and the same lineage. A structurally valid binding that
  is temporarily offline remains queued and retryable.
- Celery Beat surfaces queued scheduled Runs, Celery submits token-authenticated
  dispatch requests, and the API process that owns the Fleet WebSocket schedules
  execution. Dispatch is non-blocking and duplicate-safe through the
  `queued -> running` database compare-and-set. Local scheduler ticks recover
  the same queued rows, and API restarts preserve queued scheduled claims.
- Starter Automations are installed paused until a compatible published Agent
  is explicitly bound. Pausing any Automation prevents future claims without
  deleting its durable Run history; acceptance/proof Automations remain paused
  after execution.
