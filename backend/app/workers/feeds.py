"""The feeds worker: the one process that fetches from the internet (ADR-8).

``python -m app.workers.feeds`` (or ``make feeds``) runs forever: every due
product is fetched within its provider's limits and stored as a snapshot.
``--once`` fetches what is due and exits (for a cron job, or to fill the
database before a demo). It wakes early on ``NOTIFY pw_feeds``, which the
Settings page's "Refresh now" sends. Old raw bodies nothing depends on are
dropped once a day.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.config import get_settings
from app.db.repositories.feeds import FEEDS_CHANNEL, FeedRepository
from app.db.session import session_scope
from app.feeds import scheduler, targets

log = logging.getLogger("polar_window.feeds")

#: Raw bodies older than this are dropped unless an answer of record used them.
RAW_KEEP_DAYS = 30
TICK_S = 30.0


#: Launch opportunities further ahead than this are past the ensemble forecasts.
FORECAST_REACH = timedelta(days=16)


async def launch_times(region: str) -> list[datetime]:
    """Liftoffs of the designed launch opportunities stored for any mission, from pads in
    ``region``, between now and the ensembles' reach (the GEFS times to fetch, B3)."""
    now = datetime.now(UTC)
    out: set[datetime] = set()
    async with session_scope() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT DISTINCT ON (mission_id) result FROM assessments "
                    "WHERE kind = 'launch' ORDER BY mission_id, id DESC"
                )
            )
        ).scalars()
        for result in rows:
            for o in (result.get("data") or {}).get("opportunities") or []:
                t0 = (o.get("t0") or {}).get("value")
                if o.get("basis") != "designed" or t0 is None:
                    continue
                t = datetime.fromtimestamp(float(t0), UTC)
                if (
                    now <= t <= now + FORECAST_REACH
                    and targets.region_of_pad(o["pad_id"]) == region
                ):
                    out.add(t)
    return sorted(out)


def build() -> scheduler.Scheduler:
    s = get_settings()
    return scheduler.Scheduler(
        products=targets.products(wanted=launch_times),
        providers=targets.providers(),
        raw_root=s.data_dir / "feeds" / "raw",
        secrets=targets.secrets(),
    )


async def run(once: bool) -> None:
    sch = build()
    await sch.sync()
    log.info("feeds worker: %d products from %d providers", len(sch.products), len(sch.providers))
    if once:
        await sch.run_once()
        return
    stop = asyncio.Event()
    wake = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    listener = asyncio.create_task(_listen(wake, stop))
    last_gc = datetime.min.replace(tzinfo=UTC)
    try:
        while not stop.is_set():
            try:
                await sch.run_once()
            except Exception:
                log.exception("feeds loop error")
            if (datetime.now(UTC) - last_gc).total_seconds() > 86_400:
                async with session_scope() as sess:
                    n = await FeedRepository(sess).gc_raw(RAW_KEEP_DAYS)
                log.info("dropped %d old raw bodies", n)
                last_gc = datetime.now(UTC)
            wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), timeout=TICK_S)
    finally:
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener


async def _listen(wake: asyncio.Event, stop: asyncio.Event) -> None:
    import asyncpg

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    while not stop.is_set():
        try:
            conn = await asyncpg.connect(dsn)
            await conn.add_listener(FEEDS_CHANNEL, lambda *_: wake.set())
            try:
                await stop.wait()
            finally:
                await conn.close()
        except Exception as exc:
            log.warning("LISTEN %s failed (%s); polling instead", FEEDS_CHANNEL, exc)
            await asyncio.sleep(60)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="fetch what is due, then exit")
    args = ap.parse_args()
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s %(name)s: %(message)s")
    if s.offline:
        raise SystemExit("OFFLINE is set: the feeds worker does not fetch. Unset it to record.")

    async def go() -> None:
        try:
            await run(args.once)
        finally:
            from app.db.session import dispose_engine

            await dispose_engine()

    asyncio.run(go())


if __name__ == "__main__":
    main()
