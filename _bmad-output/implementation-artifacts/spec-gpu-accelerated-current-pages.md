---
title: '在现有页面内支持可降级的 GPU 加速渲染'
type: 'feature'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
baseline_commit: '0f4b56edb3fd739bab1f0b3cbb9a7c185dab50ca'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/tests/frontend-regression-plan.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前登录背景、项目 Galaxy 和记录关系图已经分别使用 OGL、Three.js、Sigma 等 GPU/WebGL 渲染器，但没有统一的能力探测、可观察后端标记和安全降级边界；渲染器不可用时可能留下空白画布或影响页面可用性。

**Approach:** 在现有 Next.js 页面内增加共享 `GpuSurface` 客户端边界，统一探测 WebGPU/WebGL2、暴露实际渲染后端并提供 DOM/Canvas 降级；先接入登录背景和现有图谱页面，不新增页面、不替换 Base UI，也不引入 GPUIX。

## Boundaries & Constraints

**Always:** GPU 只负责呈现，业务数据、选择状态和权限继续由 React/API 持有；探测必须 SSR 安全；无 GPU、创建上下文失败、减少动态效果或上下文丢失时页面核心操作仍可用；延续 `next/dynamic({ ssr: false })`、可见性暂停和显式资源释放模式；现有用户改动保持不动。

**Ask First:** 引入新的 GPU 依赖、在浏览器启用实验性 WebGPU renderer、把 Canvas2D 关系图整体迁移到另一渲染库，或改变现有路由/产品导航。

**Never:** 新建独立 GPU 页面或桌面应用；把 GPUIX 注入 Next.js；让 GPU 成为登录、工作流、证据或交付的前置条件；以能力探测冒充实际 WebGPU 渲染；删除 DOM fallback、可访问性或 reduced-motion 行为。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| GPU 可用 | 浏览器可创建 WebGL2，上层 GPU renderer 正常挂载 | 原页面内渲染 GPU island，并以稳定属性暴露实际后端 | renderer 异常由边界切换到 fallback，不影响页面其余区域 |
| GPU 不可用 | `getContext('webgl2')` 返回空或抛错 | 登录页显示静态背景；图谱页显示可操作的非 GPU 降级视图 | 不重试死循环，不显示空白画布，不阻止表单和导航 |
| SSR/首次加载 | `window`、`navigator` 尚不可用 | 输出确定的 pending/loading shell，客户端探测后再挂载 renderer | 不在模块加载期访问浏览器全局 |
| 生命周期变化 | 页面隐藏、组件卸载、reduced-motion 或 context lost | 停止无意义帧循环并释放资源；恢复时从 React 状态重建 | 保留业务状态，明确降级原因，避免泄漏 renderer/context |

</frozen-after-approval>

## Code Map

