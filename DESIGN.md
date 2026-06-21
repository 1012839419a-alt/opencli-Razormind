# Design

## Source of truth
- Status: Draft
- Last refreshed: 2026-06-21
- Primary product surfaces: Vite React admin UI under `frontend/src/`
- Evidence reviewed:
  - `PLAN_ui_reskin.md`
  - `frontend/src/components/Layout.tsx`
  - `frontend/src/pages/DashboardPage.tsx`
  - `frontend/src/pages/NotificationsPage.tsx`
  - `frontend/src/components/Card.tsx`
  - `frontend/src/components/PageHeader.tsx`
  - `frontend/src/index.css`
  - `frontend/tailwind.config.js`
  - `vstorm-co/agentcanvas` at GitHub main branch, reviewed 2026-06-21
  - `superloglabs/superlog` at GitHub main branch, reviewed 2026-06-21
  - `2233admin/monoscope` at GitHub master branch, reviewed 2026-06-21

## Brand
- Personality: dark mission-control workspace for browser/data collection operations, with Grok-like intelligent black UI restraint and SpaceX-like telemetry precision.
- Trust signals: clear topology, visible health, timestamped events, deterministic controls.
- Avoid: generic CRUD dashboard feel, rainbow KPI cards, emoji branding, decorative gradients, oversized marketing composition.

## Product goals
- Goals:
  - Make the system understandable as connected runtime nodes and data flows.
  - Surface operational health before configuration tables.
  - Preserve dense admin workflows for repeated use.
  - Make the console usable for ADHD-style operation: one current focus, low memory load, fast command access, and obvious next actions.
- Non-goals:
  - No framework rewrite.
  - No marketing landing page.
  - No decorative graph that cannot drive real work.
- Success signals:
  - A user can see which sources, browser nodes, tasks, agents, records, and notifications are connected.
  - A user can inspect a failing run from topology to event log without guessing where to click.
  - Visual language feels like one product, not Tailwind defaults.

## Personas and jobs
- Primary personas:
  - Operator: monitors collection health and recovers failed runs.
  - Builder: configures sources, agents, schedules, notifications, and browser nodes.
  - Maintainer: deploys on NAS or local hosts and validates worker/browser connectivity.
- User jobs:
  - Understand the current runtime topology.
  - Trace data from source to task run to record to notification ACK.
  - Find failed or stale nodes quickly.
  - Configure new collection paths with confidence.
- Key contexts of use: desktop, dark environments, long-running operations, repeated inspection.

## Information architecture
- Primary navigation:
  - Overview
  - Topology
  - Runs
  - Records
  - Configuration
  - System
- Core routes/screens:
  - Dashboard becomes an operational overview plus topology preview.
  - A new Topology view should show node relationships as the primary mental model.
  - Existing CRUD pages remain available as focused configuration/detail surfaces.
- Content hierarchy:
  - First: health, broken paths, active work.
  - Second: node graph and data-flow relationships.
  - Third: tables, filters, and raw configuration.

## Design Principles
- Workflow-first, node-assisted: the dashboard stays the control surface; node and flow diagrams explain a selected run or subsystem instead of becoming the whole product.
- Storyboard every run: model calls, tools, nested agents, records, latency, token usage, and cost should be represented as ordered operational stages when the data exists.
- Operational density: compact information, stable rows, clear scan paths.
- Observable by default: every node should expose state, last event, and next action.
- One accent color: use color for state and action, not decoration.
- Preserve reversibility: destructive or external actions remain explicit.
- Notebook-friendly: records, runs, and nodes should support quick notes, pinned context, and saved work views without forcing the user to keep state in memory.

## Library decisions
- Component library: shadcn/ui source-owned components over Radix Primitives.
  - Rationale: the project already has `components.json`, Radix packages, Tailwind, `class-variance-authority`, `clsx`, and `tailwind-merge`; this lets us build an OpenCLI-native kit without adopting a pre-styled system that fights the Grok/SpaceX direction.
  - Rule: install/copy shadcn primitives when behavior is needed, then immediately reskin them to OpenCLI tokens. Do not leave default rounded-md/slate component styling in product screens.
  - Use for: buttons, inputs, dialogs, selects, tooltips, badges, menus, tabs, drawers, forms, skeletons, and command surfaces.
  - Avoid for now: Ant Design, Mantine, Carbon, Radix Themes, or other full visual systems unless a specific enterprise surface needs that tradeoff.
