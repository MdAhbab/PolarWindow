"""mission schema v2: the lifecycle facts of each mission (ADR-10)

One JSONB column: vehicle, pad, T-0, transfer, descent, radio, spacecraft,
rovers, return, and the URL each came from. Nullable, so a v1 load still
works; ``make missions`` fills it.

Revision ID: a4c6e8f0b2d1
Revises: 9b3e5d7f1a22
Create Date: 2026-09-27 05:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4c6e8f0b2d1"
down_revision: str | None = "9b3e5d7f1a22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("missions", sa.Column("lifecycle", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("missions", "lifecycle")
