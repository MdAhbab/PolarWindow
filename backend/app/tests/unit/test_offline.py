"""OFFLINE=1: nothing is downloaded, and a missing input says so loudly."""

from __future__ import annotations

import pytest


def test_offline_refuses_to_fetch_the_regional_dem(monkeypatch, tmp_path) -> None:
    from app.config import get_settings
    from app.data import ingest_lola
    from app.data.lola import DemUnavailable

    monkeypatch.setenv("OFFLINE", "1")
    monkeypatch.setenv("PW_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        with pytest.raises(DemUnavailable, match="OFFLINE=1"):
            ingest_lola.ensure_regional_dem()
    finally:
        get_settings.cache_clear()


def test_offline_disables_the_model(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("OFFLINE", "1")
    monkeypatch.setenv("PW_GEMINI_API_KEY", "some-key")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.offline and not s.agents_enabled
    finally:
        get_settings.cache_clear()
