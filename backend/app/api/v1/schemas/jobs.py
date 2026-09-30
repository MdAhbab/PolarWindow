"""Jobs (ADR-12) and data sources (ADR-8) on the wire."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobRefOut(BaseModel):
    """A heavy answer being worked out. Poll ``GET /jobs/{job_id}`` after ``poll_after_s``."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    status: Literal["queued", "running", "done", "failed"]
    progress: float | None = Field(description="0 to 1, when the job reports it.")
    message: str = Field(description="One plain sentence about where the job is.")
    poll_after_s: float
    assessment_id: int | None = Field(
        default=None, description="The stored answer, once the job is done."
    )


class FeedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    provider_name: str
    product: str
    location: str | None = Field(description="Pad or buoy the product is for, if any.")
    last_ok: datetime | None = Field(description="When the product was last fetched or checked.")
    data_time: datetime | None = Field(
        description="The time the data itself refers to (model run, issue time, newest reading)."
    )
    age_s: float | None = Field(description="How old the data is, seconds; null if none yet.")
    stale: bool = Field(
        description="Past its staleness budget (or no data yet); for a product fetched only "
        "while a launch is near (`note`), past the budget since it was last asked."
    )
    staleness_budget_s: int
    next_run: datetime | None
    errors: int = Field(description="Failed attempts in a row.")
    last_error: str | None
    licence: str
    note: str | None = Field(
        description="Why the product may hold nothing or no age (fetched only while a launch "
        "is near); null for the rest."
    )
    breaker: Literal["closed", "open", "half_open"] = Field(
        description="`open`: the provider failed repeatedly and is being left alone for a while."
    )


class FeedsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feeds: list[FeedOut]


class RefreshOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    products: int
    message: str
