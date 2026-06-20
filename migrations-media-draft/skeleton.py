"""接口骨架: backend/media/ 核心类型 + 类签名.

不是可运行代码, 是设计草稿, 给你审 API 形态.
详情见 docs/media-superset/DESIGN.md

文件组织:
  backend/media/
  ├── models.py            ← SQLAlchemy 模型
  ├── schemas.py           ← Pydantic schemas (API DTO)
  ├── detector.py          ← AssetDetector 主类
  ├── downloader.py        ← 异步下载
  ├── runner.py            ← processor 调度
  ├── store/base.py        ← MediaStore 抽象
  ├── store/local.py
  ├── store/factory.py
  ├── index/base.py        ← MediaIndex 抽象 (M3)
  ├── index/sqlite.py
  ├── processors/base.py   ← MediaProcessor 抽象
  ├── processors/registry.py
  └── detectors/...
"""

# ─── backend/media/models.py ──────────────────────────────────────────────

from datetime import datetime
from typing import Any, Optional
from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.models.base import TimestampMixin


class MediaAsset(TimestampMixin):
    """媒体资产. 见 DESIGN §2.1."""
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("collected_records.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)         # image|video|audio|document
    mime_type: Mapped[Optional[str]] = mapped_column(String(64))
    file_extension: Mapped[Optional[str]] = mapped_column(String(8))

    source_url: Mapped[Optional[str]] = mapped_column(Text)
    referer_url: Mapped[Optional[str]] = mapped_column(Text)
    discovered_by: Mapped[str] = mapped_column(String(32), nullable=False, default="detector")

    storage_backend: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    download_error: Mapped[Optional[str]] = mapped_column(Text)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    processed_jobs: Mapped[list] = mapped_column(JSON, default=list)


class MediaText(TimestampMixin):
    """媒体派生文本. 见 DESIGN §2.2."""
    __tablename__ = "media_text"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)

    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # ocr|asr|...
    language: Mapped[Optional[str]] = mapped_column(String(8))

    text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[Optional[dict]] = mapped_column(JSON)
    summary: Mapped[Optional[str]] = mapped_column(Text)

    start_sec: Mapped[Optional[float]] = mapped_column(Float)
    end_sec: Mapped[Optional[float]] = mapped_column(Float)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)

    model_name: Mapped[Optional[str]] = mapped_column(String(64))
    model_version: Mapped[Optional[str]] = mapped_column(String(32))
    confidence: Mapped[Optional[float]] = mapped_column(Float)


class MediaFeature(TimestampMixin):
    """媒体特征向量. 见 DESIGN §2.3."""
    __tablename__ = "media_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)

    feature_type: Mapped[str] = mapped_column(String(16), nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(64))
    model_version: Mapped[Optional[str]] = mapped_column(String(32))