- OpenCLI UI Kit: product-specific components under `frontend/src/components/opencli/`.
  - Rationale: keep repeated control-surface patterns such as panel headers, metric tiles, playback controls, inspectors, timelines, and telemetry rails reusable without coupling them to page files.
  - Rule: page components should prefer OpenCLI UI Kit pieces before writing page-local panel/header/metric markup.
- Graph/workflow canvas: `@xyflow/react`.
  - Rationale: mature MIT React Flow package for draggable/selectable nodes, edges, minimap, controls, keyboard interaction, and custom node rendering.
  - Use for: Topology, node inspector selection, failure-path tracing, future workflow editing.
- Auto layout: `elkjs`.
  - Rationale: handles layered data-flow layouts better than hand-positioned nodes.
  - Constraint: EPL-2.0 license; acceptable for runtime dependency review, but keep graph model code independent so it can be swapped if needed.
- Data grids: `@tanstack/react-table`; add `@tanstack/react-virtual` only when a screen stops using bounded pagination.
  - Rationale: headless table state, sorting/filtering/selection/column visibility, and a clean path to saved views while preserving current UI style.
  - Use for: Records first, then tasks/logs/notifications.
- Command surface: `cmdk`.
  - Rationale: lightweight accessible command menu for quick navigation and action launch.
  - Use for: global command palette, route switching, "show failed", "open recent records", and future note commands.
- Notebook editor: evaluate `@blocknote/react` in a later phase.
  - Rationale: strong block editor for notes, but heavier and MPL-2.0; persistence and note data model should be designed before adding it.
  - Phase-1 fallback: pinned plain-text/Markdown note panels and saved views.

## Visualization References
- Agentcanvas:
  - Keep: run-as-storyboard, step inspector, token/cost meters, nested-agent framing, guided flow language.
  - Adaptation: embed as a dashboard strip and detail drawer, not a full-screen canvas by default.
  - Data gap: current APIs expose task run events and elapsed time; token, model-call, tool-call, nested-agent, and dollar fields should be read from event detail when available and added to backend contracts later.
- Superlog:
  - Keep: Explore-style filters, incident timeline, dense event tables, dashboard widgets, and honest sparse timeseries.
  - Adaptation: use for operational overview and run failure recovery flows.
- Monoscope:
  - Keep: virtualized high-volume logs, query editor, trace waterfall, and deferred heavy charts.
  - Constraint: AGPL-3.0 source, use only as product reference unless licensing is explicitly accepted.

## Visual language
- Color:
  - Default dark canvas: off-black base, near-black panels, white hairline borders.
  - Primary accent: aviation red for selected, warning attention, destructive, and operator-active states.
  - Neutral white/zinc for totals, charts, and table structure.
  - Green/yellow/red remain semantic health colors only.
  - Avoid blue/purple dashboard defaults unless a domain state explicitly requires them.
- Typography:
  - Primary UI font: Source Han Sans / Noto Sans SC stack for Chinese readability.
  - Telemetry font: `ToaHI-Rg` first, used selectively for the OC mark, micro-labels, metrics, IDs, timestamps, and short operational codes.
  - Do not set the whole product in monospace; use mono/data styling only where it improves scan speed.
- Spacing/layout rhythm:
  - Dense but breathable 8px rhythm.
  - No large marketing-style hero blocks.
- Shape/radius/elevation:
  - 0-2px radius for tactical panels and controls.
  - Border-first surfaces, inner highlights, no decorative shadows.
- Motion:
  - Subtle transitions for selection, drawer entry, and graph hover.
  - Run/story playback is allowed when it explains sequence, causality, or debugging state.
  - Preferred engine for richer playback: `gsap` + `@gsap/react`, using `useGSAP()` cleanup semantics.
  - Fallback when animation dependencies are unavailable: React state machine plus CSS transitions and `scrollIntoView`, preserving `prefers-reduced-motion`.
  - No ornamental movement.
- Imagery/iconography:
  - Lucide icons for navigation and state.
  - Topology nodes use semantic icon + status ring, not illustrations.
  - No emoji logo marks in product chrome.

