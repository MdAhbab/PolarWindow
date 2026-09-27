# Validation against flown CLPS landers

Three CLPS landers have reached the surface: IM-1, Blue Ghost Mission 1 and
IM-2. Each has a published landing coordinate (LROC) and published surface
dates (NASA). That makes them the only external check this product can run
against reality rather than against itself.

**Method.** The published coordinate is used as-is, the site's horizon mask is
built the usual way (or a smooth-sphere skyline outside 80°S), and the Sun and
Earth arcs are computed at a 300 s step over the mission's surface window.
Nothing is tuned to these events. The numbers below come from
`GET /sites/{site}/windows` on this build.

**What this can and cannot show.** It compares the *geometry* with the
*reported timeline*. It does not model a lander: tilt, panel orientation,
battery, thermal design and communications hardware are all outside this
system. Where a mission ended before the geometry changed, the geometry is
reported and **no cause is asserted**.

| Mission | Site used | Our result | Published | Agreement |
|---|---|---|---|---|
| **Blue Ghost Mission 1** (TO19D) | 18.5623°N, 61.8103°E ([LROC](https://lroc.im-ldi.com/images/1407)); outside the polar DEM, smooth-sphere skyline on a flat mare floor | Local sunset **2025-03-16 20:10 UTC**. Sun up continuously from landing until then; Earth up throughout. | "Blue Ghost continued operations for five hours after lunar sunset on March 16" ([NASA Media Advisory M25-033](https://www.nasa.gov/news-release/nasa-firefly-invite-media-to-discuss-end-of-blue-ghost-moon-mission/)); "concluded its mission March 16" ([NASA release 25-026](https://www.nasa.gov/news-release/nasa-science-continues-after-fireflys-first-moon-mission-concludes/)) | **Same date.** Pinned by `tests/golden/test_hindcast.py`. |
| **IM-1 Odysseus** (TO2-IM) | 80.13°S, 1.44°E ([LROC](https://lroc.im-ldi.com/images/1360)); real 20 m terrain, 83 % DEM coverage (the site is 4 km from the DEM's edge) | Sun up from landing until **2024-03-02 14:01 UTC ± 28 min**; Earth up throughout. | Instruments "ceased science and technology operations seven days after landing", i.e. about 29 February 2024 ([NASA, 1 Mar 2024](https://www.nasa.gov/missions/artemis/clps/nasa-collects-first-surface-science-in-decades-via-commercial-moon-mission/)) | Operations ended about two days **before** the site's computed sunset. The geometry does not explain the end date. We make no claim about the cause. |
| **IM-2 Athena** (PRIME-1) | 84.7906°S, 29.1957°E, where Athena came to rest ([LROC](https://lroc.im-ldi.com/images/1408)); real terrain | Over the 12 h 45 min from touchdown to end of mission: **Sun and Earth both up the whole time**. The next sunset at that spot is 2025-03-19 19:17 UTC. | Touched down about 400 m from the target, came to rest on its side in a 20 m crater, and ended the mission early ([NASA release 25-025](https://www.nasa.gov/news-release/nasa-receives-some-data-before-intuitive-machines-ends-lunar-mission/)) | The geometry offered light and a line of sight to Earth throughout. NASA reports the lander on its side and the PRIME-1 instruments unable to meet their goals because of it. We make no claim about why the mission ended. |

## What this supports

- **Timing at a published coordinate is right to the day** for the one case
  where a sunset and an end of mission coincide (Blue Ghost 1).
- **The product separates geometry from hardware.** Two of three landers ended
  while the Sun and Earth were both still up at their site. A tool that reports
  illumination is not a tool that predicts mission survival, and the product
  does not claim to be one: the backend returns durations and refuses verdicts
  (`docs/system-design.md` §9, assumption 4).

## What it does not support

- It is not a test of the polar terrain model at a shadow edge. None of the
  three events is a terrain-cast sunset: Blue Ghost is at 18°N, and neither
  IM mission ended at a sunset. The terrain model's own checks are the golden
  fixtures, the analytic surfaces in `test_horizon.py`, and the uncertainty
  every response carries.
- One agreement to the day is not a timing accuracy. The ± on each crossing
  comes from the DEM's vertical error (`meta.uncertainty`), and a published
  timeline to the day cannot confirm a figure in minutes.

# The trip propagator against flown trajectories (plan C1)

Measured on commit `d01b407` with `make validate-trip`
(`backend/app/tests/golden/validate_trip.py`; the acceptance numbers are
pinned by `test_propagate_vs_clps.py`).

**Method.** The references are NASA's reconstructed trajectories in NAIF's
CLPS SPICE archive (IM-1, Blue Ghost Mission 1, IM-2, Peregrine) and the
Lunar Reconnaissance Orbiter's reconstructed orbit for 20–27 March 2025.
Every 10 minutes the acceleration each reconstruction implies (a five-point
difference of its velocity) is compared with the force model's. Where they
differ by more than 1e-5 m/s² the spacecraft was firing an engine or
thrusters; a *quiet stretch* is a run below that, less 30 minutes at each
end. From the start of a quiet stretch the reconstructed state is propagated
and compared with the reconstruction 24 h and 72 h later. Nothing is fitted.
The force model is the default one (DE440 Sun and Moon, Earth J2–J6, GRAIL
GRGM1200A to degree 50 in cruise and 100 in lunar orbit, no sunlight
pressure); the last column repeats the run with sunlight pressure for an
assumed Cr·A/m of 0.01 m²/kg, since no lander publishes its area or mass
at that point in the flight.

| Reference | Start (UTC) | Where | After | Position error | With assumed sunlight pressure |
|---|---|---|---|---|---|
| Blue Ghost 1 | 2025-01-16 07:32 | cruise | 24 h | 0.11 km | 0.07 km |
| Blue Ghost 1 | 2025-01-17 07:32 | cruise | 24 h | 0.11 km | 0.07 km |
| Blue Ghost 1 | 2025-01-15 07:32 | cruise | 24 h | 0.37 km | 0.51 km |
| Blue Ghost 1 | 2025-01-15 07:32 | cruise | 72 h | 1.46 km | 3.21 km |
| Blue Ghost 1 | 2025-02-03 13:12 | cruise | 72 h | 1.08 km | 0.62 km |
| IM-2 | 2025-03-03 13:01 | lunar orbit, ~100 km | 24 h | 0.51 km | 0.50 km |
| IM-2 | 2025-03-04 13:01 | lunar orbit, ~100 km | 24 h | 0.27 km | 0.28 km |
| LRO | 2025-03-20 00:01 | lunar orbit, 80–100 km | 24 h | 0.05 km | 0.05 km |
| LRO | 2025-03-21 01:41 | lunar orbit, 80–100 km | 24 h | 0.03 km | 0.03 km |
| IM-1 | 2024-02-19 20:26 | cruise | 8.5 h (longest stretch) | 0.64 km | 0.64 km |
| IM-2 | 2025-02-27 01:51 | cruise | 24 h | **4.61 km** | 4.43 km |

Raising the Moon's field from degree 100 to 200 changes the lunar-orbit rows
by at most 8 m. A 24 h forward-and-back run from Blue Ghost's reconstructed
state returns to within **5.8 mm**.

**Against the plan's tolerances.** Reconstructions: ≤1 km after 24 h is met
for Blue Ghost 1 and for IM-2 in lunar orbit, **not for IM-2's cruise
(4.61 km)**; ≤5 km after 72 h is met (1.08 and 1.46 km). LRO: ≤1 km after
24 h is met (0.03–0.05 km). Round trip ≤1 m is met.

**Why IM-2's cruise misses.** Throughout its cruise IM-2's reconstruction
carries an acceleration the force model does not have: median 6.4e-7 m/s²
over the whole file, about 1e-6 m/s² in the stretch used (IM-1's is
1.8e-6 m/s², Blue Ghost's 2.9e-7 m/s²). Held for a day, 1e-6 m/s² moves a
spacecraft ½·a·t² ≈ 3.7 km, which is the size of the miss. The residual is
constant within each hour of the reconstruction and steps between hours, as
an estimated acceleration in an orbit-determination solution would; whether
it is thruster activity, venting or the solution's own estimate is not
published, and we do not assert one.

**Leak detection (Peregrine).** Peregrine's reconstruction needs an
unexplained push for its whole flight: median 7.6e-5 m/s², 90th percentile
1.8e-4 m/s², and no quiet stretch at all. Astrobotic's post-mission report
traces the loss to a helium pressure control valve that failed to seal
([PM1 post-mission report](https://www.astrobotic.com/wp-content/uploads/2024/08/PM1_Post-Mission-Report_Website.pdf));
the residual is where that shows in the trajectory, and nothing here
estimates the leak itself.

**What replaces GMAT.** The plan's reference for the propagator was GMAT
R2026a run offline (`make gmat-golden`). GMAT is not installed on this
machine and no container runtime is available, so the GMAT comparisons (a
5-day coast to 10 m and 1 mm/s; a 100 km polar lunar orbit for 24 h to 10 m)
have **not been run**. In their place, `test_propagate.py` checks the
integrator against closed forms: two-body motion against Kepler's equation
over five orbits (under 1 mm), the J2 nodal drift against the textbook rate
(within 2 %), forward-and-back in a 100 km lunar orbit with a lumpy field and
sunlight pressure (under 1 m; measured 0.2–0.9 mm), and the same trip about
the Earth and about the Moon (under 1 m).

# Launch instants and direct transfers against the flown launches (plan D1, C2, D2)

`make validate-trip` prints this table (`app/tests/golden/validate_launch.py`;
the acceptance is pinned in `test_launch_vs_clps.py`). Each Falcon 9 lunar
launch is predicted with its own flight left out of the vehicle's climb.

| Mission | Published liftoff | From its TLI | Designed (due east) | Coast designed / flown | TLI speed designed / flown | Flight designed / flown |
|---|---|---|---|---|---|---|
| im-1 | 2024-02-15T06:05:37Z | +15 s | +9.8 min | 41.3 / 42.0 min | 3134 / 3135 m/s | 6.32 / 6.33 d |
| blue-ghost-m1 | 2025-01-15T06:11:39Z | -11 s | phasing loops (C3) | 59.0 min | 3119 m/s | 29.78 d |
| im-2 | 2025-02-27T00:16:30Z | -4 s | +43.8 min | 34.6 / 36.9 min | 3125 / 3126 m/s | 4.45 / 4.48 d |

**How a climb is described.** From the first reconstructed state after TLI
the trajectory is propagated back to its perigee, where TLI fired. That gives
the TLI time and point, the parking orbit's radius (6,570 to 6,598 km for Falcon 9) and
the *climb constant* `c`: the angle a climb falls behind a circular orbit that
started at the pad at liftoff, `u(pad → TLI point) − n·(t_TLI − T0)`. For
Falcon 9 it is −18.2° (IM-1), −17.5° (IM-2) and −17.1° (Blue Ghost), although
the coasts differ (42, 37 and 59 min) and Blue Ghost's orbit was inclined 35°.
Vulcan's one flight (Peregrine) gives −26.1° and cannot be checked against
another.

**From its TLI** (plan: 2 min for IM-1 and IM-2, 5 min for Blue Ghost). The
liftoff solved from the flown TLI and the other two flights' mean `c` lands
15, 4 and 11 s from the published one. One degree of `c` moves the liftoff by
15.5 s, so the spread of `c` (1.1°) is what sets this. The plan's first
formulation, the instant the pad crosses the flown orbit's plane, is ill
conditioned for these launches: all three flew close to due east, so the pad
grazes the plane (IM-1's orbit was inclined 0.04° more than the pad's
latitude, IM-2's 0.10° *less*, which only a turn at TLI allows), and a few
hundredths of a degree move the crossing by ten minutes or more.

**Designed** (plan: the right day, and within 10 min). Given only the pad,
the other flights' climb and NASA's arrival at the Moon (time, closest
approach, inclination to the Moon's equator), the design assumes a due-east
climb and corrects three things in the force model (Sun, Moon, Earth J2–J6;
the Moon a point mass): the liftoff time, which turns the parking orbit's
plane with the Earth; the coast, which moves the TLI point along it; and the
speed TLI adds. It converges in 3–4 steps to under 0.1 km in the B-plane and
1 s in time. The coast, TLI speed and flight time it needs agree with the
flown ones (within 2.3 min, 2 m/s and 0.03 d), so the transfer itself is
right; the liftoff is right to the day but lands 9.8 min (IM-1, inside the
plan's 10 min) and 43.8 min (IM-2, outside it) after the real one. The
difference is the climb's direction: a due-east climb is the assumption, and
IM-2's orbit shows it did not fly exactly that. The calendar therefore gives
a designed liftoff ± 44 min, the larger of the two misses, and says so.
Keeping the TLI point fixed and steering with a sideways push at TLI instead
was tried first and fails: for a transfer of nearly 180° the push barely
moves the arrival, and the correction found answers about 100 to 190 m/s from the
flown TLI.

**Backed out from the landing** (plan D2: flown landings inside the
landing rule; flown launch days inside the calendar). With no Sun-height band
entered, the rule is: the Sun's centre above the skyline and rising, and the
Earth up. IM-1's, IM-2's and Blue Ghost's landings all fall inside it
(`test_launch.py`). Designing the calendar as if IM-1 and IM-2 had not flown
(own flight left out of the climb, the other Nova-C's time in lunar orbit)
puts a launch opportunity on each one's real launch day (`test_launch.py`).
The lunar orbit's plane passing over the landing spot (plan L4) is not
checked: near the poles the lighting decides.

**Not yet done.** Phasing-loop transfers (Blue Ghost, C3) are not designed;
correction burns and dispersions (C4) are not worked out; the vehicle's
azimuth limits are not applied, because the design flies due east, inside
the Eastern Range's assumed 35–120°. Coasts longer than any flown one are
accepted up to 120 min and flagged: with the Moon south of the equator a
due-east climb reaches the TLI point only after most of an orbit, and upper
stage coast limits are not published.
