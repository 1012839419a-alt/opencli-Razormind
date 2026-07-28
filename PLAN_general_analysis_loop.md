# 通用 Deep Research / Analysis：研究闭环与 A 股盘前 PTT

## 目标

交付一个真实可运行、可审计、严格有界的研究闭环：

```text
ResearchBrief
  -> 多源 EvidenceBatch / recordCandidate
  -> Claim Projection
  -> Coverage Audit
  -> Counter Thesis
  -> Scenario Simulation
  -> Revision Diff
  -> Publish Gate -> Existing Record Acceptance / Sink
  -> ResearchRevision
  -> approved collect_more -> immutable child WorkflowRun
```

- A 股盘前研究是首个 PTT；通用算子不写入 A 股字段，垂直场景只存在于可导入 Workflow fixture。
- Workflow 图保持 DAG；不在编译图中制造反馈边。
- `Coverage Audit` 输出 `finalize | collect_more | stop_incomplete` 和有界 Collection Proposal。
- 补搜需显式调用 research continuation API；每轮创建不可变子 Run，服务端推进预算并复用父图快照。
- 每个 Claim 必须绑定当前 Run 的 EvidenceBatch 和稳定 Evidence ID；反方结论与修订保留可追溯 Evidence ID。
- 首轮复用现有 Workflow Compiler、Runtime Registry、Capability Catalog、WorkflowRun/Event、EvidenceBatch、Data Operator 和 AgentDrawer proposal 链路。
- 合成测试证明跨 Run 补搜闭环；A 股 PTT 证明 2026-07-28 官方源快照可走完整通用链，仍不冒充持续在线采集。

## 首轮非目标

- 不宣称“任意网页”已经达到生产可用。
- 不新增数据库表、队列、向量库、依赖或另一套 Artifact/Run 系统。
- 不实现后台无限循环或动态改图。
- 不允许 Agent 绕过 Capability/Runtime/权限 Gate。
- 不包含交易、下单、通知、发帖等外部写操作。
- 不把 A 股字段、日报格式或交易策略写进通用算子。

## 最小契约

首轮继续使用 `recordCandidate[]`。研究结构写入
`recordCandidate.normalizedData`，并保留原有 lineage。

### EvidenceRef

```json
{
  "evidenceId": "stable source item id",
  "itemKey": "item key inside the EvidenceBatch",
  "batchId": "current-run EvidenceBatch id",
  "runId": "current workflow run id",
  "nodeId": "EvidenceBatch producer node",
  "manifestUri": "EvidenceBatch detail endpoint",
  "odpRef": "stable ODP batch reference",
  "sourceId": "optional source id",
  "url": "optional source URL"
}
```

只引用 Batch 而不引用单条 Evidence 不能支撑 Claim。

### Claim

```json
{
  "claimId": "stable hash",
  "statement": "claim text",
  "disposition": "supported|contradicted|mixed|unverified",
  "supportingEvidenceIds": [],
  "contradictingEvidenceIds": [],
  "qualifyingEvidenceIds": [],
  "evidenceIds": [],
  "evidenceRefs": [],
  "dimensions": []
}
```

### CoverageReport

```json
{
  "claimSetHash": "fingerprint of the exact audited claim set",
  "semanticClaimSetHash": "fingerprint excluding run-local EvidenceRef locations",
  "requiredDimensions": [],
  "coveredDimensions": [],
  "gaps": [],
  "satisfied": false,
  "decision": "finalize|collect_more|stop_incomplete",
  "stopReason": "coverage_satisfied|max_iterations_reached|max_additional_collections_reached",
  "continuationProposal": {
    "proposalId": "stable id",
    "action": "collect_more",
    "gaps": [],
    "nextIteration": 2,
    "nextAdditionalCollectionCount": 1
  }
}
```

### CounterThesis

```json
{
  "counterThesisId": "stable hash",
  "statement": "contrary or qualifying evidence summary",
  "targetClaimIds": [],
  "evidenceIds": []
}
```

### ResearchRevision

```json
{
  "claimSetHash": "fingerprint of the exact revised claim set",
  "scenarioSetHash": "fingerprint of scenario assessments",
  "added": [],
  "changed": [],
  "removed": [],
  "evidenceIds": []
}
```

## 有界执行与后续闭环

当前实际强制：

