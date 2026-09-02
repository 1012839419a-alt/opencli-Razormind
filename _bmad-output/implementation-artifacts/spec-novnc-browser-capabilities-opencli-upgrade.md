---
title: 'noVNC 浏览器能力内置与 OpenCLI 升级'
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 1
baseline_commit: '2e945e47912a43c10b3c6c5c6d4abd07d6b54695'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前 noVNC Chromium 默认能力包只有 OpenCLI Browser Bridge 与 Script Host，缺少可见、可离线使用的用户脚本管理器；OpenCLI 仍锁定在 1.8.5，构建、安装脚本和运行时报告版本不一致风险随升级扩大。

**Approach:** 将开源 Violentmonkey MV3 v2.48.0 作为 required、只读、版本锁定的 Runtime Bundle 扩展内置，同时把所有有效 OpenCLI 运行时锁定从 1.8.5 原子升级到 npm 当前稳定版 1.8.7；BBX 继续复用 OpenCLI Browser Bridge，不伪装成第三个浏览器扩展。

## Boundaries & Constraints

**Always:** Profile 仅保存登录、网站状态与 Chromium 必须持久化的用户授权偏好；能力代码仍只来自 Bundle allowlist。新实例启动时以 Chromium `developerPrivate` 支持的配置入口幂等启用 Violentmonkey `userScriptsAccess`，并验证真实脚本执行；该派生偏好不能替代 Bundle 组件或 loaded 健康事实。第三方产物固定来源、版本与 SHA-256（官方 MV3 zip：`583ac595bb698a926eadb6064431fce1108dc2f2adb966ed984738824d2d5a54`），保留上游 MIT 许可证与版权声明，并在构建时校验后解包。Bundle 文件 manifest、数据库默认种子、loaded/desired 上报必须一致。

**Ask First:** 更换用户脚本管理器、使用非官方构建、改变 `userScriptsAccess` 之外的扩展权限或自动预装具体用户脚本。

**Never:** 内置专有 Tampermonkey 包；把能力代码写入 Profile；从浮动 latest URL 构建；跳过散列校验；把 BBX 当成独立 Chrome 扩展；修改历史 verification 证据冒充新验收结果。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新镜像启动 | 默认 Bundle 完整 | Chromium 同时加载 Violentmonkey、Bridge、Script Host；BBX daemon 使用 OpenCLI 1.8.7 | 任一 required 组件缺失或版本不符时拒绝启动/READY |
| 第三方包构建 | 官方 v2.48.0 MV3 zip | 散列验证通过后解包到版本目录，manifest 版本匹配 | 下载或散列失败则镜像构建失败 |
| 版本漂移 | desired/loaded 缺少 Violentmonkey或 OpenCLI 仍为旧版 | Slot 不进入 READY，并返回可诊断漂移 | 不得静默降级或以 desired 冒充 loaded |
| 用户脚本授权 | 新 Profile 或偏好被清除 | 启动自检自动启用 Violentmonkey `userScriptsAccess`，最小用户脚本可执行 | 无法启用或验证执行时不得 READY |

</frozen-after-approval>

## Code Map

