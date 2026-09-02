# CloakBrowser 兼容接入研究

> 调研日期：2026-09-02。范围限定为 CloakHQ/CloakBrowser 官方仓库的 README、源码、发布信息和二进制许可文件，以及本仓库现有浏览器/CDP 接入面。官方自述的反检测测试结果不作第三方验证；本文将官方明确事实与接入推断分开。

## 结论

CloakBrowser 提供的是一个**定制 Chromium 二进制 + Playwright/Puppeteer 薄包装器**，不是新的浏览器自动化协议，也不是一个有认证的远程浏览器服务。默认最小接入有两条路径：

1. **本地启动路径（优先）**：在需要浏览器的机器上安装官方 Python 或 Node 包，由 `launch()` / `launchContext()` / `launchPersistentContext()` 启动本机二进制，再继续使用标准 Playwright API。
2. **CDP 服务路径（适合接入现有 CDP pool）**：运行官方 `cloakserve`，它在一个 HTTP 端口上按 fingerprint seed 启动和复用多个 Chromium 子进程，代理 Chrome DevTools Protocol 的 HTTP discovery 与 WebSocket。客户端仍使用标准 `connect_over_cdp()`。

对本项目最小且真实的改动是增加一个**可配置的 CloakBrowser CDP endpoint/runtime bundle**，复用现有 `backend.browser_pool.py` 的 endpoint、`/json/list`、Playwright `connect_over_cdp` 和按 endpoint 单槽调度；不要实现新的协议，也不要把 `cloakserve` 的内部子端口（默认从 5100 开始）暴露给调用方。第一阶段建议使用本机/内网 `cloakserve`，端口绑定 loopback；如将浏览器能力提供给第三方，需另行取得二进制许可中的 OEM/SaaS 授权。

## 1. 能力边界：官方实际提供什么

### 已证实事实

