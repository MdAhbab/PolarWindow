"""The opt-in SPICE worker pool (ADR-24)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import numpy as np
import pytest

from app.config import get_settings
from app.core import spice, spice_pool


@pytest.fixture(autouse=True)
def _no_pool_left_behind() -> Iterator[None]:
    yield
    spice_pool.shutdown()


def test_default_is_off() -> None:
    assert get_settings().spice_workers == 0
    assert spice_pool.describe() == {"workers": 0, "started": False, "tasks_served": 0}
    assert spice.describe()["pool"]["started"] is False


def test_fewer_than_two_workers_spawns_nothing() -> None:
    assert spice_pool.start(0, get_settings().kernel_dir) is False
    assert spice_pool.start(1, get_settings().kernel_dir) is False
    assert spice_pool.describe()["started"] is False
    assert not spice_pool.eligible()


def test_extra_kernel_call_is_never_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(spice_pool, "_pool", sentinel)
    monkeypatch.setattr(spice_pool, "_directory", spice.state().directory)
    monkeypatch.setattr(spice, "_state", spice.KernelState(loaded=True, directory="d"))
    monkeypatch.setattr(spice_pool, "_directory", "d")
    assert spice_pool.eligible()
    assert not spice_pool.eligible(needs_extra=True)
    monkeypatch.setattr(spice_pool, "_directory", "other")
    assert not spice_pool.eligible()
    monkeypatch.setattr(spice_pool, "_pool", None)


def test_unavailable_pool_falls_back_to_the_thread() -> None:
    with pytest.raises(spice_pool.PoolUnavailableError):
        asyncio.run(spice_pool.ephemeris("2026-11-01T00:00:00", "2026-11-02T00:00:00", 900.0))


def test_shutdown_is_idempotent() -> None:
    spice_pool.shutdown()
    spice_pool.shutdown()
    assert spice_pool.describe()["started"] is False


@pytest.mark.slow
@pytest.mark.requires_kernels
def test_pool_results_are_bit_identical() -> None:
    spice.load(get_settings().kernel_dir)
    args = ("2026-11-01T00:00:00", "2026-11-04T00:00:00", 900.0)
    direct = spice.ephemeris(*args)

    async def go() -> tuple[spice.Ephemeris, spice.Ephemeris]:
        ok = await asyncio.to_thread(spice_pool.start, 2, get_settings().kernel_dir)
        assert ok
        assert spice_pool.eligible()
        pooled = await spice.ephemeris_async(*args)
        return pooled, direct

    pooled, _ = asyncio.run(go())
    for f in ("ets", "sun", "earth"):
        assert np.array_equal(getattr(direct, f), getattr(pooled, f))
    d = spice.describe()["pool"]
    assert d["workers"] == 2 and d["started"] and d["tasks_served"] >= 1
    spice_pool.shutdown()
    spice_pool.shutdown()
    assert spice.describe()["pool"]["started"] is False
