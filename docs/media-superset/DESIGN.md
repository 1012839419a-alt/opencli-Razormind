# opencli-admin Media Superset — 设计文档

> 状态: **草稿 v0.1, 待审**
> 范围: 给 opencli-admin 加完整的**多媒体超集**能力(图片 / 视频 / 音频 / 文档)
> 定位: **通用扩展**, 不绑死任何垂直场景(量化 / 运营 / 训练 各取所需)

---

## 0. 设计原则

| 原则 | 含义 |
|---|---|
| **First-class media** | 媒体是独立实体, 不是 `extra_*` 字典里的一行 |
| **Pluggable everything** | 存储 / 索引 / 处理 / 导出 全部 `@register_*` |
| **Progressive enhancement** | M1 先能存能看, M2 处理, M3 检索, M4 训练 ETL |
| **Don't break** | 不动 `collected_records` 已有数据, 新表是"挂"上去的 |
| **Test-first** | 写代码前先有 pytest 用例 + 端到端 demo |

---

## 1. 核心抽象

### 1.1 实体(Entity) 关系

```
┌─────────────────┐       1:N      ┌─────────────────┐
│ collected_records │ ──────────────→ │   media_assets    │
│   (已有, 不动)    │                │                   │
└─────────────────┘                └────┬───────┬────┘
                                         │       │
                                  1:N    │       │  1:N
                                         ▼       ▼
                              ┌──────────────┐  ┌────────────────┐
                              │  media_text  │  │ media_features │
                              │  OCR/ASR/... │  │  CLIP/VIT/...   │
                              └──────────────┘  └────────────────┘
                                         │
                                  1:N    │
                                         ▼
                              ┌──────────────────┐
                              │  media_labels    │  ← stanza 训练目标
                              │  bbox/category/..│
                              └──────────────────┘
```

### 1.2 接口分层

```python
# 4 个接口, 4 个目录, 各有多种实现

backend/media/
├── store/         # 文件存储 (本地 / S3 / GCS)
│   ├── base.py    # MediaStore 抽象
│   ├── local.py   # LocalFSStore
│   ├── s3.py      # S3Store
│   └── factory.py # MediaStore.for_backend("local")
│
├── index/         # 元数据索引 (SQLite / DuckDB / PG)
│   ├── base.py    # MediaIndex 抽象
│   ├── sqlite.py  # SQLiteMediaIndex
│   ├── duckdb.py  # DuckDBMediaIndex
│   └── factory.py
│
├── processors/    # 媒体处理 (缩略图/转码/转写/...)
│   ├── base.py    # MediaProcessor 抽象 + @register_processor
│   ├── image_thumbnail.py
│   ├── pdf_extract.py
│   ├── audio_transcribe.py
│   ├── video_metadata.py
│   ├── clip_embed.py
│   └── registry.py
│
└── detectors/     # 媒体引用检测 (HTML 标签 / 裸 URL)
    ├── base.py
    ├── html.py    # BeautifulSoup
    ├── url.py     # 正则
    └── registry.py
```

---

## 2. 数据模型(详细)

### 2.1 `media_assets` — 媒体资产主表