class MediaLabel(TimestampMixin):
    """媒体标签 — 训练目标. 见 DESIGN §2.4."""
    __tablename__ = "media_labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)

    source: Mapped[str] = mapped_column(String(16), nullable=False)
    annotator: Mapped[Optional[str]] = mapped_column(String(64))

    label_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    split: Mapped[Optional[str]] = mapped_column(String(8), index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ─── backend/media/schemas.py ──────────────────────────────────────────────
# Pydantic DTO, 给 API 用. 这里只列关键 fields.

from pydantic import BaseModel, Field


class MediaAssetResponse(BaseModel):
    id: str
    record_id: str
    source_id: str
    kind: str           # image|video|audio|document
    mime_type: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    status: str        # pending|downloading|ready|error
    source_url: str | None = None
    width: int | None = None
    height: int | None = None
    duration_sec: float | None = None
    page_count: int | None = None
    preview_url: str | None = None       # 缩略图 URL (computed)
    download_url: str | None = None      # 原始文件 URL (computed, signed)
    text_outputs: list["MediaTextResponse"] = []
    feature_count: int = 0
    label_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MediaTextResponse(BaseModel):
    id: str
    source: str         # ocr|asr|...
    language: str | None
    text: str
    summary: str | None = None
    entities: dict | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    page_number: int | None = None
    confidence: float | None = None
    model_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MediaLabelCreate(BaseModel):
    label_type: str = Field(..., description="category|bbox|segmentation|classification|caption")
    label_value: dict
    confidence: float | None = None
    split: str | None = None
    notes: str | None = None
    source: str = "human"


class MediaLabelResponse(MediaLabelCreate):
    id: str
    asset_id: str
    annotator: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MediaAssetListResponse(BaseModel):
    data: list[MediaAssetResponse]
    total: int
    page: int
    limit: int


# ─── backend/media/store/base.py ──────────────────────────────────────────

from abc import ABC, abstractmethod
from typing import AsyncIterator


class MediaStore(ABC):
    """文件存储抽象. 多种 backend (local/s3/gcs) 共用同一接口."""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """存文件, 返回最终 key (可能后端会重命名)."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """读文件. 找不到抛 FileNotFoundError."""

    @abstractmethod
    async def stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """流式读, 大文件用."""

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def size(self, key: str) -> int: ...

    @abstractmethod
    async def url_for(self, key: str, expires: int = 3600) -> str:
        """返回前端可访问的 URL.
        - local backend: /api/v1/media/assets/{id}/file
        - s3 backend: presigned URL
        """

    @abstractmethod
    async def list(self, prefix: str = "", limit: int = 1000) -> list[str]: ...


# ─── backend/media/store/local.py ─────────────────────────────────────────

class LocalFSStore(MediaStore):
    """本地文件系统. 默认 backend."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 防 path traversal: 拒绝 ../ 和绝对路径
        if ".." in key or key.startswith("/") or key.startswith("\\"):
            raise ValueError(f"Invalid key: {key!r}")
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError(f"Key escapes root: {key!r}")
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(p, "wb") as f:
            await f.write(data)
        return key

    async def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.exists():
            raise FileNotFoundError(key)
        async with aiofiles.open(p, "rb") as f:
            return await f.read()

    # ... 其他方法类似

    async def url_for(self, key: str, expires: int = 3600) -> str:
        # 本地 backend 不签名, 直接返回代理 URL
        # 前端用这个 URL 走 /api/v1/media/assets/{id}/file 拿内容
        return f"/api/v1/media/proxy?key={quote(key)}"


# ─── backend/media/processors/base.py ─────────────────────────────────────

class MediaProcessor(ABC):
    """媒体处理器抽象. 多个 processor 由 registry 管理."""

    processor_type: str
    supported_kinds: list[str]   # ["image"] | ["video", "audio"] | ["document"]

    @abstractmethod
    async def process(
        self, asset: MediaAsset, store: MediaStore
    ) -> "ProcessResult": ...


@dataclass
class ProcessResult:
    ok: bool
    error: str | None = None

    # 派生数据
    meta_updates: dict[str, Any] = field(default_factory=dict)    # 回写到 MediaAsset (width/height/duration_sec/...)
    text_outputs: list[dict] = field(default_factory=list)         # 待插入 MediaText
    feature_outputs: list[dict] = field(default_factory=list)      # 待插入 MediaFeature
    file_outputs: list[dict] = field(default_factory=list)         # 派生文件 (key, kind, mime, role=preview|transcoded|...)


# ─── backend/media/processors/registry.py ────────────────────────────────

_PROCESSORS: dict[str, MediaProcessor] = {}


def register_processor(cls):
    inst = cls()
    _PROCESSORS[inst.processor_type] = inst
    return cls


def get_processor(p: str) -> MediaProcessor:
    if p not in _PROCESSORS:
        raise ValueError(f"Unknown processor: {p!r}")
    return _PROCESSORS[p]


def list_processors() -> list[str]:
    return list(_PROCESSORS.keys())


# ─── backend/media/processors/image_thumbnail.py ──────────────────────────
# 示例: ImageThumbnailer (M1 就要做)

@register_processor
class ImageThumbnailer(MediaProcessor):
    """图片缩略图. 输入: 任意 image. 输出: 256x256 webp."""

    processor_type = "image_thumbnail"
    supported_kinds = ["image"]

    async def process(self, asset, store):
        from PIL import Image

        try:
            data = await store.get(asset.storage_key)
            img = Image.open(BytesIO(data))
        except Exception as e:
            return ProcessResult(ok=False, error=f"open image failed: {e}")

        # 生成预览
        img.thumbnail((256, 256))
        buf = BytesIO()
        img.save(buf, "WEBP", quality=80)
        preview_key = f"preview/{asset.id}.webp"
        await store.put(preview_key, buf.getvalue(), "image/webp")

        return ProcessResult(
            ok=True,
            meta_updates={"width": img.width, "height": img.height},
            file_outputs=[{
                "key": preview_key, "kind": "image", "mime": "image/webp",
                "role": "preview", "size": len(buf.getvalue()),
            }],
        )


# ─── backend/media/detector.py ────────────────────────────────────────────

@dataclass
class MediaRef:
    """Detector 发现的媒体引用."""
    url: str
    kind: str           # image|video|audio|document
    referer_url: str | None = None
    mime_hint: str | None = None
    discovered_by: str = "detector"     # html|url|json_field


class AssetDetector:
    """主 detector 协调器. 扫一条 record, 抽所有媒体引用."""

    URL_PATTERNS = {
        "image":    re.compile(r"https?://[^\s\"']+\.(?:jpg|jpeg|png|gif|webp|avif|svg)(?:\?[^\s\"']*)?", re.I),
        "video":    re.compile(r"https?://[^\s\"']+\.(?:mp4|webm|m3u8|flv|mov)(?:\?[^\s\"']*)?", re.I),
        "audio":    re.compile(r"https?://[^\s\"']+\.(?:mp3|wav|m4a|ogg|aac|flac)(?:\?[^\s\"']*)?", re.I),
        "document": re.compile(r"https?://[^\s\"']+\.(?:pdf|docx?|xlsx?|pptx?)(?:\?[^\s\"']*)?", re.I),
    }

    def __init__(self, sub_detectors: list["SubDetector"] | None = None):
        self.detectors = sub_detectors or [
            HtmlDetector(),
            UrlDetector(),
            JsonFieldDetector(),
        ]

    async def detect_for_record(self, record: CollectedRecord) -> list[MediaAsset]:
        refs: list[MediaRef] = []
        for det in self.detectors:
            refs.extend(await det.scan(record))

        # 去重
        seen = set()
        unique = []
        for r in refs:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)

        # 入库
        assets: list[MediaAsset] = []
        for ref in unique:
            asset = MediaAsset(
                id=uuid4().hex,
                record_id=record.id,
                source_id=record.source_id,
                kind=ref.kind,
                source_url=ref.url,
                referer_url=ref.referer_url,
                mime_type=ref.mime_hint,
                discovered_by=ref.discovered_by,
                storage_backend="",         # 待下载后填
                storage_key="",             # 待下载后填
                status="pending",
            )
            session.add(asset)
            assets.append(asset)
        await session.flush()
        return assets


