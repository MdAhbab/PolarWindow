"""Compare request and response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import Meta
from app.api.v1.schemas.sites import MetricsResponse


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_ids: list[str] = Field(min_length=1, max_length=8)
    start: datetime | None = None
    end: datetime | None = None
    step_s: int | None = Field(default=None, ge=60, le=86400)
    rank_by: str = Field(
        default="longest_dark_s",
        description="One of sunlit_s, earth_contact_s, longest_dark_s, longest_blackout_s. "
        "There is no composite option by design.",
    )


class CompareWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    step_s: int


class CompareItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    position: int = Field(description="1-based place in `items`; strictly increasing.")
    rank: int = Field(
        description="Competition rank: sites the data cannot distinguish share their "
        "group leader's rank (1, 1, 3), so a tie is never printed as an order."
    )
    tied: bool = Field(description="This site is in one of the `ties` groups.")
    metrics: MetricsResponse
    delta_vs_best: dict[str, float]


class Unavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    reason: str


class CompareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: CompareWindow
    rank_by: str
    items: list[CompareItem]
    ties: list[list[str]] = Field(
        description="Groups whose metric differs by less than the tie tolerance. "
        "Reported rather than ordered: ranking sites the data cannot distinguish "
        "asserts a difference that is not there."
    )
    unavailable: list[Unavailable] = Field(
        description="Sites that could not be computed. One unsurveyed site does not "
        "blank the comparison."
    )
    meta: Meta
