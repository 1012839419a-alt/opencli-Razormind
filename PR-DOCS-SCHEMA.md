## 内容

两处独立的小改动，纯文档：

### 1. 新增 `docs/schema.md` —— 数据模型参考

`collected_records` 表里的标准字段（标题、正文、作者、链接、发布时间）不是顶层列，而是嵌在 `normalized_data` JSON 列里。我自己在写一个下游 AI worker 时第一反应是 `SELECT title FROM records`，跑了一整轮才发现表名是 `collected_records` 而字段全在 JSON 里。文档化一下，让后来的下游消费者少踩这个坑。

内容包括：

- `collected_records` 各列含义与约束
- `normalized_data` 内的标准 key 及其在各渠道侧的别名映射（来自 `backend/pipeline/normalizer.py`）
- 字段值的真实类型行为（都是 str；缺值是 `""` 不是 `null`）
- 从 SQLite / Postgres 查询的正确 SQL 姿势（`json_extract` / `->>'...'`）
- `status` 状态机：`raw → normalized → ai_processed → notified`（失败为 `error`）
- `ai_enrichment` 当前无强制 schema 校验的事实，及各 processor 的 fallback 行为
- 一段 SQLite 并发写注意事项（WAL / Postgres）

### 2. 修 README dashboard 图片链接 `develop` → `main`

`README.md` 第 10 行的 dashboard 图片链接指向 `https://raw.githubusercontent.com/xjh1994/opencli-admin/develop/docs/dashboard.png`，但 default branch 是 `main`。两个分支当前指向同一 blob 所以图能加载，但 `develop` 若删除或分歧链接会断。

只换分支名，不动图。

## 范围

- 改文件：`README.md`（1 行链接）、新增 `docs/schema.md`
- 不动代码、不动 schema、不动测试
- 跟我之前那个 `feat/external-http-processor` PR 完全独立（那个是加 processor 抽象，这个纯文档）

## 为什么单独发

文档类改动评审成本低，跟功能 PR 解耦后能让你按节奏 review 不互相阻塞。如果觉得 schema.md 应该挪位置 / 改风格随时说，我立刻改。
