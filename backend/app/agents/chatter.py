"""A5 Ask: a quick chat answer about whatever page the person is on.

The asker's tools, in a quick mode: the light model chain, at most three
rounds, two to four sentences. What the question is about is first worked out
by simple rules (a mission named in it or open on the page, a step, the space
weather, a site) and those tools are called before the model sees anything, so
the grounding pool is never empty and the answer without a model is a real one:
built from the same tool results with the same sentences the other agents'
fallbacks use, and checked by the same guard.

``actions`` (links into the app) are built here from the tool calls and the
page, never by the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from app.agents import base, guards, tools
from app.agents.asker import SPEC as ASKER
from app.agents.base import AgentOutcome, AgentSpec, model_chain, run_agent
from app.agents.schemas import Status
from app.agents.tools import Session

SYSTEM = """\
You answer quick questions in a lunar mission planning dashboard, about the
page the person is on: a CLPS mission and its six steps (ready, launch, trip,
landing on the surface, contact, return), a landing site, or the space weather.

Answer in two to four plain sentences. Fill `interpreted_as` with how you read
the question (which mission, step, site or window), and `follow_ups` with up to
three short next questions the person might ask, with no numbers in them. Do
not write links or paths: the app adds them.

Rules:
- Use ONLY numbers and dates that appear in tool results. Never calculate new
  ones. Durations in site results are SECONDS; hours and days are allowed.
- A step that says it is not worked out yet, or has no data, is an answer: say so.
- Never give a verdict: no go/no-go, "safe", readiness percentage, risk score or
  overall chance. Say what each number or rule shows; people decide.
- If the data cannot answer it, set status to "insufficient_data" and say what
  is missing. Do not guess.
- The prompt gives today's date. A date before it has passed: never call it
  upcoming or next, and go by each mission's status. Do not write today's date
  in the answer.
"""


class ChatAnswer(BaseModel):
    """What the model (or the rules, without one) writes. Links are added afterwards."""

    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str | None = None
    answer: str | None = Field(default=None, description="Two to four plain sentences.")
    interpreted_as: str | None = None
    follow_ups: list[str] = Field(default_factory=list, max_length=3)


SPEC = AgentSpec(
    name="chatter",
    system_prompt=SYSTEM,
    tool_names=ASKER.tool_names,
    output_model=ChatAnswer,
    max_rounds=3,
)

#: The hub's address for each step (``landing`` is shown as Surface).
SECTION_SLUG = {
    "ready": "ready",
    "launch": "launch",
    "launch_weather": "launch",
    "trip": "trip",
    "landing": "surface",
    "contact": "contact",
    "return": "return",
}
SECTION_LABEL = {
    "ready": "Ready",
    "launch": "Launch",
    "launch_weather": "Launch",
    "trip": "Trip",
    "landing": "Surface",
    "contact": "Contact",
    "return": "Return",
}
STATE_WORDS = {
    "available": "answered",
    "computing": "being worked out",
    "no_data": "no data",
    "needs_input": "needs input",
    "not_applicable": "does not apply",
}
_SECTION_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (s, re.compile(p, re.IGNORECASE))
    for s, p in (
        ("ready", r"\bready\b|\breadiness\b|\brisks?\b|\bparts?\b|\bmilestones?\b"),
        ("launch", r"\blaunch\w*|\blift[- ]?off\b|\brocket\b|\bpad\b"),
        ("trip", r"\btrip\b|\btransit\b|\bcruise\b|\bburns?\b|\btrajector\w+|\bradiation\b"),
        ("contact", r"\bcontact\b|\bdsn\b|\bdeep space network\b|\brelays?\b|\bradio\b|\bcomms?\b"),
        ("return", r"\breturn\b|\bbooster\b|\brecovery\b|\bsplash\w*"),
        ("landing", r"\bsurface\b|\blanding\b|\bsunlight\b|\bsunlit\b|\bdark\w*|\bnight\b"),
    )
)
_SPACE_WEATHER = re.compile(
    r"space weather|\bsolar\b|\bflares?\b|\bkp\b|geomagnetic|\bprotons?\b|\bcmes?\b|"
    r"\bstorms?\b|\bsun now\b",
    re.IGNORECASE,
)
_SITE_WORDS = re.compile(
    r"\bsites?\b|\bsunlight\b|\bsunlit\b|\bdark\w*\b|\bskyline\b|\bhorizon\b|\bearth\b",
    re.IGNORECASE,
)
#: Most characters of one prefetched result shown in the prompt (the guard sees all of it).
PROMPT_RESULT_MAX = 6000


@dataclass
class Intent:
    """What the question was read as being about, by rules."""

    mission_id: str | None = None
    mission_name: str | None = None
    section: str | None = None
    site_id: str | None = None
    space_weather: bool = False
    names: dict[str, str] = field(default_factory=dict)


def _word_re(name: str) -> re.Pattern[str]:
    body = re.escape(name).replace(r"\ ", r"[\s-]*").replace(r"\-", r"[\s-]*")
    return re.compile(rf"(?<![\w]){body}(?![\w])", re.IGNORECASE)


def section_of(question: str) -> str | None:
    for section, pat in _SECTION_WORDS:
        if pat.search(question):
            return section
    return None


def mission_named(question: str, missions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The mission the question names (its name or id), longest name first."""
    cands: list[tuple[int, dict[str, Any]]] = []
    for m in missions:
        for n in {str(m.get("name") or ""), str(m.get("mission_id") or "")}:
            if len(n) >= 3 and _word_re(n).search(question):
                cands.append((len(n), m))
    return max(cands, key=lambda c: c[0])[1] if cands else None


