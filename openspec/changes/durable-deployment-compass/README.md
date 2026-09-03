# durable-deployment-compass

Make the deployment compass explicit: OpenCLI Admin must be installable,
persisted, upgraded, observed, backed up, and PTT-accepted on Docker, NAS, and
Fleet Agent nodes before capabilities are called deployable.


## Current Handoff / Closure

- Frontend gate closed; Agent packaging closed.
- PTT D1-D4 and D6-D7 are evidenced.
- D0 remains partial because the OpenSpec CLI is unavailable and the Sentrux
  baseline is missing.
- D5 is blocked: workstation DNS resolves public RSS hosts to `198.18.0.x`,
  and the SSRF guard correctly rejects those addresses.
- Data-node IDE work is intentionally deferred.

