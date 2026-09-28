"""Cited catalogues (ADR-10): pads, vehicles, ground stations, relays,
recovery zones, lunar landing attempts, lessons and weather rules.

Each catalogue is one JSON file under ``data/catalogues/``, curated by hand
and validated here as strictly as the mission list (ADR-5):

* ``extra="forbid"`` everywhere: a misspelt field is an error, not a silent
  default.
* **Every value says where it came from.** A record's data fields are each
  either published (named in ``field_sources`` with a URL that is one of the
  record's ``sources``), assumed (named in ``assumed_fields`` with the reason
  and, where there is one, the secondary source it rests on), or null and
  listed in ``unconfirmed_fields``. Nothing is filled in to look complete.
* The file's SHA-256 is its version; every answer built from a catalogue
  records that version (ADR-12 lineage).

The catalogues are small and read-only, so they are read from the validated
files (cached per process) rather than copied into tables: a table copy would
add a seed step and a second place for the same facts to drift apart.

``python -m app.data.catalogues`` validates every file and prints a summary.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import get_settings

URL = Field(pattern=r"^https://\S+$")


class CatalogueError(ValueError):
    """A catalogue file is not fit to use. The message names file, record and field."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Strict):
    url: str = URL
    title: str = Field(min_length=3)
    publisher: str = Field(min_length=2)
    accessed: date


class Assumption(_Strict):
    reason: str = Field(min_length=10)
    #: A secondary source the assumption rests on, when there is one.
    url: str | None = Field(default=None, pattern=r"^https://\S+$")
    #: The range an assumed number may take ("an unpublished value is an
    #: assumed range"); the field holds a value inside it. Both or neither.
    lo: float | None = None
    hi: float | None = None

    @model_validator(mode="after")
    def _range(self) -> Assumption:
        if (self.lo is None) != (self.hi is None):
            raise ValueError("an assumed range needs both ends")
        if self.lo is not None and self.hi is not None and self.lo > self.hi:
            raise ValueError("assumed range reversed")
        return self


class CitedRecord(_Strict):
    """A record whose every data field is published, assumed, or listed as unconfirmed."""

    #: Fields that identify a record rather than state a fact about it.
    IDENTITY: ClassVar[frozenset[str]] = frozenset(
        {"id", "name", "sources", "field_sources", "assumed_fields", "unconfirmed_fields", "notes"}
    )

    id: str = Field(pattern=r"^[a-z0-9]+([.-][a-z0-9]+)*$")
    name: str = Field(min_length=2)
    sources: list[Source] = Field(min_length=1)
    field_sources: dict[str, str] = Field(default_factory=dict)
    assumed_fields: dict[str, Assumption] = Field(default_factory=dict)
    unconfirmed_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    #: This project's own classification of a record (explained in the file's
    #: ``about``), not a fact attributed to a source.
    CLASSIFICATION: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _honest(self) -> CitedRecord:
        skip = self.IDENTITY | self.CLASSIFICATION
        data = [f for f in type(self).model_fields if f not in skip]
        urls = {s.url for s in self.sources}
        listed = set(self.unconfirmed_fields)
        named = set(self.field_sources) | set(self.assumed_fields) | listed
        unknown = named - set(data)
        if unknown:
            raise ValueError(f"names fields that do not exist: {sorted(unknown)}")
        both = set(self.field_sources) & set(self.assumed_fields)
        if both:
            raise ValueError(f"fields both published and assumed: {sorted(both)}")
        na = self.not_applicable()
        for f in data:
            value = getattr(self, f)
            empty = value is None or value == [] or value == {}
            if empty and f in na:
                continue
            if empty and f not in listed:
                raise ValueError(f"'{f}' is empty but not listed in unconfirmed_fields")
            if not empty and f in listed:
                raise ValueError(f"'{f}' has a value but is listed as unconfirmed")
            if not empty and f not in self.field_sources and f not in self.assumed_fields:
                raise ValueError(f"'{f}' has a value but no source and no stated assumption")
        for f, a in self.assumed_fields.items():
            value = getattr(self, f)
            if (a.lo is not None and a.hi is not None) and (
                not isinstance(value, int | float) or not a.lo <= value <= a.hi
            ):
                raise ValueError(f"'{f}' = {value!r} is outside its assumed range")
        for f, url in self.field_sources.items():
            if url not in urls:
                raise ValueError(
                    f"field_sources['{f}'] = {url} is not one of this record's sources"
                )
        return self

    def not_applicable(self) -> set[str]:
        """Fields that are empty because they do not apply to this record (not unknown)."""
        return set()

    def provenance(self, f: str) -> tuple[str, str | None]:
        """("published", url) | ("assumed", reason) | ("unconfirmed", None)."""
        if f in self.field_sources:
            return "published", self.field_sources[f]
        if f in self.assumed_fields:
            return "assumed", self.assumed_fields[f].reason
        return "unconfirmed", None


