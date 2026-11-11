"""Benchmark the opt-in SPICE worker pool (ADR-24).

K concurrent 30-day ephemeris sweeps at 900 s: single SPICE thread vs pools of
2 and 4 workers. Asserts every pooled result is bit-identical to the
single-thread result. Run from ``backend/``::

    .venv/Scripts/python.exe scripts/bench_spice_pool.py [--k 8] [--days 30]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.core import spice, spice_pool


def _windows(k: int, days: int) -> list[tuple[str, str]]:
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    out = []
    for i in range(k):
        a = t0 + timedelta(days=3 * i)
        out.append(
            (
                a.strftime("%Y-%m-%dT%H:%M:%S"),
                (a + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            )
        )
    return out


async def _sweep(wins: list[tuple[str, str]], step: float) -> tuple[float, list[spice.Ephemeris]]:
    t = time.perf_counter()
    res = await asyncio.gather(*(spice.ephemeris_async(a, b, step) for a, b in wins))
    return time.perf_counter() - t, list(res)


async def _best(
    wins: list[tuple[str, str]], step: float, repeats: int
) -> tuple[float, list[spice.Ephemeris]]:
    runs = [await _sweep(wins, step) for _ in range(repeats)]
    return min(runs, key=lambda r: r[0])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--step", type=float, default=900.0)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    kdir = get_settings().kernel_dir
    spice.load(kdir)
    wins = _windows(args.k, args.days)

    await _sweep(wins[:1], args.step)  # warm the thread
    base_t, base = await _best(wins, args.step, args.repeats)
    print(
        f"K={args.k} sweeps of {args.days} d at {args.step:.0f} s ({base[0].ets.size} epochs each)"
    )
    print(f"{'config':<14}{'start-up s':>11}{'wall s':>9}{'speed-up':>10}  identical")
    print(f"{'1 thread':<14}{'-':>11}{base_t:>9.3f}{1.0:>10.2f}  -")
    for n in (2, 4):
        t = time.perf_counter()
        ok = await asyncio.to_thread(spice_pool.start, n, kdir)
        startup = time.perf_counter() - t
        if not ok:
            print(f"pool of {n}: failed to start")
            return 1
        try:
            await _sweep(wins[:n], args.step)  # warm the workers
            wall, res = await _best(wins, args.step, args.repeats)
        finally:
            spice_pool.shutdown()
        for a, b in zip(base, res, strict=True):
            for f in ("ets", "sun", "earth"):
                assert np.array_equal(
                    getattr(a, f), getattr(b, f)
                ), f"{f} differs under pool of {n}"
        print(f"{f'pool of {n}':<14}{startup:>11.2f}{wall:>9.3f}{base_t / wall:>10.2f}  yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
