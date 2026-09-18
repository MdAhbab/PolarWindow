"""POST /compare — ranked comparison over one shared window."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.compare import CompareRequest, CompareResponse
from app.config import Settings
from app.services import compare_service

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CompareResponse, summary="Rank sites over one window")
async def post_compare(
    body: CompareRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    from datetime import UTC, timedelta

    start = body.start or s.reference_window_start
    end = body.end or (start + timedelta(days=s.reference_window_days))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    try:
        return await compare_service.compare(
            session, body.site_ids, start, end, body.step_s or s.default_step_s, body.rank_by
        )
    except compare_service.TooManySites as exc:
        raise deps.problem(
            422,
            "too-many-sites",
            "Too many sites to compare",
            str(exc),
            "Comparing up to eight sites at once works.",
        ) from exc
    except compare_service.UnknownMetric as exc:
        raise deps.problem(
            422,
            "unknown-metric",
            "Unknown ranking metric",
            str(exc),
            "The four key metrics can each be ranked on.",
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc
