"""Which model has the air right between 30 and 70 km on OSIRIS-REx's entry day (plan track H).

A capsule loses its speed between 30 and 70 km, so the landing rests on the air there (the
density 5 % higher over 30 to 50 km moves it 2.3 km, over 50 to 70 km 2.4 km). Two measurements
of that air are on disk (``capsule_air_data`` says where they are from and how they were reduced):

* TIMED/SABER's limb profiles of the entry day, 136 of them from 28 to 49 N, at 3.6 and 18 h local
  solar time (the capsule flew at 6.7 h), and
* the Table Mountain lidar's nine nights from 19 to 30 September (34.4 N; no night of the 23rd
  to 25th), at 19 to 21 h local solar time.

Each model is asked, with the flux and geomagnetic activity of the profile's own time
(``data.msis_indices``), for the density and temperature at each profile's place, time and heights
(1 km bins), and the mean of ``ln(model / measured)`` over each 5 km band from 30 to 70 km is its
bias there. **The rule:** a model's score is the root mean square of its eight band biases; the
one with the lower score for both instruments is the default, and if the two scores are less than
a percentage point apart for either, the published evaluations decide (Emmert et al. 2021: NRLMSIS
2.0 follows the stratosphere and mesosphere better than NRLMSISE-00, and NRLMSIS 2.1 is NRLMSIS
2.0 with nitric oxide added, Emmert et al. 2022, a trace species above 73 km).

How the rule came about, said as it was: the score and the one-point tie went into the first
comparison script (SABER only) before it was run, and the lidar was scored the same way after;
"the lower score for both instruments" was written after SABER's scores had been seen; and all of
it was written after the two landings were known (12.1 km in NRLMSISE-00, 6.6 km in NRLMSIS 2.1).
Nothing here flies a capsule or reads where one lands. The cuts (``cuts``) drop some profiles at a
time and score again; they are a check on the rule and do not enter it.

Neither instrument is independent of the models in every respect. SABER's temperatures were
fitted by NRLMSIS 2.0 for 2002 to 2016 at 40 to 97.5 km (Emmert et al. 2021, Table 1), so its
agreement on a day in 2023 is a test in time, not against another instrument. The lidar is in
no fit (Table 1 has no Rayleigh lidar; its lidars are sodium ones at 88 to 105 km), but its file
names MERRA-2 as the source it scales density and temperature to (the height of the scaling is
not given), and MERRA-2 is in NRLMSIS 2.0's fit up to 55 km: the level of the lidar's density is
not independent of that fit, its change with height is. ``Score.shape_rms_pct`` is that part.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import numpy.typing as npt

from app.config import get_settings
from app.core import atmosphere
from app.data import msis_indices
from app.services import capsule

FloatArray = npt.NDArray[np.float64]

SABER = "capsule/saber_20230924.json"
LIDAR = "capsule/tmf_lidar_202309.json"
#: Mean molecular mass of dry air, kg/mol, and Avogadro's number: number density to mass density.
M_AIR = 28.9647e-3
N_A = 6.02214076e23
BANDS_KM = tuple((lo, lo + 5) for lo in range(30, 70, 5))
#: Two scores less than this many percentage points apart are a tie.
TIE_POINTS = 1.0
#: The models that can be the default, and the reference that cannot (it has no day in it).
CANDIDATES = tuple(capsule.MSIS_VERSIONS)
REFERENCE = capsule.STANDARD_NAME


@dataclass(frozen=True, slots=True)
class Profiles:
    """Measured profiles on a common set of heights (bin centres, km): ``temperature_k`` and
    ``density`` (kg/m^3) are (profiles, heights), NaN where nothing was measured."""

    name: str
    when: list[datetime]
    lat_deg: FloatArray
    lon_deg: FloatArray
    z_km: FloatArray
    temperature_k: FloatArray
    density: FloatArray
    #: Local solar time of each profile, h, where the instrument gives it (SABER).
    local_time_h: FloatArray | None = None
    #: What the profiles are, in words for a sentence on screen (no straight apostrophe).
    plain: str = ""


def _load(rel: str, name: str, plain: str) -> Profiles:
    raw = json.loads((get_settings().data_dir / rel).read_text())
    ps = raw["profiles"]

    def grid(key: str, scale: float = 1.0) -> FloatArray:
        return np.array(
            [[np.nan if x is None else x * scale for x in p[key]] for p in ps], dtype=np.float64
        )

    lst = [p.get("local_solar_time_h") for p in ps]
    return Profiles(
        name,
        [datetime.fromisoformat(p["time"].replace("Z", "+00:00")) for p in ps],
        np.array([p["lat_deg"] for p in ps]),
        np.array([p["lon_deg"] for p in ps]),
        np.array(raw["z_km"], dtype=np.float64),
        grid("temperature_k"),
        grid("number_density_cm3", 1e6 * M_AIR / N_A),
        None if any(x is None for x in lst) else np.array(lst, dtype=np.float64),
        plain,
    )


def saber() -> Profiles:
    return _load(
        SABER,
        "TIMED/SABER, 24 September 2023, 28 to 49 N",
        "the TIMED/SABER satellite’s profiles of that day",
    )


def lidar() -> Profiles:
    return _load(
        LIDAR,
        "Table Mountain lidar, nine nights 19 to 30 September 2023",
        "the Table Mountain laser radar’s (lidar’s) nights either side of it",
    )


def model_grid(p: Profiles, model: str) -> tuple[FloatArray, FloatArray]:
    """(density kg/m^3, temperature K) of ``model`` at each profile's place, time and heights."""
    rho = np.full(p.temperature_k.shape, np.nan)
    temp = np.full(p.temperature_k.shape, np.nan)
    if model == REFERENCE:
        for k, z in enumerate(p.z_km):
            lower = atmosphere.lower(float(z) * 1000.0)
            rho[:, k], temp[:, k] = lower[2], lower[0]  # below 80 km the two temperatures agree
        return rho, temp
    for i, ix in enumerate(msis_indices.at_many(p.when)):
        if ix is None:
            raise RuntimeError(f"the OMNI files on disk lack the indices for {p.when[i]}")
        rho[i], temp[i] = capsule.msis_column(
            p.when[i],
            float(p.lat_deg[i]),
            float(p.lon_deg[i]),
            p.z_km * 1000.0,
            ix.f107,
            ix.f107a,
            ix.ap,
            capsule.MSIS_VERSIONS[model],
        )
    return rho, temp