- README 将项目定义为“Stealth Chromium”，即在 Chromium C++ 源码级别修改 fingerprint 的真实浏览器二进制；它不是 JS 注入或单纯配置补丁。官方 README 的 **Why CloakBrowser / How It Works** 章节声称覆盖 canvas、WebGL、audio、fonts、GPU、screen、WebRTC、network timing、hardware reporting、automation signals 和 CDP input behavior 等信号。来源：[README — Why CloakBrowser](https://github.com/CloakHQ/CloakBrowser#why-cloakbrowser)、[README — How It Works](https://github.com/CloakHQ/CloakBrowser#how-it-works)。
- 包装器返回标准 Playwright 对象：Python `cloakbrowser/browser.py::launch` 返回 Playwright `Browser`；`launch_context` 返回 `BrowserContext`；持久化变体使用 Playwright 的 persistent context。来源：[browser.py](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/browser.py#L302-L430)、[README — API](https://github.com/CloakHQ/CloakBrowser#api)。
- Python 导出 `launch`、`launch_async`、`launch_context`、`launch_context_async`、`launch_persistent_context`、`launch_persistent_context_async`、`ensure_binary`、`binary_info`、`validate_license` 等；来源：[cloakbrowser/__init__.py](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/__init__.py)。
- Node 默认入口是 Playwright；`cloakbrowser/puppeteer` 是 Puppeteer 入口；`cloakbrowser/human` 暴露 CDP 后再手工加 humanize 的辅助层。来源：[js/src/index.ts](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/index.ts)、[js/package.json](https://github.com/CloakHQ/CloakBrowser/blob/main/js/package.json)。
- Node 包声明 Node `>=20.0.0`，Playwright peer dependency `>=1.53.0`，Puppeteer peer dependency `>=21.0.0`；Python `pyproject.toml` 声明 Python `>=3.9`、`playwright>=1.40`、`httpx>=0.24`、`cryptography>=41.0`，`serve` extra 需要 `aiohttp>=3.9` 与 `websockets>=12.0`。来源：[js/package.json](https://github.com/CloakHQ/CloakBrowser/blob/main/js/package.json)、[pyproject.toml](https://github.com/CloakHQ/CloakBrowser/blob/main/pyproject.toml)。
- 官方明确说它**不解决 CAPTCHA，也不内置代理轮换**；代理、目标网站授权、访问频率与数据合规仍由接入方负责。来源：[README — Why CloakBrowser](https://github.com/CloakHQ/CloakBrowser#why-cloakbrowser)。

### 不能从官方资料推出的内容

- 没有公开一个独立、版本化的“CloakBrowser API/HTTP automation protocol”。可复用协议是 Playwright API 或 CDP，而非 CloakBrowser 自定义 RPC。
- “通过检测站”表格是官方测试声明，不构成对任意目标站点、任意代理或任意 headless 环境的保证。README 也明确某些站点仍会检测 headless，需要 headed 模式。

## 2. 安装、启动与平台/版本

### 本地 wrapper 启动

```bash
# Python
pip install cloakbrowser
# 可选 GeoIP
pip install 'cloakbrowser[geoip]'

# Node + Playwright
npm install cloakbrowser playwright-core
# 或 Puppeteer
npm install cloakbrowser puppeteer-core
```

第一次 launch 会下载约 200MB 二进制并缓存到 `~/.cloakbrowser`；也可先运行 `python -m cloakbrowser install` / `npx cloakbrowser install`，或调用 `ensure_binary()`。来源：[README — Install/CLI](https://github.com/CloakHQ/CloakBrowser#install)、[cloakbrowser/download.py::ensure_binary](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/download.py#L174-L285)。

官方版本信息（研究日以仓库和最新 GitHub release 为准）：

- wrapper `0.5.10`：[_version.py](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/_version.py)、[js/package.json](https://github.com/CloakHQ/CloakBrowser/blob/main/js/package.json)。
- 最新可见 Pro Stable release 为 `chromium-v151.0.7922.108.3-pro`，发布时间为 2026-08-27；release 说明 Linux x64/ARM64、Windows x64、macOS ARM64/x64 均统一到 Chromium 151，并发布 `SHA256SUMS` 与 `SHA256SUMS.sig`。来源：[GitHub release API](https://api.github.com/repos/CloakHQ/CloakBrowser/releases?per_page=10)、[release 页面](https://github.com/CloakHQ/CloakBrowser/releases/tag/chromium-v151.0.7922.108.3-pro)。
- README 的平台表明确列出 Linux x86_64/arm64、Windows x86_64、macOS x86_64/arm64；不同平台可能处于不同 Chromium 版本线。来源：[README — Platforms](https://github.com/CloakHQ/CloakBrowser#platforms)。
- 可用 `browser_version` / JS `browserVersion` / 环境变量 `CLOAKBROWSER_VERSION` 精确 pin/rollback；可用 `release_channel="preview"` / `releaseChannel` / `CLOAKBROWSER_RELEASE_CHANNEL=preview` 选 Preview。版本校验只接受完整数字点号版本。来源：[README — Configuration](https://github.com/CloakHQ/CloakBrowser#configuration)、[config.py::normalize_requested_version](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/config.py#L104-L125)、[CHANGELOG 0.5.2](https://github.com/CloakHQ/CloakBrowser/blob/main/CHANGELOG.md#052--2026-07-25)。
- 下载的官方二进制会对签名的 `SHA256SUMS` 做 Ed25519 验证；官方二进制下载路径不能用 `CLOAKBROWSER_SKIP_CHECKSUM` 跳过签名验证。来源：[BINARY-LICENSE.md](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md)、[download.py::BinaryVerificationError/ensure_binary](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/download.py#L43-L50)。

### 直接使用二进制

官方包装器通过 `executable_path` 启动下载的二进制，并附加默认 stealth args；也允许 `CLOAKBROWSER_BINARY_PATH` 指向本地二进制。直接二进制可使用 `--fingerprint=<seed>`、`--fingerprint-platform` 等参数，但要自行承担参数与版本兼容。来源：[browser.py::launch](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/browser.py#L302-L383)、[config.py::get_local_binary_override](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/config.py#L292-L319)、[README — Fingerprint Management](https://github.com/CloakHQ/CloakBrowser#fingerprint-management)。

## 3. cloakserve/CDP 真实协议与端口约定

### 启动

官方 `bin/cloakserve` 是 aiohttp HTTP 服务 + `websockets` CDP 双向代理，不是 Playwright server。最小启动：

```bash
pip install 'cloakbrowser[serve]'
cloakserve                         # 默认监听 9222
cloakserve --port=9222
# Docker
# docker run -d --name cloak -p 127.0.0.1:9222:9222 cloakhq/cloakbrowser cloakserve
```

`bin/cloakserve::parse_cli_args` 默认 `port=9222`、`headless=True`、`idle_timeout=0`；`main()` 在容器中监听 `0.0.0.0`，裸机监听 `127.0.0.1`。每个 seed 的 Chromium 内部 CDP 端口从 `5100` 起分配，但这不是客户端契约；客户端只访问 multiplexer 的 9222（或自定义）端口。来源：[bin/cloakserve](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L704-L894)。

可用 `--data-dir=...` 指定 profile 根目录，`--headless=false` 开启 headed，`--idle-timeout=SECONDS` 或 `CLOAKSERVE_IDLE_TIMEOUT` 在最后一个 WebSocket 断开后回收 seed 进程；默认 `0` 表示不回收。来源：[bin/cloakserve::parse_cli_args/main](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L770-L894)、[README — Docker CDP server mode](https://github.com/CloakHQ/CloakBrowser#cdp-server-mode)。

### HTTP discovery 与 WebSocket

实际路由定义在 `main()`：

- `GET /`：健康/状态 JSON，返回 `status`, `active`, `idle_timeout`, `processes`；每个 process 包含 `pid`, 内部 `port`, `seed`, `connections`, `timezone`, `locale`, `proxy`。
- `GET /json/version`（也接受尾 `/`）：按查询参数启动或取得浏览器，代理 Chrome `/json/version`，并重写 `webSocketDebuggerUrl`。
- `GET /json/list`、`GET /json`（及尾 `/`）：按查询参数代理 Chrome target 列表，重写每个 target 的 WebSocket URL。
- `GET /devtools/{path}`：无 seed 的 CDP WebSocket。
- `GET /fingerprint/{seed}/devtools/{path}`：指定 seed 的 CDP WebSocket。
- `POST /fingerprint/{seed}/close`：立即终止指定 seed；幂等返回 `{ "seed": ..., "terminated": bool }`。当前 `ChromePool._cleanup_process()` 会调用 `_safe_rmtree()` 清理该 seed 的临时 user-data-dir；但同一源码中 `terminate_seed()`/`handle_close()` 的 docstring 又声称“persistent profile is preserved”，且当前文件没有可见的持久化 pool 子类。因此“close 后 profile 是否保留”是官方源码内部未决/需实测项，不能作为接入假设。

证据：[bin/cloakserve::handle_root/handle_json_version/handle_json_list](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L475-L620)、[bin/cloakserve::main routes](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L866-L894)。

客户端标准连接方式：

```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222?fingerprint=11111")
page = browser.new_page()
page.goto("https://example.com")
# browser.close() 只断开 CDP 客户端；cloakserve/Chrome 继续运行
```

如果客户端需要原始 WebSocket，应先请求 `/json/version` 并使用返回的 `webSocketDebuggerUrl`；官方示例是 `ws://localhost:9222/devtools/browser/<id>` 或带 seed 的 `ws://localhost:9222/fingerprint/11111/devtools/browser/<id>`。反向代理应转发 `Host`、`X-Forwarded-Host`、`X-Forwarded-Proto`，否则返回的 WebSocket host/scheme 可能指向容器内部。来源：[README — Docker CDP server mode](https://github.com/CloakHQ/CloakBrowser#cdp-server-mode)。

### 查询参数与 first-launch-wins

`parse_connection_params()` 将 query string 映射到 Chromium 参数：

- 特殊参数：`fingerprint`, `timezone`, `locale`, `proxy`, `geoip`；
- 其它参数统一成为 `--fingerprint-{key}={value}`，例如 `platform`, `brand`, `gpu-vendor`, `hardware-concurrency`；
- seed 只允许 `[A-Za-z0-9_-]{1,128}`，`__default__` 保留；非法 seed 返回 400；
- 无 seed 使用共享 `__default__` 进程；有 seed 每个唯一 seed 一个 Chromium/profile；
- 同一个 seed 已运行时，第一次连接的参数胜出，后来的不同参数只记录 warning 并忽略；
- 同一个 seed 可复用相同进程，连接例如 `http://localhost:9222?fingerprint=11111`。

证据：[bin/cloakserve::parse_connection_params](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L425-L474)、[ChromePool::get_or_launch](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L199-L298)、[README — Per-connection fingerprint seeds](https://github.com/CloakHQ/CloakBrowser#docker-compose)。

### 认证与安全

- 官方 `cloakserve` 源码没有 HTTP bearer/basic/token 认证中间件；CDP discovery 和 close endpoint 依赖网络边界。README 明确警告 CDP 可执行 JS、读取页面和访问文件，示例只绑定 `127.0.0.1`，绝不能无额外认证暴露公网。来源：[README — Docker CDP server mode / Security](https://github.com/CloakHQ/CloakBrowser#cdp-server-mode)。
- WebSocket 有 Origin 防护：`_reject_untrusted_origin()` 拒绝不可信 browser-origin，允许无 Origin 的 Playwright/Puppeteer 等客户端、`devtools://devtools`、`chrome-devtools://devtools`，以及与 loopback Host 完全匹配的 http/https Origin；不可信 Origin 返回 403。它是 CSRF 防护，不是用户认证。来源：[bin/cloakserve::_origin_is_allowed/_reject_untrusted_origin](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L44-L111)、[CHANGELOG 0.3.29](https://github.com/CloakHQ/CloakBrowser/blob/main/CHANGELOG.md#0329--2026-05-20)。
- 进程默认只绑定本机 CDP（子 Chrome 由 `--remote-debugging-address=127.0.0.1` 启动）；容器外层 9222 是否暴露由 Docker/反向代理决定。来源：[bin/cloakserve::get_or_launch](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L250-L286)。

## 4. 持久 profile 与隐私/反检测边界

### 已证实事实

- `launch_persistent_context(user_data_dir=...)` / Node `launchPersistentContext({userDataDir})` 使用真实 user-data-dir，cookies、localStorage、cache、service workers、IndexedDB 等可跨运行保存；README 将其用于保持登录、避免空 incognito profile 检测、扩展和 DRM。来源：[README — launch_persistent_context](https://github.com/CloakHQ/CloakBrowser#launch_persistent_context)、[browser.py::launch_persistent_context](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/browser.py#L554-L823)、[js/src/playwright.ts::launchPersistentContext](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/playwright.ts#L336-L431)。
- headed 默认不叠加固定 Playwright viewport；新版 headless binary 也可能使用 no-viewport，旧 headless binary 使用 `1920x947` 默认 viewport。显式 `viewport`/`no_viewport` 仍优先。来源：[browser.py::_resolve_context_viewport/_default_no_viewport](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/browser.py#L156-L220)、[js/src/playwright.ts::buildContextOptions](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/playwright.ts#L43-L118)。
- Linux 默认 wrapper persona 是 Windows；官方强烈建议安装/复制 Windows 字体；headed、residential proxy、`geoip=True`、`humanize=True` 是官方对强反爬站点的组合建议。它们不是协议要求，而是检测结果相关的运行参数。来源：[README — Font Setup on Linux](https://github.com/CloakHQ/CloakBrowser#font-setup-on-linux)、[README — Recommended config](https://github.com/CloakHQ/CloakBrowser#recommended-config-for-anti-bot-sites)。
- `humanize=True` 是 wrapper 层行为补丁，不是 Chromium/CDP 协议能力；通过独立 CDP 连接时 fingerprint patch 仍在，但必须额外导入并调用 JS `patchBrowser`/`resolveConfig` 或对应 Python human 模块。来源：[README — Framework Integrations/Humanize over CDP](https://github.com/CloakHQ/CloakBrowser#framework-integrations)、[js/src/index.ts](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/index.ts)。
- 官方二进制许可证允许组织在内部 Docker、CI、内部 artifact repository 存储并运行未修改二进制；但禁止再分发、重打包、把二进制嵌入提供给第三方，第三方客户可控制浏览器/浏览器能力或作为 hosted browser service 时需要 OEM/SaaS 单独许可。包装器源代码是 MIT；二进制不是 MIT。来源：[BINARY-LICENSE.md — Grant/Cloud, Container, OEM/SaaS](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md#cloud-container-oemsaas-license--integration-use)、[LICENSE](https://github.com/CloakHQ/CloakBrowser/blob/main/LICENSE)。

### 接入边界推断

- 本项目若只在自有 Worker 上控制浏览器并产出数据/报告，按官方许可证文字更接近允许的内部使用；若用户能直接操作、配置或管理 CloakBrowser session，则不能假设属于内部使用，应先走 OEM/SaaS 许可。这是基于许可证条款的接入判断，不是法律意见。
- 不应把 fingerprint seed、持久 profile、proxy、timezone/locale 当作普通用户输入无审计转发：它们决定可持续身份、网络出口和站点登录态。最小接入应将 seed/profile/代理配置存为受控 runtime config，并在 workflow/run 审计中记录引用而非泄露 cookie 或 license key。

## 5. License、认证与并发限制

### 已证实事实

- License key 来源优先级是显式参数 `license_key`/`licenseKey`，其次 `CLOAKBROWSER_LICENSE_KEY`，再其次 `~/.cloakbrowser/license.key`（自定义 cache dir 也支持文件）。来源：[license.py::_resolve_license_key_with_source](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/license.py#L189-L229)。
- Python wrapper 调用 `POST https://cloakbrowser.dev/api/license/validate`，JSON body 为 `{ "license_key": "..." }`，10 秒超时；成功结果读 `valid`、`plan`、`expires`，有效结果按 key hash 本地缓存 24 小时；服务器不可达时会使用 stale cache。来源：[license.py::validate_license](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/license.py#L355-L393)。
- Pro 版本解析调用 `GET https://cloakbrowser.dev/api/download/version`，携带 `X-Platform`，Preview 时带 `?channel=preview`；版本检查本地按 channel/platform 约缓存 1 小时。来源：[license.py::get_pro_latest_release](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/license.py#L395-L478)。
- `cloakbrowser info` 的 seat 查询调用 `POST https://cloakbrowser.dev/api/license/session/count`，JSON body 同样是 `license_key`，不缓存；成功返回 `active` 和可选 `limit`。网络不可达、403/429、服务端返回 active 非整数等情况分别映射为 `unreachable`、`denied`、`unknown`，不会伪造 0。来源：[license.py::get_session_seats/get_active_session_count](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/license.py#L480-L562)。
- Pro 二进制许可拒绝码在 wrapper 中映射为：76 session limit reached、77 key invalid/expired/missing、78 license server unreachable、79 local config not writable；启动握手后才发生的拒绝由二进制写入 `CLOAKBROWSER_LICENSE_STATUS_FILE`，wrapper 在下一次 page/context 调用时转换成 `CloakBrowserLicenseError`。来源：[license.py::_LICENSE_EXIT_MESSAGES/read_denial_file](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/license.py#L84-L177)、[browser.py::_install_license_guard](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/browser.py#L71-L151)。
- README/最新 release 明确免费 key 为一并发 session，Pro 按 plan 提供更高并发；实际 limit 以 license 服务返回和启动时拒绝为准，不应在本项目中硬编码。来源：[README — CloakBrowser Pro](https://github.com/CloakHQ/CloakBrowser#cloakbrowser-pro)、[GitHub release 151.0.7922.108.3](https://github.com/CloakHQ/CloakBrowser/releases/tag/chromium-v151.0.7922.108.3-pro)。
- `cloakserve` 自身没有 license HTTP auth；license 是浏览器二进制/官方下载与 session 服务的运行约束，不是 CDP endpoint 的访问控制。`--license-through-proxy` 可让部分新二进制的 license/session 请求经浏览器 proxy，但 README 标注其为 Chromium 148+ 且 Linux only for now。来源：[README — Additional Flags](https://github.com/CloakHQ/CloakBrowser#additional-flags)、[license.py](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/license.py)。

### 对接建议

- 不把 license key 作为普通 Workflow 参数、日志字段、frontend payload 或数据库明文；优先 Worker 环境变量/受控 secret，调用 `cloakbrowser info --json` 或官方 `validate_license` 做启动前诊断。
- 将 76/77/78/79 和 CDP 连接拒绝区分成 runtime readiness/error code；并发席位耗尽必须 fail closed，不能退回 stock Chrome 或无 stealth 的“兼容模式”。
- `browser.close()` 经 CDP 只断开客户端，不能释放 cloakserve 的 Chrome/seat；要释放 seed，调用官方 `POST /fingerprint/{seed}/close`，或设置 idle timeout，并在接入层确保每次租约结束都有关闭/回收策略。来源：[README — CDP server mode](https://github.com/CloakHQ/CloakBrowser#cdp-server-mode)、[bin/cloakserve::handle_close](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve#L475-L495)。

## 6. 对本项目的最小接入方案

### 现有可复用接口（本仓库事实）

- `backend/config.py` 已有 `opencli_cdp_endpoint` 默认 `http://localhost:9222`，以及逗号分隔的 `agent_pool_endpoints`。
- `backend/browser_pool.py::LocalBrowserPool` / `RedisBrowserPool` 以 endpoint 字符串为槽位，并对每个 endpoint 一次只放行一个任务；`profile_kind` 与 runtime readiness 也已有建模。
- `backend/skills/page.py` 与 `backend/agent_runtime_dispatch.py` 使用标准 `connect_over_cdp()`、`GET {endpoint}/json/list`、`GET {endpoint}/json/close/{tab_id}`、`PUT {endpoint}/json/new`。
- `backend/agent_server.py` 通过 `OPENCLI_CDP_ENDPOINT` 将 CDP endpoint 注入边缘任务；`backend/api/v1/browser_containers.py` 使用 `http://<name>:19222` 作为容器 endpoint。

这些现有调用与 `cloakserve` 的 `GET /json/list`、标准 `connect_over_cdp(http://host:9222?... )` 直接兼容。需要注意：本项目当前的 `/json/close/{tab_id}` 和 `/json/new` 是 Chrome discovery API 的兼容假设；官方 `cloakserve` 明确实现了 `/json/list`/`/json/version`/WebSocket，但源码没有自定义 `/json/close/{tab_id}` 或 `/json/new` 路由。接入前必须对 tab cleanup 做一次真实 probe，失败时不能静默吞掉清理失败。

### 建议的最小切面

1. 新增一个明确的 runtime bundle/config（例如 `cloakbrowser`），字段只包含 endpoint、seed policy、headless、profile/data-dir、release/version channel、license readiness 和 idle timeout；不要复制官方二进制到本项目仓库。
2. Worker/容器外部安装 `cloakbrowser` 与 `cloakserve`，启动后健康检查 `GET /` 与 `GET /json/version`；解析 `processes`、实际 Chromium version 和 `webSocketDebuggerUrl`，将结果登记为 runtime evidence。
3. 任务调度仍复用 `browser_pool.acquire(endpoint)`；endpoint 形如 `http://cloakserve:9222?fingerprint=<seed>`。seed 需要稳定生成/绑定到 profile，避免每次任务随机新身份；同 seed 的 timezone/locale/proxy 参数遵循官方 first-launch-wins，不能在已有进程上假装动态更新。
4. 连接使用标准 Playwright `connect_over_cdp()`；调用完 `browser.close()` 只视为“断开客户端”，另行执行官方 close endpoint 或租约/idle cleanup。对 `/json/list` cleanup 的不兼容要显式标记并用 CDP Browser/Target 命令或官方关闭 endpoint 兜底。
5. readiness 至少检查：endpoint 可达、`/json/version` 有可用 WebSocket URL、版本在批准矩阵、license/seat 可用、profile 目录可写、容器字体/显示依赖满足；任一失败就发布 `blocked/degraded`，不自动降级到普通 Chrome。
6. 第一阶段不接 `humanize=True` 语义到平台协议；如确有需要，在同一个本地 wrapper 进程中启用，或显式调用官方 human patch helper。CDP 远程接入只保证二进制 fingerprint 层。

## 7. 未知项与风险

1. 官方没有承诺 `cloakserve` 的 HTTP 路由会遵循 Chrome discovery API 的完整版本兼容矩阵；尤其 `/json/close/{tab_id}`、`/json/new` 在当前源码路由中不存在，需在目标版本做 probe。另一个必须实测的冲突是 `POST /fingerprint/{seed}/close` 的实现会清理 `user-data-dir`，而同文件 docstring 声称持久 profile 会保留；本项目不能默认 close 后身份仍可恢复。
2. GitHub release 的公开 assets 主要是 checksum/signature；Pro 实际 binary 下载由 `cloakbrowser.dev` license/download 服务决定。无法仅凭 GitHub release 推出无 key 可获取当前 Pro 二进制。
3. 官方没有公开 license 服务的完整 schema、错误码契约、seat lease 续租/释放时序或 SLA；只能按 wrapper 实际调用和错误映射实现 readiness，不能把服务当稳定公共 API。
4. 首次运行的下载、版本检查、license validate、session count、GeoIP 和可选 WebRTC exit-IP resolution 都可能产生网络访问；若 Worker 出网策略严格，必须将这些依赖列为显式 capability，不可把“二进制已在 cache”误报为“runtime ready”。
5. Chromium 151 固定 seed 在跨版本升级后可能映射到不同完整硬件身份；官方 release 建议若 seed 与持久 profile/sticky IP 绑定，升级时保留旧版本或一起轮换 seed、profile、IP。来源：[latest Pro release — Fingerprint seed continuity](https://github.com/CloakHQ/CloakBrowser/releases/tag/chromium-v151.0.7922.108.3-pro)。
6. 二进制的“隐私/反检测”是官方实现和声明，不等于目标网站允许自动化，也不等于所有环境都不泄漏；license 的 Acceptable Use 明确禁止未授权金融/医疗/政府认证访问、credential stuffing、brute force、欺诈和未经授权的数据收集。来源：[BINARY-LICENSE.md — Acceptable Use](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md#acceptable-use)。

## 8. 可验证验收标准

接入实现完成后，至少在批准平台矩阵中验证以下行为：

- `cloakserve` 以默认和自定义端口启动；`GET /` 返回 `status=ok`，`GET /json/version` 返回 `webSocketDebuggerUrl`，且 `connect_over_cdp()` 能创建 page 并完成一次导航。
- `?fingerprint=11111` 与 `?fingerprint=22222` 产生两个独立 process/seed；重复连接 `11111` 复用同一 process；对运行中的 `11111` 改 timezone/proxy 能被记录为 first-launch-wins，而不是静默改变身份。
- WebSocket 无 Origin 的 Playwright 客户端可连接；不可信 browser Origin 返回 403；未配置额外 auth 时 endpoint 只在 loopback/受控内网可达。
- `POST /fingerprint/<seed>/close` 幂等；关闭后 health 状态下降、再连接能重启；`--idle-timeout` 到期能回收进程/profile（若使用持久 pool，则验证 profile 恢复身份）。
- 本项目现有 `GET /json/list` tab snapshot 与清理流程在 cloakserve 上成功；若 `/json/close`/`/json/new` 不支持，系统返回显式 cleanup incompatibility 并使用替代清理，而不是吞掉异常。
- 持久 profile 第二次启动后 cookies/localStorage 仍存在；不同 seed/profile 不能互相读取 cookie、storage 或页面。
- 缺失/无效/过期 key、session cap、license server timeout、不可写 cache 分别映射到不同 readiness/error code；任何一种都不能悄悄退回 stock Chrome。
- 版本 pin 与 Preview 选择结果被记录为实际 resolved version/platform/channel；下载签名/sha256 校验失败时启动失败，不使用未验证 binary。
- 在本项目日志、API 响应、错误事件和数据库快照中检索不到 license key、cookie、完整 profile 路径中的敏感 token；CDP endpoint 不被公网暴露。

## 官方来源索引

- [CloakHQ/CloakBrowser README](https://github.com/CloakHQ/CloakBrowser)
- [Python launcher](https://github.com/CloakHQ/CloakBrowser/blob/main/cloakbrowser/browser.py)
- [Python download/config/license](https://github.com/CloakHQ/CloakBrowser/tree/main/cloakbrowser)
- [JavaScript package manifest and public API](https://github.com/CloakHQ/CloakBrowser/blob/main/js/package.json) · [index.ts](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/index.ts) · [playwright.ts](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/playwright.ts) · [types.ts](https://github.com/CloakHQ/CloakBrowser/blob/main/js/src/types.ts)
- [cloakserve source](https://github.com/CloakHQ/CloakBrowser/blob/main/bin/cloakserve)
- [CHANGELOG](https://github.com/CloakHQ/CloakBrowser/blob/main/CHANGELOG.md)
- [Latest Pro release API](https://api.github.com/repos/CloakHQ/CloakBrowser/releases?per_page=10) · [Latest Pro release page](https://github.com/CloakHQ/CloakBrowser/releases/tag/chromium-v151.0.7922.108.3-pro)
- [Wrapper MIT license](https://github.com/CloakHQ/CloakBrowser/blob/main/LICENSE) · [Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md)
