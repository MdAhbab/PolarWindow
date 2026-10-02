"""A missing raw archive must not erase an existing scientific benchmark."""

import sys

import pytest

from app.feeds import hindcast_hrrr, hindcast_reforecast


@pytest.mark.parametrize("module", [hindcast_hrrr, hindcast_reforecast])
def test_score_only_without_raw_cache_keeps_existing_report(module, tmp_path, monkeypatch):
    report = tmp_path / "benchmark.json"
    report.write_text('{"cases": 1459, "passes": false}')
    monkeypatch.setattr(sys, "argv", ["hindcast", "--score-only"])
    monkeypatch.setattr(module, "read_cache", lambda: {})
    monkeypatch.setattr(module, "out_path", lambda region: report)
    with pytest.raises(SystemExit, match="No raw"):
        module.main()
    assert report.read_text() == '{"cases": 1459, "passes": false}'
