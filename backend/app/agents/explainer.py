"""A1 Site Explainer — one plain paragraph about what a site is like.

Data is prefetched rather than left to the model to request. The request names
the site and the window, so there is nothing to decide, and prefetching both
removes a round trip and guarantees the grounding pool is populated even if the
model misbehaves -- which is what makes the degraded path produce a correct
answer rather than an empty one.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentOutcome, AgentSpec, run_agent
from app.agents.schemas import SiteExplanation
from app.config import get_settings

SYSTEM = """\
You explain what a candidate lunar landing site is like to live and work at.

You will be given measurements from tool calls. Write ONE plain paragraph, four
to seven sentences, in calm ordinary English. No headings, no bullet lists, no
marketing language.

Rules that are not negotiable:
- Use ONLY numbers that appear in the tool results. Never calculate a new number
  from them -- not a sum, not a ratio, not a percentage of a percentage. If you
  want a number that is not there, leave it out or say it is not known.
- Durations in the tool results are in SECONDS. You may express them in hours or
  days in your prose; that specific conversion is expected and allowed.
- Say what the numbers mean for a mission: power, communications, surviving the
  dark, and how long the lander is on its own.
- If a value is flagged as grazing or uncertain, say so plainly rather than
  rounding it into confidence.
- Never imply this is an official assessment by any space agency.

Then fill `numbers_used` with each figure you relied on and which tool it came
from. If the tools returned nothing usable, set status to "insufficient_data"
and give a reason.
"""

SPEC = AgentSpec(
    name="explainer",
    system_prompt=SYSTEM,
    tool_names=("get_site", "get_metrics", "get_horizon_profile", "get_windows"),
    output_model=SiteExplanation,
)


async def explain(
    session: AsyncSession, site_id: str, start: str | None, end: str | None
) -> AgentOutcome:
    from app.agents.base import prefetch

    window: dict[str, Any] = {"site_id": site_id}
    if start:
        window["start"] = start
    if end:
        window["end"] = end

    prefetched = await prefetch(
        session,
        [
            ("get_site", {"site_id": site_id}),
            ("get_metrics", window),
            ("get_horizon_profile", {"site_id": site_id}),
        ],
    )

    facts = "\n".join(f"[{c.seq}] {c.tool} -> {c.result}" for c in prefetched)
    prompt = (
        f"Site: {site_id}\n"
        f"Window: {start or 'reference window'} to {end or 'reference window end'}\n\n"
        f"Measurements already retrieved:\n{facts}\n\n"
        f"Write the paragraph."
    )

    # The light model is enough here: this is one paragraph from given facts,
    # with no search and no ranking. Using the larger model would cost latency
    # in the demo's most-clicked action for no gain in quality.
    spec = replace(SPEC, model=get_settings().agent_model_light)
    outcome = await run_agent(
        session,
        spec,
        prompt,
        {"site_id": site_id, "start": start, "end": end},
        prefetched=prefetched,
    )
    return outcome