# ---------------------------------------------------------------------------
# The catalogues
# ---------------------------------------------------------------------------

RangeName = Literal["eastern", "western", "tanegashima", "sriharikota", "guiana", "wenchang"]

#: Pads on one range share one weather-model point set (a GEFS cell is ~50 km); the
#: feeds worker records each set under this name.
MODEL_REGION_OF_RANGE: dict[str, str] = {"eastern": "florida", "western": "vandenberg"}


class LaunchSite(CitedRecord):
    operator: str | None
    launch_range: RangeName
    lat_deg: float | None = Field(ge=-90, le=90)
    lon_deg: float | None = Field(ge=-180, le=180)
    #: Launch azimuths the range allows, degrees from north.
    azimuth_min_deg: float | None = Field(ge=0, le=360)
    azimuth_max_deg: float | None = Field(ge=0, le=360)
    vehicles: list[str]
    status: Literal["active", "damaged", "inactive", "under_construction"]
    status_note: str | None
    #: Where to look for weather: NWS covers US pads only.
    nws_forecast: bool
    ndbc_buoys: list[str]
    ll2_pad_id: int | None
    ll2_location_id: int | None


class Vehicle(CitedRecord):
    provider: str | None
    #: How the first stage (or side boosters) is usually recovered.
    booster_recovery: (
        Literal["droneship_or_land", "droneship", "land", "expended", "unknown"] | None
    )
    pads: list[str]
    user_guide_url: str | None
    #: A launch window the vehicle can fly (it steers in azimuth) or a single instant.
    window_kind: Literal["window", "instantaneous"] | None


class HorizonMaskPoint(_Strict):
    az_deg: float = Field(ge=0, le=360)
    el_deg: float = Field(ge=-5, le=90)


class GroundStation(CitedRecord):
    network: Literal["DSN", "ESTRACK", "KSAT", "SSC", "Goonhilly", "JAXA", "ISRO", "other"]
    operator: str | None
    #: Geodetic, WGS84 / ITRF93 to the precision given in the source.
    lat_deg: float | None = Field(ge=-90, le=90)
    lon_deg: float | None = Field(ge=-180, le=360)
    height_m: float | None
    #: NAIF body name in the DSN station kernels ("DSS-14"), when there is one.
    naif_name: str | None
    diameter_m: float | None = Field(gt=0)
    bands: list[str]
    #: Horizon mask: elevation below which the antenna cannot track, by azimuth.
    mask: list[HorizonMaskPoint]
    #: Mask used when ``mask`` is empty: a flat minimum elevation.
    min_elevation_deg: float | None
    status: Literal["operating", "planned", "retired"]


class Relay(CitedRecord):
    #: ``relay``: meant to relay for landers. ``validation_only``: a real
    #: orbiter used to check the pass calculation; never called a relay.
    role: Literal["relay", "validation_only"]
    operator: str | None
    #: NAIF id, for orbiters whose trajectory JPL Horizons serves.
    naif_id: int | None

    CLASSIFICATION: ClassVar[frozenset[str]] = frozenset({"role"})

    def not_applicable(self) -> set[str]:
        return {"naif_id"} if self.role == "relay" and self.status != "operating" else set()

    status: Literal["operating", "planned", "not_launched", "launched_not_operating"]
    launch_note: str | None
    #: Nominal orbit about the Moon: heights above the mean radius (1737.4 km),
    #: angles to the lunar equator. Published, or an assumed range, or unknown.
    periapsis_km: float | None
    apoapsis_km: float | None
    inclination_deg: float | None
    #: Argument of periapsis; about 90 deg puts the far point over the south pole.
    arg_periapsis_deg: float | None = None
    period_h: float | None
    orbit_note: str | None
    serves_missions: list[str]
    bands: list[str]