@dataclass(frozen=True, slots=True)
class Score:
    model: str
    #: Mean of ln(model / measured) in each band of ``BANDS_KM``, as a percentage of density.
    density_bias_pct: tuple[float, ...]
    #: Mean of (model - measured) temperature in each band, K.
    temperature_bias_k: tuple[float, ...]

    @property
    def rms_pct(self) -> float:
        return float(np.sqrt(np.mean(np.square(self._ln))))

    @property
    def rms_k(self) -> float:
        return float(np.sqrt(np.mean(np.square(self.temperature_bias_k))))

    @property
    def shape_rms_pct(self) -> float:
        """The same, with each band's bias taken from the 30 to 35 km band's (the seven above
        it): what is left of the score when the level of the measured density is not trusted."""
        ln = self._ln
        return float(np.sqrt(np.mean(np.square(ln[1:] - ln[0]))))

    @property
    def _ln(self) -> FloatArray:
        return np.log1p(np.array(self.density_bias_pct) / 100.0) * 100.0


def score(
    p: Profiles,
    model: str,
    keep: npt.NDArray[np.bool_] | None = None,
    grid: tuple[FloatArray, FloatArray] | None = None,
) -> Score:
    """``model``'s score over the profiles ``keep`` (all when None); ``grid`` is its
    ``model_grid`` when that is already worked out."""
    rho, temp = grid if grid is not None else model_grid(p, model)
    rows = np.ones(len(p.when), dtype=bool) if keep is None else keep
    ln = np.log(rho[rows] / p.density[rows])
    dt = temp[rows] - p.temperature_k[rows]
    biases: list[float] = []
    dts: list[float] = []
    for lo, hi in BANDS_KM:
        s = (p.z_km >= lo) & (p.z_km < hi)
        biases.append(float(np.nanmean(ln[:, s])))
        dts.append(float(np.nanmean(dt[:, s])))
    return Score(model, tuple(100.0 * math.expm1(b) for b in biases), tuple(dts))


def scores(p: Profiles) -> dict[str, Score]:
    return {m: score(p, m) for m in (*CANDIDATES, REFERENCE)}


def cuts(p: Profiles) -> dict[str, npt.NDArray[np.bool_]]:
    """Ways of dropping some of the profiles that should not change which model is nearer:
    SABER's by latitude and by local solar time, the lidar's by leaving each night out."""
    if p.local_time_h is not None:
        lat, lt = p.lat_deg, p.local_time_h
        return {
            "28 to 38 N": lat < 38.0,
            "35 to 42 N (round the entry track)": (lat >= 35.0) & (lat <= 42.0),
            "38 to 49 N": lat >= 38.0,
            "before noon, local solar time": lt < 12.0,
            "after noon, local solar time": lt >= 12.0,
        }
    out: dict[str, npt.NDArray[np.bool_]] = {}
    for i, t in enumerate(p.when):
        keep = np.ones(len(p.when), dtype=bool)
        keep[i] = False
        out[f"without the night of {t:%d %b}, {t:%H:%M} UTC"] = keep
    return out