# ─── backend/media/downloader.py ──────────────────────────────────────────

class MediaDownloader:
    """异步下载 worker. M1 用 asyncio 循环, M5 换 Celery."""

    def __init__(self, store: MediaStore, batch_size: int = 20, max_retries: int = 3):
        self.store = store
        self.batch_size = batch_size
        self.max_retries = max_retries

    async def run_forever(self):
        """M1 实现. 简单 sleep 循环."""
        logger.info("media downloader started")
        while True:
            try:
                n = await self.process_batch()
                if n == 0:
                    await asyncio.sleep(10)
                else:
                    logger.info("downloaded %d assets", n)
            except Exception as e:
                logger.exception("downloader loop error: %s", e)
                await asyncio.sleep(30)

    async def process_batch(self) -> int:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(MediaAsset)
                .where(MediaAsset.status == "pending")
                .order_by(MediaAsset.created_at)
                .limit(self.batch_size)
            )
            assets = (await session.execute(stmt)).scalars().all()

        n_ok = 0
        for asset in assets:
            ok = await self._download_one(asset)
            if ok:
                n_ok += 1
        return n_ok

    async def _download_one(self, asset: MediaAsset) -> bool:
        # 详见 DESIGN §4.2
        ...


# ─── backend/api/v1/media.py ──────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/assets", response_model=MediaAssetListResponse)
async def list_assets(
    record_id: str | None = None,
    source_id: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """列表. 支持按 record_id / source_id / kind / status 过滤."""
    ...


@router.get("/assets/{asset_id}", response_model=MediaAssetResponse)
async def get_asset(asset_id: str):
    """详情. 包含 text_outputs 列表."""
    ...


@router.get("/assets/{asset_id}/file")
async def get_asset_file(asset_id: str):
    """原始文件. 重定向到 storage.url_for()."""
    ...


@router.get("/assets/{asset_id}/preview")
async def get_asset_preview(asset_id: str):
    """缩略图 (image webp / 视频首帧 / 音频波形 PNG)."""
    ...


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str):
    """删除 asset + 存储文件 + 级联 text/feature/label."""
    ...


