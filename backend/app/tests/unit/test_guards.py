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


# ---------------------------------------------------------------------------
# Adversarial: each of these passed the guard unchecked before it was hardened
# ---------------------------------------------------------------------------

POOL = [
    {
        "seq": 1,
        "tool": "get_metrics",
        "result": {
            # get_metrics returns its window; dates in an answer ground against it.
            "start": "2027-03-14T00:00:00Z",
            "end": "2027-04-12T12:30:00Z",
            "sunlit_s": 2067804.0,
            "longest_dark_s": 437688.0,
            "sun_fraction_up": 0.8103,
            "earth_fraction_up": 0.09,
        },
    }
]


@pytest.mark.parametrize(
    "prose,bad",
    [
        ("The night lasts 999h here.", 999.0),
        ("The ridge is 873km away.", 873.0),
        ("It gets 7e5 seconds of sun.", 700000.0),
        ("Earth is visible only 7 % of the time.", 7.0),
        ("A 10 h blackout follows.", 10.0),
        ("The night lasts three hundred hours.", 300.0),
        ("A fraction of .95 of the window is lit.", 0.95),
        ("The skyline sits at \N{MINUS SIGN}2.4 degrees.", -2.4),
    ],
)
def test_ungrounded_numbers_in_every_written_form_are_rejected(prose: str, bad: float) -> None:
    """Unit suffixes, exponents, words, leading dots and Unicode minus signs.

    The old number pattern required a non-word character after the digits and
    exempted every integer up to twelve, so all of these passed unchecked.
    """
    verdict = guards.check_grounding({"paragraph": prose}, POOL)
    assert not verdict.ok, f"{prose!r} passed the guard"
    assert bad in [v.value for v in verdict.violations]


@pytest.mark.parametrize(
    "prose",
    [
        "Earth is visible only 9 % of the time.",
        "The longest night is 122 h and it is sunlit 81 % of the window.",
        "The night lasts one hundred and twenty-two hours.",
        "From 14 March 2027 the site is lit 81 % of the time.",
        "The window runs 2027-03-14T00:00:00Z to 2027-04-12T12:30:00Z.",
        "Three documents cover the first site and one ridge.",
    ],
)
def test_grounded_counted_and_dated_numbers_still_pass(prose: str) -> None:
    """Hardening must not make the guard uselessly strict."""
    verdict = guards.check_grounding({"paragraph": prose}, POOL)
    assert verdict.ok, [v.detail for v in verdict.violations]


def test_the_users_threshold_cannot_ground_a_measured_value() -> None:
    """An observed value equal to the requirement is the classic hallucination.

    With one shared pool the user's "600 hours" grounded a structured
    `observed_value` of 600 -- measuring the site against itself.
    """
    pool = [
        *POOL,
        {
            "seq": 0,
            "tool": guards.USER_REQUEST_TOOL,
            "result": {"requirement": "at least 600 hours of sunlight"},
        },
    ]
    structured = {"ranked": [{"checks": [{"observed_value": 600.0}]}]}
    assert not guards.check_grounding(structured, pool).ok
    quoted = {"nothing_satisfies_message": "No site offers the 600 hours you asked for."}
    assert guards.check_grounding(quoted, pool).ok


# --- dates are facts once missions are in the pool --------------------------


def test_a_date_the_tools_returned_is_grounded() -> None:
    tools_ = [{"tool": "get_site", "seq": 1, "result": {"landing": "2025-03-06T17:30:00Z"}}]
    for text in ("It landed on 2025-03-06.", "It landed on March 6, 2025.", "Landed 6 March 2025."):
        v = guards.check_grounding({"summary": text}, tools_)
        assert not [x for x in v.violations if x.kind == "ungrounded_date"], text


def test_an_invented_date_is_rejected() -> None:
    tools_ = [{"tool": "get_site", "seq": 1, "result": {"landing": "2025-03-06T17:30:00Z"}}]
    v = guards.check_grounding({"summary": "IM-4 lands on 2027-05-01."}, tools_)
    assert any(x.kind == "ungrounded_date" for x in v.violations)
    v = guards.check_grounding({"summary": "It lands on May 1, 2027."}, tools_)
    assert any(x.kind == "ungrounded_date" for x in v.violations)


def test_a_month_or_year_alone_is_not_a_date_claim() -> None:
    v = guards.check_grounding({"summary": "Launch is expected in late 2027, around March."}, [])
    assert not [x for x in v.violations if x.kind == "ungrounded_date"]


@pytest.mark.parametrize(
    "text",
    [
        "Weather is GO for launch.",
        "It is a go.",
        "The go/no-go call is yours.",
        "The site looks safe.",
        "It is not safe to launch.",
        "The lander can land safely.",
        "Readiness score: high.",
        "The payload is 80% ready.",
        "The mission is ready to launch.",
        "Its risk score is low.",
        "The overall chance of launch is good.",
        "We recommend launching on the 13th.",
        "Likelihood times consequence gives the ranking.",
    ],
)
def test_a_verdict_word_is_rejected(text: str) -> None:
    v = guards.check({"status": "ok", "answer": text}, [])
    assert any(x.kind == "verdict_word" for x in v.violations), text


@pytest.mark.parametrize(
    "text",
    [
        "Three readiness items are in test; one risk is on the list.",
        "The weather rules show what the forecasts say for each rule.",
        "The capsule entry model's safety margin is not modelled.",
        "Seven of the rules have a forecast; the other five do not.",
        "The flight readiness review is a milestone.",
    ],
)
def test_evidence_words_are_not_verdicts(text: str) -> None:
    v = guards.check_verdict_words({"answer": text})
    assert v.ok, [x.detail for x in v.violations]


def test_the_users_own_words_may_carry_a_verdict_word() -> None:
    out = {"answer": "The wind rule is over its limit.", "question": "Is it safe to launch?"}
    assert guards.check_verdict_words(out).ok
