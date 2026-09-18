"""Grounding and refusal guards.

`guards.check(parsed, collected)` is a pure function of two values, which makes
the highest-risk component in the system the easiest to test exhaustively --
the right way round.
"""

from __future__ import annotations

import pytest

from app.agents import guards


def tool(seq: int, name: str, result: dict) -> dict:
    return {"seq": seq, "tool": name, "result": result}


METRICS = tool(
    1,
    "get_metrics",
    {
        "site_id": "connecting-ridge",
        "sunlit_s": 2067804.0,
        "earth_contact_s": 1548108.0,
        "longest_dark_s": 437688.0,
        "longest_blackout_s": 1002492.0,
        "sun_fraction_up": 0.8103,
        "earth_fraction_up": 0.6067,
    },
)


def test_grounded_answer_passes() -> None:
    out = {
        "status": "ok",
        "paragraph": "The site is sunlit for about 574 hours, 81% of the window.",
    }
    v = guards.check(out, [METRICS])
    assert v.ok, [x.detail for x in v.violations]
    assert any(c.value == 574 for c in v.citations)


def test_invented_number_is_rejected() -> None:
    out = {"status": "ok", "paragraph": "Sunlight reaches 72% of the window."}
    v = guards.check(out, [METRICS])
    assert not v.ok
    assert any(x.kind == "ungrounded_number" and x.value == 72 for x in v.violations)


def test_rounding_within_the_stated_precision_is_allowed() -> None:
    """0.8103 written as '81%' is rounding, not invention.

    Forbidding it would push the model toward raw seconds, which is worse prose
    and no more truthful.
    """
    out = {"status": "ok", "paragraph": "Sunlit 81% of the time."}
    assert guards.check(out, [METRICS]).ok


def test_correct_derived_arithmetic_is_still_rejected() -> None:
    """Deliberate, and the most counter-intuitive rule here.

    2067804 s / 3600 = 574.39 h, and 574.39 / 708.7 = 81%. Both are correct. But
    a model allowed to derive is a model allowed to derive wrongly, and the
    guard cannot tell correct arithmetic from lucky arithmetic. Derivations
    belong in tools.
    """
    out = {
        "status": "ok",
        "paragraph": "That leaves 134.3 hours of darkness beyond the survival limit.",
    }
    v = guards.check(out, [METRICS])
    assert not v.ok
    assert any(x.value == pytest.approx(134.3) for x in v.violations)


def test_seconds_to_hours_and_days_are_allowed_conversions() -> None:
    out = {"status": "ok", "paragraph": "The longest night is 121.6 hours, about 5.1 days."}
    v = guards.check(out, [METRICS])
    assert v.ok, [x.detail for x in v.violations]


def test_ordinals_years_and_small_counts_are_exempt() -> None:
    """Without this the guard is uselessly strict and forces stilted prose."""
    out = {
        "status": "ok",
        "paragraph": "In 2027 the first of three ridges blocks one bearing.",
    }
    assert guards.check(out, [METRICS]).ok


def test_number_hidden_in_a_structured_field_is_also_checked() -> None:
    """A hallucinated value in a field is as damaging as one in a sentence, and
    less likely to be noticed."""
    out = {
        "status": "ok",
        "paragraph": "See the figures.",
        "numbers_used": [{"label": "sunlit", "value_s": 9999999.0, "source": "get_metrics"}],
    }
    v = guards.check(out, [METRICS])
    assert not v.ok
    assert any(x.value == 9999999.0 for x in v.violations)


def test_no_tools_called_forbids_every_number() -> None:
    out = {"status": "ok", "paragraph": "It is sunlit for 500 hours."}
    v = guards.check(out, [])
    assert not v.ok
    assert any(x.kind == "ungrounded_no_tools" for x in v.violations)


def test_insufficient_data_needs_a_reason() -> None:
    assert not guards.check({"status": "insufficient_data", "reason": ""}, []).ok
    assert guards.check(
        {"status": "insufficient_data", "reason": "No soil data exists in this dataset."}, []
    ).ok


def test_ok_with_no_content_is_rejected() -> None:
    """An 'ok' with empty fields renders as a blank card -- a silent failure."""
    v = guards.check({"status": "ok", "paragraph": ""}, [METRICS])
    assert not v.ok
    assert any(x.kind == "empty_ok" for x in v.violations)


def test_advisor_must_state_a_negative_result() -> None:
    """The specific failure: ranking the least-bad site as though it passed."""
    bad = {
        "status": "ok",
        "any_satisfies": False,
        "nothing_satisfies_message": None,
        "ranked": [
            {"site_id": "a", "rank": 1, "satisfies_all": False, "checks": [], "why": "closest"}
        ],
    }
    v = guards.check(bad, [METRICS])
    assert not v.ok
    assert any(x.kind == "missing_negative_statement" for x in v.violations)

    good = dict(bad, nothing_satisfies_message="No site in this set meets the requirement.")
    assert guards.check(good, [METRICS]).ok


def test_repair_hint_names_the_offending_numbers() -> None:
    """'Your output contained an ungrounded number' produces another guess.
    '72 is not in the tool results' produces a correction."""
    v = guards.check({"status": "ok", "paragraph": "Sunlight is 72%."}, [METRICS])
    hint = v.repair_hint()
    assert "72" in hint
    assert "insufficient_data" in hint


def test_flatten_numbers_excludes_booleans() -> None:
    """True is an int in Python and would otherwise ground every '1'."""
    flat = dict(guards.flatten_numbers({"a": True, "b": 3.5, "c": [1.0, False]}))
    assert "a" not in flat
    assert flat["b"] == 3.5
    assert flat["c[0]"] == 1.0
    assert "c[1]" not in flat


def test_citations_point_at_a_real_field() -> None:
    out = {"status": "ok", "paragraph": "Earth is in view 61% of the window."}
    v = guards.check(out, [METRICS])
    assert v.ok
    cite = next(c for c in v.citations if c.value == 61)
    assert cite.tool == "get_metrics"
    assert cite.call_seq == 1
    assert "earth_fraction_up" in cite.field


def test_percent_and_fraction_are_the_same_claim() -> None:
    assert guards.check({"status": "ok", "paragraph": "0.8103 of the window"}, [METRICS]).ok
    assert guards.check({"status": "ok", "paragraph": "81% of the window"}, [METRICS]).ok


def test_comma_separated_numbers_are_parsed() -> None:
    out = {"status": "ok", "paragraph": "Sunlit for 2,067,804 seconds."}
    assert guards.check(out, [METRICS]).ok
