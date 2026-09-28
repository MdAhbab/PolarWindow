"""The project manager's writes: every change needs a named session, bodies and
values are bounded, and a caller who writes too often is told to wait (plan track I)."""

from __future__ import annotations

import math
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Body, FastAPI
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.api.limits import AGENTS, COMPARE, SIGN_IN, WRITES, BodyLimit, RateLimit, allowance
from app.api.v1.schemas.contact import BookingIn
from app.api.v1.schemas.ready import ParameterIn, RiskIn, RiskLinks
from app.api.v1.schemas.weather import LimitIn, OfficialForecastIn, SeaLimitsIn
from app.main import create_app

P = "/api/v1"

#: Non-GET routes that do not change anything recorded, and why they need less
#: than a named project manager.
NOT_A_CHANGE = {
    ("POST", f"{P}/auth/demo"): set(),  # signing in
    ("POST", f"{P}/compare"): set(),  # a comparison computed on the request; nothing stored
    ("POST", f"{P}/agents/explain"): {"project_manager"},  # the AI assistant reads
    ("POST", f"{P}/agents/advise"): {"project_manager"},
    ("POST", f"{P}/agents/brief"): {"project_manager"},
    ("POST", f"{P}/agents/ask"): {"project_manager"},
}


def _deps(d: object, acc: set[str]) -> set[str]:
    for sub in getattr(d, "dependencies", []):
        acc.add(getattr(sub.call, "__name__", ""))
        _deps(sub, acc)
    return acc


def test_every_change_needs_a_named_project_manager() -> None:
    app = create_app()
    writes = [
        (m, r)
        for r in app.routes
        if isinstance(r, APIRoute)
        for m in sorted(r.methods - {"GET", "HEAD"})
    ]
    assert len(writes) > 20
    for method, route in writes:
        found = _deps(route.dependant, set())
        need = NOT_A_CHANGE.get((method, route.path), {"named_manager"})
        assert need <= found, f"{method} {route.path} lacks {need - found}"


def test_the_browser_may_send_every_method_the_api_has() -> None:
    """PATCH (a readiness item, a part, a risk) was missing from the CORS list."""
    import asyncio

    async def go() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.options(
                f"{P}/risks/r-1",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )

    r = asyncio.run(go())
    assert r.status_code == 200, r.text
    assert "PATCH" in r.headers["access-control-allow-methods"]


def test_what_a_request_counts_against() -> None:
    assert allowance("GET", f"{P}/missions", P) is None
    assert allowance("OPTIONS", f"{P}/risks/1", P) is None
    assert allowance("POST", f"{P}/auth/demo", P) == SIGN_IN
    assert allowance("POST", f"{P}/agents/ask", P) == AGENTS
    assert allowance("POST", f"{P}/compare", P) == COMPARE
    assert allowance("PATCH", f"{P}/risks/1", P) == WRITES
    assert allowance("DELETE", f"{P}/settings/cache", P) == WRITES


def test_a_sliding_minute_per_caller() -> None:
    now = [0.0]
    rl = RateLimit(lambda *_: None, {WRITES: 3}, P, clock=lambda: now[0])  # type: ignore[arg-type]
    assert [rl.check(WRITES, "a") for _ in range(3)] == [None, None, None]
    now[0] = 20.0
    wait = rl.check(WRITES, "a")
    assert wait is not None and math.isclose(wait, 40.0)
    assert rl.check(WRITES, "b") is None  # another address has its own minute
    now[0] = 60.5  # the first three have left the minute
    assert rl.check(WRITES, "a") is None
    assert rl.check(SIGN_IN, "a") is None  # no allowance configured: not limited


def _tiny(max_bytes: int = 100, per_min: int = 2) -> FastAPI:
    app = FastAPI()

    @app.post("/api/v1/things")
    async def things(body: dict = Body(...)) -> dict:
        return {"n": len(body)}

    @app.get("/api/v1/things")
    async def read() -> dict:
        return {}

    app.add_middleware(BodyLimit, max_bytes=max_bytes)
    app.add_middleware(RateLimit, per_minute={WRITES: per_min}, prefix=P)
    return app


@pytest.mark.asyncio
async def test_too_many_changes_are_refused_with_a_wait_and_reads_never_are() -> None:
    transport = httpx.ASGITransport(app=_tiny())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        ok = [await c.post(f"{P}/things", json={"a": 1}) for _ in range(2)]
        assert [r.status_code for r in ok] == [200, 200]
        r = await c.post(f"{P}/things", json={"a": 1})
        assert r.status_code == 429
        assert 1 <= int(r.headers["retry-after"]) <= 60
        d = r.json()["detail"]
        assert d["type"].endswith("/too-many-requests") and d["ui"]["still_works"]
        assert "2 changes a minute" in d["detail"]
        reads = [(await c.get(f"{P}/things")).status_code for _ in range(10)]
        assert reads == [200] * 10


@pytest.mark.asyncio
async def test_a_body_over_the_limit_is_refused_before_it_is_read() -> None:
    transport = httpx.ASGITransport(app=_tiny(max_bytes=100, per_min=100))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.post(f"{P}/things", json={"a": "x" * 50})).status_code == 200
        r = await c.post(f"{P}/things", json={"a": "x" * 200})
        assert r.status_code == 413
        assert r.json()["detail"]["type"].endswith("/too-large")

        # Sent in chunks with no Content-Length: counted while it is read.
        async def chunks() -> AsyncIterator[bytes]:
            yield b'{"a": "'
            yield b"x" * 200
            yield b'"}'

        r = await c.post(
            f"{P}/things", content=chunks(), headers={"content-type": "application/json"}
        )
        assert r.status_code == 413
        assert r.json()["detail"]["type"].endswith("/too-large")


def test_values_are_finite_and_bounded() -> None:
    nan, inf = float("nan"), float("inf")
    for bad in (nan, inf, 31.0):
        with pytest.raises(ValidationError):
            SeaLimitsIn(wave_height_m=bad)
    with pytest.raises(ValidationError):
        SeaLimitsIn(wind_m_s=nan)
    SeaLimitsIn(wave_height_m=2.5, wind_m_s=12.0)
    for bad in (nan, inf):
        with pytest.raises(ValidationError):
            ParameterIn(value=bad)
        with pytest.raises(ValidationError):
            LimitIn(rule_id="cumulus", value=bad, unit="m/s")
    with pytest.raises(ValidationError):
        LimitIn(rule_id="x" * 65, value=1.0, unit="m/s")


def test_text_and_lists_are_bounded() -> None:
    url = "https://example.org/f.pdf"
    with pytest.raises(ValidationError):
        OfficialForecastIn(probability_pct=10, concerns=["x" * 501], pdf_url=url)
    with pytest.raises(ValidationError):
        OfficialForecastIn(probability_pct=10, pdf_url="https://" + "x" * 2000)
    with pytest.raises(ValidationError):
        RiskLinks(parts=["p"] * 201)
    with pytest.raises(ValidationError):
        RiskLinks(parts=["p" * 161])
    base = {"title": "t", "cause": "c", "consequence_text": "q"}
    rating = {"category": "technical", "likelihood": 1, "consequence": 1}
    with pytest.raises(ValidationError):
        RiskIn(**base, scale_id="s" * 65, ratings=[rating])
    with pytest.raises(ValidationError):
        RiskIn(**base, scale_id="s", ratings=[rating] * 21)
    with pytest.raises(ValidationError):
        BookingIn(station="d" * 65, start="2026-01-01T00:00Z", end="2026-01-01T01:00Z")
