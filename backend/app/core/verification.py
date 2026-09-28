"""Scores for forecast shares checked against what happened (T4, Verification).

A forecast here is a share ``p`` = k of N ensemble runs that break a rule; the
outcome ``o`` is 1 when the observation broke it. The plan's gate for saying a
rule's shares are "checked against observations":

* Brier skill of at least 0.1 against the month-by-hour climatology of the
  same event, at every lead up to 48 h;
* reliability within 0.1 in every bin of forecast share holding at least 30
  cases (the observed frequency against the mean share in the bin).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

BSS_MIN = 0.1
RELIABILITY_TOL = 0.1
MIN_BIN_CASES = 30


def brier(p: FloatArray, o: FloatArray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(o)) ** 2))


def brier_skill(p: FloatArray, o: FloatArray, p_ref: FloatArray) -> float | None:
    """``1 - BS / BS_ref``; None when the reference is perfect (no events, or all)."""
    ref = brier(p_ref, o)
    if ref == 0.0:
        return None
    return 1.0 - brier(p, o) / ref


@dataclass(frozen=True, slots=True)
class Bin:
    lo: float
    hi: float
    n: int
    mean_p: float | None
    freq: float | None

    @property
    def counted(self) -> bool:
        return self.n >= MIN_BIN_CASES

    @property
    def ok(self) -> bool:
        """Within tolerance, or too few cases to say."""
        if not self.counted or self.mean_p is None or self.freq is None:
            return True
        return abs(self.freq - self.mean_p) <= RELIABILITY_TOL


def reliability(p: FloatArray, o: FloatArray, n_bins: int = 10) -> list[Bin]:
    """Forecast shares in ``n_bins`` equal bins over [0, 1] (the last one closed)."""
    p = np.asarray(p, dtype=np.float64)
    o = np.asarray(o, dtype=np.float64)
    idx = np.minimum((p * n_bins).astype(int), n_bins - 1)
    out = []
    for b in range(n_bins):
        sel = idx == b
        n = int(np.count_nonzero(sel))
        out.append(
            Bin(
                lo=b / n_bins,
                hi=(b + 1) / n_bins,
                n=n,
                mean_p=float(np.mean(p[sel])) if n else None,
                freq=float(np.mean(o[sel])) if n else None,
            )
        )
    return out


def passes(skills: dict[int, float | None], bins: list[Bin]) -> bool:
    """The plan's gate: skill at every lead and reliability in every counted bin."""
    if not skills:
        return False
    if any(s is None or s < BSS_MIN for s in skills.values()):
        return False
    return all(b.ok for b in bins)


def neutral_ratio(z_from_m: float, z_to_m: float, z0_m: float) -> float:
    """``u(z_to) / u(z_from)`` for a neutral logarithmic profile with roughness ``z0``."""
    return math.log(z_to_m / z0_m) / math.log(z_from_m / z0_m)
