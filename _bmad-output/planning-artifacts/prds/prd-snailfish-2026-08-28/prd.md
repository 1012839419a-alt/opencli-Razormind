---
title: OpenCLI 可编程 Agent 平台：高吉星实时业务闭环（首个生产用例）
status: final
created: 2026-08-28
updated: 2026-08-28
---

## Executive Summary

本产品将 OpenCLI 定义为面向 Agent 的**可编程运行平台**，而非单一浏览器工具：使用者应能在产品内发现可用能力、看到其真实运行条件，并把合适的能力带入工作流。

高吉星 Live Business Chain 是这一平台的首个生产用例。系统自身通过实时或定时 keyword collection 完成 Observe → Orient → Decide → Act 的 OODA 闭环：真实浏览器/OpenCLI 调用 Doubao，处理可归因问题包，保留答案、引用与会话证据的血缘，经 normalize → accept → sink 后交给 geoXI 对应项目持久化、查询和分析；仅当 geoXI 返回与 delivery identity 匹配的消费回执时，才判定该投递业务成功。P1 的目标是让这一用例出现在正确的平台操作上下文中；它不是营销首页复制，也不将长期平台愿景误写成本期承诺。

## Product Vision

让 Agent 能力从“存在于某个适配器或命令中”变成可发现、可判断是否真实可用、可投入工作流并可审计其业务结果的产品能力。平台以真实运行事实为准：浏览器、登录、配置、运行绑定和业务确认均应被清楚区分。

平台自身应能围绕实时与定时 keyword collection 完成可观察、可判断、可决策、可行动并吸收反馈的 OODA 循环。高吉星证明该平台可以承载生产级闭环：能力的调用结果不仅可被看到，还能被追溯到问题包、证据、血缘，并由 geoXI 消费回执确认业务结果。
## Problem / Opportunity

- 已登记的网站适配、Provider、节点和技能需要一个连贯的操作入口；使用者不应只看到静态目录，却无法判断何种能力当前可运行、需要什么条件或应在何处使用。
- 从能力发现到工作流使用之间若缺少连续路径，平台的现有能力难以被可靠地转化为实际自动化。
- 浏览器或 Agent 给出答案并不构成业务成功。高吉星需要在平台中明确呈现真实调用、证据与血缘，以及 geoXI 消费回执的匹配状态，避免将 fixture/mock、执行完成、发送成功或 geoXI 尚未消费冒充 live 业务完成。
- 平台必须自身完成 OODA，而非把闭环责任转交 geoXI；实时与定时 keyword collection、反馈和下一轮行动构成本期生产验证范围。
- 平台愿景包含可复用的 Agent 环境，但本期优先解决产品内可操作性；将公共营销、分发或开放生态提前纳入会稀释生产闭环的验证重点。
## Product Principles

1. **运行事实优先于目录宣称。** 已登记、已安装、已配置、可运行与业务成功是不同状态，产品不得混淆。
2. **能力发现必须通向实际使用。** 使用者应能从能力上下文理解其限制与 readiness，并进入工作流使用路径。
3. **Live 必须可证明。** 只有真实浏览器/OpenCLI 与真实 Doubao 会话产生的结果可计入高吉星 live；fixture、mock、缓存或演示结果必须保持可区分。
4. **系统自身完成 OODA。** Observe、Orient、Decide、Act 及反馈回流必须可观察；完成必须有 cycle、immutable package 和各阶段最小记录，所需 feedback 必须被消费并记录影响，合法 no-action 必须说明原因；geoXI 是 Act 阶段的业务 destination/消费者和反馈来源之一，不是 OODA 的唯一责任主体。
5. **证据和归因分层。** 必需 evidence/lineage pack 完整且 identity 一致才可 accepted/交付；可选 citation 内容为空或 conversation unknown 可继续但不得过度宣称；核心缺失或 package/run/project/artifact mismatch 必须 blocked/failed 或 fail closed；无匹配 geoXI receipt 不得 consumed/confirmed。
6. **状态维度不得混用。** 总体 readiness 仅为 unknown、blocked 或 ready；独立 gates、execution status（queued/running/completed/failed）和 mode（live/fixture/mock）分开呈现，completed 不等于 business success。static gates 仅在配置/版本/绑定未变化时有效，dynamic gates 在 admission 与等待、重试、依赖动作前重观。
7. **OODA 按风险分层。** 低风险可自动 Act；中风险需 OODA 策略责任人批准；高风险需业务复核者或平台管理员批准。低置信度、冲突、证据/lineage/receipt/mode 异常或重复副作用风险必须停止并人工处理。
## Current Release Scope

