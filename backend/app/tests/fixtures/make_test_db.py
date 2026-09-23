"""Build ``polar_window_test``: the migrations, then a copy of the seeded rows.

Run with ``make test-db``. The integration suite reads real masks and metrics,
which take a seeded database to exist; copying the rows (not the whole
database) keeps the test schema exactly what the migrations produce, and keeps
test writes out of the development database the running app serves.

Uses the PostgreSQL client tools (``dropdb``, ``createdb``, ``pg_dump``,
``psql``), which are installed with the server.
"""

# ruff: noqa: S603, S607 -- runs the local PostgreSQL client tools by name, with
# arguments built from this project's own settings; no external input.
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit

from app.config import get_settings

#: Seeded tables, in foreign-key order. Agent runs are deliberately absent.
TABLES = ("sites", "horizon_masks", "site_window_metrics", "missions", "mission_payloads")


def _conn(url: str) -> tuple[list[str], str]:
    parts = urlsplit(url.replace("+asyncpg", ""))
    q = parse_qs(parts.query)
    host = unquote(q["host"][0]) if "host" in q else (parts.hostname or "localhost")
    port = q.get("port", [str(parts.port or 5432)])[0]
    user = parts.username or "postgres"
    return ["-h", host, "-p", port, "-U", user], parts.path.lstrip("/")


def main() -> None:
    dev_url = get_settings().database_url
    args, dev = _conn(dev_url)
    test = os.environ.get("PW_TEST_DB_NAME", f"{dev}_test")
    if test == dev:
        sys.exit("refusing: the test database name equals the development one")
    subprocess.run(["dropdb", *args, "--if-exists", test], check=True)
    subprocess.run(["createdb", *args, test], check=True)
    env = {**os.environ, "PW_DATABASE_URL": dev_url.replace(f"/{dev}", f"/{test}", 1)}
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    dump = subprocess.run(
        [
            "pg_dump",
            *args,
            "--data-only",
            "--disable-triggers",
            *[f"--table={t}" for t in TABLES],
            dev,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["psql", *args, "-q", "-v", "ON_ERROR_STOP=1", test], input=dump.stdout, check=True
    )
    print(f"{test}: migrated and seeded from {dev} ({', '.join(TABLES)})")


if __name__ == "__main__":
    main()
