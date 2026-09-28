"""lifecycle foundations: users, the audit chain, feeds, jobs and assessments

ADR-8 (feed snapshots and health), ADR-12 (jobs, assessments and their
inputs), ADR-17 (named users and the append-only, hash-chained audit log).

The audit chain lives in the database, not in Python: a BEFORE INSERT trigger
takes a transaction-scoped advisory lock, numbers the entry, links it to the
previous hash and computes its own with ``audit_hash``. ``audit_verify()``
recomputes the chain with the same function, so the rule is written once.
Another trigger refuses UPDATE, DELETE and TRUNCATE on the log.

Additive: the previous image ignores every table here.

Revision ID: 8d4f1a2b6c90
Revises: 5e8a2f7c1d44
Create Date: 2026-09-27 02:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8d4f1a2b6c90"
down_revision: str | None = "5e8a2f7c1d44"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)

#: One statement each: asyncpg runs a prepared statement, which holds one command.
_AUDIT_SQL = r"""
CREATE FUNCTION audit_hash(
    prev text, seq bigint, at timestamptz, user_id integer, actor text, action text,
    entity text, entity_id text, mission_id text, before jsonb, after jsonb,
    note text, request_id text
) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT encode(sha256(convert_to(concat_ws(chr(31),
        prev,
        seq::text,
        to_char(at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        coalesce(user_id::text, ''),
        actor, action, entity, entity_id,
        coalesce(mission_id, ''),
        coalesce(before::text, 'null'),
        coalesce(after::text, 'null'),
        coalesce(note, ''),
        coalesce(request_id, '')
    ), 'UTF8')), 'hex')
$$;

CREATE FUNCTION audit_chain() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    last_seq bigint;
    last_hash text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('audit_log'));
    SELECT a.seq, a.hash INTO last_seq, last_hash FROM audit_log a ORDER BY a.seq DESC LIMIT 1;
    NEW.seq := coalesce(last_seq, 0) + 1;
    NEW.at := clock_timestamp();
    NEW.prev_hash := coalesce(last_hash, repeat('0', 64));
    NEW.hash := audit_hash(NEW.prev_hash, NEW.seq, NEW.at, NEW.user_id, NEW.actor, NEW.action,
        NEW.entity, NEW.entity_id, NEW.mission_id, NEW.before, NEW.after, NEW.note,
        NEW.request_id);
    RETURN NEW;
END
$$;

CREATE FUNCTION audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$;

CREATE TRIGGER audit_log_chain BEFORE INSERT ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_chain();

CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_append_only();

CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_append_only();

-- The first entry whose link or hash does not recompute, or null; and how
-- many entries were checked.
CREATE FUNCTION audit_verify(OUT first_bad bigint, OUT checked bigint)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r record;
    expected_prev text := repeat('0', 64);
BEGIN
    first_bad := NULL;
    checked := 0;
    FOR r IN SELECT * FROM audit_log ORDER BY seq LOOP
        checked := checked + 1;
        IF r.prev_hash <> expected_prev OR r.hash <> audit_hash(r.prev_hash, r.seq, r.at,
            r.user_id, r.actor, r.action, r.entity, r.entity_id, r.mission_id, r.before,
            r.after, r.note, r.request_id) THEN
            first_bad := r.seq;
            RETURN;
        END IF;
        expected_prev := r.hash;
    END LOOP;
END
$$;
"""
AUDIT_SQL: tuple[str, ...] = tuple(
    part.strip().rstrip(";") + ";" for part in _AUDIT_SQL.split(";\n\n") if part.strip()
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("team", sa.String(120), nullable=True),
        sa.Column("name_key", sa.String(250), nullable=False, unique=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", _TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor", sa.String(250), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("entity", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(160), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity", "entity_id"])
    for statement in AUDIT_SQL:
        op.execute(statement)

    op.create_table(
        "feed_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("location_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("issued_at", _TS, nullable=True),
        sa.Column("valid_from", _TS, nullable=True),
        sa.Column("valid_to", _TS, nullable=True),
        sa.Column("fetched_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("raw", sa.LargeBinary(), nullable=True),
        sa.Column("raw_ref", sa.Text(), nullable=True),
        sa.Column("raw_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed", postgresql.JSONB(), nullable=True),
        sa.Column("parser_version", sa.String(24), nullable=False),
        sa.Column("licence", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("issues", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("of_record", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_feed_latest", "feed_snapshots", ["provider", "product", "location_key", "fetched_at"]
    )
    # One good snapshot per distinct body per issue time (PostgreSQL 15+).
    op.execute(
        "CREATE UNIQUE INDEX uq_feed_body ON feed_snapshots "
        "(provider, product, location_key, issued_at, content_sha256) NULLS NOT DISTINCT "
        "WHERE status = 'ok'"
    )

    op.create_table(
        "feed_health",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("product", sa.String(64), primary_key=True),
        sa.Column("location_key", sa.String(64), primary_key=True, server_default=""),
        sa.Column("licence", sa.String(200), nullable=False, server_default=""),
        sa.Column("staleness_budget_s", sa.Integer(), nullable=False),
        sa.Column("interval_s", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", _TS, nullable=True),
        sa.Column("last_ok_at", _TS, nullable=True),
        sa.Column("last_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("next_run_at", _TS, nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
    )

    op.create_table(
        "feed_limits",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("breaker", sa.String(12), nullable=False, server_default="closed"),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opened_at", _TS, nullable=True),
        sa.Column("tokens", sa.Float(), nullable=False),
        sa.Column("capacity", sa.Float(), nullable=False),
        sa.Column("refill_per_s", sa.Float(), nullable=False),
        sa.Column("tokens_at", _TS, nullable=False),
    )

    op.create_table(
        "assessments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("closure", sa.String(128), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("code_version", sa.String(64), nullable=False),
        sa.Column("of_record", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("compute_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_assessment_key", "assessments", ["kind", "params_hash", "closure", "created_at"]
    )

    op.create_table(
        "assessment_inputs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "assessment_id",
            sa.BigInteger(),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("ref", sa.String(200), nullable=False),
        sa.Column("version", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "snapshot_id", sa.BigInteger(), sa.ForeignKey("feed_snapshots.id"), nullable=True
        ),
    )
    op.create_index("ix_assessment_inputs_assessment", "assessment_inputs", ["assessment_id"])
    op.create_index("ix_assessment_inputs_snapshot", "assessment_inputs", ["snapshot_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("closure", sa.String(128), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("run_after", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(80), nullable=True),
        sa.Column("lease_until", _TS, nullable=True),
        sa.Column("heartbeat_at", _TS, nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "assessment_id",
            sa.BigInteger(),
            sa.ForeignKey("assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", _TS, nullable=True),
        sa.Column("finished_at", _TS, nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_status"
        ),
    )
    op.create_index(
        "uq_jobs_in_flight",
        "jobs",
        ["kind", "params_hash", "closure"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "priority", "run_after"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("assessment_inputs")
    op.drop_table("assessments")
    op.drop_table("feed_limits")
    op.drop_table("feed_health")
    op.drop_table("feed_snapshots")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_chain ON audit_log")
    op.drop_table("audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_verify()")
    op.execute("DROP FUNCTION IF EXISTS audit_append_only()")
    op.execute("DROP FUNCTION IF EXISTS audit_chain()")
    op.execute("DROP FUNCTION IF EXISTS audit_hash(text, bigint, timestamptz, integer, text, "
               "text, text, text, text, jsonb, jsonb, text, text)")
    op.drop_table("users")
