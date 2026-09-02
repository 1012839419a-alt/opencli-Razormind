---
title: 'Browser Runtime Bundle 一等能力'
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'b9ec317efda601322f6c314af8d18b5700b7aeb0'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前 Chromium 镜像和启动器把 OpenCLI Bridge 固定在单一路径，扩展版本随镜像、能力隐含在 Profile，管理端无法编排、锁定、验证或审计实例真实加载的浏览器能力。

**Approach:** 将浏览器实例建模为基础镜像、登录 Profile、Browser Runtime Bundle 与资源规格的组合；以版本化 Manifest 驱动多扩展/脚本/OpenCLI 插件加载，并把选择、部署健康、受控 capability invoke 与 Trace 作为现有浏览器管理和插件中心的一等能力。

## Boundaries & Constraints

**Always:** Profile 只存登录和网站状态；能力来自只读版本目录。Bundle/组件显式版本化并受 allowlist、最小权限、信任等级和风险门禁约束。只有 loaded 与 desired 一致且自检通过的 Slot 才 READY。同一 Profile 禁止两个 Chromium 同时写入。Agent/前端只调用结构化 capability。

**Ask First:** 新外部包仓库、签名基础设施、Profile Lease 语义变更、生产第三方扩展或破坏性迁移。

**Never:** 加载 Bundle 外扩展；把扩展状态写进 Profile；暴露 eval/new Function/远程代码；以 desired 冒充 loaded；原地热升级执行中 Slot。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 创建实例 | 有效 Bundle 版本、Profile、资源规格、启动页与网络策略 | 持久化锁定配置，启动器只加载 Manifest allowlist 中存在且版本匹配的组件 | 缺包、路径越界、版本不符或 required 组件失败时拒绝 READY |
| Slot 上报 | desired/loaded Bundle、扩展、脚本、插件及自检结果 | 计算 READY/DEGRADED/CONFIG_DRIFT/EXTENSION_FAILED/SCRIPT_FAILED/RESTART_REQUIRED | 未知组件或动作清单漂移必须 fail closed 并保留诊断 |
| 能力调用 | `POST /browser-sessions/{id}/capabilities/{capability}/invoke` 与结构化 args | 校验 Bundle 暴露能力、schema、host、risk/gate 后路由到对应动作 | 未授权、未健康、schema 错误或 gate 缺失不得调用 |

</frozen-after-approval>

## Code Map

- `backend/models/browser.py`、`backend/schemas/browser.py` -- BrowserInstance 绑定与版本化包、Bundle、部署、健康契约。
- `backend/api/v1/browsers.py`、`backend/services/browser_service.py` -- 复用现有注册/patch/base64 endpoint，增加 Bundle CRUD、状态上报和 invoke。
- `backend/browser_pool.py`、`backend/acquisition/runner.py` -- desired/loaded 健康归并、READY 准入、Profile Lease 与调用路由。
- `backend/services/plugin_registry_service.py`、`backend/api/v1/plugins.py` -- 复用版本、签名、权限、能力和 Runtime readiness，增加浏览器插件类型。
- `chrome/entrypoint.sh`、`agent/entrypoint.sh` -- 两条路径按 Bundle allowlist 加载多个只读版本目录。
- `chrome/Dockerfile`、`agent/Dockerfile`、`docker-compose.yml` -- 安装系统扩展并挂载 Manifest；Profile volume 仅存用户数据。
- `frontend/lib/api/{types,endpoints,hooks}.ts` -- Bundle、包、健康、实例选择和 invoke API/query。
- `frontend/components/browsers/{chrome-instance-form-dialog,chrome-instances-panel}.tsx` -- Bundle/Profile/资源/策略选择与漂移展示。
- `frontend/app/(app)/plugins/page.tsx`、`browser-act-packs-panel.tsx` -- 复用插件卡片与状态；Act Pack 只读关联 Bundle。
- `tests/unit/test_browser_service.py`、`tests/unit/test_browser_pool.py`、新 API/UI 测试 -- 覆盖 allowlist、健康、准入、门禁和界面行为。

## Tasks & Acceptance

**Execution:**
- [x] `backend/models/browser.py`、迁移、schemas/services -- 实现版本化包、Bundle、实例锁定、部署与健康领域模型及严格 Manifest 校验。
- [x] `backend/api/v1/browsers.py`、插件注册表 -- 暴露管理、Slot 上报和 capability invoke；记录 Bundle/组件版本、输入输出、耗时、风险、gate、错误及页面前后状态。
- [x] `chrome/entrypoint.sh`、`agent/entrypoint.sh`、Dockerfiles/compose -- 以明确环境变量和 Bundle Manifest 加载多个版本目录，required 缺失即启动失败。
- [x] `frontend/lib/api/*`、浏览器管理组件、插件中心 -- 完成 Bundle 管理、实例选择、状态/漂移展示与 Act Pack 关联。
- [x] 后端和前端测试邻域 -- 覆盖 I/O 矩阵、迁移兼容、权限失败、Profile Lease 和 UI 关键流程。

