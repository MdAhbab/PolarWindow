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
