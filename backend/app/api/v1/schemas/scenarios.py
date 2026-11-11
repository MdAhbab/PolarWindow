"""Scenarios and the activity tray on the wire.

Mirrors ``frontend/src/lib/api/experience.types.ts`` field for field (snake_case).
A scenario's results are the same ``{data, meta}`` sections the mission pages
show, so they travel as plain objects and are not re-modelled here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ScenarioSection = Literal["launch", "trip", "landing", "contact", "return"]
SectionState = Literal["available", "computing", "no_data", "needs_input", "not_applicable"]
Basis = Literal["you", "published", "live", "default"]
Status = Literal["queued", "running", "done", "failed"]
AssumptionValue = str | float | int | list[str] | None


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OptionOut(_Out):
    value: str
    label: str
    hint: str | None = None


class AssumptionSourceOut(_Out):
    name: str
    url: str | None = None
    fetched_at: str | None = None


class AssumptionOut(_Out):
    field: str
    label: str
    value: AssumptionValue
    display: str
    unit: str | None
    basis: Basis
    source: AssumptionSourceOut | None
    note: str | None


class AssumptionFieldOut(_Out):
    field: str
    label: str
    help: str
    kind: Literal["choice", "multi_choice", "date", "number"]
    unit: str | None
    options: list[OptionOut] | None
    min: float | None
    max: float | None
    default: AssumptionOut | None
    sections: list[ScenarioSection]


class MissingOut(_Out):
    field: str
    label: str
    why: str


class GapOut(_Out):
    section: ScenarioSection
    state: SectionState
    missing: list[MissingOut]
    can_explore: bool


class ScenarioBriefOut(_Out):
    id: str
    mission_id: str
    name: str
    prompt: str | None
    status: Status
    progress: float
    message: str
    preset: bool
    sections: list[ScenarioSection]
    created_at: str
    created_by_name: str | None


class ScenarioGapsOut(_Out):
    mission_id: str
    gaps: list[GapOut]
    fields: list[AssumptionFieldOut]
    presets: list[ScenarioBriefOut]
    suggestions: list[str]


class InterpretIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=1000)
    section: ScenarioSection | None = None


class InterpretedOut(_Out):
    assumptions: list[AssumptionOut]
    interpreted_as: str
    unresolved: list[str]
    method: Literal["model", "rules"]
    matches_preset: str | None


class AssumedValueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: AssumptionValue = None


class ScenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    prompt: str | None = Field(default=None, max_length=1000)
    assumptions: list[AssumedValueIn] = Field(default_factory=list, max_length=20)
    sections: list[ScenarioSection] | None = None


class PhaseOut(_Out):
    id: str
    label: str
    state: Literal["pending", "active", "done", "skipped", "failed"]
    detail: str | None


class ScenarioOut(ScenarioBriefOut):
    assumptions: list[AssumptionOut]
    phases: list[PhaseOut]
    summaries: dict[str, str]
    results: dict[str, Any] | None
    poll_after_s: float
    error: str | None


class ScenarioListOut(_Out):
    items: list[ScenarioBriefOut]


class ScenarioDeletedOut(_Out):
    id: str
    deleted: Literal[True] = True


class ActivityItemOut(_Out):
    key: str
    kind: Literal["launch", "trip", "contact", "rover", "site_build", "scenario"]
    label: str
    mission_id: str | None
    mission_name: str | None
    href: str | None
    status: Status
    progress: float | None
    message: str
    started_at: str
    finished_at: str | None


class ActivityOut(_Out):
    active: list[ActivityItemOut]
    recent: list[ActivityItemOut]
    poll_after_s: float