@router.post("/assets/{asset_id}/process")
async def trigger_process(asset_id: str, processors: list[str] | None = None):
    """手动触发处理. processors 为空则跑所有支持的."""
    ...


@router.post("/assets/{asset_id}/labels", response_model=MediaLabelResponse)
async def add_label(asset_id: str, payload: MediaLabelCreate):
    """打标签 (训练目标)."""
    ...


@router.get("/processors")
async def list_processors():
    """列出所有注册的 processor + 它支持的 kind."""
    return [
        {"type": p.processor_type, "kinds": p.supported_kinds}
        for p in _PROCESSORS.values()
    ]


# ─── backend/api/v1/datasets.py ──────────────────────────────────────────

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


class DatasetFilters(BaseModel):
    kinds: list[str] | None = None
    label_types: list[str] | None = None
    has_labels: bool | None = None
    since: datetime | None = None
    until: datetime | None = None
    split: str | None = None
    limit: int | None = None


class DatasetExportRequest(BaseModel):
    format: str  # coco|yolo|parquet|csv
    filters: DatasetFilters = Field(default_factory=DatasetFilters)
    output_dir: str | None = None  # null = server default


@router.post("/export")
async def start_export(payload: DatasetExportRequest, background: bool = True):
    """异步导出. 返回 export_id, 用 GET /exports/{id} 查状态."""
    ...


@router.get("/exports")
async def list_exports():
    """历史导出任务."""
    ...


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str):
    """下载导出产物 (zip)."""
    ...


# ─── tools/opencli-export/src/opencli_export/cli.py ───────────────────────

import typer

app = typer.Typer()


@app.command()
def main(
    format: str = typer.Option(..., help="coco|yolo|parquet|csv"),
    output: Path = typer.Option(..., help="output directory"),
    since: datetime | None = typer.Option(None),
    until: datetime | None = typer.Option(None),
    kind: list[str] | None = typer.Option(None),
    split: str | None = typer.Option(None),
    incremental: bool = typer.Option(False),
    sqlite_path: str = typer.Option("./data/opencli-admin.db"),
    limit: int | None = typer.Option(None),
):
    """独立 CLI: 读 opencli-admin SQLite, 导出训练集."""
    # 1. 打开 sqlite (只读)
    # 2. 查 media_assets + media_labels
    # 3. 调对应 exporter
    # 4. 写 output/
    ...


if __name__ == "__main__":
    app()
