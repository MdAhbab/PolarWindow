"""Contact (T1) on the wire: docs/lifecycle-api.md, section *Contact*."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import QuantityOut


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StretchOut(_M):
    start: datetime
    end: datetime
    open_start: bool = Field(description="Cut by the start of the dates.")
    open_end: bool = Field(description="Cut by the end of the dates.")


class Node(_M):
    id: str
    kind: Literal["station", "relay", "lander", "rover", "earth"]
    name: str
    operator: str | None
    status: Literal["operating", "planned", "not_launched"]
    orbit: Literal["real", "planned"] | None
    launch_note: str | None


class Link(_M):
    from_: str = Field(alias="from")
    to: str
    stretches: list[StretchOut]
    data_rate_kbps: QuantityOut | None
    margin_db: QuantityOut | None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ContactNumbers(_M):
    direct_h: QuantityOut = Field(
        description="Time in contact with Earth (Earth above the skyline)."
    )
    via_relay_h: QuantityOut = Field(
        description="Through a relay, as a range, if it flies as planned."
    )
    either_h: QuantityOut
    station_hears_h: QuantityOut = Field(description="Time a ground station can hear the lander.")
    longest_unheard_h: QuantityOut
    longest_message_wait_min: QuantityOut
    dark_and_unheard_h: QuantityOut = Field(
        description="The longest single stretch that is dark and out of contact at once."
    )


class RelayRow(_M):
    id: str
    name: str
    adds_h: QuantityOut
    status: str


class Booking(_M):
    station: str
    start: datetime
    end: datetime
    entered_by: str
    note: str | None = None


class LightTime(_M):
    min: float
    max: float


class Contact(_M):
    start: datetime
    end: datetime
    window_note: str
    nodes: list[Node]
    links: list[Link]
    numbers: ContactNumbers
    relays: list[RelayRow]
    link_budget_note: str | None
    bookings: list[Booking]
    light_time_s: LightTime
    longest_wait_from: datetime
    sun_total_h: QuantityOut


class BookingIn(_M):
    station: str = Field(
        max_length=64, description="Ground station id from the catalogue, e.g. `dss-14`."
    )
    start: datetime
    end: datetime
    note: str | None = Field(default=None, max_length=2000)


class BookingOut(_M):
    id: int
    station: str
    start: datetime
    end: datetime
    note: str | None
    entered_by: str
    entered_at: datetime


class RoverOut(_M):
    viewshed_tile: str | None
    out_of_sight_share: QuantityOut
    longest_out_of_sight_m: QuantityOut
    resolvable: bool
    reason: str | None
