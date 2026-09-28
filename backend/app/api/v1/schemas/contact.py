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


class RelayOrbit(_M):
    periapsis_km: QuantityOut = Field(description="Height of the near point above the mean radius.")
    apoapsis_km: QuantityOut = Field(description="Height of the far point above the mean radius.")
    inclination_deg: QuantityOut = Field(description="To the lunar equator.")
    arg_periapsis_deg: QuantityOut = Field(
        description="About 90 degrees puts the far point over the south pole."
    )
    period_h: QuantityOut


class RelayRow(_M):
    id: str
    name: str
    adds_h: QuantityOut = Field(description="Time it adds to direct contact, as a range.")
    via_h: QuantityOut = Field(
        description="Time the lander can reach Earth through it, as a range."
    )
    status: str = Field(description="Its launch note, or its status when there is none.")
    launch_status: Literal["operating", "planned", "not_launched", "launched_not_operating"]
    for_this_mission: bool = Field(
        description="False for a relay added to compare what it would add; not planned "
        "for this mission."
    )
    orbit: RelayOrbit
    orbit_note: str | None
    sweep_note: str | None = Field(
        description="What was swept to get the ranges; null when nothing was worked out."
    )


class DirectOnly(_M):
    longest_unheard_h: QuantityOut
    longest_message_wait_min: QuantityOut


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
    direct_only: DirectOnly | None = Field(
        description="With a relay in the graph: the same two numbers without it. Null otherwise."
    )
    relay_note: str | None
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