class RecoveryZone(CitedRecord):
    kind: Literal["booster_droneship", "booster_land", "capsule_splashdown", "capsule_land"]
    vehicle: str | None
    #: A fixed zone's position; a droneship's moves with each launch (null, unconfirmed).
    lat_deg: float | None = Field(ge=-90, le=90)
    lon_deg: float | None = Field(ge=-180, le=180)
    radius_km: float | None = Field(gt=0)
    #: How far downrange of the pad a droneship waited on the flights in ``used_by``.
    downrange_km: float | None = Field(gt=0)
    nearest_buoys: list[str]
    pads: list[str]
    #: Missions in data/missions.json whose booster came down here.
    used_by: list[str]

    def not_applicable(self) -> set[str]:
        return {"downrange_km"} if self.kind in ("booster_land", "capsule_land") else set()


class LandingAttempt(CitedRecord):
    mission: str
    agency: str
    commercial: bool
    #: The company that built and flew the lander, for commercial missions.
    provider: str | None
    date: date
    outcome: Literal["landed_working", "landed_tipped_or_partial", "failed"]
    cause: str | None
    clps: bool
    #: This product's mission id, for CLPS missions in data/missions.json.
    mission_id: str | None

    def not_applicable(self) -> set[str]:
        na = set()
        if self.outcome == "landed_working":
            na.add("cause")
        if not self.clps:
            na.add("mission_id")
        if not self.commercial:
            na.add("provider")
        return na


class Lesson(CitedRecord):
    text: str = Field(min_length=10)
    from_mission: str
    year: int = Field(ge=1960, le=2100)
    checklist_item: str = Field(min_length=10)
    applies_to: list[
        Literal[
            "lander",
            "payload",
            "rover",
            "launch_vehicle",
            "ops_team",
            "range",
            "ground_booking",
            "relay_agreement",
            "licence",
        ]
    ]


RuleClass = Literal["model", "proxy", "observation"]


class WeatherRule(CitedRecord):
    #: ``rule_class`` and ``variable`` are this project's classification of a rule (how it
    #: can be checked: from a forecast model, from model ingredients, or only by
    #: observation), explained in the file's ``about``.
    CLASSIFICATION: ClassVar[frozenset[str]] = frozenset({"rule_class", "variable"})

    #: The rule text as published, verbatim.
    text: str = Field(min_length=10)
    rule_class: RuleClass
    applies_to: list[str]
    variable: str | None
    threshold: float | None
    unit: str | None
    comparison: Literal["gt", "ge", "lt", "le"] | None
    height_m: float | None
    duration_note: str | None

    def not_applicable(self) -> set[str]:
        # Only a model rule is read at a height; a rule that states no duration has none.
        na = {"duration_note"}
        if self.rule_class != "model":
            na.add("height_m")
        return na


CATALOGUES: dict[str, type[CitedRecord]] = {
    "launch_sites": LaunchSite,
    "vehicles": Vehicle,
    "ground_stations": GroundStation,
    "relays": Relay,
    "recovery_zones": RecoveryZone,
    "landing_attempts": LandingAttempt,
    "lessons": Lesson,
    "weather_rules": WeatherRule,
}


class CatalogueFile(_Strict):
    schema_version: Literal[1]
    catalogue: str
    compiled: date
    about: str
    records: list[dict[str, Any]]


