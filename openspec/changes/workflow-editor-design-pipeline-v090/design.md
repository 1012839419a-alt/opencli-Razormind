# Change Design

## Requirements Map

| Requirement | Design consequence |
| --- | --- |
| Immediate node authoring | Render local mutation first; never wait for persistence before showing the node. |
| Yjs collaboration | Show LIVE, SYNCING, OFFLINE, and TOKEN REQUIRED in compact text; keep presence secondary. |
| Durable authority | Show local rendering and acknowledged revision as separate facts. |
| Demand-driven labels | Keep original demand, generated labels, and generation provenance visible in project and node context. |
| Grounded evidence | Show grounded count, readable source URLs, missing evidence, and recovery action; never promote model discovery alone. |
| Failure recovery | Preserve disconnected full-Draft PUT, visible retry, revision conflict, and validation blockers. |
| Dense workflow engineering | Preserve compact cards, typed ports, one Dock, keyboard paths, and low-noise canvas surfaces. |

## Evidence Adoption Matrix

| Source | Observed property | Decision | Reason | Target |
| --- | --- | --- | --- | --- |
| Existing `DESIGN.md` and Dark Ops Console | Compact operational density and truth-first states | Adopt | Established product identity | Project foundation and Studio shell |
| Existing React Flow implementation | Canvas, selection, typed handles, viewport | Adopt | Mature installed execution layer | Workflow canvas |
| Existing Yjs/y-websocket implementation | Incremental graph collaboration | Adopt | Mature installed execution layer | Draft authoring |
| Design Pipeline v0.9.0 | Foundation, motion, component-first, evidence gates | Adopt | Prevents design-by-guessing | This change lifecycle |
| Public Yjs demo server | Unscoped external room | Reject | Violates project ownership and privacy | None |
| Generic AI dashboard styling | Gradients, glass, oversized cards, sparkle treatments | Reject | Conflicts with operational trust and density | None |
| Evidence-first permanent split view | Persistent large review pane | Reject as default | Reduces authoring space | Keep in Evidence workspace |

## Product Design Output

Project foundation: `DESIGN.md` (`sha256:150086d05ca2940d2e741501de2f3d86c99454415d846abf832c0a752d8ffbd6`).

Selected direction: Calm Live Operations.

Implementation targets:

- Collaboration badge reports protocol state and scoped room without dominating the canvas.
- Lifecycle strip reports durable revision independently from LIVE state.
- Node picker and local canvas update remain immediate.
- Workflow Dock owns outline, configuration, last run, and Trace.
- Project surfaces show demand labels and grounded counts before entering the graph.
- Evidence and data workbenches receive deeper audit content rather than duplicating it in every node.

## Component Strategy

Reuse project-owned Button, Badge, Tooltip, Tabs, Select, Dialog, Sheet, WorkflowNode, CommandPalette, Workflow Dock, lifecycle strip, status badges, and data-state components. React Flow, Zustand, Yjs, and y-websocket remain runtime providers. No new UI framework or collaboration engine is authorized by this change.

## Accessibility

- WCAG 2.2 AA target.
- Status always includes text or an icon.
- Keyboard add/select/delete/undo, palette search, Dock navigation, and visible focus remain required.
- Reduced motion uses static state and immediate positioning.
- Long Chinese, mixed-script, and identifier strings must expose their complete accessible names.

## Performance

- Local node appearance remains below 350ms in browser acceptance, with a sub-100ms implementation target once palette interaction is excluded.
- Connected persistence is asynchronous and does not issue per-edit full graph PUT.
- Durable acknowledgement target is below 1.5s.
- Offline fallback remains below 1.5s.

## Spec Reconciliation

- Graybox evidence: not required for this bounded refinement; the existing rendered workflow editor is the implementation authority.
- Reference: browser-verified `/studio/workflow` surface and the project foundations.
- Reconciliation: preserve canvas topology, project navigation, canonical node contracts, and status semantics. Change only the collaboration/persistence behavior and the clarity of its state representation.
