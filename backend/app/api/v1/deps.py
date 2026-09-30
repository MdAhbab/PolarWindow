"""Shared route dependencies and the problem-detail translation.

Routes stay thin: parse, delegate, serialise. This module is where a domain
exception becomes an HTTP response, so that no route contains an `except`
clause and every error gets the same shape -- including the `ui` block the
frontend's ErrorPanel renders directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.core.kernels import KernelError
from app.db.session import get_session
from app.services import auth_service
from app.services.geometry_service import StepOutOfRange, WindowTooLong
from app.services.mission_service import MissionNotFound
from app.services.site_service import MaskNotBuilt, SiteNotFound

ERROR_BASE = "https://polar-window.dev/errors"


def problem(
    status: int,
    type_: str,
    title: str,
    detail: str,
    still_works: str,
    *,
    retryable: bool = False,
    action: str | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status,
        headers=headers,
        detail={
            "type": f"{ERROR_BASE}/{type_}",
            "title": title,
            "status": status,
            "detail": detail,
            "ui": {"still_works": still_works, "retryable": retryable, "action": action},
        },
    )


def to_http(exc: Exception) -> HTTPException:
    """Map a domain exception onto a problem detail.

    Each message says what still works, because a failure that takes the whole
    screen down when only one layer is broken is a worse failure than it needs
    to be. Three of the four cases here leave most of the product usable.
    """
    if isinstance(exc, SiteNotFound):
        return problem(
            404,
            "site-not-found",
            "No such site",
            f"'{exc.args[0]}' is not a site in this dataset.",
            "Every other site is unaffected. The site list shows what is available.",
            action="Browse the site list",
        )
    if isinstance(exc, MissionNotFound):
        return problem(
            404,
            "mission-not-found",
            "That mission isn't in the list",
            f"'{exc.args[0]}' is not a CLPS mission in this dataset.",
            "All other missions are available.",
            action="Back to missions",
        )
    if isinstance(exc, MaskNotBuilt):
        return problem(
            409,
            "horizon-not-built",
            "This site has not been surveyed yet",
            str(exc),
            "Sites that have been surveyed are unaffected, and this site's "
            "coordinates and terrain are still shown.",
            retryable=True,
            action="Run make seed",
        )
    if isinstance(exc, StepOutOfRange | WindowTooLong):
        return problem(
            422,
            "bad-window",
            "That window cannot be computed",
            str(exc),
            "Narrowing the window or increasing the step will work.",
            action="Adjust the window",
        )
    if isinstance(exc, KernelError):
        return problem(
            503,
            "kernel-missing",
            # "Ephemeris" is planner vocabulary and this product has educator
            # and public faces too. Name the thing that is missing in words
            # every audience shares; the technical term stays in `detail`.
            "Sun and Earth positions are unavailable",
            str(exc),
            "Horizon masks, terrain and the site list are unaffected; Sun and "
            "Earth positions are not available.",
            retryable=True,
            action="Run make kernels and restart",
        )
    raise exc


async def db() -> AsyncIterator[Any]:
    async for s in get_session():
        yield s


def settings() -> Settings:
    return get_settings()


def window_params(
    start: datetime | None = Query(
        None, description="Window start, ISO 8601 UTC. Defaults to the reference window."
    ),
    end: datetime | None = Query(None, description="Window end, ISO 8601 UTC."),
    step_s: int | None = Query(
        None,
        ge=60,
        le=86400,
        description="Sampling step in seconds. Bounds are enforced by the service, "
        "which returns a 422 explaining the limit rather than silently clamping.",
    ),
    s: Settings = Depends(settings),
) -> tuple[datetime, datetime, int]:
    """Resolve the window, defaulting to the reference window.

    Defaulting rather than requiring: `/metrics` with no arguments should answer
    something useful, and the reference window is what the site list is already
    computed over, so the default is also the fast path.
    """
    step = step_s or s.default_step_s
    if start is None:
        start = s.reference_window_start
    if end is None:
        end = start + timedelta(days=s.reference_window_days)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return start, end, step


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(
    auto_error=False,
    description="A session token from POST /auth/demo, sent as `Authorization: Bearer <token>`.",
)


async def signed_in(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> auth_service.Claims:
    """The caller's session. 401 when there is none or it has ended."""
    challenge = {"WWW-Authenticate": "Bearer"}
    if creds is None:
        raise problem(
            401,
            "not-signed-in",
            "Sign in first",
            "This action needs a session token, and the request did not carry one.",
            "Everything you can read without signing in still works: the missions, "
            "the map and every number.",
            action="Open the dashboard from the home page",
            headers=challenge,
        )
    try:
        return auth_service.verify(creds.credentials)
    except auth_service.InvalidToken as exc:
        raise problem(
            401,
            "session-ended",
            "Your session has ended",
            f"The session token was not accepted ({exc}).",
            "Nothing you were looking at has changed. Signing in again restores it.",
            retryable=True,
            action="Sign in again",
            headers=challenge,
        ) from exc


async def project_manager(
    claims: auth_service.Claims = Depends(signed_in),
) -> auth_service.Claims:
    """The caller, who must be the project manager."""
    if claims.role != auth_service.ROLE_MANAGER:
        raise problem(
            403,
            "not-allowed",
            "Only the project manager can do this",
            f"This session's role is '{claims.role}'.",
            "Reading is unaffected.",
        )
    return claims


async def named_manager(
    claims: auth_service.Claims = Depends(project_manager),
) -> auth_service.Claims:
    """The project manager, signed in with a name: needed for every change (ADR-17)."""
    if not claims.named:
        raise problem(
            403,
            "name-needed",
            "Sign in with your name to change this",
            "Changes are recorded against the person who made them, and this session "
            "has no name.",
            "Everything can still be read.",
            action="Sign in again with your name",
        )
    return claims
