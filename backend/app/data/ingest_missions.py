"""Load the cited CLPS mission list and give each target a site (ADR-5, ADR-6).

``data/missions.json`` is curated by hand from NASA pages, LROC images and the
IAU Gazetteer (``docs/data-sources.md``). This module is the gate between that
file and the database:

* **Validation is total.** A record with no source, a payload with no source
  URL, a null field not listed in ``unconfirmed_fields``, an unknown status or
  instrument type, or a coordinate out of range fails the whole load, naming
  the record and field. Nothing partial is ever written.
* **Targets become sites.** A published landing point becomes its own site,
  ``mission-<id>``. The centre of a named feature, used when no landing point
  is published, becomes one shared site, ``feature-<slug>``, because three
  missions aimed at "Mons Mouton" have one coordinate and so one skyline.
  Inside the 80-90 deg S elevation model the site gets real terrain; outside
  it the site is flagged ``terrain_modelled = false`` and later gets a
  smooth-sphere skyline.

Coordinates are used exactly as published. The open-sky search in
``ingest_sites`` exists to turn a crater name into a landable point; a mission
already has a point, and moving it would make it a different mission.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

log = logging.getLogger("ingest_missions")

#: The polar elevation model's northern edge. Targets at or south of it get
#: terrain; everything else gets a flagged smooth-sphere skyline.
POLAR_DEM_EDGE_LAT_DEG = -80.0

Status = Literal[
    "planned",
    "in_transit",
    "operating",
    "completed",
    "partial_success",
    "landing_failed",
    "lost_before_landing",
    "cancelled",
    "reassigned",
]
InstrumentType = Literal[
    "volatiles",
    "geology_geophysics",
    "heat_flow",
    "radiation_space_weather",
    "exosphere_dust",
    "imaging",
    "landing_navigation",
    "communications",
    "laser_retroreflector",
    "rover_mobility",
    "technology_demo",
    "other",
]
Precision = Literal["minute", "day", "month", "quarter", "year"]
Region = Literal["south_polar", "nearside", "farside", "polar_other"]
CoordinateKind = Literal["actual_landing", "planned_target", "feature_centre"]

#: Top-level fields that may be null, and must then be listed as unconfirmed.
NULLABLE_FIELDS: tuple[str, ...] = (
    "vehicle_name",
    "task_order",
    "provider",
    "lander",
    "region",
    "target",
    "target_name",
    "ellipse",
    "launch",
    "landing",
    "end_of_mission",
    "planned_surface_days",
)
#: Schema v2 (ADR-10): the lifecycle facts. Each is null and listed, or
#: carries its own source in ``field_sources``.
NULLABLE_FIELDS_V2: tuple[str, ...] = (
    "vehicle_id",
    "pad_id",
    "t0",
    "transfer",
    "descent",
    "comms",
    "spacecraft",
    "returns",
)
#: Sub-fields of the v2 objects that may be null, listed as "transfer.flight_days".
NESTED_NULLABLE: dict[str, tuple[str, ...]] = {
    "transfer": ("flight_days", "lunar_orbit_days"),
    "descent": ("sun_el_min_deg", "sun_el_max_deg", "earth_required"),
    "comms": ("eirp_dbw", "gt_dbk"),
    "spacecraft": ("mass_kg", "area_m2", "cr"),
}
#: "payloads" may also be listed: it means NASA counts more than it names;
#: "rovers" likewise.
UNCONFIRMABLE = (
    frozenset(NULLABLE_FIELDS)
    | frozenset(NULLABLE_FIELDS_V2)
    | {"payloads", "rovers"}
    | {f"{k}.{f}" for k, fs in NESTED_NULLABLE.items() for f in fs}
)


class MissionDataError(ValueError):
    """The mission file is not fit to load. The message names record and field."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceIn(_Strict):
    url: str = Field(pattern=r"^https://\S+$")
    title: str = Field(min_length=3)
    publisher: str = Field(min_length=2)
    accessed: date


class DateIn(_Strict):
    date: str
    precision: Precision
    as_published: str = Field(min_length=1)

    @model_validator(mode="after")
    def _parses(self) -> DateIn:
        parse_date(self.date)
        return self


