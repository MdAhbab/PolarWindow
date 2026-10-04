"""FastAPI application factory.

Startup loads SPICE kernels but **does not exit if they are missing**. That is
deliberate: a process that dies at boot reports its problem to a log nobody is
reading, whereas one that starts and reports `status: down` on `/healthz` puts
the actual error message -- filename, URL, and the command that fixes it -- in
front of the person looking at the screen. The kernel error is the single most
common way this project breaks, so it gets the visible failure mode.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.limits import AGENTS, COMPARE, SIGN_IN, WRITES, BodyLimit, RateLimit
from app.config import ENGINE_VERSION, get_settings
from app.core import spice
from app.core.kernels import KernelError
from app.services.job_service import QueueFull

log = logging.getLogger("polar_window")

#: The body of an unhandled failure. Same shape as every other error -- the
#: problem detail inside `detail` -- because the frontend's ErrorPanel reads
#: `detail.ui.still_works`, and a 500 that put it anywhere else rendered as a
#: shrug at exactly the moment the user most needed to know what still works.
INTERNAL_ERROR: dict[str, Any] = {
    "detail": {
        "type": "https://polar-window.dev/errors/internal",
        "title": "Something failed on our side",
        "status": 500,
        "detail": "The request could not be completed.",
        "ui": {
            "still_works": "Other sites and windows are unaffected. "
            "The site list and terrain are unchanged.",
            "retryable": True,
            "action": None,
        },
    }
}


class ProblemOn500:
    """Turn an unhandled exception into a problem detail *inside* CORS.

    Starlette runs its own 500 handler in the outermost middleware, outside
    CORS, so the response it sends carries no ``Access-Control-Allow-Origin``.
    The browser then reports a network failure instead of the 500, the
    frontend shows "cannot reach the service", and the server's own words
    about what still works are thrown away. Catching here, below CORS, gives
    the browser a readable response with the right headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception:
            log.exception("unhandled error on %s", scope.get("path"))
            if started:
                raise
            response = JSONResponse(status_code=500, content=INTERNAL_ERROR)
            await response(scope, receive, send)


