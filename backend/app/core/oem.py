"""Trajectory exports: CCSDS Orbit Ephemeris Message (KVN) and CSV. Pure.

The OEM follows CCSDS 502.0-B-3 (Orbit Data Messages), version 2.0 KVN:
one metadata block and one data block per covered stretch, so a gap in the
source is a gap in the file rather than an interpolated line across it.
Positions in km and velocities in km/s, as the standard requires.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Segment:
    times: Sequence[str]  # ISO-8601 UTC, no zone letter
    states_m: FloatArray  # (n, 6) m and m/s


def _km(states_m: FloatArray) -> FloatArray:
    return np.asarray(states_m, dtype=np.float64) / 1000.0


def oem(
    *,
    object_name: str,
    object_id: str,
    center: str,
    frame: str,
    segments: Sequence[Segment],
    created: str,
    originator: str,
    comments: Sequence[str] = (),
) -> str:
    """The OEM text. ``created`` and the segment times are UTC ISO strings without 'Z'."""
    if not segments:
        raise ValueError("an OEM needs at least one segment")
    out = io.StringIO()
    out.write("CCSDS_OEM_VERS = 2.0\n")
    for c in comments:
        out.write(f"COMMENT {c}\n")
    out.write(f"CREATION_DATE = {created}\n")
    out.write(f"ORIGINATOR = {originator}\n")
    for seg in segments:
        if len(seg.times) != seg.states_m.shape[0] or len(seg.times) < 2:
            raise ValueError("a segment needs at least two states, one per time")
        out.write("\nMETA_START\n")
        out.write(f"OBJECT_NAME = {object_name}\n")
        out.write(f"OBJECT_ID = {object_id}\n")
        out.write(f"CENTER_NAME = {center}\n")
        out.write(f"REF_FRAME = {frame}\n")
        out.write("TIME_SYSTEM = UTC\n")
        out.write(f"START_TIME = {seg.times[0]}\n")
        out.write(f"STOP_TIME = {seg.times[-1]}\n")
        out.write("META_STOP\n\n")
        for t, s in zip(seg.times, _km(seg.states_m), strict=True):
            out.write(f"{t} {s[0]:.6f} {s[1]:.6f} {s[2]:.6f} {s[3]:.9f} {s[4]:.9f} {s[5]:.9f}\n")
    return out.getvalue()


def csv_text(segments: Sequence[Segment], frame_note: str) -> str:
    """One row per state; a ``stretch`` column numbers the covered stretches from 1."""
    out = io.StringIO()
    out.write(f"# {frame_note}\n")
    out.write("time_utc,stretch,x_km,y_km,z_km,vx_km_s,vy_km_s,vz_km_s\n")
    for k, seg in enumerate(segments, start=1):
        for t, s in zip(seg.times, _km(seg.states_m), strict=True):
            out.write(
                f"{t}Z,{k},{s[0]:.6f},{s[1]:.6f},{s[2]:.6f},{s[3]:.9f},{s[4]:.9f},{s[5]:.9f}\n"
            )
    return out.getvalue()


def parse_oem(text: str) -> list[tuple[list[str], FloatArray]]:
    """Read back the data blocks of an OEM this module wrote: ``[(times, states_km)]``."""
    blocks: list[tuple[list[str], FloatArray]] = []
    times: list[str] = []
    rows: list[list[float]] = []
    in_data = False
    for line in text.splitlines():
        line = line.strip()
        if line == "META_START":
            if times:
                blocks.append((times, np.array(rows)))
            times, rows, in_data = [], [], False
        elif line == "META_STOP":
            in_data = True
        elif in_data and line and not line.startswith("COMMENT"):
            parts = line.split()
            times.append(parts[0])
            rows.append([float(x) for x in parts[1:7]])
    if times:
        blocks.append((times, np.array(rows)))
    return blocks
