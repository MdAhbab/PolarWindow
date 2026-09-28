"""The mission hub's six steps (docs/lifecycle-api.md, `SectionStatus`)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SectionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Literal["ready", "launch", "trip", "landing", "contact", "return"]
    state: Literal["available", "computing", "needs_input", "not_applicable", "no_data"]
    summary: str = Field(description="One plain sentence; never a verdict.")
    as_of: datetime | None
