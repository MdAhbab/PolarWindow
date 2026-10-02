"""Pad-limit windows must meet the same coast and flight constraints as their instant."""

from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from app.core import propagate, transfer
from app.services import ascent
from app.workers.handlers import launch as job


@pytest.mark.parametrize("bad", [None, "coast", "flight", "sweep", "outside"])
def test_both_pad_limits_are_required_and_failed_windows_have_a_reason(
    monkeypatch: pytest.MonkeyPatch,
    bad: str | None,
) -> None:
    monkeypatch.setattr(propagate, "environment", lambda *_: None)
    monkeypatch.setattr(ascent, "pad_j2000", lambda _: lambda t: np.array([1.0, 0.0, 0.0]))
    monkeypatch.setattr(job, "_epoch", lambda t: t)
    called = []

    def design(tables, target, pad, az, *args, **kw):
        called.append(az)
        assert target.inc_deg == 90  # arrival orbit, independent of the climb direction
        t = 100000.0 + (-100.0 if az == 35 else 100.0)
        coast, flight = 2400.0, 4.5 * job.DAY
        if az == 120:
            if bad == "coast":
                coast = job.COAST_MAX_S + 1
            if bad == "flight":
                flight = 7 * job.DAY
            if bad == "sweep":
                t += job.DAY
            if bad == "outside":
                t -= 300
        return SimpleNamespace(
            converged=True,
            t_launch=t,
            coast_s=coast,
            t_tli=t + coast,
            t_peri=t + coast + flight,
        )

    monkeypatch.setattr(transfer, "launch_at", design)
    asc = cast(ascent.Ascent, SimpleNamespace(coasts_s=[2300, 2400], c_rad=0, r_park_m=6600000))
    opportunity: dict[str, Any] = {
        "t_launch_et": 100000.0,
        "arrive_et": 500000.0,
        "t0": 100000.0,
        "inc": 90.0,
        "northward": True,
    }
    job._window_ends({"pad_id": "pad"}, asc, [opportunity], (35, 120))
    assert called == [35, 120]
    if bad is None:
        assert (opportunity["open"], opportunity["close"]) == (99900, 100100)
    else:
        assert "open" not in opportunity and "close" not in opportunity
        assert "could not be resolved" in opportunity["window_failure"]