async def route(
    session: Session, question: str, ctx: dict[str, Any]
) -> tuple[Intent, list[tools.ToolCallLog]]:
    """Read the question by rules and fetch what it is about, as logged tool calls."""
    calls: list[tools.ToolCallLog] = []

    async def call(name: str, args: dict[str, Any]) -> tools.ToolCallLog:
        c = await tools.execute(session, name, args, len(calls) + 1)
        calls.append(c)
        return c

    intent = Intent(section=section_of(question) or ctx.get("section"))
    listing = await call("list_missions", {})
    missions = [m for m in (listing.result or {}).get("missions") or [] if isinstance(m, dict)]
    intent.names = {str(m["mission_id"]): str(m["name"]) for m in missions if m.get("mission_id")}
    named = mission_named(question, missions)
    if named is not None:
        intent.mission_id = str(named["mission_id"])
    elif ctx.get("mission_id") and str(ctx["mission_id"]) in intent.names:
        intent.mission_id = str(ctx["mission_id"])
    if intent.mission_id:
        intent.mission_name = intent.names.get(intent.mission_id)
    intent.space_weather = bool(_SPACE_WEATHER.search(question))
    if intent.space_weather:
        await call("get_space_weather", {})
    if intent.mission_id:
        await call("get_mission_sections", {"mission_id": intent.mission_id})

    site_id = ctx.get("site_id")
    if not site_id and not intent.mission_id and not intent.space_weather:
        found = await call("search_sites", {"limit": 50})
        rows = [r for r in (found.result or {}).get("sites") or [] if isinstance(r, dict)]
        hits = [r for r in rows if r.get("name") and _word_re(str(r["name"])).search(question)]
        if hits:
            site_id = str(max(hits, key=lambda r: len(str(r["name"])))["site_id"])
    if site_id and (not intent.mission_id or _SITE_WORDS.search(question)):
        intent.site_id = str(site_id)
        await call("get_site", {"site_id": intent.site_id})
        window = {"site_id": intent.site_id}
        for k in ("start", "end"):
            if ctx.get(k):
                window[k] = str(ctx[k])
        await call("get_metrics", window)
    return intent, calls


# ---------------------------------------------------------------------------
# The answer without a model
# ---------------------------------------------------------------------------