本期为 **P1：内部/产品内的 operational platform entry**，优化已有平台功能，不交付公共营销站。
- **能力发现：** 在产品内提供网站适配、Provider、节点与相关能力的可理解入口，使使用者能按能力上下文进行发现。
- **真实 readiness：** 独立呈现 gates；static gates 在配置/版本/绑定变化后失效并须重观，dynamic gates 在每次 run admission 前及等待/重试/依赖动作前重观；每次 run 必须有同一有效窗口内的 coherent run-scoped all-required-gate evaluation，未观察为 unknown，明确失败为 blocked，全部通过才 ready。

- **Acceptance boundary:** 本节范围与下列指标是 acceptance target, not current proof；checked tasks、fixture、catalog/configuration 或历史记录均不证明 live、geoXI consumed 或 OODA completed。
- **从能力到工作流使用：** 让已发现且总体 readiness 为 ready 的能力能够进入既有工作流/Studio 使用路径；queued/running/completed/failed 仅描述执行状态，completed 不代表业务成功。
- **高吉星的正确平台上下文：** 将高吉星表述并呈现为首个生产用例：真实 Doubao 调用、可归因 keyword package、答案/引用/会话证据、normalize → accept → sink 血缘；snailfish 通过自身交付能力向 geoXI downstream interface 派发，结果进入对应项目供持久化、查询和分析，只有 matching consumption receipt 才确认业务结果。


## Users & Roles

### 工作流设计者 / 运营人员

在产品内寻找合适的能力，理解当前 readiness 与使用前提，并将能力带入工作流以完成自动化任务；只能查看或暂停运行，不能指定生产技能版本。

### 高吉星运行操作者

发起并观察实时或定时 keyword collection，观察真实 Doubao 问题包的生产运行，区分执行状态、证据状态、geoXI 消费状态和 OODA cycle 状态。

### OODA 策略责任人

定义或复核系统 Observe、Orient、Decide、Act 的业务判断依据与行动边界，检查反馈是否形成下一轮，并对需要人工处理的决策负责。

### 业务结果复核者

从答案回查引用、会话证据、问题包、血缘与匹配 geoXI 消费回执，判断结果是否可接受、是否已被 geoXI 持久化并可供后续使用。

### geoXI 下游产品责任方

geoXI 是独立的下游产品，负责将结果持久化到对应项目并产生消费回执；其消费状态、时间、结果引用和失败原因由 snailfish 接收并用于业务复核。

### 技能维护者

查看技能失败 trace，发起纠正并提出回滚建议；不能单独批准生产启用或生产回滚。

### 平台管理员

维护 readiness，审批技能生产启用与回滚，可暂停运行，并审计全程；不以审批替代证据或真实性护栏。
## Capabilities & Functional Requirements

### 1. 能力目录与上下文发现

产品应让内部用户在正确的平台上下文中发现可用能力，并理解能力适用的运行语境与下一步用途。

#### FR-001
用户可以按能力类别浏览已登记的网站适配、Provider、节点、Agent 与技能，并看到每项能力的名称、用途和适用运行语境。

#### FR-002
能力详情应区分总体 readiness（unknown、blocked、ready）与独立 gates；static gates 在配置、版本或绑定变化后须重新观察，dynamic gates 须在每次 run admission 前及等待、重试或依赖动作前重新观察。

#### FR-003
能力详情应提供进入既有 Studio/工作流使用路径的明确入口，并保留当前能力上下文，避免用户重新寻找或误选能力。

### 2. 真实 readiness

产品应以可观察的运行事实呈现能力是否真正具备执行条件，并在条件不足时阻止不真实的成功预期。

