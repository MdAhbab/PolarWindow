"""A3 Audience Writer — same facts, three documents.

One generation produces all three. Three independent generations could disagree
about the numbers, and a planner memo that contradicts the public explainer is
worse than either being less polished -- so the three documents share one fact
set by construction, and a test asserts their numbers are identical.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentOutcome, AgentSpec, prefetch, run_agent
from app.agents.schemas import AudienceBrief
from app.agents.tools import Session

SYSTEM = """\
You write three short documents about one lunar landing site, from one set of
measurements.

  planner_memo      — for a mission planner. Direct, quantitative, decision-first.
  lesson_plan       — for a secondary school teacher. Includes one activity or
                      discussion question the class can actually do.
  public_explainer  — for a general reader. No jargon, no numbers without a
                      plain-English anchor for what they mean.

The three documents describe the SAME facts. Every number that appears in more
than one document must be identical in each. Simplifying the words never
simplifies the claim: the public explainer may use fewer numbers, but it may not
use different ones, and it may not drop a caveat to read more smoothly.

Each document carries a `caveat`: the one limitation a reader of that document
most needs to know. It is never omitted.

Rules:
- Use ONLY numbers that appear in the tool results. Never calculate new ones.
- Durations in tool results are SECONDS; expressing them in hours or days is
  expected and allowed.
- Never imply this is an official product or assessment of any space agency.
- Fill `shared_numbers` with the figures all three documents draw on.
"""

SPEC = AgentSpec(
    name="writer",
    system_prompt=SYSTEM,
    tool_names=("get_site", "get_metrics", "get_horizon_profile"),
    output_model=AudienceBrief,
)


async def brief(session: Session, site_id: str, start: str | None, end: str | None) -> AgentOutcome:
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
        f"Site: {site_id}\n\nMeasurements:\n{facts}\n\n"
        f"Write all three documents from these same facts."
    )
    outcome = await run_agent(
        session,
        SPEC,
        prompt,
        {"site_id": site_id, "start": start, "end": end},
        prefetched=prefetched,
    )
    return outcome
