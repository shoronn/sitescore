"""no visitor answers (the backup question is gone)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("scans", "answers")


def downgrade() -> None:
    op.add_column("scans", sa.Column("answers", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
                                     nullable=False, server_default=sa.text("'{}'")))