#### FR-004
用户可以看到每个 gate 当前是否通过、未观察或明确失败及原因；每次 run 只有在同一有效窗口内完成 coherent run-scoped all-required-gate evaluation 才可 admission。必要 gate 未观察为 unknown，任一明确失败为 blocked，全部通过才 ready。

#### FR-005
关键 gate 在 admission 后失效时，产品应将运行转为 blocked 或 paused，保留已有 partial evidence，不继续执行、不 fixture fallback、不复用旧 ready；恢复须重观所有必要 gates、记录 blocker 与恢复原因，全部通过后才产生新 admission。

#### FR-006
产品应将总体 readiness、execution status（queued、running、completed、failed）和 mode（live、fixture、mock）作为独立维度呈现；partial coverage 或任何 live+fixture/mock 混合 artifacts 必须明确标记 partial/mixed、non-live、non-confirmed，保留每项 provenance，且不得满足 live success。

#### FR-007
当 live 前提不满足或结果为 partial/mixed 时，产品不得静默切换或宣称 live success；应显示 blocked、partial 或 mixed mode 及可纠正原因。

### 3. 能力到 Studio/工作流连续入口

产品应把能力发现连接到现有 Studio/Canvas 工作流，使用户能在理解约束后实际编排和运行能力。

#### FR-008
用户从能力详情进入 Studio/Canvas 时，产品应带入该能力的正确上下文，并允许用户将其作为工作流中的候选能力使用。

#### FR-009
工作流编辑与运行入口应呈现独立 gates、总体 readiness、execution status 与 mode；运行 admission 前须有同一有效窗口的 coherent gate evaluation，旧 ready 不能跨 run/时间复用，execution completed 也不得呈现为 business success。

#### FR-010
工作流运行后，用户应能从项目操作或运行视图进入该次运行的状态、事件和结果，而不必依赖目录页面推断执行是否发生。

### 4. 高吉星生产闭环上下文

产品应将高吉星呈现为平台首个生产级用例，并让业务结果可由问题包、证据、血缘和 destination 确认共同复核。

#### FR-011
高吉星运行应展示不可变 keyword package/digest，以及 project、workflow、run、execution、source、binding、worker、runtime、mode 和 provenance 归因，使结果可确认对应本次运行。

#### FR-012
产品应分别呈现 nonempty raw answer artifact、citation projection（status、method、items，可为空且 extraction 不等于 verified）和 conversation projection（status、reference，可 unknown/unavailable，不猜）；缺失可选内容不得被过度宣称为已验证证据。

#### FR-013
被接受的答案应展示 normalize/accept outcome 与 reason、accepted record reference，并保留从 package、raw answer、evidence 到 record、delivery 和 geoXI receipt 的 end-to-end lineage；核心 package、raw answer、identity 或 lineage 缺失时不得 accepted/交付。

#### FR-014
产品应分别呈现每个 delivery transport attempt、geoXI receipt 状态（pending、consumed、rejected、expired）与 OODA cycle completed；transport accepted 或 execution completed 均不等于业务成功。

#### FR-015
receipt 必须匹配 target project、package、run、execution、delivery identity 和 persisted result reference；只有目标项目可查询且匹配的 receipt 才能显示 consumed/confirmed。late receipt 仅归原 attempt，不确认新 attempt；duplicate、replay、ambiguous 或 mismatch receipt 必须 rejected/unconfirmed。

#### FR-016
当核心 evidence/lineage 缺失，或 package、digest、run、project、artifact 任一 identity mismatch、receipt 异常或 timeout-after-send/concurrent/unknown outcome 未完成 reconciliation 时，产品应 fail closed，显示可行动原因，不得创建或暗示 live business success。

产品应提升现有技能录制→蒸馏→执行→纠正流程的可信度，让用户能判断版本、失败原因、回滚选择和纠正状态。

#### FR-017
技能用户应能区分录制、蒸馏、可执行、执行中、执行成功、执行失败、candidate、under-review、known-good 和 rolled-back 状态，并看到每个状态绑定的 exact skill version。

