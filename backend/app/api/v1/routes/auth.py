"""Sign-in: one button on the landing page, no user name or password."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.auth import SessionOut, Who
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["sign-in"])


def _who(c: auth_service.Claims) -> dict[str, Any]:
    return {
        "subject": c.subject,
        "role": c.role,
        "role_name": c.role_name,
        "expires_at": datetime.fromtimestamp(c.expires_at, UTC),
    }


@router.post("/demo", response_model=SessionOut, summary="Sign in as the project manager")
async def demo_sign_in() -> dict[str, Any]:
    """A project manager's session, with no user name or password.

    For a judged demo: the landing page's "Open the dashboard" button calls
    this. Turned off with `PW_DEMO_SIGN_IN=false`, when it answers 403.
    """
    try:
        token, claims = auth_service.issue_demo()
    except auth_service.SignInDisabled as exc:
        raise deps.problem(
            403,
            "sign-in-disabled",
            "One-click sign-in is turned off",
            str(exc),
            "The missions, the map and every number can still be read.",
        ) from exc
    return {"token": token, "token_type": "bearer", **_who(claims)}


@router.get("/me", response_model=Who, summary="Who this session belongs to")
async def me(claims: auth_service.Claims = Depends(deps.signed_in)) -> dict[str, Any]:
    return _who(claims)
