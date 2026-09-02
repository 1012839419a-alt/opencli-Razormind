---
title: '为采集流水线增加受治理的 PAW 本地富化运行时'
type: 'feature'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'c5804809f2688b110eaac4d9aabe1e3312b5d1d1'
context:
  - '{project-root}/_bmad-output/planning-artifacts/prds/prd-snailfish-2026-08-28/addendum.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 高频短文本分类/提取缺少低成本离线路径；直接使用公共 Hub 或在主 API 加载 llama.cpp 又有供应链、隐私和隔离风险。

**Approach:** 增加 `processor_type="paw"`，让现有流水线调用只执行固定程序的本地 sidecar；短文本通过身份、契约和 JSON Schema 验证后才持久化。

## Boundaries & Constraints

**Always:** 复用处理器注册表和 `process_with_ai`；sidecar 固定 `program_id`、默认离线、串行、有界 JSON 输出；健康信息暴露身份和就绪状态；容器非 root、只读、内部网络；错误记录不标记 `ai_processed`。

**Ask First:** 联网准备模型、切换程序、提高并发、传入原始浏览器数据/凭据/完整 HTML、设为默认处理器。

**Never:** 提供编译、Hub 自动安装或任意程序入口；向 PAW 托管服务发送生产数据；在 API/Celery 进程加载 PAW；失败时伪造成功或切换模型。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 正常 | 固定程序、短 prompt | 匹配身份的 JSON object 写入 `ai_enrichment` | N/A |
| 身份/契约错配 | 响应 ID/version 不符 | 拒绝且记录保持原状态 | 稳定错误码，不计成功数 |
| 非法输出 | 非 object、过大或 schema 不符 | 不写入富化 | 返回验证错误 |
| 不可用 | 缓存缺失、超时、连接/加载失败 | 健康 not-ready；同批其他记录继续 | 失败记录保持未富化 |
| 超长 | prompt 超限 | 推理前拒绝 | 413/422，不隐式截断 |

</frozen-after-approval>

## Code Map

- `backend/processors/external_http_processor.py`, `backend/processors/registry.py` -- guarded HTTP、逐记录容错和注册模式。
- `backend/processors/paw_processor.py`, `backend/pipeline/ai_processor.py:135-145` -- PAW 验证及真实成功状态。
- `compat/kats_runtime/app.py`, `compat/paw_runtime/` -- 复用 sidecar 边界并新增 PAW 0.4.4 离线服务、镜像和合同测试。
- `docker-compose.yml` -- opt-in profile、只读缓存、内部网络和健康检查。
- `frontend/components/agents/agent-form-dialog.tsx`, `frontend/app/(app)/agents/page.tsx`, `frontend/lib/api/types.ts` -- PAW 类型和安全配置提示。

## Tasks & Acceptance

**Execution:**
- [x] `compat/paw_runtime/` -- 实现 `/health`、`/v1/enrich`、离线固定程序、串行推理和有界 JSON 输出。
- [x] `backend/processors/paw_processor.py`, `backend/processors/registry.py`, `backend/config.py` -- 实现 HTTP adapter、身份/schema 验证和默认 URL。
- [x] `backend/pipeline/ai_processor.py` -- 错误结果保持未富化并返回准确成功数。
- [x] `docker-compose.yml` -- 增加隔离、默认关闭的 PAW sidecar 和只读缓存挂载。
- [x] Agent 前端文件 -- 增加 PAW 选择、标签和配置示例，不增加编译/Hub UI。
- [x] 聚焦测试 -- 覆盖矩阵全部场景及配置往返。

**Acceptance Criteria:**
- Given 已固定的本地 PAW 程序，when 标准化记录进入 `paw` Agent，then 验证后的 object 持久化为 `ai_enrichment`。
- Given 部分响应失败，when 批处理结束，then 失败记录保持未富化，其他记录成功且计数准确。
- Given 未启用 `paw` profile，when 运行现有服务，then 启动和行为不变。
- Given 操作者配置 PAW，when 查看 UI/健康信息，then 可识别程序和离线就绪状态，且无编译/Hub 安装入口。

