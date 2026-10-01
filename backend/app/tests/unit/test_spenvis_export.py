"""External reference inputs preserve frames, times, units and passage gaps."""

from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest

from app.services import radiation
from app.validation.export_spenvis import trajectory_text


def test_upload_uses_utc_and_cartesian_km_without_a_second_frame_conversion() -> None:
    local = timezone(timedelta(hours=6))
    times = [datetime(2025, 2, 27, 1, 0, 0, 123456, tzinfo=local)]
    times.append(times[0] + timedelta(seconds=60))
    xyz = np.array([[7000.1, -1234.2, 987.3], [7010.1, -1244.2, 997.3]])
    text = trajectory_text("IM-2", times, xyz)
    assert "Coordinates: GEO\n" in text
    rows = text.split("$$BEGIN\n")[1].split("$$END")[0].splitlines()
    first = rows[0].split(",")
    assert list(map(int, first[:5])) == [2025, 2, 26, 19, 0]
    assert float(first[5]) == pytest.approx(0.123456)
    assert np.allclose(list(map(float, first[6:])), xyz[0])
    assert text.endswith("$$END\n")


@pytest.mark.parametrize("problem", ["naive", "reverse", "nan", "shape", "single"])
def test_invalid_upload_samples_are_rejected(problem: str) -> None:
    times = [datetime(2025, 2, 27, tzinfo=UTC), datetime(2025, 2, 27, 0, 1, tzinfo=UTC)]
    xyz = np.zeros((2, 3))
    if problem == "naive":
        times[0] = times[0].replace(tzinfo=None)
    elif problem == "reverse":
        times.reverse()
    elif problem == "nan":
        xyz[0, 0] = np.nan
    elif problem == "shape":
        xyz = np.zeros((2, 2))
    else:
        times, xyz = times[:1], xyz[:1]
    with pytest.raises(ValueError):
        trajectory_text("test", times, xyz)


def test_passages_do_not_integrate_over_missing_trajectory_time() -> None:
    times = np.array([0., 60., 120., 600., 660.])
    passages = radiation._segments(times)
    duration = sum(float(times[s[-1]] - times[s[0]]) for s in passages)
    assert duration == 180.0
    assert len(passages) == 2