```python
class MediaAsset(TimestampMixin):
    __tablename__ = "media_assets"

    # 主键 + 关联
    id:           Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    record_id:    Mapped[str] = mapped_column(String(36), ForeignKey("collected_records.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id:    Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # 类型 / MIME
    kind:           Mapped[str] = mapped_column(String(16), nullable=False, index=True)   # image|video|audio|document
    mime_type:      Mapped[Optional[str]] = mapped_column(String(64))
    file_extension: Mapped[Optional[str]] = mapped_column(String(8))

    # 来源(原始 URL)
    source_url:     Mapped[Optional[str]] = mapped_column(Text)         # 原始 URL
    referer_url:    Mapped[Optional[str]] = mapped_column(Text)         # 哪个页面引用的
    discovered_by:  Mapped[str] = mapped_column(String(32), nullable=False, default="detector")  # detector=自动 / manual=人工

    # 存储(MediaStore 抽象)
    storage_backend: Mapped[str] = mapped_column(String(16), nullable=False)  # local|s3|gcs
    storage_key:     Mapped[str] = mapped_column(Text, nullable=False)         # 桶内相对路径
    file_size:       Mapped[Optional[int]] = mapped_column(BigInteger)
    file_hash:       Mapped[Optional[str]] = mapped_column(String(64), index=True)  # SHA-256, 全局去重

    # 处理状态
    status:          Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)  # pending|downloading|ready|error
    download_error:  Mapped[Optional[str]] = mapped_column(Text)
    downloaded_at:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # 元数据(由 processors 填充)
    width:           Mapped[Optional[int]] = mapped_column(Integer)     # 图片/视频
    height:          Mapped[Optional[int]] = mapped_column(Integer)
    duration_sec:    Mapped[Optional[float]] = mapped_column(Float)     # 视频/音频
    page_count:      Mapped[Optional[int]] = mapped_column(Integer)     # PDF/DOCX
    meta:            Mapped[Optional[dict]] = mapped_column(JSON)        # EXIF / ID3 / codec 等

    # 处理进度(progress 跟踪)
    processed_jobs:  Mapped[list] = mapped_column(JSON, default=list)    # ["image_thumbnail:ok", "clip_embed:pending"]
```

**索引**:
- `(record_id)`: 按记录查
- `(source_id)`: 按数据源查
- `(kind, status)`: 按类型和状态过滤
- `(file_hash)`: 全局去重

### 2.2 `media_text` — 文本派生(OCR / ASR / 文档解析 / LLM caption)

```python
class MediaText(TimestampMixin):
    __tablename__ = "media_text"

    id:        Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id:  Mapped[str] = mapped_column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)

    # 来源
    source:    Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # ocr|asr|pdf_extract|docx_extract|llm_caption
    language:  Mapped[Optional[str]] = mapped_column(String(8))                       # zh|en|ja|...

    # 文本内容
    text:      Mapped[str] = mapped_column(Text, nullable=False)
    entities:  Mapped[Optional[dict]] = mapped_column(JSON)   # 抽实体(股票/品牌/事件)
    summary:   Mapped[Optional[str]] = mapped_column(Text)    # LLM 摘要

    # 时序(ASR / 视频字幕)
    start_sec: Mapped[Optional[float]] = mapped_column(Float)
    end_sec:   Mapped[Optional[float]] = mapped_column(Float)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)  # PDF 页码

    # 模型元信息
    model_name:    Mapped[Optional[str]] = mapped_column(String(64))
    model_version: Mapped[Optional[str]] = mapped_column(String(32))
    confidence:    Mapped[Optional[float]] = mapped_column(Float)
```

**索引**:
- `(asset_id)`: 反向查
- `(source)`: 按来源过滤
- SQLite: 全文索引用 FTS5; PostgreSQL: `tsvector`

### 2.3 `media_features` — 多模态向量特征

```python
class MediaFeature(TimestampMixin):
    __tablename__ = "media_features"

    id:           Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id:     Mapped[str] = mapped_column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_type: Mapped[str] = mapped_column(String(16), nullable=False)  # clip|vit|audio_embed|custom
    vector:       Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dim:          Mapped[int] = mapped_column(Integer, nullable=False)
    model_name:   Mapped[Optional[str]] = mapped_column(String(64))
    model_version: Mapped[Optional[str]] = mapped_column(String(32))
```

**注**: 生产用 pgvector / Milvus / Qdrant. M3 阶段先存 BLOB, 后续可换.

### 2.4 `media_labels` — 标签(训练目标)

```python
class MediaLabel(TimestampMixin):
    __tablename__ = "media_labels"

    id:          Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id:    Mapped[str] = mapped_column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)

    # 来源
    source:      Mapped[str] = mapped_column(String(16), nullable=False)  # human|auto|llm
    annotator:   Mapped[Optional[str]] = mapped_column(String(64))

    # 标签内容
    label_type:  Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # category|bbox|segmentation|classification|caption
    label_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence:  Mapped[Optional[float]] = mapped_column(Float)

    # 训练集分割
    split:       Mapped[Optional[str]] = mapped_column(String(8), index=True)  # train|val|test|null
    notes:       Mapped[Optional[str]] = mapped_column(Text)
```

