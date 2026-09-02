# Addendum — 平台机制与来源范围判定

本文件保留用户提供的技术深度、外部网站来源分析与后置决定；它们不构成本期 P1 的验收承诺。

## 1. OpenCLI「AI Agent 的 Emacs」文章：长期机制，不纳入本期验收

来源：用户提供的 OpenCLI Team 2026-04-05 文章《OpenCLI：人工智能代理的 Emacs》。

文章提出的长期平台机制：

- **Everything is CLI** 的可编程环境理念；
- 从 operate 的交互探索、network/API 发现，经 init 脚手架和 verify，最终将即兴浏览 crystallize 为永久 CLI 技能的路径；
- TypeScript / YAML 适配器、动态加载，以及保存后下次调用即时生效；
- 透明 adapter 源码与结构化诊断，以支持 Agent 原地自修复；
- CLI Hub 统一外部工具；
- 可组合的 pipeline primitives；
- 一次开发、重复低 token 调用的经济性；文章中的约 **92% token reduction** 仅是示例，不是本期 KPI、SLA 或性能承诺。

这些内容说明长期平台方向，但本期不验收通用 CLI 化、API 发现、永久技能 crystallization、TS/YAML 动态加载、自动 adapter 修复、CLI Hub 或 pipeline primitive。P1 只采用其产品含义：能力应在产品内可发现、可判断真实 readiness、可进入既有工作流。

## 2. `jackwener/opencli-website` 来源分析与范围决定

来源：用户提供的 GitHub 仓库，默认分支 `master`：<https://github.com/jackwener/opencli-website>。

### P1：本期采用的产品含义

不复制其营销首页。仅采用与产品内 operational platform entry 一致的能力：

- 平台/命令目录的能力发现与按类别理解；
- 将 browser、desktop、public 等运行语境和命令能力清楚区分；
- 从能力详情进入实际工作流使用；
- 以 Doubao 作为高吉星首个生产用例的正确平台上下文，而非一个孤立页面。

对应网站来源包括 `src/components/Platforms.tsx`、`src/components/data.ts` 与 `src/App.tsx`；P1 在 snailfish 中以现有的产品内插件、OpenCLI 适配和工作流入口为优化对象，不承诺公开站点。

### P2：后置的社区插件生态

网站已实现/表达的社区插件目录、插件详情、安装命令、GitHub metadata、贡献 PR 入口和 YAML/TS 分类，不属于本期。

后置原因：第三方社区插件进入生产平台前必须先解决审核、安装安全、权限、兼容性和治理。该阶段不因网站存在展示页而被视为已可安全交付。

相关来源：`src/pages/PluginsPage.tsx`、`src/pages/PluginDetailPage.tsx`、`src/data/plugins.json`、`CONTRIBUTING_PLUGINS.md`。

### P3：后置的公共分发和内容面

以下均明确后置：Download、Windows/macOS 安装、Release/完整性、公开文档、中英博客与理念文章。

网站的相应实现位于 `src/pages/DownloadPage.tsx`、`src/pages/BlogPage.tsx`、`src/pages/BlogPostPage.tsx`；`/docs/` 在部署时由另一仓库的 VitePress 文档构建并合并（`.github/workflows/deploy.yml`）。这些是未来公共产品面/分发责任，不是当前优化产品功能的 P1 交付。

## 3. 本期边界结论

本期标题中的「OpenCLI 可编程 Agent 平台」是产品愿景与上下文；本期承诺仅限 P1 的内部/产品内 capability discovery、真实 readiness、从能力到工作流使用，以及高吉星的 live evidence / lineage / matching destination ACK 上下文。长期平台愿景不自动扩张为本期范围。

## 4. geoXI 与 OODA 的当前事实边界

仓库当前没有已定义的 geoXI/GEO-XI 专属消费契约、消费事件或 ACK 规范；本期产品决定将 geoXI 作为 Act 阶段业务 destination/消费者，并要求匹配消费回执后才确认业务结果，但不在此处发明技术合同。

`docs/SYSTEM_ANALYSIS.md` 与 `docs/CONTROL_THEORY_ARCHITECTURE.md` 提供 OODA、反馈和控制动作的现状分析/架构参考，指出当前采集管线存在单向开环、质量反馈弱和 egress ACK 缺口。它们是产品抽取与范围判断的参考，不是 snailfish 已完成 OODA 交付或 geoXI ACK 能力的证明。