#### FR-018
每次技能执行或纠正失败时，用户应能查看与 exact skill version 绑定的失败 trace、阶段和可理解原因，并区分 environment-error 与 skill failure。

#### FR-019
用户应能查看 execution、correction、approval 和 rollback 与 exact skill version 及 linked trace 的关联；proposal 或 distill 不得 promotion，candidate/under-review/known-good/rolled-back 不得互换。

#### FR-020
技能维护者可以提出纠正或回滚，平台管理员审批生产启用与回滚；工作流/运营人员不能指定生产版本，只能查看或暂停运行。

#### FR-021
纠正记录应关联 from/to version、prior snapshot 和触发 trace，并显示待处理、进行中、成功、失败或需人工复核；未满足条件的版本不得自动成为 known-good。

#### FR-022
known-good 至少要求目标能力验证通过、至少一条目标范围真实 passing execution、完整 linked evidence/lineage、无未解决严重失败且无真实性/重复护栏违规；由技能维护者提出、平台管理员确认，未确认保持 under-review。批准可见且可审计。

### 6. 实时与定时 Keyword Collection

产品应支持以 keyword 驱动高吉星的实时和定时采集，并让每次采集的时效、状态、失败与归因可被复核。

#### FR-023
用户应能从正确的平台上下文发起一次实时 keyword collection，并在 admission 前看到 coherent run-scoped readiness evaluation；static 或 dynamic gate 失效时不得开始 live 运行。
#### FR-024
用户应能配置、查看、启用、停用和修改按 keyword 运行的定时采集，并能看到下一次计划时间与最近一次运行状态；每个 planned occurrence 具有可观察的唯一 identity 与 outcome，duplicate、skipped、coalesced、late 均明确记录，±1 分钟基于该 occurrence 的 planned time，duplicate/missed 不得消失。

#### FR-025
每次实时或定时采集都应保留不可变 keyword package/digest 及完整 lineage；采集启动后修改不得改变该次归因，gate 失效或 recovery 后旧 admission 不得复用。

#### FR-026
采集结果应呈现 freshness、运行阶段、结果状态和失败原因；空结果、过期结果、超时、认证/网络阻塞或来源变化不得被显示为成功采集。

#### FR-027
当实时或定时采集缺少必要 readiness、证据或合法运行条件时，产品应 fail closed，显示 blocked、unknown 或 failed；不得以 fixture/mock 替代 live 结果。

### 7. 系统级 OODA 与 geoXI 反馈闭环

产品应让 snailfish 自身完成可观察的 OODA 循环，使用 geoXI 作为 Act 阶段业务消费者和反馈来源之一，并推动下一轮行动。

#### FR-028
用户应能查看每个 OODA cycle 的 Observe、Orient、Decide、Act 阶段的最小可观察记录，并确认该 cycle 与 immutable keyword package、采集运行和反馈关联。仅有阶段标签不能构成 completed。

#### FR-029
Observe 阶段应呈现采集结果、freshness、质量/有效性状态及 evidence/lineage pack；nonempty raw answer 是核心条件，可选 citation 内容为空或 conversation unknown 时保持状态并限制声明。

#### FR-030
Orient 阶段应呈现 normalize/accept outcome、reason、record reference、证据关联和上下文判断；核心归因缺失或不一致时不得进入 accepted。

#### FR-031
Decide 阶段应呈现触发 Act、暂缓、重试、人工复核或结束本轮的判断及依据，并按风险分层。中/高风险 approval 必须绑定 exact OODA cycle、proposed action、keyword package、target project、risk tier、policy version、evidence snapshot、actor 和 time；任一 scope/evidence 改变即失效，generic prior approval 不可复用。

#### FR-032
Act 阶段应呈现每个 transport attempt 以及 snailfish 向 geoXI downstream interface 派发的结果；低置信度、lineage mismatch、缺关键证据、receipt 缺失/错配、fixture/mock/live 混淆或重复副作用风险必须停止并转人工处理。

#### FR-033
geoXI 是独立 downstream product，负责持久化并提供可查询结果。receipt 必须包含并匹配 target project、package、run、execution、delivery identity 和 persisted result reference；snailfish 负责验证关联、保存和展示。receipt 状态为 pending、consumed、rejected 或 expired；只有匹配且目标项目可查询时才可显示 consumed/confirmed。

