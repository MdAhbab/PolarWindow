"""window-edge flags on reference metrics

A longest night or blackout that touches the edge of its window was ended by
the window, not by the geometry, so the stored duration is a lower bound. The
flags let `/sites` summaries say so instead of presenting a truncated night as
a measured one.

Additive, with a server default, so it applies to a populated table and the
previous image keeps working against it.

Revision ID: 3c1d7e9a4b20
Revises: af5ff894cd2a
Create Date: 2026-09-18 16:40:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "3c1d7e9a4b20"
down_revision: str | None = "af5ff894cd2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_window_metrics",
        sa.Column("longest_dark_open", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "site_window_metrics",
        sa.Column(
            "longest_blackout_open", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("site_window_metrics", "longest_blackout_open")
    op.drop_column("site_window_metrics", "longest_dark_open")
