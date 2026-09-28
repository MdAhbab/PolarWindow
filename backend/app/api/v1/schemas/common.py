"""Shared response pieces: the `meta` envelope and the error contract.

Every 200 response in this API carries `meta`, and `meta.uncertainty` is never
absent and never null. That is a product rule, not a convention: the frontend's
design carries an uncertainty state in every data-bound component, and an
endpoint that omits the margin forces the UI to either invent one or hide it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Resolution(BaseModel):
    """What this answer was computed at."""

    model_config = ConfigDict(extra="forbid")

    azimuth_deg: float = Field(description="Angular step of the horizon mask, degrees.")
    azimuth_count: int
    time_step_s: int = Field(description="Sampling step of the timeline, seconds.")
    max_range_m: float = Field(description="How far terrain was modelled around the site.")
    dem_product: str
    dem_resolution_m: float
    ephemeris: str
    frame: str


class Uncertainty(BaseModel):
    """How wrong this could be, in the units the caller is reading."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["terrain"] = Field(
        default="terrain",
        description="Which uncertainty envelope this is (ADR-9). Surface answers are "
        "always `terrain`; lifecycle answers carry a `composite` envelope instead.",
    )

    dem_vertical_error_m: float
    dem_resolution_m: float
    coverage: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of sampled terrain that fell inside the elevation model. "
        "Below 1.0 the mask is partial and the numbers are likely optimistic.",
    )
    horizon_el_deg: float = Field(
        description="Angular uncertainty of the skyline, from the DEM's vertical error "
        "at the range where the skyline is actually set."
    )
    edge_timing_s: float | None = Field(
        description="Worst arc-edge timing uncertainty in this response, seconds. "
        "null when at least one crossing is a graze -- see `grazing`. A null here is "
        "a stronger statement than a large number: the edge is not knowable from this data."
    )
    grazing: bool
    penumbra_sun_deg: float = Field(
        description="Apparent angular radius of the Sun from the Moon. The lit/dark "
        "boundary is soft by this much."
    )
    penumbra_earth_deg: float
    terrain_modelled: bool = Field(
        default=True,
        description="False when no elevation model covers the site (a CLPS target outside "
        "80 deg S): the skyline is a smooth sphere, so real terrain could block more.",
    )
    notes: list[str]


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    computed_at: datetime
    resolution: Resolution
    uncertainty: Uncertainty
    engine_version: str
    cache: Literal["hit", "miss", "bypass", "memo"] = "miss"
    compute_ms: float | None = None


class ErrorUI(BaseModel):
    """What the frontend's ErrorPanel renders, with no translation layer.

    The panel already takes a title, a detail and a "what still works" line;
    supplying all three from the server means an error message can be improved
    without a frontend deploy, and means no error ever renders as a shrug.
    """

    model_config = ConfigDict(extra="forbid")

    still_works: str
    retryable: bool = False
    action: str | None = None


class Problem(BaseModel):
    """RFC 9457 problem details, plus the UI block."""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    ui: ErrorUI


# ---------------------------------------------------------------------------
# Lifecycle answers (ADR-9): one number shape and a composite envelope
# ---------------------------------------------------------------------------

Provenance = Literal["computed", "published", "entered", "assumed"]


class QuantityOut(BaseModel):
    """A number with its margin in exactly one form, or the reason it has none.

    Mirrors `app/core/quantity.py`, which refuses to build a number that breaks
    these rules; this model is how it reaches the wire.
    """

    model_config = ConfigDict(extra="forbid")

    value: float | None
    unit: str
    provenance: Provenance
    pm: float | None = Field(default=None, description="Symmetric margin, same unit.")
    lo: float | None = Field(default=None, description="Lower end of a range.")
    hi: float | None = Field(default=None, description="Upper end of a range.")
    factor: float | None = Field(
        default=None, ge=1.0, description="Multiplicative margin: value / factor to value * factor."
    )
    open: bool = Field(default=False, description="A lower bound: the dates cut it short.")
    no_margin_reason: str | None = None
    missing_reason: str | None = Field(
        default=None, description="Why there is no value, when `value` is null."
    )
    source: str | None = Field(
        default=None, description="Who entered it, or the URL it was published at."
    )


class ShareOut(BaseModel):
    """k of n model runs, with an exact 95 % interval (ADR-9, ADR-14)."""

    model_config = ConfigDict(extra="forbid")

    k: int = Field(ge=0)
    n: int = Field(ge=1)
    lo: float = Field(ge=0.0, le=1.0)
    hi: float = Field(ge=0.0, le=1.0)
    checked: bool = Field(
        description="True only once this rule has been checked against observations."
    )


class SourceRef(BaseModel):
    """Where one input to an answer came from, and when."""

    model_config = ConfigDict(extra="forbid")

    name: str
    url: str | None = None
    issued_at: datetime | None = Field(
        default=None, description="Model run or issue time of a forecast; null for files."
    )
    fetched_at: datetime | None = None
    licence: str | None = None
    snapshot_id: int | None = Field(
        default=None, description="The stored snapshot this answer used (ADR-8)."
    )


class UncertaintyPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="What contributes this error, in plain words.")
    note: str


class CompositeUncertainty(BaseModel):
    """Every source of error in a lifecycle answer, one part each."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["composite"] = "composite"
    parts: list[UncertaintyPart]


class LifecycleMeta(BaseModel):
    """`meta` for launch, trip, contact, readiness and recovery answers."""

    model_config = ConfigDict(extra="forbid")

    computed_at: datetime
    uncertainty: CompositeUncertainty
    engines: dict[str, str] = Field(description="Engine versions this answer depends on.")
    sources: list[SourceRef]
    stale: bool = Field(
        default=False,
        description="True when an input is past its staleness budget; the numbers it "
        "fed are then missing, with the reason (invariant 11).",
    )
    compute_ms: float | None = None