#### FR-034
产品应分别呈现各 transport attempt、receipt 状态与 OODA cycle completed；accepted transport 不等于 consumed，缺 receipt 或未完成 reconciliation 不得 confirmed。late receipt 仅归原 attempt，不确认新 attempt。

#### FR-035
geoXI 消费反馈应回流对应 OODA cycle；duplicate、replay、ambiguous 或 mismatch receipt 必须 rejected/unconfirmed，异常时不得虚构闭环完成并须人工处理。

#### FR-036
重试保持同一 business identity，各 transport attempt 可见；timeout-after-send、concurrent retry 和 unknown outcome 必须 reconciliation，重复 geoXI 结果计入 guardrail incident 且不得被 dedupe 隐藏。

## Success Metrics
### Scheduled keyword collection punctuality

- **Definition:** Percentage of scheduled keyword collection planned occurrences started or triggered within ±1 minute of each occurrence’s planned time.
- **Target:** 99%.
- **Denominator:** All enabled, user-not-paused planned occurrences, including occurrences with a declared external blocker.
- **Reporting:** Eligibility and blocker classification are fixed at planned trigger time and cannot be rewritten later; blocked/not-started occurrences remain in the denominator and are reported separately, never silently counted as success.

### Real-time collection latency

- **Definition:** Baseline measurement of elapsed time from an accepted real-time keyword collection request to its recorded start/trigger event, using real live runs only.
- **Baseline sample contract:** The initial baseline uses two real geoXI projects (one normal-volume and one new/low-volume), at least three keywords per project (normal high-hit, low-hit/empty, and Chinese composite/boundary), both real-time and scheduled triggers, and at least 100 real live OODA cycles over seven consecutive days. It includes normal/delayed receipts, rejection/failure, retries, and missing/mismatched receipts, reported by project × keyword × trigger × outcome × receipt.
- **Baseline rule:** Report external blockers separately; never silently remove them from denominators or count them as success. This metric has no pass claim until a numeric target is set after reviewing this representative baseline.
- **Target-setting trigger:** Set a numeric target after the baseline review establishes the normal operating range.

### Complete system-owned OODA cycle success

- **Definition:** Percentage of all triggered live real-time or scheduled cycles with completion evidence.
- **Target:** 95%.
- **Denominator:** All triggered cycles; report admitted, blocked, waiting, completed, and no-action totals. Blocker/eligibility classification is fixed at admission/trigger and cannot be shrunk post hoc; only cycles with immutable package, minimum stage records, and required feedback evidence count completed.

### GeoXI consumption latency

- **Definition:** Baseline measurement from snailfish delivery dispatch to the matching geoXI consumption receipt for a persisted, queryable project result.
- **Baseline rule:** Collect only after real geoXI interface integration, including successful and delayed/failed receipts; no target or pass claim is made before baseline review.
- **Target-setting trigger:** Set a numeric target after real-interface integration provides a representative baseline and the consumer responsibility boundary is confirmed.

### Authenticity and outcome guardrails

- **Definition:** Count of incidents where fixture/mock is presented as live, an unmatched receipt marks business outcome confirmed, retry creates a duplicate business result, or a missing core evidence/lineage pack is accepted.
- **Target:** 0 incidents.
- **Denominator:** All live and fixture/mock runs, delivery attempts, receipts, retries, and acceptance decisions subject to these guardrails; optional empty/unknown projections are reported separately.
### Counter-metrics

- Report total triggered, admitted, blocked, waiting, completed, and no-action OODA cycles beside the 95% rate; blocker/eligibility classification is fixed at trigger/admission and cannot be shrunk post hoc.
- Report eligible-run volume and blocked-run volume beside every rate; do not improve rates by excluding blocked work or reducing runs.
- Report evidence completeness and lineage coverage by required pack element; optional empty/unknown projections are reported separately and cannot inflate completeness.
- Report live-versus-fixture/mock volumes separately; fixture output cannot substitute for live execution.
- Report retry count and duplicate-result incidents; suppressing retries or hiding duplicates cannot improve the guardrail metric.
- Report no-action, waiting_feedback, partial, blocked, failed, and expired cycle volumes separately; no-action cannot be used to inflate the 95% completion rate.

