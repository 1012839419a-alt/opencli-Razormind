# PRD: Project Evidence Relationships and Galaxy Explorer

Status: in-development

Date: 2026-07-24

Owner: OpenCLI project intelligence

Upstream reference:

- `2233admin/galaxy-view`, version `0.6.0`, commit `ca00838`
- License: MIT
- Product reference: Obsidian Graph View interaction model

## 1. Problem

The project workbench already stores evidence-bearing records, sources, runs, workflows,
entities, and their relationships. The current evidence page exposes these records as
lists and summaries, but it does not provide a usable spatial model for answering:

- What evidence supports this entity or conclusion?
- Which records refer to each other in both directions?
- Which workflows, runs, sources, and records form a dense cluster?
- What is peripheral, isolated, or unexpectedly connected?

The first graph prototype proved that the existing project record graph API can feed
both 2D and 3D renderers. It did not meet the intended product quality. In particular,
the 3D page used a generic force graph without the spatial atmosphere, camera direction,
focus modes, visual presets, quality control, and lifecycle discipline demonstrated by
Galaxy View.

## 2. Product decision

OpenCLI will develop a downstream product based on Galaxy View's rendering and
interaction capabilities. This is not an embedding of the Obsidian plugin shell and is
not a pixel-for-pixel copy of Obsidian.

The downstream product replaces the following upstream boundaries:

| Upstream boundary | OpenCLI implementation |
| --- | --- |
| Obsidian vault and metadata cache | Project record graph API |
| Notes, tags, and canvas files | Projects, workflows, runs, sources, records, entities |
| Obsidian view lifecycle | React route and component lifecycle |
| Obsidian commands and settings tab | Project navigation and in-view controls |
| Vault file opening | Evidence inspector and project-native deep links |

The rendering ideas, visual behavior, camera behavior, search/focus behavior, quality
tiers, and WebGL resource-management patterns are valid downstream product inputs.

## 3. Product outcome

Every project has two independent graph pages:

1. **Evidence relationships** — a legible 2D bidirectional graph for tracing evidence
   and relationships.
2. **Galaxy explorer** — an immersive 3D spatial view for discovering structure,
   clusters, hubs, and unexpected relationships.

Both pages:

- are first-class project navigation destinations;
- use the same project evidence graph contract;
- support search, selection, inspection, and stable node identity;
- require no API key or hosted third-party service;
- remain usable when the backend returns a sampled or truncated graph.

## 4. Page responsibilities

### 4.1 Evidence relationships

Primary jobs:

- trace direct and reverse relationships;
- distinguish evidence kinds and relation kinds;
- focus one node and its immediate neighborhood;
- read labels without entering a cinematic mode;
- drag, pan, zoom, and reset the layout;
- open project-native evidence details.

This page should feel close to Obsidian Graph View, not Obsidian Canvas. It is a graph
navigation surface, not a free-form document editor.

### 4.2 Galaxy explorer

Primary jobs:

- reveal clusters, hubs, bridges, and isolated evidence in three dimensions;
- provide camera fly-to, orbit, zoom, reset, wander, and focus modes;
- render deep-space atmosphere without obscuring evidence semantics;
- support visual presets and explicit quality tiers;
- preserve smooth interaction under the supported project graph sizes.

## 5. Shared domain contract

The project record graph is the stable domain Interface. Renderers consume a
project-owned Adapter and must not depend directly on Obsidian or Galaxy View types.

Required node fields:

- stable id;
- kind;
- label and optional subtitle/preview;
- count/status;
- derived degree and visual weight.

Required edge fields:

- stable source and target ids;
- relation kind;
- weight;
- direction and bidirectional state.

The Adapter may derive layout and rendering fields but must not mutate API objects.

## 6. Galaxy capability map

