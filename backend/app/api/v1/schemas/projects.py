"""Projects the team enters, and files read into the project form.

Mirrors ``frontend/src/lib/api/experience.types.ts`` field for field. A
project is a mission record (``origin = 'project'``): only its name is
required, and every field left out stays unknown, listed in
``unconfirmed_fields``, never filled in.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.v1.schemas.jobs import JobRefOut
from app.api.v1.schemas.missions import InstrumentType, MissionBrief, MissionDetail

DatePrecision = Literal["second", "minute", "day", "month", "quarter", "year"]
ProjectStatus = Literal["planned", "in_transit", "operating", "completed"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectDateIn(_In):
    """A date as the team knows it. ``as_published`` is written by the server when omitted."""

    date: str = Field(
        min_length=4,
        max_length=40,
        description="ISO date or datetime (UTC): '2027', '2027-03', '2027-03-14' or "
        "'2027-03-14T10:30Z'.",
    )
    precision: DatePrecision
    as_published: str | None = Field(default=None, max_length=200)


class ProjectTargetIn(_In):
    """Exactly one of ``site_id`` or the coordinate (``lat_deg`` and ``lon_deg``)."""

    site_id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=160)
    lat_deg: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon_deg: float | None = Field(
        default=None,
        ge=-180.0,
        lt=360.0,
        description="Degrees east, 0-360 (-180..180 is accepted and normalised).",
    )

    @model_validator(mode="after")
    def _one_way(self) -> ProjectTargetIn:
        coord = (self.lat_deg is not None, self.lon_deg is not None)
        if coord[0] != coord[1]:
            raise ValueError("a coordinate needs both lat_deg and lon_deg")
        if (self.site_id is not None) == coord[0]:
            raise ValueError("give either site_id or a coordinate (lat_deg and lon_deg)")
        return self


class ProjectPayloadIn(_In):
    name: str = Field(min_length=1, max_length=200)
    acronym: str | None = Field(default=None, max_length=40)
    organisation: str | None = Field(default=None, max_length=200)
    instrument_types: list[InstrumentType] = Field(default_factory=list, max_length=12)
    purpose: str | None = Field(default=None, max_length=2000)


class ProjectLifecycleIn(_In):
    vehicle_id: str | None = Field(default=None, max_length=64)
    pad_id: str | None = Field(default=None, max_length=64)
    transfer_type: Literal["direct", "phasing_loops", "low_energy", "unknown"] | None = None
    flight_days: float | None = Field(default=None, gt=0.0, le=1000.0)
    lunar_orbit_days: float | None = Field(default=None, ge=0.0, le=1000.0)
    sun_el_min_deg: float | None = Field(default=None, ge=-5.0, le=90.0)
    sun_el_max_deg: float | None = Field(default=None, ge=-5.0, le=90.0)
    bands: list[str] = Field(default_factory=list, max_length=8)
    ground_stations: list[str] = Field(default_factory=list, max_length=40)
    relays: list[str] = Field(default_factory=list, max_length=12)
    mass_kg: float | None = Field(default=None, gt=0.0, le=1.0e6)
    returns: Literal["none", "sample_capsule", "crew"] | None = None

    @model_validator(mode="after")
    def _short_ids(self) -> ProjectLifecycleIn:
        for name in ("bands", "ground_stations", "relays"):
            if any(not 0 < len(x) <= 64 for x in getattr(self, name)):
                raise ValueError(f"each of {name} is 1 to 64 characters")
        return self


class ProjectIn(_In):
    """The project form. Only ``name`` is required; everything else may be left unknown."""

    name: str = Field(min_length=1, max_length=160)
    provider: str | None = Field(default=None, max_length=120)
    lander: str | None = Field(default=None, max_length=120)
    vehicle_name: str | None = Field(
        default=None, max_length=80, description="The spacecraft's own name ('Athena')."
    )
    task_order: str | None = Field(default=None, max_length=40)
    status: ProjectStatus = "planned"
    target: ProjectTargetIn | None = None
    launch: ProjectDateIn | None = None
    landing: ProjectDateIn | None = None
    end_of_mission: ProjectDateIn | None = None
    planned_surface_days: float | None = Field(default=None, gt=0.0, le=3650.0)
    lifecycle: ProjectLifecycleIn | None = None
    payloads: list[ProjectPayloadIn] = Field(default_factory=list, max_length=60)
    notes: list[str] = Field(default_factory=list, max_length=20)
    intake_id: int | None = Field(
        default=None,
        ge=1,
        description="The file reading this form was filled from, so each field keeps its "
        "evidence.",
    )

    @model_validator(mode="after")
    def _short_notes(self) -> ProjectIn:
        if any(len(n) > 1000 for n in self.notes):
            raise ValueError("each note is at most 1000 characters")
        return self


class ProjectDraft(ProjectIn):
    """The form as read from a file: ``name`` is empty when the file did not say it."""

    name: str = Field(default="", max_length=160)


class ProjectSaved(BaseModel):
    """POST /projects (201) and PUT /projects/{id} (200)."""

    model_config = ConfigDict(extra="forbid")

    mission: MissionDetail
    site_job: JobRefOut | None = Field(
        description="Set when the target is a new coordinate: its skyline is being built "
        "(job kind `site_build`). Until it is done, Surface and Contact say so."
    )


class ProjectList(BaseModel):
    """GET /projects: the team's own projects, newest first."""

    model_config = ConfigDict(extra="forbid")

    items: list[MissionBrief]
    total: int


class ProjectDeleted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    deleted: Literal[True]


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    hint: str | None = Field(default=None, description="A short second line.")


class SiteOption(Option):
    lat_deg: float
    lon_deg: float
    kind: Literal["candidate", "mission_target"]


class ProjectOptions(BaseModel):
    """GET /projects/options: every choice the form offers, from the catalogues."""

    model_config = ConfigDict(extra="forbid")

    vehicles: list[Option]
    pads: list[Option]
    sites: list[SiteOption] = Field(description="Existing sites, candidates first.")
    providers: list[str]
    landers: list[str]
    instrument_types: list[Option]
    relays: list[Option]
    max_upload_bytes: int
    accepted_extensions: list[str]
    model_reading: bool = Field(
        description="False with no model key: files are read by rules (dates, names, "
        "coordinates) only."
    )


class IntakeField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: Literal["stated", "inferred", "not_found"]
    evidence: str | None = Field(description="The words in the file, at most ~240 characters.")
    page: int | None = Field(description="1-based page (PDF) or line (text), when known.")
    note: str | None


class Intake(BaseModel):
    """POST /projects/intake: the form filled with what the file says, and where."""

    model_config = ConfigDict(extra="forbid")

    intake_id: int
    filename: str
    media_type: str
    size_bytes: int
    method: Literal["model", "rules"]
    model: str | None
    draft: ProjectDraft
    fields: dict[str, IntakeField]
    warnings: list[str]
    characters_read: int
