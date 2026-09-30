"""Readiness as a state machine (ADR-17). Pure: no I/O, no clock.

Each readiness item moves along a ladder of states. The ladder depends on
what the item is: a payload is built, tested, delivered to the lander
provider, integrated and verified on the lander; a licence or a ground
station booking is only started, in progress and in hand. The rules:

* **Forward, one step at a time.** Skipping from "in build" to "ready" would
  hide the steps that make "ready" mean something.
* **Back, to any earlier step** (a failed test sends a payload back to the
  build), with a note saying why.
* **Blocked from any state**, with the reason; from blocked, back to the
  state it was blocked in or any earlier one.
* **Every change has a date and an evidence link.**

There is no percentage and no overall state: the product counts items per
state and shows them (invariant 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

ReadyState = Literal[
    "not_started",
    "in_build",
    "in_test",
    "test_passed",
    "delivered",
    "integrated",
    "verified_on_lander",
    "ready",
    "blocked",
]

STATES: Final[tuple[ReadyState, ...]] = (
    "not_started",
    "in_build",
    "in_test",
    "test_passed",
    "delivered",
    "integrated",
    "verified_on_lander",
    "ready",
    "blocked",
)

_HARDWARE: Final[tuple[ReadyState, ...]] = (
    "not_started",
    "in_build",
    "in_test",
    "test_passed",
    "delivered",
    "integrated",
    "verified_on_lander",
    "ready",
)
#: The lander is not delivered to itself or verified on itself.
_LANDER: Final[tuple[ReadyState, ...]] = (
    "not_started",
    "in_build",
    "in_test",
    "test_passed",
    "ready",
)
_AGREEMENT: Final[tuple[ReadyState, ...]] = ("not_started", "in_build", "ready")

LADDERS: Final[dict[str, tuple[ReadyState, ...]]] = {
    "payload": _HARDWARE,
    "rover": _HARDWARE,
    "lander": _LANDER,
    "launch_vehicle": _LANDER,
    "range": _AGREEMENT,
    "ground_booking": _AGREEMENT,
    "relay_agreement": _AGREEMENT,
    "ops_team": _AGREEMENT,
    "licence": _AGREEMENT,
}


class IllegalMove(ValueError):
    """A move the ladder does not allow; carries the moves it does allow."""

    def __init__(self, message: str, allowed: list[ReadyState]) -> None:
        super().__init__(message)
        self.allowed = allowed


@dataclass(frozen=True, slots=True)
class Move:
    to: ReadyState
    date: str | None
    evidence_url: str | None
    note: str | None = None
    blocked_reason: str | None = None


def ladder(kind: str) -> tuple[ReadyState, ...]:
    try:
        return LADDERS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown item kind {kind!r}") from exc


def allowed_moves(
    kind: str, state: ReadyState, blocked_from: ReadyState | None
) -> list[ReadyState]:
    """Every state an item of ``kind`` may move to from ``state``."""
    steps = ladder(kind)
    if state == "blocked":
        top = steps.index(blocked_from) if blocked_from in steps else 0
        return list(steps[: top + 1])
    if state not in steps:
        return [steps[0], "blocked"]
    i = steps.index(state)
    out: list[ReadyState] = list(steps[:i])
    if i + 1 < len(steps):
        out.append(steps[i + 1])
    out.append("blocked")
    return out


def check(
    kind: str, state: ReadyState, blocked_from: ReadyState | None, move: Move
) -> ReadyState | None:
    """Validate ``move``; return the new ``blocked_from`` (None when not blocked).

    Raises :class:`IllegalMove` with the allowed moves, or ``ValueError`` for
    a move with no date, no evidence, or no reason where one is required.
    """
    allowed = allowed_moves(kind, state, blocked_from)
    if move.to == state:
        raise IllegalMove(f"the item is already '{state}'", allowed)
    if move.to not in allowed:
        raise IllegalMove(f"'{state}' cannot move to '{move.to}' for a {kind}", allowed)
    if not move.date:
        raise ValueError("every change needs the date it happened")
    if not move.evidence_url or not move.evidence_url.startswith(("https://", "http://")):
        raise ValueError("every change needs an evidence link (a web address)")
    if move.to == "blocked":
        if not (move.blocked_reason and move.blocked_reason.strip()):
            raise ValueError("a blocked item needs the reason it is blocked")
        return state if state != "blocked" else blocked_from
    steps = ladder(kind)
    going_back = state != "blocked" and steps.index(move.to) < steps.index(state)
    if going_back and not (move.note and move.note.strip()):
        raise ValueError("moving an item back a step needs a note saying why")
    return None


def counts(states: list[str]) -> dict[str, int]:
    """Items per state, every state present (zero included). Never a percentage."""
    out: dict[str, int] = dict.fromkeys(STATES, 0)
    for s in states:
        if s in out:
            out[s] += 1
    return out
