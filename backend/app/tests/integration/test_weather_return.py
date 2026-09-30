"""Launch weather per opportunity (T4 B1/B3), its entries, and Return (B2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert, text

from app.db.models import FeedSnapshot, OfficialForecast, ReturnLimits, VehicleLimit
from app.db.session import session_scope

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]
API = "/api/v1"
T0 = (datetime.now(UTC) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)


def _member(u80: float) -> dict[str, float]:
    return {"u10_m_s": u80 * 0.8, "v10_m_s": 0.0, "u80_m_s": u80, "v80_m_s": 0.0}


async def _snap(provider: str, product: str, key: str, parsed: dict) -> None:
    async with session_scope() as s:
        await s.execute(
            insert(FeedSnapshot).values(
                provider=provider,
                product=product,
                location_key=key,
                issued_at=datetime.now(UTC),
                fetched_at=datetime.now(UTC),
                url=f"https://example.test/{provider}/{product}",
                http_status=200,
                parsed=parsed,
                parser_version="test",
                licence="test",
                status="ok",
                issues=[],
            )
        )


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        await s.execute(delete(FeedSnapshot))
        await s.execute(delete(OfficialForecast))
        await s.execute(delete(VehicleLimit))
        await s.execute(delete(ReturnLimits))
        for t in ("jobs", "assessment_inputs", "assessments"):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


async def test_a_flown_launch_shows_its_rules_and_why_no_forecast(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/im-2/launch/weather?opportunity=ksc-lc-39a-flown")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["t0"].startswith("2025-02-27T00:16") and d["lead_time_h"] < 0
    rows = {x["id"]: x for x in d["rules"]}
    wind = rows["f9-wind-162ft"]
    assert (
        wind["class"] == "model" and wind["limit"]["value"] == 30 and wind["limit"]["unit"] == "mph"
    )
    assert wind["limit"]["provenance"] == "published"
    gefs = wind["per_system"][0]
    assert gefs["system"] == "GEFS" and gefs["share"] is None and "past" in gefs["missing_reason"]
    assert rows["er-lightning"]["observed"]["state"] == "no_data"
    shear = rows["f9-upper-wind-shear"]
    assert shear["limit"]["value"] is None and shear["units"] == []
    assert "any unit" in shear["limit"]["missing_reason"]
    assert "not known" in d["range_note"] or "Launch Library" in d["range_note"]
    assert "HTTP" not in d["range_note"] and "make " not in d["range_note"]


async def test_ensemble_share_and_one_forecast_at_a_launch_time(anon_client) -> None:
    valid = (T0 + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    members = {str(i): _member(20.0 if i < 10 else 3.0) for i in range(31)}
    await _snap(
        "nomads",
        "gefs_launch",
        "florida",
        {
            "model": "GEFS",
            "points": {"ksc-lc-39a": {"leads": {"48": {"valid": valid, "members": members}}}},
        },
    )
    await _snap(
        "nomads",
        "hrrr",
        "florida",
        {
            "model": "HRRR",
            "points": {
                "ksc-lc-39a": {"leads": {"18": {"valid": valid, "members": {"0": _member(20.0)}}}}
            },
        },
    )
    hours = [(T0 + timedelta(hours=h)).isoformat().replace("+00:00", "Z") for h in (-1, 0, 1)]
    await _snap("nws", "grid", "ksc-lc-39a", {"times": hours, "p_thunder_frac": [0.0, 0.3, 0.0]})
    r = await anon_client.get(
        f"{API}/missions/im-2/launch/weather",
        params={"t0": T0.isoformat(), "pad": "ksc-lc-39a"},
    )
    assert r.status_code == 200, r.text
    rows = {x["id"]: x for x in r.json()["data"]["rules"]}
    share = rows["f9-wind-162ft"]["per_system"][0]["share"]
    from app.data import verification

    checked = verification.checked("florida", "f9-wind-162ft")  # make hindcast-weather
    assert (share["k"], share["n"], share["checked"]) == (10, 31, checked)
    assert share["lo"] < 10 / 31 < share["hi"]
    (hrrr,) = rows["f9-wind-162ft"]["one_forecast"]
    assert hrrr["system"] == "HRRR" and hrrr["over"] is True and hrrr["value"]["unit"] == "mph"
    assert "30% chance of thunder" in rows["er-lightning"]["observed"]["detail"]
    from app.data import climatology

    clim = rows["f9-wind-162ft"]["climatology"]
    if climatology.load("florida") is not None:  # built by make climatology
        assert 0.0 <= clim["share"] <= 0.2 and clim["years"] == "2001-2024"
        assert "50 m" in clim["source"] and f"{T0.hour:02d} UTC" in clim["source"]
    from app.data import thunder_climatology

    thunder = rows["er-lightning"]["climatology"]
    if thunder_climatology.load("florida") is not None:  # built by make thunder-climatology
        assert 0.0 <= thunder["share"] <= 1.0 and thunder["years"] == "2019-2025"
    else:
        assert thunder is None
    assert rows["er-attached-anvil"]["climatology"] is None
    assert [p["system"] for p in rows["f9-wind-162ft"]["per_system"]] == [
        "GEFS",
        "ECMWF-ENS",
        "AIFS-ENS",
    ]


async def test_bad_requests_are_refused(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/im-2/launch/weather")
    assert r.status_code == 422
    r = await anon_client.get(f"{API}/missions/im-2/launch/weather?opportunity=nonsense")
    assert r.status_code == 422


async def test_entries_are_recorded_and_show_up(client) -> None:
    body = {
        "probability_pct": 80,
        "concerns": ["Cumulus Cloud Rule"],
        "pdf_url": "https://example.test/l1.pdf",
    }
    r = await client.put(f"{API}/missions/griffin-1/launch/official-forecast", json=body)
    assert r.status_code == 200, r.text
    put = r.json()
    lim = {
        "limits": [
            {"rule_id": "f9-wind-162ft", "value": 25, "unit": "kt", "note": "from the provider"}
        ]
    }
    r = await client.put(f"{API}/vehicles/falcon-heavy/limits", json=lim)
    assert r.status_code == 200, r.text
    assert r.json()["limits"][0]["entered_by"].startswith("Test manager")
    bad = {"limits": [{"rule_id": "f9-wind-162ft", "value": 25, "unit": "ft"}]}
    assert (await client.put(f"{API}/vehicles/falcon-heavy/limits", json=bad)).status_code == 422
    r = await client.get(
        f"{API}/missions/griffin-1/launch/weather",
        params={"t0": T0.isoformat(), "pad": "ksc-lc-39a"},
    )
    d = r.json()["data"]
    assert d["official"]["probability_pct"] == 80
    # The stored row's id and time, the same in both answers.
    assert d["official"]["id"] == put["id"] and d["official"]["entered_at"] == put["entered_at"]
    assert "space_weather_now" not in d
    wind = next(x for x in d["rules"] if x["id"] == "f9-wind-162ft")
    assert wind["limit"]["provenance"] == "entered" and wind["limit"]["unit"] == "kt"
    assert wind["limit_note"] == "from the provider"
    assert wind["units"][0] == "mph" and set(wind["units"]) == {"mph", "kt", "m/s", "km/h"}
    got = (await client.get(f"{API}/vehicles/falcon-heavy/limits")).json()
    assert got["limits"][0]["note"] == "from the provider"
    miss = await client.get(f"{API}/vehicles/no-such-rocket/limits")
    assert miss.status_code == 404 and miss.json()["detail"]["type"].endswith("/vehicle-not-found")
    h = await client.get(f"{API}/history", params={"entity": "limits", "id": "falcon-heavy"})
    assert h.status_code == 200 and h.json()["entries"]


async def test_an_entered_forecast_can_be_taken_back(client) -> None:
    url = f"{API}/missions/griffin-1/launch/official-forecast"
    assert (await client.delete(url)).status_code == 404
    first = {"probability_pct": 60, "concerns": [], "pdf_url": "https://example.test/a.pdf"}
    second = {"probability_pct": 90, "concerns": [], "pdf_url": "https://example.test/b.pdf"}
    assert (await client.put(url, json=first)).status_code == 200
    assert (await client.put(url, json=second)).status_code == 200
    r = await client.delete(url)
    assert r.status_code == 200, r.text
    assert r.json()["official"]["probability_pct"] == 60
    r = await client.delete(url)
    assert r.json()["official"] is None
    h = await client.get(f"{API}/history", params={"entity": "forecast", "id": "griffin-1"})
    actions = [e.get("action") for e in h.json()["entries"]]
    assert actions.count("delete") >= 2  # the audit log is kept between runs


async def test_return_for_flown_and_planned_missions(client, anon_client) -> None:
    d = (await anon_client.get(f"{API}/missions/im-1/return")).json()["data"]
    assert d["booster"]["landing"] == "land" and d["booster"]["zone"]["lat_deg"] == pytest.approx(
        28.4857, abs=1e-3
    )
    assert d["booster"]["wave_height_m"] is None
    assert d["booster"]["wind_m_s"]["provenance"] == "computed"
    assert d["capsule"]["applicable"] is False
    check = d["capsule"]["model_check"]
    # Whether the plan's 10 km is met is what the check says, not a given: it depends on the
    # air the model flies through (docs/validation.md, capsule entry).
    assert check["limit_km"] == 10.0
    assert check["passed"] == (check["distance_km"] <= check["limit_km"])
    assert "NRLMSIS 2.1" in check["atmosphere"] and "'" not in check["atmosphere"]
    assert "OSIRIS-REx" in check["note"] and "'" not in check["note"]
    r = (await anon_client.get(f"{API}/missions/im-2/return")).json()
    d = r["data"]
    assert d["booster"]["landing"] == "droneship" and d["booster"]["zone"] is None
    assert "700 km" in d["booster"]["note"]
    assert "Launch Library" not in d["booster"]["note"] and "'" not in d["booster"]["note"]
    assert r["meta"]["sources"][0]["name"] == "Launch Library 2 landing records"
    assert r["meta"]["sources"][0]["fetched_at"]  # the date the record was read
    # As old as its newest input (the catalogue), not the request.
    at = datetime.fromisoformat(r["meta"]["computed_at"].replace("Z", "+00:00"))
    assert at < datetime.now(UTC) - timedelta(minutes=1)
    d = (await anon_client.get(f"{API}/missions/griffin-1/return")).json()["data"]
    assert d["booster"]["landing"] == "unknown" and "IM-1" in d["booster"]["note"]
    assert d["booster"]["limits"]["wave_height_m"]["missing_reason"]
    r = await client.put(
        f"{API}/missions/griffin-1/return/limits",
        json={"booster": {"wave_height_m": 2.5, "wind_m_s": None}},
    )
    assert r.status_code == 200, r.text
    lim = r.json()["data"]["booster"]["limits"]
    assert lim["wave_height_m"]["value"] == 2.5 and lim["wave_height_m"]["provenance"] == "entered"
    assert lim["wind_m_s"]["value"] is None
    bad = await client.put(
        f"{API}/missions/griffin-1/return/limits", json={"booster": {"wave_height_m": -1}}
    )
    assert bad.status_code == 422
    d = (await anon_client.get(f"{API}/missions/blue-ghost-m3/return")).json()["data"]
    assert d["booster"] is None


async def test_entries_need_a_signed_in_name(anon_client) -> None:
    body = {"probability_pct": 80, "concerns": [], "pdf_url": "https://example.test/l1.pdf"}
    r = await anon_client.put(f"{API}/missions/griffin-1/launch/official-forecast", json=body)
    assert r.status_code in (401, 403)
    r = await anon_client.put(f"{API}/missions/griffin-1/return/limits", json={})
    assert r.status_code in (401, 403)


async def test_lightning_seen_from_space_in_the_hours_before_a_launch(anon_client) -> None:
    now = datetime.now(UTC).replace(microsecond=0)

    def iso(t: datetime) -> str:
        return t.isoformat().replace("+00:00", "Z")

    await _snap(
        "goes",
        "glm",
        "florida",
        {
            "satellite": "G19",
            "start": iso(now - timedelta(minutes=30)),
            "end": iso(now),
            "pads": {
                "ksc-lc-39a": {
                    "counts": {"5": 0, "10": 1, "20": 2},
                    "nearest_km": 12.0,
                    "flashes": [
                        {"km": 12.0, "t": iso(now - timedelta(minutes=4))},
                        {"km": 30.0, "t": iso(now - timedelta(minutes=2))},
                    ],
                }
            },
        },
    )
    soon = now + timedelta(hours=2)
    r = await anon_client.get(
        f"{API}/missions/im-2/launch/weather", params={"t0": soon.isoformat(), "pad": "ksc-lc-39a"}
    )
    obs = {x["id"]: x for x in r.json()["data"]["rules"]}["er-lightning"]["observed"]
    assert obs["state"] == "seen" and obs["detail"].startswith("1 flash within 10 nmi")
    assert "not at the launch time" in obs["detail"]
    # Two days ahead the half hour just gone says nothing about the launch.
    r = await anon_client.get(
        f"{API}/missions/im-2/launch/weather", params={"t0": T0.isoformat(), "pad": "ksc-lc-39a"}
    )
    obs = {x["id"]: x for x in r.json()["data"]["rules"]}["er-lightning"]["observed"]
    assert obs["state"] == "no_data" and "six hours" in obs["detail"]


async def test_lightning_rules_say_how_often_thunder_was_heard_at_the_pad(
    anon_client, monkeypatch
) -> None:
    from app.data import thunder_climatology as tc

    when = (T0 + timedelta(days=40)).replace(hour=20)
    counts = {"ksc-lc-39a": {f"{when.month:02d}": {"20": [210, 42]}}}
    cl = tc.ThunderClimatology(region="florida", years="2019-2025", source_url="u", counts=counts)
    monkeypatch.setattr(tc, "load", lambda region: cl if region == "florida" else None)
    r = await anon_client.get(
        f"{API}/missions/im-2/launch/weather", params={"t0": when.isoformat(), "pad": "ksc-lc-39a"}
    )
    body = r.json()
    rows = {x["id"]: x for x in body["data"]["rules"]}
    got = rows["er-lightning"]["climatology"]
    assert got["share"] == pytest.approx(0.2) and got["years"] == "2019-2025"
    assert "42 of the 210 hours" in got["source"]
    assert any("Thunder Hour" in s["name"] for s in body["meta"]["sources"])


async def test_space_weather_now_says_what_is_recorded_and_what_is_not(anon_client) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    await _snap("swpc", "kp", "", {"latest": {"t": now, "kp": 4.33}, "series": []})
    await _snap(
        "swpc",
        "goes_protons",
        "",
        {"latest": {">=10 MeV": {"t": now, "pfu": 0.4}, ">=100 MeV": {"t": now, "pfu": 0.1}}},
    )
    await _snap(
        "donki",
        "flr",
        "",
        {
            "count": 1,
            "days": 30,
            "events": [{"id": "f1", "peak": now, "class": "X1.1", "link": "l"}],
        },
    )
    r = await anon_client.get(f"{API}/space-weather")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["now"]["kp"]["value"] == 4.33 and d["now"]["kp"]["provenance"] == "published"
    assert d["now"]["proton_10mev_pfu"]["value"] == 0.4
    assert d["now"]["bz_nt"]["value"] is None and d["now"]["bz_nt"]["missing_reason"]
    assert d["donki"]["flares"][0]["class"] == "X1.1"
    assert d["donki"]["counts"] == {"cme": None, "flares": 1, "sep": None}
    # Not recorded: said, so an empty list does not read as a quiet Sun.
    assert d["now"]["xray_class"] is None and d["now"]["xray_missing_reason"]
    assert d["now"]["alerts"] == [] and d["now"]["alerts_missing_reason"]
    assert d["outlook"]["text"] is None and d["outlook"]["missing_reason"]
    await _snap("swpc", "alerts", "", {"alerts": []})
    await _snap("swpc", "goes_xrays", "", {"latest": {"t": now, "class": "C1.2"}})
    d = (await anon_client.get(f"{API}/space-weather")).json()["data"]
    assert d["now"]["alerts"] == [] and d["now"]["alerts_missing_reason"] is None
    assert d["now"]["xray_class"] == "C1.2" and d["now"]["xray_missing_reason"] is None
    assert r.json()["meta"]["engines"] == {"rad": "rad-3"}