| Capability | Target | Phase |
| --- | --- | --- |
| Deterministic starfield and spatial motes | Required | P0 |
| Deep-space and daylight visual presets | Required | P0 |
| High, low, and mobile quality tiers | Required | P0 |
| Search or inspector selection flies camera to node | Required | P0 |
| Recenter / zoom-to-fit | Required | P0 |
| Selection and neighbor emphasis | Required | P0 |
| Visibility-aware animation pause | Required | P0 |
| Dispose Three.js geometry/materials on unmount | Required | P0 |
| Nebula volume layer | Required | P1 |
| Cluster cloud layer after force settlement | Required | P1 |
| Curved relation paths and directional travel | Required | P1 |
| Focus card and neighbor-only mode | Required | P1 |
| Wander / guided tour | Required | P1 |
| Connect-two path exploration | Required | P1 |
| Tag/kind lens and graph filters | Required | P1 |
| Bloom/post-processing where supported | Required | P2 |
| Worker-based force layout for very large graphs | Conditional | P2 |
| Import of Obsidian settings or vault data | Not planned | — |

## 7. Architecture

### 7.1 Modules

- `project-force-graph`: domain-to-renderer Adapter shared by 2D and 3D pages.
- `project-relationship-force-graph`: 2D renderer Implementation.
- `project-galaxy-force-graph`: 3D renderer Implementation and interaction controller.
- `project-galaxy-rendering`: visual tokens, quality tiers, atmosphere objects, and
  disposal helpers.
- `project-graph-explorer`: route shell, data query, search, selection, and inspector.

### 7.2 Seams

- Data seam: `ProjectRecordGraphPreview -> ProjectForceGraphData`.
- Selection seam: stable node id shared by search, renderer, and inspector.
- Camera seam: selected node id drives fly-to without coupling search to Three.js.
- Rendering seam: scene decoration is attached through the renderer's scene Interface
  and removed through React lifecycle cleanup.
- Quality seam: one tier controls pixel ratio, geometry density, and optional effects.

## 8. Interaction requirements

- Clicking a node selects it and flies the camera to a readable distance.
- Selecting a search result performs the same camera action.
- Clicking the background clears focus.
- Reset returns the whole visible graph to frame.
- Selected node and direct neighbors remain prominent; unrelated edges recede.
- Controls remain keyboard reachable and have text or accessible labels.
- Mobile uses tap selection, a capped pixel ratio, reduced atmospheric density, and no
  mandatory hover interaction.

## 9. Performance and lifecycle

P0 targets:

- desktop: interactive at 1,200 visible nodes on the existing project graph API;
- mobile: cap graph density at 700 visible nodes unless explicitly increased;
- animation work pauses while the page is hidden;
- all custom geometries, materials, animation frames, observers, and timers are released
  on unmount;
- no external network request is required to render either graph.

Performance degradation must be explicit. A lower quality tier reduces pixel ratio,
star density, node geometry resolution, and link effects before removing core graph
content.

## 10. Acceptance criteria

P0 is complete when:

- project navigation exposes both graph pages;
- both pages render from a real `ProjectRecordGraphPreview`;
- 2D supports drag, pan, zoom, select, clear, and neighbor emphasis;
- Galaxy includes deterministic atmosphere, preset selection, quality selection,
  camera fly-to from canvas and search, reset, and selection emphasis;
- hidden pages stop custom animation work;
- custom Three.js resources are disposed during unmount;
- TypeScript, targeted lint, production build, and browser smoke checks pass;
- the UI and repository documentation retain MIT attribution to Galaxy View where
  downstream code is adapted.

## 11. Delivery slices

### P0 — Product baseline

- lock the two-page information architecture;
- establish the shared Adapter;
- ship 2D relationship exploration;
- ship the downstream Galaxy renderer baseline;
- verify lifecycle, build, and project navigation.

### P1 — Investigation tools

- nebula and cluster-cloud rendering;
- focus card and neighbor-only mode;
- kind/tag lenses and relation filters;
- Wander and Connect-two interactions;
- project-native deep links from the inspector.

### P2 — Scale and polish

- bloom and post-processing capability detection;
- worker force layout and large-graph profiling;
- saved user visual preferences;
- automated interaction and WebGL leak checks.

## 12. Licensing

Galaxy View is MIT licensed. Adapted source must retain the upstream copyright and MIT
notice. OpenCLI-owned adapters, product shell, domain model, and project navigation
remain native OpenCLI code. Dependency notices must be updated before release.
