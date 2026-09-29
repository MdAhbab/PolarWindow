"""The relays a Contact comparison can add: what ``?relay=`` takes (T1, F4).

The catalogue is a small read-only file, so this answers at once and needs no job or session.
Which relay is *planned for a mission* is in the mission's own contact answer
(``relays[].for_this_mission``); this lists what could be added to any of them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.v1.schemas.contact import RelayCatalogue
from app.services import contact_service

router = APIRouter(tags=["mission sections"])


@router.get(
    "/relays",
    response_model=RelayCatalogue,
    summary="The relays in the catalogue, to compare on a mission's Contact answer",
)
async def relays() -> Any:
    return contact_service.relay_catalogue()
