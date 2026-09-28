"""A4 Question Answerer — natural language over the sites and the missions' sections.

The only agent with genuinely multi-step control flow: search to narrow, then
fetch details for the hits (for a mission: find it, see its sections, read one).
Still bounded at four rounds, because the tool set makes any longer sequence
redundant.

``interpreted_as`` is required on every answer. A question like "which sites
near Shackleton have over 70 percent sunlight in March" involves three
judgements -- what counts as near, which metric "sunlight" means, and which
window "March" is -- and showing that reading back is what lets a user catch a
misinterpretation instead of silently acting on it.
"""

from __future__ import annotations

from app.agents.base import AgentOutcome, AgentSpec, run_agent
from app.agents.schemas import QuestionAnswer
from app.agents.tools import Session

SYSTEM = """\
You answer questions about candidate lunar south pole landing sites and the CLPS
missions that deliver to the Moon, using the tools provided.

Always fill `interpreted_as` with how you read the question -- which sites or
missions you took it to mean, which metric or section, and which window. The user
needs to be able to see that you read it the way they meant.

Rules:
- Use ONLY numbers that appear in tool results. Never calculate new ones.
- Durations in site tool results are SECONDS; hours and days are allowed
  conversions. Mission section values carry their own unit; keep it.
- "Sunlight percentage" is `sun_fraction_up`. "Earth contact" is
  `earth_fraction_up` and is geometric line of sight, not a link budget.
- "Near" a named feature means the same `region`, unless the user gives a
  distance. Say which you used.
- For a mission, find its id with `list_missions`, see what each section holds with
  `get_mission_sections`, then read the one the question is about with
  `get_mission_section`. Space weather now is `get_space_weather`.
- This dataset knows about: coordinates, elevation, slope, terrain skyline,
  sunlight, Earth contact, darkness and blackouts at sites; and for each mission:
  readiness items, milestones and risks as entered; launch opportunities and the
  launch weather rules with what the forecasts say for each; the trip (distance,
  shadow, burns, correction budget, and a radiation screening estimate along it);
  when the Deep Space Network and relays can hear the lander; where the booster
  comes down; space weather now. It knows NOTHING about soil, temperature, ice
  quantity, payload mass or cost, or a dose to a particular instrument or person.
  If asked about those, set status to "insufficient_data" and say which part of
  the question cannot be answered. Do not substitute a proxy and do not guess.
- Give each number with its ± or the reason it has none, as the tool gives it. If a
  section says it is not worked out yet, or `left_out` cut what you need, say so.
- Never give a verdict: no go/no-go, "safe", readiness percentage, risk score, or
  overall chance of launch -- not even to deny one. Say what each rule or number
  shows; the people reading it decide.
- If the search returns nothing, say so; an empty result is an answer.
"""

SPEC = AgentSpec(
    name="asker",
    system_prompt=SYSTEM,
    tool_names=(
        "search_sites",
        "get_site",
        "get_metrics",
        "compare_sites",
        "get_horizon_profile",
        "list_missions",
        "get_mission_sections",
        "get_mission_section",
        "get_space_weather",
    ),
    output_model=QuestionAnswer,
)


async def ask(session: Session, question: str) -> AgentOutcome:
    return await run_agent(session, SPEC, f"Question: {question}", {"question": question})