`label_value` 形态示例:
- `category`: `{"category": "k线图"}`
- `bbox`: `{"bbox": [x, y, w, h], "label": "涨停"}` (YOLO 风格)
- `segmentation`: `{"polygon": [[x,y],...], "label": "logo"}`
- `caption`: `{"text": "今日大盘上涨 1.2%"}`

---

## 3. 状态机

### 3.1 MediaAsset 状态

```
   ┌─────────┐
   │ pending │  Detector 创建
   └────┬────┘
        │ MediaStore.put(source_url → bytes)
        ▼
   ┌──────────────┐
   │ downloading │  (可选, 异步)
   └────┬─────┬───┘
        │     │ 失败 N 次
        │     ▼
        │   ┌───────┐
        │   │ error │  download_error 记录
        │   └───────┘
        ▼ 成功
   ┌──────┐
   │ ready│  file_hash / file_size 已存
   └──┬───┘
      │ MediaProcessor 跑
      ▼
   (processed_jobs 累加, 状态不变, 仍为 ready)
```

### 3.2 MediaText / MediaFeature 状态

无显式状态字段, **append-only**: 一个 asset 可以有多条 text (OCR + ASR + caption), 多条 feature (CLIP + ViT).

### 3.3 MediaLabel 状态

也 append-only, 但 `split` 字段可被训练脚本重写 (move from null → train).

---

## 4. 关键流程

### 4.1 媒体发现(Detector)

```
CollectedRecord.raw_data / .normalized_data
        │
        ▼
┌──────────────────┐
│   Detector        │
│  ├─ HTMLDetector  │  解析 <img> <video> <source> <a href>
│  ├─ URLDetector   │  正则匹配 .jpg .mp4 .pdf ...
│  └─ JsonDetector  │  通用 JSON 字段 (Twitter entities.media 等)
└────────┬─────────┘
         │ list[MediaRef(url, kind, referer)]
         ▼
   media_assets 表 INSERT (status=pending, storage_key=待分配)
         │
         ▼
   (触发 download worker, 异步)
```

### 4.2 媒体下载(Downloader)

```python
# backend/media/downloaders/worker.py
async def download_pending_assets(limit: int = 50):
    """从 media_assets 取 pending 的, httpx 异步下载, 写 MediaStore."""
    async with AsyncSessionLocal() as session:
        stmt = select(MediaAsset).where(MediaAsset.status == "pending").limit(limit)
        assets = (await session.execute(stmt)).scalars().all()

    for asset in assets:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(asset.source_url, follow_redirects=True)
                resp.raise_for_status()
                data = resp.content

            # 全局去重
            h = hashlib.sha256(data).hexdigest()
            existing = await session.execute(
                select(MediaAsset).where(MediaAsset.file_hash == h, MediaAsset.id != asset.id)
            )
            if existing.first():
                # 已有相同文件, 复用 storage_key, 删除当前 row
                dup = existing.scalar_one()
                asset.storage_key = dup.storage_key
                asset.file_hash = h
                asset.status = "ready"
                asset.downloaded_at = datetime.now(timezone.utc)
                continue

            # 写存储
            key = f"original/{asset.kind}/{asset.id}{guess_ext(asset)}"
            await store.put(key, data, asset.mime_type or "application/octet-stream")

            asset.storage_key = key
            asset.file_hash = h
            asset.file_size = len(data)
            asset.status = "ready"
            asset.downloaded_at = datetime.now(timezone.utc)
        except Exception as e:
            asset.status = "error"
            asset.download_error = str(e)[:500]
        await session.commit()
```

### 4.3 媒体处理(Processors)

```python
# backend/media/processors/registry.py
PROCESSORS: dict[str, MediaProcessor] = {}

def register_processor(cls):
    inst = cls()
    PROCESSORS[inst.processor_type] = inst
    return cls

def get_processor(p: str) -> MediaProcessor: return PROCESSORS[p]
```

每个 processor 是 **stateless** 的, 输入是 asset + store, 输出是 `ProcessResult` (元数据 + 派生文件 + 派生 text/feature).

