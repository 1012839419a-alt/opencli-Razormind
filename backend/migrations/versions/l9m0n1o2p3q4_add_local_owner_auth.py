"""add local owner credentials and opaque sessions

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from alembic import op

revision = "l9m0n1o2p3q4"
down_revision = "k8l9m0n1o2p3"
branch_labels = None
depends_on = None


def _timestamps():
    return (
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "local_credentials",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("singleton_key", sa.String(16), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("singleton_key"),
        sa.UniqueConstraint("username"),
        *_timestamps(),
    )
    op.create_table(
        "local_auth_sessions",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash"),
        *_timestamps(),
    )
    op.create_index(
        "ix_local_auth_sessions_expires_at",
        "local_auth_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_local_auth_sessions_expires_at", table_name="local_auth_sessions")
    op.drop_table("local_auth_sessions")
    op.drop_table("local_credentials")