class InstantIn(DateIn):
    """A published launch instant (T-0) and the launch window it was published with."""

    #: The window's ends (UTC); equal when the launch was published as a single instant.
    #: Absent when no window was published.
    window_open: str | None = None
    window_close: str | None = None

    @model_validator(mode="after")
    def _inside(self) -> InstantIn:
        if (self.window_open is None) != (self.window_close is None):
            raise ValueError("a launch window has both ends or neither")
        if self.window_open is not None and self.window_close is not None:
            a, t, b = (parse_date(x) for x in (self.window_open, self.date, self.window_close))
            if not a <= t <= b:
                raise ValueError("the launch instant lies outside its published window")
        return self


class TargetIn(_Strict):
    name: str
    lat_deg: float = Field(ge=-90.0, le=90.0)
    lon_deg: float = Field(ge=0.0, lt=360.0)
    coordinate_kind: CoordinateKind
    source_url: str = Field(pattern=r"^https://\S+$")
    feature_id: int | None = None


class EllipseIn(_Strict):
    semi_major_km: float = Field(gt=0)
    semi_minor_km: float = Field(gt=0)
    azimuth_deg: float = Field(ge=0, lt=180)
    source_url: str = Field(pattern=r"^https://\S+$")


class TransferIn(_Strict):
    type: Literal["direct", "phasing_loops", "low_energy", "unknown"]
    flight_days: float | None = Field(default=None, gt=0)
    lunar_orbit_days: float | None = Field(default=None, ge=0)


class DescentIn(_Strict):
    sun_el_min_deg: float | None = Field(default=None, ge=-5, le=90)
    sun_el_max_deg: float | None = Field(default=None, ge=-5, le=90)
    earth_required: bool | None = None


class CommsIn(_Strict):
    bands: list[str] = Field(default_factory=list)
    eirp_dbw: float | None = None
    gt_dbk: float | None = None
    ground_stations: list[str] = Field(default_factory=list)
    relays: list[str] = Field(default_factory=list)


class SpacecraftIn(_Strict):
    mass_kg: float | None = Field(default=None, gt=0)
    area_m2: float | None = Field(default=None, gt=0)
    cr: float | None = Field(default=None, ge=1.0, le=2.0)


class RoverIn(_Strict):
    id: str = Field(pattern=r"^[a-z0-9-]+/[a-z0-9-]+$")
    name: str
    organisation: str | None
    source_url: str = Field(pattern=r"^https://\S+$")


class PayloadIn(_Strict):
    id: str = Field(pattern=r"^[a-z0-9-]+/[a-z0-9-]+$")
    name: str
    acronym: str | None
    organisation: str | None
    instrument_types: list[InstrumentType] = Field(min_length=1)
    purpose: str = Field(min_length=5)
    source_url: str = Field(pattern=r"^https://\S+$")
    unconfirmed: bool = False


class MissionIn(_Strict):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    vehicle_name: str | None
    task_order: str | None
    provider: str | None
    lander: str | None
    status: Status
    outcome_note: str
    region: Region | None
    target_name: str | None
    target: TargetIn | None
    ellipse: EllipseIn | None
    launch: DateIn | None
    landing: DateIn | None
    end_of_mission: DateIn | None
    planned_surface_days: float | None = Field(default=None, gt=0)
    payloads: list[PayloadIn]
    sources: list[SourceIn] = Field(min_length=1)
    unconfirmed_fields: list[str]
    notes: list[str] = Field(default_factory=list)
    # --- schema v2 (ADR-10) ---------------------------------------------------
    vehicle_id: str | None = None
    pad_id: str | None = None
    #: The published launch instant (T-0), to the minute or better.
    t0: InstantIn | None = None
    transfer: TransferIn | None = None
    descent: DescentIn | None = None
    comms: CommsIn | None = None
    spacecraft: SpacecraftIn | None = None
    rovers: list[RoverIn] = Field(default_factory=list)
    returns: Literal["none", "sample_capsule", "crew"] | None = None
    #: v2 field -> the URL that states it (one of ``sources``).
    field_sources: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _honest(self) -> MissionIn:
        unconfirmed = set(self.unconfirmed_fields)
        unknown = unconfirmed - UNCONFIRMABLE
        if unknown:
            raise ValueError(
                f"unconfirmed_fields names fields that do not exist: {sorted(unknown)}"
            )
        for name in NULLABLE_FIELDS:
            value = getattr(self, name)
            if value is None and name not in unconfirmed:
                raise ValueError(f"'{name}' is null but not listed in unconfirmed_fields")
            if value is not None and name in unconfirmed:
                raise ValueError(f"'{name}' has a value but is listed as unconfirmed")
        for name in NULLABLE_FIELDS_V2:
            value = getattr(self, name)
            if value is None and name not in unconfirmed:
                raise ValueError(f"'{name}' is null but not listed in unconfirmed_fields")
            if value is not None and name in unconfirmed:
                raise ValueError(f"'{name}' has a value but is listed as unconfirmed")
            if value is not None and name not in self.field_sources:
                raise ValueError(f"'{name}' has a value but no entry in field_sources")
            if value is not None and name in NESTED_NULLABLE:
                for sub in NESTED_NULLABLE[name]:
                    dotted = f"{name}.{sub}"
                    if getattr(value, sub) is None and dotted not in unconfirmed:
                        raise ValueError(f"'{dotted}' is null but not listed in unconfirmed_fields")
                    if getattr(value, sub) is not None and dotted in unconfirmed:
                        raise ValueError(f"'{dotted}' has a value but is listed as unconfirmed")
        if self.t0 is not None and self.t0.precision != "minute":
            raise ValueError("t0 is a launch instant: its precision must be 'minute'")
        if self.rovers and "rovers" not in self.field_sources:
            raise ValueError("'rovers' has entries but no entry in field_sources")
        urls = {s.url for s in self.sources}
        for f, url in self.field_sources.items():
            if f not in (*NULLABLE_FIELDS_V2, "rovers"):
                raise ValueError(f"field_sources names '{f}', which is not a v2 field")
            if url not in urls:
                raise ValueError(f"field_sources['{f}'] is not one of the mission's sources")
        ids = [p.id for p in self.payloads]
        if len(ids) != len(set(ids)):
            raise ValueError("payload ids are not unique")
        for pid in ids:
            if not pid.startswith(self.id + "/"):
                raise ValueError(f"payload id {pid!r} is not prefixed with the mission id")
        return self