```python
@dataclass
class ProcessResult:
    ok: bool
    meta: dict[str, Any] = field(default_factory=dict)   # 填回 MediaAsset
    text_outputs: list[TextOutput] = field(default_factory=list)
    feature_outputs: list[FeatureOutput] = field(default_factory=list)
    file_outputs: list[FileOutput] = field(default_factory=list)
    error: str | None = None
```

**调度**: 简单的 asyncio 循环 (M1) → Celery/rq (M5).

### 4.4 训练集导出(ETL)

```python
# backend/datasets/exporters/base.py
class DatasetExporter(ABC):
    format: str  # "coco" | "yolo" | "parquet" | "csv"

    @abstractmethod
    async def export(self, filters: DatasetFilters, output_dir: Path) -> ExportResult: ...

# 注册:
@register_exporter
class CocoExporter(DatasetExporter):
    format = "coco"
    # 读 media_assets + media_labels
    # 生成 annotations.json + images/

@register_exporter
class ParquetExporter(DatasetExporter):
    format = "parquet"
    # 读 media_assets + media_text
    # 生成 df.parquet (asset_id, kind, source_url, text, ...)
```

**独立 CLI**:
```bash
$ opencli-export --format coco --output ./stanza-train-2026-06 --split train,val
$ opencli-export --format parquet --include text --output ./stanza-text-2026-06
$ opencli-export --incremental --since 2026-06-01
```

---

## 5. API 设计

### 5.1 Media 资源

```
GET    /api/v1/media/assets                      # 列表
GET    /api/v1/media/assets/{id}                 # 详情
GET    /api/v1/media/assets/{id}/file            # 原始文件 (redirect to signed URL or proxy)
GET    /api/v1/media/assets/{id}/preview         # 缩略图/转码
GET    /api/v1/media/assets/{id}/text            # 派生文本 (text_outputs)
GET    /api/v1/media/assets/{id}/features        # 派生特征
POST   /api/v1/media/assets                      # 手动上传
DELETE /api/v1/media/assets/{id}                 # 删除 (级联)
POST   /api/v1/media/assets/{id}/process         # 触发处理
POST   /api/v1/media/assets/{id}/labels          # 打标签
```

### 5.2 训练集导出

```
POST   /api/v1/datasets/export                   # 异步导出
GET    /api/v1/datasets/exports                  # 导出历史
GET    /api/v1/datasets/exports/{id}/download    # 下载 zip/parquet
```

### 5.3 处理任务(可选)

```
GET    /api/v1/media/processors                  # 列出已注册 processors
POST   /api/v1/media/process-queue               # 手动入队
GET    /api/v1/media/process-queue/stats         # 队列状态
```

---

## 6. 配置

`.env` 新增:
```bash
# Media Store
MEDIA_STORE_BACKEND=local                         # local | s3 | gcs
MEDIA_LOCAL_ROOT=./data/media                     # 本地存储根
MEDIA_S3_BUCKET=                                   # s3://bucket-name
MEDIA_S3_REGION=us-east-1
MEDIA_S3_ACCESS_KEY=
MEDIA_S3_SECRET_KEY=

# Media Index
MEDIA_INDEX_BACKEND=sqlite                        # sqlite | duckdb | pg
# (sqlite 用同一个 db, 不需额外配置; duckdb: ./data/media_index.duckdb)

# Processors
MEDIA_PROCESSOR_IMAGE_THUMBNAIL=enabled
MEDIA_PROCESSOR_PDF_EXTRACT=enabled
MEDIA_PROCESSOR_AUDIO_TRANSCRIBE=disabled         # 较重, 默认关
MEDIA_PROCESSOR_CLIP_EMBED=disabled               # 较重, 默认关

# Whisper
WHISPER_MODEL=base
WHISPER_DEVICE=cpu

# Clip
CLIP_MODEL=sentence-transformers/clip-ViT-B-32

# 队列(M5)
MEDIA_QUEUE_BACKEND=asyncio                       # asyncio | celery
CELERY_BROKER_URL=redis://localhost:6379/0
```

---

## 7. 数据流示例(端到端)

**场景**: 加一个「微博热搜图文」数据源, 抓下来, 自动存图, 跑缩略图, OCR 文字, 导出训练集

