"""the visitor's language on each scan (English or Bangla)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("lang", sa.String(5), nullable=False, server_default="en"))


def downgrade() -> None:
    op.drop_column("scans", "lang")
