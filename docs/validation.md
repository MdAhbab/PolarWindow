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
| blue-ghost-m1 | 2025-01-15T06:11:39Z | -11 s | phasing loops (below) | 59.0 min | 3119 m/s | 29.78 d |
| im-2 | 2025-02-27T00:16:30Z | -4 s | +27.4 min | 35.5 / 36.9 min | 3125 / 3126 m/s | 4.46 / 4.48 d |

| Mission | Climbed at (inertial / over the ground) | Designed: due east | at the azimuth it climbed | at the other direct flight's |
|---|---|---|---|---|
| im-1 | 88.8° / 88.7° | +9.8 min | +0.2 min | −15.8 min (86.6°) |
| blue-ghost-m1 | 110.2° / 111.3° | −139 min (loops) | +0.6 min (loops, below) | none flown with loops |
| im-2 | 86.6° / 86.4° | +27.4 min (+43.8 before) | −0.0 min | +17.5 min (88.8°) |

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
approach, inclination to the Moon's equator and the way round the orbit
goes), the design takes a climb azimuth and corrects three things in the
force model (Sun, Moon, Earth J2–J6; the Moon a point mass): the liftoff
time, which turns the parking orbit's plane with the Earth; the coast, which
moves the TLI point along it; and the speed TLI adds. It converges in 3–4
steps to under 0.1 km in the B-plane and 1 s in time. The coast, TLI speed
and flight time it needs agree with the flown ones (within 1.4 min, 1 m/s
and 0.02 d), so the transfer itself is right.

