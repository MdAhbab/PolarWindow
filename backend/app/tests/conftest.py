"""Shared fixtures and the rules that keep the suite honest.

Two of these matter more than the rest:

* ``no_live_gemini`` fails any test that lets an HTTP request escape to a model
  provider. Forgetting a mock then costs a loud failure rather than money and a
  flaky suite.
* ``skip_without_kernels`` / ``skip_without_db`` turn missing inputs into skips
  rather than errors, so ``make test-fast`` is genuinely runnable on a laptop
  with nothing installed.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest


def _with_suffix_db(url: str, suffix: str) -> str:
    """``.../polar_window?x`` -> ``.../polar_window_test?x``; idempotent."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    if not name or name.endswith(suffix):
        return url
    return urlunsplit(parts._replace(path=f"/{name}{suffix}"))


def _redis_db(url: str, db: int) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{db}"))


def pytest_configure(config: pytest.Config) -> None:
    """Point the whole suite at its own database and Redis index.

    Integration tests write (agent runs, cached payloads). They used to write
    into the development database, so a test run changed what the running app
    served. Now they use ``polar_window_test`` (``make test-db`` builds it from
    the migrations and a copy of the seeded rows) and Redis database 1.
    ``PW_TEST_DATABASE_URL`` / ``PW_TEST_REDIS_URL`` override the derived names.
    """
    os.environ.setdefault("PW_ENV", "test")
    from app.config import get_settings

    s = get_settings()
    os.environ["PW_DATABASE_URL"] = os.environ.get(
        "PW_TEST_DATABASE_URL", _with_suffix_db(s.database_url, "_test")
    )
    os.environ["PW_REDIS_URL"] = os.environ.get("PW_TEST_REDIS_URL", _redis_db(s.redis_url, 1))
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def settings():
    from app.config import get_settings

    return get_settings()


#: The unpatched model call, kept so ``gemini_http`` can put it back.
_REAL: dict[str, object] = {}