DESCRIPTION = """
Sun, Earth and terrain geometry for candidate landing sites at the Moon's south pole.

Four numbers decide a mission and this API exists to serve them:

1. **Sunlit seconds** in the window — power
2. **Earth-contact seconds** in the window — direct-to-Earth comms
3. **Longest unbroken dark gap** — survival
4. **Longest unbroken comms blackout** — autonomy

There is deliberately **no composite score**. A score ranks sites on one axis and
hides which corner was given up, and the trade is the product.

Every response carries a `meta` object with `computed_at`, `resolution` and
`uncertainty`. `uncertainty` is never absent and never null: where a value cannot
be known, the field says so (`grazing: true`, `edge_timing_s: null`) rather than
reporting a plausible number.

**Not an official product of any space agency.** Data product names are the public
identifiers of the inputs, nothing more.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        state = spice.load(s.kernel_dir, allow_download=s.download_kernels_on_start)
        log.info("SPICE ready: %d kernels in %.0f ms", state.count, state.furnsh_ms)
    except KernelError as exc:
        # Logged in full, surfaced through /healthz, and not fatal.
        log.error(
            "SPICE kernels unavailable. The API will start and report this "
            "through /healthz.\n%s",
            exc,
        )
    yield
    from app.db.session import dispose_engine

    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="POLAR WINDOW",
        version=ENGINE_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        openapi_url=f"{s.api_prefix}/openapi.json",
        docs_url=f"{s.api_prefix}/docs",
        redoc_url=None,
    )

    # Order matters: Starlette wraps the last-added middleware outermost. The
    # 500 handler must sit inside CORS (see ProblemOn500), and compression
    # between them so error bodies are compressed like any other.
    app.add_middleware(ProblemOn500)
    # Limits sit inside CORS (and outside the 500 handler), so a refusal
    # reaches the browser with its headers and its own words.
    app.add_middleware(BodyLimit, max_bytes=s.max_body_bytes)
    if s.rate_limits:
        app.add_middleware(
            RateLimit,
            prefix=s.api_prefix,
            per_minute={
                SIGN_IN: s.rate_sign_in_per_min,
                AGENTS: s.rate_agents_per_min,
                COMPARE: s.rate_compare_per_min,
                WRITES: s.rate_writes_per_min,
            },
        )
    # A 2,835-sample timeline is ~210 KB of JSON. Measured on it: level 1 gives
    # 82 KB in 1.1 ms, level 5 gives 74 KB in 4.9 ms, level 9 the same 74 KB in
    # 18 ms. Level 1 keeps ~90 % of the saving at a quarter of the CPU, which is
    # the right trade on an endpoint whose whole budget is latency.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=1)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(s.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Tile-Source", "X-Tile-Note", "ETag"],
    )

    from app.api.v1.routes import (
        agents,
        auth,
        compare,
        contact_relays,
        contact_tiles,
        health,
        jobs,
        lifecycle,
        missions,
        ready,
        settings,
        sites,
        tiles,
        windows,
    )

    app.include_router(health.router, prefix=s.api_prefix)
    app.include_router(sites.router, prefix=s.api_prefix)
    app.include_router(missions.router, prefix=s.api_prefix)
    app.include_router(windows.router, prefix=s.api_prefix)
    app.include_router(compare.router, prefix=s.api_prefix)
    app.include_router(tiles.router, prefix=s.api_prefix)
    app.include_router(contact_tiles.router, prefix=s.api_prefix)
    app.include_router(contact_relays.router, prefix=s.api_prefix)
    app.include_router(agents.router, prefix=s.api_prefix)
    app.include_router(auth.router, prefix=s.api_prefix)
    app.include_router(settings.router, prefix=s.api_prefix)
    app.include_router(jobs.router, prefix=s.api_prefix)
    app.include_router(lifecycle.router, prefix=s.api_prefix)
    app.include_router(ready.router, prefix=s.api_prefix)

    # /healthz is also mounted unprefixed: container health checks and load
    # balancers look there, and they should not need to know the API version.
    app.include_router(health.router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Give FastAPI's own validation errors the same shape as ours.

        Without this there are two error contracts: hand-written problem details
        from the service layer, and FastAPI's `{"detail": [...]}` list from
        parameter constraints. The frontend renders `ui.still_works` on every
        error panel, so a response missing it renders as a shrug -- and the
        user cannot tell which layer rejected them, nor should they have to.
        """
        problems = [
            f"{'.'.join(str(p) for p in e['loc'][1:]) or 'body'}: {e['msg']}" for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "type": "https://polar-window.dev/errors/invalid-request",
                    "title": "That request could not be read",
                    "status": 422,
                    "detail": "; ".join(problems),
                    "ui": {
                        "still_works": "Everything else is unaffected. Adjusting the "
                        "highlighted value will work.",
                        "retryable": False,
                        "action": "Adjust the request",
                    },
                }
            },
        )

    @app.exception_handler(QueueFull)
    async def queue_full(request: Request, exc: QueueFull) -> JSONResponse:
        """Too many answers are waiting for a compute worker to queue another."""
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={
                "detail": {
                    "type": "https://polar-window.dev/errors/queue-full",
                    "title": "Too many answers are being worked out",
                    "status": 503,
                    "detail": f"{exc.queued} answers are waiting for a compute worker, the "
                    "most this service queues. This one was not added.",
                    "ui": {
                        "still_works": "Every answer already worked out can still be read, "
                        "and every other section still answers.",
                        "retryable": True,
                        "action": "Try again in a minute",
                    },
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Wrap plain HTTP exceptions in RFC 7807 problem details with ui.still_works."""
        detail: Any = exc.detail
        if isinstance(detail, dict) and "ui" in detail:
            return JSONResponse(
                status_code=exc.status_code,
                headers=exc.headers,
                content={"detail": detail},
            )
        slug = "not-found" if exc.status_code == 404 else "http-error"
        title = "Not found" if exc.status_code == 404 else "Request error"
        still_works = (
            "The site list and other sections are available."
            if exc.status_code == 404
            else "Everything else is unaffected."
        )
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "detail": {
                    "type": f"https://polar-window.dev/errors/{slug}",
                    "title": title,
                    "status": exc.status_code,
                    "detail": str(exc.detail),
                    "ui": {
                        "still_works": still_works,
                        "retryable": False,
                        "action": "Check the address or browse the site list",
                    },
                }
            },
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {
            "name": "POLAR WINDOW",
            "engine_version": ENGINE_VERSION,
            "docs": f"{s.api_prefix}/docs",
            "openapi": f"{s.api_prefix}/openapi.json",
            "notice": "Not an official product of any space agency.",
        }

    return app


app = create_app()
