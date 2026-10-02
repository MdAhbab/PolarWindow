"""Compare a downloaded SPENVIS passage with the exported engine samples.

No credentials or browser access are used. Raw files are preserved locally.
Example: python -m app.validation.compare_spenvis --mission im-2
  --protons ../data/spenvis_spp.txt --electrons ../data/spenvis_spe.txt
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core import belts
from app.services import lifecycle


@dataclass
class Spectrum:
    metadata: dict[str, list[str]]
    energies: list[float]
    values: np.ndarray


def read_spectrum(path: Path) -> Spectrum:
    """Read the B(Gauss), L, integral-flux columns in a SPENVIS spectrum file."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    metadata = {}
    start = None
    for index, line in enumerate(lines):
        row = [v.strip() for v in next(csv.reader([line], quotechar="'"))]
        if row and row[0] == "Flux":
            if row[1] != "cm!u-2!n s!u-1!n" or "Integral Flux" not in row[3]:
                raise ValueError("expected integral omnidirectional flux in cm^-2 s^-1")
            start = index + 1
            break
        if row and line.startswith("'"):
            metadata[row[0]] = row[1:]
    if start is None or metadata.get("ENERGY", [""])[-1] != "MeV":
        raise ValueError("missing spectrum columns or MeV energy metadata")
    energies = list(map(float, metadata["ENERGY"][1:-1]))
    if len(energies) != int(metadata["ENERGY"][0]) or len(set(energies)) != len(energies):
        raise ValueError("invalid energy count or duplicate energies")
    if metadata.get("TRP_OMN", []) != ["1", "1", ""]:
        raise ValueError("expected omnidirectional spectra")
    rows = []
    for line in lines[start:]:
        if not line.strip():
            continue
        if line.strip() == "'End of File'":
            break
        numeric = list(map(float, line.split(",")))
        if len(numeric) != len(energies) + 2:
            raise ValueError("spectrum row has the wrong number of columns")
        rows.append(numeric)
    values = np.asarray(rows)
    if not rows or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("spectrum values must be finite and nonnegative")
    return Spectrum(metadata, energies, values)


def compare(spectrum: Spectrum, model: str, passage: dict, engine: Path, energy: float) -> dict:
    if spectrum.metadata["TRP_MOD"][1] != model:
        raise ValueError(f"expected {model}")
    if spectrum.metadata["ORB_HDR"][1] != Path(passage["trajectory_file"]).stem:
        raise ValueError("raw spectrum belongs to another passage")
    duration = float(spectrum.metadata["ORB_DUR"][1]) * 86400.0
    if abs(duration - passage["mission_length_seconds"]) > 0.1:
        raise ValueError("raw spectrum and exported passage durations differ")
    with engine.open() as file:
        rows = list(csv.DictReader(file))
    if len(rows) != len(spectrum.values) or len(rows) != passage["samples"]:
        raise ValueError("sample counts differ; do not align by guessed row numbers")
    start = lifecycle.parse_time(rows[0]["utc"])
    recorded = [
        int(float(spectrum.metadata[k][1]))
        for k in ("ORB_YEA", "ORB_MON", "ORB_DAY", "ORB_HOU", "ORB_MIN")
    ]
    if recorded != [start.year, start.month, start.day, start.hour, start.minute]:
        raise ValueError("spectrum start date differs")
    if abs(float(spectrum.metadata["ORB_SEC"][1]) - start.second - start.microsecond / 1e6) > 0.1:
        raise ValueError("spectrum start second differs")
    times = np.array([(lifecycle.parse_time(r["utc"]) - start).total_seconds() for r in rows])
    if np.any(np.diff(times) <= 0) or abs(times[-1] - duration) > 0.1:
        raise ValueError("invalid passage times")
    flux = spectrum.values[:, 2 + spectrum.energies.index(energy)]
    reference = belts.fluence(times, flux)
    particle = "electron" if model.startswith("AE") else "proton"
    field = "electron_gt1mev_cm-2_s-1" if particle == "electron" else "proton_gt10mev_cm-2_s-1"
    predicted = belts.fluence(times, np.array([float(r[field]) for r in rows]))
    if reference <= 0:
        raise ValueError("positive reference fluence required for a relative comparison")
    difference = predicted / reference - 1
    return {
        "particle": particle,
        "energy_mev": energy,
        "samples": len(rows),
        "spenvis_fluence_cm-2": reference,
        "engine_fluence_cm-2": predicted,
        "relative_difference_fraction": difference,
        "passes_5_percent": abs(difference) <= 0.05,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", required=True)
    parser.add_argument("--passage", type=int, default=1)
    parser.add_argument("--protons", type=Path, required=True)
    parser.add_argument("--electrons", type=Path, required=True)
    args = parser.parse_args()
    root = get_settings().data_dir / "validation" / "spenvis"
    manifest = json.loads((root / "manifest.json").read_text())
    mission = next(m for m in manifest["missions"] if m["mission"] == args.mission)
    if not 1 <= args.passage <= len(mission["segments"]):
        parser.error("passage must identify one of the exported segments (starting at 1)")
    passage = mission["segments"][args.passage - 1]
    results = []
    output = root / "results" / args.mission
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for path, model, energy in [(args.protons, "AP-8", 10.0), (args.electrons, "AE-8", 1.0)]:
        spectrum = read_spectrum(path)
        results.append(
            compare(
                spectrum,
                f"{model} {mission['solar'].upper()}",
                passage,
                root / passage["engine_file"],
                energy,
            )
        )
        if path.resolve() != (output / path.name).resolve():
            shutil.copyfile(path, output / path.name)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "status": "passed_for_this_passage"
        if all(r["passes_5_percent"] for r in results)
        else "failed_for_this_passage",
        "mission": args.mission,
        "passage": args.passage,
        "raw_sha256": hashes,
        "engine": manifest.get("engine", "not recorded"),
        "trajectory_sha256": passage["sha256"],
        "comparison": results,
        "method": "trapezoid integration over exported sample times; denominator SPENVIS",
        "limitations": "Checks this passage only. Equal sample count, name, start and duration "
        "are required; sample order follows the downloaded trajectory. Rounded raw outputs.",
    }
    target = output / "comparison-summary.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
