"""Which API errors move an agent run to the next model, and for how long."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.base import _seconds_to_daily_reset, classify_api_error

DAILY = (
    "RESOURCE_EXHAUSTED {'error': {'code': 429, 'details': [{'@type': "
    "'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaId': "
    "'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}]}}"
)
PER_MINUTE = (
    "RESOURCE_EXHAUSTED {'error': {'code': 429, 'details': [{'@type': "
    "'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '27s'}]}}"
)


def test_a_used_up_daily_quota_waits_for_the_reset() -> None:
    e = classify_api_error("gemini-3.8-flash", 429, DAILY)
    assert e is not None and e.model == "gemini-3.8-flash"
    assert e.why == "daily quota used up"
    assert 60 <= e.cooldown_s <= 25 * 3600


def test_a_per_minute_quota_waits_as_long_as_the_server_says() -> None:
    e = classify_api_error("gemini-3.5-flash", 429, PER_MINUTE)
    assert e is not None and e.cooldown_s == 28.0


def test_an_unknown_or_forbidden_model_is_skipped_for_hours() -> None:
    for code in (403, 404):
        e = classify_api_error("gemini-3-flash", code, "NOT_FOUND")
        assert e is not None and e.cooldown_s >= 3600


def test_an_outage_moves_on_briefly() -> None:
    e = classify_api_error("gemini-2.5-flash", 503, "UNAVAILABLE")
    assert e is not None and e.cooldown_s == 30.0


def test_a_bad_request_is_not_the_model_s_fault() -> None:
    assert classify_api_error("gemini-3.8-flash", 400, "INVALID_ARGUMENT") is None


def test_daily_quotas_reset_at_midnight_pacific() -> None:
    # 07:00 UTC in September is midnight in Los Angeles (PDT, UTC-7).
    assert _seconds_to_daily_reset(datetime(2026, 9, 24, 6, 0, tzinfo=UTC)) == 3600
    assert _seconds_to_daily_reset(datetime(2026, 9, 24, 7, 0, tzinfo=UTC)) == 24 * 3600
