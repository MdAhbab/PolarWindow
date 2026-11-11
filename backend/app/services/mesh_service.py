"""Surface-to-surface mesh fallback at a site (ADR-23). Computes on the request; stores nothing.

Takes Earth's and the Sun's tracks from ``site_service.compute``, the nodes' positions,
antennas, batteries and traffic from the caller, and one radio block, and asks: when a
node loses its direct link to Earth, can a peer relay for it, and what does that cost the
peer? Every figure is an input (nothing here has a default); the answer says so.

Two terrain grids are used: a node at the site origin ``(0, 0)`` reuses the site's
far-horizon mask described in ``meta.resolution`` (1440 bearings to 50 km on the 20 m
regional DEM), whereas nodes away from ``(0, 0)`` and all surface-to-surface links use
the local DEM patch described in the ``terrain`` block (5 m post spacing where covered,
20 m otherwise, with partial skylines marched to 20 km at 0.5 deg over the bearings
Earth's and the Sun's tracks pass through).

Surface-to-surface links are tested by straight-line sight between the antennas against
the local DEM's height error; first-Fresnel-zone clearance is reported beside it in
``links[]`` without gating ``usable``, because flat-ground reflection inside the first
Fresnel zone between low antennas is already in the two-ray path loss. The simulation
is run twice: the primary run uses only links whose line of sight is ``clear``, and a
conditional second run also allows links whose line of sight is ``uncertain`` (within
the DEM's height error) to populate ``with_mesh_if_uncertain_links_hold`` alone.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import mesh as core
from app.core import visibility
from app.core.horizon import TerrainSampler, build_mask
from app.core.quantity import Quantity
from app.data import rover_terrain
from app.data.lola import DemTile, make_samplers
from app.services import site_service
from app.services.lifecycle import q

FloatArray = npt.NDArray[np.float64]

MAX_NODES = 6
MAX_POSITIONS = 12
MAX_WAYPOINTS = 8
MAX_STEPS = 6000
MAX_RADIUS_M = 5000.0
#: Bearings of a node's partial skyline: step, widening around the tracks, and range.
NODE_AZ_STEP_DEG = 0.5
NODE_AZ_MARGIN_DEG = 1.0
NODE_MAX_RANGE_M = 20_000.0

NOT_MODELLED = [
    "Peer data is not retransmitted in a time-slotted schedule: capacity is shared by strict "
    "priority per step, and the Shannon bound is an upper bound, so throughput is too and the "
    "energy per bit a lower bound. No LTE or 5G modulation and coding table is applied.",
    "A helper's charge falls only by the forwarding energy counted here: its own loads and "
    "its solar charging are not modelled, so a charge cut-off is reached later than it would "
    "be in flight.",
    "Receive and idle-listening power, wake-up and discovery signalling, and handshake time: "
    "standby and isolated listening draw 0 W here, and only transmitted or forwarded bits "
    "spend battery energy.",
    "The Earth-uplink energy and rate of an exit node are counted only if its uplink figures "
    "are entered; otherwise its uplink is taken as neither limiting nor costing energy.",
    "Data buffered in a helper that is no longer on any route is not drained.",
    "Ground reflection and diffraction off the actual terrain: the two-ray model reflects from "
    "one flat plane of the stated permittivity at the antennas' common height reference, which "
    "is why the first Fresnel zone is reported in the links table without gating a link; rough "
    "or sloping ground, rocks and knife-edge diffraction where terrain intrudes into the "
    "Fresnel zone without blocking the line of sight are not in the loss (a ridge that blocks "
    "the line of sight blocks the link).",
    "Delay-tolerant bundle handling (custody, retransmission, expiry): data is moved or "
    "dropped by the buffer rule only; light-time and queueing delay are not computed.",
    "Rover motion between waypoints: a node sits at each waypoint until the next.",
    "Interference between nodes and the lander's antenna pattern; antennas are isotropic "
    "with the entered gain at both ends.",
]


class BadMesh(ValueError):
    def __init__(self, field_name: str, why: str) -> None:
        super().__init__(f"{field_name}: {why}")
        self.field = field_name
        self.why = why


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Terrain:
    sample: TerrainSampler
    sigma: TerrainSampler
    post_m: float
    products: list[str]
    vertical_error_m: float


@lru_cache(maxsize=2)
def _tile(path: Path, stamp: int) -> DemTile:
    return DemTile.load(path)


def _terrain(site_id: str, lat: float, lon: float, radius_m: float) -> Terrain:
    s = get_settings()
    path = rover_terrain.terrain_path(site_id, lat, lon, radius_m)
    coarse_path = s.regional_dem_path
    coarse = _tile(coarse_path, coarse_path.stat().st_mtime_ns)
    fine = None if path == coarse_path else _tile(path, path.stat().st_mtime_ns)
    sample, sigma = make_samplers(lat, lon, fine, coarse)
    src = fine if fine is not None else coarse
    products = [src.product] + ([coarse.product] if fine is not None else [])
    return Terrain(sample, sigma, src.scale_m, products, src.vertical_error_m)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Node:
    id: str
    name: str
    waypoints: list[tuple[float, float, float]]  # (t_s, east_m, north_m), by t_s
    antenna_m: float
    capacity_wh: float
    soc0: float
    own_bps: float
    may_help: bool
    uplink_bps: float | None
    uplink_w: float | None


def _node(d: dict[str, Any]) -> Node:
    wp = d.get("waypoints")
    if wp:
        pts = sorted((float(w["t_s"]), float(w["east_m"]), float(w["north_m"])) for w in wp)
    else:
        pos = d.get("position")
        if pos is None:
            raise BadMesh(f"nodes.{d['id']}.position", "give a position or waypoints")
        pts = [(0.0, float(pos["east_m"]), float(pos["north_m"]))]
    if len(pts) > MAX_WAYPOINTS:
        raise BadMesh(f"nodes.{d['id']}.waypoints", f"at most {MAX_WAYPOINTS} waypoints")
    return Node(
        id=str(d["id"]),
        name=str(d.get("name") or d["id"]),
        waypoints=pts,
        antenna_m=float(d["antenna_height_m"]),
        capacity_wh=float(d["battery_capacity_wh"]),
        soc0=float(d["initial_soc_fraction"]),
        own_bps=float(d["own_traffic_bps"]),
        may_help=bool(d["may_help"]),
        uplink_bps=None if d.get("earth_uplink_bps") is None else float(d["earth_uplink_bps"]),
        uplink_w=None
        if d.get("earth_uplink_power_w") is None
        else float(d["earth_uplink_power_w"]),
    )


def _pos_key(e: float, n: float) -> tuple[float, float]:
    return (round(e, 1), round(n, 1))


def _entered(value: float | str | bool, unit: str, who: str = "entered in the request") -> Any:
    return q(
        Quantity(
            value=float(value),
            unit=unit,
            provenance="entered",
            source=who,
            no_margin_reason="taken as entered; the figure has no margin of its own",
        )
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


async def simulate(
    session: AsyncSession,
    site_id: str,
    start: datetime,
    end: datetime,
    step_s: int,
    nodes: list[dict[str, Any]],
    radio: dict[str, Any],
    guard: dict[str, Any],
    loss_threshold_s: float,
) -> dict[str, Any]:
    ns = [_node(d) for d in nodes]
    if not ns:
        raise BadMesh("nodes", "give at least one node")
    if len(ns) > MAX_NODES:
        raise BadMesh("nodes", f"at most {MAX_NODES} nodes")
    if len({n.id for n in ns}) != len(ns):
        raise BadMesh("nodes", "node ids must be distinct")
    positions = {_pos_key(e, n) for nd in ns for (_t, e, n) in nd.waypoints}
    if len(positions) > MAX_POSITIONS:
        raise BadMesh("nodes", f"at most {MAX_POSITIONS} distinct positions in all")
    radius = max(math.hypot(*p) for p in positions)
    if radius > MAX_RADIUS_M:
        raise BadMesh("nodes", f"positions must be within {MAX_RADIUS_M:g} m of the site")
    for nd in ns:
        if not (0.0 < nd.soc0 <= 1.0 and nd.capacity_wh > 0 and nd.own_bps >= 0):
            raise BadMesh(f"nodes.{nd.id}", "battery and traffic figures out of range")
        if not 0.0 <= nd.antenna_m <= 50.0:
            raise BadMesh(f"nodes.{nd.id}.antenna_height_m", "between 0 and 50 m")
    try:
        rad = core.Radio(**radio)
    except (TypeError, ValueError) as exc:
        raise BadMesh("radio", str(exc)) from exc
    cw = await site_service.compute(session, site_id, start, end, step_s)
    if len(cw.result.earth.t_s) > MAX_STEPS:
        raise BadMesh("step_s", f"at most {MAX_STEPS} steps; use a longer step or a shorter window")
    return await asyncio.to_thread(_both, cw, ns, rad, guard, float(loss_threshold_s), radius)


@dataclass(slots=True)
class _Skies:
    earth_ok: npt.NDArray[np.bool_]
    earth_uncertain: npt.NDArray[np.bool_]
    sunlit: npt.NDArray[np.bool_]


def _skies(
    cw: site_service.ComputedWindow,
    terrain: Terrain,
    pos: tuple[float, float],
) -> _Skies:
    """Is Earth in clear view, and is the Sun up, at each step from this position."""
    earth, sun = cw.result.earth, cw.result.sun
    if pos == (0.0, 0.0):
        m = cw.mask_record.mask
        az = np.arange(m.azimuth_count, dtype=np.float64) * m.azimuth_step_deg
        el = np.asarray(m.el_deg, dtype=np.float64)
    else:
        ax, ay = pos

        def sh(x: FloatArray, y: FloatArray) -> FloatArray:
            return terrain.sample(x + ax, y + ay)

        def sg(x: FloatArray, y: FloatArray) -> FloatArray:
            return terrain.sigma(x + ax, y + ay)

        az = core.needed_azimuths(
            [np.asarray(earth.az_deg), np.asarray(sun.az_deg)], NODE_AZ_STEP_DEG, NODE_AZ_MARGIN_DEG
        )
        mask = build_mask(
            sh,
            azimuths_deg=az,
            max_range_m=NODE_MAX_RANGE_M,
            dem_post_spacing_m=terrain.post_m,
            dem_vertical_error_m=terrain.vertical_error_m,
            sample_sigma=sg,
        )
        el = np.asarray(mask.el_deg, dtype=np.float64)

    def state(track: Any) -> npt.NDArray[np.int8]:
        margin = np.asarray(track.el_deg, dtype=np.float64) - core.skyline_at(
            az, el, np.asarray(track.az_deg, dtype=np.float64)
        )
        return visibility.visibility_state(
            margin, np.asarray(track.angular_radius_deg, dtype=np.float64)
        )

    es, ss = state(earth), state(sun)
    return _Skies(es == visibility.LIT, es == visibility.PENUMBRAL, ss == visibility.LIT)


@dataclass(slots=True)
class _Link:
    terrain: core.PathTerrain
    own: core.LinkBudget
    fwd: core.LinkBudget


@dataclass(slots=True)
class _Helper:
    soc_wh: float
    min_soc_wh: float
    buffer_bits: float = 0.0
    forwarded_bits: float = 0.0
    dropped_bits: float = 0.0
    energy_wh: float = 0.0
    today_wh: float = 0.0
    day: int = 0
    refused: list[str | None] = field(default_factory=list)


def _iso(start: datetime, t_s: float) -> str:
    return (start + timedelta(seconds=t_s)).isoformat().replace("+00:00", "Z")


def _both(
    cw: site_service.ComputedWindow,
    ns: list[Node],
    rad: core.Radio,
    guard: dict[str, Any],
    loss_threshold_s: float,
    radius_m: float,
) -> dict[str, Any]:
    """Two runs: the primary run on links whose line of sight is certainly clear beyond
    the local DEM's height error, and a conditional second run that also allows surface
    links whose line of sight lies within that height-error band ('uncertain'). Only
    ``with_mesh_if_uncertain_links_hold`` (and its start time) comes from the second
    run; ``with_mesh``, ``routes``, ``links[].usable``, ``helpers`` and the radio state
    timelines all come from the first, certain run."""
    out = _run(cw, ns, rad, guard, loss_threshold_s, radius_m)
    hopeful = _run(cw, ns, rad, guard, loss_threshold_s, radius_m, use_uncertain=True)
    by_id = {n["id"]: n for n in hopeful["nodes"]}
    for node in out["nodes"]:
        lw = node["longest_without_path_to_earth"]
        hopeful_lw = by_id[node["id"]]["longest_without_path_to_earth"]
        lw["with_mesh_if_uncertain_links_hold"] = hopeful_lw["with_mesh"]
        lw["with_mesh_if_uncertain_links_hold_starts_utc"] = hopeful_lw["with_mesh_starts_utc"]
        lw["basis"] += (
            " 'With the mesh' uses only surface links whose line of sight is clear above the "
            "terrain model's height error; 'if uncertain links hold' is a conditional second "
            "run that also allows surface links whose line of sight lies within that height-"
            "error band (routes, link usability and helper costs in this response do not use "
            "those uncertain links)."
        )
    return out


def _run(
    cw: site_service.ComputedWindow,
    ns: list[Node],
    rad: core.Radio,
    guard: dict[str, Any],
    loss_threshold_s: float,
    radius_m: float,
    use_uncertain: bool = False,
) -> dict[str, Any]:
    import time

    t0 = time.perf_counter()
    cutoff = float(guard["soc_cutoff_fraction"])
    quota_share = float(guard["quota_share_per_lunar_day"])
    cap_w = float(guard["max_forwarding_power_w"])
    buf_bits = float(guard["buffer_bytes"]) * 8.0
    r = cw.result
    t_s = np.asarray(r.earth.t_s, dtype=np.float64)
    n_steps = len(t_s) - 1
    dts = np.diff(t_s)
    site = cw.site
    terrain = _terrain(site.id, site.lat_deg, site.lon_deg, radius_m + 500.0)

    # -- where each node is, and what it sees from there ------------------------------
    pos_of: dict[str, list[tuple[float, float]]] = {}
    for nd in ns:
        arr: list[tuple[float, float]] = []
        for t in t_s[:-1]:
            cur = nd.waypoints[0]
            for w in nd.waypoints:
                if w[0] <= t:
                    cur = w
            arr.append(_pos_key(cur[1], cur[2]))
        pos_of[nd.id] = arr
    t_sky = time.perf_counter()
    skies = {p: _skies(cw, terrain, p) for p in sorted({p for a in pos_of.values() for p in a})}
    sky_ms = (time.perf_counter() - t_sky) * 1000.0
    healthy: dict[str, npt.NDArray[np.bool_]] = {}
    unsure: dict[str, npt.NDArray[np.bool_]] = {}
    sunlit: dict[str, npt.NDArray[np.bool_]] = {}
    for nd in ns:
        idx = pos_of[nd.id]
        healthy[nd.id] = np.array([skies[p].earth_ok[i] for i, p in enumerate(idx)])
        unsure[nd.id] = np.array([skies[p].earth_uncertain[i] for i, p in enumerate(idx)])
        sunlit[nd.id] = np.array([skies[p].sunlit[i] for i, p in enumerate(idx)])

    # -- when a node's direct-link outage has passed the wake threshold ---------------
    seeking: dict[str, npt.NDArray[np.bool_]] = {
        nd.id: core.seeking_relay(t_s[:-1], healthy[nd.id], loss_threshold_s) for nd in ns
    }
    used_route: dict[str, npt.NDArray[np.bool_]] = {
        nd.id: np.zeros(n_steps, dtype=bool) for nd in ns
    }
    forwarded_step: dict[str, npt.NDArray[np.bool_]] = {
        nd.id: np.zeros(n_steps, dtype=bool) for nd in ns
    }

    # -- links, cached by (node, position, node, position) -----------------------------
    links: dict[tuple[str, tuple[float, float], str, tuple[float, float]], _Link] = {}
    by_id = {nd.id: nd for nd in ns}

    def link(a: str, pa: tuple[float, float], b: str, pb: tuple[float, float]) -> _Link:
        key = (a, pa, b, pb) if (a, pa) <= (b, pb) else (b, pb, a, pa)
        got = links.get(key)
        if got is None:
            ka, kpa, kb, kpb = key
            ha, hb = by_id[ka].antenna_m, by_id[kb].antenna_m
            tr = core.terrain_between(
                terrain.sample, terrain.sigma, kpa, kpb, ha, hb, rad.frequency_hz, terrain.post_m
            )
            d = max(tr.distance_m, 1.0)
            got = _Link(
                tr,
                core.link_budget(rad, d, ha, hb, rad.tx_power_w),
                core.link_budget(rad, d, ha, hb, rad.forwarding_tx_power_w),
            )
            links[key] = got
        return got

    # -- the time loop ---------------------------------------------------------------------
    helpers = {
        nd.id: _Helper(nd.soc0 * nd.capacity_wh, nd.soc0 * nd.capacity_wh)
        for nd in ns
        if nd.may_help
    }
    quota_wh = {nid: quota_share * by_id[nid].capacity_wh for nid in helpers}
    p_own_dc = rad.tx_power_w / rad.tx_efficiency
    p_fwd_dc = rad.forwarding_tx_power_w / rad.tx_efficiency
    own_tx_wh = {nd.id: 0.0 for nd in ns}
    delivered_bits = {nd.id: 0.0 for nd in ns}
    route_keys: dict[str, list[Any]] = {nd.id: [] for nd in ns}
    pair_keys: dict[tuple[str, str], list[Any]] = {}
    mesh_up: dict[str, list[bool]] = {nd.id: [] for nd in ns}

    for i in range(n_steps):
        dt = float(dts[i])
        day = int(t_s[i] // core.LUNAR_DAY_S)
        for h in helpers.values():
            if h.day != day:
                h.day, h.today_wh = day, 0.0
        cap_of = {nid: by_id[nid].capacity_wh for nid in helpers}
        rule: dict[str, str | None] = {
            nid: core.guard_refusal(
                sunlit=bool(sunlit[nid][i]),
                soc_fraction=h.soc_wh / cap_of[nid],
                soc_cutoff_fraction=cutoff,
                energy_today_wh=h.today_wh,
                quota_wh=quota_wh[nid],
                forwarding_power_w=rad.forwarding_tx_power_w,
                power_cap_w=cap_w,
            )
            for nid, h in helpers.items()
        }
        asked: set[str] = set()
        used_out: dict[str, float] = {}
        for nd in ns:
            if not seeking[nd.id][i]:
                st = "direct" if healthy[nd.id][i] else "waiting"
                route_keys[nd.id].append((st, (), None, None, (), ()))
                mesh_up[nd.id].append(bool(healthy[nd.id][i]))
                continue
            src = nd.id
            cands = [c for c in ns if c.id != src and c.may_help]
            ids = {c.id for c in cands}
            edges: dict[str, dict[str, float]] = {}
            capacity: dict[tuple[str, str], float] = {}
            uncertain_peers: list[str] = []
            for u in [nd, *cands]:
                for v in cands:
                    if u.id == v.id:
                        continue
                    lk = link(u.id, pos_of[u.id][i], v.id, pos_of[v.id][i])
                    b = lk.own if u.id == src else lk.fwd
                    # The terrain test for a link is the straight line between the two
                    # antennas. The first Fresnel zone is reported beside it but does not
                    # decide: between antennas a few metres up the ground is always inside
                    # that zone, and its effect is what the two-ray loss already carries.
                    if b.closes and lk.terrain.sight == "uncertain" and u.id == src:
                        uncertain_peers.append(v.id)
                    seen = lk.terrain.sight == "clear" or (
                        use_uncertain and lk.terrain.sight == "uncertain"
                    )
                    if b.closes and seen:
                        p = rad.tx_power_w if u.id == src else rad.forwarding_tx_power_w
                        edges.setdefault(u.id, {})[v.id] = core.energy_per_bit_j(
                            p, rad.tx_efficiency, b.shannon_bps
                        )
                        capacity[(u.id, v.id)] = b.shannon_bps
                    a, c2 = sorted([u.id, v.id])
                    pair_keys.setdefault((a, c2), [None] * n_steps)
                    pair_keys[(a, c2)][i] = (
                        lk.terrain.sight,
                        lk.terrain.radio,
                        round(lk.terrain.distance_m, 1),
                    )
            targets = {c.id for c in cands if healthy[c.id][i]}
            ideal = core.min_energy_path(edges, src, targets, ids)
            refused_by: list[str] = []
            path = ideal
            if ideal is not None:
                refused_by = sorted(
                    f"{h}:{rule[h]}" for h in ideal[0][1:] if h in rule and rule[h] is not None
                )
                if refused_by:
                    asked.update(h for h in ideal[0][1:] if rule.get(h))
                    ok = {h for h in ids if rule.get(h) is None}
                    path = core.min_energy_path(edges, src, targets & ok, ok)
            key_unc = tuple(sorted(set(uncertain_peers)))
            if path is None:
                st = "refused" if ideal is not None else "isolated"
                route_keys[src].append((st, (), None, None, tuple(refused_by), key_unc))
                mesh_up[src].append(False)
                continue
            nodes_on = path[0]
            # capacity left after each helper's own traffic, hop by hop
            hop_caps: list[float] = []
            for a_id, b_id in pairwise(nodes_on):
                hop_caps.append(capacity[(a_id, b_id)])
            exit_id = nodes_on[-1]
            ex = by_id[exit_id]
            spare = [
                core.spare_capacity_bps(c, by_id[nodes_on[k + 1]].own_bps)
                for k, c in enumerate(hop_caps[1:])
            ]
            # hop_caps[k] is node k -> k+1; relay k+1 sends on hop k+1; its own traffic first
            out_rates = [
                core.spare_capacity_bps(hop_caps[k + 1], by_id[nodes_on[k + 1]].own_bps)
                for k in range(len(hop_caps) - 1)
            ]
            out_rates.append(
                np.inf
                if ex.uplink_bps is None
                else core.spare_capacity_bps(ex.uplink_bps, ex.own_bps)
            )
            del spare
            bottleneck = min([hop_caps[0], *out_rates])
            if bottleneck <= 0.0:
                route_keys[src].append(
                    ("no_capacity", tuple(nodes_on), None, None, tuple(refused_by), key_unc)
                )
                mesh_up[src].append(False)
                continue
            epb = path[1]
            route_keys[src].append(
                (
                    "mesh",
                    tuple(nodes_on),
                    float(f"{epb:.3g}"),
                    float(f"{bottleneck:.3g}") if math.isfinite(bottleneck) else None,
                    tuple(refused_by),
                    key_unc,
                )
            )
            mesh_up[src].append(True)
            # -- carry the data along the path ------------------------------------------
            flow = min(nd.own_bps * dt, hop_caps[0] * dt)
            if flow > 0:
                own_tx_wh[src] += p_own_dc * (flow / hop_caps[0]) / 3600.0
                used_route[src][i] = True
            for k in range(1, len(nodes_on)):
                hid = nodes_on[k]
                h = helpers[hid]
                last = k == len(nodes_on) - 1
                out_rate = out_rates[k - 1]
                air = hop_caps[k] if not last else (ex.uplink_bps or math.inf)
                p_dc = p_fwd_dc if not last else (ex.uplink_w or 0.0)
                room = (
                    out_rate * dt - used_out.get(hid, 0.0) if math.isfinite(out_rate) else math.inf
                )
                budget_wh = max(
                    0.0, min(quota_wh[hid] - h.today_wh, h.soc_wh - cutoff * cap_of[hid])
                )
                if p_dc > 0.0 and math.isfinite(air):
                    energy_bits = budget_wh * 3600.0 / p_dc * air
                else:
                    energy_bits = math.inf
                step = core.relay_step(
                    buffer_bits=h.buffer_bits,
                    inflow_bits=flow,
                    out_bits=min(room, energy_bits),
                    buffer_cap_bits=buf_bits,
                )
                spent = (
                    p_dc * (step.sent_bits / air) / 3600.0
                    if p_dc > 0 and math.isfinite(air)
                    else 0.0
                )
                if step.sent_bits > 0:
                    forwarded_step[hid][i] = True
                h.buffer_bits = step.buffer_bits
                h.dropped_bits += step.dropped_bits
                h.forwarded_bits += step.sent_bits
                h.energy_wh += spent
                h.today_wh += spent
                h.soc_wh -= spent
                h.min_soc_wh = min(h.min_soc_wh, h.soc_wh)
                used_out[hid] = used_out.get(hid, 0.0) + step.sent_bits
                flow = step.sent_bits
            delivered_bits[src] += flow
        for nid, h in helpers.items():
            h.refused.append(rule[nid] if nid in asked else None)

    # -- radio state machines (active_relay only while actually sending/forwarding) ----
    sm: dict[str, tuple[list[core.RadioState], list[core.Transition]]] = {}
    for nd in ns:
        full_h = np.concatenate([healthy[nd.id], healthy[nd.id][-1:]])
        full_u = np.concatenate([used_route[nd.id], used_route[nd.id][-1:]])
        full_f = np.concatenate([forwarded_step[nd.id], forwarded_step[nd.id][-1:]])
        sm[nd.id] = core.run_state_machine(
            t_s, full_h, loss_threshold_s, usable_route=full_u, forwarding=full_f
        )

    away_count = sum(1 for p in skies if p != (0.0, 0.0))
    at_origin = (0.0, 0.0) in skies
    if away_count and at_origin:
        sky_note = (
            f"{len(skies)} distinct node positions: (0, 0) uses the site's far-horizon mask "
            f"in meta.resolution, and {away_count} off-site position(s) are marched to "
            f"{NODE_MAX_RANGE_M / 1000:g} km at {NODE_AZ_STEP_DEG:g} deg on the "
            f"{terrain.post_m:g} m link terrain over the bearings Earth and the Sun cover"
        )
    elif away_count:
        sky_note = (
            f"{away_count} off-site node position(s), skylines marched to "
            f"{NODE_MAX_RANGE_M / 1000:g} km at {NODE_AZ_STEP_DEG:g} deg on the "
            f"{terrain.post_m:g} m link terrain over the bearings Earth and the Sun cover"
        )
    else:
        sky_note = "1 position at (0, 0), using the site's far-horizon mask in meta.resolution"
    return _present(
        cw, ns, rad, guard, loss_threshold_s, t_s, healthy, unsure, sunlit, sm, route_keys,
        mesh_up, pair_keys, links, helpers, own_tx_wh, delivered_bits, terrain, pos_of,
        sky_note, sky_ms, (time.perf_counter() - t0) * 1000.0,
    )  # fmt: skip


def _qty_h(seconds: float, step_s: float, open_: bool) -> dict[str, Any]:
    return q(
        Quantity(
            value=seconds / 3600.0,
            unit="h",
            provenance="computed",
            pm=step_s / 3600.0,
            open=open_,
        )
    )


def _plain(value: float, unit: str, why: str) -> dict[str, Any]:
    return q(Quantity(value=value, unit=unit, provenance="computed", no_margin_reason=why))


def _present(
    cw: site_service.ComputedWindow,
    ns: list[Node],
    rad: core.Radio,
    guard: dict[str, Any],
    loss_threshold_s: float,
    t_s: FloatArray,
    healthy: dict[str, npt.NDArray[np.bool_]],
    unsure: dict[str, npt.NDArray[np.bool_]],
    sunlit: dict[str, npt.NDArray[np.bool_]],
    sm: dict[str, tuple[list[core.RadioState], list[core.Transition]]],
    route_keys: dict[str, list[Any]],
    mesh_up: dict[str, list[bool]],
    pair_keys: dict[tuple[str, str], list[Any]],
    links: dict[Any, _Link],
    helpers: dict[str, _Helper],
    own_tx_wh: dict[str, float],
    delivered_bits: dict[str, float],
    terrain: Terrain,
    pos_of: dict[str, list[tuple[float, float]]],
    sky_note: str,
    sky_ms: float,
    total_ms: float,
) -> dict[str, Any]:
    start = cw.result.start
    step = float(np.median(np.diff(t_s)))
    n = len(t_s) - 1

    def span(a: int, b: int) -> dict[str, Any]:
        return {
            "start_s": float(t_s[a]),
            "end_s": float(t_s[b]),
            "start_utc": _iso(start, float(t_s[a])),
            "end_utc": _iso(start, float(t_s[b])),
        }

    out_nodes: list[dict[str, Any]] = []
    for nd in ns:
        states, events = sm[nd.id]
        sv = [s.value for s in states[:n]]
        time_in = {s.value: 0.0 for s in core.RadioState}
        for i in range(n):
            time_in[sv[i]] += float(t_s[i + 1] - t_s[i])
        no_direct = ~healthy[nd.id][:n]
        no_mesh = no_direct & ~np.array(mesh_up[nd.id][:n], dtype=bool)
        flag_d = np.concatenate([no_direct, [False]])
        flag_m = np.concatenate([no_mesh, [False]])
        d_len, d_at, d_open = core.longest_run(t_s, flag_d)
        m_len, m_at, m_open = core.longest_run(t_s, flag_m)
        route_iv = []
        for a, b, key in core.intervals(route_keys[nd.id]):
            r_status, r_path, r_epb, r_thr, r_refused, r_unc = cast("tuple[Any, ...]", key)
            route_iv.append(
                {
                    **span(a, b),
                    "status": r_status,
                    "path": list(r_path),
                    "hops": max(0, len(r_path) - 1),
                    "energy_per_bit_j": r_epb,
                    "throughput_bound_bps": r_thr,
                    "refused_by": [
                        {"node": x.split(":")[0], "rule": x.split(":")[1]} for x in r_refused
                    ],
                    "uncertain_peers": list(r_unc),
                }
            )
        pos_iv = [
            {**span(a, b), "east_m": p[0], "north_m": p[1]}
            for a, b, p in core.intervals(list(pos_of[nd.id]))
        ]
        out_nodes.append(
            {
                "id": nd.id,
                "name": nd.name,
                "may_help": nd.may_help,
                "positions": pos_iv,
                "radio_state_timeline": [
                    {**span(a, b), "state": s} for a, b, s in core.intervals(list(sv))
                ],
                "radio_transitions": [
                    {
                        "t_s": e.t_s,
                        "utc": _iso(start, e.t_s),
                        "from": e.from_state.value,
                        "to": e.to_state.value,
                    }
                    for e in events
                ],
                "time_in_state_h": {k: round(v / 3600.0, 4) for k, v in time_in.items()},
                "direct_earth_link": [
                    {**span(a, b), "healthy": bool(v)}
                    for a, b, v in core.intervals([bool(x) for x in healthy[nd.id][:n]])
                ],
                "earth_view_uncertain_h": round(
                    float(unsure[nd.id][:n] @ np.diff(t_s)) / 3600.0, 4
                ),
                "longest_without_path_to_earth": {
                    "direct_only": _qty_h(d_len, step, d_open),
                    "with_mesh": _qty_h(m_len, step, m_open),
                    "direct_only_starts_utc": None if d_at is None else _iso(start, d_at),
                    "with_mesh_starts_utc": None if m_at is None else _iso(start, m_at),
                    "basis": "A step with no healthy direct link is a step without a path; "
                    "with the mesh it is one only if no route exists too. Earth in the "
                    "partial-view band counts as not healthy. Open means the stretch touches "
                    "the window's edge.",
                },
                "routes": route_iv,
                "delivered_via_mesh_mb": round(delivered_bits[nd.id] / 8e6, 6),
                "own_mesh_tx_energy_wh": round(own_tx_wh[nd.id], 6),
                "missing_inputs": [
                    k
                    for k, v in (
                        ("earth_uplink_bps", nd.uplink_bps),
                        ("earth_uplink_power_w", nd.uplink_w),
                    )
                    if v is None
                ]
                if nd.may_help
                else [],
            }
        )

    helper_out: list[dict[str, Any]] = []
    for hid, h in helpers.items():
        nd = next(x for x in ns if x.id == hid)
        refusal_iv = [
            {**span(a, b), "rule": rule}
            for a, b, rule in core.intervals(list(h.refused))
            if rule is not None
        ]
        helper_out.append(
            {
                "id": hid,
                "forwarded_mb": _plain(
                    h.forwarded_bits / 8e6, "MB", "the sum of the steps; the rate is an upper bound"
                ),
                "dropped_mb": _plain(h.dropped_bits / 8e6, "MB", "a count of buffer overflow"),
                "buffered_at_end_mb": _plain(h.buffer_bits / 8e6, "MB", "what the buffer holds"),
                "energy_spent_wh": _plain(
                    h.energy_wh, "Wh", "the energy per bit is a lower bound, so this is too"
                ),
                "minimum_state_of_charge": _plain(
                    h.min_soc_wh / nd.capacity_wh,
                    "1",
                    "the entered start less forwarding only; its own loads are not modelled",
                ),
                "refusals": refusal_iv,
                "refused_hours_by_rule": {
                    r_: round(
                        sum(x["end_s"] - x["start_s"] for x in refusal_iv if x["rule"] == r_)
                        / 3600.0,
                        4,
                    )
                    for r_ in core.RULES
                },
            }
        )

    ordered = {pid: i for i, pid in enumerate(nd.id for nd in ns)}
    table: list[dict[str, Any]] = []
    for (pa_id, pb_id), keys in sorted(
        pair_keys.items(), key=lambda kv: (ordered[kv[0][0]], ordered[kv[0][1]])
    ):
        for lo_i, hi_i, k in core.intervals(list(keys)):
            if k is None:
                continue
            sight, radio_state, dist = cast("tuple[Any, Any, float]", k)
            ha = next(x for x in ns if x.id == pa_id).antenna_m
            hb = next(x for x in ns if x.id == pb_id).antenna_m
            bud = core.link_budget(rad, max(dist, 1.0), ha, hb, rad.tx_power_w)
            rng = core.first_failing_range_m(rad, ha, hb, rad.tx_power_w)
            table.append(
                {
                    "a": pa_id,
                    "b": pb_id,
                    **span(lo_i, hi_i),
                    "distance_m": dist,
                    "terrain_sight": sight,
                    "terrain_fresnel": radio_state,
                    "path_loss_db": round(bud.path_loss_db, 2),
                    "free_space_loss_db": round(bud.free_space_db, 2),
                    "snr_db": round(bud.snr_db, 2),
                    "radio_closes": bud.closes,
                    "usable": bool(bud.closes and sight == "clear"),
                    "range_to_first_failure_m": None if rng is None else round(rng, 1),
                    "throughput_bound_bps": round(bud.shannon_bps, 1),
                }
            )

    meta = cw.meta("bypass")
    res = meta.get("resolution") or {}
    unc = dict(meta["uncertainty"])
    site_post = res.get("dem_resolution_m", unc.get("dem_resolution_m", 20.0))
    site_err = unc.get("dem_vertical_error_m", 4.0)
    site_rng_km = float(res.get("max_range_m", 50_000.0)) / 1000.0
    unc["notes"] = [
        *unc["notes"],
        f"Two terrain grids are used: meta.resolution and meta.uncertainty describe the site's "
        f"far-horizon mask at (0, 0) ({site_post:g} m post spacing, {site_err:g} m height error, "
        f"marched to {site_rng_km:g} km), while the terrain block ({terrain.post_m:g} m post "
        f"spacing, {terrain.vertical_error_m:g} m height error, {', '.join(terrain.products)}) "
        "is used for surface-to-surface links and for skylines of node positions away from (0, 0).",
        "Mesh: every radio, battery, traffic and guard figure is entered and taken as given; "
        "none has a margin of its own. Sight and Fresnel-zone states carry the link terrain "
        f"model's height error ({terrain.vertical_error_m:g} m). In the primary run ('with_mesh', "
        "routes, link usability and helper costs), a surface link is used only when the straight "
        "line between the antennas is clear; a link whose line of sight lies within that height-"
        "error band ('uncertain') is reported with usable=false and counted only in the "
        "conditional figure 'with_mesh_if_uncertain_links_hold'. The Fresnel-zone state is "
        "reported beside it and does not gate a link: flat-ground reflection inside the first "
        "Fresnel zone is in the two-ray loss.",
        "Radio states: a node is in 'active_relay' only during steps where it sends or forwards "
        "traffic over a usable mesh route; when its direct link is lost and no mesh route carries "
        "traffic (waiting, isolated, refused or no spare capacity), it stays in 'standby' at 0 W "
        "because receive and idle-listening power are not modelled.",
        f"Node skylines: {sky_note}.",
        "Earth is 'healthy' only when its whole disc is above the node's skyline; a partly "
        "hidden disc ('earth_view_uncertain_h') counts as not healthy in both runs.",
    ]
    meta["uncertainty"] = unc
    meta["compute_ms"] = round(total_ms, 1)
    radio_in = {
        "frequency_hz": _entered(rad.frequency_hz, "Hz"),
        "tx_power_w": _entered(rad.tx_power_w, "W"),
        "forwarding_tx_power_w": _entered(rad.forwarding_tx_power_w, "W"),
        "tx_efficiency": _entered(rad.tx_efficiency, "1"),
        "antenna_gain_dbi": _entered(rad.antenna_gain_dbi, "dBi"),
        "bandwidth_hz": _entered(rad.bandwidth_hz, "Hz"),
        "noise_figure_db": _entered(rad.noise_figure_db, "dB"),
        "snr_threshold_db": _entered(rad.snr_threshold_db, "dB"),
        "eps_r": _entered(rad.eps_r, "1"),
        "polarisation": rad.polarisation,
        "loss_threshold_s": _entered(loss_threshold_s, "s"),
    }
    guard_in = {
        "soc_cutoff_fraction": _entered(guard["soc_cutoff_fraction"], "1"),
        "quota_share_per_lunar_day": _entered(guard["quota_share_per_lunar_day"], "1"),
        "max_forwarding_power_w": _entered(guard["max_forwarding_power_w"], "W"),
        "buffer_bytes": _entered(guard["buffer_bytes"], "B"),
        "lunar_day_s": q(
            Quantity(
                value=core.LUNAR_DAY_S,
                unit="s",
                provenance="published",
                pm=0.0,
                source="https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html",
            )
        ),
    }
    return {
        "site_id": cw.result.site_id,
        "start": _iso(start, 0.0),
        "end": _iso(start, float(t_s[-1])),
        "step_s": cw.result.step_s,
        "inputs": {"radio": radio_in, "guard": guard_in},
        "nodes": out_nodes,
        "links": table,
        "helpers": helper_out,
        "terrain": {
            "products": terrain.products,
            "post_m": terrain.post_m,
            "vertical_error_m": terrain.vertical_error_m,
            "used_for": (
                "surface-to-surface links (line of sight and first Fresnel zone) and skylines "
                "for node positions away from (0, 0); the site origin (0, 0) uses the site "
                "horizon mask described in meta.resolution"
            ),
        },
        "timing_ms": {"skylines": round(sky_ms, 1), "total": round(total_ms, 1)},
        "not_modelled": NOT_MODELLED,
        "meta": meta,
    }
