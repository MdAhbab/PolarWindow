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
from fastapi.responses import JSONResponse, ORJSONResponse

from app.config import ENGINE_VERSION, get_settings
from app.core import spice
from app.core.kernels import KernelError

log = logging.getLogger("polar_window")

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(s.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Tile-Source", "ETag"],
    )

    from app.api.v1.routes import agents, compare, health, sites, tiles

    app.include_router(health.router, prefix=s.api_prefix)
    app.include_router(sites.router, prefix=s.api_prefix)
    app.include_router(compare.router, prefix=s.api_prefix)
    app.include_router(tiles.router, prefix=s.api_prefix)
    app.include_router(agents.router, prefix=s.api_prefix)

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

    @app.exception_handler(500)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
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
