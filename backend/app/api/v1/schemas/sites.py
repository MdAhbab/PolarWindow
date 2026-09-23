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
    longest_dark_open: bool = Field(
        description="The longest night touches an edge of the reference window, so the "
        "window ended it and `longest_dark_s` is a lower bound."
    )
    longest_blackout_open: bool = Field(
        description="As `longest_dark_open`, for the longest loss of Earth contact."
    )
    reference_window_start: datetime
    reference_window_end: datetime
    reference_step_s: int
    computed_at: datetime = Field(description="When this summary was computed.")


class SiteBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    code: str
    name: str
    region: str
    lat_deg: float
    lon_deg: float
    elev_m: float | None = Field(
        description="Height above the 1737.4 km reference sphere, metres. Null where no "
        "elevation model covers the site: an unknown height is not zero."
    )
    slope_deg: float | None
    note: str
    search_kind: Literal["rim", "massif", "published"] = Field(
        description="How the landing point was found: on the rim of a named crater "
        "(so it borders that crater's shadowed floor) or on a massif or plateau."
    )
    kind: Literal["candidate", "mission_target"] = Field(
        default="candidate",
        description="A derived candidate site, or a CLPS mission target (ADR-6).",
    )
    coordinate_rule: Literal["derived_open_sky", "published"] = Field(
        default="derived_open_sky",
        description="Searched in the DEM for open sky, or used exactly as published.",
    )
    terrain_modelled: bool = Field(
        default=True,
        description="False outside the 80-90 deg S elevation model: smooth-sphere skyline.",
    )
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
        description="Timing uncertainty of this arc's duration: the quadrature sum of its "
        "two edges' tolerances."
    )
    start_tolerance_s: float | None = Field(
        description="Timing uncertainty of the crossing that starts this arc; null when the "
        "arc starts at the window edge rather than at a crossing."
    )
    end_tolerance_s: float | None = Field(
        description="As `start_tolerance_s`, for the crossing that ends it."
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
    open_start: bool = Field(
        description="The arc begins at the window start: it was already in progress, so "
        "its true start -- and duration -- lie beyond the window."
    )
    open_end: bool = Field(description="The arc is still in progress at the window end.")


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
    longest_down_open: bool = Field(
        description="The longest down arc touches a window edge; `longest_down_s` is a "
        "lower bound on the stretch it belongs to."
    )
    grazing: bool


class CompoundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    duration_s: float
    open_start: bool
    open_end: bool


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
    required_autonomy_s: float = Field(
        description="The worst compound event (no Sun and no link) plus `margin_fraction`."
    )
    margin_fraction: float = Field(
        description="The margin applied on top of the worst compound event, as a fraction."
    )
    survival_needed_s: float = Field(
        description="The battery must carry the longest night whatever the radio is doing; "
        "a blackout inside a night never shortens it."
    )
    compound_inside_dark: bool
    survival_open: bool = Field(
        description="The night that sets `survival_needed_s` is cut by a window edge: a "
        "lower bound."
    )
    worst_compound_open: bool


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
    longest_dark_open: bool = Field(
        description="The longest night touches a window edge, so `longest_dark_s` is a "
        "lower bound: the window ended it, not the terrain."
    )
    longest_blackout_open: bool = Field(
        description="As `longest_dark_open`, for `longest_blackout_s`."
    )
    worst_compound_open: bool
    sunlit_full_disc_s: float = Field(
        description="Time the whole solar disc was above the skyline (lower bound on sunlit_s; "
        "sampled at the timeline step). sunlit_s times the disc centre."
    )
    sunlit_any_limb_s: float = Field(
        description="Time any part of the solar disc was above the skyline (upper bound)."
    )
    earth_contact_full_disc_s: float
    earth_contact_any_limb_s: float
    sunlit_tolerance_s: float = Field(
        description="Timing uncertainty of the sunlit total: every skyline crossing's edge "
        "tolerance, added in quadrature. Seconds."
    )
    earth_contact_tolerance_s: float = Field(
        description="Timing uncertainty of the Earth-contact total, as for sunlit. Seconds."
    )
    longest_dark_tolerance_s: float | None = Field(
        description="Tolerance of the longest night's two edges in quadrature; null when "
        "an edge is a graze and cannot be timed. Seconds."
    )
    longest_blackout_tolerance_s: float | None = Field(
        description="Tolerance of the longest blackout's two edges; null when grazing. Seconds."
    )
    longest_dark_grazing: bool
    longest_blackout_grazing: bool
    autonomy: Autonomy
    meta: Meta


class CalendarBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    sun_fraction_up: float
    earth_fraction_up: float
    sunlit_s: float
    earth_contact_s: float
    longest_dark_s: float
    longest_dark_open: bool = Field(
        description="The longest night in this bucket was cut by the bucket's edge: a lower bound."
    )
    longest_blackout_s: float
    longest_blackout_open: bool


class CalendarResponse(BaseModel):
    """Sun and Earth by day or by month, for choosing dates (contract v2)."""

    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: datetime
    end: datetime
    bucket: Literal["day", "month"]
    step_s: int
    items: list[CalendarBucket]
    meta: Meta
