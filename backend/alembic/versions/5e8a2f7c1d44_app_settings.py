"""app settings the project manager changes from the dashboard

One key-value table. Additive: the previous image ignores it.

Revision ID: 5e8a2f7c1d44
Revises: 7b2e4c1d9f30
Create Date: 2026-09-24 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "5e8a2f7c1d44"
down_revision: str | None = "7b2e4c1d9f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