class MissionFile(_Strict):
    schema_version: Literal[1, 2]
    compiled: date
    about: str
    missions: list[MissionIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> MissionFile:
        ids = [m.id for m in self.missions]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate mission ids: {dupes}")
        return self


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_date(text: str) -> datetime:
    """An ISO date or datetime as an aware UTC datetime (a date is its midnight)."""
    t = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(t) if "T" in t else datetime.fromisoformat(t + "T00:00:00+00:00")
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def load(path: Path) -> MissionFile:
    """Parse and validate the whole file, or raise one readable error."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MissionDataError(f"cannot read {path}: {exc}") from exc
    try:
        mf = MissionFile.model_validate(raw)
    except ValidationError as exc:
        lines = []
        for err in exc.errors():
            loc = list(err["loc"])
            where = "file"
            if len(loc) >= 2 and loc[0] == "missions" and isinstance(loc[1], int):
                mid = raw["missions"][loc[1]].get("id", f"#{loc[1]}")
                where = f"mission '{mid}'" + (
                    f" field {'.'.join(map(str, loc[2:]))}" if loc[2:] else ""
                )
            lines.append(f"  {where}: {err['msg']}")
        raise MissionDataError(
            f"{path} failed validation; nothing was loaded:\n" + "\n".join(lines)
        ) from exc
    bad = catalogue_problems(mf)
    if bad:
        raise MissionDataError(
            f"{path} names catalogue records that do not exist; nothing was loaded:\n"
            + "\n".join(f"  {b}" for b in bad)
        )
    return mf


def catalogue_problems(mf: MissionFile) -> list[str]:
    """v2 references to pads, vehicles, stations and relays that the catalogues lack."""
    from app.data import catalogues

    out: list[str] = []
    ids: dict[str, set[str] | None] = {}
    for name in ("vehicles", "launch_sites", "ground_stations", "relays"):
        try:
            ids[name] = set(catalogues.load(name).ids())
        except catalogues.CatalogueError:
            ids[name] = None
    for m in mf.missions:
        checks: list[tuple[str, str]] = []
        if m.vehicle_id:
            checks.append(("vehicles", m.vehicle_id))
        if m.pad_id:
            checks.append(("launch_sites", m.pad_id))
        if m.comms:
            checks += [("ground_stations", g) for g in m.comms.ground_stations]
            checks += [("relays", r) for r in m.comms.relays]
        for cat, rid in checks:
            known = ids[cat]
            if known is None:
                out.append(f"mission '{m.id}': catalogue {cat} is missing or invalid")
            elif rid not in known:
                out.append(f"mission '{m.id}': no {cat} record '{rid}'")
    return out


def data_version(m: MissionIn) -> str:
    """A content hash of one record, so a changed fact is visible downstream."""
    canonical = json.dumps(m.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def sort_at(m: MissionIn) -> datetime | None:
    """The instant a mission sorts and filters by: landing, else launch."""
    d = m.landing or m.launch
    return parse_date(d.date) if d is not None else None


def _slug(text: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def feature_name(target: TargetIn) -> str:
    """ "Mons Mouton (IAU feature centre)" -> "Mons Mouton"."""
    return re.sub(r"\s*\(IAU [^)]*\)\s*$", "", target.name).strip()


def target_site_id(m: MissionIn) -> str | None:
    if m.target is None:
        return None
    if m.target.coordinate_kind == "feature_centre":
        return f"feature-{_slug(feature_name(m.target))}"
    return f"mission-{m.id}"


#: Short codes the UI draws on a pin. Candidates use A-O; targets use these.
SITE_CODES: dict[str, str] = {
    "mission-im-1": "IM1",
    "mission-im-2": "IM2",
    "mission-blue-ghost-m1": "BG1",
    "mission-peregrine-m1": "PM1",
    "feature-mons-mouton": "MM",
    "feature-reiner-gamma": "RG",
    "feature-schrodinger": "SCH",
    "feature-sinus-viscositatis": "SV",
}


def site_code(site_id: str) -> str:
    if site_id in SITE_CODES:
        return SITE_CODES[site_id]
    tail = site_id.split("-", 1)[-1]
    return re.sub(r"[^A-Z0-9]", "", tail.upper())[:4] or "T"


#: ``(lat, lon) -> (elev_m, slope_deg)`` from an elevation model, or None
#: where the model does not cover the point.
TerrainSampler = Callable[[float, float], tuple[float, float] | None]


def plan_sites(missions: list[MissionIn], terrain: TerrainSampler) -> list[dict[str, Any]]:
    """The site rows the mission targets need, one per distinct target site."""
    rows: dict[str, dict[str, Any]] = {}
    served_by: dict[str, list[str]] = {}
    for m in missions:
        sid = target_site_id(m)
        if sid is None or m.target is None:
            continue
        served_by.setdefault(sid, []).append(m.name)
        if sid in rows:
            continue
        t = m.target
        polar = t.lat_deg <= POLAR_DEM_EDGE_LAT_DEG
        sampled = terrain(t.lat_deg, t.lon_deg) if polar else None
        feature = t.coordinate_kind == "feature_centre"
        where = feature_name(t) if feature else t.name
        if feature:
            source = "IAU Gazetteer of Planetary Nomenclature"
            rule = (
                f"The IAU centre of {where}, used because no landing point is published. "
                "It is not a landing point, and numbers here describe the centre of the "
                "named feature."
            )
        else:
            source = (
                "LROC landing-site image (NASA/GSFC/Arizona State University)"
                if "lroc" in t.source_url
                else "Published target coordinate"
            )
            kind = (
                "where the lander came to rest"
                if t.coordinate_kind == "actual_landing"
                else "the published target"
            )
            rule = f"The coordinate {kind}, as published; used as given, not searched."
        terrain_note = (
            "Height and slope sampled from the 80 m LOLA model at the nearest post."
            if sampled is not None
            else "No elevation model covers this site: height, slope and terrain are not modelled."
        )
        rows[sid] = {
            "id": sid,
            "code": site_code(sid),
            "name": f"{where} (feature centre)" if feature else where,
            "region": m.region or "unknown",
            "lat_deg": round(t.lat_deg, 5),
            "lon_deg": round(t.lon_deg % 360.0, 5),
            "elev_m": None if sampled is None else round(sampled[0], 1),
            "slope_deg": None if sampled is None else round(sampled[1], 2),
            "note": "",
            "anchor_lat_deg": t.lat_deg,
            "anchor_lon_deg": t.lon_deg % 360.0,
            "search_kind": "published",
            "search_inner_km": 0.0,
            "search_outer_km": 0.0,
            "offset_from_anchor_km": 0.0,
            "source": source,
            "source_url": t.source_url,
            "source_note": f"{rule} {terrain_note}",
            "kind": "mission_target",
            "coordinate_rule": "published",
            "terrain_modelled": polar,
        }
    for sid, names in served_by.items():
        rows[sid]["note"] = "CLPS target of " + ", ".join(dict.fromkeys(names)) + "."
    return list(rows.values())


def mission_row(m: MissionIn) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "vehicle_name": m.vehicle_name,
        "task_order": m.task_order,
        "provider": m.provider,
        "lander": m.lander,
        "status": m.status,
        "outcome_note": m.outcome_note,
        "region": m.region,
        "target_name": m.target_name,
        "target": m.target.model_dump(mode="json") if m.target else None,
        "ellipse": m.ellipse.model_dump(mode="json") if m.ellipse else None,
        "launch": m.launch.model_dump(mode="json") if m.launch else None,
        "landing": m.landing.model_dump(mode="json") if m.landing else None,
        "end_of_mission": m.end_of_mission.model_dump(mode="json") if m.end_of_mission else None,
        "planned_surface_days": m.planned_surface_days,
        "sort_at": sort_at(m),
        "site_id": target_site_id(m),
        "sources": [s.model_dump(mode="json") for s in m.sources],
        "unconfirmed_fields": list(m.unconfirmed_fields),
        "notes": list(m.notes),
        "data_version": data_version(m),
        "lifecycle": lifecycle_of(m),
    }


def lifecycle_of(m: MissionIn) -> dict[str, Any]:
    """The v2 facts as stored: every field, with the URL that states it."""
    return {
        "vehicle_id": m.vehicle_id,
        "pad_id": m.pad_id,
        "t0": m.t0.model_dump(mode="json") if m.t0 else None,
        "transfer": m.transfer.model_dump(mode="json") if m.transfer else None,
        "descent": m.descent.model_dump(mode="json") if m.descent else None,
        "comms": m.comms.model_dump(mode="json") if m.comms else None,
        "spacecraft": m.spacecraft.model_dump(mode="json") if m.spacecraft else None,
        "rovers": [r.model_dump(mode="json") for r in m.rovers],
        "returns": m.returns,
        "field_sources": dict(m.field_sources),
    }


def payload_rows(m: MissionIn) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "mission_id": m.id,
            "position": i,
            "name": p.name,
            "acronym": p.acronym,
            "organisation": p.organisation,
            "instrument_types": list(p.instrument_types),
            "purpose": p.purpose,
            "source_url": p.source_url,
            "unconfirmed": p.unconfirmed,
        }
        for i, p in enumerate(m.payloads)
    ]


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def dem_terrain_sampler(tile: Any) -> TerrainSampler:
    """Height and slope at the nearest post of a loaded polar DEM tile."""
    from app.core.projections import geographic_to_polar
    from app.data.ingest_sites import _slope_deg

    def sample(lat: float, lon: float) -> tuple[float, float] | None:
        x, y = geographic_to_polar(np.array([lon]), np.array([lat]))
        c = int(round((float(x[0]) - tile.origin_x_m) / tile.scale_m))
        r = int(round((tile.origin_y_m - float(y[0])) / tile.scale_m))
        h, w = tile.heights.shape
        if not (2 <= r < h - 2 and 2 <= c < w - 2):
            return None
        patch = tile.heights[r - 2 : r + 3, c - 2 : c + 3]
        if not np.isfinite(patch).all():
            return None
        slope = _slope_deg(patch, tile.scale_m)
        return float(patch[2, 2]), float(slope[2, 2])

    return sample


async def ingest(path: Path, terrain: TerrainSampler) -> tuple[int, int]:
    """Validate, then write sites, missions and payloads in one transaction."""
    from app.db.repositories.missions import MissionRepository
    from app.db.repositories.sites import SiteRepository
    from app.db.session import session_scope

    data = load(path)
    sites = plan_sites(data.missions, terrain)
    async with session_scope() as session:
        if sites:
            await SiteRepository(session).upsert_many(sites)
        await MissionRepository(session).replace_all(
            [mission_row(m) for m in data.missions],
            [row for m in data.missions for row in payload_rows(m)],
        )
    return len(data.missions), len(sites)


async def main_async() -> None:
    from app.config import get_settings
    from app.data.lola import DemTile
    from app.db.session import dispose_engine

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = get_settings()
    tile = DemTile.load(s.regional_dem_path)
    try:
        n_missions, n_sites = await ingest(s.missions_path, dem_terrain_sampler(tile))
    finally:
        await dispose_engine()
    log.info("loaded %d missions and %d target sites from %s", n_missions, n_sites, s.missions_path)


def main() -> None:
    import asyncio

    try:
        asyncio.run(main_async())
    except MissionDataError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
