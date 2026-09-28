"""event lists have no issue time

DONKI's lists (before f1e4d3e) and SWPC's alert list took their newest event's
time as their issue time, so a quiet Sun (no flare for a day, no alert for six
hours) made a list fetched minutes ago look old, and it was hidden as stale.
The parsers now leave it empty, but a fetch whose body is unchanged keeps the
snapshot stored before, with the old time. Clear it: such a list is as new as
the last fetch that found it current.

Revision ID: c2e4a6b8d0f1
Revises: a4c6e8f0b2d1
Create Date: 2026-09-28 22:30:00
"""

from __future__ import annotations

from alembic import op

revision: str = "c2e4a6b8d0f1"
down_revision: str | None = "a4c6e8f0b2d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE feed_snapshots SET issued_at = NULL "
        "WHERE provider = 'donki' OR (provider = 'swpc' AND product = 'alerts')"
    )


def downgrade() -> None:
    # The old times were wrong; nothing to restore.
    pass
