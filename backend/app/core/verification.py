"""Scores for forecast shares checked against what happened (T4, Verification).

A forecast here is a share ``p`` = k of N ensemble runs that break a rule; the
outcome ``o`` is 1 when the observation broke it. The plan's gate for saying a
rule's shares are "checked against observations":

* Brier skill of at least 0.1 against the month-by-hour climatology of the
  same event, at every lead up to 48 h;
* reliability within 0.1 in every bin of forecast share holding at least 30
  cases (the observed frequency against the mean share in the bin).

The continuous ranked probability score (CRPS) scores the whole spread of runs
against the measured value, so a limit that is rarely reached still gets a
skill number; it is reported, never part of the gate.
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
#: A Brier skill is not worked out from fewer cases above the limit than this: the
#: reference score is then a few misses' worth of noise, and the skill a ratio of noises.
MIN_EVENTS = 10


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
    def freq_95(self) -> tuple[float, float] | None:
        """95 % (Wilson) interval of the observed frequency from this bin's cases."""
        if self.freq is None or not self.n:
            return None
        return wilson(round(self.freq * self.n), self.n)

    @property
    def ok(self) -> bool:
        """Within tolerance, or too few cases to say."""
        if not self.counted or self.mean_p is None or self.freq is None:
            return True
        return abs(self.freq - self.mean_p) <= RELIABILITY_TOL


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95 % Wilson score interval of a frequency ``k`` of ``n``."""
    if n <= 0:
        raise ValueError("no cases")
    p = k / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1.0 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


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


def crps_ensemble(x: FloatArray, y: FloatArray, fair: bool = False) -> FloatArray:
    """CRPS of each case's runs ``x`` (cases x runs) against the measured ``y``.

    ``fair`` gives the score an ensemble of unlimited size would be expected to
    get from the same distribution (Ferro 2014, Q. J. R. Meteorol. Soc. 140), so
    a 5-run reforecast and a 31-run forecast can be compared.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    m = x.shape[1]
    near = np.mean(np.abs(x - y[:, None]), axis=1)
    pair = np.abs(x[:, :, None] - x[:, None, :]).sum(axis=(1, 2))
    spread = pair / (2 * m * (m - 1)) if fair else pair / (2 * m * m)
    out: FloatArray = near - spread
    return out


def spread_term(sample: FloatArray) -> float:
    """``E|X - X'| / 2`` of a sample, from its sorted values (the CRPS spread term)."""
    s = np.sort(np.asarray(sample, dtype=np.float64))
    n = s.size
    return float(np.sum(s * (2 * np.arange(n) - n + 1)) / (n * n))


def crps_sample(sample: FloatArray, y: float, spread: float | None = None) -> float:
    """CRPS of a sample of past values (a climatology) against the measured ``y``."""
    s = np.asarray(sample, dtype=np.float64)
    return float(np.mean(np.abs(s - y)) - (spread_term(s) if spread is None else spread))


def skill_interval(
    score: FloatArray,
    ref: FloatArray,
    n: int = 2000,
    seed: int = 0,
    blocks: npt.ArrayLike | None = None,
) -> tuple[float, float] | None:
    """95 % interval of ``1 - mean(score) / mean(ref)`` from resampling the cases.

    Cases close in time are not independent (one front gives a run of similar
    cases), so with ``blocks`` (a label per case: its month, say) whole blocks
    are drawn together, the way they occurred; without, single cases.
    """
    score = np.asarray(score, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    if score.size < 2:
        return None
    if blocks is None:
        labels = np.arange(score.size)
    else:
        labels = np.unique(np.asarray(blocks), return_inverse=True)[1].ravel()
    m = int(labels.max()) + 1
    if m < 2:
        return None
    sum_score = np.bincount(labels, weights=score, minlength=m)
    sum_ref = np.bincount(labels, weights=ref, minlength=m)
    rng = np.random.default_rng(seed)
    i = rng.integers(0, m, size=(n, m))
    r = sum_ref[i].sum(axis=1)
    ok = r > 0
    if not ok.any():
        return None
    s = 1.0 - sum_score[i].sum(axis=1)[ok] / r[ok]
    return float(np.quantile(s, 0.025)), float(np.quantile(s, 0.975))