```
1. 用户配置 DataSource:
   {
     "name": "微博热搜图文",
     "channel_type": "opencli",
     "channel_config": {
       "site": "weibo",
       "command": "trending",
       "args": {"limit": "20"},
       "format": "json"
     }
   }

2. 定时触发 collect:
   - 调 opencli weibo trending → 返回 20 条 record
   - raw_data 里有 image_urls: ["https://wx1.sinaimg.cn/...jpg", ...]

3. Normalize:
   - title/content/author/published_at 进 normalized_data
   - image_urls 进 extra_image_urls

4. Store:
   - collected_records 写入 (已有逻辑)

5. (新) AssetDetector 触发:
   - 扫 extra_image_urls
   - 写 media_assets (kind=image, source_url=..., status=pending)
   - 返回 20 个 MediaAsset (假设每条有 3 张图)

6. (新) Downloader 异步:
   - httpx 拉每张图, 写 LocalFS / S3
   - 更新 asset.status=ready, file_hash, file_size

7. (新) Processors 异步:
   - ImageThumbnailer: 生成 256x256 webp 预览
   - (可选) OcrEngine: tesseract 抽图里的中文
   - 写 media_text (source=ocr, text=...)
   - 更新 asset.processed_jobs

8. 前端 RecordsPage:
   - 显示 record 时, 拉 /api/v1/media/assets?record_id=...
   - 渲染 Gallery 视图 (缩略图 grid + 灯箱)

9. (新) Dataset 导出:
   - POST /api/v1/datasets/export {format: "coco", filters: {since: "..."}}
   - 后台任务: 拉所有有 media_labels 的 asset
   - 写 annotations.json + 拷贝图片到 ./stanza-train-2026-06/
   - 给你手动喂给 stanza 训练
```

---

## 8. 阶段化(M1-M5)

### M1 — 媒体能存 + 能看 (1-2 周)
- [ ] `media_assets` 表 + alembic 迁移
- [ ] `MediaStore` 抽象 + `LocalFSStore`
- [ ] `AssetDetector` (HTML + URL)
- [ ] `Downloader` worker (asyncio)
- [ ] 前端 `<MediaGallery>` (图墙 + 灯箱)
- [ ] API: 列表/详情/文件/预览
- [ ] 测试: pytest (~25 用例) + 端到端 demo (curl + 浏览器)

### M2 — 媒体能处理 (1-2 周)
- [ ] `MediaProcessor` 抽象 + 4 个内置:
  - `ImageThumbnailer` (Pillow)
  - `PdfExtractor` (pypdf)
  - `AudioTranscriber` (faster-whisper, 可选)
  - `VideoMetadata` (ffprobe)
- [ ] `media_text` 表
- [ ] 前端: PDF 预览, 音频波形, 缩略图
- [ ] 测试: ~20 用例

### M3 — 多模态 + 检索 (1-2 周)
- [ ] `MediaIndex` 抽象 + DuckDB 实现
- [ ] `ClipEmbedder` (sentence-transformers)
- [ ] `media_features` 表
- [ ] 前端: 跨记录相似图检索, 按文本搜图
- [ ] 测试: ~15 用例

### M4 — 训练 ETL + stanza 集成 (1-2 周)
- [ ] `/api/v1/datasets/*` 端点
- [ ] `CocoExporter` / `YoloExporter` / `ParquetExporter`
- [ ] 独立 `opencli-export` CLI
- [ ] README: stanza 调用示例
- [ ] 测试: ~15 用例

### M5 — 分布式存储 + 生产化 (可选, 1-2 周)
- [ ] `S3Store` (boto3)
- [ ] Celery + Redis 异步队列
- [ ] 签名 URL / CDN
- [ ] 反垃圾(去重, 大小限制, MIME 白名单)
- [ ] 媒体配额 / 容量监控

---

## 9. 风险与开放问题

