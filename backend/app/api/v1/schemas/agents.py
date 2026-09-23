"""Agent request models and the shared response envelope."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: datetime | None = None
    end: datetime | None = None


class AdviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(
        min_length=3,
        max_length=1000,
        description="A mission requirement in plain language, e.g. "
        "'at least 4 hours of Earth contact per day and no night longer than 100 hours'.",
    )
    start: datetime | None = None
    end: datetime | None = None


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: datetime | None = None
    end: datetime | None = None


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=1000)


class ProvenanceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    value: float
    tool: str
    call_seq: int
    field: str


class ToolCallView(BaseModel):
    """One tool call, as shown in the demo's run log."""

    model_config = ConfigDict(extra="forbid")

    seq: int
    tool: str
    args: dict[str, Any]
    latency_ms: float
    error: str | None = None
    number_count: int


class AgentResponse(BaseModel):
    """Shared envelope for all four agents.

    `provenance` is produced by the grounding guard, not by the model, and is
    not optional. It is the artifact that makes the guard demonstrable rather
    than merely claimed.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "insufficient_data", "degraded"]
    run_status: Literal[
        "ok", "insufficient_data", "guard_rejected", "timeout", "degraded", "error"
    ] = Field(
        description="Why this answer is what it is, exactly as recorded in the run log. "
        "`status` folds the last four into `degraded`; this keeps them apart."
    )
    reason: str | None = None
    result: dict[str, Any] | None = None
    provenance: list[ProvenanceItem] = Field(default_factory=list)
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    run_id: str | None = None
    attempts: int = 1
    latency_ms: float = 0.0
    guard_failures: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Guards that fired, including ones a retry then fixed. Kept so the "
        "guard can be shown working rather than asserted to exist.",
    )
    meta: AgentMeta


class AgentResolution(BaseModel):
    """What the answer's numbers were computed at: those of the tools it called."""

    model_config = ConfigDict(extra="forbid")

    time_step_s: int
    azimuth_deg: float
    ephemeris: str
    source: str


class AgentUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grounded: bool = Field(
        description="Every number in the answer traced to a tool result (always true for an "
        "answer that is shown; a failed check replaces the text with the measurements)."
    )
    notes: list[str]


class AgentMeta(BaseModel):
    """The shared `meta` envelope for agent answers and the run log."""

    model_config = ConfigDict(extra="forbid")

    computed_at: datetime
    resolution: AgentResolution
    uncertainty: AgentUncertainty
    engine_version: str
    model: str
    agents_configured: bool = Field(description="False without an API key or under OFFLINE=1.")
    offline: bool
    notice: str


class AgentRunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    agent: str
    model: str
    status: str
    attempts: int
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime
    tool_calls: list[ToolCallView]
    guard_failures: list[dict[str, Any]] | None = None


class AgentRunList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AgentRunView]
    meta: AgentMeta
