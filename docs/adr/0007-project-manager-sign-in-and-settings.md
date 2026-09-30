# ADR-7: One stakeholder, the project manager; one-click sign-in; admin tasks live in their Settings

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** product owner, frontend and backend leads
**Relates to:** ADR-2 (frontend data fetching), ADR-3 (agents and the model chain), `docs/api.md` *Sign-in* and *Settings*

## Context

The product had no notion of who is using it, and everything an operator does
was a shell task: turning the AI off, reordering the Gemini fallback chain
after a quota ran out, clearing the AI run log before a demo, flushing Redis
after new data. The front door was a redirect, and a first visit landed on a
four-panel story with no way to learn the dashboard itself.

Three things are required of the next version:

1. **An introduction** a judge can scroll through in a minute, then a way in.
2. **Access to the dashboard without a user name or password.** Judges will
   not make accounts, and the demo must open in one click.
3. **The critical operator tasks inside the dashboard**, reachable by the
   person who runs the mission, not by a separate admin.

## Decision

1. **One stakeholder: the project manager** of a lunar lander mission. They
   read everything, and they run the service for their team. There is no
   separate admin role or screen. Settings has a *Project* section with the
   operator's controls (the AI assistant, its model order, the activity log,
   saved results) and a read-only health list. (The detail switch,
   Simple · Explain · Expert, stayed at first; it was removed on 24 September
   in favour of one view with detail on request. See the amendment below.)

2. **A signed session, issued with one click.** `POST /auth/demo` returns an
   HS256 JWT with `role = project_manager` and no credentials asked for. The
   server checks it where it matters and nowhere else:
   - the four AI endpoints, because they spend model quota;
   - every `/settings` route, because a change applies to everyone.

   Reading stays public: sites, missions, numbers and tiles are public data,
   and a credential on reads would add a CORS preflight to every slider step.
   The client sends the token only on the calls that need it, and on a 401
   signs in again once and retries (a restart with a blank `PW_JWT_SECRET`
   invalidates every token). The dashboard routes are gated in the client: no
   session sends a visitor to the front page with `?next=` and back after the
   click. `PW_DEMO_SIGN_IN=false` turns the button off anywhere real.

3. **Settings changes are stored, not held in memory.** The AI switch and
   model orders live in `app_settings` (migration `5e8a2f7c1d44`) and are read
   per AI request into a context variable the agent loop consults
   (`AgentRuntime` in `app/agents/base.py`), so every process follows the same
   switch and the agent layer still imports no repository. Model lists are
   checked against the configured chain: Settings reorders or drops models; it
   does not accept new names, which stay an environment decision.

4. **Every change can be undone or is harmless.** *Reset the AI settings*
   returns to the environment's defaults; a cleared cached result is worked
   out again when next needed (and only `pw:*` keys go, never `FLUSHDB`); the
   run log only records. The two clears need a second, explicit step.

5. **The front page replaces the story.** `/` is a scroll-driven page (GSAP
   ScrollTrigger) over a three.js Moon whose south-polar cap is the real LOLA
   hillshade in its own stereographic projection; the rest of the globe is
   drawn and labelled as a drawing. The four story ideas are its sections, with
   the story's drawings kept as the still version for reduced motion and no
   WebGL. `/story` redirects to `/#why`. three.js and GSAP load only with the
   front page's chunk.

6. **A guide bar, not a modal tour.** Nine steps along the bottom, one feature
   each, in an order that keeps the default dates until a mission's page is
   opened last. Each step takes the visitor to its page and outlines the
   element it describes (`data-guide`). It opens on the first visit to the
   dashboard, closes to a *Guide* button in the header, and never blocks the
   page.

## Consequences

- Anyone who can reach the front page is a project manager. That is the
  requirement for judging, stated in the API docs, the security section of the
  system design and the runbook, and it is one environment variable from off.
- The integration client is signed in by default; `anon_client` tests the
  401s. The e2e helpers sign in from Node, so a test that blocks the API in the
  browser still starts in the dashboard.
- The offline copy has no server to sign in to: it opens with an offline
  session, and the Project section says its controls need the live service.
- A real deployment needs an identity provider in front of `/auth` and roles
  beyond one. The role check is a single dependency (`deps.project_manager`),
  so adding a read-only role later touches one place.

## Amendment, 24 September 2026: one view

With one stakeholder, a switch for "how much detail" asked the project manager
to choose a version of the product before using it. It was removed. The plain
wording is the only wording; what Expert added (the professional terms, what
blocks the Sun and Earth, the margins and sources) opens from the content
itself: a number's label, or a closed row beside the chart. The AI activity log
moved from the header into Settings → Project, next to the controls that act on
it, and the header keeps only the five tabs, Guide and Settings.

