"""Prepare reconstructed belt passages for an external SPENVIS comparison.

Run ``python -m app.validation.export_spenvis``. Files are written under
``data/validation/spenvis``; no account details are needed or exported.
The format follows https://www.spenvis.oma.be/help/models/sapre_upl.html.
This prepares inputs and engine references; it does not run or validate SPENVIS.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import numpy as np

from app.config import ENGINES, get_settings
from app.core import belts, spice
from app.services import ascent, lifecycle, radiation


def trajectory_text(title: str, times: list[datetime], geo_km: np.ndarray) -> str:
    """Earth-fixed Cartesian kilometres and UTC dates, with no frame conversion."""
    xyz = np.asarray(geo_km, dtype=float)
    if xyz.shape != (len(times), 3) or len(times) < 2 or not np.isfinite(xyz).all():
        raise ValueError("at least two finite XYZ samples matching the UTC times are required")
    if any(t.tzinfo is None or t.utcoffset() is None for t in times):
        raise ValueError("trajectory times must include a timezone")
    utc = [t.astimezone(UTC) for t in times]
    if any(b <= a for a, b in pairwise(utc)):
        raise ValueError("trajectory times must strictly increase")
    if "\n" in title or "\r" in title:
        raise ValueError("title must be a single line")
    lines = [
        f"Title: {title}", "Planet: Earth", "Coordinates: GEO",
        "Columns: DYEA, DMON, DDAY, DHOU, DMIN, DSEC, X, Y, Z",
        "Format: CSV", "$$BEGIN",
    ]
    for t, row in zip(utc, xyz, strict=True):
        sec = t.second + t.microsecond / 1e6
        lines.append(
            f"{t.year},{t.month},{t.day},{t.hour},{t.minute},{sec:.6f},"
            + ",".join(f"{v:.9f}" for v in row)
        )
    return "\n".join([*lines, "$$END", ""])


def export_mission(mission: str, output: Path) -> dict[str, object]:
    path = ascent.spk_path(mission)
    spice.load_extra([path])
    spacecraft = ascent.RECONSTRUCTED[mission][1]
    cover = spice.coverage(path, spacecraft)
    start = lifecycle.parse_time(spice.et_to_utc(cover[0][0]))
    phase = radiation.solar_phase(start)
    if phase is None:
        raise ValueError(f"{mission}: missing solar phase data")
    seconds, times, geo = radiation.belt_samples(str(spacecraft), cover)
    if seconds.size == 0:
        return {"mission": mission, "status": "no_belt_coverage", "segments": []}
    flux = {
        "electron": belts.integral_flux("e", phase.solar, [radiation.E_MEV], times, geo)[0],
        "proton": belts.integral_flux("p", phase.solar, [radiation.P_MEV], times, geo)[0],
    }
    passages = []
    for index, ids in enumerate(radiation._segments(seconds), start=1):
        if ids.size < 2:
            raise ValueError(f"{mission}: passage {index} has no integration interval")
        selected_times = [times[int(i)] for i in ids]
        stem = f"{mission}-passage-{index:02d}"
        content = trajectory_text(stem, selected_times, geo[ids]).encode("ascii")
        (output / f"{stem}.csv").write_bytes(content)
        baseline = output / f"{stem}-engine.csv"
        with baseline.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "utc", "seconds", "electron_gt1mev_cm-2_s-1", "proton_gt10mev_cm-2_s-1",
            ])
            for i in ids:
                writer.writerow([
                    times[i].isoformat(), seconds[i], flux["electron"][i], flux["proton"][i],
                ])
        duration = float(seconds[ids[-1]] - seconds[ids[0]])
        passages.append({
            "trajectory_file": f"{stem}.csv",
            "engine_file": baseline.name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "samples": int(ids.size),
            "start_utc": selected_times[0].isoformat(),
            "end_utc": selected_times[-1].isoformat(),
            "mission_length_seconds": duration,
            "mission_length_days": duration / radiation.DAY_S,
            "engine_fluence_cm-2": {
                name: belts.fluence(seconds[ids], values[ids]) for name, values in flux.items()
            },
        })
    return {
        "mission": mission, "status": "prepared_not_run", "solar": phase.solar,
        "trajectory_source": path.name,
        "trajectory_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "segments": passages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", action="append", choices=sorted(ascent.RECONSTRUCTED))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    output = args.output or settings.data_dir / "validation" / "spenvis"
    output.mkdir(parents=True, exist_ok=True)
    spice.load(settings.kernel_dir)
    missions = [export_mission(m, output) for m in args.mission or sorted(ascent.RECONSTRUCTED)]
    manifest = {
        "status": "prepared_not_run", "generated_at": datetime.now(UTC).isoformat(),
        "upload_format_source": "https://www.spenvis.oma.be/help/models/sapre_upl.html",
        "coordinates": "GEO", "position_unit": "km", "date_scale": "UTC",
        "models": ["AE8", "AP8"], "electron_threshold_mev": radiation.E_MEV,
        "engine": ENGINES["rad"],
        "saa_correction": {"eastward_deg_per_year": belts.SAA_DRIFT_DEG_YR,
                           "electron_epoch": 1960, "ap8_max_epoch": 1970},
        "proton_threshold_mev": radiation.P_MEV, "comparison_tolerance_fraction": 0.05,
        "requirements": [
            "Trajectory upload requires Advanced-user access in SPENVIS.",
            "Upload each passage separately; never integrate across trajectory gaps.",
            "Set mission length to that passage's exact duration, not a default year.",
            "Select the recorded solar MIN/MAX phase and integral omnidirectional flux.",
            "Record magnetic field and B0 settings; differing shells are a separate comparison.",
            "Download raw outputs and run report; prepared inputs are not a validation result.",
        ],
        "missions": missions,
    }
    target = output / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
