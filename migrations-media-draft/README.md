# opencli-admin Media Superset — 草稿包

> **状态**: 草稿, 等你审完才能动代码
> **作者**: Claude (Opus 4.8) on 2026-06-15
> **对应 PR/commit**: 还未提交, 这是新分支的 seed

## 这是什么

给 opencli-admin 加**完整的多媒体超集**能力(图片 / 视频 / 音频 / 文档 / 多模态 / 训练 ETL)。
**通用化** — 不绑死任何垂直场景, 量化 / 运营 / 训练 / 研究 各取所需。

## 文件清单

```
docs/media-superset/
└── DESIGN.md                        ← ★ 主设计文档, 请先读这个
                                      12 节, 约 400 行, 含完整数据模型 / 接口 / 状态机 / 流程

migrations-media-draft/
├── m3n4o5p6q7r8_add_media_tables.py ← ★ alembic 迁移草稿, 直接可用
│                                      4 张新表: media_assets / media_text / media_features / media_labels
│                                      6 个索引, 复合索引 (kind, status) 优化队列查询
│
└── skeleton.py                       ← ★ 接口骨架 (伪代码)
                                       backend/media/ 全部文件的类型签名 + 关键逻辑
                                       4 大抽象: MediaStore / MediaIndex / MediaProcessor / AssetDetector
                                       9 个 API 端点: 媒体 CRUD + 处理触发 + 标签 + 训练导出
                                       独立 CLI: opencli-export (Coco / Yolo / Parquet)
```

## 5 阶段交付(请审 M1 范围)

| 阶段 | 内容 | 估时 |
|---|---|---|
| **M1** | 媒体能存 + 能看(4 表 + LocalFS + Detector + Downloader + Gallery UI) | 1-2 周 |
| M2 | 媒体能处理(Thumbnailer / PdfExtractor / AudioTranscriber / VideoMetadata) | 1-2 周 |
| M3 | 多模态 + 检索(ClipEmbedder + DuckDB 索引) | 1-2 周 |
| M4 | 训练 ETL + stanza 集成(`/api/v1/datasets/*` + `opencli-export` CLI) | 1-2 周 |
| M5 | 分布式(S3 + Celery + CDN + 配额) | 1-2 周 |

## 关键设计决策

1. **不动 `collected_records`**: 新表是"挂"上去的, 通过 `record_id` 关联, **已有数据零迁移成本**
2. **4 个抽象接口, 4 个目录**: `store / index / processors / detectors`, 各有多种实现 + registry
3. **append-only 设计**: `media_text` / `media_features` / `media_labels` 都不修改, 一个 asset 可以多条记录
4. **存储/索引/处理 全部可插拔**: M1 用 LocalFS + SQLite + asyncio 起步, M5 可换 S3 + PG + Celery
5. **不绑死 stanza**: `media_labels.label_value` 是 JSON, 任意形态 (bbox / polygon / category / caption), stanza / YOLO / COCO 各取所需

## 验收

### M1 验收(本 PR 目标)
- [ ] 4 个新表迁移能跑
- [ ] pytest 全过(新增 ~25 用例, 已有 380/382 不退化)
- [ ] **真实端到端**: 配 web scraper 数据源抓一篇带图网页 → 图自动入库 → Gallery 显示
- [ ] 手动跑 `opencli-export --format parquet --limit 5` 能导出

## 审稿请关注 (TODO)

1. **`media_assets` 字段够不够?** 缺什么场景字段?
2. **Detector 三种 (HTML / URL / JSON 字段) 覆盖度**? 还需要什么?
3. **M1 范围**: 1-2 周够吗, 还是想 M1+M2 一起?
4. **训练 ETL 优先 COCO 还是 YOLO?**
5. **stanza-public-clean 是什么任务?** (分类? 检测? 分割?) — 决定 `media_labels.label_type` 默认形态

## 下一步

等你审过 DESIGN.md + 迁移草稿 + 骨架, 确认 5 个 TODO 后:
1. 切到新 git 分支 (e.g. `feature/media-superset`)
2. 复制迁移草稿到 `backend/migrations/versions/`
3. 复制骨架到 `backend/media/` 真正可运行版
4. 写 pytest
5. 跑端到端 demo

## 跟量化项目的关系

**不强绑量化**。但用得上:
- Tushare / akshare / BaoStock 都是普通 Channel, 跟图片爬取同套调度
- DuckDB 同步器自然导出到 pandas/polars/backtrader
- 信号触发器推到 Telegram, 跟你现有那套接得上
- 训练集可以反哺 `stanza-public-clean` 做图片识别
