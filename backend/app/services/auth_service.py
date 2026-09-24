"""Session tokens: issued without a password on a demo host, checked on every call that needs one.

There is one role, the project manager. They read everything and hold the
settings: the AI assistant, the run log and the cache. Map data stays public,
because it is public data; what a token guards is what costs money (the model
calls) and what changes the service for everyone (the settings).

The token is a JWT signed with HS256. ``PW_JWT_SECRET`` signs it; when that is
empty a random secret is made once per process, so a restart invalidates every
token and the client simply signs in again.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.config import get_settings

ROLE_MANAGER = "project_manager"
ISSUER = "polar-window"

#: What a role is called on screen.
ROLE_NAMES = {ROLE_MANAGER: "Project manager"}


class InvalidToken(Exception):
    """Missing, malformed, expired or signed with another secret."""


class SignInDisabled(Exception):
    """One-click sign-in is turned off on this server."""


@dataclass(frozen=True, slots=True)
class Claims:
    subject: str
    role: str
    issued_at: int
    expires_at: int

    @property
    def role_name(self) -> str:
        return ROLE_NAMES.get(self.role, self.role)


@lru_cache(maxsize=1)
def _process_secret() -> str:
    return secrets.token_urlsafe(32)


def _secret() -> str:
    return get_settings().jwt_secret or _process_secret()


def issue_demo() -> tuple[str, Claims]:
    """A project manager's token, for the landing page's one button."""
    s = get_settings()
    if not s.demo_sign_in:
        raise SignInDisabled("One-click sign-in is turned off on this server.")
    now = int(time.time())
    claims = Claims(
        subject=f"demo-{secrets.token_hex(4)}",
        role=ROLE_MANAGER,
        issued_at=now,
        expires_at=now + s.jwt_ttl_s,
    )
    token = jwt.encode(
        {
            "sub": claims.subject,
            "role": claims.role,
            "iss": ISSUER,
            "iat": claims.issued_at,
            "exp": claims.expires_at,
        },
        _secret(),
        algorithm="HS256",
    )
    return token, claims


def verify(token: str) -> Claims:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            issuer=ISSUER,
            options={"require": ["sub", "role", "iat", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    return Claims(
        subject=str(payload["sub"]),
        role=str(payload["role"]),
        issued_at=int(payload["iat"]),
        expires_at=int(payload["exp"]),
    )
