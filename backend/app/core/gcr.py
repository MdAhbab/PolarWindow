"""Galactic cosmic rays: the spectrum, how the Sun modulates it, and the dose it gives
(plan track E).

Spectrum: Matthiä et al. (2013), "A ready-to-use galactic cosmic ray model",
Adv. Space Res. 51, 329-338 (doi:10.1016/j.asr.2012.09.022), a version of
ISO 15390 with one parameter W for the Sun's modulation, for nuclei Z = 1-28
above 10 MeV per nucleon. W is read from the Oulu neutron monitor's count rate,
W = -0.093 N + 638.7 with N in counts per minute (their equation). The element
constants (C, gamma, alpha, A) are the paper's table, as its reference
implementation (CosRayModifiedISO, DLR/Surrey) also carries them.

Dose: an absolute dose from a spectrum needs a transport code. Here the dose
rate comes from measurements (CRaTER in lunar orbit, Chang'e-4's LND on the
surface) and only the change with the Sun's modulation comes from the model:
each measured rate is scaled by the ratio of the model's energy deposit in a
thin silicon layer (Bethe stopping power, summed over Z = 1-28 above
10 MeV/n) now and at the measurement. The ratio is also checked in absolute
terms against CRaTER (docs/validation.md).

Surface shielding: on the surface the Moon hides half the sky; terrain above
the horizontal hides more. With the cosmic rays taken as arriving evenly from
every direction (isotropic), the site's share of the open sky is its skyline's
solid angle over 2 pi.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# Matthiä et al. 2013, per element Z = 1..28 (seven per line): A (mass number), C, gamma,
# alpha.
A_I = (
    1.0,
    4.0,
    6.9,
    9.0,
    10.8,
    12.0,
    14.0,
    16.0,
    19.0,
    20.2,
    23.0,
    24.3,
    27.0,
    28.1,
    31.0,
    32.1,
    35.4,
    39.9,
    39.1,
    40.1,
    44.9,
    47.9,
    50.9,
    52.0,
    54.9,
    55.8,
    58.9,
    58.7,
)
C_I = (
    18500.0,
    3690.0,
    19.5,
    17.7,
    49.2,
    103.0,
    36.7,
    87.4,
    3.19,
    16.4,
    4.43,
    19.3,
    4.17,
    13.4,
    1.15,
    3.06,
    1.3,
    2.33,
    1.87,
    2.17,
    0.74,
    2.63,
    1.23,
    2.12,
    1.14,
    9.32,
    0.1,
    0.48,
)
GAMMA_I = (
    2.74,
    2.77,
    2.82,
    3.05,
    2.96,
    2.76,
    2.89,
    2.7,
    2.82,
    2.76,
    2.84,
    2.7,
    2.77,
    2.66,
    2.89,
    2.71,
    3.0,
    2.93,
    3.05,
    2.77,
    2.97,
    2.99,
    2.94,
    2.89,
    2.74,
    2.63,
    2.63,
    2.63,
)
ALPHA_I = (
    2.85,
    3.12,
    3.41,
    4.3,
    3.93,
    3.18,
    3.77,
    3.11,
    4.05,
    3.11,
    3.14,
    3.65,
    3.46,
    3.0,
    4.04,
    3.3,
    4.4,
    4.33,
    4.49,
    2.93,
    3.78,
    3.79,
    3.5,
    3.28,
    3.29,
    3.01,
    4.25,
    3.52,
)
Z_MAX = 28
W_MIN, W_MAX = 0.0, 200.0
E_MIN_MEV_N = 10.0
E_MAX_MEV_N = 1.0e5

# Bethe stopping power in silicon.
K_MEV_CM2_MOL = 0.307075
SI_Z_OVER_A = 14.0 / 28.0855
SI_I_MEV = 173.0e-6
ME_C2_MEV = 0.51099895
MEV_PER_G_TO_GY = 1.602176634e-10


def w_from_oulu(counts_per_min: float) -> float:
    """Matthiä et al. (2013): W from the Oulu neutron monitor's corrected count rate."""
    return -0.093 * counts_per_min + 638.7


def _rest_gev(z: int) -> float:
    return 0.938 if z == 1 else 0.939


def flux(w: float, z: int, e_mev_n: FloatArray) -> FloatArray:
    """Differential flux of element ``z`` at kinetic energy per nucleon ``e_mev_n``:
    particles per (cm² s sr MeV/n). Valid for 0 <= W <= 200 and E >= 10 MeV/n."""
    if not W_MIN <= w <= W_MAX:
        raise ValueError(f"W must be within {W_MIN}-{W_MAX}, got {w}")
    if not 1 <= z <= Z_MAX:
        raise ValueError(f"Z must be within 1-{Z_MAX}")
    i = z - 1
    a = A_I[i]
    m = _rest_gev(z)
    x = np.asarray(e_mev_n, dtype=np.float64) * 1e-3  # GeV/n
    p = np.sqrt(x * (x + 2.0 * m))
    rigidity = a / z * p  # GV
    beta = p / (x + m)
    r0 = 0.37 + 3.0e-4 * w**1.45
    delta = 0.02 * w + 4.7
    phi = (
        C_I[i] * beta ** ALPHA_I[i] / rigidity ** GAMMA_I[i] * (rigidity / (rigidity + r0)) ** delta
    )
    return np.asarray(1e-4 * phi * a / z * 1e-3 / beta, dtype=np.float64)


def stopping_si(z: int, e_mev_n: FloatArray) -> FloatArray:
    """Bethe mass stopping power of a fully stripped nucleus in silicon, MeV cm²/g
    (no shell or density corrections: used for ratios and a coarse absolute check)."""
    m_n = _rest_gev(z) * 1e3
    gamma = 1.0 + np.asarray(e_mev_n, dtype=np.float64) / m_n
    beta2 = 1.0 - 1.0 / gamma**2
    arg = 2.0 * ME_C2_MEV * beta2 * gamma**2 / SI_I_MEV
    return np.asarray(
        K_MEV_CM2_MOL * z**2 * SI_Z_OVER_A / beta2 * (np.log(arg) - beta2), dtype=np.float64
    )


def _grid(n: int = 400) -> FloatArray:
    return np.geomspace(E_MIN_MEV_N, E_MAX_MEV_N, n)


def thin_si_dose_gy_s(w: float) -> float:
    """Dose rate in a thin, unshielded silicon layer in free space (4 pi sr), Gy/s,
    from nuclei Z = 1-28 above 10 MeV/n."""
    e = _grid()
    total = 0.0
    for z in range(1, Z_MAX + 1):
        # flux per (MeV/n) integrated over MeV/n: particles per cm² s sr; stopping
        # power depends on the speed (MeV/n) and z² only.
        integrand = 4.0 * math.pi * flux(w, z, e) * stopping_si(z, e)
        total += float(np.trapezoid(integrand, e))
    return total * MEV_PER_G_TO_GY


def dose_ratio(w: float, w_ref: float) -> float:
    """How much the dose at modulation ``w`` differs from that at ``w_ref``."""
    return thin_si_dose_gy_s(w) / thin_si_dose_gy_s(w_ref)


def open_sky_fraction(el_deg: npt.NDArray[np.floating[Any]]) -> float:
    """Solid angle of the sky above a skyline (one elevation per equal azimuth bin),
    over 2 pi: 1 for a flat horizon, less where terrain rises, more where it falls
    away. Cosmic rays taken as arriving evenly from every direction."""
    el = np.radians(np.clip(np.asarray(el_deg, dtype=np.float64), -90.0, 90.0))
    return float(np.mean(1.0 - np.sin(el)))
