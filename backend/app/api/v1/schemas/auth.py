"""Sign-in responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Who(BaseModel):
    """Who a session belongs to."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    role: Literal["project_manager"]
    role_name: str = Field(description="The role as the screen names it.")
    expires_at: datetime


class SessionOut(Who):
    token: str = Field(description="A JWT (HS256). Send it as `Authorization: Bearer <token>`.")
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 -- the scheme name, not a secret
