"""Space weather now (track E) on the wire: docs/lifecycle-api.md, *Changes*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import QuantityOut


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Now(_M):
    kp: QuantityOut
    proton_10mev_pfu: QuantityOut
    proton_100mev_pfu: QuantityOut
    xray_class: str | None
    xray_missing_reason: str | None = Field(
        description="Why there is no X-ray class (no reading recorded, or too old); null "
        "when there is one."
    )
    solar_wind_km_s: QuantityOut
    bz_nt: QuantityOut
    alerts: list[str] = Field(description="SWPC alert headlines of the last 24 hours.")
    alerts_missing_reason: str | None = Field(
        description="Why the alert list is not shown (not recorded, or too old); null when "
        "it is current, so an empty list means SWPC issued no alert in the last 24 hours."
    )


class Outlook(_M):
    issued: datetime | None
    days: str | None
    s1_or_greater_pct: list[int] | None = Field(
        description="SWPC's chance of a solar radiation storm (S1 or more), day 1-3, verbatim."
    )
    kp_max_expected: float | None
    text: str | None = Field(description="SWPC's 3-day forecast as issued.")
    missing_reason: str | None


class Cme(_M):
    id: str
    start: str | None
    speed_m_s: float | None
    earth_arrival_estimates: list[str] | None
    link: str | None


class Flare(_M):
    id: str
    peak: str | None
    class_: str | None = Field(alias="class")
    link: str | None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Sep(_M):
    id: str
    time: str | None
    instruments: list[str | None] | None
    link: str | None


class DonkiCounts(_M):
    cme: int | None
    flares: int | None
    sep: int | None


class Donki(_M):
    cme: list[Cme] = Field(description="The newest 20.")
    flares: list[Flare] = Field(description="The newest 20.")
    sep: list[Sep] = Field(description="The newest 20.")
    counts: DonkiCounts = Field(
        description="How many DONKI gave per kind over `days` (the lists show the newest "
        "20); null for a kind not shown."
    )
    days: int | None = Field(description="How many days back DONKI was asked.")
    missing_reason: str | None


class SpaceWeather(_M):
    now: Now
    outlook: Outlook
    donki: Donki
    note: str
