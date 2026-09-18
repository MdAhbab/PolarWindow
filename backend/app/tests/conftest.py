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


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("PW_ENV", "test")


@pytest.fixture(scope="session")
def settings():
    from app.config import get_settings

    return get_settings()


@pytest.fixture(autouse=True)
def no_live_gemini(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test may reach a real model provider. Enforced at the transport seam.

    Blanking the API key is not sufficient, and finding that out was instructive:
    a test that set a fake key sent a real request to
    generativelanguage.googleapis.com and got back a 400. `respx` could not
    intercept it because google-genai's sync client runs inside
    `asyncio.to_thread`, so the patched transport in the main thread never saw
    it.

    So the block is placed at `app.agents.base._generate` -- our own documented
    boundary -- where it holds regardless of what the SDK does underneath. A
    test that wants to exercise the loop overrides it explicitly with
    `fake_gemini`, which is visible in the test body.
    """
    monkeypatch.setenv("PW_GEMINI_API_KEY", "")

    from app.agents import base
    from app.config import get_settings

    async def blocked(*_args: object, **_kwargs: object) -> dict:
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
    # needs the same treatment for the same reason.
    from app.services import cache

    try:
        await cache.reset()
    except Exception:
        pass


@pytest.fixture
async def client() -> AsyncIterator:
    """An ASGI client against the real app. No uvicorn, so tests stay fast."""
    import httpx

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as c,
        app.router.lifespan_context(app),
    ):
        yield c
