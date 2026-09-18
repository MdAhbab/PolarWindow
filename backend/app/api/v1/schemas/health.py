"""Health response models.

Typed rather than a bare dict, because the frontend's client is generated from
the OpenAPI document: an untyped endpoint produces `never` on the client and
quietly defeats the whole reason for generating. The provenance badge reads
these fields, so they are part of the contract, not diagnostics.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KernelHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loaded: bool
    count: int
    furnsh_ms: float
    missing: list[str]
    error: str | None = None


class DemHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regional_present: bool
    fine_windows: int = Field(description="Per-site high-resolution windows on disk.")
    product: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "down"] = Field(
        description="`degraded` still returns 200: a missing elevation model leaves "
        "every ephemeris endpoint working and the UI has a state for partial data. "
        "Only a missing ephemeris or database is `down`."
    )
    engine_version: str
    kernels: KernelHealth
    db: Literal["ok", "down"]
    redis: Literal["ok", "bypass"]
    dem: DemHealth
