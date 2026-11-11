"""Request and response models for POST /sites/{site_id}/mesh/simulate (ADR-23).

Every radio, battery, traffic and guard figure is required: there are no defaults, so a
missing one is a 422 naming the field. Nothing is stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.v1.schemas.common import Meta


class XY(BaseModel):
    model_config = ConfigDict(extra="forbid")

    east_m: float = Field(ge=-5000, le=5000, description="East of the site origin, metres.")
    north_m: float = Field(ge=-5000, le=5000, description="North of the site origin, metres.")


class WaypointIn(XY):
    t_s: float = Field(ge=0, description="Seconds from the window start; the node sits here.")


class NodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str | None = Field(default=None, max_length=80)
    position: XY | None = Field(default=None, description="A fixed node (lander or parked rover).")
    waypoints: list[WaypointIn] | None = Field(
        default=None, max_length=8, description="Positions by time, instead of position."
    )
    antenna_height_m: float = Field(ge=0, le=50)
    battery_capacity_wh: float = Field(gt=0)
    initial_soc_fraction: float = Field(gt=0, le=1)
    own_traffic_bps: float = Field(ge=0, description="The node's own traffic, served first.")
    may_help: bool = Field(description="Whether this node may forward for others.")
    earth_uplink_bps: float | None = Field(
        default=None, gt=0, description="Optional: this node's direct Earth rate, if an exit."
    )
    earth_uplink_power_w: float | None = Field(
        default=None, gt=0, description="Optional: DC power drawn while uplinking to Earth."
    )

    @model_validator(mode="after")
    def _where(self) -> NodeIn:
        if (self.position is None) == (not self.waypoints):
            raise ValueError("give exactly one of position or waypoints")
        return self


class RadioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frequency_hz: float = Field(gt=0)
    tx_power_w: float = Field(gt=0, description="A node's own transmit power (RF).")
    forwarding_tx_power_w: float = Field(gt=0, description="A helper's transmit power (RF).")
    tx_efficiency: float = Field(gt=0, le=1, description="RF output over DC input.")
    antenna_gain_dbi: float = Field(description="At each end.")
    bandwidth_hz: float = Field(gt=0)
    noise_figure_db: float
    snr_threshold_db: float = Field(description="The link closes at or above this SNR.")
    eps_r: float = Field(ge=1, description="Relative permittivity of the regolith.")
    polarisation: Literal["horizontal", "vertical"]


class GuardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soc_cutoff_fraction: float = Field(ge=0, le=1, description="A helper stops below this charge.")
    quota_share_per_lunar_day: float = Field(
        ge=0, le=1, description="Share of a helper's battery it may spend forwarding per day."
    )
    max_forwarding_power_w: float = Field(gt=0, description="Cap on a helper's forwarding power.")
    buffer_bytes: float = Field(ge=0, description="A helper's buffer for waiting peer data.")


class MeshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime | None = None
    end: datetime | None = None
    step_s: int | None = Field(default=None, ge=60, le=86400)
    nodes: list[NodeIn] = Field(min_length=1, max_length=6)
    radio: RadioIn
    guard: GuardIn
    loss_threshold_s: float = Field(
        ge=0, description="A direct-link loss longer than this wakes the radio."
    )


class MeshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: str
    end: str
    step_s: int
    inputs: dict[str, Any]
    nodes: list[dict[str, Any]]
    links: list[dict[str, Any]]
    helpers: list[dict[str, Any]]
    terrain: dict[str, Any]
    timing_ms: dict[str, Any]
    not_modelled: list[str]
    meta: Meta
