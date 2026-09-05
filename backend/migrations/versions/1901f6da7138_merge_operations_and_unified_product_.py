"""merge operations and unified product heads

Revision ID: 1901f6da7138
Revises: f5a6b7c8d9e0, w3c4d5e6f7g8
Create Date: 2026-07-26 00:02:50.017059

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '1901f6da7138'
down_revision: str | tuple[str, str] = ('f5a6b7c8d9e0', 'w3c4d5e6f7g8')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
