"""The relays a Contact comparison can add: the list the frontend offers, from the catalogue."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

from app.data import catalogues
from app.main import create_app
from app.services import contact_service


def test_only_relay_services_are_listed_never_the_orbiters_kept_for_checking() -> None:
    listed = contact_service.relay_catalogue()["relays"]
    cat = catalogues.load("relays")
    assert [r["id"] for r in listed] == [r.id for r in cat.records if r.role == "relay"]
    assert listed, "the catalogue has relays"
    orbiters = {r.id for r in cat.records if r.role == "validation_only"}
    assert orbiters and not orbiters & {r["id"] for r in listed}


def test_each_relay_is_told_as_the_catalogue_has_it() -> None:
    by_id = {r["id"]: r for r in contact_service.relay_catalogue()["relays"]}
    lp = by_id["lunar-pathfinder"]
    assert lp["status"] == "planned" and lp["orbit_known"] is True
    assert lp["operator"].startswith("ESA") and "Blue Ghost" in lp["launch_note"]
    assert lp["serves_missions"] == ["blue-ghost-m2"]  # in that mission's answer already
    altus = by_id["altus-1"]
    assert altus["serves_missions"] == ["im-3"] and altus["orbit_known"] is True
    assert "assumed" in altus["orbit_note"]


def test_every_relay_listed_is_one_the_answer_accepts() -> None:
    """A choice the list offers must not be refused when it is asked for."""
    listed = [r["id"] for r in contact_service.relay_catalogue()["relays"]]
    mission = cast(Any, type("Mission", (), {"lifecycle": {}})())
    assert contact_service._extra_relays(mission, listed[:3]) == sorted(listed[:3])


def test_a_relay_whose_orbit_is_not_known_is_listed_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cat = catalogues.load("relays")
    lp = cat.get("lunar-pathfinder").model_copy(update={"arg_periapsis_deg": None})
    thin = cat.model_copy(update={"records": (lp,)})
    monkeypatch.setattr(catalogues, "load", lambda name: thin)
    (row,) = contact_service.relay_catalogue()["relays"]
    assert row["id"] == "lunar-pathfinder" and row["orbit_known"] is False


async def test_the_route_answers_at_once_with_no_session() -> None:
    """The list is the catalogue's own: no job, no database, no sign-in."""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/relays")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == contact_service.relay_catalogue()
    assert {"lunar-pathfinder", "altus-1"} <= {x["id"] for x in body["relays"]}
    assert set(body["relays"][0]) == {
        "id",
        "name",
        "operator",
        "status",
        "launch_note",
        "orbit_known",
        "orbit_note",
        "serves_missions",
    }