def _pool(calls: list[tools.ToolCallLog], req: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"seq": 0, "tool": guards.USER_REQUEST_TOOL, "result": req},
        *(c.as_dict() for c in calls),
    ]


def _grounded(text: str, pool: list[dict[str, Any]]) -> bool:
    return guards.check({"answer": text}, pool).ok


def _value(q: Any) -> float | None:
    v = q.get("value") if isinstance(q, dict) else None
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def space_weather_sentences(result: dict[str, Any]) -> list[str]:
    """Space weather now in words, from the tool's own values; a missing one says why."""
    now = ((result.get("data") or {}).get("now")) or {}
    out: list[str] = []
    parts: list[str] = []
    kp = _value(now.get("kp"))
    if kp is not None:
        parts.append(f"Kp is {kp:.1f}")
    p10 = _value(now.get("proton_10mev_pfu"))
    if p10 is not None:
        parts.append(f"protons above 10 MeV are at {p10:.2f} pfu")
    wind = _value(now.get("solar_wind_km_s"))
    if wind is not None:
        parts.append(f"the solar wind is {wind:.0f} km/s")
    xray = now.get("xray_class")
    if isinstance(xray, str) and xray:
        parts.append(f"the X-ray class is {xray}")
    if parts:
        out.append("Space weather now, as NOAA SWPC reports it: " + ", ".join(parts) + ".")
    else:
        why = (
            (now.get("kp") or {}).get("missing_reason") if isinstance(now.get("kp"), dict) else None
        )
        out.append(
            "No space weather reading is recorded yet"
            + (f": {str(why).rstrip('.')}." if why else ".")
        )
    alerts = [a for a in now.get("alerts") or [] if isinstance(a, str) and a]
    if alerts:
        out.append(f"SWPC's latest alert in the last day: {alerts[0].rstrip('.')}.")
    return out


def _label(row: dict[str, Any]) -> str:
    return SECTION_LABEL.get(str(row["section"]), str(row["section"]))


def _state(row: dict[str, Any]) -> str:
    return STATE_WORDS.get(str(row.get("state")), str(row.get("state")))


def mission_sentences(
    result: dict[str, Any], name: str, focus: str | None, pool: list[dict[str, Any]]
) -> list[str]:
    """A mission's steps in words: the one asked about first, with its own summary."""
    rows = [s for s in result.get("sections") or [] if isinstance(s, dict) and s.get("section")]
    if not rows:
        return []
    out: list[str] = []
    focus_row = next((s for s in rows if s["section"] == focus), None) if focus else None
    if focus_row is not None:
        label = SECTION_LABEL.get(focus_row["section"], focus_row["section"])
        summary = str(focus_row.get("summary") or "").strip().rstrip(".")
        line = f"{label} for {name}: {summary}." if summary else ""
        if not line or not _grounded(line, pool):
            state = STATE_WORDS.get(str(focus_row.get("state")), str(focus_row.get("state")))
            line = f"{label} for {name}: {state}."
        out.append(line)
    others = [s for s in rows if s is not focus_row]
    listed = "; ".join(f"{_label(s)} {_state(s)}" for s in others)
    if listed:
        out.append(
            f"{'The other steps' if focus_row is not None else f'The steps for {name}'}: {listed}."
        )
    if focus_row is None:
        for s in rows:
            if s.get("state") != "available" or len(out) >= 3:
                continue
            summary = str(s.get("summary") or "").strip().rstrip(".")
            line = f"{SECTION_LABEL.get(s['section'], s['section'])}: {summary}."
            if summary and _grounded(line, pool):
                out.append(line)
    return out


