"""Mission summaries must format dates on Windows as well as Unix."""

import pytest

from app.services.sections_service import _when


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-03-06", "6 Mar 2025"),
        ("2025-03-06T17:30:00Z", "6 Mar 2025 17:30 UTC"),
        ("2025-02-27T00:16:00Z", "27 Feb 2025 00:16 UTC"),
    ],
)
def test_mission_summary_dates(value: str, expected: str) -> None:
    assert _when(value) == expected
