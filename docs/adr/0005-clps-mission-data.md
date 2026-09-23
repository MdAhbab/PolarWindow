# ADR-5: CLPS mission data is a curated, cited file, ingested at seed time

**Status:** Accepted
**Date:** 2026-09-23
**Deciders:** backend lead
**Relates to:** `docs/system-design.md` §10 (contract v2), N8 (no network for mission data at runtime)

## Context

The challenge is **CLPS Lunar Mission Browser**. From v2 on, the product starts
from CLPS missions: every delivery with its provider, lander, task order,
target, dates, status, outcome and payload manifest. The mission table becomes
the first thing a judge sees, so it is also the first thing an expert judge
checks.

The data has four properties that decide where it should live:

1. **It is small.** A few dozen deliveries, each with ten or so payloads.
2. **It changes slowly and irregularly.** Awards, launches and outcomes arrive a
   few times a year, in press releases.
3. **No authoritative machine-readable feed exists.** NASA publishes CLPS
   deliveries as web pages and news releases. NSSDCA has per-mission records.
   Neither is an API with stable fields for payload type, target coordinate and
   date precision.
4. **Every field needs a human-checked source.** A wrong payload list is the
   failure an expert notices first. A missing value has to be shown as missing,
   not guessed.

The demo must also run with the wifi off (the build guide's offline rule).

## Decision

Mission facts live in **`data/missions.json`**. It is committed, and every
record carries `sources[]` (url, title, publisher, accessed date) and
`unconfirmed_fields[]`. `data/ingest_missions.py` validates the file with
pydantic at **seed time** and loads it into `missions` and `mission_payloads`.

Validation **fails the seed** if any of these hold:
- a record has no source;
- a payload has no `source_url`;
- an enum is unknown;
- a coordinate is out of range;
- a field is null without being listed in `unconfirmed_fields`.

Nothing is fetched from the web at runtime. The research that fills the file is
logged in `docs/data-sources.md`, including the rule that assigns
`instrument_types`.

## Options Considered

### Option A: Curated JSON, validated at seed (chosen)
| Dimension | Assessment |
|---|---|
| Complexity | Low: one file, one validator, one loader |
| Cost | The research time, once, before the event |
| Scalability | Fine to hundreds of records |
| Team familiarity | High |

**Pros:** Works offline. Every field is reviewable in a diff. Provenance is part
of the schema, so an unsourced fact cannot load. It is deterministic for the
golden and integration tests.
**Cons:** It goes stale, and freshness depends on someone re-checking.

### Option B: Scrape nasa.gov CLPS pages at runtime or seed time
| Dimension | Assessment |
|---|---|
| Complexity | High: HTML parsing, layout drift, rate limits |
| Cost | A parser per page layout, plus breakage during the demo |
| Scalability | Irrelevant at this size |
| Team familiarity | Medium |

**Pros:** Fresher, in principle.
**Cons:** Prose pages don't have the fields we need (payload type, date
precision, coordinate kind), so a human still has to interpret them. It fails
offline. A layout change silently corrupts the table.

### Option C: A third-party lunar mission API or dataset
**Pros:** Machine-readable.
**Cons:** None was found that is authoritative for CLPS payload manifests with
per-field sources. Using one would move the trust problem to a source a judge
cannot check.

## Trade-off Analysis

The question is not freshness against effort. It is **checkability against
freshness**. Option A makes every number and name traceable to a URL a judge
can open, and lets the UI mark exactly which fields are unconfirmed. B and C
trade that away for freshness that doesn't matter over a 48-hour judging window.

Staleness is handled by making it visible:
- each source carries an `accessed` date;
- the API serves `data_version`;
- the 28 Oct 2026 full-statement checkpoint includes a re-verification pass.

## Consequences

- **Easier:**
  - Offline demos.
  - Deterministic tests.
  - Answering "where does this payload list come from?" with a link.
  - Agents can only ever repeat sourced facts, because tools read the same tables.
- **Harder:**
  - Keeping it current. The re-verification has to be done by hand.
  - `instrument_types` is our classification, not NASA's. The docs have to say so.
- **Revisit** if NASA publishes a machine-readable CLPS manifest. The loader's
  input changes; the validation contract stays.

## Action Items

1. [ ] `data/missions.json`, following the research rules in the plan (polar
       missions fully sourced first).
2. [ ] `docs/data-sources.md`: the research log, the source precedence
       (nasa.gov → NSSDCA → LROC/LRO → provider), and the instrument-type
       assignment rule.
3. [ ] `data/ingest_missions.py` with the pydantic contract; `make seed` runs it.
4. [ ] Tests: schema validation, source completeness, and "every null field is
       listed as unconfirmed".