def deterministic_answer(
    calls: list[tools.ToolCallLog], reason: str, req: dict[str, Any]
) -> dict[str, Any]:
    """The answer from the tool results alone, in the chat's contract (no model)."""
    pool = _pool(calls, req)
    names: dict[str, str] = {}
    for c in calls:
        if c.tool == "list_missions" and not c.error:
            for m in (c.result or {}).get("missions") or []:
                if isinstance(m, dict) and m.get("mission_id"):
                    names[str(m["mission_id"])] = str(m.get("name") or m["mission_id"])
    focus = req.get("section")
    sentences: list[str] = []
    about: list[str] = []
    for c in calls:
        if c.error:
            continue
        if c.tool == "get_mission_sections":
            mid = str((c.result or {}).get("mission_id"))
            name = names.get(mid, mid)
            sentences += mission_sentences(c.result or {}, name, focus, pool)
            about.append(name + (f", {SECTION_LABEL[focus]}" if focus in SECTION_LABEL else ""))
        elif c.tool == "get_space_weather":
            sentences += space_weather_sentences(c.result or {})
            about.append("the space weather now")
    site_facts, site_id = base._facts(calls)
    if site_facts:
        sentences += site_facts
        about.append(f"the site {site_id}" if site_id else "the site")
    sentences = [s for s in sentences if _grounded(s, pool)][:4]
    if not sentences:
        return {
            "status": "insufficient_data",
            "reason": (
                f"{reason} Nothing in the question or on this page matched a mission, a site "
                "or the space weather in the data, so there is nothing to answer from."
            ).strip(),
            "answer": None,
            "interpreted_as": "Read by simple rules: no mission, site or space weather matched.",
            "follow_ups": [
                "Which missions land near the south pole?",
                "What is the space weather now?",
            ],
        }
    interpreted = "Read by simple rules (the written answer is unavailable): about " + (
        "; ".join(dict.fromkeys(about)) + "."
    )
    if not _grounded(interpreted, pool):
        interpreted = "Read by simple rules (the written answer is unavailable)."
    return {
        "status": "ok",
        "reason": reason,
        "answer": " ".join(sentences),
        "interpreted_as": interpreted,
        "follow_ups": [f for f in follow_ups(names, req) if _grounded(f, pool)][:3],
    }


def follow_ups(names: dict[str, str], req: dict[str, Any]) -> list[str]:
    mid = req.get("mission_id")
    name = names.get(str(mid)) if mid else None
    if name:
        asked = req.get("section")
        options = [
            ("launch", f"When can {name} launch?"),
            ("contact", f"When can the Deep Space Network hear {name}?"),
            ("landing", f"How much sunlight does {name} get on the surface?"),
            ("trip", f"What does {name} go through on the way?"),
        ]
        return [q for s, q in options if s != asked]
    return ["Which missions are planned next?", "What is the space weather now?"]


base.FALLBACKS[ChatAnswer.__name__] = deterministic_answer


# ---------------------------------------------------------------------------
# Links into the app (built here, never by the model)
# ---------------------------------------------------------------------------


