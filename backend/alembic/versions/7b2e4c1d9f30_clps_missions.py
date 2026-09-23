"""CLPS missions, their payloads, and mission-target sites (contract v2)

Adds the mission aggregate (ADR-5) and three columns on `sites` that let a CLPS
target be a site with a published coordinate (ADR-6). Every added column has a
server default that describes the existing rows exactly, so the fifteen
candidate sites, their masks and the golden fixtures are untouched.

`elev_m` and `slope_deg` become nullable: a target outside the polar DEM has no
modelled height, and an unknown height is not zero.

Revision ID: 7b2e4c1d9f30
Revises: 3c1d7e9a4b20
Create Date: 2026-09-24 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7b2e4c1d9f30"
down_revision: str | None = "3c1d7e9a4b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sites",
        sa.Column("kind", sa.String(24), nullable=False, server_default="candidate"),
    )
    op.add_column(
        "sites",
        sa.Column(
            "coordinate_rule", sa.String(24), nullable=False, server_default="derived_open_sky"
        ),
    )
    op.add_column(
        "sites",
        sa.Column("terrain_modelled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_sites_kind", "sites", ["kind"])
    op.alter_column("sites", "elev_m", existing_type=sa.Float(), nullable=True)
    op.alter_column("sites", "slope_deg", existing_type=sa.Float(), nullable=True)

    op.create_table(
        "missions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("vehicle_name", sa.String(80), nullable=True),
        sa.Column("task_order", sa.String(40), nullable=True),
        sa.Column("provider", sa.String(120), nullable=True),
        sa.Column("lander", sa.String(120), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("outcome_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("region", sa.String(24), nullable=True),
        sa.Column("target_name", sa.String(160), nullable=True),
        sa.Column("target", postgresql.JSONB(), nullable=True),
        sa.Column("ellipse", postgresql.JSONB(), nullable=True),
        sa.Column("launch", postgresql.JSONB(), nullable=True),
        sa.Column("landing", postgresql.JSONB(), nullable=True),
        sa.Column("end_of_mission", postgresql.JSONB(), nullable=True),
        sa.Column("planned_surface_days", sa.Float(), nullable=True),
        sa.Column("sort_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "site_id",
            sa.String(64),
            sa.ForeignKey("sites.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("unconfirmed_fields", postgresql.JSONB(), nullable=False),
        sa.Column("notes", postgresql.JSONB(), nullable=False),
        sa.Column("data_version", sa.String(64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_missions_provider", "missions", ["provider"])
    op.create_index("ix_missions_status", "missions", ["status"])
    op.create_index("ix_missions_region", "missions", ["region"])
    op.create_index("ix_missions_site_id", "missions", ["site_id"])

    op.create_table(
        "mission_payloads",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(64),
            sa.ForeignKey("missions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("acronym", sa.String(40), nullable=True),
        sa.Column("organisation", sa.String(200), nullable=True),
        sa.Column("instrument_types", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(400), nullable=False),
        sa.Column("unconfirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_mission_payloads_mission_id", "mission_payloads", ["mission_id"])
    op.create_index(
        "ix_payload_types", "mission_payloads", ["instrument_types"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_payload_types", table_name="mission_payloads")
    op.drop_index("ix_mission_payloads_mission_id", table_name="mission_payloads")
    op.drop_table("mission_payloads")
    for ix in ("ix_missions_site_id", "ix_missions_region", "ix_missions_status"):
        op.drop_index(ix, table_name="missions")
    op.drop_index("ix_missions_provider", table_name="missions")
    op.drop_table("missions")
    op.execute("DELETE FROM sites WHERE kind <> 'candidate'")
    op.alter_column("sites", "slope_deg", existing_type=sa.Float(), nullable=False)
    op.alter_column("sites", "elev_m", existing_type=sa.Float(), nullable=False)
    op.drop_index("ix_sites_kind", table_name="sites")
    op.drop_column("sites", "terrain_modelled")
    op.drop_column("sites", "coordinate_rule")
    op.drop_column("sites", "kind")
