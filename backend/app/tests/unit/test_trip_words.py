"""A stored trip is served in today's words where a sentence is rebuilt from what was stored."""

from __future__ import annotations

from typing import Any

from app.services import radiation, trip_service

OLD = (
    "One solar particle event crossed NOAA's threshold (10 pfu above 10 MeV at GOES) during the "
    "trip, from NASA DONKI; its fluence is not worked out."
)


def stored(note: str, events: int) -> dict[str, Any]:
    listed = [{"t": "x", "link": "y"}] * events
    return {"data": {"radiation": {"sep_note": note, "sep_events": listed}}}


def test_an_old_particle_event_sentence_is_served_in_the_current_words() -> None:
    out = trip_service._current_words(stored(OLD, 1))
    assert out["data"]["radiation"]["sep_note"] == radiation.sep_note(1)
    assert len(out["data"]["radiation"]["sep_events"]) == 1


def test_a_reason_the_events_could_not_be_read_is_left_alone() -> None:
    why = "The space weather log could not be read for these dates."
    assert trip_service._current_words(stored(why, 0))["data"]["radiation"]["sep_note"] == why


def test_an_answer_with_no_radiation_is_served_as_stored() -> None:
    r = {"data": {"radiation": None}}
    assert trip_service._current_words(r) is r
