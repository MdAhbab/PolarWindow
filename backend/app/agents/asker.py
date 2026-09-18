"""A4 Question Answerer — natural language over the site database.

The only agent with genuinely multi-step control flow: search to narrow, then
fetch details for the hits. Still bounded at four rounds, because the tool set
makes any longer sequence redundant.

``interpreted_as`` is required on every answer. A question like "which sites
near Shackleton have over 70 percent sunlight in March" involves three
judgements -- what counts as near, which metric "sunlight" means, and which
window "March" is -- and showing that reading back is what lets a user catch a
misinterpretation instead of silently acting on it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentOutcome, AgentSpec, run_agent
from app.agents.schemas import QuestionAnswer

SYSTEM = """\
You answer questions about candidate lunar south pole landing sites using the
tools provided.

Always fill `interpreted_as` with how you read the question -- which sites you
took it to mean, which metric, and which window. The user needs to be able to
see that you read it the way they meant.

Rules:
- Use ONLY numbers that appear in tool results. Never calculate new ones.
- Durations in tool results are SECONDS; hours and days are allowed conversions.
- "Sunlight percentage" is `sun_fraction_up`. "Earth contact" is
  `earth_fraction_up` and is geometric line of sight, not a link budget.
- "Near" a named feature means the same `region`, unless the user gives a
  distance. Say which you used.
- This dataset knows about: coordinates, elevation, slope, terrain skyline,
  sunlight duration, Earth-contact duration, darkness, blackouts. It knows
  NOTHING about soil, temperature, ice quantity, radiation, payload or cost.
  If asked about those, set status to "insufficient_data" and say which part of
  the question cannot be answered. Do not substitute a proxy and do not guess.
- If the search returns nothing, say so; an empty result is an answer.
"""

SPEC = AgentSpec(
    name="asker",
    system_prompt=SYSTEM,
    tool_names=("search_sites", "get_site", "get_metrics", "compare_sites", "get_horizon_profile"),
    output_model=QuestionAnswer,
)


async def ask(session: AsyncSession, question: str) -> AgentOutcome:
    return await run_agent(session, SPEC, f"Question: {question}", {"question": question})
