"""projects: missions the team enters, and the files read into the project form

A project is a mission record with ``origin = 'project'``: it lives in
``missions`` beside the CLPS records, so every section works on it unchanged,
and a re-seed of ``data/missions.json`` replaces catalogue rows only. Every
existing row is a catalogue record, which the server default says exactly.

``project_intakes`` keeps each reading of an uploaded file (what was found and
the words it was found in), never the file itself.

Revision ID: f3a5c7e9b1d2
Revises: e1b3d5f7a9c2
Create Date: 2026-11-10 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3a5c7e9b1d2"
down_revision: str | None = "e1b3d5f7a9c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "missions",
        sa.Column("origin", sa.Text(), nullable=False, server_default="catalogue"),
    )
    op.create_check_constraint(
        "ck_missions_origin", "missions", "origin IN ('catalogue', 'project')"
    )
    op.create_index("ix_missions_origin", "missions", ["origin"])
    op.add_column(
        "missions",
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "missions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # `updated_at` exists since the CLPS missions migration (7b2e4c1d9f30).

    op.create_table(
        "project_intakes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("extracted", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("text_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("method IN ('model', 'rules')", name="ck_project_intakes_method"),
    )


def downgrade() -> None:
    op.drop_table("project_intakes")
    op.drop_column("missions", "created_at")
    op.drop_column("missions", "owner_id")
    op.drop_index("ix_missions_origin", table_name="missions")
    op.drop_constraint("ck_missions_origin", "missions", type_="check")
    op.drop_column("missions", "origin")