| 风险 | 缓解 |
|---|---|
| **大文件存储膨胀** | M5 配额 / LRU 淘汰 / 软链接到外部 |
| **CDP 截图孤儿** | Detector 阶段直接归到 record, 不留孤岛 |
| **向量检索性能** | M3 起步用 DuckDB, 后续换 pgvector / Milvus |
| **whisper / clip 模型体积大** | 默认 disabled, 按需启用 |
| **SQLite 全文检索** | FTS5 起步, 生产 PG 换 tsvector |
| **与原项目 PR 冲突** | 自己 fork, 长期看 PR 价值决定是否合入上游 |

---

## 10. 文件清单(预计)

**新增** (~30 个文件):

```
backend/
├── media/
│   ├── __init__.py
│   ├── models.py              # MediaAsset, MediaText, MediaFeature, MediaLabel
│   ├── schemas.py             # Pydantic
│   ├── detector.py            # 主 detector 协调
│   ├── detectors/
│   │   ├── base.py
│   │   ├── html.py
│   │   ├── url.py
│   │   └── json_field.py
│   ├── store/
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── s3.py              # M5
│   │   └── factory.py
│   ├── index/
│   │   ├── base.py
│   │   ├── sqlite.py
│   │   ├── duckdb.py          # M3
│   │   └── factory.py
│   ├── processors/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── image_thumbnail.py
│   │   ├── pdf_extract.py
│   │   ├── audio_transcribe.py
│   │   ├── video_metadata.py
│   │   └── clip_embed.py      # M3
│   ├── downloader.py          # 异步下载 worker
│   └── runner.py              # processor 调度
├── datasets/
│   ├── __init__.py
│   ├── exporters/
│   │   ├── base.py
│   │   ├── coco.py
│   │   ├── yolo.py
│   │   └── parquet.py
│   └── cli.py                 # opencli-export 入口
├── migrations/versions/
│   └── m3n4o5p6q7r8_add_media_tables.py   # 一次性建 4 张表
├── api/v1/
│   ├── media.py
│   └── datasets.py
└── tests/
    ├── unit/media/
    │   ├── test_detector.py
    │   ├── test_store_local.py
    │   ├── test_processors.py
    │   └── test_models.py
    └── integration/
        └── test_media_e2e.py
```

**前端** (~10 个文件):
```
frontend/src/
├── pages/
│   └── MediaPage.tsx                 # 新页面
├── components/
│   ├── MediaGallery.tsx
│   ├── MediaPlayer.tsx               # 视频
│   ├── AudioPlayer.tsx               # 音频 + 波形
│   ├── PdfPreview.tsx
│   └── LabelEditor.tsx
├── api/
│   └── media.ts                      # API client
└── i18n/locales/{en,zh}/media.json
```

**独立工具**:
```
tools/opencli-export/
├── pyproject.toml
└── src/opencli_export/
    ├── __init__.py
    └── cli.py
```

---

## 11. 与现有架构的对接点

| 现有 | 新增/改动 |
|---|---|
| `backend/pipeline/pipeline.py` | 加 step 5.5: `await detector.detect_for_record(record)` |
| `backend/pipeline/runner.py` | 不变 |
| `backend/api/v1/records.py` | 加 `/records/{id}/media` 子资源 |
| `backend/models/__init__.py` | 加 4 个新 model 的 export |
| `backend/config.py` | 加 `MediaSettings` |
| `backend/main.py` | 启动时调 `media.downloader.start()` |

---

## 12. 验收标准

### M1 验收
- [ ] 4 个新表迁移能跑
- [ ] pytest 全过 (新增 ~25 用例)
- [ ] 真实端到端 demo: 配一个 web scraper 数据源 → 抓一篇带图的网页 → 图出现在前端 Gallery → 详情页可点开看大图
- [ ] 手动跑 `opencli-export --format parquet --limit 5` 能导出

### 后续阶段
每阶段加 ~20 用例 + 真实场景验证

---

**TODO**(审稿时请关注):
1. `media_assets` 字段是否齐全? 缺什么?
2. Detector 三种 (HTML/URL/JSON) 覆盖度够吗? 还需要什么?
3. M1 范围 OK 吗, 还是想 M1+ M2 一起?
4. 训练 ETL 优先 COCO 还是 YOLO? (YOLO 适合目标检测, COCO 适合多任务)
5. stanza-public-clean 是什么类型任务? 分类? 检测? 分割? (决定 label_type 默认形态)
