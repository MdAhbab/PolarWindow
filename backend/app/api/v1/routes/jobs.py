"""Jobs and data sources: poll a heavy answer; see and refresh the live feeds."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path

from app.api.v1 import deps
from app.api.v1.schemas.jobs import FeedsOut, JobRefOut, RefreshOut
from app.services import auth_service, feed_service, job_service

router = APIRouter(tags=["jobs and data sources"])


@router.get("/jobs/{job_id}", response_model=JobRefOut, summary="Where a heavy answer has got to")
async def get_job(job_id: int = Path(ge=1), session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await job_service.get_job(session, job_id)
    except job_service.JobNotFound as exc:
        raise deps.problem(
            404,
            "job-not-found",
            "No such job",
            f"There is no job {job_id}.",
            "Opening the section again starts a new one if it is needed.",
        ) from exc


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobRefOut,
    summary="Work out a failed answer again",
)
async def retry_job(
    job_id: int = Path(ge=1),
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await job_service.retry(session, job_id, who.user_id)
    except job_service.JobNotFound as exc:
        raise deps.problem(
            404,
            "job-not-found",
            "No such job",
            f"There is no job {job_id}.",
            "Opening the section again starts a new one if it is needed.",
        ) from exc


@router.get("/feeds", response_model=FeedsOut, summary="Every live data source and its age")
async def list_feeds(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await feed_service.list_feeds(session)


@router.post(
    "/feeds/{provider}/refresh",
    response_model=RefreshOut,
    summary="Ask the feeds worker to fetch a provider's products now",
)
async def refresh(
    provider: str,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        n = await feed_service.request_refresh(session, provider, who)
    except feed_service.UnknownProvider as exc:
        raise deps.problem(
            404,
            "feed-not-found",
            "No such data source",
            f"'{provider}' is not a data source.",
            "Every other data source is unaffected.",
        ) from exc
    return {
        "provider": provider,
        "products": n,
        "message": f"Asked for {n} products to be fetched now. The feeds worker does it within "
        "a minute if it is running.",
    }
