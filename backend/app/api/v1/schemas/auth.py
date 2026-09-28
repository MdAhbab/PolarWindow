"""Sign-in requests and responses (ADR-7, amended by ADR-17)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SignInIn(BaseModel):
    """Who is signing in. With no body, the name is "Demo project manager"."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, description="Recorded on every change.")
    team: str | None = Field(default=None, max_length=120)


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    team: str | None


class Who(BaseModel):
    """Who a session belongs to."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    role: Literal["project_manager"]
    role_name: str = Field(description="The role as the screen names it.")
    expires_at: datetime
    user: UserOut | None = Field(
        default=None,
        description="The named person. Null for a session that can read but not change "
        "records (a token issued before names were asked for).",
    )


class SessionOut(Who):
    token: str = Field(description="A JWT (HS256). Send it as `Authorization: Bearer <token>`.")
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 -- the scheme name, not a secret
