# CloakBrowser 兼容接入设计

## 目标

让 OpenCLI Admin 的内置 Chrome 运行时可以显式选择 CloakBrowser 二进制，同时保留现有 CDP、Browser Bridge、持久 Profile、noVNC、runtime bundle 和浏览器池租约语义。默认行为必须继续使用现有 Chromium。

## 依据

- `docs/research/2026-09-02-cloakbrowser-compatibility.md`
- `chrome/entrypoint.sh`
- `chrome/Dockerfile`
- `backend/browser_pool.py`
- `backend/channels/opencli_channel.py`
- `backend/api/v1/browser_containers.py`

CloakBrowser 官方提供定制 Chromium 二进制和 Playwright/Puppeteer 包装器；现有后端不直接使用 Playwright，而是通过 CDP/Bridge 驱动 OpenCLI。因此第一阶段只接入兼容的浏览器可执行文件，不把包装器引入后端。

## 方案

### 引擎选择

Chrome 镜像新增显式引擎配置：

- `BROWSER_ENGINE=chromium|cloakbrowser`，默认 `chromium`。
- `CLOAKBROWSER_VERSION` 固定可复现的 wrapper/binary 版本。
- `CLOAKBROWSER_BINARY_PATH` 可覆盖为已安装的本地二进制。
- `CLOAKBROWSER_CACHE_DIR` 指向容器内可写缓存。
- `CLOAKBROWSER_LICENSE_KEY` 仅作为运行时 secret 传入，不写入镜像、数据库、前端 payload 或日志。

构建 CloakBrowser 变体时安装官方包并预热已验证的二进制缓存；容器启动时通过官方 `ensure_binary()` 解析实际可执行文件，使有效 Pro key 可以更新到授权版本。没有 key 时使用已缓存的免费版本。二进制校验失败或授权失败必须启动失败，禁止静默退回 stock Chromium。

### 启动边界

`chrome/entrypoint.sh` 保持现有生命周期，只在 `start_chrome()` 前解析 `CHROME_BIN`：

- `chromium` 引擎使用现有系统 Chromium。
- `cloakbrowser` 引擎使用 `CLOAKBROWSER_BINARY_PATH` 或官方缓存解析结果。

以下参数和流程不变：

- Xvfb、x11vnc、noVNC、nginx CDP 代理。
- runtime bundle 的 allowlisted extension 目录。
- `/home/chrome/.config/chromium` 持久 Profile。
- 启动页、网络策略、`9222` CDP 和 `19222` 代理端口。
- Browser Bridge daemon、runtime self-check、崩溃重启。

不采用 `cloakserve` 作为第一阶段实现。它的 seed 子进程、临时 profile、first-launch-wins 参数语义、`browser.close()` 不释放服务端 session，以及缺少项目现有 `/json/close/{tab_id}` 和 `/json/new` 路由，都会改变当前池和 profile 生命周期；这些应另立兼容性项目。

### 上层兼容

不修改 `browser_pool`、`OpenCLIChannel`、agent HTTP/WS 协议或数据库 schema。所有现有 endpoint 仍指向 `http://<container>:19222`，OpenCLI 继续按 `bridge`/`cdp` 选择连接方式。动态创建的浏览器实例复用已经构建好的 Chrome 镜像变体。

## 错误与安全

- `BROWSER_ENGINE` 只允许 `chromium` 或 `cloakbrowser`；未知值必须 fail closed，并输出不含 secret 的诊断。
- CloakBrowser 路径不存在、缓存不可写、官方二进制下载/签名校验失败、license/session cap/服务不可达都必须阻止 CloakBrowser 启动。
- CloakBrowser 不可用时不自动降级为普通 Chromium，避免调用方误以为仍有 stealth 能力。
- license key 不得出现在进程日志、API 返回、数据库快照和 runtime report 中。
- 现有 CDP 端口安全边界不变：仅 loopback/受控 Docker 网络暴露，不新增公网入口。
- 文档明确：CloakBrowser 不负责 CAPTCHA 求解或代理轮换；CDP 接入获得二进制级能力，不自动获得 wrapper 层 `humanize=True`。

## 文件范围

预期修改：

- `chrome/Dockerfile`
- `chrome/entrypoint.sh`
- `docker-compose.build.yml`
- `docker-compose.yml`
- `.env.example`
- 与 Chrome 启动选择直接相关的单元/脚本测试
- 必要的现有 README/运行文档段落

不修改：

- `backend/browser_pool.py`
- `backend/channels/opencli_channel.py`
- `backend/models/browser.py`
- `backend/schemas/browser.py`
- CloakBrowser 官方源码或二进制

## 验收标准

1. 默认构建/启动路径仍使用系统 Chromium，现有 CDP healthcheck 和 Bridge 能力不回归。
2. CloakBrowser 变体能启动，`GET /json/version` 返回可用 CDP discovery，现有 `/json/list`、OpenCLI CDP 采集和 runtime self-check 能工作。
3. CloakBrowser 可使用自定义 `CLOAKBROWSER_BINARY_PATH`；缺失路径、未知引擎、校验失败均返回明确失败且不 fallback。
4. 容器重启后持久 Profile 中的 cookies/localStorage 仍存在，扩展和 runtime bundle 自检仍通过。
5. 运行时 license secret 不出现在日志和 API/runtime report；license/缓存错误可观察且不被吞掉。
6. 修改有针对性测试或可执行 smoke check，验证引擎解析、启动参数选择和 fail-closed 行为。

## 非目标

- 在后端新增 Playwright/CloakBrowser wrapper provider。
- 第一阶段实现 `cloakserve` 多 seed CDP 服务或跨任务 fingerprint 管理。
- 实现 CAPTCHA 求解、代理轮换、自动 GeoIP、humanize 行为层。
- 修改工作流、站点绑定、浏览器池调度模型。
