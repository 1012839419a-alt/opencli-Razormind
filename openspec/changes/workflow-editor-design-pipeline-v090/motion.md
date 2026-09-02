# Motion

## Foundation

- Project foundation: `MOTION.md`
- Foundation SHA-256: `31c6d70594b5c0c7d396544ff84a2e31e30795c657a24592869cf5f26094331e`
- Posture: minimal
- Selected primitive: `reveal.trim-line`

## Scene: Node Authoring

- Trigger: operator selects a node from the picker or confirms an Agent proposal.
- Local layer: node appears immediately at the resolved canvas position.
- Selection layer: 70ms press response, then 120ms selected-surface response.
- Persistence layer: status changes to saving without moving the node; durable acknowledgement changes text and icon once revision advances.
- Interruption: undo or delete removes/retargets the local state immediately and cancels obsolete acknowledgement.

## Scene: Edge Creation

- Trigger: a valid typed connection is committed.
- Primitive: `reveal.trim-line` for one bounded causal reveal.
- Duration: up to 200ms.
- Invalid connection: no reveal; show the typed contract error and preserve focus.
- Reduced motion: render the complete static edge immediately.

## Scene: Collaboration State

- LIVE, SYNCING, OFFLINE, and TOKEN REQUIRED change through 120ms surface/icon response only.
- Remote graph updates never replay entry animation for the whole graph.
- Remote selection or cursor movement does not produce trails.
- Reconnection does not flash every node or edge.

## Scene: Workflow Dock

- Trigger: open, close, switch mode, or select a node.
- Duration: 160ms for mode response; 200ms for bounded panel entry/exit.
- Interruption: retarget to the latest mode and keep canvas focus recovery deterministic.
- Reduced motion: no translation; content appears immediately or with near-zero opacity duration.

## Runtime Bindings

- CSS: press, response, status, compact disclosure.
- WAAPI: optional interruptible panel/spatial choreography.
- React Flow: canvas viewport and edge geometry.
- No GSAP, Anime.js, Canvas renderer, PixiJS, WebGL, or WebGPU adoption.

## Evidence

Browser acceptance must record local node appearance, durable revision acknowledgement, LIVE/OFFLINE state, disconnected fallback, keyboard cleanup, and reduced-motion behavior before the change can claim visual completion.
