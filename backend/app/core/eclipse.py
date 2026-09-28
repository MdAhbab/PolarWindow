"""Sunlight along the trip: in Earth's shadow, in the Moon's shadow (T2, eclipse). Pure.

Conical shadows of spherical bodies, as in Montenbruck and Gill, *Satellite
Orbits* (2000), section 3.4.2: from the spacecraft, the Sun is a disc of
angular radius ``a``, the occulting body a disc of radius ``b``, their
centres ``c`` apart. The visible fraction of the Sun is 1 when ``c >= a + b``,
0 when the body covers the Sun entirely (``c <= b - a``), and the
circle-overlap area otherwise. Three states follow, the same three the
surface engine uses: lit, penumbral (partly covered, including an annular
view) and dark.

Edges are placed between samples by linear interpolation of the margin
``c - (a + b)`` (first contact) and ``c - (b - a)`` (full cover), which is
exact to well under a second at a one-minute step for these slowly varying
angles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from app.core import intervals
from app.core.intervals import Run

FloatArray = npt.NDArray[np.float64]

LIT: Final[int] = 2
PENUMBRAL: Final[int] = 1
DARK: Final[int] = 0


def _angle(u: FloatArray, v: FloatArray) -> FloatArray:
    """Angle between row vectors, robust near 0 and pi (atan2 of cross and dot)."""
    cross = np.linalg.norm(np.cross(u, v), axis=1)
    dot = np.einsum("ij,ij->i", u, v)
    return np.asarray(np.arctan2(cross, dot), dtype=np.float64)


@dataclass(frozen=True, slots=True)
class Occultation:
    """One occulting body's geometry against the Sun, per sample (radians)."""

    sun_radius: FloatArray
    body_radius: FloatArray
    separation: FloatArray

    @property
    def first_contact_margin(self) -> FloatArray:
        """> 0 when no part of the Sun is covered."""
        return self.separation - (self.sun_radius + self.body_radius)

    @property
    def full_cover_margin(self) -> FloatArray:
        """< 0 when the whole Sun is covered."""
        return self.separation - (self.body_radius - self.sun_radius)

    def visible_fraction(self) -> FloatArray:
        a, b, c = self.sun_radius, self.body_radius, self.separation
        frac = np.ones_like(c)
        covered = c <= b - a
        frac[covered] = 0.0
        partial = (~covered) & (c < a + b)
        if np.any(partial):
            ap, bp, cp = a[partial], b[partial], c[partial]
            # Area of intersection of two circles (Montenbruck and Gill eq. 3.93).
            x = (cp**2 + ap**2 - bp**2) / (2.0 * cp)
            y = np.sqrt(np.clip(ap**2 - x**2, 0.0, None))
            area = (
                ap**2 * np.arccos(np.clip(x / ap, -1, 1))
                + bp**2 * np.arccos(np.clip((cp - x) / bp, -1, 1))
                - cp * y
            )
            # Annular: the body is inside the Sun's disc.
            annular = cp <= ap - bp
            area = np.where(annular, np.pi * bp**2, area)
            frac[partial] = 1.0 - area / (np.pi * ap**2)
        return frac


def occultation(
    sc_to_sun: FloatArray, sc_to_body: FloatArray, r_sun_m: float, r_body_m: float
) -> Occultation:
    ds = np.linalg.norm(sc_to_sun, axis=1)
    db = np.linalg.norm(sc_to_body, axis=1)
    return Occultation(
        sun_radius=np.arcsin(np.clip(r_sun_m / ds, -1, 1)),
        body_radius=np.arcsin(np.clip(r_body_m / db, -1, 1)),
        separation=_angle(sc_to_sun, sc_to_body),
    )


def state(occs: list[Occultation]) -> npt.NDArray[np.int8]:
    """Three states from any number of occulting bodies: the worst one wins."""
    out = np.full(occs[0].separation.shape, LIT, dtype=np.int8)
    for o in occs:
        out[o.first_contact_margin <= 0] = np.minimum(out[o.first_contact_margin <= 0], PENUMBRAL)
        out[o.full_cover_margin < 0] = DARK
    return out


def shadow_runs(t_s: FloatArray, occs: list[Occultation]) -> list[Run]:
    """Runs of "some of the Sun is covered" (value True), edges interpolated."""
    parts = [
        intervals.complement(intervals.runs_from_margin(t_s, o.first_contact_margin)) for o in occs
    ]
    return intervals.any_of(parts) if len(parts) > 1 else parts[0]


def dark_runs(t_s: FloatArray, occs: list[Occultation]) -> list[Run]:
    """Runs of "all of the Sun is covered" (value True)."""
    parts = [intervals.runs_from_margin(t_s, -o.full_cover_margin) for o in occs]
    return intervals.any_of(parts) if len(parts) > 1 else parts[0]
