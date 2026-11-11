"""Surface-to-surface mesh fallback (ADR-23). Pure: arrays and numbers in, numbers out.

This module evaluates the physics and routing rules on figures entered by the caller;
it is a conditional calculation on those inputs, not a prediction of any flight radio
or mission. When a rover loses its direct link to Earth, can a peer that still has one
pass its data on, without the peer being harmed? Four parts, each usable alone:

1. **Radio link.** Two-ray ground-reflection path loss over regolith (Fresnel
   reflection coefficient for the stated polarisation and relative permittivity),
   against free space; received power; signal-to-noise from the bandwidth and noise
   figure; the link closes when the SNR reaches an entered threshold. Throughput is
   the Shannon bound ``B log2(1 + SNR)`` and is an **upper bound**: no coding or
   modulation scheme reaches it. Every radio figure is an input.
2. **Radio state machine** per node: ``deep_sleep`` while the node's own direct link
   to Earth is healthy and it is not forwarding peer traffic; ``standby`` once its
   direct link is lost (both while counting the loss up to the wake threshold and
   afterwards whenever no usable mesh route carries traffic); ``active_relay`` only
   while the node is actively sending over a mesh route after the loss has exceeded
   the threshold, or while it is forwarding peer data as a helper; and back to
   ``deep_sleep`` when the direct link is healthy and no peer traffic is forwarded.
3. **Helper guard.** A helper forwards only while it is sunlit, its charge is at or
   above the cut-off, its forwarding energy this lunar day is within its share of the
   battery, and the forwarding power is within the cap. Forwarded data gets only the
   link capacity left after the helper's own traffic. A ring buffer holds waiting
   peer data; overflow is dropped and counted.
4. **Routing.** Minimum transmit energy per bit over the usable links (Dijkstra) from
   an isolated node to a node that has a direct link.

The Moon has no atmosphere, so the loss between two nodes is the geometry's: the
terrain decides whether the path exists (``viewshed``) and the ground reflection
decides what it costs.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

from app.core import viewshed
from app.core.horizon import TerrainSampler

FloatArray = npt.NDArray[np.float64]

C_M_S: Final[float] = viewshed.C_M_S
#: Thermal noise density kT0 at the 290 K reference temperature of the noise-figure
#: convention (IEEE), dBm/Hz: 10 log10(1.380649e-23 * 290 * 1000).
THERMAL_NOISE_DBM_HZ: Final[float] = -173.975
#: The synodic month (one lunar day and night), seconds. NASA Moon fact sheet: 29.53 d.
LUNAR_DAY_S: Final[float] = 29.530589 * 86_400.0

Polarisation = Literal["horizontal", "vertical"]

# ---------------------------------------------------------------------------
# 1. The radio link
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Radio:
    """The mesh radio. Every figure is entered; nothing here has a default."""

    frequency_hz: float
    tx_power_w: float  # a node's own transmitter
    forwarding_tx_power_w: float  # a helper's transmitter while it forwards
    tx_efficiency: float  # RF output over DC input, 0..1
    antenna_gain_dbi: float  # at each end
    bandwidth_hz: float
    noise_figure_db: float
    snr_threshold_db: float
    eps_r: float
    polarisation: Polarisation

    def __post_init__(self) -> None:
        if not 0.0 < self.tx_efficiency <= 1.0:
            raise ValueError("tx_efficiency must be in (0, 1]")
        if self.frequency_hz <= 0 or self.bandwidth_hz <= 0:
            raise ValueError("frequency and bandwidth must be positive")
        if self.tx_power_w <= 0 or self.forwarding_tx_power_w <= 0:
            raise ValueError("transmit powers must be positive")
        if self.eps_r < 1.0:
            raise ValueError("relative permittivity is at least 1")


def wavelength_m(frequency_hz: float) -> float:
    return C_M_S / frequency_hz


def free_space_loss_db(r_m: FloatArray | float, frequency_hz: float) -> FloatArray:
    """``20 log10(4 pi r / lambda)`` over the slant range ``r``."""
    r = np.asarray(r_m, dtype=np.float64)
    return np.asarray(20.0 * np.log10(4.0 * math.pi * r / wavelength_m(frequency_hz)))


def reflection_coefficient(
    eps_r: float, grazing_rad: FloatArray | float, polarisation: Polarisation
) -> FloatArray:
    """Fresnel reflection coefficient of a smooth lossless dielectric at a grazing angle.

    Horizontal (perpendicular) polarisation: ``(sin p - sqrt(e - cos^2 p)) / (sin p +
    sqrt(e - cos^2 p))``; vertical (parallel): the same with ``e sin p`` in place of
    ``sin p``. Both tend to -1 at grazing incidence.
    """
    psi = np.asarray(grazing_rad, dtype=np.float64)
    s, c = np.sin(psi), np.cos(psi)
    root = np.sqrt(eps_r - c * c + 0j)
    top = eps_r * s if polarisation == "vertical" else s
    return np.real((top - root) / (top + root))


def break_distance_m(h1_m: float, h2_m: float, frequency_hz: float) -> float:
    """``4 h1 h2 / lambda``: beyond it the two-ray loss falls as d^4, not d^2."""
    return 4.0 * h1_m * h2_m / wavelength_m(frequency_hz)


def two_ray_loss_db(
    d_m: FloatArray | float,
    h1_m: float,
    h2_m: float,
    frequency_hz: float,
    eps_r: float,
    polarisation: Polarisation,
) -> FloatArray:
    """Path loss, dB, between antennas ``h1`` and ``h2`` above flat ground ``d`` apart.

    ``PL = -20 log10( (lambda / 4 pi) |1/r1 + R exp(-j k (r2 - r1)) / r2| )`` with the
    direct path ``r1`` and the ground-reflected path ``r2``. Near the antennas the two
    rays beat against each other (nulls and peaks around free space); beyond the break
    distance they cancel to a ``d^-4`` power law.
    """
    d = np.maximum(np.asarray(d_m, dtype=np.float64), 1e-3)
    lam = wavelength_m(frequency_hz)
    r1 = np.hypot(d, h1_m - h2_m)
    r2 = np.hypot(d, h1_m + h2_m)
    r_coef = reflection_coefficient(eps_r, np.arctan2(h1_m + h2_m, d), polarisation)
    field = 1.0 / r1 + r_coef * np.exp(-2j * math.pi * (r2 - r1) / lam) / r2
    mag = np.maximum(np.abs(field), 1e-30)
    return np.asarray(-20.0 * np.log10(lam / (4.0 * math.pi) * mag))


@dataclass(frozen=True, slots=True)
class LinkBudget:
    path_loss_db: float
    free_space_db: float
    rx_dbm: float
    noise_dbm: float
    snr_db: float
    closes: bool
    shannon_bps: float  # an upper bound


def noise_dbm(radio: Radio) -> float:
    return THERMAL_NOISE_DBM_HZ + 10.0 * math.log10(radio.bandwidth_hz) + radio.noise_figure_db


def shannon_bps(bandwidth_hz: float, snr_db: float) -> float:
    return bandwidth_hz * math.log2(1.0 + 10.0 ** (snr_db / 10.0))


def link_budget(
    radio: Radio, d_m: float, h1_m: float, h2_m: float, tx_power_w: float
) -> LinkBudget:
    pl = float(
        two_ray_loss_db(d_m, h1_m, h2_m, radio.frequency_hz, radio.eps_r, radio.polarisation)
    )
    fs = float(free_space_loss_db(math.hypot(d_m, h1_m - h2_m), radio.frequency_hz))
    rx = 10.0 * math.log10(tx_power_w * 1000.0) + 2.0 * radio.antenna_gain_dbi - pl
    nz = noise_dbm(radio)
    snr = rx - nz
    return LinkBudget(
        path_loss_db=pl,
        free_space_db=fs,
        rx_dbm=rx,
        noise_dbm=nz,
        snr_db=snr,
        closes=snr >= radio.snr_threshold_db,
        shannon_bps=shannon_bps(radio.bandwidth_hz, snr),
    )


def first_failing_range_m(
    radio: Radio, h1_m: float, h2_m: float, tx_power_w: float, *, max_m: float = 100_000.0
) -> float | None:
    """The nearest distance at which the link stops closing, scanning outward; None if it
    still closes at ``max_m``. Taken as the first failure, not the last success: the
    ground reflection makes the loss ripple, and a node should not plan on a lucky peak."""
    d = np.geomspace(1.0, max_m, 4000)
    pl = two_ray_loss_db(d, h1_m, h2_m, radio.frequency_hz, radio.eps_r, radio.polarisation)
    snr = 10.0 * math.log10(tx_power_w * 1000.0) + 2.0 * radio.antenna_gain_dbi - pl
    snr = snr - noise_dbm(radio)
    bad = np.nonzero(snr < radio.snr_threshold_db)[0]
    return float(d[bad[0]]) if bad.size else None


def energy_per_bit_j(tx_power_w: float, tx_efficiency: float, rate_bps: float) -> float:
    """DC energy to send one bit at ``rate_bps``: a lower bound, since the rate is."""
    return tx_power_w / tx_efficiency / rate_bps


# ---------------------------------------------------------------------------
# Terrain path between two nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PathTerrain:
    distance_m: float
    sight: str  # clear / uncertain / blocked
    radio: str  # first Fresnel zone: clear / uncertain / blocked


def terrain_between(
    sample_h: TerrainSampler,
    sample_sigma: TerrainSampler,
    a_xy: tuple[float, float],
    b_xy: tuple[float, float],
    h_a_m: float,
    h_b_m: float,
    frequency_hz: float,
    post_m: float,
) -> PathTerrain:
    """Line of sight and first-Fresnel-zone clearance from node A's antenna to node B's,
    over the terrain, by ``viewshed.compute`` on a single bearing and range, taken with
    the worse of the two directions."""
    worst_sight, worst_radio = viewshed.CLEAR, viewshed.CLEAR
    dist = math.hypot(b_xy[0] - a_xy[0], b_xy[1] - a_xy[1])
    if dist <= 0.0:
        return PathTerrain(0.0, "clear", "clear")
    for p, q, hp, hq in ((a_xy, b_xy, h_a_m, h_b_m), (b_xy, a_xy, h_b_m, h_a_m)):
        px, py = p

        def sh(x: FloatArray, y: FloatArray, px: float = px, py: float = py) -> FloatArray:
            return sample_h(x + px, y + py)

        def sg(x: FloatArray, y: FloatArray, px: float = px, py: float = py) -> FloatArray:
            return sample_sigma(x + px, y + py)

        brg = math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) % 360.0
        v = viewshed.compute(
            sh,
            sg,
            bearings_deg=np.array([brg]),
            ranges_m=np.array([dist]),
            lander_antenna_m=hp,
            rover_antenna_m=hq,
            frequency_hz=frequency_hz,
            post_m=post_m,
        )
        worst_sight = min(worst_sight, int(v.sight[0, 0]))
        worst_radio = min(worst_radio, int(v.radio[0, 0]))
    return PathTerrain(dist, viewshed.STATE_WORDS[worst_sight], viewshed.STATE_WORDS[worst_radio])


# ---------------------------------------------------------------------------
# 2. The radio state machine
# ---------------------------------------------------------------------------


class RadioState(StrEnum):
    DEEP_SLEEP = "deep_sleep"
    STANDBY = "standby"
    ACTIVE_RELAY = "active_relay"


@dataclass(frozen=True, slots=True)
class Transition:
    index: int
    t_s: float
    from_state: RadioState
    to_state: RadioState


def seeking_relay(
    t_s: FloatArray, healthy: npt.NDArray[np.bool_], threshold_s: float
) -> npt.NDArray[np.bool_]:
    """True where the direct link has been unhealthy for longer than ``threshold_s``."""
    out = np.zeros(len(t_s), dtype=bool)
    lost_since: float | None = None
    for i, (t, ok) in enumerate(zip(t_s, healthy, strict=True)):
        if ok:
            lost_since = None
        else:
            if lost_since is None:
                lost_since = float(t)
            out[i] = float(t) - lost_since > threshold_s
    return out


def run_state_machine(
    t_s: FloatArray,
    healthy: npt.NDArray[np.bool_],
    threshold_s: float,
    *,
    usable_route: npt.NDArray[np.bool_] | None = None,
    forwarding: npt.NDArray[np.bool_] | None = None,
) -> tuple[list[RadioState], list[Transition]]:
    """States at each sample, and the changes between them.

    A loss is counted from the first sample at which the direct link is not healthy
    (a loss already there at the window's start is counted from the start, so the
    time to wake is then a late estimate). The radio is in ``deep_sleep`` while the
    direct link is healthy and the node is not forwarding peer data. Once the direct
    link is lost, the radio enters ``standby`` and stays in ``standby`` whenever no
    usable mesh route carries traffic; it enters ``active_relay`` only while the loss
    has lasted *longer than* ``threshold_s`` and ``usable_route`` holds (or while
    ``forwarding`` holds for a helper relaying peer traffic).
    """
    seek = seeking_relay(t_s, healthy, threshold_s)
    states: list[RadioState] = []
    events: list[Transition] = []
    for i, (t, ok, sk) in enumerate(zip(t_s, healthy, seek, strict=True)):
        fwd = False if forwarding is None else bool(forwarding[i])
        route_ok = True if usable_route is None else bool(usable_route[i])
        if fwd:
            s = RadioState.ACTIVE_RELAY
        elif ok:
            s = RadioState.DEEP_SLEEP
        else:
            s = RadioState.ACTIVE_RELAY if (sk and route_ok) else RadioState.STANDBY
        if states and states[-1] != s:
            events.append(Transition(i, float(t), states[-1], s))
        states.append(s)
    return states, events


# ---------------------------------------------------------------------------
# 3. The helper guard
# ---------------------------------------------------------------------------

RULE_NIGHT: Final[str] = "night"
RULE_LOW_CHARGE: Final[str] = "charge_below_cutoff"
RULE_QUOTA: Final[str] = "energy_quota"
RULE_POWER_CAP: Final[str] = "power_cap"
RULES: Final[tuple[str, ...]] = (RULE_NIGHT, RULE_LOW_CHARGE, RULE_QUOTA, RULE_POWER_CAP)


def guard_refusal(
    *,
    sunlit: bool,
    soc_fraction: float,
    soc_cutoff_fraction: float,
    energy_today_wh: float,
    quota_wh: float,
    forwarding_power_w: float,
    power_cap_w: float,
) -> str | None:
    """The first rule that forbids forwarding right now, or None when all hold."""
    if not sunlit:
        return RULE_NIGHT
    if soc_fraction < soc_cutoff_fraction:
        return RULE_LOW_CHARGE
    if energy_today_wh >= quota_wh:
        return RULE_QUOTA
    if forwarding_power_w > power_cap_w:
        return RULE_POWER_CAP
    return None


def spare_capacity_bps(link_bps: float, own_traffic_bps: float) -> float:
    """What strict priority leaves for forwarded data: the helper's own traffic is served first."""
    return max(0.0, link_bps - own_traffic_bps)