@pytest.fixture(autouse=True)
def no_live_gemini(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test may reach a real model provider. Enforced at the transport seam.

    Blanking the API key is not sufficient: a test that set a fake key once
    sent a real request to generativelanguage.googleapis.com. So the block sits
    at `app.agents.base._generate`, our own documented boundary, where it holds
    whatever the SDK does underneath. Tests that exercise the loop override it
    explicitly: `fake_gemini` scripts `_generate` itself, and `gemini_http`
    restores the real call and scripts the HTTP responses with respx (the SDK's
    async client speaks httpx, so respx sees it), with every other request
    refused.

    With no key the stand-in behaves exactly as the real transport does and
    raises `GeminiUnavailable`, so the "not configured" path is the one under
    test. It used to raise an AssertionError unconditionally, which the loop
    caught as a generic failure: the no-key tests passed without ever reaching
    the branch they were named after.
    """
    monkeypatch.setenv("PW_GEMINI_API_KEY", "")

    from app.agents import base
    from app.config import get_settings

    _REAL.setdefault("generate", base._generate)
    # Model cooldowns live in the process; one test's quota error must not
    # skip a model in the next.
    base.reset_model_cooldowns()

    async def blocked(*_args: object, **_kwargs: object) -> dict:
        if not get_settings().gemini_api_key:
            raise base.GeminiUnavailable("PW_GEMINI_API_KEY is not set")
        raise AssertionError(
            "A test tried to call the real model API. Use the `fake_gemini` "
            "fixture to script responses instead."
        )

    monkeypatch.setattr(base, "_generate", blocked)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """Script model responses at the transport boundary.

    Yields a setter taking a list of payloads; each call to the model consumes
    the next one, and the last repeats. A payload may be a dict (returned as a
    JSON answer), a list of tool calls, or an exception instance to raise.
    """
    from app.agents import base

    state: dict[str, object] = {"queue": [], "calls": 0}

    async def fake(model, contents, system_prompt, tool_decls, *, response_schema, timeout_s):
        """Stand in for one model call.

        The loop makes two kinds of call and the fake has to tell them apart, or
        a scripted answer gets eaten by the gather phase and the retry under
        test never happens:

        * **gather** (`response_schema is None`) -- the model may request tools.
          A queued *list* is a batch of tool calls and is consumed here.
          Anything else means "nothing to fetch", and is left for the answer
          phase rather than consumed.
        * **answer** (`response_schema` set) -- consumes the next payload: a
          dict is returned as JSON, a string as raw text (to exercise schema
          failures), an exception is raised.
        """
        import json as _json

        queue: list = state["queue"]  # type: ignore[assignment]
        state["calls"] = cast(int, state["calls"]) + 1
        head = queue[0] if queue else {}

        if response_schema is None:
            if isinstance(head, list):
                queue.pop(0)
                return {
                    "function_calls": head,
                    "text": "",
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                }
            return {
                "function_calls": [],
                "text": "",
                "prompt_tokens": 100,
                "completion_tokens": 5,
            }

        item = queue.pop(0) if len(queue) > 1 else head
        if isinstance(item, BaseException):
            raise item
        text = item if isinstance(item, str) else _json.dumps(item)
        return {
            "function_calls": [],
            "text": text,
            "prompt_tokens": 120,
            "completion_tokens": 60,
        }

    monkeypatch.setattr(base, "_generate", fake)
    monkeypatch.setenv("PW_GEMINI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    def script(*payloads: object) -> dict[str, object]:
        state["queue"] = list(payloads)
        return state

    yield script
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def kernels_available(settings) -> bool:
    from app.core.kernels import missing

    return not missing(settings.kernel_dir)


@pytest.fixture(autouse=True)
def skip_without_kernels(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("requires_kernels"):
        from app.config import get_settings
        from app.core.kernels import missing

        absent = missing(get_settings().kernel_dir)
        if absent:
            pytest.skip(f"SPICE kernels missing: {', '.join(absent)} (run make kernels)")


@pytest.fixture(autouse=True)
def skip_without_dem(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("requires_dem"):
        from app.config import get_settings

        if not get_settings().regional_dem_path.exists():
            pytest.skip("LOLA DEM subset missing (run make seed)")


@pytest.fixture(autouse=True)
def skip_without_db(request: pytest.FixtureRequest) -> None:
    """Skip DB-backed tests when Postgres is not up.

    A plain socket probe rather than a query: it needs no event loop, no driver
    and no credentials, so it works identically from sync and async tests and
    cannot itself fail for a reason unrelated to the database being reachable.
    """
    if not request.node.get_closest_marker("requires_db"):
        return

    import socket
    from urllib.parse import unquote, urlparse

    from app.config import get_settings

    url = urlparse(get_settings().database_url)
    query: dict[str, str] = {}
    for part in (url.query or "").split("&"):
        if "=" in part:
            key, value = part.split("=", 1)
            query[key] = value

    # A unix-socket DSN carries its directory in ?host=; TCP carries it in the
    # netloc. Both spellings appear in this project's defaults.
    if query.get("host", "").startswith("/"):
        sock_path = Path(unquote(query["host"])) / f".s.PGSQL.{query.get('port', '5432')}"
        if not sock_path.exists():
            pytest.skip(f"Postgres socket not found at {sock_path} (run make services)")
        return

    host = url.hostname or "localhost"
    port: int = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        pytest.skip(f"Postgres not reachable at {host}:{port} (run make services)")


@pytest.fixture(autouse=True)
async def fresh_engine() -> AsyncIterator[None]:
    """Give every test its own async engine.

    ``get_engine`` is lru_cached, so without this the asyncpg pool created by
    the first DB test outlives the event loop it was bound to. Later tests then
    reuse connections attached to a closed loop, which surfaces as
    "coroutine Connection._cancel was never awaited" and as tests that pass
    alone and fail in a batch -- the least pleasant failure mode there is.
    """
    yield
    from app.db.session import dispose_engine, get_engine, get_sessionmaker

    try:
        await dispose_engine()
    except Exception:
        pass
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    # The Redis client is process-global for the same reason the engine is, and
    # needs the same treatment for the same reason. So is the geometry memo: a
    # test that changes what is seeded must not be answered from the last one.
    from app.services import cache, site_service

    site_service.clear_memo()

    try:
        await cache.reset()
    except Exception:
        pass


@pytest.fixture
async def anon_client() -> AsyncIterator:
    """An ASGI client against the real app, with no session. No uvicorn, so tests stay fast."""
    import httpx

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as c,
        app.router.lifespan_context(app),
    ):
        yield c


@pytest.fixture
async def client(anon_client) -> AsyncIterator:
    """The same client, signed in as the project manager, as the dashboard always is."""
    from app.services import auth_service

    token, _ = auth_service.issue_demo()
    anon_client.headers["Authorization"] = f"Bearer {token}"
    yield anon_client


GEMINI_URL = r"https://generativelanguage\.googleapis\.com/.*:generateContent"


@pytest.fixture
def gemini_http(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """Script Gemini at the HTTP layer, through the real SDK (ADR-3 amendment).

    Yields ``(script, route)``: ``script(*responses)`` queues
    ``httpx.Response`` objects or exceptions, one per model request, the last
    repeating; ``route.calls`` holds the requests actually sent. Any request
    that is not a generateContent call fails the test.
    """
    import respx

    from app.agents import base
    from app.config import get_settings

    monkeypatch.setattr(base, "_generate", _REAL["generate"])
    monkeypatch.setenv("PW_GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    import httpx

    queue: list[httpx.Response | BaseException] = []

    def respond(request: httpx.Request) -> httpx.Response:
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, BaseException):
            raise item
        return item

    def script(*responses: httpx.Response | BaseException) -> None:
        queue[:] = list(responses)

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as rx:
        route = rx.post(url__regex=GEMINI_URL).mock(side_effect=respond)
        yield script, route
    get_settings.cache_clear()
