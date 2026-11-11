"""Projects the team enters, and files read into the project form.

Reading is public, like every mission. Saving, changing, deleting and reading a
file need a named session (ADR-17) and are written to the change history. A
catalogue record cannot be changed or deleted here (409).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.exceptions import HTTPException

from app.api.v1 import deps
from app.api.v1.schemas.missions import MissionDetail
from app.api.v1.schemas.projects import (
    Intake,
    ProjectDeleted,
    ProjectIn,
    ProjectList,
    ProjectOptions,
    ProjectSaved,
)
from app.services import auth_service, intake_service, project_service
from app.services.mission_service import MissionNotFound

router = APIRouter(prefix="/projects", tags=["projects"])

Named = auth_service.Claims
ProjectId = Annotated[str, Path(max_length=64, description="Project id, e.g. `p-athena-2`.")]


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, MissionNotFound):
        return deps.problem(
            404,
            "project-not-found",
            "That project isn't in the list",
            f"'{exc.args[0]}' is not a mission or project in this dataset.",
            "Every other project and mission is unaffected.",
            action="Back to missions",
        )
    if isinstance(exc, project_service.NotAProject):
        return deps.problem(
            409,
            "not-a-project",
            "This is a published mission, not a project",
            f"'{exc.args[0]}' is a CLPS record compiled from published sources; only "
            "projects the team entered can be changed or deleted here.",
            "The mission is unchanged and can still be read.",
        )
    if isinstance(exc, project_service.BadProject):
        return deps.problem(
            422,
            "bad-project",
            "That project cannot be saved",
            str(exc),
            "Nothing was saved. Correcting the field will work.",
            action="Correct the entry",
            errors=exc.errors,
        )
    if isinstance(exc, intake_service.BadFile):
        return deps.problem(
            415 if "not a kind of file" in str(exc) else 422,
            "unreadable-file",
            "That file cannot be read",
            str(exc),
            "Nothing was saved. The form can still be filled in by hand.",
            action="Fill in the form, or try a PDF, DOCX, TXT, MD, CSV or JSON file",
        )
    return deps.to_http(exc)


@router.get("/options", response_model=ProjectOptions, summary="Choices for the project form")
async def options(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await project_service.options(session)


@router.get("", response_model=ProjectList, summary="The team's projects, newest first")
async def list_projects(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await project_service.list_projects(session)


@router.post(
    "/intake",
    response_model=Intake,
    summary="Read a file into the project form (the body is the file's bytes)",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def intake(
    request: Request,
    filename: str = Query(min_length=1, max_length=255, description="The file's name."),
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    """The draft is not saved as a project: the form arrives filled, and Save saves it."""
    data = await request.body()
    try:
        return await intake_service.read_file(
            session, who, data, filename, request.headers.get("content-type")
        )
    except Exception as exc:
        raise _http(exc) from exc


@router.post("", response_model=ProjectSaved, status_code=201, summary="Save a new project")
async def create(
    body: ProjectIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await project_service.create(session, who, body.model_dump(mode="json"))
    except Exception as exc:
        raise _http(exc) from exc


@router.get("/{project_id}", response_model=MissionDetail, summary="One project, as a mission")
async def get_project(project_id: ProjectId, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await project_service.get(session, project_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.put("/{project_id}", response_model=ProjectSaved, summary="Change a project")
async def update(
    project_id: ProjectId,
    body: ProjectIn,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await project_service.update(session, who, project_id, body.model_dump(mode="json"))
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/{project_id}/skyline",
    response_model=ProjectSaved,
    summary="Build the target's skyline again (after a failed build)",
)
async def rebuild_skyline(
    project_id: ProjectId,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await project_service.rebuild_skyline(session, who, project_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.delete(
    "/{project_id}",
    response_model=ProjectDeleted,
    summary="Delete a project (a published mission is refused)",
)
async def delete(
    project_id: ProjectId,
    session: Any = Depends(deps.db),
    who: Named = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await project_service.delete(session, who, project_id)
    except Exception as exc:
        raise _http(exc) from exc