@dataclass(frozen=True, slots=True)
class RelayStep:
    sent_bits: float
    dropped_bits: float
    buffer_bits: float


def relay_step(
    *, buffer_bits: float, inflow_bits: float, out_bits: float, buffer_cap_bits: float
) -> RelayStep:
    """One step of a helper's ring buffer: peer data arrives, as much as the spare
    capacity and the energy allow is sent, and what does not fit the buffer is dropped."""
    held = buffer_bits + inflow_bits
    sent = min(held, max(0.0, out_bits))
    held -= sent
    dropped = max(0.0, held - buffer_cap_bits)
    return RelayStep(sent, dropped, held - dropped)


# ---------------------------------------------------------------------------
# 4. Routing
# ---------------------------------------------------------------------------


def min_energy_path(
    edges: dict[str, dict[str, float]],
    source: str,
    targets: set[str],
    usable: set[str],
) -> tuple[list[str], float] | None:
    """Cheapest path ``source -> ... -> target`` by Dijkstra, summing per-edge energy per bit.

    ``edges[u][v]`` is the cost of ``u`` sending to ``v``; an edge exists only where the
    caller put one. Every node after the source must be in ``usable``. Returns the path
    and its total cost, or None.
    """
    best = {source: 0.0}
    prev: dict[str, str] = {}
    heap: list[tuple[float, str]] = [(0.0, source)]
    while heap:
        cost, u = heapq.heappop(heap)
        if cost > best.get(u, math.inf):
            continue
        if u != source and u in targets:
            path = [u]
            while path[-1] != source:
                path.append(prev[path[-1]])
            return path[::-1], cost
        for v, w in edges.get(u, {}).items():
            if v != source and v not in usable:
                continue
            c = cost + w
            if c < best.get(v, math.inf):
                best[v] = c
                prev[v] = u
                heapq.heappush(heap, (c, v))
    return None


