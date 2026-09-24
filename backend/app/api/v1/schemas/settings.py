"""The project manager's settings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    ready: bool
    skipped_until: datetime | None = Field(
        description="When a skipped model is tried again; null when it is ready."
    )
    why: str | None = Field(description="Why it is being skipped, in words.")


class AiSettingsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(description="False: every AI panel answers from the measurements.")
    configured: bool = Field(
        description="A model API key is set and the server is not offline. Without it the "
        "switch has nothing to turn on."
    )
    customised: bool = Field(description="False while the configured defaults apply.")
    models: list[ModelState] = Field(description="The main list, in the order tried.")
    models_light: list[ModelState] = Field(
        description="The list for short explanations, in the order tried."
    )


class AiSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    models: list[str] = Field(min_length=1, max_length=20)
    models_light: list[str] = Field(min_length=1, max_length=20)


class Counts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missions: int
    candidate_sites: int
    mission_targets: int
    agent_runs: int
    cached_results: int | None = Field(description="Null when the cache is not in use.")


class SystemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="ok, degraded or down, as /healthz reports it.")
    moon_data: bool = Field(description="The south-polar elevation model is present.")
    sun_earth_data: bool = Field(description="The ephemeris files are loaded.")
    database: bool
    cache: bool
    counts: Counts


class SettingsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai: AiSettingsOut
    system: SystemOut


class Cleared(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what: str
    removed: int | None = Field(description="How many records went; null when there was no store.")
    message: str
