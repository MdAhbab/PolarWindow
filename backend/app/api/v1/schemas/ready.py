"""Ready (T3) on the wire: docs/lifecycle-api.md, section *Ready* and its *Changes*."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.v1.schemas.common import LifecycleMeta, QuantityOut

T = TypeVar("T")

ReadyState = Literal[
    "not_started",
    "in_build",
    "in_test",
    "test_passed",
    "delivered",
    "integrated",
    "verified_on_lander",
    "ready",
    "blocked",
]
ItemKind = Literal[
    "lander",
    "payload",
    "rover",
    "launch_vehicle",
    "range",
    "ground_booking",
    "relay_agreement",
    "ops_team",
    "licence",
]
TestKind = Literal["vibration", "shock", "thermal_vacuum", "emi_emc", "functional"]
PartStatus = Literal["installed", "spare", "in_test", "damaged", "failed", "lost"]
RiskCategory = Literal["safety", "technical", "cost", "schedule"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Section(_M, Generic[T]):
    """Every section response: the answer and its `meta` (ADR-9)."""

    data: T
    meta: LifecycleMeta


class TestRecord(_M):
    kind: TestKind
    result: Literal["passed", "failed", "not_done"]
    report_url: str | None
    date: str | None


class ReadyItem(_M):
    id: str
    kind: ItemKind
    name: str
    organisation: str | None
    state: ReadyState
    state_known: bool = Field(
        description="False for a prefilled item nobody has entered a state for: show "
        "'not entered yet', not the state. Such items are not in `counts`."
    )
    allowed_next: list[ReadyState] = Field(description="States this item may move to next.")
    blocked_reason: str | None
    changed_at: str | None = Field(description="The date the change happened, as entered.")
    changed_by: str | None
    evidence_url: str | None
    source: Literal["public", "entered"]
    tests: list[TestRecord]


class Milestone(_M):
    id: str
    name: str
    date: QuantityOut
    done: bool
    source: str | None


class RiskRating(_M):
    category: RiskCategory
    likelihood: int = Field(ge=1, le=100)
    consequence: int = Field(ge=1, le=100)


_Id = Annotated[str, StringConstraints(max_length=160)]


class RiskLinks(_M):
    readiness_items: list[_Id] = Field(default_factory=list, max_length=200)
    parts: list[_Id] = Field(default_factory=list, max_length=200)
    lessons: list[_Id] = Field(default_factory=list, max_length=200)


class Risk(_M):
    id: str
    title: str
    cause: str
    consequence_text: str
    scale_id: str
    ratings: list[RiskRating] = Field(description="Per category; never multiplied or summed.")
    trend: Literal["rising", "steady", "falling"]
    owner: str | None
    mitigation: str | None
    links: RiskLinks
    changed_at: datetime | None = None
    changed_by: str | None = None


class PartsSummary(_M):
    total: int
    spares: int
    lost: int
    damaged: int
    failed: int


class Ready(_M):
    counts: dict[ReadyState, int] = Field(description="Items per state. Never a percentage.")
    not_entered: int = Field(description="Prefilled items with no state entered yet.")
    items: list[ReadyItem]
    milestones: list[Milestone]
    risks: list[Risk]
    parts: PartsSummary
    lessons_available: int
    lessons_adopted: int


class ItemCreateIn(_M):
    kind: ItemKind
    name: str = Field(min_length=1, max_length=200)
    organisation: str | None = Field(default=None, max_length=200)


class ItemMoveIn(_M):
    state: ReadyState
    date: str = Field(description="When it happened, ISO date.", min_length=10, max_length=32)
    evidence_url: str = Field(min_length=8, max_length=2000)
    note: str | None = Field(default=None, max_length=4000)
    blocked_reason: str | None = Field(default=None, max_length=2000)


class TestIn(_M):
    kind: TestKind
    result: Literal["passed", "failed", "not_done"]
    report_url: str | None = Field(default=None, max_length=2000)
    date: str | None = Field(default=None, max_length=32)


class HistoryEntry(_M):
    at: datetime
    by: str
    action: str
    before: Any
    after: Any
    note: str | None


class History(_M):
    entries: list[HistoryEntry]


class Part(_M):
    id: str
    name: str
    part_number: str | None
    serial: str | None
    parent_item_id: str | None
    status: PartStatus
    location: str | None
    changed_at: datetime | None
    changed_by: str | None


class Parts(_M):
    parts: list[Part]


class PartIn(_M):
    name: str = Field(min_length=1, max_length=200)
    part_number: str | None = Field(default=None, max_length=120)
    serial: str | None = Field(default=None, max_length=120)
    parent_item_id: str | None = Field(default=None, max_length=160)
    status: PartStatus
    location: str | None = Field(default=None, max_length=200)


class PartPatch(_M):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    part_number: str | None = Field(default=None, max_length=120)
    serial: str | None = Field(default=None, max_length=120)
    parent_item_id: str | None = Field(default=None, max_length=160)
    status: PartStatus | None = None
    location: str | None = Field(default=None, max_length=200)


class ImpactItem(_M):
    id: str
    name: str
    kind: str


class PartImpact(_M):
    stops_working: list[ImpactItem]
    note: str


class Risks(_M):
    risks: list[Risk]


class RiskIn(_M):
    title: str = Field(min_length=1, max_length=300)
    cause: str = Field(min_length=1, max_length=4000)
    consequence_text: str = Field(min_length=1, max_length=4000)
    scale_id: str = Field(max_length=64)
    ratings: list[RiskRating] = Field(min_length=1, max_length=20)
    trend: Literal["rising", "steady", "falling"]
    owner: str | None = Field(default=None, max_length=200)
    mitigation: str | None = Field(default=None, max_length=4000)
    links: RiskLinks = Field(default_factory=RiskLinks)


class RiskPatch(_M):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    cause: str | None = Field(default=None, max_length=4000)
    consequence_text: str | None = Field(default=None, max_length=4000)
    scale_id: str | None = Field(default=None, max_length=64)
    ratings: list[RiskRating] | None = Field(default=None, min_length=1, max_length=20)
    trend: Literal["rising", "steady", "falling"] | None = None
    owner: str | None = Field(default=None, max_length=200)
    mitigation: str | None = Field(default=None, max_length=4000)
    links: RiskLinks | None = None


class RiskLevel(_M):
    level: int
    words: str


class ConsequenceScale(_M):
    category: RiskCategory
    levels: list[RiskLevel]


class RiskScale(_M):
    id: str
    name: str
    source_url: str | None
    likelihood: list[RiskLevel]
    consequence: list[ConsequenceScale]
    notes: list[str] = Field(default_factory=list)


class RiskScales(_M):
    default_id: str
    scales: list[RiskScale]


class Attempt(_M):
    mission: str
    agency: str
    date: str
    outcome: Literal["landed_working", "landed_tipped_or_partial", "failed"]
    cause: str | None
    source_url: str
    cause_url: str | None
    clps: bool
    mission_id: str | None


class AttemptCounts(_M):
    attempts: int
    landed_working: int
    landed_tipped_or_partial: int
    failed: int


class LandingHistory(_M):
    attempts: list[Attempt]
    counts: AttemptCounts = Field(description="Counts of outcomes; never a chance of success.")
    since: str | None
    note: str


class Lesson(_M):
    id: str
    text: str
    from_mission: str
    year: int
    source_url: str
    checklist_item: str
    adopted: bool


class Lessons(_M):
    lessons: list[Lesson]


class Adopted(_M):
    adopted: bool
    item_id: str


class Parameter(_M):
    id: str
    name: str
    value: QuantityOut
    note: str | None
    changed_by: str | None
    changed_at: datetime | None


class Parameters(_M):
    parameters: list[Parameter]


class ParameterIn(_M):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    value: float
    note: str | None = Field(default=None, max_length=2000)
