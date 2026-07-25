# DataFlow 内化边界与落地顺序

状态：研究完成；P0 数据算子纵切已实现，后续 domain pack 继续受本文约束。

研究基线：

- [OpenDCAI/DataFlow](https://github.com/OpenDCAI/DataFlow) `main`：
  `f62aa1349e0ff14cb737a4cbda1945d04fde85bb`
- [DataFlow-Skills](https://github.com/OpenDCAI/DataFlow-Skills)
- [DataFlow-WebUI](https://github.com/OpenDCAI/DataFlow-webui)
- [RayOrch](https://github.com/OpenDCAI/RayOrch)
- [DataFlow 技术报告](https://arxiv.org/abs/2512.16676)

这里的“内化”不是复制 DataFlow 的代码结构，也不是引入第二套 Workflow
runtime。目标是把它已经验证过的产品机制吸收到 OpenCLI Admin 现有的 typed
Workflow、Capability Catalog、Agent Control API、Run Event 和 Artifact
体系中。

## 一句话结论

DataFlow 最值得吸收的不是 Operator 数量或 Python Pipeline DSL，而是这一条闭环：

> 可发现的能力目录 + 程序化编排知识 + 共享可编辑 DAG + 编译验证 + 可替换执行器。

OpenCLI Admin 已经拥有更严格的 typed ports、reviewable patch、权限与资源 Gate、
append-only run events、artifact lineage、checkpoint 和 proposal/confirmation
边界。后续实现必须补齐“能力驱动的编排知识”，不能退回 DataFlow 的隐式 key
约定或捕获式 Python 图。

## 已落地的 P0 纵切（2026-07-25）

第一批实现没有引入第二套 Pipeline runtime，而是把 DataFlow 的通用算子形态接到
现有 Workflow 主链：

- registry：`builtin.core-data@1.0.0` Pack 注册 `generate`、`filter`、`evaluate`、
  `refine` 四类可发现算子，并同时绑定对应执行器；
- contract：`recordCandidate[] -> recordCandidate[]` typed ports、参数、产物和事件；
- compiler：catalog 与 operator kind 精确匹配，未知或错类 operator fail closed；
- runtime：保留 `normalizedData` envelope 和结构化 lineage，输出 metrics 与受限的
  rejected candidate IDs；
- composition：明确的数据清洗/质量/SFT 需求会生成可 review 的算子链，普通采集
  需求保持原拓扑；
- Canvas：动态 backend contract 优先，静态 fallback、参数界面和中英文展示同步。

这是一条可以继续增加 domain operator 的权威扩展缝，不代表已经移植 DataFlow 的
全部 Operator。下一阶段仍按下文顺序推进 capability-driven demand planning、
composition knowledge 与更多有业务验收标准的 domain packs。

## DataFlow 的真实模型

### 1. Pipeline 是捕获出来的，不是独立图定义

`PipelineABC.compile()` 临时把 Pipeline 上的 Operator 替换成 `AutoOP`，执行一次
`forward()` 来记录调用，然后生成 `OperatorNode` 和 `KeyNode`。运行时再按捕获顺序
调用真实 `operator.run()`。

优点是 Python 用户几乎没有额外样板；代价是图契约依赖：

- Pipeline 属性；
- `forward()` 的一次捕获执行；
- `input_*` / `output_*` 参数命名；
- storage 中当前可见的 key。

它主要验证 key 是否在前序步骤出现，不提供 OpenCLI Admin 当前具备的 typed-port、
permission、resource、artifact、event-shape 和 readiness 合同。

### 2. Operator、Prompt、Serving、Storage 是四个替换点

- Operator：最小 `run(storage, ...)` 抽象，注册表按类名发现。
- Prompt：Prompt 类可以被 Operator 白名单约束，也允许 DIY Prompt。
- Serving：API、本地模型、VLM、embedding、RAG 等后端可替换。
- Storage：文件、延迟文件、内存、MyScale、batch、stream 等实现可替换。

这个分层意图值得吸收，但 DataFlow 的 nominal ABC 并不总是严格一致。例如部分
Serving 实现是 async，基础合同仍是 sync；embedding serving 也不能满足普通文本
生成语义。OpenCLI Admin 应继续使用 action-specific runtime contracts，不建立一个
过宽的统一 executor 接口。

### 3. 数据通过 step cache 前进

Operator 读取 storage 当前 step，写入下一 step；batch/stream Pipeline 额外记录
成功批次以便恢复。这个模型适合线性数据清洗，但 provenance 主要由 step 和 key
位置隐式表达。

OpenCLI Admin 的 Run Event、Artifact Reference、Lineage、Checkpoint、
idempotency 和 CAS 聚合更适合有分支、外部副作用、人工介入和跨 run 恢复的控制面。
因此只能吸收“节点边界必须可恢复”的意图，不能引入共享可变 step counter 作为
权威状态。

### 4. Agent 的能力来自 Harness，不在 DataFlow core

DataFlow core 仓库没有完整的 DataFlow-Agent 实现。公开生态把 agent 能力拆成：

- Skills：告诉 agent 如何选 Operator、填 schema、组 Pipeline；
- MCP：提供实时 Operator registry 和 pipeline state；
- WebUI：让 agent 生成的流程成为持久、可编辑的可视 DAG；
- validation：检查图结构和 schema。

DataFlow 的关键经验是把“程序化知识”和“实时工具事实”分开。Skills 不应复制
catalog；MCP 也不应承载编排策略。

## 与 OpenCLI Admin 的对应关系

| DataFlow 机制 | OpenCLI Admin 现状 | 决策 |
| --- | --- | --- |
| Python `forward()` 捕获 Pipeline | `WorkflowProject` + 后端 authoritative compiler | 拒绝移植 |
| `input_*` / `output_*` key 约定 | typed ports + compatibility validation | 保留现状 |
| Operator registry | capability catalog、runtime registry、node catalog | 吸收“实时可发现”，合并事实来源 |
| DataFlow-Skills | browser skill 的 record → distill → execute → correct；尚缺 Workflow composition knowledge | 新增独立的编排知识层，不能混成 browser skill |
| WebUI shared DAG | Studio Canvas + reviewable Workflow patch | 保留并强化 |
| MCP live registry/state | Agent Control API，MCP 作为 adapter | 按 ADR-0012 实现，不让 MCP 绕过 proposal/gate |
| Storage step cache | artifacts、events、checkpoint、typed references | 只吸收恢复语义 |
| Serving replacement | runtime binding + action-specific contract | 保留现状 |
| Ray accelerated operator wrapper | runtime executor/fleet dispatch | 只对 stateless、row-independent 节点适配 |

## 当前最重要的真实缺口

`backend/workflow/demand_assembler.py` 虽然已经输出可 review 的 native-node patch，
但 `_source_slots_for_need()` 仍只用关键词硬编码小红书和哔哩哔哩。这还不是
Runtime-Aware Plan Drafting，也没有利用现有 capability/runtime/resource metadata。

这个缺口的上游原因是同一 capability 的事实仍分散在 backend compiler port
contracts、runtime contracts、runtime registry、backend node registry 和 frontend
node contracts 中。仓库已经通过
`backend/workflow/capability_projection.py::build_workflow_capabilities()` 和
`/api/v1/workflows/capabilities` 聚合 runtime contract、binding、readiness、
resources 和 OpenCLI adapter registry；frontend 也已优先消费该投影。真正缺少的是
把这条现有投影固化为权威路径，并逐步消除 compiler/frontend 的 fallback 副本。
不能让 demand assembler 再读取一组手写事实。

此外，`frontend/app/api/generate-workflow/route.ts` 和
`frontend/lib/flow/local-generate.ts` 仍生成一套较浅的通用节点对象，没有天然进入
`demand_assembler → patcher → compiler → explicit accept` 主路径。这是 agent
composition 的第二种语义，必须收口，不能在增加编排知识后继续保留旁路。

因此第一优先级不是增加 Operator，不是移植 DataFlow Pipeline，也不是再做一个
Canvas，而是建立单一能力投影，让所有 demand/agent drafting 从它选择、组合和解释
节点，并统一产出 `WorkflowPatchOperation`。

同时，OpenCLI Admin 当前有三类相关但不能混淆的知识：

1. capability/runtime contract：系统此刻能做什么；
2. Workflow composition knowledge：怎样把能力组合成可验证的 Workflow；
3. browser skill：怎样在具体页面上完成一段交互。

DataFlow 的 Skills/MCP 分离证明第 1 和第 2 类必须解耦；OpenCLI Admin 还要继续把
第 3 类限制在 browser execution 边界内。

## 必须保持的不可退化边界

后续任何 DataFlow 内化实现都必须满足：

1. `WorkflowProject` 是唯一 authoring graph；不增加第二种本地 Pipeline IR。
2. backend compiler 是运行前的权威验证器；前端预览不能产生真实结果。
3. agent 只能生成 reviewable patch/proposal，不能直接注入 executor 或运行参数。
4. capability、binding、permission、resource 和 readiness 缺失时 fail closed。
5. runtime 只接收已经解析的引用和 ephemeral grants，不在节点中持久化 cookie、
   profile、worker 或 secret material。
6. node lifecycle、tool calls、artifact refs、checkpoint 和 side effects 继续进入同一
   append-only event/evidence spine。
7. 外部执行器或加速器必须位于 runtime binding 后面，不改变 Canvas node 合同。
8. 同步、异步、batch、stream 能力要显式声明，不能依赖一个过宽 ABC 的名义兼容。

## 最小落地顺序

### Slice 1：固化现有 Capability Projection

扩展并规范现有 `build_workflow_capabilities()` 和
`/api/v1/workflows/capabilities`，不新建第二套 manifest。投影至少稳定覆盖：

- capability id、typed ports 和参数；
- runtime binding 和 execution mode；
- output artifacts、events、permissions、resources 和 limits；
- readiness/certification；
- Canvas 所需的稳定 metadata。

它是现有事实的统一投影，不是新的 Operator 基类，也不改变执行行为。frontend
已经优先消费 runtime contract；下一步是让 compiler、agent read API 和其余静态
fallback 逐步收敛到同一权威定义。

验收：同一 capability 的 port/type/binding/readiness 只需修改一个权威定义；
现有 `test_workflow_capabilities_api.py` 继续验证 ports、binding、permissions、
resources 和 readiness，`test_capability_exposure_matrix.py` 继续验证引用闭包与
secret 不泄漏，并增加生成检查发现 backend/frontend fallback 漂移。

### Slice 2：能力目录驱动的 demand draft

把 `_source_slots_for_need()` 的站点关键词表替换成对现有 capability projection、
runtime contract、saved source/preset 和 resource readiness 的查询。编排器输出：

- 命中的 capability 和依据；
- reviewable `WorkflowPatchOperation`；
- 缺失 capability/resource 的稳定 reason；
- backend compile preview。

验收：增加一个新 source capability 时，不修改 demand assembler 的 Python
分支即可被 draft 发现；未知需求仍返回 `request_missing_capability`，不编造节点。

### Slice 3：Workflow composition knowledge

建立一组小而可审查的组合规则，描述“何时选什么能力、常见拓扑、必需 Gate、
失败恢复和验证步骤”。它只引用稳定 capability id 和 contract 字段，不复制当前
可用性、凭据或 worker 状态。

优先覆盖已有主路径：

- collect → normalize → merge → accept → records；
- collect → evaluate/filter/refine → accept；
- source fanout → lineage-preserving merge；
- review/approval → governed sink。

验收：同一需求在能力目录未变化时得到确定性结构；能力被 blocked/removed 后，
知识层不能让它伪装为 runnable。

### Slice 4：统一 Agent composition 与 Control API Harness

先让通用 `/generate-workflow` 和本地 generator 不再产生第二套 graph 语义；所有
agent composition 统一输出 `WorkflowPatchOperation`，进入
`patcher → compiler → explicit accept`。

向 first-party/external agent 暴露只读 capability/contract/resource-summary 和
draft/compile/proposal 能力。MCP/SDK 只做 adapter：

1. 读取实时目录；
2. 使用 composition knowledge 规划；
3. 创建 patch preview；
4. backend compile；
5. 生成带 base revision 的 Agent Operation Proposal；
6. 通过既有确认和 Gate 应用。

验收：agent 和 Canvas 使用同一个 Workflow draft、revision、compile result 和 run
projection；不存在 MCP 私有 mutation path。

### Slice 5：有实际吞吐证据后再增加可替换执行

在 runtime binding/fleet dispatch 后增加执行策略，而不是包装 authoring node。
仅对 contract 明确声明 stateless、row-independent、bounded-output 的节点允许
parallel map / micro-batch；merge、global dedupe、side-effect sink 和有 session
affinity 的浏览器节点不得透明并行。

验收：串行和加速执行产生相同 artifact contract、lineage、event ordering 约束和
failure semantics；加速器关闭后无需修改 Workflow。

在 profiler、queue metrics 或真实 workload 证明本地执行是瓶颈前，不实现
distributed adapter。DataFlow/RayOrch 只提供设计参考，不构成提前建设理由。

## 明确不做

- 不 vendor 或 fork DataFlow core。
- 不新增 DataFlow 兼容 Canvas 或 Python `forward()` DSL。
- 不用 `input_*` / `output_*` 命名代替 typed ports。
- 不把完整 DataFrame/JSON body 放进 run events。
- 不把 DataFlow-Skills 直接塞进 browser `skill` channel。
- 不为“将来可能用”先建统一 Operator/Prompt/Serving/Storage 基类。
- 不先追求 Operator 数量；能力是否可运行由 contract、fixture、gate 和 readiness
  共同决定。

## 验证依据

DataFlow 侧交叉检查了 Pipeline compile/runtime、AutoOP、nodes、Operator、
Prompt、Serving、registry、Storage、Ray wrapper、scaffold 和测试目录。静态代码图
覆盖 488 个文件、1,418 条 import edge、1,510 条 call edge、124 条 inheritance
edge。Sentrux 的项目规则门未执行成功，因为上游仓库没有
`.sentrux/rules.toml` 和 `.sentrux/baseline.json`；这不构成上游代码质量结论。

OpenCLI Admin 侧对照了：

- `backend/workflow/compiler.py`
- `backend/workflow/capability_projection.py`
- `backend/workflow/demand_assembler.py`
- `backend/workflow/node_registry.py`
- `backend/workflow/runtime_contracts.py`
- `backend/workflow/opencli_hda_tracer.py`
- `backend/workflow/workflow_run_events.py`
- `frontend/lib/workflow/canonical-node-contract.ts`
- `frontend/lib/workflow/run-artifacts.ts`
- ADR-0009、ADR-0010、ADR-0012、ADR-0025
- `tests/integration/test_workflow_capabilities_api.py`
- `tests/unit/test_capability_exposure_matrix.py`

这些现有边界已经覆盖 DataFlow core 没有解决的治理、资源、并发编辑、事件、
artifact 和副作用问题，后续工作应集中在编排知识和实时能力发现，不重写运行脊柱。
