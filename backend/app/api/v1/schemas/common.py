"""Shared response pieces: the `meta` envelope and the error contract.

Every 200 response in this API carries `meta`, and `meta.uncertainty` is never
absent and never null. That is a product rule, not a convention: the frontend's
design carries an uncertainty state in every data-bound component, and an
endpoint that omits the margin forces the UI to either invent one or hide it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Resolution(BaseModel):
    """What this answer was computed at."""

    model_config = ConfigDict(extra="forbid")

    azimuth_deg: float = Field(description="Angular step of the horizon mask, degrees.")
    azimuth_count: int
    time_step_s: int = Field(description="Sampling step of the timeline, seconds.")
    max_range_m: float = Field(description="How far terrain was modelled around the site.")
    dem_product: str
    dem_resolution_m: float
    ephemeris: str
    frame: str


class Uncertainty(BaseModel):
    """How wrong this could be, in the units the caller is reading."""

    model_config = ConfigDict(extra="forbid")

    dem_vertical_error_m: float
    dem_resolution_m: float
    coverage: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of sampled terrain that fell inside the elevation model. "
        "Below 1.0 the mask is partial and the numbers are likely optimistic.",
    )
    horizon_el_deg: float = Field(
        description="Angular uncertainty of the skyline, from the DEM's vertical error "
        "at the range where the skyline is actually set."
    )
    edge_timing_s: float | None = Field(
        description="Worst arc-edge timing uncertainty in this response, seconds. "
        "null when at least one crossing is a graze -- see `grazing`. A null here is "
        "a stronger statement than a large number: the edge is not knowable from this data."
    )
    grazing: bool
    penumbra_sun_deg: float = Field(
        description="Apparent angular radius of the Sun from the Moon. The lit/dark "
        "boundary is soft by this much."
    )
    penumbra_earth_deg: float
    notes: list[str]


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    computed_at: datetime
    resolution: Resolution
    uncertainty: Uncertainty
    engine_version: str
    cache: Literal["hit", "miss", "bypass"] = "miss"
    compute_ms: float | None = None


class ErrorUI(BaseModel):
    """What the frontend's ErrorPanel renders, with no translation layer.

    The panel already takes a title, a detail and a "what still works" line;
    supplying all three from the server means an error message can be improved
    without a frontend deploy, and means no error ever renders as a shrug.
    """

    model_config = ConfigDict(extra="forbid")

    still_works: str
    retryable: bool = False
    action: str | None = None


class Problem(BaseModel):
    """RFC 9457 problem details, plus the UI block."""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    ui: ErrorUI
