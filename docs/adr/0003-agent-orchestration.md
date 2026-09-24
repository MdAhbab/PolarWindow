# ADR-3: A single bounded function-calling loop, not a graph

**Status:** Accepted (amended 2026-09-23, see the end)
**Date:** 2026-09-18
**Deciders:** backend lead
**Relates to:** §6 of the brief, §8 of `docs/system-design.md`, N4

## Context

Four agents sit on top of the deterministic core:

- **A1 Site Explainer** — one site, one window, one paragraph + its sources.
- **A2 Trade-off Advisor** — a requirement in prose ("200 W solar and ≥ 4 h of
  Earth contact per day"), searched and ranked, and it must say plainly when
  nothing qualifies.
- **A3 Audience Writer** — same facts, three documents (planner memo, lesson
  plan, public explainer).
- **A4 Question Answerer** — natural language over the site database.

They reach the system only through six tools in `agents/tools.py`. Model:
`gemini-3.8-flash`, with `gemini-3.5-flash-lite` for short explainers, each at
the head of a fallback chain (amendment below).

The brief's own framing settles half the argument before it starts: *justify
against demo reliability, not elegance.* The requirements that follow from that
are N4 (20 s timeout, one retry, then a deterministic non-AI summary) and the
grounding guard — **reject and retry any response containing a number not
present in the tool outputs** — which the brief calls the single most important
guard.

That guard is the crux. It is not a post-filter bolted onto an orchestration
strategy; it is a **control-flow requirement**: validate → on failure, re-prompt
with the specific violation → on second failure, degrade. Whatever orchestrates
must make that loop obvious, cheap to test, and impossible to bypass.

The shapes of the four agents are also worth noticing before choosing machinery.
A1 is one tool call then one generation. A3 is one fact-gathering phase then
three generations from the *same* facts. A4 is the only genuinely multi-step one
(search, then fetch details for the hits), and it is bounded at two rounds by the
tool set: `search_sites` narrows, `get_metrics`/`compare_sites` resolve. **None
of them branch on model output in a way that changes which tools exist.** There
is no plan-then-execute, no sub-agent delegation, no cyclic refinement.

## Decision

One orchestrator — `agents/base.py::run_agent()` — implementing a bounded
function-calling loop, shared by all four agents. Agents differ only in
(system prompt, allowed tool subset, output pydantic model, model id).

```
run_agent(spec, request):
  budget  = ToolBudget(max_rounds=4, max_calls=8, max_tokens=spec.token_budget)
  deadline = now + 20s
  transcript = [system(spec.prompt), user(render(request))]
  collected  = ToolResults()        # every call, arg, result, and flattened numbers

  for round in 0..budget.max_rounds:
      resp = genai.generate(model=spec.model, contents=transcript,
                            tools=spec.tools,
                            response_schema=spec.output_model if round>0 else None,
                            timeout=remaining(deadline))
      if resp.function_calls:
          for call in resp.function_calls:          # executed concurrently
              result = TOOLS[call.name](**validate(call.args))
              collected.record(call, result)        # → agent_tool_calls
          transcript += tool_results
          continue
      break                                          # model produced an answer

  # ---- the part that actually matters ----
  for attempt in 1..2:
      parsed = spec.output_model.model_validate_json(resp.text)   # contract
      verdict = guards.check(parsed, collected)                   # grounding
      if verdict.ok: return Ok(parsed, provenance=verdict.provenance)
      if attempt == 1:
          transcript += repair_prompt(verdict.violations)         # name the numbers
          resp = genai.generate(...)                              # one retry
      else:
          return Degraded(deterministic_summary(collected), verdict.violations)
```

Four properties of this shape are the reason for it:

1. **The guard is in the control flow, not beside it.** There is no code path
   from a model response to an HTTP response that skips `guards.check`. A graph
   would express the same thing as an edge, which is a weaker guarantee because
   edges are configuration.
2. **Every exit is enumerable.** `ok`, `insufficient_data`, `guard_rejected`,
   `timeout`, `degraded`, `error` — the six values of `agent_runs.status`. A
   demo can show all six from SQL.
3. **The budget is one object.** Rounds, calls, tokens and wall-clock in one
   place, so "why did this agent stop" always has a single answer.
4. **`deterministic_summary(collected)` needs no model.** It renders the tool
   results through a template. This is what makes N4's fallback real rather than
   aspirational: if Gemini is down entirely, A1 still returns a correct
   paragraph, marked `degraded`, built from numbers that are by construction
   grounded.

A3 (three documents) does **not** get three orchestrator runs. It gathers facts
once and asks for a single structured object with three fields, so the three
documents cannot disagree about the numbers — which is the actual risk in
"same facts, three audiences", and one that parallel independent generations
would create rather than solve.

## Options Considered

### Option A: Direct call, no loop (one generation, tools pre-fetched by us)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Lowest |
| Reliability | Highest — no model-chosen control flow at all |
| Capability | **Insufficient for A2 and A4** |
| Latency | Best (~2 s) |

We fetch the data ourselves and hand it to the model as context; the model only
writes prose. Genuinely attractive, and it is what A1 collapses to in practice.
But A4 ("which sites near Shackleton have over 70 % sunlight in March") requires
the *model* to decide the filter arguments, and A2 requires it to decide which
sites to compare after an initial search. Pre-fetching everything for 20 sites
would blow the context and still not answer A4's "near Shackleton". Rejected as
the general mechanism; retained as the **degraded** path, which is a good place
for it.

### Option B (chosen): Bounded function-calling loop, one orchestrator

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low-medium — ~200 lines, one file |
| Reliability | High — bounded, enumerable exits, guard inline |
| Capability | Covers all four agents |
| Latency | 3–8 s typical, 20 s hard ceiling |
| Debuggability | Whole run is one transcript + one `agent_runs` row |

**Pros:** smallest thing that satisfies all four agents; no new dependency beyond
`google-genai`; the retry-on-guard-failure is four lines and directly testable
with `respx` by scripting a first response containing a hallucinated number and
a second that does not; failure modes are exhausted by a small enum.
**Cons:** the loop is imperative and will grow conditionals if agents diverge;
concurrency inside a round is manual; no built-in visualisation.

### Option C: A small graph (LangGraph, or a hand-rolled node/edge runner)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium-high |
| Reliability | Medium — more machinery, more failure surface |
| Capability | Exceeds what is needed |
| Latency | Comparable, plus framework overhead |
| Debuggability | Good *if* the tracing is wired up; opaque if not |

**Pros:** explicit state machine; retry/fallback as first-class edges;
checkpointing; the shape generalises if the agents later gain genuine
multi-step planning; nice diagrams for a presentation.
**Cons:** the decisive one — **there is no branching to model.** Every agent is
`gather → generate → validate → (repair) → done`. Encoding a straight line as a
graph adds a dependency, a state-schema, a serialisation format and a new
vocabulary, and returns a drawing. Under a hackathon budget that is a day spent
on the part that was never going to fail. It also *weakens* the guard guarantee
by turning an inline function call into an edge someone can reroute. LangGraph
additionally pulls a LangChain-adjacent dependency tree we otherwise have no
reason to carry, and its failure modes (version skew, async/sync mismatches)
are precisely the kind that surface at 3 a.m. before a demo.

### Option D: Per-agent bespoke orchestration

Rejected on sight. Four implementations of the guard is four chances to forget
it, and the brief's most important requirement is the one that must not have
four implementations.

## Trade-off Analysis

The honest comparison is B vs C, and it is decided by asking what a graph buys
*here*. Graphs earn their cost when control flow is data-dependent and
non-trivial — a planner that may spawn sub-agents, a workflow that loops until a
critic is satisfied, a pipeline that must resume after a crash. None of that is
present. The only cycle in this system is "guard failed → repair once", which is
a `for attempt in 1..2`.

The reliability argument actually runs *against* the more structured option,
which is counter-intuitive enough to state plainly: reliability here means
"number of places a guard can be bypassed" and "number of dependencies that can
break between now and the demo". The loop scores better on both. Elegance would
favour the graph; the brief explicitly says not to optimise for that, and in this
case it happens also to be the less robust choice.

The cost accepted is that if a fifth agent needs real planning, this loop is the
wrong home for it. That is a cheap cost: the orchestrator is one file and one
function signature, and replacing it does not touch `tools.py`, `guards.py`,
`schemas.py`, or the persistence — which is where the value actually is.

## Consequences

**Easier**
- One place to add logging, so `agent_runs` + `agent_tool_calls` are populated by
  construction rather than by remembering.
- Guards are unit-testable without any orchestration: `check(parsed, collected)`
  is a pure function over two values.
- Mocking is trivial — `respx` intercepts the `google-genai` HTTP calls and the
  whole loop runs offline. No real API key in CI, ever.
- Swapping `gemini-3.5-flash-lite` for A1 is a field on the spec (`models`, the
  chain the agent tries).

**Harder**
- Concurrency within a round is hand-rolled (`asyncio.gather` over tool calls),
  including the timeout accounting against the shared deadline.
- Adding a genuinely branching agent later means either ugly conditionals or the
  rewrite this ADR defers. Accepted, and flagged here so the choice is revisited
  deliberately rather than by accretion.
- The token budget is enforced approximately (we count what the SDK reports after
  the fact); a runaway prompt is caught by the round/call limits, not by a
  pre-flight token count.

**To revisit**
- If any agent starts needing > 4 rounds or conditional tool sets, re-open C.
- If multiple agents must share intermediate state across requests, the
  checkpointing a graph provides stops being overhead.

## Action Items
1. [ ] `agents/base.py`: `AgentSpec`, `ToolBudget`, `run_agent()`, deadline
       accounting, `deterministic_summary()`.
2. [ ] `agents/tools.py`: the six tools with JSON schemas; each returns a
       `ToolResult` carrying its flattened numeric leaves.
3. [ ] `agents/guards.py`: `check_grounding`, `check_refusal`,
       `check_insufficient_data`; pure, no I/O.
4. [ ] `agents/schemas.py`: four pydantic output contracts, each with an
       `insufficient_data` variant.
5. [ ] Persist `agent_runs` + `agent_tool_calls` on every exit path, including
       timeout and error.
6. [ ] `respx` fixtures: a grounded response, a hallucinated-number response, a
       schema-invalid response, a timeout, and a total outage.

---

## Amendment, 2026-09-23: SDK upgrade, async client, thought signatures, HTTP-level mocks

**What changed.** The loop design is unchanged: one bounded function-calling
loop, six tools, grounding guard, 20 s budget, one retry, deterministic
fallback. Four things around it change:

1. **SDK.** `google-genai` is pinned at `0.3.0`, an early release, and no live
   model call has ever been made from this machine (there was no API key). It
   moves to the current release before any live run. The loop calls the SDK's
   **async** client (`client.aio.models.generate_content`) instead of wrapping
   the sync client in `asyncio.to_thread`. Timeouts become cancellations the
   event loop owns.
2. **Thought signatures.** Gemini 3 models return signed thought parts alongside
   function calls. They must be sent back unchanged in the next turn's history,
   or the follow-up call is rejected. The loop therefore appends the model's
   **complete returned `Content`** to the history, never a reconstructed
   function-call part.
3. **Mocks at the HTTP level.** The Action Items asked for `respx` fixtures, and
   the tests instead patched `base._generate` (D18). With the SDK's httpx-based
   async transport, `respx` can intercept the real request. The fixtures (a
   grounded answer, a hallucinated number, schema-invalid output, a timeout, an
   outage) move to HTTP. The `_generate` block stays as a backstop, so a
   forgotten mock still fails loudly. Confirm at upgrade time that the installed
   SDK version really routes through httpx.
4. **Missions.** Agents gain missions **without new tools**. `get_site` returns
   the linked missions, and `search_sites` gains mission filters
   (system-design §10.8). The guard treats ISO dates in tool output as grounded
   tokens.

The status names match the code and README: two guard rejections give
`guard_rejected` plus the deterministic summary, not `insufficient_data`
(D19). `insufficient_data` is the agent's own declared outcome when the tools
don't hold the answer.

**Action items, added**
1. [ ] Upgrade `google-genai` and move to `client.aio`; carry thought signatures
       through the history; live-smoke all four agents.
2. [ ] respx fixtures at the HTTP level, covering the five cases above.
3. [ ] Date-token grounding in `guards.py`, with a test.
4. [ ] Full `meta` (computed_at, resolution, uncertainty) on agent responses and
       on `GET /agents/runs`.

## Amendment, 2026-09-24: a model chain, not a model

Free-tier quotas are per model and per day (20 requests a day on each Flash
model), and a demo that loses its agents when one model's quota runs out is the
failure N4 exists to prevent. So each agent tries an ordered chain
(`PW_AGENT_MODELS`, `PW_AGENT_MODELS_LIGHT`): the Flash models first, then the
Flash-Lite models, whose daily quotas are far larger; nothing older than
Gemini 2.5.

- A run moves to the next model on a 429 (quota), 403 or 404 (not available to
  this key, or not served under that name) and a 5xx (outage). Not on a 400:
  the next model would reject the same request.
- Each model gets a **clean run**. Gemini 3 signs its own function calls, and a
  conversation begun on one model is not continued on another. A model over its
  quota fails on its first request, so moving on costs one round trip.
- A model that failed is skipped until it can answer again: a daily quota until
  midnight Pacific, when the API resets it; a per-minute quota for the delay the
  API asks for; an unknown or forbidden model for six hours; an outage for 30 s.
  The cooldowns live in the process.
- Every skip is in the run's record (`guard_failures`, kind `model_unavailable`)
  and the response's `meta.model` names the model that answered. When no model
  in the chain can answer, the run degrades to the measurement-only summary,
  exactly as with no key.

Considered and not taken: the Antigravity managed agent (Interactions API,
`antigravity-preview-05-2026`). It runs its own multi-step loop on Google's
side, which is the loop this ADR keeps in our code so that every tool call is
bounded, logged and seen by the grounding guard.

