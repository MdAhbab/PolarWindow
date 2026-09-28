"""U.S. Standard Atmosphere, 1976 (NOAA/NASA/USAF, NASA TM-X-74335): air density with
height, for capsule entry (plan track H).

Up to 86 km the standard is defined by seven layers of linear molecular-scale
temperature in geopotential height, from which pressure and density follow in
closed form (its equations 23, 33a, 33b and 42). Above 86 km the standard is
defined through the diffusion of each gas; its tabulated densities (Table I)
are used here, interpolated in the logarithm, up to 150 km. Higher up the drag
is left out: the density there is below 2.1e-9 kg/m^3, and a capsule's flight
starts at the entry interface, 121.9 km.
"""

from __future__ import annotations

import math

import numpy as np

G0 = 9.80665  # m/s^2
R_STAR = 8.31432e3  # J/(kmol K), the standard's gas constant
M0 = 28.9644  # kg/kmol, sea-level mean molecular weight
R0_M = 6_356_766.0  # the standard's effective Earth radius for geopotential height
T0 = 288.15
P0 = 101_325.0
#: Base geopotential heights (m') and molecular-scale temperature gradients (K/m').
H_B = (0.0, 11_000.0, 20_000.0, 32_000.0, 47_000.0, 51_000.0, 71_000.0, 84_852.0)
L_B = (-6.5e-3, 0.0, 1.0e-3, 2.8e-3, 0.0, -2.8e-3, -2.0e-3)
TOP_LOWER_M = 86_000.0


def _bases() -> tuple[list[float], list[float]]:
    t = [T0]
    p = [P0]
    k = G0 * M0 / R_STAR
    for i, lb in enumerate(L_B):
        dh = H_B[i + 1] - H_B[i]
        tb, pb = t[-1], p[-1]
        t_next = tb + lb * dh
        p_next = pb * math.exp(-k * dh / tb) if lb == 0.0 else pb * (tb / t_next) ** (k / lb)
        t.append(t_next)
        p.append(p_next)
    return t, p


T_B, P_B = _bases()

#: Table I of the standard from 86 to 150 km (its pages 68-69): geometric height (km),
#: density (kg/m^3).
UPPER_KM_RHO: tuple[tuple[float, float], ...] = (
    (86, 6.958e-06),
    (86.5, 6.366e-06),
    (87, 5.824e-06),
    (87.5, 5.328e-06),
    (88, 4.875e-06),
    (88.5, 4.46e-06),
    (89, 4.081e-06),
    (89.5, 3.734e-06),
    (90, 3.416e-06),
    (90.5, 3.126e-06),
    (91, 2.86e-06),
    (91.5, 2.616e-06),
    (92, 2.393e-06),
    (92.5, 2.188e-06),
    (93, 2e-06),
    (93.5, 1.828e-06),
    (94, 1.67e-06),
    (94.5, 1.526e-06),
    (95, 1.393e-06),
    (95.5, 1.273e-06),
    (96, 1.162e-06),
    (96.5, 1.061e-06),
    (97, 9.685e-07),
    (97.5, 8.842e-07),
    (98, 8.071e-07),
    (98.5, 7.367e-07),
    (99, 6.725e-07),
    (99.5, 6.139e-07),
    (100, 5.604e-07),
    (101, 4.695e-07),
    (102, 3.935e-07),
    (103, 3.3e-07),
    (104, 2.769e-07),
    (105, 2.325e-07),
    (106, 1.954e-07),
    (107, 1.643e-07),
    (108, 1.381e-07),
    (109, 1.161e-07),
    (110, 9.708e-08),
    (111, 8.111e-08),
    (112, 6.838e-08),
    (113, 5.811e-08),
    (114, 4.975e-08),
    (115, 4.289e-08),
    (116, 3.72e-08),
    (117, 3.246e-08),
    (118, 2.847e-08),
    (119, 2.509e-08),
    (120, 2.222e-08),
    (121, 1.977e-08),
    (122, 1.767e-08),
    (123, 1.585e-08),
    (124, 1.428e-08),
    (125, 1.291e-08),
    (126, 1.171e-08),
    (127, 1.065e-08),
    (128, 9.717e-09),
    (129, 8.889e-09),
    (130, 8.152e-09),
    (131, 7.494e-09),
    (132, 6.904e-09),
    (133, 6.374e-09),
    (134, 5.897e-09),
    (135, 5.465e-09),
    (136, 5.074e-09),
    (137, 4.719e-09),
    (138, 4.396e-09),
    (139, 4.101e-09),
    (140, 3.831e-09),
    (141, 3.584e-09),
    (142, 3.358e-09),
    (143, 3.15e-09),
    (144, 2.958e-09),
    (145, 2.781e-09),
    (146, 2.618e-09),
    (147, 2.466e-09),
    (148, 2.326e-09),
    (149, 2.196e-09),
    (150, 2.076e-09),
)


def geopotential_m(z_m: float) -> float:
    return R0_M * z_m / (R0_M + z_m)


def lower(z_m: float) -> tuple[float, float, float]:
    """(molecular-scale temperature K, pressure Pa, density kg/m^3) at geometric height
    ``z_m`` from 0 to 86 km."""
    h = geopotential_m(min(max(z_m, 0.0), TOP_LOWER_M))
    i = max(k for k in range(len(L_B)) if H_B[k] <= h)
    lb, tb, pb = L_B[i], T_B[i], P_B[i]
    dh = h - H_B[i]
    tm = tb + lb * dh
    k = G0 * M0 / R_STAR
    p = pb * math.exp(-k * dh / tb) if lb == 0.0 else pb * (tb / tm) ** (k / lb)
    return tm, p, p * M0 / (R_STAR * tm)


_KS = np.array([z for z, _ in UPPER_KM_RHO])
_LOG_RHO = np.log([r for _, r in UPPER_KM_RHO])


def density(z_m: float) -> float:
    """Air density, kg/m^3, at geometric height ``z_m`` (0 above 150 km)."""
    if z_m <= TOP_LOWER_M:
        return lower(z_m)[2]
    z_km = z_m / 1000.0
    if z_km > _KS[-1]:
        return 0.0
    return float(math.exp(np.interp(z_km, _KS, _LOG_RHO)))