## User Journeys

### UJ-001 — 工作流/运营人员：keyword 到运行

**角色：** 林然，工作流/运营人员。**起点：** 在平台能力上下文输入一个 keyword 并选择实时或已启用的定时运行。**步骤：** 确认 keyword package 与 readiness；启动或等待采集；查看 freshness、状态、失败与 OODA 阶段；在阻塞时修正前置条件或等待恢复。**成功终点：** 采集结果进入可追溯的 OODA cycle，并按规则进入 Act；未满足条件时以明确 blocked/failed 终止而非假成功。

### UJ-002 — 系统：完成 OODA 并派发 geoXI

**角色：** snailfish 系统。**起点：** 接收到实时或定时 keyword collection 的观察结果。**步骤：** 记录 Observe；整理并解释为 Orient；依据业务判断完成 Decide；执行采集调整/记录处理并通过自身交付能力派发 geoXI；接收消费反馈并安排下一轮。**失败/恢复：** 缺少 readiness、证据、lineage、匹配回执或动作失败时保持 fail-closed，记录状态并按策略重试或请求人工处理。**成功终点：** OODA cycle 记录完整阶段与反馈状态，且 geoXI 消费回执与 delivery identity 匹配时该投递业务结果 confirmed。

### UJ-003 — 业务结果复核者：追踪 evidence/lineage/receipt
**角色：** 许宁，业务结果复核者。**起点：** 打开一次高吉星运行或待复核结果。**步骤：** 回查 immutable keyword package/digest、project/workflow/run/execution/source/binding/worker/runtime/mode/provenance、nonempty raw answer、citation/conversation projections、normalize/accept outcome、record、delivery 和 geoXI receipt。**失败/恢复：** 核心证据/归因缺失或 mismatch 时保持 blocked/failed；可选 citation 为空或 conversation unknown 时仅限制声明并继续复核；仅 transport accepted 时保持 unknown/unconfirmed。**成功终点：** 仅在 matching receipt 证明 geoXI 已持久化且可查询时接受业务结果。


### UJ-004 — 平台管理员：处理 readiness/blocked
**角色：** 周衡，平台管理员。**起点：** 能力或计划显示 blocked/unknown。**步骤：** 检查各 static/dynamic gate 的最新观察，修复或明确声明外部阻塞；重新观察所有必要 gates 并记录 blocker 与恢复原因，产生新的 admission。**成功终点：** 条件恢复后运行可继续，或保留有原因的 blocked/paused 状态；管理员不能用 fixture/mock 掩盖阻塞。

### UJ-005 — 技能维护者：失败到纠正/回滚
**角色：** 沈岚，技能维护者。**起点：** 技能执行失败并进入待纠正。**步骤：** 查看与 exact skill version 绑定的 failure trace，区分 environment-error 与 skill failure；提交纠正并记录 from/to version、prior snapshot；提出回滚，等待平台管理员审批。**失败/恢复：** 纠正失败或无 known-good 时保持 under-review 并转人工。批准回滚后 detail/后续 run 显示 prior version active，corrected version history=rolled_back，下一 target-scope execution 归因 restored version；仅 mutation 完成不算成功，无法执行或结果 unknown 时为 blocked/unknown/failed。**成功终点：** 纠正/回滚证据完整且生产审批可审计。

## Non-Functional Requirements

### NFR-001 — 可靠性与幂等
同一 keyword package、delivery identity 和 OODA cycle 的重试不得产生重复业务结果；失败恢复后状态可继续追溯。
### NFR-002 — 可审计与证据保留
运行、阶段、证据、lineage、投递、receipt、技能版本、纠正、审批和回滚状态应可回查；每次生产启用/暂停/回滚必须关联 exact version 与 trace 并可审计。

### NFR-003 — 安全与权限
技能维护者只能查看 trace、发起纠正和提出回滚；平台管理员审批生产启用/回滚并可暂停；工作流/运营人员仅查看/暂停运行且不能指定生产版本。认证信息和 secret 不得暴露。