- `maxIterations <= 5`
- `maxAdditionalCollections <= 3`
- `iteration` 不得超过 `maxIterations`
- `additionalCollectionCount` 不得超过 `maxAdditionalCollections`
- Workflow Compiler 沿用现有 DAG 环检测，不允许反馈边
- Demand Draft 受现有双输入 merge 契约约束，一次最多组装两个 source
- Coverage 只输出有界决策：`finalize | collect_more | stop_incomplete`
- Publish Gate 要求当前 Claim 集合的 Coverage/Revision 指纹一致，并且每个 Evidence ID 有当前 Run 的 EvidenceRef
- continuation 每次最多 200 个新增 evidence item / 2 MiB
- 单个 ledger 最多累计 1000 个 evidence item / 8 MiB
- continuation 只接受现有 source node ID，不接受客户端 project 或预算覆盖
- 相同 idempotency key 重放同一个子 Run；不同输入冲突关闭
- 重复证据不创建子 Run；语义 Claim 集与 coverage gaps 无进展时 ledger 标记 `no_progress`
- `maxGraphMutations = 0`，子 Run 只更新 Coverage/Revision 的运行态配置

Agent 权限边界：

1. 读取 Capability Catalog 和上一轮 Run/Event/EvidenceBatch。
2. 提议新增或调整 source、研究算子配置。
3. 提交 Workflow patch preview。
4. 只有显式 continuation 调用可把已批准 `sourceOutputs` 带入下一轮；不会自动选择任意网站。

## 分布式工作包

所有 Agent 共用工作树；每个文件只有一个 owner，任何人不得回滚别人的修改。

| 工作包 | Owner | 文件范围 | 依赖 | 交付 |
|---|---|---|---|---|
| WP0 架构与边界 | Lead/Architect | 本计划 | 无 | 目标、契约、停止条件 |
| WP1 研究算子 | Research semantics Agent | `backend/workflow/research_operators.py`、最小注册改动 | WP0 | Claim、Coverage、Counter、Scenario、Revision、Publish Gate |
| WP2 单元与集成 | Test Agent | 新增 research 专用测试 | WP1 契约 | 确定性、预算、DAG/API 运行 |
| WP3 前端入口验收 | Frontend Agent | Run Trace 与 API proxy | 现有 UI | Revision Ledger、EvidenceRef、补搜输入与子 Run |
| WP4 编排入口 | Backend Agent | 需求组装/HDA 的最小接入文件 | WP1、WP2 | Agent 可组装研究节点 |
| WP5 独立审查 | Critic/Verifier | 只读 | WP1-WP4 | 范围、证据链、测试复核 |

当前用户已有改动必须保留，首轮避免触碰：

- `backend/api/v1/nodes.py`
- `backend/workflow/opencli_adapter_nodes.py`
- `tests/unit/test_opencli_adapter_nodes.py`
- `tests/unit/test_realtime_market_executor.py`

## 验收

1. `builtin.research@1.0.0` 在现有 Capability Catalog 中可发现并有真实 runtime binding。
2. 六个研究算子可作为现有 data-operator 节点编译、执行和记录 metrics。
3. 相同输入得到相同 Claim ID、Evidence ID、Coverage、Counter Thesis 和 Revision Diff。
4. 每个可发布 Claim 的 EvidenceRef 都绑定当前 Run 的 EvidenceBatch；旧 Coverage/Revision 指纹不能解锁 Gate。
5. 缺引用 Claim 是 `unverified`；Coverage 的成功、`collect_more` 决策和预算终止路径都有算子测试。
6. Publish Gate 的通过和阻断两条路径都跑过 Existing Record Acceptance / Sink；阻断路径写入零条研究记录。
7. 合成跨源研究证据可跑三轮不可变 Run，预算、幂等、重复证据拒绝和 ledger ancestry 可验证。
8. Agent 修改仍是 proposal-only；接受前不应用 patch。
9. 无新依赖、无迁移、无外部写操作。
10. 可导入的 A 股盘前 Workflow 使用上交所休市/公告、深交所公告和国家统计局发布四类官方证据快照，逐 Claim EvidenceRef 可导航。

目标命令：

```powershell
uv run pytest tests/unit/test_research_operators.py tests/unit/test_data_operators.py --no-cov -q
uv run pytest tests/integration/test_workflow_deep_research_api.py --no-cov -q
uv run pytest tests/integration/test_a_share_premarket_research_ptt.py --no-cov -q
uv run pytest tests/integration/test_dataflow_operator_pipeline_api.py tests/integration/test_workflow_patch_api.py --no-cov -q
```

持续在线 A 股 PTT 仍需把四个已核验官方端点物化为已批准的只读 source capability，
并记录限速、抓取时间、HTTP 元数据与截断。当前仓库验收是 2026-07-28
`verified_snapshot`，不会把 fixture 冒充持续在线采集。