- `chrome/runtime-bundles/opencli-default/1/manifest.json` -- 已发布的两组件 Bundle，保持不可变。
- `chrome/runtime-bundles/opencli-default/2/manifest.json` -- 新默认 Bundle 真值源；声明 `violentmonkey@2.48.0` required extension。
- `scripts/resolve-browser-runtime-bundle.mjs:19-135` -- 已有 path containment、required 文件、组件 manifest 版本和 capability 引用校验；直接复用。
- `chrome/Dockerfile:4-40`、`agent/Dockerfile:24-47` -- OpenCLI 安装锁定及 Bundle 产物装配；加入固定 URL/散列的 Violentmonkey MV3 解包和 GPL 许可证/源码链接。
- `chrome/entrypoint.sh:48-78`、`agent/entrypoint.sh:14-43` -- 已按 resolver 输出生成 `--disable-extensions-except/--load-extension`，原则上无需第二套加载机制。
- `backend/migrations/versions/l9m0n1o2p3q4_add_browser_runtime_bundles.py:15-44` -- 历史 revision 保持不可变。
- `backend/migrations/versions/` -- 新增后续 revision：写入 `opencli-default@2`，迁移仍指向系统默认 v1 的实例/分配，同时保留 v1 供回滚和谱系审计。
- `Dockerfile:31-34`、`scripts/install-agent.sh:315-332`、`scripts/install-managed-opencli.ps1:11-29`、`backend/acquisition/registry.py:7-35`、`backend/api/v1/nodes.py:384-385` -- 有效 OpenCLI 1.8.5 锁定/报告位置，统一迁移至 1.8.7。
- `tests/unit/test_browser_runtime_bundle.py`、`tests/unit/api/test_nodes_install_script.py` -- 覆盖升级数据库、READY、required 缺失、版本漂移及 V2 patch 标记。
- `frontend/e2e/browser-runtime-bundle.spec.mjs:3-125` -- 验证管理界面显示第三组件和 CONFIG_DRIFT。

## Tasks & Acceptance

**Execution:**
- [x] `chrome/Dockerfile`、`agent/Dockerfile`、`opencli-default/2` Bundle manifest -- 固定并校验 Violentmonkey 官方 MV3 产物，保留 GPL-3.0 许可证与上游源码链接，作为 required 扩展装入两类镜像；v1 不变。
- [x] 新 Alembic revision 与运行时默认选择 -- 新增 v2 Bundle 并迁移系统默认 v1 引用，证明已应用旧 revision 的数据库升级后不会 CONFIG_DRIFT。
- [x] OpenCLI 构建、安装、运行时版本位置 -- 统一升级到 1.8.7，更新 V2 patch 契约及所有当前断言，删除仍影响当前行为的 1.8.5 锁定。
- [x] 后端单测、前端 E2E 与真实浏览器 smoke -- 覆盖正常加载、旧库升级、缺失、版本漂移、许可证落盘、管理界面展示、Violentmonkey 用户脚本和 BBX 调用。

**Acceptance Criteria:**
- Given 新建 noVNC 浏览器实例，when 默认镜像完成启动自检，then 扩展清单含 Violentmonkey 2.48.0、OpenCLI Browser Bridge 0.1.0、OpenCLI Script Host 1.2.0，Slot 为 READY，BBX/OpenCLI 调用可用。
- Given 任一构建或托管安装入口，when 安装 OpenCLI，then 使用并报告 1.8.7，当前行为路径中不存在 1.8.5 锁定。
- Given Violentmonkey 包被篡改或组件缺失，when 构建或启动，then 对应阶段明确失败，不产生看似 READY 的实例。

## Spec Change Log

- iteration 1：审查发现直接修改已应用 migration 且原地改变 `opencli-default@1` 会使升级数据库永久 CONFIG_DRIFT，并破坏不可变版本谱系；改为保留 v1、新建 v2 和后续迁移。KEEP：固定官方 v2.48.0/SHA、OpenCLI 1.8.7、三组件 fail-closed、现有 UI 展示和测试结构；同时补齐上游许可证、V2 patch 断言与真实浏览器 smoke。
- 用户批准 A：允许启动流程自动设置 Violentmonkey `userScriptsAccess`。授权偏好可由 Chromium 持久化，但能力代码仍必须来自只读 Bundle；新增授权失败 fail-closed 与真实用户脚本执行验收。审查核对上游 v2.48.0 后纠正规格中的许可事实：Violentmonkey 使用 MIT，不是 GPL-3.0；镜像必须保留上游 MIT 全文与版权声明。

## Design Notes

