# InvokeAI Canvas Is An Audited First-Party Subeditor

Status: accepted

OpenCLI will internalize selected InvokeAI Canvas capabilities as an audited,
first-party Image Studio subeditor. This is a narrow exception to ADR-0015's
platform-rendered plugin UI rule; it does not grant plugins a general ability to
ship arbitrary frontend applications. The editor is entered from a governed
Workflow media node and returns to the same Workflow draft without creating a
second application shell.

The browser talks only to OpenCLI-owned APIs through `CanvasHostBridge`. It must
not discover or call the InvokeAI sidecar, hold sidecar credentials, or retain
InvokeAI image URLs. OpenCLI remains authoritative for workspaces, projects,
Canvas documents and snapshots, durable media assets, Workflow versions, Runs,
authorization, and evidence. InvokeAI is a private GPU execution service and a
disposable working cache.

InvokeAI-derived source must remain isolated beneath the governed vendored root,
be listed in `docs/vendor/invokeai/source-files.json`, and carry its origin and
local modifications in `docs/vendor/invokeai/PATCHES.md`. The upstream commit,
OpenAPI digest, license, and container digest are immutable inputs checked by
`scripts/check_invokeai_upstream.py`. A container is deployable only when its
attested source commit equals the approved source commit.

Consequences:

- The Image Studio may provide Canvas, gallery, generation, and administrator-only
  model management, but not InvokeAI user management or its standalone shell.
- InvokeAI routing, authentication, storage, Redux state, browser persistence,
  and Socket.IO access are replaced by OpenCLI-owned boundaries; iframe embedding
  and transparent API proxying are prohibited.
- Online installation of arbitrary InvokeAI custom-node packs is disabled.
  Production images may contain only reviewed, signed, allowlisted extensions.
- Models, LoRAs, and custom nodes keep separate license and provenance records;
  InvokeAI's Apache-2.0 license does not grant rights to those artifacts.
- Missing NOTICE, floating tags, OpenAPI drift, and unregistered vendored files
  fail the repository governance check.