## Spec Change Log

- 2026-08-28：sidecar 从通用子进程入口改为固定的 `programasweights==0.4.4` SDK；仅以 `paw.function(program_id, offline=True)` 加载环境固定程序，并以 `paw.is_offline_ready` 报告只读缓存就绪状态。移除了可执行文件路径约定，禁止编译、联网回退和任意入口。
- 2026-08-28：收紧 sidecar 仅本地 URL、敏感占位符、流式响应和 PAW Agent 配置边界；SDK callable 缓存复用且超时后 fail-closed。无经批准只读 `.paw` 缓存时，真实运行时保持 `503 not_ready`，不尝试准备、下载、编译或远程推理。

## Design Notes

契约固定为 `opencli.paw.runtime.v1`：请求含配置的 `programId`、渲染后 `input`、有界 `maxTokens`；响应含同一 ID、契约版本和 `enrichment` object。sidecar 只加载环境固定程序，ID 不匹配直接拒绝。默认 `PAW_OFFLINE=1`，缓存由操作者只读挂载；联网准备属于独立运维动作。

## Verification

**Commands:**
- `pytest -q compat/paw_runtime/tests` -- sidecar 合同和边界通过。
- `pytest -q tests/unit/test_paw_processor.py tests/unit/pipeline/test_ai_processor.py tests/integration/test_agents_api.py` -- adapter、状态和配置合同通过。
- `npm --prefix frontend run lint && npm --prefix frontend run build` -- Agent UI 通过检查。
- `docker compose --profile paw config` -- 隔离服务可解析且默认 profile 不启用。

**Executed:**
- `uv run ruff check ...` — PAW 新增/修改的 Python 文件全部通过。
- `uv run pytest --no-cov -q compat/paw_runtime/tests tests/unit/test_paw_processor.py tests/unit/pipeline/test_ai_processor.py tests/integration/test_agents_api.py` — 49 passed。
- `npm --prefix frontend run lint` — 0 errors；2 条既有无关 warning。
- `npm --prefix frontend run build` — Next.js 生产构建通过。
- fresh 3100 端口运行 `paw-agent.spec.mjs` — 1 passed，覆盖 PAW 选择、说明、空提示词阻断和合法配置提交。
- `docker compose --profile paw build paw-runtime` — 镜像构建通过；PAW SDK 与 llama wheel 均校验 SHA-256。
- `API_AUTH_TOKEN=test-token docker compose --profile paw config` — profile、内部网络、只读缓存和健康检查可解析；默认 services 不含 sidecar。
- 真实容器在未配置 `PAW_PROGRAM_ID`/缓存时 `/health` 返回 `503 not_ready`，不使用伪造程序 ID、不联网回退。

## Suggested Review Order

**受治理的后端入口**

- 仅传递渲染后的标准化短文本，并逐条隔离失败。
  [`paw_processor.py:135`](../../backend/processors/paw_processor.py#L135)

- 仅持久化已验证成功的富化结果。
  [`ai_processor.py:142`](../../backend/pipeline/ai_processor.py#L142)

**固定离线运行时**

- 首次离线加载后缓存官方 PAW callable，串行复用于后续记录。
  [`engine.py:87`](../../compat/paw_runtime/engine.py#L87)

- 健康返回真实就绪状态，推理不阻塞事件循环。
  [`app.py:122`](../../compat/paw_runtime/app.py#L122)

**部署隔离与操作界面**

- 以 opt-in profile 隔离只读、非特权的内部 sidecar。
  [`docker-compose.yml:146`](../../docker-compose.yml#L146)

- PAW 选择说明固定离线边界并要求短提示词。
  [`agent-form-dialog.tsx:201`](../../frontend/components/agents/agent-form-dialog.tsx#L201)

**回归覆盖**

- 验证 sidecar 身份、边界、并发与固定调用合同。
  [`test_contract.py:61`](../../compat/paw_runtime/tests/test_contract.py#L61)

- 验证 adapter 契约、拒绝路径及批次连续性。
  [`test_paw_processor.py:78`](../../tests/unit/test_paw_processor.py#L78)
