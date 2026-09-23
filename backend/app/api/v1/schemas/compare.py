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
    rank: int | None = Field(
        description="Definite competition rank, shared by measured sites whose intervals "
        "overlap (1, 1, 3). Null when a window-censored value or an untimeable edge is "
        "involved, so the place cannot be stated: read `rank_range` instead."
    )
    rank_range: list[int] = Field(
        min_length=2,
        max_length=2,
        description="[best possible, worst possible] place given every site's interval.",
    )
    tied: bool = Field(description="Overlaps at least one other measured site.")
    tied_with: list[str] = Field(description="Measured sites this one cannot be separated from.")
    incomparable_with: list[str] = Field(
        description="Sites this one cannot be ordered against because a lower bound or an "
        "untimeable edge is involved."
    )
    censored: bool = Field(
        description="The ranked value is a lower bound: the window, not the terrain, ended it."
    )
    grazing: bool = Field(description="An edge of the ranked value cannot be timed.")
    uncertainty_s: float | None = Field(
        description="This site's own timing tolerance on the ranked metric; null when grazing."
    )
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
        description="Connected groups of measured sites whose intervals overlap. "
        "Reported rather than ordered: ranking sites the data cannot distinguish "
        "asserts a difference that is not there."
    )
    unavailable: list[Unavailable] = Field(
        description="Sites that could not be computed. One unsurveyed site does not "
        "blank the comparison."
    )
    meta: Meta
