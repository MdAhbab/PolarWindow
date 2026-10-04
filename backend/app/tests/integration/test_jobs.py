"""Jobs (ADR-12): single-flight, leasing, heartbeat, retries, lineage."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db.repositories.jobs import InputRef, JobRepository
from app.db.session import session_scope
from app.services import job_service
from app.workers.compute import HandlerResult, JobContext, Worker, backoff_s

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
async def clean_jobs():
    async with session_scope() as s:
        await s.execute(text("DELETE FROM jobs"))
        await s.execute(text("DELETE FROM assessment_inputs"))
        await s.execute(text("DELETE FROM assessments"))
    yield


async def _enqueue(kind: str = "toy", params: dict | None = None) -> dict:
    async with session_scope() as s:
        a = await job_service.answer_or_enqueue(
            s, kind=kind, closure="net-1", params=params or {"x": 1}, mission_id="im-2"
        )
    assert a.job is not None and a.assessment is None
    return a.job


async def test_a_repeated_request_joins_the_job_already_queued() -> None:
    first = await _enqueue()
    second = await _enqueue()
    assert first["job_id"] == second["job_id"]
    assert first["status"] == "queued"
    third = await _enqueue(params={"x": 2})
    assert third["job_id"] != first["job_id"]
    # A wait says why: the first job is worked out before it.
    assert "1 answer is being worked out first" in third["message"]
    assert "first" not in first["message"]


async def test_the_key_ignores_parameter_order() -> None:
    a = job_service.params_hash("k", "c", {"a": 1, "b": [1, 2]})
    b = job_service.params_hash("k", "c", {"b": [1, 2], "a": 1})
    assert a == b
    assert a != job_service.params_hash("k", "c2", {"a": 1, "b": [1, 2]})


async def test_two_workers_never_claim_the_same_job() -> None:
    for i in range(6):
        await _enqueue(params={"i": i})

    async def claim(owner: str) -> list[int]:
        got: list[int] = []
        while True:
            async with session_scope() as s:
                j = await JobRepository(s).claim(owner, 60)
            if j is None:
                return got
            got.append(j.id)

    a, b = await asyncio.gather(claim("a"), claim("b"))
    assert len(a) + len(b) == 6
    assert not set(a) & set(b)


async def test_a_finished_job_leaves_an_answer_with_its_inputs() -> None:
    job = await _enqueue()

    async def toy(ctx: JobContext) -> HandlerResult:
        ctx.progress(0.5, "halfway")
        return HandlerResult(
            result={"answer": 42},
            inputs=[InputRef(kind="catalogue", ref="ground_stations", version="abc")],
        )

    ran = await Worker(owner="w1", handlers={"toy": toy}).run_once()
    assert ran is not None and ran.id == job["job_id"]
    async with session_scope() as s:
        ref = await job_service.get_job(s, job["job_id"])
        assert ref["status"] == "done" and ref["progress"] == 1.0
        assert ref["assessment_id"] is not None
        again = await job_service.answer_or_enqueue(
            s, kind="toy", closure="net-1", params={"x": 1}, mission_id="im-2"
        )
    assert again.assessment is not None
    assert again.assessment.result == {"answer": 42}
    assert again.assessment.inputs == (InputRef("catalogue", "ground_stations", "abc", None),)
    assert again.assessment.code_version


async def test_a_failing_job_is_retried_then_failed_with_its_reason() -> None:
    job = await _enqueue()

    async def boom(ctx: JobContext) -> HandlerResult:
        raise RuntimeError("no kernels")

    w = Worker(owner="w1", handlers={"toy": boom})
    await w.run_once()
    async with session_scope() as s:
        j = await JobRepository(s).get(job["job_id"])
        assert j is not None and j.status == "queued" and j.attempts == 1
        # Make it due now rather than after the back-off.
        await s.execute(text("UPDATE jobs SET run_after = now()"))
    await w.run_once()
    async with session_scope() as s:
        await s.execute(text("UPDATE jobs SET run_after = now()"))
    await w.run_once()
    async with session_scope() as s:
        ref = await job_service.get_job(s, job["job_id"])
    assert ref["status"] == "failed"
    assert "no kernels" in ref["message"]
    # A failed key is reported, not re-queued on the next page load.
    async with session_scope() as s:
        again = await job_service.answer_or_enqueue(
            s, kind="toy", closure="net-1", params={"x": 1}, mission_id="im-2"
        )
    assert again.job is not None and again.job["job_id"] == job["job_id"]


async def test_an_unknown_kind_fails_rather_than_spinning() -> None:
    job = await _enqueue(kind="nobody-handles-this")
    w = Worker(owner="w1", handlers={})
    for _ in range(3):
        await w.run_once()
        async with session_scope() as s:
            await s.execute(text("UPDATE jobs SET run_after = now()"))
    async with session_scope() as s:
        ref = await job_service.get_job(s, job["job_id"])
    assert ref["status"] == "failed"
    assert "no handler" in ref["message"]


async def test_a_dead_workers_job_is_claimed_again_after_its_lease() -> None:
    job = await _enqueue()
    async with session_scope() as s:
        claimed = await JobRepository(s).claim("dead-worker", 60)
        assert claimed is not None
        await s.execute(text("UPDATE jobs SET lease_until = now() - interval '1 second'"))
    async with session_scope() as s:
        again = await JobRepository(s).claim("live-worker", 60)
    assert again is not None and again.id == job["job_id"]
    assert again.attempts == 2 and again.lease_owner == "live-worker"
    async with session_scope() as s:
        # The dead worker's late heartbeat is refused.
        assert not await JobRepository(s).heartbeat(job["job_id"], "dead-worker", 60)
        assert await JobRepository(s).heartbeat(job["job_id"], "live-worker", 60, progress=0.3)


async def test_a_stopped_worker_hands_its_job_back_without_spending_attempt() -> None:
    job = await _enqueue()
    started = asyncio.Event()

    async def slow_handler(ctx: JobContext) -> HandlerResult:
        started.set()
        await asyncio.sleep(30)
        return HandlerResult(result={"ok": True})

    worker = Worker(owner="stopping-worker", handlers={"toy": slow_handler})
    worker_task = asyncio.create_task(worker.run_once())

    await asyncio.wait_for(started.wait(), timeout=2.0)
    async with session_scope() as s:
        ref = await job_service.get_job(s, job["job_id"])
        assert ref["status"] == "running"

    worker.stop()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(worker_task, timeout=2.0)

    async with session_scope() as s:
        rec = await JobRepository(s).get(job["job_id"])
        ref = await job_service.get_job(s, job["job_id"])
        assert rec is not None
        assert rec.status == "queued"
        assert rec.attempts == 0
        assert rec.lease_owner is None
        assert "Interrupted when its worker stopped" in ref["message"]


async def test_a_job_out_of_attempts_with_a_dead_lease_is_failed() -> None:
    job = await _enqueue()
    async with session_scope() as s:
        await s.execute(
            text(
                "UPDATE jobs SET status='running', attempts=max_attempts, "
                "lease_until = now() - interval '1 second'"
            )
        )
        assert await JobRepository(s).fail_exhausted() == 1
    async with session_scope() as s:
        ref = await job_service.get_job(s, job["job_id"])
    assert ref["status"] == "failed"


async def test_back_off_doubles_and_is_capped() -> None:
    assert [backoff_s(a) for a in (1, 2, 3)] == [30.0, 60.0, 120.0]
    assert backoff_s(20) == 900.0


async def _failed_job() -> dict:
    job = await _enqueue(params={"x": "fails"})
    async with session_scope() as s:
        await s.execute(
            text("UPDATE jobs SET status = 'failed', error = :e WHERE id = :i"),
            {"i": job["job_id"], "e": "RuntimeError: no kernels\nTraceback ..."},
        )
    return job


async def test_a_retry_is_recorded_against_the_person_who_asked(client) -> None:
    job = await _failed_job()
    r = await client.post(f"/api/v1/jobs/{job['job_id']}/retry")
    assert r.status_code == 200, r.text
    again = r.json()
    assert again["status"] == "queued" and again["job_id"] != job["job_id"]
    h = await client.get("/api/v1/history", params={"entity": "job", "id": str(job["job_id"])})
    (entry,) = h.json()["entries"]
    assert entry["action"] == "retry" and entry["by"].startswith("Test manager")
    assert entry["before"] == {"status": "failed", "error": "RuntimeError: no kernels"}
    assert entry["after"]["job_id"] == again["job_id"]


@pytest.fixture
def queue_of_one(monkeypatch):
    monkeypatch.setenv("PW_MAX_QUEUED_JOBS", "1")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("PW_MAX_QUEUED_JOBS")
    get_settings.cache_clear()


async def test_a_full_queue_takes_no_new_job(queue_of_one) -> None:
    """Asking for arbitrary windows cannot grow the queue without end."""
    first = await _enqueue()
    # Joining the job already queued for the same key is still fine.
    assert (await _enqueue())["job_id"] == first["job_id"]
    with pytest.raises(job_service.QueueFull) as exc:
        await _enqueue(params={"x": 2})
    assert exc.value.queued == 1


async def test_a_full_queue_answers_503_with_a_wait(queue_of_one, anon_client) -> None:
    await _enqueue()
    r = await anon_client.get(
        "/api/v1/missions/im-2/contact",
        params={"start": "2025-03-07T00:00:00Z", "end": "2025-03-09T00:00:00Z"},
    )
    assert r.status_code == 503, r.text
    assert r.headers["retry-after"] == "60"
    d = r.json()["detail"]
    assert d["type"].endswith("/queue-full") and d["ui"]["retryable"] is True


async def test_latest_for_job_uses_index() -> None:
    async with session_scope() as s:
        await s.execute(text("SET enable_seqscan = off"))
        res = await s.execute(
            text(
                "EXPLAIN SELECT * FROM jobs "
                "WHERE kind = 'launch' AND params_hash = 'test' AND closure = 'test' "
                "ORDER BY id DESC LIMIT 1"
            )
        )
        plan = " ".join(r[0] for r in res.fetchall())
        assert "ix_jobs_latest" in plan
