"""Launch weather (T4 B1/B3) and Return (T4 B2) on the wire: docs/lifecycle-api.md."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.v1.schemas.common import QuantityOut, ShareOut


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SystemShare(_M):
    system: Literal["GEFS", "ECMWF-ENS", "AIFS-ENS"]
    share: ShareOut | None
    missing_reason: str | None


class OneForecast(_M):
    system: Literal["NWS", "HRRR", "GEOS-FP"]
    value: QuantityOut
    over: bool
    note: str | None = Field(
        description="How this forecast did against a weather station's record (HRRR), or why "
        "it could not be checked (NWS keeps no archive)."
    )


class Observed(_M):
    state: Literal["clear", "seen", "no_data"]
    detail: str


class Climatology(_M):
    share: float
    years: str
    source: str


class RuleRow(_M):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    text: str = Field(description="The rule as published, word for word.")
    source_url: str
    class_: Literal["model", "proxy", "observation"] = Field(alias="class")
    limit: QuantityOut
    units: list[str] = Field(
        description="Units a limit for this rule can be entered in, the published one first; "
        "empty when no unit is published (any unit is taken)."
    )
    limit_note: str | None = Field(description="The team's note with an entered limit.")
    per_system: list[SystemShare]
    one_forecast: list[OneForecast]
    disagreement: bool
    disagreement_note: str | None = Field(
        description="Who disagrees and how, in plain words; null when `disagreement` is false."
    )
    observed: Observed | None
    climatology: Climatology | None


class OfficialForecast(_M):
    id: int
    probability_pct: float
    concerns: list[str]
    pdf_url: str
    entered_by: str
    entered_at: datetime


class RangeConflict(_M):
    name: str
    t0: datetime
    pad: str


class LaunchWeather(_M):
    t0: datetime
    lead_time_h: float
    pad_id: str
    vehicle_id: str | None
    note: str
    rules: list[RuleRow]
    official: OfficialForecast | None
    range_conflicts: list[RangeConflict]
    range_note: str


class OfficialForecastIn(_M):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    probability_pct: float = Field(ge=0, le=100)
    concerns: list[Annotated[str, StringConstraints(max_length=500)]] = Field(
        default_factory=list, max_length=20
    )
    pdf_url: str = Field(pattern=r"^https://\S+$", max_length=2000)


class OfficialForecastOut(_M):
    id: int
    probability_pct: float
    concerns: list[str]
    pdf_url: str
    entered_by: str
    entered_at: datetime


class OfficialForecastRemoved(_M):
    removed_id: int = Field(description="The forecast taken back.")
    official: OfficialForecastOut | None = Field(
        description="The forecast shown now (the one entered before), or null."
    )


class LimitIn(_M):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    rule_id: str = Field(max_length=64)
    value: float = Field(gt=0, le=1e6)
    unit: str = Field(min_length=1, max_length=24)
    note: str | None = Field(default=None, max_length=2000)


class LimitsIn(_M):
    limits: list[LimitIn] = Field(max_length=50)


class LimitOut(_M):
    rule_id: str
    value: float
    unit: str
    note: str | None
    entered_by: str
    entered_at: datetime


class VehicleLimits(_M):
    vehicle_id: str
    limits: list[LimitOut]


# --- Return --------------------------------------------------------------------


class Zone(_M):
    lat_deg: float
    lon_deg: float
    pm_km: float | None = Field(description="Null when the zone's size is not published.")


class SeaLimits(_M):
    wave_height_m: QuantityOut
    wind_m_s: QuantityOut


class Booster(_M):
    landing: Literal["droneship", "land", "expended", "unknown"]
    zone: Zone | None
    note: str
    wave_height_m: QuantityOut | None
    wind_m_s: QuantityOut | None
    limits: SeaLimits
    hazard_area_seen: bool | None


class CapsuleModelCheck(_M):
    """The capsule entry model (3-DOF, through an empirical model of the entry day's air)
    flown from OSIRIS-REx's reconstructed entry state, against where its capsule landed."""

    case: str
    distance_km: float
    distance_range_km: list[float]
    limit_km: float
    passed: bool
    #: The air the modelled fall went through, what it was given and why that model, in plain
    #: words.
    atmosphere: str
    mission_team_km: float
    ellipse_99_km: list[float]
    measured_inside_ellipse: bool
    checked_at: str
    sources: list[str]
    note: str


class Capsule(_M):
    applicable: bool
    reason: str | None
    zone: Zone | None
    wave_height_m: QuantityOut | None
    wind_m_s: QuantityOut | None
    daylight: bool | None
    limits: SeaLimits
    model_check: CapsuleModelCheck | None


class Return(_M):
    booster: Booster | None
    capsule: Capsule | None


class SeaLimitsIn(_M):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    #: Upper bounds are sanity only: above any sea state or surface wind on record.
    wave_height_m: float | None = Field(default=None, le=30)
    wind_m_s: float | None = Field(default=None, le=100)


class ReturnLimitsIn(_M):
    booster: SeaLimitsIn = Field(default_factory=SeaLimitsIn)
    capsule: SeaLimitsIn = Field(default_factory=SeaLimitsIn)
