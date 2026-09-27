"""Ready (T3): readiness, parts, risks, lessons, landing history, parameters.

Reading is public. Every change needs a named session (ADR-17) and writes a
line in the change history.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from fastapi.exceptions import HTTPException

from app.api.v1 import deps
from app.api.v1.schemas.ready import (
    Adopted,
    History,
    ItemCreateIn,
    ItemMoveIn,
    LandingHistory,
    Lessons,
    ParameterIn,
    Parameters,
    Part,
    PartImpact,
    PartIn,
    PartPatch,
    Parts,
    Ready,
    ReadyItem,
    Risk,
    RiskIn,
    RiskPatch,
    Risks,
    RiskScales,
    Section,
    TestIn,
)
from app.services import auth_service, parameters_service, ready_service
from app.services.mission_service import MissionNotFound

router = APIRouter(tags=["ready"])

Named = auth_service.Claims


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, MissionNotFound):
        return deps.to_http(exc)
    if isinstance(exc, ready_service.NotFound):
        return deps.problem(
            404,
            "not-found",
            "Not found",
            f"There is no record '{exc.args[0]}'.",
            "Every other record is unaffected.",
        )
    if isinstance(exc, ready_service.IllegalMove):
        p = deps.problem(
            409,
            "illegal-move",
            "That change is not allowed",
            f"{exc} Allowed next: {', '.join(exc.allowed)}.",
            "The item is unchanged.",
            action="Choose one of the allowed states",
        )
        detail: Any = p.detail
        detail["allowed"] = exc.allowed
        return p
    if isinstance(exc, ready_service.BadEntry | parameters_service.BadValue):
        return deps.problem(
            422,
            "bad-entry",
            "That entry cannot be saved",
            str(exc),
            "Nothing was changed.",
            action="Correct the entry",
        )
    if isinstance(exc, parameters_service.UnknownParameter):
        return deps.problem(
            404,
            "not-found",
            "No such parameter",
            f"'{exc.args[0]}' is not a parameter.",
            "Every other parameter is unaffected.",
        )
    raise exc


@router.get(
    "/missions/{mission_id}/ready",
    response_model=Section[Ready],
    summary="Readiness: every item's state, milestones, risks and parts",
)
async def get_ready(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await ready_service.ready(session, mission_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/missions/{mission_id}/ready/items",
    response_model=ReadyItem,
    status_code=201,
    summary="Add a readiness item",
)
async def add_item(
    mission_id: str,
    body: ItemCreateIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.add_item(
            session,
            who,
            mission_id,
            kind=body.kind,
            name=body.name,
            organisation=body.organisation,
        )
    except Exception as exc:
        raise _http(exc) from exc


@router.patch(
    "/ready/items/{item_id}",
    response_model=ReadyItem,
    summary="Move an item to its next state (409 with the allowed states when not allowed)",
)
async def move_item(
    item_id: str,
    body: ItemMoveIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.move_item(
            session,
            who,
            item_id,
            state=body.state,
            date=body.date,
            evidence_url=body.evidence_url,
            note=body.note,
            blocked_reason=body.blocked_reason,
        )
    except Exception as exc:
        raise _http(exc) from exc


@router.put(
    "/ready/items/{item_id}/tests",
    response_model=ReadyItem,
    summary="Record an environmental test result for an item",
)
async def record_test(
    item_id: str,
    body: TestIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.record_test(
            session,
            who,
            item_id,
            kind=body.kind,
            result=body.result,
            report_url=body.report_url,
            date=body.date,
        )
    except Exception as exc:
        raise _http(exc) from exc


@router.get(
    "/ready/items/{item_id}/history",
    response_model=History,
    summary="Change history of one readiness item",
)
async def item_history(item_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await ready_service.history(session, "ready_item", item_id)


@router.get("/history", response_model=History, summary="Change history of any entered record")
async def history(
    entity: str = Query(
        description="ready_item, part, risk, booking, forecast, limits, " "parameter, lesson, feed"
    ),
    record_id: str = Query(alias="id"),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        return await ready_service.history(session, entity, record_id)
    except Exception as exc:
        raise _http(exc) from exc


# --- parts -----------------------------------------------------------------------


@router.get("/missions/{mission_id}/parts", response_model=Parts, summary="Flight parts and spares")
async def list_parts(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await ready_service.parts(session, mission_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/missions/{mission_id}/parts", response_model=Part, status_code=201, summary="Add a part"
)
async def add_part(
    mission_id: str,
    body: PartIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.save_part(session, who, mission_id, None, body.model_dump())
    except Exception as exc:
        raise _http(exc) from exc


@router.patch("/parts/{part_id}", response_model=Part, summary="Change a part (its status, place)")
async def patch_part(
    part_id: str,
    body: PartPatch,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.save_part(
            session, who, None, part_id, body.model_dump(exclude_unset=True)
        )
    except Exception as exc:
        raise _http(exc) from exc


@router.get(
    "/parts/{part_id}/impact",
    response_model=PartImpact,
    summary="What stops working if this part is lost",
)
async def part_impact(part_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await ready_service.part_impact(session, part_id)
    except Exception as exc:
        raise _http(exc) from exc


# --- risks -------------------------------------------------------------------------


@router.get("/risk-scales", response_model=RiskScales, summary="Likelihood and consequence scales")
async def risk_scales() -> dict[str, Any]:
    return ready_service.risk_scales()


@router.get("/missions/{mission_id}/risks", response_model=Risks, summary="A mission's risks")
async def list_risks(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await ready_service.risks(session, mission_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/missions/{mission_id}/risks",
    response_model=Risk,
    status_code=201,
    summary="Add a risk (likelihood and consequence per category, never multiplied)",
)
async def add_risk(
    mission_id: str,
    body: RiskIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.save_risk(session, who, mission_id, None, body.model_dump())
    except Exception as exc:
        raise _http(exc) from exc


@router.patch("/risks/{risk_id}", response_model=Risk, summary="Change a risk")
async def patch_risk(
    risk_id: str,
    body: RiskPatch,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.save_risk(
            session, who, None, risk_id, body.model_dump(exclude_unset=True)
        )
    except Exception as exc:
        raise _http(exc) from exc


# --- history of landings, lessons, parameters -------------------------------------------


@router.get(
    "/landing-history",
    response_model=LandingHistory,
    summary="Every lunar landing attempt since 2013 and its cause (counts, no odds)",
)
async def landing_history() -> dict[str, Any]:
    return ready_service.landing_history()


@router.get("/lessons", response_model=Lessons, summary="Lessons from past landings")
async def lessons(
    mission: str | None = Query(None, description="Mark which lessons this mission adopted."),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        return await ready_service.lessons(session, mission)
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/missions/{mission_id}/lessons/{lesson_id}/adopt",
    response_model=Adopted,
    summary="Adopt a lesson as a readiness checklist item",
)
async def adopt(
    mission_id: str,
    lesson_id: str,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await ready_service.adopt_lesson(session, who, mission_id, lesson_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.get("/parameters", response_model=Parameters, summary="Values the project sets")
async def parameters(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await parameters_service.list_parameters(session)


@router.put("/parameters/{parameter_id}", response_model=Parameters, summary="Set a value")
async def set_parameter(
    body: ParameterIn,
    parameter_id: str = Path(),
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await parameters_service.set_parameter(
            session, who, parameter_id, body.value, body.note
        )
    except Exception as exc:
        raise _http(exc) from exc
