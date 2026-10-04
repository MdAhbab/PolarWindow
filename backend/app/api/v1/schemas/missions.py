"""CLPS mission responses (contract v2, docs/system-design.md 10.5).

Every mission fact is as published, with its sources. A field no source
confirms is null and named in ``unconfirmed_fields``; it is never filled in.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import Meta

MissionStatus = Literal[
    "planned",
    "in_transit",
    "operating",
    "completed",
    "partial_success",
    "landing_failed",
    "lost_before_landing",
    "cancelled",
    "reassigned",
]
InstrumentType = Literal[
    "volatiles",
    "geology_geophysics",
    "heat_flow",
    "radiation_space_weather",
    "exosphere_dust",
    "imaging",
    "landing_navigation",
    "communications",
    "laser_retroreflector",
    "rover_mobility",
    "technology_demo",
    "other",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublishedDate(_Model):
    date: str = Field(description="ISO date or datetime. A year-precision date is 1 January.")
    precision: Literal["second", "minute", "day", "month", "quarter", "year"]
    as_published: str = Field(description="The phrase as published, e.g. 'late 2027'. Show this.")


class MissionTarget(_Model):
    name: str
    lat_deg: float
    lon_deg: float = Field(description="Degrees east, 0-360.")
    coordinate_kind: Literal["actual_landing", "planned_target", "feature_centre"] = Field(
        description="`feature_centre` is the IAU centre of the named target, used because no "
        "landing point is published. It is not a landing point."
    )
    source_url: str
    feature_id: int | None = None


class SurfaceWindow(_Model):
    start: datetime | None
    end: datetime | None
    basis: Literal["published", "planned", "assumed", "none"]
    note: str


class MissionSummary(_Model):
    """The four numbers at the target over the surface window."""

    window_start: datetime
    window_end: datetime
    sunlit_s: float
    earth_contact_s: float
    longest_dark_s: float
    longest_blackout_s: float
    sun_fraction_up: float
    earth_fraction_up: float
    longest_dark_open: bool
    longest_blackout_open: bool
    grazing: bool
    terrain_modelled: bool


class MissionBrief(_Model):
    id: str
    name: str
    vehicle_name: str | None
    task_order: str | None
    provider: str | None
    lander: str | None
    status: MissionStatus
    region: Literal["south_polar", "nearside", "farside", "polar_other"] | None
    target_name: str | None
    target: MissionTarget | None
    launch: PublishedDate | None
    landing: PublishedDate | None
    payload_types: list[InstrumentType]
    payload_count: int
    site_id: str | None = Field(
        description="The site standing for the target; open it for the full site views."
    )
    terrain_modelled: bool | None = Field(
        description="False outside the 80-90 deg S elevation model; null with no target."
    )
    surface_window: SurfaceWindow
    summary: MissionSummary | None = Field(
        description="Null when there is no surface window or no target. Never zeros."
    )
    unconfirmed_fields: list[str]
    data_version: str


class MissionList(_Model):
    items: list[MissionBrief]
    total: int
    meta: Meta


class Payload(_Model):
    id: str
    name: str
    acronym: str | None
    organisation: str | None
    instrument_types: list[InstrumentType] = Field(
        description="This project's classification from the sourced description, not NASA's."
    )
    purpose: str
    source_url: str
    unconfirmed: bool


class Source(_Model):
    url: str
    title: str
    publisher: str
    accessed: date


class TargetSite(_Model):
    id: str
    code: str
    name: str
    lat_deg: float
    lon_deg: float
    elev_m: float | None
    kind: Literal["candidate", "mission_target"]
    coordinate_rule: Literal["derived_open_sky", "published"]
    terrain_modelled: bool
    source_note: str


class Transfer(_Model):
    type: Literal["direct", "phasing_loops", "low_energy", "unknown"]
    flight_days: float | None
    lunar_orbit_days: float | None


class Descent(_Model):
    sun_el_min_deg: float | None
    sun_el_max_deg: float | None
    earth_required: bool | None


class Comms(_Model):
    bands: list[str]
    eirp_dbw: float | None
    gt_dbk: float | None
    ground_stations: list[str]
    relays: list[str]


class Spacecraft(_Model):
    mass_kg: float | None
    area_m2: float | None
    cr: float | None


class Rover(_Model):
    id: str
    name: str
    organisation: str | None
    source_url: str


class MissionLifecycle(_Model):
    """Schema v2 facts (ADR-10); each non-null field has its URL in ``field_sources``."""

    vehicle_id: str | None
    vehicle_name: str | None = Field(description="The launch vehicle's name, from the catalogue.")
    pad_id: str | None
    pad_name: str | None
    t0: PublishedDate | None = Field(description="The published launch instant.")
    transfer: Transfer | None
    descent: Descent | None
    comms: Comms | None
    spacecraft: Spacecraft | None
    rovers: list[Rover]
    returns: Literal["none", "sample_capsule", "crew"] | None
    field_sources: dict[str, str]


class MissionDetail(MissionBrief):
    outcome_note: str
    end_of_mission: PublishedDate | None
    planned_surface_days: float | None
    payloads: list[Payload]
    sources: list[Source] = Field(min_length=1)
    notes: list[str]
    ellipse_ring: list[list[float]] | None = Field(
        description="Published landing ellipse as [lat, lon] vertices; null when none is published."
    )
    site: TargetSite | None
    lifecycle: MissionLifecycle | None = Field(
        default=None, description="Launch, trip, radio and return facts (schema v2)."
    )
    meta: Meta
