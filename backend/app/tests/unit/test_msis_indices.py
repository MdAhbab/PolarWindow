"""The day's solar flux and geomagnetic activity as NRLMSISE-00 takes them, worked out from
hourly values (synthetic here, so the blocks and days can be read off), and the real
values for OSIRIS-REx's entry day when the OMNI files are on disk."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.data import msis_indices
from app.data.space_climate import omni_dir

START = datetime(2023, 7, 1, tzinfo=UTC)
DAYS = 100


def _hours() -> list[datetime]:
    return [START + timedelta(hours=i) for i in range(DAYS * 24)]


def _blocks() -> np.ndarray:
    """ap = the number of the 3-hour block since START, repeated on each of its hours."""
    return np.array([i // 3 for i in range(DAYS * 24)], dtype=np.float64)


def _days() -> np.ndarray:
    """F10.7 = the number of the day since START, repeated on each of its hours."""
    return np.array([i // 24 for i in range(DAYS * 24)], dtype=np.float64)


def test_the_seven_ap_numbers_are_the_blocks_nrlmsise_00_asks_for() -> None:
    t = START + timedelta(days=40, hours=14, minutes=41, seconds=55)
    ix = msis_indices.compute(t, _hours(), _days(), _blocks())
    assert ix is not None
    block = (40 * 24 + 14) // 3  # the 12-15 h block of day 40
    daily, now, h3, h6, h9, d12_33, d36_57 = ix.ap
    assert daily == pytest.approx(np.mean(range(40 * 8, 41 * 8)))  # the day's eight blocks
    assert (now, h3, h6, h9) == (block, block - 1, block - 2, block - 3)
    # Eight blocks from 12 to 33 hours before, and from 36 to 57: the mean of blocks
    # (block - 4) down to (block - 11), and (block - 12) down to (block - 19).
    assert d12_33 == pytest.approx(block - 7.5)
    assert d36_57 == pytest.approx(block - 15.5)


def test_the_flux_is_the_day_before_and_the_81_day_mean_is_centred_on_the_day() -> None:
    t = START + timedelta(days=50, hours=6)
    ix = msis_indices.compute(t, _hours(), _days(), _blocks())
    assert ix is not None
    assert ix.f107 == 49.0
    assert ix.f107a == pytest.approx(50.0)  # mean of days 10 to 90


def test_a_missing_day_is_left_out_of_the_mean_but_a_missing_previous_day_is_not_made_up() -> None:
    t = START + timedelta(days=50, hours=6)
    f = _days()
    f[(30 * 24) : (32 * 24)] = np.nan  # days 30 and 31 have no flux
    ix = msis_indices.compute(t, _hours(), f, _blocks())
    assert ix is not None
    assert ix.f107a == pytest.approx((sum(range(10, 91)) - 30 - 31) / 79)
    f[(49 * 24) : (50 * 24)] = np.nan  # the day before has none
    assert msis_indices.compute(t, _hours(), f, _blocks()) is None


def test_a_missing_ap_or_hours_the_files_do_not_cover_give_no_indices() -> None:
    t = START + timedelta(days=50, hours=6)
    ap = _blocks()
    ap[50 * 24 + 6] = np.nan  # the 3-hour ap at the time
    assert msis_indices.compute(t, _hours(), _days(), ap) is None
    # Files that end before the 57 hours NRLMSISE-00 looks back over.
    late = START + timedelta(days=1)
    assert msis_indices.compute(late, _hours(), _days(), _blocks()) is None


def test_the_time_carries_its_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        msis_indices.at(datetime(2023, 9, 24, 14, 41, 55))


def test_the_entry_day_of_osiris_rex_from_the_omni_files() -> None:
    if not list(omni_dir().glob("omni2_h0_mrg1hr_20230701_v01.cdf")):
        pytest.skip("OMNI hourly file for July to December 2023 not on disk (make space-climate)")
    ix = msis_indices.at(datetime(2023, 9, 24, 14, 41, 55, tzinfo=UTC))
    assert ix is not None
    assert ix.f107 == pytest.approx(174.1, abs=0.05)  # 23 September
    assert ix.f107a == pytest.approx(149.29, abs=0.05)
    daily, now, h3, h6, h9, d12_33, d36_57 = ix.ap
    # The day's storm came in the 18-21 h block, after the landing: the 12-15 h block was
    # quiet, and the day's Ap (the mean of its eight blocks) holds the evening.
    assert (now, h3, h6, h9) == (4.0, 6.0, 7.0, 5.0)
    assert daily == pytest.approx((7 + 5 + 7 + 6 + 4 + 4 + 67 + 67) / 8)
    assert math.isfinite(d12_33) and math.isfinite(d36_57)


def test_several_times_are_the_same_as_one_at_a_time_and_a_time_with_no_files_gives_none() -> None:
    if not list(omni_dir().glob("omni2_h0_mrg1hr_20230701_v01.cdf")):
        pytest.skip("OMNI hourly file for July to December 2023 not on disk (make space-climate)")
    times = [
        datetime(2023, 9, 22, 4, 19, tzinfo=UTC),
        datetime(2023, 9, 24, 14, 41, 55, tzinfo=UTC),
        datetime(2023, 9, 28, 23, 59, tzinfo=UTC),
    ]
    many = msis_indices.at_many(times)
    for t, ix in zip(times, many, strict=True):
        assert ix is not None and ix == msis_indices.at(t)
    assert msis_indices.at_many([]) == []
    with pytest.raises(ValueError, match="time zone"):
        msis_indices.at_many([datetime(2023, 9, 24)])
