"""Request and response models for POST /sites/{site_id}/energy (ADR-21)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import Meta, QuantityOut


class FigureIn(BaseModel):
    """A figure with its provenance. A bare number means 'entered by the caller'."""

    model_config = ConfigDict(extra="forbid")

    value: float | str
    provenance: Literal["entered", "published", "assumed"] = "entered"
    source: str | None = Field(
        default=None,
        description="Required for published (the URL) and assumed (how it was derived).",
    )


Figure = float | FigureIn


class LanderIn(BaseModel):
    """Every lander figure is an input; there are no defaults. A missing required
    figure is a 422 naming the field. Temperatures are in degrees Celsius."""

    model_config = ConfigDict(extra="forbid")

    array_geometry: Literal["vertical_faces", "top_deck_flat", "sun_tracking"] | FigureIn | None = (
        None
    )
    array_area_m2: Figure | None = Field(
        default=None, description="One face's area for vertical_faces; the whole array otherwise."
    )
    face_count: Figure | None = Field(default=None, description="vertical_faces only; at least 3.")
    face_azimuth_offset_deg: Figure | None = Field(
        default=None,
        description="vertical_faces only: bearing of face 0; the rest are evenly spaced.",
    )
    cell_efficiency: Figure | None = None
    dust_loss_fraction: Figure | None = None
    battery_capacity_wh: Figure | None = None
    initial_soc_fraction: Figure | None = None
    avionics_w: Figure | None = None
    payload_w: Figure | None = None
    load_dissipation_fraction: Figure | None = Field(
        default=None, description="Share of avionics and payload power that heats the bus."
    )
    heater_power_w: Figure | None = None
    heater_setpoint_c: Figure | None = None
    initial_bus_temp_c: Figure | None = None
    operational_min_c: Figure | None = None
    survival_min_c: Figure | None = None
    bus_absorptivity: Figure | None = None
    bus_side_area_m2: Figure | None = Field(
        default=None, description="Area the Sun sees from the horizon (vertical sides)."
    )
    bus_top_area_m2: Figure | None = Field(
        default=None, description="Area the Sun sees from overhead."
    )
    bus_emissivity: Figure | None = None
    regolith_emissivity: Figure | None = None
    regolith_absorptivity: Figure | None = None
    view_factor: Figure | None = Field(default=None, description="Lander to regolith.")
    base_area_m2: Figure | None = None
    radiator_emissivity: Figure | None = None
    radiator_area_m2: Figure | None = None
    heat_capacity_j_per_k: Figure | None = None


class EnergyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime | None = None
    end: datetime | None = None
    step_s: int | None = Field(default=None, ge=60, le=86400)
    lander: LanderIn
    lander_example_id: str | None = Field(
        default=None,
        description="Fill figures not given in `lander` from a catalogue example, "
        "each keeping its own provenance.",
    )
    ground_radius_m: float = Field(
        default=1000.0,
        gt=0,
        le=20000,
        description="Diviner triangles within this distance of the site set the ground "
        "temperatures; their spread is the uncertainty.",
    )


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lo: list[float | None]
    value: list[float | None]
    hi: list[float | None] = Field(
        description="Entries are null when the warm end of the ground range is unknown."
    )


class EnergySeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t_s: list[int] = Field(description="Seconds from the window start.")
    t_utc: list[str | None]
    p_gen_w: list[float]
    lit: list[float] = Field(description="1 while the Sun's centre is above the skyline.")
    soc_wh: Band
    t_bus_c: Band


class TimeQuantityOut(QuantityOut):
    """A time as hours after the window start, with its UTC copies."""

    value_utc: str | None = None
    lo_utc: str | None = None
    hi_utc: str | None = None


class EnergyKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    energy_generated: QuantityOut
    lowest_soc: QuantityOut
    battery_empty_at: TimeQuantityOut
    lowest_bus_temperature: QuantityOut
    hours_below_operational: QuantityOut
    survival_threshold_crossed_at: TimeQuantityOut


class EnergyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: str | None
    end: str | None
    step_s: int
    inputs: dict[str, Any] = Field(
        description="Every lander figure echoed with its provenance (entered, published, assumed)."
    )
    model: dict[str, Any]
    ground: dict[str, Any]
    series: EnergySeries
    key: EnergyKey
    not_modelled: list[str]
    meta: Meta
