"""sign-up without email codes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11 18:00:00

Visitors no longer confirm their address with a code, so the codes table and the
"email verified" date go. Sign-ups that never entered their code (and so never ran
a scan) are removed, as the Privacy page promised for unconfirmed sign-ups.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM leads WHERE email_verified_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM scans WHERE scans.lead_id = leads.id)"
    )
    op.drop_column("leads", "email_verified_at")
    op.drop_index(op.f("ix_email_codes_email"), table_name="email_codes")
    op.drop_table("email_codes")


def downgrade() -> None:
    op.create_table(
        "email_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_codes_email"), "email_codes", ["email"], unique=False)
    op.add_column("leads", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Everyone who signed up meanwhile counts as confirmed, so the older code keeps working.
    op.execute("UPDATE leads SET email_verified_at = created_at")