## Components
- Existing components to reuse:
  - `Layout`
  - `Card`
  - `PageHeader`
  - `DataTable`
  - `StatusBadge`
  - `ErrorAlert`
  - `LoadingSpinner`
- New/changed components:
  - `AgentFlightBoard`
  - `TopologyCanvas`
  - `TopologyNode`
  - `TopologyEdge`
  - `NodeInspector`
  - `HealthRail`
  - `EventTimeline`
  - `CommandPalette`
  - `FocusQueue`
  - `SavedViewBar`
  - `MetricTile`
  - semantic `Button`, `Input`, `Select`, and `Tabs` wrappers over current styling
- Variants and states:
  - Nodes: idle, running, warning, failed, offline, selected, stale.
  - Edges: active, inactive, failed, delayed.
  - Tables: loading, empty, error, filtered empty, stale data.
- Token/component ownership:
  - Theme tokens live in `frontend/src/index.css` and `frontend/tailwind.config.js`.
  - Shared primitive styling lives under `frontend/src/components/ui/`.
  - Page-level hand-written color classes should be replaced incrementally.

## Accessibility
- Target standard: WCAG 2.1 AA where practical.
- Keyboard/focus behavior:
  - Topology nodes must be keyboard selectable.
  - Inspector drawers and modals restore focus.
- Contrast/readability:
  - Dark theme must avoid low-contrast gray-on-gray text.
  - Status is not color-only; labels and icons remain visible.
- Screen-reader semantics:
  - Topology has a list/table fallback or semantic summary.
- Reduced motion and sensory considerations:
  - Respect reduced-motion preferences for graph transitions.

## Responsive Behavior
- Supported breakpoints/devices:
  - Desktop is primary.
  - Tablet should remain usable.
  - Mobile should show stacked summaries and lists, not a cramped graph.
- Layout adaptations:
  - Desktop: sidebar + main topology + inspector panel.
  - Narrow screens: topology summary list + bottom/detail drawer.
- Touch/hover differences:
  - Hover affordances must also be available on click/tap.

## Interaction States
- Loading:
  - Skeletons for tiles and topology nodes.
  - Preserve layout dimensions to avoid shifting.
- Empty:
  - Explain what object is missing and give the next configuration action.
- Error:
  - Show failing subsystem and retry action.
- Success:
  - Use concise toasts for mutation completion.
- Disabled:
  - Explain unavailable actions through title/tooltip or adjacent text.
- Offline/slow network:
  - Show stale timestamp and keep last-known topology visible.

## Content Voice
- Tone: concise, operational, calm.
- Terminology:
  - Node: browser node, worker node, agent node, source node, notification endpoint.
  - Flow: source -> task -> processor -> record -> notification.
  - Run: one execution of a collection task.
- Microcopy rules:
  - Prefer state labels over explanations.
  - Avoid feature-description copy inside the app chrome.

## Implementation Constraints
- Framework/styling system:
  - Keep Vite + React 18 + Tailwind 3 + TanStack Query.
  - Use proven dependencies for graph/table/command behavior instead of custom-building those primitives.
- Design-token constraints:
  - Replace raw `blue-600`, `gray-900`, and rainbow KPI classes with semantic tokens.
- Performance constraints:
  - Topology must handle dozens of nodes without expensive re-render loops.
  - Large tables should remain paginated or virtualized before broad expansion.
- Compatibility constraints:
  - Keep existing API contracts unless backend changes are explicitly coordinated.
  - Preserve i18n for Chinese and English.
- Test/screenshot expectations:
  - `npm test`
  - `npm run build`
  - Browser smoke on `http://localhost:8030/`
  - Before/after screenshots for Dashboard, Topology, Notifications.

## Open questions
- [x] Should the first topology implementation be custom SVG/HTML or use a graph library? Use `@xyflow/react`.
- [ ] Should Topology replace Dashboard as the default route, or sit beside Dashboard first?
- [x] Which node types are P0 for the first graph: sources, tasks, browser nodes, agents, records, notifications? P0 includes all of them, with sampled records/logs.
- [ ] Do we want a live event stream view in the first pass or only polling via current APIs? Start with polling and keep event stream as a later enhancement.
