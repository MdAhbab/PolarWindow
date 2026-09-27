"""Launch (T2 D1/D2) on the wire: docs/lifecycle-api.md, section *Launch*."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import QuantityOut


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pad(_M):
    id: str
    name: str
    lat_deg: float | None
    lon_deg: float | None
    operator: str


class TransferOut(_M):
    type: Literal["direct", "phasing_loops"]
    flight_days: QuantityOut
    orbit_wait_days: QuantityOut


class LandingOut(_M):
    time: QuantityOut
    sun_elevation_deg: QuantityOut
    sunlight_after_h: QuantityOut
    earth_up: bool


class Opportunity(_M):
    id: str
    pad_id: str
    pad_name: str
    vehicle_id: str
    t0: QuantityOut = Field(description='Liftoff, unit "s since epoch".')
    kind: Literal["instantaneous", "window"]
    window_open: datetime | None
    window_close: datetime | None
    transfer: TransferOut
    landing: LandingOut
    weather: Literal["forecast", "climatology", "none"] = Field(
        description="What numbers the weather tab can show. With none it still shows the "
        "rules and limits; weather_note says why there are no numbers."
    )
    weather_note: str
    basis: Literal["reconstructed", "designed", "published"] = Field(
        description="How t0 was worked out: again from a flown trajectory, designed, or as "
        "published."
    )
    note: str
    azimuth_deg: QuantityOut
    dv_tli_m_s: QuantityOut
    coast_min: QuantityOut


class LandingRule(_M):
    sun_elevation_min_deg: QuantityOut
    sun_elevation_max_deg: QuantityOut
    earth_required: bool
    note: str


class LaunchCalendar(_M):
    none_reason: str | None
    start: datetime | None
    end: datetime | None
    dates_note: str | None
    vehicle_id: str | None
    pads: list[Pad]
    opportunities: list[Opportunity]
    landing_rule: LandingRule
    published_t0: QuantityOut | None
