# QA

## Release integrity

- Release: `design-pipeline v0.9.0`
- Asset: `design-pipeline-skill.tgz`
- Expected SHA-256: `1c6ed651590dc255b96ae8a0a2bdfd87bf3d9649d72f47c06a76041cdb68e957`
- Actual SHA-256: `1c6ed651590dc255b96ae8a0a2bdfd87bf3d9649d72f47c06a76041cdb68e957`
- License: MIT
- Pipeline doctor: ready; no missing requirements.

## Foundations

- `DESIGN.md`: ready
- Design SHA-256: `150086d05ca2940d2e741501de2f3d86c99454415d846abf832c0a752d8ffbd6`
- `MOTION.md`: ready
- Motion SHA-256: `31c6d70594b5c0c7d396544ff84a2e31e30795c657a24592869cf5f26094331e`
- Motion posture: minimal
- Primitive: `reveal.trim-line`

## Scope

- Budget: program
- Score: 37/60
- Surfaces: 3
- Workflows: 4
- Integrations: 3
- Unknowns: 2
- Design decisions: 8
- Wayfinder: not required.

## Runtime evidence

Actual surface: `/studio/workflow` for project `gaojixing-competitor-demand`.

- Collaboration state rendered as `LIVE` with the canonical Workspace/Project/Workflow room.
- Unauthorized WebSocket upgrade returned HTTP 401.
- Local node appearance measured between approximately 263ms and 321ms including picker interaction.
- Durable Yjs revision acknowledgement measured approximately 1.44s.
- Disconnected local appearance measured approximately 153ms.
- Disconnected full-Draft PUT acknowledgement measured approximately 996ms.
- Persisted collaboration writes recorded `updated_by_user_id=collaboration-service`.
- Disconnected fallback recorded `updated_by_user_id=local-development-user`.
- Verification nodes were removed; final graph returned to six nodes.

## Engineering gates

- Collaboration API and demand routing tests: 3 passed.
- Frontend production build: passed.
- TypeScript: passed.
- Static page generation: 42/42.
- Collaboration Node syntax: passed.
- Docker Compose configuration: passed.
- API, frontend, Agent, and collaboration containers: healthy.

## Accessibility and reduced motion

The foundation requires textual collaboration and grounding states, visible focus, keyboard authoring paths, and static reduced-motion substitutes. No new decorative runtime or motion dependency was adopted. Browser acceptance verified the real desktop authoring route; a separate mobile visual refinement was not part of this bounded implementation.

## Claim

The design foundation and implemented collaboration behavior are verified for the current desktop workflow editor. This change does not claim a new visual redesign, pixel reconstruction, or completed mobile redesign.