def actions(
    calls: list[tools.ToolCallLog], ctx: dict[str, Any], intent: Intent
) -> list[dict[str, str]]:
    """Up to three in-app places holding the full answer: from the tools called and the page."""
    out: list[dict[str, str]] = []
    names = dict(intent.names)
    site_names: dict[str, str] = {}
    for c in calls:
        if c.error:
            continue
        r = c.result or {}
        if c.tool == "list_missions":
            for m in r.get("missions") or []:
                if isinstance(m, dict) and m.get("mission_id"):
                    names.setdefault(str(m["mission_id"]), str(m.get("name") or m["mission_id"]))
        if c.tool == "get_site" and r.get("site_id"):
            site_names[str(r["site_id"])] = str(r.get("name") or r["site_id"])

    def add(label: str, href: str) -> None:
        if href not in {a["href"] for a in out}:
            out.append({"label": label, "href": href})

    for c in calls:
        if c.error:
            continue
        if c.tool in ("get_mission_section", "get_mission_sections"):
            mid = str(c.args.get("mission_id") or "")
            if not mid:
                continue
            name = names.get(mid, mid)
            base_href = f"/missions/{quote(mid, safe='')}"
            section = c.args.get("section") or intent.section
            if section in SECTION_SLUG:
                add(f"{name} · {SECTION_LABEL[section]}", f"{base_href}/{SECTION_SLUG[section]}")
            add(name, base_href)
        elif c.tool == "get_space_weather":
            add("Space weather now", "/home")
        elif c.tool in ("get_site", "get_metrics", "get_horizon_profile", "get_windows"):
            sid = str(c.args.get("site_id") or "")
            if sid:
                add(site_names.get(sid, sid), f"/site?site={quote(sid, safe='')}")
    if not out and ctx.get("mission_id"):
        mid = str(ctx["mission_id"])
        add(names.get(mid, mid), f"/missions/{quote(mid, safe='')}")
    return out[:3]


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _prompt(
    messages: list[dict[str, Any]],
    ctx: dict[str, Any],
    intent: Intent,
    calls: list[tools.ToolCallLog],
    today: str | None = None,
) -> str:
    where = [f"page {ctx.get('path') or 'unknown'}"]
    if intent.mission_id:
        where.append(f"mission {intent.mission_name or intent.mission_id} (id {intent.mission_id})")
    if intent.section:
        where.append(f"step {SECTION_LABEL.get(intent.section, intent.section)}")
    if intent.site_id:
        where.append(f"site {intent.site_id}")
    if ctx.get("start") or ctx.get("end"):
        where.append(f"dates {ctx.get('start') or '…'} to {ctx.get('end') or '…'}")
    talk = "\n".join(
        f"{'Person' if m['role'] == 'user' else 'You'}: {m['text']}" for m in messages[:-1]
    )
    facts = "\n".join(
        f"[{c.seq}] {c.tool}({json.dumps(c.args)}) -> "
        f"{json.dumps(c.result, default=str)[:PROMPT_RESULT_MAX]}"
        for c in calls
    )
    return (
        (f"Today is {today} (UTC).\n" if today else "")
        + f"Where the person is: {'; '.join(where)}.\n"
        + (f"Conversation so far, oldest first:\n{talk}\n" if talk else "")
        + f"Question: {messages[-1]['text']}\n\n"
        f"Already retrieved:\n{facts}\n\n"
        "Answer in two to four sentences."
    )


def result_of(outcome: AgentOutcome, ctx: dict[str, Any], intent: Intent) -> dict[str, Any] | None:
    """The contract's ``ChatResult`` from the agent's answer, with the app's links added."""
    r = outcome.result
    if r is None:
        return None
    answer = (r.get("answer") or "").strip() or (r.get("reason") or "").strip()
    return {
        "answer": answer or "This cannot be answered from the data here.",
        "interpreted_as": (r.get("interpreted_as") or "").strip()
        or "How the question was read was not given.",
        "follow_ups": [str(f) for f in r.get("follow_ups") or []][:3],
        "actions": actions(outcome.tool_calls, ctx, intent),
    }


async def chat(
    session: Session, messages: list[dict[str, Any]], context: dict[str, Any] | None
) -> AgentOutcome:
    """One quick answer. ``outcome.result`` is the contract's ``ChatResult`` (or None)."""
    ctx = dict(context or {})
    question = str(messages[-1]["text"])
    intent, prefetched = await route(session, question, ctx)
    # Only the person's own words may be quoted: an earlier answer of ours is not a
    # source, so the numbers in it must come from this run's tools again.
    request = {
        "question": question,
        "earlier_questions": [str(m["text"]) for m in messages[:-1] if m["role"] == "user"],
        "context": ctx,
        "mission_id": intent.mission_id,
        "section": intent.section,
    }
    spec = replace(SPEC, models=model_chain(light=True))
    outcome = await run_agent(
        session,
        spec,
        _prompt(messages[-12:], ctx, intent, prefetched, datetime.now(UTC).date().isoformat()),
        request,
        prefetched=prefetched,
    )
    outcome.result = result_of(outcome, ctx, intent)
    return outcome
