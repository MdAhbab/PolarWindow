"""Site, horizon, timeline, window and metric response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import Meta

Body = Literal["sun", "earth"]


class Provenance(BaseModel):
    """How a site's coordinate came to exist.

    Carried on every site because these coordinates are *derived* -- the IAU
    coordinate for a named crater is its centre, which is the permanently
    shadowed floor and the worst place to land. A site that did not say how it
    was chosen would be asking to be trusted for no reason.
    """

    model_config = ConfigDict(extra="forbid")

    anchor_lat_deg: float
    anchor_lon_deg: float
    search_kind: str
    search_inner_km: float
    search_outer_km: float
    offset_from_anchor_km: float
    source: str
    source_url: str
    source_note: str


class SiteSummary(BaseModel):
    """Coarse four-numbers over the reference window.

    `null` on a site whose precompute has not run -- never zeros. A zero is a
    measurement; absence is absence, and the UI has a state for it.
    """

    model_config = ConfigDict(extra="forbid")

    sunlit_s: float
    earth_contact_s: float
    longest_dark_s: float
    longest_blackout_s: float
    sun_fraction_up: float
    earth_fraction_up: float
    worst_compound_s: float
    grazing: bool
    reference_window_start: datetime
    reference_window_end: datetime
    reference_step_s: int


class SiteBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    code: str
    name: str
    region: str
    lat_deg: float
    lon_deg: float
    elev_m: float
    slope_deg: float
    note: str
    summary: SiteSummary | None = None


class SiteList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SiteBrief]
    total: int
    meta: Meta


class HorizonSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_el_deg: float
    max_el_bearing_deg: float
    mean_el_deg: float
    coverage: float
    dem_product: str
    computed_at: datetime


class SiteDetail(SiteBrief):
    model_config = ConfigDict(extra="forbid")

    provenance: Provenance
    horizon: HorizonSummary | None = None
    meta: Meta


class HorizonResponse(BaseModel):
    """Azimuth -> skyline elevation.

    Parallel arrays rather than objects: 1440 entries x 3 fields is ~60 KB as
    arrays and ~250 KB as a list of objects, and the frontend indexes them by
    bin anyway.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: str
    azimuth_step_deg: float
    azimuth_count: int
    el_deg: list[float]
    range_m: list[float]
    tol_deg: list[float]
    max_el_deg: float
    max_el_bearing_deg: float
    meta: Meta


class BodyTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    az_deg: list[float]
    el_deg: list[float]
    mask_el_deg: list[float]
    margin_deg: list[float]
    state: list[int] = Field(description="2 = lit/in contact, 1 = penumbral, 0 = dark/blocked.")


class TimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: datetime
    end: datetime
    step_s: int
    t_s: list[int] = Field(description="Seconds from `start`, one per sample.")
    sun: BodyTimeline
    earth: BodyTimeline
    meta: Meta


class Arc(BaseModel):
    """One unbroken stretch above or below the skyline."""

    model_config = ConfigDict(extra="forbid")

    up: bool
    start: datetime
    end: datetime
    duration_s: float
    tolerance_s: float = Field(
        description="Half-width of the timing uncertainty on this arc's edges."
    )
    grazing: bool = Field(
        description="True when a crossing is too shallow to time. The duration "
        "stands; its edges do not."
    )
    blocked_by_bearing_deg: float | None = Field(
        default=None,
        description="For a blocked arc, the bearing of the terrain doing the blocking. "
        "Naming the cause is the difference between an answer and an assertion.",
    )
    blocked_by_el_deg: float | None = None


class BodyWindows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Body
    arcs: list[Arc]
    up_s: float
    down_s: float
    fraction_up: float
    longest_down_s: float
    longest_down_tolerance_s: float
    longest_down_start: datetime | None = None
    longest_down_end: datetime | None = None
    grazing: bool


class CompoundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    duration_s: float


class WindowsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: datetime
    end: datetime
    sun: BodyWindows
    earth: BodyWindows
    compound: list[CompoundEvent]
    worst_compound_s: float
    meta: Meta


class Autonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worst_compound_s: float
    required_autonomy_s: float
    survival_needed_s: float = Field(
        description="If the worst blackout falls inside a night, the battery must carry "
        "the whole night, not just the silence."
    )
    compound_inside_dark: bool


class MetricsResponse(BaseModel):
    """The four numbers. There is deliberately no composite score.

    A score ranks sites on one axis, which destroys exactly the information this
    product exists to show: which corner a site gives up. The absence of a
    `score` field here is asserted by a test.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: datetime
    end: datetime
    sunlit_s: float
    earth_contact_s: float
    longest_dark_s: float
    longest_blackout_s: float
    sun_fraction_up: float
    earth_fraction_up: float
    worst_compound_s: float
    autonomy: Autonomy
    meta: Meta
