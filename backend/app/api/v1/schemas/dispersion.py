"""Request and response models for POST /sites/{site_id}/dispersion (ADR-22)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import Meta


class EllipseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semi_major_m: float = Field(gt=0, le=20000, description="3-sigma semi-major axis, metres.")
    semi_minor_m: float = Field(gt=0, le=20000, description="3-sigma semi-minor axis, metres.")
    azimuth_deg: float = Field(
        ge=-360, le=360, description="Bearing of the major axis from true north, clockwise."
    )


class LanderFiguresIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    footprint_diameter_m: float = Field(gt=0, le=100, description="Diameter of the footpad circle.")
    cg_height_m: float = Field(gt=0, le=100, description="Centre-of-gravity height above ground.")
    slope_limit_deg: float = Field(gt=0, lt=90, description="The lander's entered slope limit.")


class DispersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ellipse: EllipseIn
    lander: LanderFiguresIn
    samples: int = Field(default=1000, ge=50, le=2000, description="Landing points drawn.")


class DispersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    inputs: dict[str, Any]
    slope_source: dict[str, Any]
    slope: dict[str, Any]
    tip_over: dict[str, Any]
    shares: dict[str, Any]
    illumination: dict[str, Any]
    heatmap: dict[str, Any]
    sources: list[dict[str, str]]
    not_modelled: list[str]
    meta: Meta