def longest_run(t_s: FloatArray, flag: npt.NDArray[np.bool_]) -> tuple[float, float | None, bool]:
    """Longest stretch of consecutive steps with ``flag`` true, as ``(seconds, start_s, open)``.

    Step ``i`` stands for ``[t_i, t_i+1)``; the last sample ends the window and stands for
    nothing. ``open`` means the stretch touches the window's start or end, so it is a lower
    bound on the outage.
    """
    n = len(t_s) - 1
    best, best_start, best_open = 0.0, None, False
    i = 0
    while i < n:
        if not flag[i]:
            i += 1
            continue
        j = i
        while j < n and flag[j]:
            j += 1
        length = float(t_s[j] - t_s[i])
        if length > best:
            best, best_start, best_open = length, float(t_s[i]), (i == 0 or j == n)
        i = j
    return best, best_start, best_open


def intervals[T](values: list[T]) -> list[tuple[int, int, T]]:
    """Run-length encode: ``(first_index, last_index_exclusive, value)``."""
    out: list[tuple[int, int, T]] = []
    for i, v in enumerate(values):
        if out and out[-1][2] == v:
            out[-1] = (out[-1][0], i + 1, v)
        else:
            out.append((i, i + 1, v))
    return out


def skyline_at(mask_az_deg: FloatArray, mask_el_deg: FloatArray, az_deg: FloatArray) -> FloatArray:
    """A partial skyline (bearings in any order) read at other bearings, wrapping at 360."""
    order = np.argsort(np.mod(mask_az_deg, 360.0))
    return np.asarray(
        np.interp(
            np.mod(az_deg, 360.0),
            np.mod(mask_az_deg, 360.0)[order],
            np.asarray(mask_el_deg, dtype=np.float64)[order],
            period=360.0,
        )
    )


def needed_azimuths(
    az_tracks_deg: list[FloatArray], step_deg: float, margin_deg: float
) -> FloatArray:
    """The grid bearings (multiples of ``step_deg``) that the given tracks pass through,
    widened by ``margin_deg`` each side, so a skyline is marched only where it is read."""
    n = int(round(360.0 / step_deg))
    keep = np.zeros(n, dtype=bool)
    pad = int(math.ceil(margin_deg / step_deg))
    for az in tracks_az(az_tracks_deg):
        k = int(round((az % 360.0) / step_deg))
        for j in range(-pad, pad + 1):
            keep[(k + j) % n] = True
    return np.nonzero(keep)[0].astype(np.float64) * step_deg


def tracks_az(tracks: list[FloatArray]) -> FloatArray:
    """Bearings on the 0.05 degree grid actually visited by the tracks (de-duplicated)."""
    if not tracks:
        return np.zeros(0)
    allaz = np.concatenate([np.mod(np.asarray(t, dtype=np.float64), 360.0) for t in tracks])
    return np.asarray(np.unique(np.round(allaz, 1)), dtype=np.float64)
