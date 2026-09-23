"""Hindcast against flown CLPS landers (docs/validation.md).

The geometry is not tuned to these events; the test pins what it computes so a
change that moves a sunset by a day shows up as a failure beside its source.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytestmark = [pytest.mark.requires_kernels, pytest.mark.asyncio]


async def test_blue_ghost_1_sunset_falls_on_the_reported_date() -> None:
    """NASA Media Advisory M25-033: operations continued five hours after lunar
    sunset on March 16, 2025. The landing site is LROC's (18.5623 N, 61.8103 E);
    Mare Crisium is outside the polar DEM, so the skyline is a smooth sphere,
    which on a flat mare floor is close to the truth."""
    from app.config import get_settings
    from app.core import spice
    from app.core.horizon import smooth_mask
    from app.services.geometry_service import compute_window_metrics

    spice.load(get_settings().kernel_dir)
    start = datetime(2025, 3, 2, 9, tzinfo=UTC)
    r = await compute_window_metrics(
        site_id="blue-ghost-m1",
        lat_deg=18.5623,
        lon_deg=61.8103,
        elev_m=-3650.0,
        mask=smooth_mask(),
        start=start,
        end=datetime(2025, 3, 18, tzinfo=UTC),
        step_s=300,
    )
    sunsets = [a for a in r.sun.arcs if not a.value and a.start > 0]
    assert sunsets, "no sunset in the window"
    at = start.timestamp() + sunsets[0].start
    when = datetime.fromtimestamp(at, tz=UTC)
    assert when.date().isoformat() == "2025-03-16", when
