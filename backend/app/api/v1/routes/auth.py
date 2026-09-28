"""Sign-in: one button on the landing page and a name; no password (ADR-7, ADR-17)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends

from app.api.v1 import deps
from app.api.v1.schemas.auth import SessionOut, SignInIn, Who
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["sign-in"])


def _who(c: auth_service.Claims) -> dict[str, Any]:
    return {
        "subject": c.subject,
        "role": c.role,
        "role_name": c.role_name,
        "expires_at": datetime.fromtimestamp(c.expires_at, UTC),
        "user": (
            {"id": c.user_id, "name": c.name or "", "team": c.team}
            if c.user_id is not None
            else None
        ),
    }


@router.post("/demo", response_model=SessionOut, summary="Sign in as the project manager")
async def demo_sign_in(
    body: SignInIn | None = Body(default=None),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    """A named project manager's session, with no password.

    For a judged demo: the landing page's "Open the dashboard" button calls
    this, with the name the person typed or with no body, when the session is
    recorded as "Demo project manager". Every change made with the session is
    recorded against that name. Turned off with `PW_DEMO_SIGN_IN=false`, when
    it answers 403.
    """
    try:
        token, claims = await auth_service.sign_in(
            session, body.name if body else None, body.team if body else None
        )
    except auth_service.SignInDisabled as exc:
        raise deps.problem(
            403,
            "sign-in-disabled",
            "One-click sign-in is turned off",
            str(exc),
            "The missions, the map and every number can still be read.",
        ) from exc
    except auth_service.BadName as exc:
        raise deps.problem(
            422,
            "bad-name",
            "That name cannot be used",
            str(exc),
            "Everything can still be read without signing in.",
            action="Type a shorter name",
        ) from exc
    return {"token": token, "token_type": "bearer", **_who(claims)}


@router.get("/me", response_model=Who, summary="Who this session belongs to")
async def me(claims: auth_service.Claims = Depends(deps.signed_in)) -> dict[str, Any]:
    return _who(claims)
