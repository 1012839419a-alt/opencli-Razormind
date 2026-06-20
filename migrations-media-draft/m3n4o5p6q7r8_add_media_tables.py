"""add media tables (media_assets, media_text, media_features, media_labels)

Revision ID: m3n4o5p6q7r8
Revises: l2g3h4i5j6k7
Create Date: 2026-06-15

草稿, 待审. 详见 docs/media-superset/DESIGN.md
"""
from alembic import op
import sqlalchemy as sa


revision = 'm3n4o5p6q7r8'
down_revision = 'l2g3h4i5j6k7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── media_assets ───────────────────────────────────────────────────────
    op.create_table(
        'media_assets',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('record_id', sa.String(36), sa.ForeignKey('collected_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_id', sa.String(36), nullable=False),

        sa.Column('kind', sa.String(16), nullable=False),       # image|video|audio|document
        sa.Column('mime_type', sa.String(64), nullable=True),
        sa.Column('file_extension', sa.String(8), nullable=True),

        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('referer_url', sa.Text(), nullable=True),
        sa.Column('discovered_by', sa.String(32), nullable=False, server_default='detector'),

        sa.Column('storage_backend', sa.String(16), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('file_hash', sa.String(64), nullable=True),

        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('download_error', sa.Text(), nullable=True),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=True),

        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('duration_sec', sa.Float(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('processed_jobs', sa.JSON(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_media_assets_record_id', 'media_assets', ['record_id'])
    op.create_index('ix_media_assets_source_id', 'media_assets', ['source_id'])
    op.create_index('ix_media_assets_kind', 'media_assets', ['kind'])
    op.create_index('ix_media_assets_status', 'media_assets', ['status'])
    op.create_index('ix_media_assets_file_hash', 'media_assets', ['file_hash'])
    # 复合: 待处理队列查询常用
    op.create_index('ix_media_assets_kind_status', 'media_assets', ['kind', 'status'])

    # ── media_text ─────────────────────────────────────────────────────────
    op.create_table(
        'media_text',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('asset_id', sa.String(36), sa.ForeignKey('media_assets.id', ondelete='CASCADE'), nullable=False),

        sa.Column('source', sa.String(16), nullable=False),     # ocr|asr|pdf_extract|docx_extract|llm_caption
        sa.Column('language', sa.String(8), nullable=True),

        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('entities', sa.JSON(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),

        sa.Column('start_sec', sa.Float(), nullable=True),
        sa.Column('end_sec', sa.Float(), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),

        sa.Column('model_name', sa.String(64), nullable=True),
        sa.Column('model_version', sa.String(32), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_media_text_asset_id', 'media_text', ['asset_id'])
    op.create_index('ix_media_text_source', 'media_text', ['source'])

    # SQLite FTS5 (async 模式下 sqlite 没法直接用, 留空给后续 PRAGMA)
    # 实际项目中可能用 PG 替代, 这里仅作 placeholder
    # op.execute("CREATE VIRTUAL TABLE media_text_fts USING fts5(text, content='media_text', content_rowid='rowid')")

    # ── media_features ─────────────────────────────────────────────────────
    op.create_table(
        'media_features',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('asset_id', sa.String(36), sa.ForeignKey('media_assets.id', ondelete='CASCADE'), nullable=False),

        sa.Column('feature_type', sa.String(16), nullable=False),  # clip|vit|audio_embed|custom
        sa.Column('vector', sa.LargeBinary(), nullable=False),
        sa.Column('dim', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(64), nullable=True),
        sa.Column('model_version', sa.String(32), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_media_features_asset_id', 'media_features', ['asset_id'])
    op.create_index('ix_media_features_type', 'media_features', ['feature_type'])

    # ── media_labels ───────────────────────────────────────────────────────
    op.create_table(
        'media_labels',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('asset_id', sa.String(36), sa.ForeignKey('media_assets.id', ondelete='CASCADE'), nullable=False),

        sa.Column('source', sa.String(16), nullable=False),   # human|auto|llm
        sa.Column('annotator', sa.String(64), nullable=True),

        sa.Column('label_type', sa.String(32), nullable=False),  # category|bbox|segmentation|classification|caption
        sa.Column('label_value', sa.JSON(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),

        sa.Column('split', sa.String(8), nullable=True),       # train|val|test
        sa.Column('notes', sa.Text(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_media_labels_asset_id', 'media_labels', ['asset_id'])
    op.create_index('ix_media_labels_label_type', 'media_labels', ['label_type'])
    op.create_index('ix_media_labels_split', 'media_labels', ['split'])


def downgrade() -> None:
    op.drop_index('ix_media_labels_split', table_name='media_labels')
    op.drop_index('ix_media_labels_label_type', table_name='media_labels')
    op.drop_index('ix_media_labels_asset_id', table_name='media_labels')
    op.drop_table('media_labels')

    op.drop_index('ix_media_features_type', table_name='media_features')
    op.drop_index('ix_media_features_asset_id', table_name='media_features')
    op.drop_table('media_features')

    op.drop_index('ix_media_text_source', table_name='media_text')
    op.drop_index('ix_media_text_asset_id', table_name='media_text')
    op.drop_table('media_text')

    op.drop_index('ix_media_assets_kind_status', table_name='media_assets')
    op.drop_index('ix_media_assets_file_hash', table_name='media_assets')
    op.drop_index('ix_media_assets_status', table_name='media_assets')
    op.drop_index('ix_media_assets_kind', table_name='media_assets')
    op.drop_index('ix_media_assets_source_id', table_name='media_assets')
    op.drop_index('ix_media_assets_record_id', table_name='media_assets')
    op.drop_table('media_assets')
