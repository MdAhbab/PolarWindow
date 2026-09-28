"""Trajectory exports: the OEM reads back to the states written, one block per stretch."""

from __future__ import annotations

import numpy as np
import pytest

from app.core import oem


def _seg(t0: int, n: int) -> oem.Segment:
    times = [f"2025-03-0{t0}T00:{i:02d}:00.000" for i in range(n)]
    s = np.arange(n * 6, dtype=float).reshape(n, 6) * 1234.5
    return oem.Segment(times, s)


def test_oem_round_trip_keeps_gaps_as_blocks() -> None:
    segs = [_seg(1, 3), _seg(2, 4)]
    text = oem.oem(
        object_name="IM-2",
        object_id="NAIF -370021",
        center="EARTH",
        frame="EME2000",
        segments=segs,
        created="2026-09-27T00:00:00",
        originator="POLAR WINDOW",
        comments=["test"],
    )
    assert text.startswith("CCSDS_OEM_VERS = 2.0\n")
    assert text.count("META_START") == 2 and "TIME_SYSTEM = UTC" in text
    back = oem.parse_oem(text)
    assert [len(t) for t, _ in back] == [3, 4]
    for (times, km), seg in zip(back, segs, strict=True):
        assert times == list(seg.times)
        np.testing.assert_allclose(km, seg.states_m / 1000.0, atol=1e-6)


def test_oem_refuses_an_empty_or_short_segment() -> None:
    kw = {
        "object_name": "x",
        "object_id": "1",
        "center": "EARTH",
        "frame": "EME2000",
        "created": "t",
        "originator": "o",
    }
    with pytest.raises(ValueError):
        oem.oem(segments=[], **kw)
    with pytest.raises(ValueError):
        oem.oem(segments=[_seg(1, 1)], **kw)


def test_csv_numbers_each_stretch() -> None:
    text = oem.csv_text([_seg(1, 2), _seg(2, 2)], "note")
    rows = text.splitlines()
    assert rows[0] == "# note" and rows[1].startswith("time_utc,stretch")
    assert [r.split(",")[1] for r in rows[2:]] == ["1", "1", "2", "2"]
    assert rows[2].split(",")[0].endswith("Z")
