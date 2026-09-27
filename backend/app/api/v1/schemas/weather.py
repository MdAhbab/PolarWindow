"""Launch weather (T4 B1/B3) and Return (T4 B2) on the wire: docs/lifecycle-api.md."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    per_system: list[SystemShare]
    one_forecast: list[OneForecast]
    disagreement: bool
    observed: Observed | None
    climatology: Climatology | None


class OfficialForecast(_M):
    probability_pct: float
    concerns: list[str]
    pdf_url: str
    entered_by: str
    entered_at: datetime


class SpaceWeatherNow(_M):
    kp: QuantityOut
    proton_10mev_pfu: QuantityOut
    xray_class: str | None
    alerts: list[str]


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
    space_weather_now: SpaceWeatherNow
    range_conflicts: list[RangeConflict]
    range_note: str


class OfficialForecastIn(_M):
    probability_pct: float = Field(ge=0, le=100)
    concerns: list[str] = Field(default_factory=list, max_length=20)
    pdf_url: str = Field(pattern=r"^https://\S+$")


class OfficialForecastOut(_M):
    id: int
    probability_pct: float
    concerns: list[str]
    pdf_url: str
    entered_by: str
    entered_at: datetime


class LimitIn(_M):
    rule_id: str
    value: float = Field(gt=0)
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


class Capsule(_M):
    applicable: bool
    reason: str | None
    zone: Zone | None
    wave_height_m: QuantityOut | None
    wind_m_s: QuantityOut | None
    daylight: bool | None
    limits: SeaLimits


class Return(_M):
    booster: Booster | None
    capsule: Capsule | None


class SeaLimitsIn(_M):
    wave_height_m: float | None = None
    wind_m_s: float | None = None


class ReturnLimitsIn(_M):
    booster: SeaLimitsIn = Field(default_factory=SeaLimitsIn)
    capsule: SeaLimitsIn = Field(default_factory=SeaLimitsIn)