- `frontend/components/canvasui/Ripple.tsx` -- 复用其 SSR 安全探测、回退、暂停与销毁模式，不修改波纹业务。
- `frontend/lib/rendering/gpu-capabilities.ts` -- 新增能力快照，区分可探测与实际采用。
- `frontend/components/gpu/gpu-surface.tsx` -- 新增客户端边界、`data-*` 状态、fallback 和错误隔离。
- `frontend/app/login/page.tsx:63-128` -- 接入边界；无 GPU 时保留静态品牌背景和登录表单。
- `frontend/components/records/project-graph-explorer.tsx:41-57,233-270` -- 保持动态加载；Galaxy 降级时保留搜索、选择与 Inspector。
- `frontend/app/(app)/records/graph/page.tsx:36-45,260-265` -- 为 Sigma WebGL 图增加同一边界。
- `frontend/e2e/login.spec.mjs` -- 覆盖 GPU、无 WebGL2、SSR、reduced-motion 与 context-loss 恢复。
- `frontend/e2e/gpu-graph.spec.mjs` -- 覆盖记录图和 Galaxy 无 WebGL2 时的节点选择与 Inspector。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/lib/rendering/gpu-capabilities.ts`, `frontend/components/gpu/gpu-surface.tsx` -- 实现 SSR 安全探测、实际后端状态、错误边界和降级合同。
- [x] `frontend/app/login/page.tsx` -- 接入 GPU surface；失败时渲染静态背景，不改变登录行为和主题选择。
- [x] `frontend/components/records/project-graph-explorer.tsx`, `frontend/app/(app)/records/graph/page.tsx` -- 在原路由内接入边界，保留非 GPU 可操作路径。
- [x] `frontend/e2e/login.spec.mjs`, `frontend/e2e/gpu-graph.spec.mjs` -- 覆盖 GPU 生命周期和图谱 fallback 的可执行交互。

**Acceptance Criteria:**
- Given 支持 WebGL2 的浏览器，when 打开现有登录或图谱页面，then GPU island 在原页面内挂载且页面暴露实际 renderer 状态。
- Given 浏览器不能创建 WebGL2，when 打开同一页面，then 显示非空降级内容且登录、搜索、导航和 Inspector 等 DOM 操作保持可用。
- Given SSR、页面隐藏或组件卸载，when 生命周期变化，then 不发生浏览器全局访问错误、持续后台帧循环或遗留 GPU context。
- Given WebGPU 仅被探测但没有实际 renderer，when 查看状态，then 产品不得标记为 WebGPU 正在渲染。

## Spec Change Log

## Design Notes

`GpuSurface` 只控制 renderer 是否挂载；业务状态仍在 React/API。`data-gpu-backend` 记录实际采用的 `webgl2`、fallback 或 pending，不把设备理论能力宣称为已启用。

## Verification

**Commands:**
- `npm --prefix frontend run lint` -- 新增边界和页面集成无 ESLint 错误。
- `npm --prefix frontend run build` -- Next.js SSR/客户端边界与动态 imports 可生产构建。
- `npm --prefix frontend run check:login-themes` -- 三种现有主题与 reduced-motion 合同保持通过。
- `npm --prefix frontend run check:record-relationships` -- 现有图谱结构和交互合同保持通过。
- `npm --prefix frontend run test:smoke -- login.spec.mjs gpu-graph.spec.mjs` -- Chromium 中 7 条 GPU、SSR、恢复和图谱 fallback 场景通过。

## Suggested Review Order

**渲染边界**

- 统一实际 backend、降级、可见性和 context-loss 恢复。
  [`gpu-surface.tsx:66`](../../frontend/components/gpu/gpu-surface.tsx#L66)

- 缓存 SSR 安全探测，WebGPU 仅报告 API presence。
  [`gpu-capabilities.ts:19`](../../frontend/lib/rendering/gpu-capabilities.ts#L19)

**现有页面接入**

- 登录页在原页面切换 GPU 背景与静态 fallback。
  [`page.tsx:105`](../../frontend/app/login/page.tsx#L105)

- Galaxy 使用 WebGL2 边界，关系图诚实标记 Canvas2D。
  [`project-graph-explorer.tsx:251`](../../frontend/components/records/project-graph-explorer.tsx#L251)

- Sigma 记录图降级后仍保留节点选择与详情。
  [`graph/page.tsx:317`](../../frontend/app/(app)/records/graph/page.tsx#L317)

**可用降级**

- SSR 未水合时输出确定的 pending 静态背景。
  [`login/page.tsx:86`](../../frontend/app/login/page.tsx#L86)

- 无 GPU 的 Galaxy 以有界节点列表保留 Inspector。
  [`project-graph-explorer.tsx:294`](../../frontend/components/records/project-graph-explorer.tsx#L294)

- 无 WebGL2 的记录图保留双向邻居查看入口。
  [`graph/page.tsx:62`](../../frontend/app/(app)/records/graph/page.tsx#L62)

**行为验证**

- 覆盖 GPU、无 WebGL2、SSR、reduced-motion 与 context-loss。
  [`login.spec.mjs:65`](../../frontend/e2e/login.spec.mjs#L65)

- 覆盖记录图和 Galaxy fallback 的真实点击链路。
  [`gpu-graph.spec.mjs:167`](../../frontend/e2e/gpu-graph.spec.mjs#L167)
