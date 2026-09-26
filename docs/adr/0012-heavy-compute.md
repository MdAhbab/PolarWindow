# ADR-12: Heavy work runs as jobs in Postgres; every answer records what it used

**Status:** Accepted
**Date:** 2026-09-26
**Relates to:** ADR-1, ADR-8

## Context

Trajectory design, launch calendars, contact plans with relays, viewsheds and
weather hindcasts take seconds to minutes. They cannot run on a request, and
Redis here is deliberately disposable (no persistence), so it cannot hold a
queue.

## Decision

1. **A `jobs` table** with `FOR UPDATE SKIP LOCKED` leasing and LISTEN/NOTIFY
   wake-ups; a partial unique index on (kind, params hash, engine closure)
   makes a repeated request join the existing job.
2. **A `compute` worker process** runs jobs. The API enqueues and reads.
3. **`assessments` and `assessment_inputs`** record every lifecycle answer and
   exactly what it used: feed snapshot ids, catalogue versions, the kernel set
   hash, the terrain product, entered values, parent assessments and the code
   version. Re-running with the same inputs must give the same answer.

## Consequences

- Jobs are auditable with SQL, survive restarts and need no new service.
