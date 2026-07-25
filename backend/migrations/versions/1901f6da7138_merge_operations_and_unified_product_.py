"""merge operations and unified product heads

Revision ID: 1901f6da7138
Revises: f5a6b7c8d9e0, w3c4d5e6f7g8
Create Date: 2026-07-26 00:02:50.017059

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1901f6da7138'
down_revision: Union[str, None] = ('f5a6b7c8d9e0', 'w3c4d5e6f7g8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