class Catalogue(BaseModel):
    """A validated catalogue: its records, its file version, and a lookup by id."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    version: str
    compiled: date
    about: str
    records: tuple[Any, ...]

    def get(self, rid: str) -> Any:
        for r in self.records:
            if r.id == rid:
                return r
        raise KeyError(f"{self.name}: no record '{rid}'")

    def ids(self) -> list[str]:
        return [r.id for r in self.records]


def path_of(name: str) -> Path:
    return get_settings().data_dir / "catalogues" / f"{name}.json"


def parse(name: str, raw_bytes: bytes, where: str = "") -> Catalogue:
    model = CATALOGUES[name]
    where = where or f"{name}.json"
    try:
        raw = json.loads(raw_bytes)
        head = CatalogueFile.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise CatalogueError(f"{where}: {exc}") from exc
    if head.catalogue != name:
        raise CatalogueError(f"{where}: says it is '{head.catalogue}', expected '{name}'")
    records = []
    problems = []
    for i, r in enumerate(head.records):
        try:
            records.append(model.model_validate(r))
        except ValidationError as exc:
            rid = r.get("id", f"#{i}") if isinstance(r, dict) else f"#{i}"
            for e in exc.errors():
                loc = ".".join(str(x) for x in e["loc"])
                problems.append(f"  {rid}{' field ' + loc if loc else ''}: {e['msg']}")
    ids = [r.id for r in records]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"  duplicate ids: {dupes}")
    if problems:
        raise CatalogueError(f"{where} failed validation:\n" + "\n".join(problems))
    return Catalogue(
        name=name,
        version=hashlib.sha256(raw_bytes).hexdigest()[:16],
        compiled=head.compiled,
        about=head.about,
        records=tuple(records),
    )


@lru_cache(maxsize=16)
def load(name: str) -> Catalogue:
    """The validated catalogue ``name``. Raises CatalogueError; cached per process."""
    if name not in CATALOGUES:
        raise KeyError(f"unknown catalogue {name!r}; known: {sorted(CATALOGUES)}")
    p = path_of(name)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise CatalogueError(f"cannot read {p}: {exc}") from exc
    return parse(name, data, str(p))


class RiskLevel(_Strict):
    level: int = Field(ge=1, le=10)
    words: str = Field(min_length=1)


class ConsequenceScale(_Strict):
    category: Literal["safety", "technical", "cost", "schedule"]
    levels: list[RiskLevel] = Field(min_length=2)


class RiskScale(_Strict):
    id: str
    name: str
    source_url: str | None
    likelihood: list[RiskLevel] = Field(min_length=2)
    consequence: list[ConsequenceScale] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(min_length=1)


class RiskScaleFile(_Strict):
    schema_version: Literal[1]
    compiled: date
    default_id: str
    scales: list[RiskScale] = Field(min_length=1)

    @model_validator(mode="after")
    def _default_exists(self) -> RiskScaleFile:
        if self.default_id not in {s.id for s in self.scales}:
            raise ValueError(f"default_id '{self.default_id}' is not one of the scales")
        return self


@lru_cache(maxsize=1)
def risk_scales() -> dict[str, Any]:
    """``{default_id, scales}`` from ``risk_scales.json`` (the contract's shape)."""
    p = get_settings().data_dir / "catalogues" / "risk_scales.json"
    try:
        f = RiskScaleFile.model_validate(json.loads(p.read_bytes()))
    except (OSError, ValueError, ValidationError) as exc:
        raise CatalogueError(f"{p}: {exc}") from exc
    return {
        "default_id": f.default_id,
        "scales": [s.model_dump(mode="json", exclude={"sources"}) for s in f.scales],
    }


def versions() -> dict[str, str]:
    """``{catalogue: version}`` for every catalogue that loads."""
    out = {}
    for name in CATALOGUES:
        try:
            out[name] = load(name).version
        except CatalogueError:
            continue
    return out


def check_references() -> list[str]:
    """Cross-catalogue references that do not resolve (pad -> vehicle, zone -> pad, ...)."""
    problems: list[str] = []
    sites = load("launch_sites")
    vehicles = load("vehicles")
    vids, sids = set(vehicles.ids()), set(sites.ids())
    for s in sites.records:
        problems += [
            f"launch_sites/{s.id}: unknown vehicle {v}" for v in s.vehicles if v not in vids
        ]
    for v in vehicles.records:
        problems += [f"vehicles/{v.id}: unknown pad {p}" for p in v.pads if p not in sids]
    try:
        zones = load("recovery_zones")
        for z in zones.records:
            problems += [f"recovery_zones/{z.id}: unknown pad {p}" for p in z.pads if p not in sids]
            if z.vehicle and z.vehicle not in vids:
                problems.append(f"recovery_zones/{z.id}: unknown vehicle {z.vehicle}")
    except CatalogueError:
        pass
    return problems


def main() -> None:
    bad = 0
    for name in CATALOGUES:
        try:
            c = load(name)
            print(f"{name:18s} {len(c.records):3d} records  version {c.version}")
        except CatalogueError as exc:
            bad += 1
            print(exc, file=sys.stderr)
    refs = check_references() if not bad else []
    for r in refs:
        print("reference:", r, file=sys.stderr)
    sys.exit(1 if bad or refs else 0)


if __name__ == "__main__":
    main()
