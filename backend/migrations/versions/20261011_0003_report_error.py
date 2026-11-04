"""report delivery error

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("report_error", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("scans", "report_error")
