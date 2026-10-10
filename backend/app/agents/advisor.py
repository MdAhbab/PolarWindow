"""A2 Trade-off Advisor — rank sites against a stated requirement.

The failure mode this agent is designed against is specific: presented with
sites that all miss the requirement, a helpful model ranks the least-bad one and
describes it warmly, and the reader takes that as a pass. ``any_satisfies`` is a
required field and ``guards.check_negative_result`` refuses an answer that says
false without also saying so in words.
"""

from __future__ import annotations

from app.agents.base import AgentOutcome, AgentSpec, run_agent
from app.agents.schemas import TradeOffAdvice
from app.agents.tools import Session

SYSTEM = """\
You help a mission planner decide between candidate lunar south pole landing
sites, given a requirement stated in ordinary language.

Work strictly like this:
1. Call search_sites(limit=4) to get candidate landing sites.
2. Call compare_sites with those candidate site_ids to retrieve all measurements in a single call.
3. DO NOT call any more tools. You have all data needed. Immediately evaluate the requirements and produce the final answer.

Evaluation rules:
- Turn the stated requirement into checks you can actually evaluate against the
  available measurements, and say in `requirement_summary` how you read it.
- For each site, record each check as satisfied or not, with the observed value.
- Rank the sites based on how well they meet the criteria.
- Durations in tool results are SECONDS. Converting to hours or days is allowed;
  any other arithmetic is not.
- Use ONLY numbers present in tool results. Never compute a new figure.
- If NO site satisfies every requirement, set `any_satisfies` to false and write
  `nothing_satisfies_message` saying plainly that nothing meets it. You may still
  rank the sites, but the message must make clear none of them pass. Do not
  present the best of a failing set as a success.
- If the requirement mentions something this dataset does not measure -- watts,
  payload mass, data rate, soil, temperature -- say so explicitly in the check's
  note instead of substituting a proxy. This dataset has sunlight duration,
  Earth-contact duration, darkness, blackouts, terrain and coordinates. Nothing
  else.
- Earth contact here is geometric line of sight only. It is not a link budget.
"""

SPEC = AgentSpec(
    name="advisor",
    system_prompt=SYSTEM,
    tool_names=("search_sites", "compare_sites"),
    output_model=TradeOffAdvice,
    max_rounds=6,
)


async def advise(
    session: Session, requirement: str, start: str | None, end: str | None
) -> AgentOutcome:
    prompt = (
        f"Requirement: {requirement}\n"
        f"Window: {start or 'reference window'} to {end or 'reference window end'}\n\n"
        f"Find and rank the sites. Remember to state plainly if none qualify."
    )
    return await run_agent(
        session, SPEC, prompt, {"requirement": requirement, "start": start, "end": end}
    )