*Before* (a due-east climb, the arrival's inclination alone): the liftoff was
right to the day but 9.8 min (IM-1, inside the plan's 10 min) and 43.8 min
(IM-2) after the real one; Blue Ghost's loop design 139 min before it. Two
things were wrong. IM-2 arrived in a near-polar orbit, where the inclination
alone also allows the mirror orbit going round the other way; the design took
whichever was nearer its first guess. Holding the orbit's direction as well
(`transfer.Target.normal`) brings IM-2 to +27.4 min due east. The rest is the
climb's direction. For a direct transfer the arrival fixes the plane through
the Moon's direction, so the azimuth and the liftoff time trade one for the
other: every azimuth has its own instant, about 7 min per degree here (the
pad sits near the top of the orbit, where the plane's crossing is slow).

*After* (the climb azimuth solved for, plan §D1, `sin A = cos i / cos φ`):
the climb's direction of each flight is measured from the plane through the
pad at liftoff and the TLI point (`launchwin.climb_azimuth`; IM-1 88.8°,
IM-2 86.6°, Blue Ghost 110.2°: climb planes inclined 28.63°, 28.79° and 34.5°
from a pad at 28.61°). Designed at that azimuth the liftoff lands 0.2 min (IM-1),
0.0 min (IM-2) and 0.6 min (Blue Ghost, three loops as flown) from the
real one, inside the plan's 2 and 5 min. That uses the flight's own
direction. Held out, each Nova-C designed at the other's direction misses by
15.8 min (IM-1, early) and 17.5 min (IM-2, late): outside the plan's 10 min,
since the two flights' directions differ by 2.2°, and nothing published says
which azimuth a flight will take. All three are inside the Eastern Range's
assumed 35–120° over the ground (`launchwin.ground_azimuth`), and so the
calendar's check of the pad's limits passes for them.

The planned calendar therefore climbs at the mean of the vehicle's direct
lunar flights (Falcon 9: 87.7°, 87.6° over the ground; due east with a ±44 min
margin for a vehicle with none) and gives the liftoff ± 18 min, the larger
held-out miss (it was ± 44 min). Whether that is an instant or a window follows
what the vehicle's direct lunar launches were published as (below). Designing the calendar with the flight held out
still puts an opportunity on each real launch day (D2 below); on that day the
nearest one is 90 min before IM-1's liftoff (66 min due east) and 36 min after
IM-2's (45 min due east), because the calendar aims at the landing times the
rule allows, not at the flown arrival, and the arrival time moves the instant
more than the direction does.
Keeping the TLI point fixed and steering with a sideways push at TLI instead
was tried first and fails: for a transfer of nearly 180° the push barely
moves the arrival, and the correction found answers about 100 to 190 m/s from the
flown TLI.

**Predicting the direction** (held out; the table's last part is printed by
`make validate-trip`, pinned in `test_launch_vs_clps.py`). Four predictors were tried,
each for a Nova-C launch from what is known without its own launch:

| Mission | Other direct flight's direction | Due east | Arrival node: direction, liftoff | Other flight's inclination after TLI | The same rule, own inclination |
|---|---|---|---|---|---|
| im-1 | −15.8 min | +9.8 min | 114.1°, −145.5 min | −6.0 min | −14.3 min |
| im-2 | +17.5 min | +27.4 min | 88.0°, +10.9 min | +0.9 min | +10.2 min |

*Arrival node.* The design holds the arrival's inclination and the way round it goes;
the node about the Moon's pole is the one thing about the arrival it leaves free, so the
direction whose designed arrival has the flown node was solved for. It is ill
conditioned: the node moves 0.046° (IM-1) and 0.086° (IM-2) per degree of direction,
because a transfer of nearly 180° reaches the Moon from about the same side whatever
plane it flies in, while at the direction it really climbed IM-1's designed arrival
already has its node 1.20° off (0.12° for IM-2), the size of what the cruise's
correction burns change. For IM-1 the node points to 114° and a liftoff 2.4 h early.

*Inclination after TLI* (to the equator of the day, where the pad sits at 28.45°). A
climb aimed at the other Nova-C's orbit inclination after TLI (28.51° or 28.60°) lands
both launches within 10 min. It is chance: given each flight's *own* inclination the
same rule misses by 14.3 and 10.2 min, since the plane a flight climbed in and the plane
it left Earth in differ in inclination by 0.11 to 0.14° (the pad lay 0.10 to 0.13° off the latter at
liftoff: the vehicle turned between them). With two flights the two numbers happen to
cross; the calendar does not use it. *Due east* (the most the Earth's turning helps)
misses IM-2 by 27 min. *The Moon's declination at arrival* (25° and 14°) has no rule
tying it to the direction: for a transfer of nearly 180° every plane through the TLI
point reaches it. The range's hazard-area notices, which state a launch's direction days
before, would be the published predictor; NGA's archive of them (NAVAREA IV) refused
this machine, so it is not tried. The mean of the other flight's direction stays.

*Instant or window* (plan D1). Launch Library 2's records, the source of each flown
liftoff, give the window each launch was published with: IM-1 and IM-2 (Falcon 9,
direct) a single instant; Blue Ghost 1 (Falcon 9, phasing loops) 06:06 to 06:45 UTC;
Peregrine (Vulcan, loops) 07:18 to 08:03 UTC. They are in `data/missions.json` (`t0`)
and a flown launch now shows its own. A planned one gets a window only when the vehicle's
direct lunar launches were published with windows (it steers); its ends are then the
instants designed at the pad's two azimuth limits on the same sweep of the climb plane.
Falcon 9's were instants, so its calendar stays one instant ± 18 min. Had the vehicle
steered between the Eastern Range's assumed 35 and 120° over the ground, the same design
puts IM-1's day from 105 min before to 300 min after its liftoff and IM-2's from 163 min
before to 269 min after (converged at both ends): hours, not the single instant flown,
so the pad's limits alone are not a vehicle's window; what it can lift at the ends is
not published.

**Backed out from the landing** (plan D2: flown landings inside the
landing rule; flown launch days inside the calendar). With no Sun-height band
entered, the rule is: the Sun's centre above the skyline and rising, and the
Earth up. IM-1's, IM-2's and Blue Ghost's landings all fall inside it
(`test_launch.py`). Designing the calendar as if IM-1 and IM-2 had not flown
(own flight left out of the climb, the other Nova-C's time in lunar orbit)
puts a launch opportunity on each one's real launch day (`test_launch.py`).
The lunar orbit's plane passing over the landing spot (plan L4) is not
checked: near the poles the lighting decides.

**Not yet done.** Coasts longer than any flown one are accepted up to 120 min
and flagged: with the Moon south of the equator the climb reaches the TLI point
only after most of an orbit, and upper stage coast limits are not published.
Which azimuth a flight takes is not predicted better than the spread of the
flown ones (2.2°, 16–18 min); four predictors tried held out are above.

# Phasing loops and correction burns against the flown landers (plan C3, C4)

`make validate-trip` prints these tables (`app/tests/golden/validate_loops.py`;
the acceptance is pinned in `test_loops_vs_clps.py`).

**Burns read from the reconstruction.** Each half hour of NASA's
reconstruction is propagated in the force model and compared with the
reconstruction at its end; a window that differs by more than 0.05 m/s holds a
burn (outside burns they agree to about 1e-4 m/s). A run of such windows is one
burn, shown as one instant where the path before it (forward) and the path
after it (backward) come closest. Blue Ghost 1, up to its arrival at the Moon:

| Burn found | Size | Distance from Earth | Arcs meet within |
|---|---|---|---|
| 2025-01-19T04:15:36Z Burn near the highest point of the orbit | 22.53 m/s | 335,814 km | 86 m |
| 2025-01-23T19:32:38Z Burn near the lowest point of the orbit | 3.27 m/s | 13,081 km | 8 m |
| 2025-02-09T05:01:12Z Leaving Earth for the Moon | 23.61 m/s | 12,038 km | 83 m |
| 2025-02-10T05:01:12Z Correction 1 | 1.15 m/s | 196,485 km | 10 m |
| 2025-02-14T01:53:24Z Entering lunar orbit | 356.25 m/s | 397,914 km | 1918 m |

IM-2's reconstruction shows seven corrections (0.06 to 9.7 m/s) and its
capture (828 m/s); IM-1's shows none, because its stretches (at most four hours
each) leave its burns in the gaps. Peregrine's shows a steady push over days
(the propellant leak), reported as such rather than as burns. In lunar orbit
the force model and the reconstruction part by about 1 m/s at every close pass
of the Moon, as much as a small burn, so burns there are not listed.

**Replay** (plan: perigee and apogee times within 1 h, apogee radius within
1%). Blue Ghost's first reconstructed state propagated with these burns as
instants:

| Flown | Time | Replayed: minutes off | radius off |
|---|---|---|---|
| apogee | 2025-01-19T14:00:21Z | +0.1 | +0.001 % |
| perigee | 2025-01-23T19:30:45Z | +0.2 | +0.011 % |
| apogee | 2025-01-27T22:01:37Z | +0.9 | +0.007 % |
| perigee | 2025-02-01T00:10:21Z | +1.5 | +0.016 % |
| apogee | 2025-02-05T02:42:52Z | +2.2 | +0.008 % |
| perigee | 2025-02-09T05:08:42Z | +2.9 | +0.027 % |

**Designed loops** (plan: the flown loop count, and a launch period that holds
the flown date). Given the pad, the other Falcon 9 flights' climb, Falcon 9's
injection as flown (3,119 m/s above the parking orbit's speed), the flown first
perigee (13,067 km from the Earth's centre) and NASA's arrival at the Moon,
the design flies a due-east climb, raises the perigee at the first apogee,
sets the period of the remaining loops at the first perigee and leaves Earth
at the last, and corrects liftoff, coast and the three burns in the force
model (Sun, Moon, Earth J2–J6) until the arrival matches in the B-plane and
in time and the first perigee is where it was flown. Each launch day keeps
its cheapest design over one loop fewer, the two-body count and one more.

| Day | Loops | Liftoff (min) | Raise | Period | Leave | Total (m/s) |
|---|---|---|---|---|---|---|
| −5 | 3 | +478 | 108.8 | +30.3 | −1.5 | 140.6 |
| −4 | 3 | +479 | 122.1 | +26.3 | 3.4 | 151.9 |
| −3 | 3 | +489 | 116.1 | +16.8 | 17.6 | 150.5 |
| −2 | 3 | +490 | 92.6 | +12.2 | 16.6 | 121.4 |
| −1 | 3 | −151 | 83.0 | +12.1 | 15.8 | 110.9 |
| **0** | **3** | **−139** | **20.8** | **−4.7** | **24.8** | **50.3** |
| +1 | 3 | −159 | 47.1 | −12.3 | 36.2 | 95.6 |
| +2 | 3 | +457 | 76.6 | −11.3 | 36.0 | 124.0 |
| +3 | 2 | −167 | 80.0 | +42.0 | −15.1 | 137.2 |
| +4 | 2 | −171 | 89.5 | +37.8 | −11.2 | 138.5 |
| +5 | 1 | +448 | 94.0 | — | 27.6 | 121.6 |

The flown day needs three loops, as flown, and is the cheapest day of the
eleven by 45 m/s: its burns add up to 50.3 m/s against the 49.4 m/s found in
the reconstruction (22.5, 3.3 and 23.6 m/s). With no propellant budget
published, every day whose design works belongs to a period, so the
three-loop period (−5 to +2 days) holds the flown date. The cost curve is the
stronger result: an eight-day loop reaches 330,000 km, where the Sun's pull
over one loop moves the perigee by thousands of kilometres, and on the flown
day it did most of the raising (20.8 m/s against 85 m/s in two-body terms).
Due east, the liftoff lands 139 min before the real one (the real climb was
inclined 34.5°, which a due-east climb from Florida does not give). Climbing
at the azimuth it flew (110.2°), the flown day's design needs 3 loops and
lands 0.6 min after the real liftoff (plan: 5 min), 55.3 m/s in all (flown 49.4).

**Correction budget** (plan: linear and Monte Carlo within 10% at the 95th and
99th percentiles; a seeded run repeats bit for bit). The flight as planned is
NASA's reconstruction just before the lander entered lunar orbit, propagated
back to where it passed closest to Earth near the flown departure (propagating
the arrival itself back would not do: a close pass of the Moon spreads any
difference by thousands of kilometres). Three corrections (a day after
leaving Earth, half-way, a day before arriving) aim the estimated state at the
planned position at the planned arrival time. Errors, all assumed (no user
guide with injection accuracy is in the catalogue, and the lander makers
publish no navigation or engine figures): leaving Earth, 1 km in position and
0.5 / 1.0 / 0.5 m/s (up, along, sideways); knowledge at each correction 1 km and
1 mm/s; each burn 1% and 1° (Gates' model) plus 1 cm/s. Linear: the errors
pushed through state transition matrices of each stretch (100,000 draws, since
Gates' errors grow with the burn). Monte Carlo: 1,000 seeded runs through the
force model, each correction refined twice on the run's own estimated state.

| Mission | Planned departure | 95th linear / runs | 99th linear / runs (95 % interval) | Arrival altitude 1st–99th % | Flown corrections found |
|---|---|---|---|---|---|
| blue-ghost-m1 | 5,390 km up, +8 min | 14.71 / 14.16 m/s | 19.33 / 18.08 m/s (16.52–19.85) | 156.2–160.2 km | 1.15 m/s |
| im-1 | 622 km up, +170 min | 20.91 / 21.64 m/s | 27.45 / 28.50 m/s (25.93–30.40) | 110.6–114.5 km | none (in its gaps) |
| im-2 | 1,002 km up, −28 min | 21.29 / 21.45 m/s | 27.82 / 28.89 m/s (26.24–30.24) | 99.8–103.8 km | 0.06, 0.13, 1.06, 2.11, 9.71, 6.06, 4.72 m/s |

The two methods agree within 7% (Blue Ghost's 99th percentile; the others
within 4%); no run missed the Moon. Nearly all of the total is the first
correction, which removes the departure error. These are budgets for the
assumed errors, not what the missions needed: Blue Ghost's one correction
(1.15 m/s) sits well inside its budget, and IM-2's add up to 24 m/s, near its
99th percentile. IM-1's planned departure is 170 min after its real one, 622 km up: its
corrections (in the reconstruction's gaps) changed the path enough that the
path back from the Moon with no burn passes Earth that much later; the budget
is about that plan.

# Launch weather: wind climatology and the check against observations (plan T4 B1, Verification)

**Climatology** (`make climatology`, `app/data/climatology.py`). NASA POWER's hourly wind at
50 m above the surface (MERRA-2 reanalysis; the Falcon 9 rule's 162 ft is 49 m) at LC-39A
and SLC-4E, 2001–2024 (210,384 hours each), kept as a histogram per month and UTC hour.
The share of hours above 30 mph at the Cape runs from about 2 % in January to none in
July. It is what an opportunity beyond the ensembles' 16 days shows for the wind rule.
A reanalysis cell's hourly mean is smoother than the pad's tower, so these shares
understate gusty hours; the answer says so.

**Check against observations** (`make hindcast-weather`, `app/feeds/hindcast.py`,
`core/verification.py`; plan: a rule says "checked against observations" only if its
Brier skill is at least 0.1 against the month-by-hour climatology at every lead up to
48 h and its reliability is within 0.1 in every bin with 30 cases or more). The 162 ft
wind is not measured by any public station, so the check is made at 10 m, at the Cape
Canaveral Skid Strip's weather station (ASOS KXMR, Iowa Environmental Mesonet archive),
with the limit brought down by a neutral logarithmic profile over open flat ground
(roughness 0.03 m): 30 mph at 49 m is 23.5 mph at 10 m. One GEFS run a day for 2025
(its hour turning through 00, 06, 12 and 18 UTC; NOAA's open-data bucket on AWS), 31
runs each, 10 m wind bilinear at the station, at 24 and 48 h; the outcome is the
station's sustained wind in its report nearest that time (48 of the 730 cases had no
report within 30 minutes and are left out). The reference is the station's own
month-by-hour frequency for 2015–2024.

| Lead | Cases | Wind above the limit | Brier (GEFS) | Brier (climatology) | Brier skill |
|---|---|---|---|---|---|
| 24 h | 343 | 1 | 0.0040 | 0.0029 | −0.41 |
| 48 h | 339 | 0 | 0.0014 | 0.00003 | −41.6 |

It does not pass, and every wind share keeps saying "not checked against observations".
The event is rare: in 2025 the station reported more than 23.5 mph in 12 of 8,247
hourly reports (0.15 %; 0.36 % over 2015–2024), and only one fell at a verified time.
GEFS gave shares above zero on days it did not happen (one run at 94 %), which costs
more than climatology's near-zero forecast, probably because its 0.5° cell over the Cape
is partly sea, where the wind runs stronger than at a station a few kilometres inland. No reliability bin
other than the lowest (669 cases, mean share 0.002, observed 0) holds 30 cases. A year
cannot check a limit this rarely reached; several years, or the pad's own tower record,
would be needed.

**Lightning climatology** (`make thunder-climatology`, `app/data/thunder_climatology.py`).
NASA MSFC's Combined GLM Hourly Thunder Hour data (GHRC DAAC, doi:10.5067/GLM/HTH/DATA301),
2019–2025, 2,557 days: for each hour, whether thunder could be heard in each 0.05° cell.
A day's file is 600 MB, so only the pads' cells are read through NASA Earthdata's OPeNDAP;
for one day the pads' cells matched the whole file hour for hour. At LC-39A thunder was heard
in about 21 % of July's 20 UTC hours and none of January's.

# Radiation screening (plan track E)

`make validate-radiation` (`app/tests/golden/validate_radiation.py`) prints these tables;
`test_radiation.py` pins the cosmic-ray and past-event checks.

**Belts: the engine against a second implementation** (plan: IRBEM within 5 % of SPENVIS
running AE8/AP8). SPENVIS needs an account and was not run here. Instead, along each flown
trajectory (one-minute samples within 15 Earth radii, from NASA's reconstruction), the
fluence from IRBEM (the engine, compiled in spacepy's wheel) is compared with NASA SPDF's
own AE8/AP8 code (`radbelt`), twice. Solar-maximum maps for all four (the year before each
launch was near the cycle's peak in OMNI's sunspot record).

The two codes do not place a point on the same magnetic shell. IRBEM's `fly_in_nasa_aeap1`
works out McIlwain L and B/B0 with the field each map was built with: Jensen and Cain 1960
for AE8 MIN, AE8 MAX and AP8 MIN, GSFC 12/66 updated to 1970 for AP8 MAX, with B0 from
McIlwain's moment (31,165.3 nT/L³). These are the fields SPENVIS's model description lists
for the maps (spenvis.oma.be, help/background/traprad, Table 1). SPDF's driver uses IGRF
of the flight date and the field line's own minimum for B0. So the first table feeds
IRBEM's L and B/B0 into both codes: it checks the maps and how they are read (energy grid,
interpolation, MIN or MAX). The second gives SPDF its own shells: it shows what the choice
of field changes.

| Mission | 1-min samples | e >1 MeV IRBEM | SPDF, same shells | diff | p >10 MeV IRBEM | SPDF, same shells | diff |
|---|---|---|---|---|---|---|---|
| IM-1 | 0 | – | – | – | – | – | – |
| IM-2 | 437 | 1.09e10 | 1.09e10 | 0.0 % | 8.55e5 | 8.55e5 | 0.0 % |
| Blue Ghost 1 | 3,311 | 2.04e10 | 2.04e10 | 0.0 % | 8.00e8 | 8.00e8 | 0.0 % |
| Peregrine | 867 | 2.35e10 | 2.35e10 | 0.0 % | 2.67e8 | 2.67e8 | 0.0 % |

| Mission | e >1 MeV SPDF, IGRF of the day | IRBEM against it | p >10 MeV SPDF, IGRF of the day | IRBEM against it |
|---|---|---|---|---|
| IM-2 | 1.13e10 | −2.8 % | 1.44e6 | −40.5 % |
| Blue Ghost 1 | 2.15e10 | −5.0 % | 7.94e8 | +0.7 % |
| Peregrine | 2.33e10 | +0.8 % | 2.80e8 | −4.8 % |

With the same shells the two codes agree to 0.0 % on every trip: the maps and their reading
are the same. The 40 % on IM-2's protons is the field alone. Read with SPDF's code and
shells from other fields, IM-2's proton fluence is 8.55e5 with GSFC 12/66 (the map's own
field), 8.73e5 with IGRF of 1970 (+2 %), 1.66e6 with IGRF of the flight date (+94 %), and
1.45e6 with IGRF of the flight date and the field line's minimum as B0 (+70 %; SPDF's
choice). It is the 55 years of change in Earth's field, not the field model or the code:
the dipole has weakened and the South Atlantic Anomaly has drifted west (about 0.3° a year,
SPENVIS's description), so today's field puts the same point on a shell nearer the belt's
floor. IM-2's protons come from minutes at the inner belt's lower edge, where the flux
changes steeply with B/B0, so they feel this most; the trips that spend hours inside the
belt (Blue Ghost's four passes, Peregrine's two) move by 5 % or less. The engine is left as
it is, reading each map with the field it was built with, which is what SPENVIS's model
description lists; it has not been checked against a SPENVIS run. Reading the maps with
today's field instead would roughly double IM-2's proton number, which is inside the ×/÷2
the maps are read with. (IRBEM's IGRF in spacepy's build ends at 2025.0 and uses that for
2025 dates; this only enters the IGRF-of-the-day line above.)
IM-1's reconstruction starts 242,000 km out, a day and a half after launch, past the
belts, so it has none; the answer
says the climb out is not counted (a lower bound). The maps themselves are read as good
to a factor of two (×/÷2 on every number).

**Cosmic rays** (plan: ±30 %). The dose on the trip is CRaTER's measured rate scaled by
the model's change with the Sun's modulation (Matthiä et al. 2013, W from the Oulu
neutron monitor via NMDB). As an absolute check, the model's dose in a thin silicon layer
in free space (Bethe stopping power, nuclei Z = 1–28 above 10 MeV/n) in June 2009 (W = 5)
is 14.1 cGy a year, against CRaTER's 18.9 (microdosimeter, −26 %) and 16.5 (D1–D2,
−15 %) at 10,000 km from the Moon (Schwadron et al. 2012). Both are inside ±30 %. How
the dose changes between solar minimum and maximum is the model's alone and has not been
checked against a second measurement here. Scaled this way the trip dose was 0.21 mGy a
day for IM-1 (February 2024, W = 91) and 0.17 for Blue Ghost 1 (January 2025, W = 108),
before any shielding; on the surface, Chang'e-4's 13.2 µGy an hour (January 2019) scaled
the same way and by the site's open sky.

**Past events** (plan: within 10 % of NOAA's list). The >10 MeV peak from the GOES
detector's 5-minute averages (NOAA NCEI) against NOAA SWPC's list of solar proton events:

| Event | GOES peak (pfu) | at | NOAA list | at | diff | fluence >10 MeV (cm⁻²) |
|---|---|---|---|---|---|---|
| October 1989, 19–31 Oct (GOES-7) | 42,200 | 20 Oct 16:00 | 40,000 | 20 Oct 16:00 | +5.5 % | 1.92e10 |
| Late October 2003, 28–31 Oct (GOES-11) | 29,500 | 29 Oct 06:15 | 29,500 | 29 Oct 06:15 | 0.0 % | 1.39e10 |

August 1972 comes from King's (1974) fitted spectrum as SPENVIS gives it (7.9e9 cm⁻²
above 30 MeV). Fluences take the flux as arriving evenly from every direction. OMNI's
merged proton record was not used for these: it has gaps at both peaks and no proton
values after March 2020, so the events during a flown trip are listed from NASA DONKI (NOAA's
10 pfu threshold at GOES) without a fluence.

# Capsule entry against OSIRIS-REx (plan track H)

`make validate-capsule` (`app/tests/golden/validate_capsule.py`, about 7 minutes; the model
is `app/core/entry.py`, flown for a day by `app/services/capsule.py`). The model is a point
mass with a ballistic coefficient β, falling from the entry interface through an atmosphere
that turns with the Earth, under gravity with J2; no lift, no parachutes, and a wind only in
the footprint. The air is NRLMSISE-00 (Picone et al. 2002, run through `pymsis` 0.13.0)
driven by the entry day's 10.7 cm solar flux and 3-hour geomagnetic ap from NASA's OMNI
files (`app/data/msis_indices.py`: the flux of the day before, its 81-day mean, and the
seven ap numbers the model's storm-time mode takes), asked for at the capsule's own place
and time all the way down. The U.S. Standard Atmosphere 1976 (equations to 86 km, its Table
I densities from 86 to 150 km) stands in when the OMNI files lack the day; the answer says
which air was used. Nothing returns to Earth on a CLPS mission, so the model is checked on
the one recent sample return with a published entry state and a measured landing point.

**Entry state.** The sample return capsule's reconstructed trajectory in NAIF's PDS
archive (`src_230924_230924_230930_od383a_v1.bsp`, in the registry as
`naif:orex-src-entry`) ends at the entry interface, 6,503.142 km from the Earth's centre,
at 14:41:55.072 UTC on 24 September 2023. Its state there matches the navigation team's
reconstructed entry state (Wibben et al., AAS 24-058, Table 12) to the table's last digit:
flight path angle −8.184°, heading 66.396°, Earth-relative speed 12.361 km/s, 37.339° N,
237.216° E.

**Landing** (plan: within 10 km of the measured point). β from published numbers: the
capsule's mass at entry (49.64 kg as built plus the 121.6 g sample), Stardust's diameter
(0.8128 m, the same forebody) and its hypersonic axial force coefficient, 1.48 to 1.56
(Mitcheltree et al. 1997). Flown to the touchdown height, 1,288 m, in each atmosphere over
the published drag range, and compared with the recovery team's measured point,
40.3719° N, 113.24° W. Before, the standard atmosphere; now, NRLMSISE-00 for the day; the
newer NRLMSIS 2.1 is flown for comparison only:

| Atmosphere | C_A 1.48 | C_A 1.52 | C_A 1.56 | Entry to ground | Peak deceleration |
|---|---|---|---|---|---|
| U.S. Standard Atmosphere 1976 (before) | 6.7 km | **9.5 km** | 12.2 km | 530 s | 31.0 g |
| NRLMSISE-00, 24 September 2023 (now) | 9.4 km | **12.1 km** | 14.8 km | 537 s | 32.3 g |
| NRLMSIS 2.1, 24 September 2023 | 3.9 km | 6.6 km | 9.3 km | 531 s | 32.0 g |

The day's indices were the 10.7 cm flux of 23 September, 174.1 solar flux units (81-day mean
149.3), and a 3-hour ap of 4 at the time (the day's storm began in the 18 to 21 UTC block,
after the landing). NRLMSISE-00's flights, β from each C_A:

| C_A | β (kg/m²) | Landing | From the measured point | Entry to ground | Peak deceleration |
|---|---|---|---|---|---|
| 1.48 | 64.8 | 40.3535 N, 113.3479 W | 9.4 km | 531 s | 32.2 g |
| 1.52 | 63.1 | 40.3459 N, 113.3788 W | **12.1 km** | 537 s | 32.3 g |
| 1.56 | 61.5 | 40.3385 N, 113.4089 W | 14.8 km | 543 s | 32.4 g |

**The plan's 10 km is not met with the day's air.** NRLMSISE-00 lands the capsule 12.1 km
from the measured point (9.4 to 14.8 km over the drag range: only its low-drag end is inside
the limit), 2.6 km farther than the standard atmosphere did (9.5 km, met with 0.5 km to
spare). The answer says so (`passed: false`), names the air, and gives the other airs'
distances. NRLMSIS 2.1 lands 6.6 km away and would pass; it is not used, because the model
was fixed before the runs (the plan names NRLMSISE-00, which the low-orbit drag model uses
too) and not by which one lands nearest. All three miss on the same side, short and
west-southwest (257° from the measured point in the standard atmosphere). So did the
mission's own six-degree-of-freedom simulation from the same reconstructed entry state
with the parachutes as flown and its pre-flight atmosphere (Earth-GRAM) and winds: 8.9 km
at 257° (Francis et al., the table of comparison cases, "Cht Seq + ESF").

**What decides the landing.** The middle case in NRLMSISE-00 with the density 5 % higher over
one band of heights at a time:

| NRLMSISE-00, density 5 % higher between | Landing moves | From the measured point |
|---|---|---|
| 0 and 30 km | 0.08 km | 12.2 km |
| 30 and 50 km | 2.34 km | 14.5 km |
| 50 and 70 km | 2.37 km | 14.5 km |
| 70 and 90 km | 0.28 km | 12.4 km |
| 90 and 125 km | 0.01 km | 12.1 km |

The landing rests on the air between 30 and 70 km, where the capsule loses its speed. It does
not rest on the Sun: the solar flux and the geomagnetic activity, which are all that make
NRLMSISE-00 the day's, act above 100 km. With the flux at 70 solar flux units (solar minimum)
or 250 (maximum) the landing is 11.7 or 11.8 km from the measured point instead of 12.1,
with ap held at 4 all the way down 12.0 km, and in a severe storm (ap 100 all the way down)
12.9 km. The 12.1 km is the model's average stratosphere and mesosphere for the place and
the season; the day's indices move it by 0.8 km at most.

**The models against the day's radiosonde.** The National Weather Service's balloon from Salt
Lake City at 12 UTC (130 km from the touchdown, up to 33 km; Iowa Environmental Mesonet
archive, saved unchanged in `data/capsule/kslc_20230924_12z.json`), with its heights made
geometric and its temperatures virtual, against each model at the balloon's place and time:

| Height | Radiosonde (kg/m³) | U.S. Standard Atmosphere 1976 / radiosonde | NRLMSISE-00 / radiosonde | NRLMSIS 2.1 / radiosonde |
|---|---|---|---|---|
| 3 km | 0.8875 | 1.025 | 1.014 | 0.985 |
| 5 km | 0.7262 | 1.014 | 1.014 | 0.975 |
| 10 km | 0.4258 | 0.971 | 0.995 | 0.972 |
| 15 km | 0.2093 | 0.931 | 1.016 | 1.002 |
| 20 km | 0.0939 | 0.947 | 1.014 | 0.982 |
| 25 km | 0.04204 | 0.954 | 1.019 | 0.979 |
| 30 km | 0.01907 | 0.965 | 1.025 | 0.983 |

The standard atmosphere is 3 to 7 % thinner than the day's air from 10 to 30 km;
NRLMSISE-00 is within 2.5 % of the balloon at every height and NRLMSIS 2.1 within 2.8 %. Below
30 km the empirical models have the day's air right, and the landing hardly depends on it
(0.08 km for 5 %). Where it does depend, above 30 km, nothing measured that day is on disk.

**What the mission's team found.** Its reconstruction of the day's air, from NASA's GEOS
analysis, "showed notably lower atmospheric densities in the upper atmosphere than the
nominal GRAM atmosphere predicted, and was even lower than the predicted GRAM 3σ low density
for a significant portion of the drag pulse". Put into their simulation, with the winds it
came with, it landed 15.1 km northeast of the pre-flight prediction, 3.5 km beyond the
measured point ("Cht Seq + ESF + Atm"; 2.7 km with the winds of the balloon flown after the
landing instead). An average like NRLMSISE-00, which knows a day only through its flux and
geomagnetic activity, cannot show a thin day. The capsule flew with no parachute until 1.4 km
above the ground (the signals to the drogue's mortar and to the cutters that free its bridle
were reversed), so a model without parachutes follows the real flight nearly to the ground;
the team found that the parachutes as flown moved the touchdown point by 0.4 km and, in
their no-parachute contingency, by under 100 m. The time to the ground (537 s) is not
comparable with the observed 615 s: the observed flight ended under the main parachute, 285 s
over its last 1.4 km, and the model has no parachute and one axial force coefficient all the
way down.

**Footprint.** A seeded Monte Carlo of 200 runs: the flight path angle from TCM-12's
delivery accuracy (0.073° at 3σ, AAS 24-058 Table 5), heading and speed from the E-1 day
solution (Table 12), β ±2.6 % (the published C_A range as one sigma), and, assumed, the
density ±5 % and a wind below 30 km of 10 m/s in each direction. Its 99 % ellipse is 51.2
by 21.8 km in NRLMSISE-00 (51.4 by 21.4 km in the standard atmosphere), long axis 77° from
north, and holds the measured point in both (the mission's design ellipse was 84 by 20 km).
In the standard atmosphere, without the wind the ellipse was 0.3 km wide and missed the
measured point, which lies about 0.9 km across the track: the wind is what sets the width.

The result is written to `data/capsule/orex_check.json` and served in
`GET /missions/{id}/return` as `capsule.model_check`.

**Not done.** The Moon-to-Earth return trajectory to the entry interface (C1/C2 reversed)
is not built: no CLPS mission brings anything back, and no planned one publishes an entry
state. A capsule's zone weather (B2) waits for the same. The day's air from 30 to 76 km,
which the landing depends on, is not measured or analysed in what is on disk; NASA's
GEOS-FP analysis of it (the family of analyses the mission's team used, open on the NCCS
OPeNDAP server) is the input to try next.

# Real orbiters over the landing sites against JPL Horizons (plan T1, F2)

`make validate-orbiters` (`app/tests/golden/validate_orbiters.py`; needs the network,
about 30 requests to Horizons; writes `data/contact/orbiters_check.json`). LRO, Danuri,
Chandrayaan-2 and CAPSTONE fly over the sites. The Contact answer shows their passes as
"could see the lander", never as a relay: none of them offers to relay for a lander.

**The trajectory the product uses.** The feeds worker records each orbiter's Horizons
VECTORS (Moon-centred, ICRF, geometric) every 5 minutes, weekly from a week ago to 30 days
ahead, and once for each flown mission's surface days. The compute worker writes them as
an SPK type 13 kernel (Hermite, degree 7). Against Horizons' own 1-minute vectors for LRO
(64–116 km above the Moon, the hardest case), 5-minute knots miss by at most 1.8 m
(10-minute knots by up to 18 m, which is why 5 was chosen).

**Azimuth and elevation** (plan: 0.02° against Horizons). From each landed site, on the
1737.4 km sphere as Horizons places a lunar site at height 0, with the light time and
aberration seen from the site (CSPICE `spkcpo`), against Horizons' observer table ("airless
apparent", Moon mean-Earth frame), every minute the orbiter is up. **Rise and set** (plan:
2 s): over the flat horizon (a point, angular radius 0), ours from a 30 s grid refined by
bisection, as the Contact answer does over the terrain skyline; Horizons' from its table
every 2 seconds, interpolated.

| Site (dates) | Orbiter | Minutes up | Largest angle (°) | Rises and sets | Largest Δt (s) |
|---|---|---:|---:|---:|---:|
| IM-2, Mons Mouton (surface days, 12.75 h) | LRO | 82 | 0.0002 | 14 | 0.002 |
| | Danuri | 57 | 0.0004 | 13 | 0.002 |
| | Chandrayaan-2 | 84 | 0.0002 | 14 | 0.002 |
| | CAPSTONE | 766 (always up) | 0.0000 | 0 | – |
| IM-1, Malapert A (23 Feb 2024, 12 h) | LRO | 82 | 0.0001 | 14 | 0.002 |
| | Danuri | 87 | 0.0001 | 13 | 0.002 |
| | Chandrayaan-2 | 64 | 0.0002 | 12 | 0.002 |
| | CAPSTONE | 721 (always up) | 0.0000 | 0 | – |
| Blue Ghost 1, Mare Crisium (3 Mar 2025, 12 h) | LRO | 64 | 0.0010 | 12 | 0.003 |
| | Chandrayaan-2 | 71 | 0.0001 | 13 | 0.001 |
| | Danuri, CAPSTONE | 0 | – | 0 | – |

Every rise and set Horizons gives has one of ours within 0.003 s, none unmatched; the
largest angle is 0.001°, twenty times inside the plan's 0.02°.

**Against NAIF's LRO reconstruction** (plan: 0.01°, its WebGeocalc tolerance; WebGeocalc
itself was not used). The same azimuth and elevation from IM-2's site on 1 April 2025,
from NAIF's reconstructed kernel `lrorg_2025074_2025166_v01.bsp` and from ours built from
Horizons: at most 0.00018° apart (71 minutes up in 12 hours).

**What this does not check.** The terrain skyline the answer uses instead of the flat
horizon (the surface engine's own validation covers it), and trajectories Horizons
predicts: the weekly window reaches 30 days ahead, where LRO's and Danuri's orbits are
predictions that later reconstructions will move. CAPSTONE's Horizons trajectory ends on
14 August 2026, and Chandrayaan-2's on 23 October 2026; after that the answer says so.

# Planned relays (plan T1, F3 and F4)

A planned relay publishes an orbit's shape but never where its node will sit or where it
will be along the orbit on a given day, so those two are swept on a 36 × 36 grid and every
number through a relay is a range. No flown relay exists to check against; the geometry is
checked on analytic cases (`app/tests/unit/test_relay.py`), each exact to the sampling:

* A circular polar relay seen from the pole over a flat skyline is up for
  (π − 2 asin(R/r)) / 2π of each orbit: matched to 1e-5.
* An equatorial relay seen from Earth is behind the Moon for asin(R/r)/π of each orbit
  (the relay-to-station ray–sphere test): matched to 2e-3, the difference being Earth at
  384,400 km rather than at infinity.
* Earliest arrival through lander → relay → Earth equals a general search over the same
  contacts on 40 random sets; the longest wait also catches a message that reaches the
  relay just as its link down closes, which the general search's candidate instants miss.
* Kepler's equation to 1e-11 rad for eccentricities up to 0.95; an argument of periapsis of
  90° puts the far point over the south pole.

An example over the reference lunar day at Griffin-1's south pole site (Earth above the
skyline 422.6 of 708.8 h; with direct contact alone, nobody hears the lander for up to
286.1 h at a stretch), over all 5,184 placements of each relay: Lunar Pathfinder, if it
flies as planned, would add 194–210 h and bring the longest time unheard to 3.0–3.8 h (a
message waits 182–230 min at most); Altus-1 in NASA's reference orbit would add 236–245 h
(4.7–5.5 h unheard, 282–326 min wait). At IM-3's near-side site, where Earth never sets,
Altus-1 adds nothing. About 50 s of compute per relay for a lunar day.

**The relay in the contact plan.** A plan that asks for a relay (`?relay=`) lists its contacts at
one placement, the one swept (5,184 for each catalogue relay) whose time through the relay is
nearest the middle of the range (the first on a tie), so the file and the answer's middle value agree and the choice is the
same every time; the header says which placement, that it is planned and not a forecast, and the
ranges over all of them. Checked in `test_relay.py` (a station's own link is the part of the
combined link the sweep uses that it hears: with two stations at Earth's centre, the one with no
mask is all of it to 1e-9 and one with an 89.5° mask hears less; the placement named is a real
point of the sweep whose time through the relay is the one reported) and in `test_contact.py` (Griffin-1, 20 to 22 March
2027: with no relay asked the plan is the direct contacts and nothing else; with Lunar Pathfinder
every contact is from the lander to the relay or from it to a station, inside the dates, marked
planned, and ION has an `a range` for each `a contact`). One placement is not a schedule: another
gives other contacts, which is why it is never in a plan that did not ask for it.

# Rover-to-lander line of sight (plan T1, F5)

`app/core/viewshed.py`, served by `GET /missions/{id}/contact/rover`. For each bearing (every
5°) a ray is sampled outward from the lander; a rover at each of 20 ranges is in clear sight
when the terrain between the antennas stays below the line joining them (the running maximum
of the terrain's elevation angle), and on a clear radio path when it also stays out of the
first Fresnel zone. Each is clear, blocked or uncertain: the elevation model's height error
at each blocker, as the angle atan(σ / distance), and at the rover's ground, makes the band.
Ground within two posts of either end is not a blocker (the skyline's noise rule).

**Analytic surfaces** (plan: exact; `app/tests/unit/test_viewshed.py`). A ring wall
shadows exactly the rovers whose antenna sits below the line over its near edge, and a taller
mast ends the shadow where the line clears the wall; with a 2 m height error every cell is
either that exact state or uncertain, uncertain exactly where the clearance is inside the
band; a 2.5 m wall half way along a 500 m path at 30 GHz leaves the line clear and cuts the
Fresnel zone (1.12 m at mid-path), and at 2.4 GHz the zone (3.95 m) reaches flat ground.

**Real terrain** (`make validate-viewshed`; plan: 99 % agreement with `gdal_viewshed`
outside the uncertain band). GDAL is not installed here, so `gdal_viewshed` was not run.
The nearest check that could be: the engine's states with the height error set to zero,
against a brute-force test written separately (the terrain every metre along each straight
line, compared in heights, not angles), on the 20 m polar model around each rover site,
antennas 2 m (lander) and 0.5 m (rover), counted where the 2 m error does not make a cell
uncertain:

| Site | Radius | Cells | Outside the band | Agree | Share out of sight (lo–hi) |
|---|---:|---:|---:|---:|---|
| IM-2 (Yaoki) | 500 m | 1440 | 221 | 100.00 % | 0.7–97.1 % |
| IM-2 (Yaoki) | 2000 m | 1440 | 826 | 100.00 % | 76.8–100.0 % |
| Griffin-1 (FLIP) | 500 m | 1440 | 481 | 100.00 % | 12.0–85.7 % |
| Griffin-1 (FLIP) | 2000 m | 1440 | 742 | 100.00 % | 51.8–90.2 % |

This checks the running maximum, not the terrain model or the method against an independent
tool. **What it shows about the answer:** within 500 m most cells are uncertain (IM-2: 1,219
of 1,440): a 2 m height error at 100 m is 1.1°, more than the angles between a 2 m and a
0.5 m antenna, so the 20 m polar model cannot say whether a small rover near the lander is in
its sight, and the shares come as wide ranges. The error is taken as independent at every
post, as for the skyline; LOLA's errors between nearby posts are partly shared, so the band is
if anything too wide. No rover drive is published, so the share is over the ground within
the radius, and the longest stretch out of sight is missing with that reason. Reiner Gamma
(CADRE, Lunar Vertex) is outside the polar model and answers "not resolvable".

**The map layer** (`GET /tiles/viewshed/...`, `app/core/viewshed.py: tile_rgba`). The tiles draw the
states of that answer, not a second calculation, so what is checked is that each ground point lands
in its cell: `test_viewshed.py` gives every (bearing, range) cell its own random state at 85°S 120°E,
where the polar grid's north lies 120° from true north, and reads 300 cells back from the picture at
points given as bearing and range from the lander; all 300 agree, and with the grid's turn left out
214 of the 300 read back wrong, so the test does see it. The stripes are those of the whole map, not
of a tile (checked on tiles at three offsets), so neighbouring tiles join up. The terrain under them
is the hillshade of the 20 m window the answer read, drawn by the terrain tiles' own renderer; the
regional 80 m model those tiles come from is blocks 34 pixels wide at the zoom of a rover map.
