"""add durable Gaojixing conversation cleanup checkpoint

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a5, l9m0n1o2p3q4
"""

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = ("b9c0d1e2f3a5", "l9m0n1o2p3q4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gaojixing_question_checkpoints",
        sa.Column(
            "conversation_cleanup_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("gaojixing_question_checkpoints", "conversation_cleanup_pending")
