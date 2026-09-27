"""Trip (T2) on the wire: docs/lifecycle-api.md, section *Trip*."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import QuantityOut
from app.api.v1.schemas.contact import StretchOut


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TripSample(_M):
    t: datetime
    earth_km: float
    moon_km: float
    light: Literal["lit", "penumbral", "dark"]
    heard: bool = Field(description="A DSN antenna could see the spacecraft (line of sight).")


class TripNumbers(_M):
    sunlight_h: QuantityOut
    heard_h: QuantityOut = Field(description="Time a ground station could see the spacecraft.")
    longest_shadow_h: QuantityOut
    longest_unheard_h: QuantityOut


class Burn(_M):
    t: datetime
    name: str
    dv_m_s: QuantityOut


class CorrectionBurn(_M):
    name: str
    t: datetime
    p95_m_s: QuantityOut
    p99_m_s: QuantityOut


class Assumption(_M):
    what: str
    value: str


class Corrections(_M):
    label: str = Field(description="Always says these sizes are a budget for assumed errors.")
    burns: list[CorrectionBurn]
    total_p95_m_s: QuantityOut
    total_p99_m_s: QuantityOut = Field(description="lo/hi: its 95 % interval (bootstrap).")
    linear_p99_m_s: QuantityOut = Field(description="The same total worked out linearly.")
    arrival_altitude_km: QuantityOut = Field(description="Median; lo/hi the 1st and 99th %.")
    runs: int
    missed: int = Field(description="Runs with no close pass of the Moon (counted, not hidden).")
    assumptions: list[Assumption]
    plan_note: str
    flown_note: str


class MoonPull(_M):
    equal_pull_km: float = Field(description="From the Moon's centre, where the pulls are equal.")
    sphere_of_influence_km: float
    t_equal_pull: datetime | None = Field(description="When the Moon's pull overtook Earth's.")


class Radiation(_M):
    belt_hours: QuantityOut
    fluence_gt10mev: QuantityOut
    gcr_dose_mgy_day: QuantityOut
    screening_note: str
    confirm_in: list[str]


class Trip(_M):
    source: Literal["flown", "designed", "none"]
    none_reason: str | None
    start: datetime | None
    end: datetime | None
    coverage_note: str | None
    covered: list[StretchOut] = Field(
        description="The stretches NASA's reconstruction covers; anything between is a gap."
    )
    samples: list[TripSample] = Field(max_length=2000)
    shadow: list[StretchOut]
    heard: list[StretchOut]
    numbers: TripNumbers
    burns: list[Burn]
    burns_note: str | None
    corrections: Corrections | None
    corrections_note: str | None = Field(description="Why there is no correction budget.")
    moon_pull: MoonPull | None
    radiation: Radiation | None
