# InvokeAI Patch Ledger

Approved upstream commit:
`d315b8967f548732912bd9b390853ed4af97d8cb`.

There are currently no copied InvokeAI source files and therefore no local
patches. The existing OpenCLI Image Studio host and bridge are independently
implemented platform code.

Before adding an upstream-derived file, the same change must:

1. register its local relative path, upstream path, and upstream blob SHA in
   `source-files.json`;
2. add a ledger row below describing all local modifications and their tests;
3. preserve applicable upstream copyright and license notices; and
4. pass `python scripts/check_invokeai_upstream.py`.

| Patch ID | Local file | Upstream path/blob | OpenCLI modification | Verification |
| --- | --- | --- | --- | --- |
| _none_ | — | — | No InvokeAI source has been vendored. | Governance checker |
