---
schema: design-pipeline.motion-foundation.v0.1
name: OpenCLI Workflow Editor Motion Language
posture: minimal
primitiveRegistry: design-pipeline.motion-primitives.v1
activeChange: workflow-editor-design-pipeline-v090
---

# Motion

## Motion Thesis

Motion communicates spatial causality, direct manipulation, asynchronous acknowledgement, and recovery. It never decorates idle operational state. Node authoring appears locally before network persistence; motion must not make a durable save look complete before its revision is acknowledged.

## Motion Principles

- Direct manipulation leads: press feedback begins immediately and node placement follows the pointer or picker decision without waiting for persistence.
- State changes stay bounded: use 70ms press, 120ms response, 160ms control, 200ms panel, and 300ms spatial transitions.
- One owner controls each property and clock. React Flow owns canvas transforms; CSS/WAAPI owns DOM state transitions; Yjs owns collaboration state, not animation.
- LIVE, SYNCING, OFFLINE, BLOCKED, grounded, and ungrounded remain understandable with motion disabled.
- Interruption is safe: opening another panel, changing selection, undoing, navigating scope, or losing connection cancels or retargets motion without replaying the old state.

## Motion Vocabulary

- `press`: 70ms scale or surface response for direct controls; never applied to text-only status.
- `response`: 120ms opacity/surface response after a local edit.
- `control`: 160ms tabs, badges, focus-linked indicators, and compact disclosure.
- `panel`: 200ms Workflow Dock, Sheet, palette, and Inspector entry/exit.
- `spatial`: 300ms bounded canvas fit, scope navigation, and node focus.
- `durable-ack`: a non-looping status transition when a revision is persisted.
- primitive: reveal.trim-line — reserved for a newly created or actively traced edge; a static complete edge is the reduced-motion substitute.

## Procedural Motion

No procedural generator is selected for the workflow editor. Canvas pan/zoom and React Flow edge geometry are interaction state, not decorative procedural motion. Persistent particles, noise fields, orbiting status, shader effects, and autonomous loops are prohibited on the authoring surface.

## Runtime Policy

- CSS transitions are supported for press, response, status, and compact disclosure.
- WAAPI is supported for interruptible panel and bounded spatial choreography when CSS cannot express cancellation cleanly.
- React Flow is supported for viewport and edge geometry; it is the only owner of canvas transform state.
- Motion One remains a supported project dependency only where existing components already use it and cleanup/reduced-motion behavior is explicit.
- Anime.js, GSAP, Canvas, PixiJS, WebGL, and WebGPU are unsupported for ordinary workflow editor transitions. Adoption requires a separate design change and runtime owner.
- Collaboration updates must not replay entry motion for the whole graph. Only the changed node, edge, or acknowledgement may transition.
- Performance budget: no continuous main-thread animation; direct manipulation must remain responsive at the existing graph-size targets.

## Reduced Motion

When `prefers-reduced-motion: reduce` is active:

The reduced-motion fallback substitutes static state, immediate positioning, and textual acknowledgement for every moving treatment.


- press feedback uses color, border, or immediate state with no scale;
- panels appear without translation and with zero or near-zero opacity duration;
- canvas focus changes viewport immediately or uses the shortest non-animated positioning path;
- reveal.trim-line becomes a fully visible static edge;
- durable acknowledgement changes icon and text without movement;
- collaboration cursors may update position without interpolated trails;
- no information, ordering, status, or recovery action is lost.

## Source Decisions

- Adopted: the existing OpenCLI timing tiers, React Flow spatial ownership, project CSS tokens, Yjs collaboration states, and Design Pipeline v0.9.0 motion-foundation contract.
- Adopted: reveal.trim-line only for causal edge creation or active trace because it clarifies graph direction.
- Rejected: continuous glow, pulsing idle badges, orbiting indicators, particle backgrounds, springy card motion, and animation used as the sole status signal.
- Rejected: copying implementations from external motion catalogs; the selected primitive is semantic metadata and `codeCopied: false`.
- Provenance: `openspec/changes/workflow-editor-design-pipeline-v090/decisions/grill.md` and the existing repository design/runtime evidence.
