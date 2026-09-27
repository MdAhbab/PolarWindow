"""Session tokens: issued without a password on a demo host, checked on every call that needs one.

There is one role, the project manager. They read everything and hold the
settings: the AI assistant, the run log and the cache. Map data stays public,
because it is public data; what a token guards is what costs money (the model
calls) and what changes the service for everyone (the settings and the
records).

Sign-in asks for a name (ADR-17, amending ADR-7). The token then carries the
``users`` row id, so every change a person makes is recorded against them. A
token without a user id (issued before ADR-17, or by a test) can still read
and ask the assistant, but cannot change anything.

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories.users import UserRecord, UserRepository

ROLE_MANAGER = "project_manager"
ISSUER = "polar-window"

#: What a role is called on screen.
ROLE_NAMES = {ROLE_MANAGER: "Project manager"}

#: The name a one-click sign-in without a name is recorded under.
DEFAULT_DEMO_NAME = "Demo project manager"


class InvalidToken(Exception):
    """Missing, malformed, expired or signed with another secret."""


class SignInDisabled(Exception):
    """One-click sign-in is turned off on this server."""


class BadName(ValueError):
    """The name given at sign-in cannot be used."""


@dataclass(frozen=True, slots=True)
class Claims:
    subject: str
    role: str
    issued_at: int
    expires_at: int
    #: The ``users`` row this session belongs to; None for an unnamed session.
    user_id: int | None = None
    name: str | None = None
    team: str | None = None

    @property
    def role_name(self) -> str:
        return ROLE_NAMES.get(self.role, self.role)

    @property
    def named(self) -> bool:
        return self.user_id is not None

    @property
    def actor(self) -> str:
        """How the change history names this person."""
        if self.name is None:
            return self.subject
        return f"{self.name} ({self.team})" if self.team else self.name


@lru_cache(maxsize=1)
def _process_secret() -> str:
    return secrets.token_urlsafe(32)


def _secret() -> str:
    return get_settings().jwt_secret or _process_secret()


def issue_demo(user: UserRecord | None = None) -> tuple[str, Claims]:
    """A project manager's token, for the landing page's one button.

    With ``user`` the session is named and may change records; without it,
    the session can read and ask the assistant only.
    """
    s = get_settings()
    if not s.demo_sign_in:
        raise SignInDisabled("One-click sign-in is turned off on this server.")
    now = int(time.time())
    claims = Claims(
        subject=f"user-{user.id}" if user else f"demo-{secrets.token_hex(4)}",
        role=ROLE_MANAGER,
        issued_at=now,
        expires_at=now + s.jwt_ttl_s,
        user_id=user.id if user else None,
        name=user.name if user else None,
        team=user.team if user else None,
    )
    payload: dict[str, object] = {
        "sub": claims.subject,
        "role": claims.role,
        "iss": ISSUER,
        "iat": claims.issued_at,
        "exp": claims.expires_at,
    }
    if user is not None:
        payload |= {"uid": user.id, "name": user.name, "team": user.team}
    token = jwt.encode(payload, _secret(), algorithm="HS256")
    return token, claims


def clean_name(name: str | None, team: str | None) -> tuple[str, str | None]:
    """The name and team as stored; a missing name is the demo name."""
    n = " ".join((name or "").split())
    t = " ".join((team or "").split()) or None
    if not n:
        n = DEFAULT_DEMO_NAME
    if len(n) > 120 or (t is not None and len(t) > 120):
        raise BadName("A name or team is at most 120 characters.")
    if any(ord(c) < 32 for c in n + (t or "")):
        raise BadName("A name cannot contain control characters.")
    return n, t


async def sign_in(session: AsyncSession, name: str | None, team: str | None) -> tuple[str, Claims]:
    """A named session: the person is found or created, and the token carries them."""
    if not get_settings().demo_sign_in:
        raise SignInDisabled("One-click sign-in is turned off on this server.")
    n, t = clean_name(name, team)
    user = await UserRepository(session).sign_in(n, t)
    return issue_demo(user)


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
    uid = payload.get("uid")
    return Claims(
        subject=str(payload["sub"]),
        role=str(payload["role"]),
        issued_at=int(payload["iat"]),
        expires_at=int(payload["exp"]),
        user_id=int(uid) if isinstance(uid, int) else None,
        name=str(payload["name"]) if uid is not None and payload.get("name") else None,
        team=str(payload["team"]) if uid is not None and payload.get("team") else None,
    )
