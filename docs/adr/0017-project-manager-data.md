# ADR-17: The project manager's records have a name on every change

**Status:** Accepted
**Date:** 2026-09-26
**Amends:** ADR-7

## Context

Readiness, parts, risks, booked passes, weather limits and official forecasts
are entered by people. ADR-7's one-click sign-in gives every visitor the same
anonymous project-manager token, so an audit log would record no one.

## Decision

1. **Named sign-in.** Sign-in asks for a name (and optionally a team); the token
   carries a `users` row id. There is still one role, the project manager.
   Reading stays public. Every write needs a named session;
   `PW_DEMO_SIGN_IN=true` still issues a named demo session for judging.
2. **An append-only, hash-chained audit log**: who, when, what (before and
   after), request id, and the hash of the previous entry. A database trigger
   rejects UPDATE and DELETE on it.
3. **Readiness is a state machine** (`core/readiness.py`): not started, in
   build, in test, test passed, delivered to the lander provider, integrated,
   verified on the lander, ready; or blocked with a reason, from any state.
   Every change needs a date and an evidence link; illegal moves are refused.
4. **Risks use a configurable scale.** NPR 8000.4C leaves the likelihood and
   consequence scales to each programme; GSFC-HDBK-8005A's public scale is the
   default. Likelihood and consequence are stored and shown per consequence
   category and are never multiplied, summed or turned into a score.
5. **Landing history is counts, never a success probability.**