Violentmonkey 采用官方 `Violentmonkey-mv3-v2.48.0.zip`，而非 CRX 或源码现场构建：它与当前 Chromium MV3 方向一致，官方 release 提供可复现 SHA-256，且 unpacked 目录能被现有 `--load-extension` 路径直接加载。发布为新的 `opencli-default@2`；v1 目录、资产和历史 migration 保持可用且不变，后续 migration 负责数据库升级、默认引用迁移及旧 READY 部署失效。镜像必须携带上游 v2.48.0 的 MIT 文本、版权声明和精确源码/tag 链接。Chrome 138+ 没有公开的强制启用策略，因此启动器通过受控 `chrome://extensions`/`developerPrivate.updateExtensionConfiguration` 设置 `userScriptsAccess`，随后用真实脚本执行证明授权生效；仅对声明 Violentmonkey 的 Bundle 执行，失败必须阻止 READY。BBX 是 CLI/daemon 对 Bridge 的调用面，不增加重复扩展。

## Verification

**Commands:**
- `uv run pytest tests/unit/test_browser_runtime_bundle.py tests/unit/api/test_nodes_install_script.py` -- expected: 旧库升级到 v2、三组件 READY、required 缺失、版本漂移、V2 patch 契约和 fail-closed 全部通过。
- `npm --prefix frontend run test -- browser-runtime-bundle` -- expected: Bundle v2 组件展示与漂移断言通过；若项目脚本不支持文件过滤，则运行对应 Playwright spec。
- `docker build -f chrome/Dockerfile .` 与 `docker build -f agent/Dockerfile .` -- expected: 固定产物下载、SHA-256 校验、MIT 许可证落盘、解包及 OpenCLI 1.8.7 安装成功。
- 启动最终重建的实际 noVNC Chrome，读取 runtime report 并分别执行一个最小 Violentmonkey 用户脚本与 BBX `health/page.get_state` -- expected: v2 三项能力真实可用，非仅 manifest 声明。

## Suggested Review Order

**启动与 READY 边界**

- 启动器按 Bundle 声明执行授权、脚本探针并原子发布报告。
  [`entrypoint.sh:33`](../../chrome/entrypoint.sh#L33)

- 授权器通过 CDP 设置权限、执行真实脚本并可靠清理。
  [`ensure-violentmonkey-userscripts-access.mjs:1`](../../scripts/ensure-violentmonkey-userscripts-access.mjs#L1)

- 后端拒绝缺少 Violentmonkey 嵌套自检的 READY 报告。
  [`browser_service.py:151`](../../backend/services/browser_service.py#L151)

**不可变 Bundle 与升级**

- v2 Manifest 固定三项 required 浏览器能力。
  [`manifest.json:1`](../../chrome/runtime-bundles/opencli-default/2/manifest.json#L1)

- 后续迁移切换 v2 并使旧部署进入重启状态。
  [`m0n1o2p3q4r5_add_opencli_default_v2.py:1`](../../backend/migrations/versions/m0n1o2p3q4r5_add_opencli_default_v2.py#L1)

- 镜像同时保留 v1，校验并装配 v2 与 MIT 许可证。
  [`Dockerfile:32`](../../chrome/Dockerfile#L32)

- Compose 默认明确选择 v2，避免覆盖启动器默认值。
  [`docker-compose.yml:317`](../../docker-compose.yml#L317)

**OpenCLI 1.8.7 兼容**

- 补丁适配 1.8.7 Bridge，并保留远程 daemon 上下文。
  [`patch-opencli.js:110`](../../scripts/patch-opencli.js#L110)

- 本机和托管安装入口统一使用固定版本。
  [`install-agent.sh:312`](../../scripts/install-agent.sh#L312)

**验证**

- 行为测试覆盖授权成功、幂等、失败、端点和清理。
  [`test_violentmonkey_userscripts_access.py:1`](../../tests/unit/test_violentmonkey_userscripts_access.py#L1)

- Runtime 测试覆盖 READY、漂移、迁移与降级。
  [`test_browser_runtime_bundle.py:680`](../../tests/unit/test_browser_runtime_bundle.py#L680)

- 镜像契约锁定双 Bundle、许可证、报告与 fail-closed。
  [`test_agent_image_runtime_packaging.py:1`](../../tests/unit/test_agent_image_runtime_packaging.py#L1)
