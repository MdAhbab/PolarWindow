"""Pydantic output contracts for the four agents.

Every agent returns a validated structured object. No free text is ever rendered
directly, which means a model that decides to write a paragraph instead of
filling fields fails validation and gets one repair attempt rather than reaching
the screen.

Every contract can express ``insufficient_data``. An agent that cannot answer
must be able to say so in-band, because the alternative -- a helpful-sounding
answer assembled from nothing -- is the specific failure this product cannot
afford.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["ok", "insufficient_data"]


class Citation(BaseModel):
    """Where one number in the output came from.

    Produced by the grounding guard, not by the model. A model-authored
    citation would be exactly as trustworthy as the number it cites.
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(description="The text fragment containing the number.")
    value: float
    tool: str
    call_seq: int
    field: str


class AgentEnvelope(BaseModel):
    """Shared wrapper around every agent response."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "insufficient_data", "degraded"]
    reason: str | None = Field(default=None, description="Required whenever status is not 'ok'.")
    result: dict[str, Any] | None = None
    provenance: list[Citation] = Field(default_factory=list)
    run_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# --- A1 Site Explainer -----------------------------------------------------


class NumberUsed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value_s: float | None = None
    value_deg: float | None = None
    value_fraction: float | None = None
    source: str = Field(description="Which tool call this came from.")


class SiteExplanation(BaseModel):
    """A1: what living at this site is like."""

    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str | None = None
    site_id: str | None = None
    paragraph: str | None = Field(
        default=None,
        description="One plain paragraph. No lists, no headings, no invented numbers.",
    )
    numbers_used: list[NumberUsed] = Field(default_factory=list)


# --- A2 Trade-off Advisor --------------------------------------------------


class RequirementCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    satisfied: bool
    observed_value: float | None = None
    observed_units: str | None = None
    note: str | None = None


class RankedSite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    rank: int
    satisfies_all: bool
    checks: list[RequirementCheck]
    why: str


class TradeOffAdvice(BaseModel):
    """A2: rank sites against a stated requirement.

    ``any_satisfies`` is a required field rather than something inferable from
    the list, because the failure mode being designed against is an agent that
    ranks the least-bad site as though it passed. Making the negative explicit
    forces the model to state it.
    """

    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str | None = None
    requirement_summary: str | None = None
    any_satisfies: bool = False
    nothing_satisfies_message: str | None = Field(
        default=None,
        description="Required when any_satisfies is false. Must say plainly that no "
        "site meets the requirement, not merely which is closest.",
    )
    ranked: list[RankedSite] = Field(default_factory=list)


# --- A3 Audience Writer ----------------------------------------------------


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience: Literal["planner", "educator", "public"]
    title: str
    body: str
    caveat: str = Field(
        description="The limitation a reader of this document most needs to know. "
        "Never dropped to make a document shorter."
    )


class AudienceBrief(BaseModel):
    """A3: same facts, three documents.

    One generation producing all three, not three generations. Three
    independent calls could disagree about the numbers, which is the actual risk
    in 'same facts, three audiences' -- and a disagreement between the memo and
    the public explainer is worse than either being slightly less polished.
    """

    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str | None = None
    site_id: str | None = None
    planner_memo: Document | None = None
    lesson_plan: Document | None = None
    public_explainer: Document | None = None
    shared_numbers: list[NumberUsed] = Field(default_factory=list)


# --- A4 Question Answerer --------------------------------------------------


class AnswerRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    values: dict[str, float] = Field(default_factory=dict)


class QuestionAnswer(BaseModel):
    """A4: natural language over the site database."""

    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str | None = None
    question: str | None = None
    answer: str | None = None
    rows: list[AnswerRow] = Field(default_factory=list)
    interpreted_as: str | None = Field(
        default=None,
        description="How the question was turned into filters. Shown to the user so a "
        "misreading is visible rather than silent.",
    )