def cut_scores(p: Profiles) -> dict[str, tuple[int, dict[str, Score]]]:
    """For each cut of ``cuts``: how many profiles are left and each candidate's score."""
    grids = {m: model_grid(p, m) for m in CANDIDATES}
    return {
        name: (int(keep.sum()), {m: score(p, m, keep, grids[m]) for m in CANDIDATES})
        for name, keep in cuts(p).items()
    }


def choose(by_instrument: dict[str, dict[str, Score]]) -> tuple[str, str]:
    """(the default model, what decided it): the candidate with the lower score for every
    instrument when each gap is at least ``TIE_POINTS``, else the published evaluations'
    NRLMSIS 2.1."""
    best = min(CANDIDATES, key=lambda m: sum(s[m].rms_pct for s in by_instrument.values()))
    clear = all(
        min(s[o].rms_pct for o in CANDIDATES if o != best) - s[best].rms_pct >= TIE_POINTS
        for s in by_instrument.values()
    )
    if clear:
        return best, "measurements"
    return "NRLMSIS 2.1", "published evaluations"


def evidence() -> dict[str, Any]:
    """The comparison, and the choice, as ``data/capsule/orex_check.json`` keeps them."""
    profs = [saber(), lidar()]
    by = {p.name: scores(p) for p in profs}
    chosen, decided_by = choose(by)
    others = [m for m in CANDIDATES if m != chosen]
    parts = [f"{by[p.name][chosen].rms_pct:.1f} % from {p.plain}" for p in profs]
    against = " and ".join(f"{by[p.name][others[0]].rms_pct:.1f} %" for p in profs)
    return {
        "chosen": chosen,
        "decided_by": decided_by,
        "bands_km": [list(b) for b in BANDS_KM],
        "basis": (
            f"{chosen} was chosen over {' and '.join(others)} because it came nearer to the air "
            f"measured between 30 and 70 km up, where a capsule slows: its density was off by "
            + " and ".join(parts)
            + f", against {against} for {' and '.join(others)} (the {decided_by} decided)."
        ),
        "instruments": [
            {
                "name": p.name,
                "profiles": len(p.when),
                "models": [
                    {
                        "name": m,
                        "rms_density_bias_pct": round(s.rms_pct, 2),
                        "shape_rms_density_bias_pct": round(s.shape_rms_pct, 2),
                        "density_bias_pct": [round(x, 1) for x in s.density_bias_pct],
                        "rms_temperature_bias_k": round(s.rms_k, 2),
                        "temperature_bias_k": [round(x, 1) for x in s.temperature_bias_k],
                    }
                    for m, s in by[p.name].items()
                ],
                "cuts": [
                    {
                        "name": name,
                        "profiles": n,
                        "models": [
                            {
                                "name": m,
                                "rms_density_bias_pct": round(s.rms_pct, 2),
                                "shape_rms_density_bias_pct": round(s.shape_rms_pct, 2),
                            }
                            for m, s in sc.items()
                        ],
                    }
                    for name, (n, sc) in cut_scores(p).items()
                ],
            }
            for p in profs
        ],
    }


def print_tables(ev: dict[str, Any]) -> None:
    """The tables of docs/validation.md."""
    bands = " | ".join(f"{lo}-{hi}" for lo, hi in BANDS_KM)
    for inst in ev["instruments"]:
        print(f"\n{inst['name']} ({inst['profiles']} profiles); model / measured density - 1, %:")
        print(f"| Model | {bands} km | Score | Shape only |")
        print("|---|" + "---|" * (len(BANDS_KM) + 2))
        for m in inst["models"]:
            cells = " | ".join(f"{x:+.1f}" for x in m["density_bias_pct"])
            print(
                f"| {m['name']} | {cells} | {m['rms_density_bias_pct']:.2f} | "
                f"{m['shape_rms_density_bias_pct']:.2f} |"
            )
        print("model - measured temperature, K:")
        print(f"| Model | {bands} km | RMS |")
        print("|---|" + "---|" * (len(BANDS_KM) + 1))
        for m in inst["models"]:
            cells = " | ".join(f"{x:+.1f}" for x in m["temperature_bias_k"])
            print(f"| {m['name']} | {cells} | {m['rms_temperature_bias_k']:.2f} |")
        names = [m["name"] for m in inst["models"] if m["name"] in CANDIDATES]
        print("with some of the profiles dropped, score (shape only), %:")
        print("| Profiles dropped or kept | Kept | " + " | ".join(names) + " |")
        print("|---|---|" + "---|" * len(names))
        for c in inst["cuts"]:
            by = {m["name"]: m for m in c["models"]}
            cells = " | ".join(
                f"{by[n]['rms_density_bias_pct']:.2f} ({by[n]['shape_rms_density_bias_pct']:.2f})"
                for n in names
            )
            print(f"| {c['name']} | {c['profiles']} | {cells} |")
    print(f"\nDefault: {ev['chosen']} ({ev['decided_by']}). {ev['basis']}")