### NFR-004 — 项目隔离
keyword package、运行、证据、lineage、交付、receipt 和 geoXI 项目结果不得跨项目混用或互相确认；project identity mismatch 必须 fail closed。

### NFR-005 — 性能与容量基线
实时延迟、geoXI 消费延迟和可承载运行量先采集真实基线；在基线与范围确认前不宣称目标达成。

### NFR-006 — 可观测与故障状态
每个阶段和关键失败应显示可行动状态；OODA 终态至少包括 waiting_feedback、partial、blocked、failed、expired、completed；blocked/unknown、failed/unconfirmed、partial 与 confirmed 不得合并，completed 不得由阶段标签单独产生。

### NFR-007 — schedule 准点
启用且未暂停、无声明外部阻塞的定时运行，至少 99% 应在计划时间 ±1 分钟内启动或触发；阻塞单独报告。

## Dependencies & Risks

- 真实可执行的 Doubao capability、认证健康会话、浏览器容量和网络许可是 live 运行前置。
- 首轮 baseline 按 project × keyword × trigger × outcome × receipt 分层；稀疏 strata 必须单独报告，不得用总量掩盖。exact per-stratum minimum 由 operational acceptance 在 target-setting 前确定。
- geoXI 是独立下游产品；其接口必须支持对应项目持久化/查询/分析，并产生包含 target project、delivery identity、keyword package/run、consumption status、consumed timestamp、persisted result reference、failure/rejection reason 和 match result 的最小可观察消费回执。geoXI 负责持久化与回执，snailfish 负责派发、关联验证、保存/展示及更新 business outcome/OODA。
- OODA 决策责任与动作风险边界必须明确；低风险自动 Act，中风险由 OODA 策略责任人批准，高风险由业务复核者或平台管理员批准。证据、lineage、receipt、mode 或 duplicate-side-effect 风险异常会阻断闭环。
- 采集来源、目标项目、权限与 OODA 决策责任需保持明确，否则可能产生跨项目污染或无人负责的 Act。
- 调度准点、实时延迟和消费延迟受外部资源/网络影响；声明的 blocker 必须单独计量，不能美化指标。
- fixture/mock 与 live 混用、证据缺失、重试重复和 receipt 错配会造成错误业务确认，必须 fail closed。

- **Acceptance boundary:** All scope and metrics statements are acceptance targets, not current implementation/live proof; checked tasks, fixtures, catalog/configuration, and history do not satisfy live, geoXI, or OODA acceptance.
## Deferred Items

- **GeoXI receipt validity duration and compensation policy:** Owner: geoXI product owner with OODA strategy owner approval. Condition: before geoXI live readiness/integration acceptance; until approved, live readiness remains blocked/unknown.
- **S1 broader known-good sample count and risk strata:** Owner: skill maintainer + platform administrator (include OODA strategy owner for OODA risk). Condition: before production promotion for the target capability; until decided, the version remains under-review and cannot become known-good.
- **In-flight pause semantics:** Owner: platform operations. Condition: before production pause/recovery runbook.
- **Freshness/time-order semantics:** Owner: operational acceptance. Condition: before live baseline target setting.
## Open Questions
No phase-blocking open questions; see Deferred Items.

## Product Glossary

- **readiness:** overall unknown/blocked/ready result.
- **gate:** independent prerequisite observation.
- **admission:** coherent run-scoped decision that all required gates passed.
- **live / fixture / mock:** execution modes; fixture/mock is non-live.
- **transport attempt / accepted:** one delivery try / destination accepted transport, not business confirmation.
- **receipt pending / consumed / rejected / expired:** geoXI consumption states.
- **confirmed:** business outcome supported by matching receipt and queryable persisted result.
- **OODA cycle / completed / no-action:** one system loop / completion evidence satisfied / valid decision to take no action with reason.
- **evidence/lineage pack:** required artifacts and identity links proving what ran, what it produced, and where it was delivered.
- **candidate / under-review / known-good / rolled-back:** skill version lifecycle states; only administrator-confirmed known-good is production-trusted.
