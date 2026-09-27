"""Small vector helpers shared by the launch and transfer code. Pure."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def unit(v: FloatArray) -> FloatArray:
    return np.asarray(v / np.linalg.norm(v), dtype=np.float64)


def rotate(v: FloatArray, axis: FloatArray, angle: float) -> FloatArray:
    """Rodrigues rotation of ``v`` about unit ``axis`` by ``angle``."""
    k = unit(axis)
    return np.asarray(
        v * math.cos(angle)
        + np.cross(k, v) * math.sin(angle)
        + k * float(k @ v) * (1.0 - math.cos(angle)),
        dtype=np.float64,
    )


def east_north(up: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Local east and north unit vectors at the direction ``up`` (z is the pole)."""
    east = unit(np.cross([0.0, 0.0, 1.0], up))
    return east, np.cross(unit(up), east)
