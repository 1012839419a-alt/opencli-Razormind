# Workflow Editor Design Decisions

## Product boundary

The target is the existing OpenCLI Studio workflow editor, not a new editor shell. It serves business operators, workflow engineers, and reviewers who build demand-driven automations and inspect real runtime evidence.

## Authority

- The original demand is the authority for generated labels, search terms, and node proposals.
- React Flow remains the canvas and interaction engine.
- Yjs/y-websocket remains the incremental collaboration engine.
- Studio Workflow Draft and immutable Workflow Version remain the durable product authority.
- Evidence, Lineage, grounded status, Workspace ownership, and audit remain first-party OpenCLI responsibilities.

## Operating pressure

Operators work in dense, long-running desktop sessions. They need immediate node authoring, truthful capability state, explicit recovery, and stable project context. Network or collaboration failure must not lose edits.

## Primary workflows

1. Enter or refine a business demand.
2. Review demand-derived labels and proposed nodes.
3. Add, connect, configure, or remove nodes with immediate local feedback.
4. Observe collaboration state and durable save acknowledgement separately.
5. Validate the current revision, publish an immutable version, run it, and inspect Trace, Evidence, Lineage, and grounded gates.
6. Recover from disconnected collaboration, capability gaps, validation errors, and failed runs without hidden fallback behavior.

## Visual direction

Refine the existing Dark Ops Console rather than redesign it. Preserve compact density, zinc surfaces, one primary blue, role-based signal colors, 4px spacing rhythm, restrained radii, Noto Sans SC for UI text, and IBM Plex Mono for identifiers, ports, metrics, and trace data.

Reject decorative gradients, glass-heavy cards, oversized SaaS marketing layouts, anonymous AI sparkle styling, and continuous motion for static state.

## Collaboration behavior

- A local node mutation appears immediately.
- LIVE, SYNCING, OFFLINE, and TOKEN REQUIRED are textual states, not color-only indicators.
- Durable snapshot acknowledgement is visible independently from local rendering.
- Offline mode keeps the current full-Draft PUT fallback.
- Validate and publish force a current durable snapshot.

## Grounding behavior

- Model-discovered entities stay unverified until a concrete readable URL supports the exact product identity.
- Grounded and ungrounded states show source count, missing evidence, and recovery action.
- Project cards summarize demand labels and grounding counts; node configuration retains the original demand and generation provenance.

## Accessibility and motion

Target WCAG 2.2 AA. Preserve keyboard node selection, palette search, visible focus, readable status text, reduced-motion substitutions, and no motion-dependent state communication. Motion explains spatial entry, selection, connection, and asynchronous acknowledgement; it never decorates idle state.

## Performance budget

- Local node appearance: under 100 ms implementation target; current browser acceptance remains below 350 ms including palette interaction.
- Durable collaboration acknowledgement: under 1.5 s.
- Offline fallback acknowledgement: under 1.5 s.
- No full graph PUT for each connected edit.

## Open questions

No material product decision remains for the foundation. Exact visual changes still require direction comparison and bounded desktop/mobile browser evidence before implementation.