**Acceptance Criteria:**
- Given 两个使用同一 Bundle 版本的新 Slot，when 它们完成启动自检，then 上报的扩展、脚本、OpenCLI 插件和 capability 清单一致且都进入 READY。
- Given Bundle desired 版本或任一 required 组件与 loaded 状态不一致，when 调度器选 Slot，then 该 Slot 不接收新 Session 并显示可诊断的非 READY 状态。
- Given Agent 请求已注册 capability，when schema、host、risk 与 gate 全部满足，then 系统结构化调用并生成含完整版本谱系的 Trace；任一条件不满足则 fail closed。
- Given 管理员创建浏览器实例，when 选择 Runtime Bundle、Profile、Resource Class、Startup Pages 和 Network Policy，then 后端持久化并在实例列表准确展示 desired/loaded 状态与漂移。

## Design Notes

Bundle Manifest 是 desired 配置源；浏览器主动上报是 loaded 事实源。健康状态由二者纯函数归并，数据库不能自行宣告 READY。P0 Script Host 只加载打包 content scripts 与受控 action registry，不依赖 `chrome.userScripts`。

## Verification

**Commands:**
- `uv run pytest tests/unit/test_browser_service.py tests/unit/test_browser_pool.py tests/unit/test_browser_runtime_bundle.py` -- expected: 新旧浏览器契约通过。
- `npm --prefix frontend run typecheck` -- expected: Bundle API 与 UI 类型无错误。
- `npm --prefix frontend run test` -- expected: 实例配置、漂移和插件中心行为通过。
- `docker compose config` -- expected: Bundle 挂载和环境变量有效。
- `pwsh -NoProfile -Command "& $env:CODE_INTEL_HOME/legacy/Invoke-SentruxAgentTool.ps1 session_end ."` -- expected: 无结构回归。

## Suggested Review Order

**运行时契约**

- 从不可变 Manifest 解析唯一允许加载的组件与能力。
  [`resolve-browser-runtime-bundle.mjs:19`](../../scripts/resolve-browser-runtime-bundle.mjs#L19)

- 严格 schema 固化组件、能力、实例配置与 loaded 事实。
  [`browser.py:58`](../../backend/schemas/browser.py#L58)

- 纯归并函数确保 desired 与 loaded 一致才进入 READY。
  [`browser_service.py:84`](../../backend/services/browser_service.py#L84)

**部署与安全边界**

- 兼容迁移保留旧 Slot，并种入系统默认 Bundle。
  [`l9m0n1o2p3q4_add_browser_runtime_bundles.py:57`](../../backend/migrations/versions/l9m0n1o2p3q4_add_browser_runtime_bundles.py#L57)

- 动态容器锁定 Bundle、Profile、资源和网络配置。
  [`browser_containers.py:65`](../../backend/api/v1/browser_containers.py#L65)

- capability 调用统一校验健康、schema、host、risk 与管理员 gate。
  [`browser_capability_service.py:83`](../../backend/services/browser_capability_service.py#L83)

- 隐藏扩展页跨越 MV3 worker 休眠，保持 action registry 可调用。
  [`ensure-script-host.mjs:1`](../../scripts/ensure-script-host.mjs#L1)

- Script Host 仅通过 CDP 调用已打包 action registry。
  [`agent_runtime_dispatch.py:130`](../../backend/agent_runtime_dispatch.py#L130)

**管理控制台**

- Bundle 面板提供版本、Manifest、信任等级与 Act Pack 关系。
  [`browser-runtime-bundles-panel.tsx:208`](../../frontend/components/browsers/browser-runtime-bundles-panel.tsx#L208)

- 实例表单一次提交 Profile、Bundle、资源、启动页和网络策略。
  [`chrome-instance-form-dialog.tsx:99`](../../frontend/components/browsers/chrome-instance-form-dialog.tsx#L99)

**验证证据**

- 单元测试覆盖双 Slot READY、漂移、门禁、审计与 Profile Lease。
  [`test_browser_runtime_bundle.py:102`](../../tests/unit/test_browser_runtime_bundle.py#L102)

- 解析器测试锁定 allowlist、路径边界和组件版本。
  [`test_browser_runtime_bundle.py:431`](../../tests/unit/test_browser_runtime_bundle.py#L431)

- Playwright 验证 Bundle 期望态、加载态、漂移和配置入口。
  [`browser-runtime-bundle.spec.mjs:34`](../../frontend/e2e/browser-runtime-bundle.spec.mjs#L34)
