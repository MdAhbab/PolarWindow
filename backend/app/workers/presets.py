"""Presets: scenarios worked out ahead of time, at the lowest priority.

For each upcoming mission with a gap, up to three scenarios are queued:

1. the named defaults, as they stand (precedents, shown as defaults);
2. the next vehicle and pad precedent;
3. a landing a month later.

They are queued when the API starts and after a seed, and by
``python -m app.workers.presets``. A preset is an ordinary scenario with
``preset = true``: it runs below every real job and below any scenario somebody asked for,
and a prompt that reads to the same values opens it at once (``matches_preset``).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date
from typing import Any

from app.core import scenario as core
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.session import dispose_engine, session_scope
from app.services import job_service, ready_service, scenario_service

log = logging.getLogger("polar_window.presets")

MAX_PER_MISSION = 3
#: Statuses of a mission whose steps may still be worked out ahead of time.
UPCOMING = ("planned",)


async def variants(
    session: Any, m: MissionRecord, nm: dict[str, dict[str, str]]
) -> list[tuple[str, dict[str, Any]]]:
    """``(name, assumptions the preset sets)`` for up to three presets of one mission."""
    res = {r.field: r for r in await scenario_service.resolve_all(session, m, {})}
    veh, pad = res.get("vehicle_id"), res.get("pad_id")
    land = res.get("landing_date")
    site = res.get("site_id")
    out: list[tuple[str, dict[str, Any]]] = []

    bits = []
    if veh:
        bits.append(core.display("vehicle_id", veh.value, nm))
    if pad:
        bits.append("from " + core.display("pad_id", pad.value, nm))
    head = " ".join(bits) if bits else "none stated"
    tail = f", landing {core.display('landing_date', land.value, nm)}" if land else ""
    if site:
        tail += f", at {core.display('site_id', site.value, nm)}"
    out.append((f"Defaults from past flights: {head}{tail}", {}))

    rows = await scenario_service.flight_rows(session, m.id)
    nxt = core.next_precedent(
        m.provider, m.lander, rows, (veh.value if veh else None, pad.value if pad else None)
    )
    if nxt is not None and nxt.vehicle_id and nxt.pad_id:
        given = {"vehicle_id": nxt.vehicle_id, "pad_id": nxt.pad_id}
        label = (
            f"{core.display('vehicle_id', nxt.vehicle_id, nm)} from "
            f"{core.display('pad_id', nxt.pad_id, nm)}, as {nxt.name}"
        )
        out.append((f"As the next flight of this lander: {label}", given))

    if land is not None:
        first = date.fromisoformat(str(land.value)[:10]).replace(day=1)
        later = core.add_months(first, 1).isoformat()
        out.append(
            (
                f"A month later: landing {core.display('landing_date', later, nm)}",
                {"landing_date": later},
            )
        )
    return out[:MAX_PER_MISSION]


async def queue_presets(only: list[str] | None = None) -> int:
    """Queue the presets of every upcoming mission with a gap. Returns how many were new."""
    queued = 0
    async with session_scope() as s:
        missions = [
            m
            for m in await MissionRepository(s).find(statuses=list(UPCOMING))
            if (only is None or m.id in only) and m.status not in ready_service.CANCELLED
        ]
        nm = await scenario_service.names(s)
    for m in missions:
        try:
            async with session_scope() as s:
                gaps = await scenario_service.gaps(s, m.id)
                if not any(g["can_explore"] for g in gaps["gaps"]):
                    continue
                current = await variants(s, m, nm)
                for name, given in current:
                    rec, created = await scenario_service.create(
                        s,
                        m,
                        given=core.canonical(given),
                        sections=list(core.SECTIONS),
                        name=name,
                        prompt=None,
                        who=None,
                        preset=True,
                    )
                    queued += int(created)
                    if not created and await scenario_service.rerun_if_more(s, m, rec, name):
                        queued += 1
                # A preset built on a default that has since moved is replaced, not kept.
                gone = await scenario_service.retire_stale_presets(
                    s, m.id, [given for _, given in current]
                )
                if gone:
                    log.info("presets for %s no longer current, removed: %s", m.id, gone)
        except job_service.QueueFull:
            log.info("the queue is full; the remaining presets wait for the next start")
            break
        except Exception as exc:  # one mission must not cost the others
            log.warning("presets for %s were not queued: %s", m.id, exc)
    log.info("presets: %d queued", queued)
    return queued


async def main_async(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Queue the precedent-based scenarios of upcoming missions."
    )
    p.add_argument("--missions", nargs="*", help="only these mission ids")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        n = await queue_presets(args.missions)
        print(f"{n} presets queued")
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
