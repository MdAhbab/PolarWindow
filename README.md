<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="frontend/src/assets/brand/logo-on-dark.png">
    <img src="frontend/src/assets/brand/logo-on-light.png" alt="POLAR WINDOW" height="64">
  </picture>
</h1>

**When does a lander on the Moon have sunlight, and when can it talk to Earth?**
POLAR WINDOW answers that for every NASA Commercial Lunar Payload Services (CLPS)
mission and for candidate landing sites at the Moon's south pole, from NASA's own
terrain and ephemeris data, with a margin on every number. Built for the NASA
Space Apps Challenge, *CLPS Lunar Mission Browser*.

At the south pole the Sun never climbs more than a few degrees, so one hill can
switch it off for days, and Earth sits just as low. Four numbers decide a
mission there, and the app always shows them together and never blends them
into a score:

1. hours of sunlight over the chosen dates
2. hours in contact with Earth
3. the longest night
4. the longest time without contact

## Try it

**1. Look at it in a minute, with nothing to install but Node** (recorded answers, no backend, no data):

```bash
cd frontend && npm ci && npm run build:snapshot && npm run preview
```

Open <http://localhost:4173>. Every mission and landing-site page opens from the
saved copy, and the page says *Saved copy* so it is never mistaken for live data.

**2. Run the whole app** (Python 3.12 through [uv](https://docs.astral.sh/uv/), Node 20+, PostgreSQL 16; Redis is optional):

```bash
python3 run.py
```

Open <http://localhost:5173>. The runner installs the dependencies, starts its
own PostgreSQL and Redis, applies the migrations, starts the API, the two
workers and the frontend, then downloads any dataset that is missing (about
1.2 GB of public NASA data the first time; see *Required data* below, and
*Copying the data* there for a faster way). No API key is needed.

**3. Put it on a server** (Ubuntu, Docker):

```bash
python3 run_onVM.py
```

See *On a server* below.

### What to look at

| Step | Where | What it shows |
|---|---|---|
| 1 | The front page, then **Open the dashboard** | The four ideas on a 3D Moon drawn from LRO data; one click signs in. |
| 2 | **Missions**, filter by *volatiles* | 20 CLPS deliveries, each field with its source; what is not published says so. |
| 3 | **IM-2**, then **Surface** | The four numbers for the real landing spot, each with its ±, and the skyline that causes them. |
| 4 | The dates, then **play** | The Sun and Earth move against the skyline; every number is recomputed by the backend. |
| 5 | **Landing sites**, **Compare** | Candidate sites side by side, ranked on one number at a time, ties shown as ties. |
| 6 | A mission's six steps | Ready, Launch, Trip, Surface, Contact, Return: launch times, the flown path, radiation, ground stations and relays, where the booster comes down. |
| 7 | **Ask about missions and sites**, then *How the AI got this* | An answer whose every number is traced to a tool result; a number the tools did not return is refused. |
| 8 | **Plan** and **Printable report** | Every stretch without contact, and the exports (CSV, SPICE interval lists). |

## Why the numbers can be trusted

- **Real geometry.** The skyline at each site is ray-cast in 1,440 directions over
  NASA LOLA terrain (20 m and 80 m at the pole; SLDEM2015 and LOLA's 60 m model
  for mission targets elsewhere). Sun and Earth positions come from JPL SPICE
  (DE440), in the Moon's mean-Earth frame.
- **A margin on every number**, or the reason there is none. A crossing too
  shallow to time is called that; a value the dates cut short is marked ≥.
- **No verdicts.** No score, no go/no-go, no readiness percentage: the app shows
  the evidence and people decide.
- **Checked against what flew.** IM-1, IM-2 and Blue Ghost 1: touchdown times
  agree with NASA's descent reconstructions to the second, landing positions to
  within 100 m, and our Sun and Earth elevations at touchdown with a direct SPICE
  calculation to 0.00003°. Blue Ghost 1's sunset falls on the date NASA reported.
  The trip, launch-time, radiation, line-of-sight and weather models each have
  their own check against flown trajectories or independent tools. All of it,
  with what it does *not* show, is in [docs/validation.md](docs/validation.md).
- **AI that cannot invent a number.** The assistants (Gemini) answer only from
  tool results; a guard rejects any figure the tools did not return. Without a
  key they fall back to answers written directly from the measurements.

## Test it

```bash
make test-fast     # 675 unit, property and golden tests, no services, about 20 s
make lint          # ruff, mypy --strict, 10 layering contracts
make test          # 898 backend tests against real kernels, terrain and a test database, about 7 min
cd frontend && npm run check && npm test     # TypeScript, 292 unit and component tests
cd frontend && npm run e2e                   # 61 browser tests with accessibility checks; needs the app running
```

`make test` needs a seeded database (`python3 run.py` once, or `make seed`).
The browser tests drive the real app against the real API and run axe
(WCAG 2.1 A and AA) on every page in both themes; start the app first. The full
plan is [docs/test-plan.md](docs/test-plan.md).

## How it is built

```
frontend/   Vite, React 19, TypeScript, Tailwind v4; three.js for the Moon and the scenes.
            It computes no physics: every number on screen comes from the API.
backend/    FastAPI and Pydantic v2 over PostgreSQL, with Redis as an optional cache.
  app/core/       the geometry and astrodynamics: pure functions, no I/O (enforced by import contracts)
  app/services/   policy; app/api/ routes and schemas; app/agents/ the AI helpers and their guard
  app/workers/    compute (trip, contact and launch answers) and feeds (live weather and space weather)
data/       mission records and catalogues, every field sourced; downloaded NASA data lands here too
docs/       architecture, API, validation, decisions (ADRs), runbook
```

Start with [docs/README.md](docs/README.md): it indexes the system design, the
API reference, the 19 architecture decision records and the runbook.

## Running it

`python3 run.py` tracks what it starts in `.local/run.pids` and stops only that.
If port 8000 or 5173 is held by another program it says which and exits rather
than killing it. Ctrl+C stops everything together; a compute worker hands an
unfinished job back to the queue first. PostgreSQL (port 5433) and Redis (port
6380) are left running between runs; `python3 run.py --stop-services` stops
them. Useful options: `--skip-install`, `--no-data`, `--no-feeds`,
`--backend-port`, `--frontend-port`.

On Windows use `python run.py`; see [the Windows notes](docs/windows-setup.md).
The make targets (`make help`) run the same steps one at a time.

### Keys are optional

Everything above works with no key. Three settings in `.env` add to it:

- `PW_GEMINI_API_KEY`: the AI assistants answer with a model. Without it they
  answer from the measurements alone.
- `PW_NASA_API_KEY`: a higher rate limit for NASA's space-weather database.
- `PW_EARTHDATA_TOKEN`: only for the two very large archives
  (`polar-data sync --tier bulk`).

### On a server

`python3 run_onVM.py` is for an Ubuntu VM. It installs Docker if it is missing,
stops what an earlier run left (this project's containers and any container
holding a port it needs), removes stopped containers, dangling images and the
build cache, builds both images from nothing, downloads the datasets into
`./data`, starts the stack and waits until it answers. Only the dashboard's port
(80 by default) is open to the outside; the database, the cache and the API are
published on `127.0.0.1`.

```bash
git clone https://github.com/MdAhbab/PolarWindow.git && cd PolarWindow
python3 run_onVM.py                                   # first run: also the downloads
python3 run_onVM.py --data-from ~/polar-window-data.zip   # or bring the data from another machine
python3 run_onVM.py --status                          # what is running, and /healthz
python3 run_onVM.py --stop                            # stop; the data and the database stay
```

`--port` serves it elsewhere than 80, `--keep-cache` reuses Docker's build
cache, `--with-validation` also fetches the datasets that only check our
numbers, `--fresh-db` empties the database, and `--dry-run` prints every command
without running any. It serves plain HTTP: put a TLS proxy or a load balancer in
front for HTTPS. Allow the port in the cloud provider's firewall. The stack is
`docker-compose.yml` with the `web` profile; [docs/runbook.md](docs/runbook.md)
has the details.

## Known limits

- The battery limit (120 h) is a reference value; there is no thermal model, and
  the backend returns durations, never a verdict on survival.
- Terrain height error is one figure per terrain product (2 m at 20 m spacing,
  4 m at 80 m and 60 m, 3.5 m for SLDEM2015), not per pixel.
- A mission target with no terrain window on disk is computed on flat ground
  and says so (`terrain_modelled: false`).
- Launch directions for missions that have not flown are taken from flown
  vehicles (IM-1, IM-2).
- Planned missions whose target, launch date or payloads are not published show
  "not published": nothing is filled in.
- No screen-reader user has tested it yet; the automated accessibility checks
  pass, and that is not the same thing.
- More in [docs/validation.md](docs/validation.md) and
  [docs/test-plan.md](docs/test-plan.md).

## Required data

Everything the app reads is public NASA data (most of it also listed on
[data.nasa.gov](https://data.nasa.gov/dataset)). You do not need to fetch it by
hand: `python3 run.py` starts the app first, then checks every dataset below and
downloads whatever is missing, resuming any download that was interrupted. If
the new data is something the API loads at start-up (SPICE kernels, terrain,
seeded sites), it restarts the backend for you. The same step on its own:

```bash
cd backend
uv run polar-data list                  # what is on disk and what is missing
uv run polar-data sync                  # core, lifecycle and validation data
uv run polar-data sync --tier bulk      # also the large archives (needs PW_EARTHDATA_TOKEN)
```

Keys are optional. Without `PW_EARTHDATA_TOKEN` (a free
[NASA Earthdata Login](https://urs.earthdata.nasa.gov) token) the bulk archives
are skipped and the rest works. `PW_NASA_API_KEY` (free from
[api.nasa.gov](https://api.nasa.gov)) only raises the space-weather rate limit.
Live feeds (weather forecasts, space weather now, DSN Now, the orbiters' tracks
from JPL Horizons) are not files and are not in this table; the feeds worker
fetches them on a schedule.

**Copying the data instead of downloading it.** The first download takes hours,
because some NASA archive servers send about 30 kB/s. A machine that has the
data can pass it on (about 1.2 GB, all public data, nothing secret in it):

```bash
python3 run.py --export-data ~/polar-window-data.zip   # or a folder, for example in Google Drive
```

Share the file or the folder. On the other machine, before the first start:

```bash
python3 run.py --data-from ~/Downloads/polar-window-data.zip
```

`--data-from` takes the `.zip`, the folder, or the folder holding the several
`.zip` parts Google Drive makes when it downloads a large folder. Every file is
checked against the SHA-256 listed at export: a damaged file is not used (it is
downloaded instead), a file already on the machine is never replaced, and what
the copy lacks is downloaded as usual. Without starting the app:
`uv run polar-data export PATH` and `uv run polar-data import PATH` in `backend/`.

This table is generated from `backend/app/data/registry.py`; a test fails if
the two disagree. Regenerate it with `uv run polar-data readme`.

<!-- required-data:begin (generated by `polar-data readme`; do not edit) -->

**Needed to start (fetched first)**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [SPICE LSK naif0012.tls](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls) | NASA JPL NAIF | 5.0 kB | `kernels/naif0012.tls` | Leapseconds. Without it every UTC -> ET conversion fails and no timestamp can be interpreted at all. | none |
| [SPICE SPK de440.bsp](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp) | NASA JPL NAIF | 100 MB | `kernels/de440.bsp` | Planetary ephemeris. Without it there are no Sun or Earth positions, so sunlight and Earth-contact hours cannot be computed. | none |
| [SPICE PCK pck00011.tpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc) | NASA JPL NAIF | 100 kB | `kernels/pck00011.tpc` | Body constants: the Moon's radii and orientation model. Without it the lunar body-fixed frame has no shape to attach to. | none |
| [SPICE PCK moon_pa_de440_200625.bpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc) | NASA JPL NAIF | 10 MB | `kernels/moon_pa_de440_200625.bpc` | Lunar principal-axis orientation. Without it MOON_PA -- and therefore MOON_ME -- cannot be realised, so azimuths are meaningless. | none |
| [SPICE FK moon_de440_250416.tf](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf) | NASA JPL NAIF | 5.0 kB | `kernels/moon_de440_250416.tf` | Frame kernel defining MOON_ME relative to MOON_PA. Without it SPICE knows the Moon's spin but not the mean-Earth frame the site coordinates are expressed in. | none |
| [LOLA south polar elevation model, 80 m (LDEM_80S_80M)](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_80s_80m.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / PDS Geosciences | 116 MB | `dem/regional_80m.npz` | Terrain for every site south of 80 deg S: the skyline that decides sunlight and contact with Earth, the map tiles and site placement. | none |
| [LOLA south polar elevation model, 20 m (LDEM_80S_20M), windows around each site](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_80s_20m.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / PDS Geosciences | 40 MB | `dem/fine/` | The near skyline at each site. Only a 20 km window per site is read, by HTTP range requests; the 1.85 GB file is never downloaded whole. | none |
| [LOLA south polar elevation model, 60 m (LDEM_60S_60M), window for APEX-1 (Schrödinger)](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_60s_60m.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / PDS Geosciences | 4.7 MB | `dem/fine/feature-schrodinger.npz` | The skyline at Schrödinger for APEX-1. A 55 km window is read by HTTP range requests; the 1.93 GB file is never downloaded whole. | none |
| [SLDEM2015 elevation model (59 m), window for Blue Ghost 1 (Mare Crisium)](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/sldem2015/tiles/float_img/sldem2015_512_00n_30n_045_090_float.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / SELENE TC / PDS Geosciences | 11 MB | `dem/fine/mission-blue-ghost-m1.npz` | The skyline at Mare Crisium for Blue Ghost 1. A 55 km window is read by HTTP range requests from SLDEM2015. | none |
| [SLDEM2015 elevation model (59 m), window for Peregrine M1 (Sinus Viscositatis)](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/sldem2015/tiles/float_img/sldem2015_512_30n_60n_315_360_float.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / SELENE TC / PDS Geosciences | 14 MB | `dem/fine/feature-sinus-viscositatis.npz` | The skyline at Sinus Viscositatis for Peregrine M1. A 55 km window is read by HTTP range requests from SLDEM2015. | none |
| [SLDEM2015 elevation model (59 m), window for IM-3 (Reiner Gamma)](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/sldem2015/tiles/float_img/sldem2015_512_00n_30n_270_315_float.img) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LOLA / SELENE TC / PDS Geosciences | 11 MB | `dem/fine/feature-reiner-gamma.npz` | The skyline at Reiner Gamma for IM-3. A 55 km window is read by HTTP range requests from SLDEM2015. | none |
| Skylines and reference numbers for every site (built locally) | Built from the LOLA and SPICE data above | - | `(database)` | The 1,440-bearing skyline and the four numbers for each candidate and mission site; built once, then every answer is a lookup. | none |

**Needed by the launch, trip and contact sections**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [SPICE PCK gm_de440.tpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/gm_de440.tpc) | NASA JPL NAIF | 10 kB | `kernels/gm_de440.tpc` | Gravitational parameters consistent with DE440. Without it the trip propagator has no masses for the Sun, Earth and Moon. | none |
| [SPICE PCK earth_1962_260806_2126_combined.bpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_1962_260806_2126_combined.bpc) | NASA JPL NAIF | 31 MB | `kernels/earth_1962_260806_2126_combined.bpc` | Earth orientation (ITRF93): measured to 2026-08-06, predicted to 2126. Without it launch pads and ground stations cannot be placed in space, so launch times and station view periods cannot be computed. | none |
| [SPICE SPK earthstns_itrf93_260814.bsp](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/stations/earthstns_itrf93_260814.bsp) | NASA JPL NAIF | 10 kB | `kernels/earthstns_itrf93_260814.bsp` | Deep Space Network antenna positions. Without it the ground stations that can hear a lander cannot be computed. | none |
| [SPICE FK earth_topo_260814.tf](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/stations/earth_topo_260814.tf) | NASA JPL NAIF | 10 kB | `kernels/earth_topo_260814.tf` | Local horizon frames at each Deep Space Network antenna. Without it a station's elevation above its horizon cannot be computed. | none |
| [Native rover terrain: 3/4 m LROC NOBILE and 5 m LOLA site windows](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_NOBILE04) ([data.nasa.gov](https://data.nasa.gov/dataset/lro-moon-laser-altimeter-4-gdr-v1-0)) | NASA LRO LROC / LOLA, PDS archives | 64 MB | `dem/rover_3m/, dem/rover_4m/ and dem/rover_5m/` | Rover-to-lander sight and radio paths: native 3/4 m stereo terrain at Mons Mouton/Nobile, 5 m LOLA south of 87.5 deg S, including their terrain maps. Stereo gaps stay unknown. Coarser 20 m or 80 m terrain is used where a full neighbourhood is not covered. Height error is stated for each product. | none |
| [GRAIL lunar gravity field GRGM1200A (spherical harmonics)](https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/gggrx_1200a_sha.tab) ([data.nasa.gov](https://data.nasa.gov/dataset/grail-moon-lgrs-derived-gravity-science-data-products-v1-0)) | NASA GRAIL / PDS Geosciences | 88 MB | `gravity/gggrx_1200a_sha.tab` | The Moon's lumpy gravity for the trip and lunar orbit: without it a low lunar orbit drifts kilometres a day from where it really is. | none |
| [GRAIL GRGM1200A label (reference radius, GM, normalisation)](https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/gggrx_1200a_sha.lbl) ([data.nasa.gov](https://data.nasa.gov/dataset/grail-moon-lgrs-derived-gravity-science-data-products-v1-0)) | NASA GRAIL / PDS Geosciences | 11 kB | `gravity/gggrx_1200a_sha.lbl` | Reads the gravity field correctly: the label defines its units and frame. | none |
| [DSN Telecommunications Link Design Handbook 810-005, module 301 (coverage and geometry, antenna horizon masks)](https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301O.pdf) | NASA JPL Deep Space Network | 3.1 MB | `dsn/810-005-301O.pdf` | Each Deep Space Network antenna's real horizon: the lowest elevation at which it can hear the Moon, by direction. | none |
| [DSN 810-005 module 301 Rev. O horizon mask spreadsheet (every antenna, every degree of azimuth, effective 1 May 2024)](https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/Horizon-Masks-Download-V2-301O.xlsx) | NASA JPL Deep Space Network | 441 kB | `dsn/Horizon-Masks-Download-V2-301O.xlsx` | The ground-station catalogue's receive masks: when each Deep Space Network antenna can hear the Moon (python -m app.data.build_ground_stations). | none |
| [OMNI hourly solar wind, geomagnetic and solar indices (OMNI2_H0_MRG1HR), 1963 to date](https://gov-nasa-hdrl-data1.s3.amazonaws.com) ([data.nasa.gov](https://data.nasa.gov/dataset/omni-hourly-data-set)) | NASA GSFC Space Physics Data Facility, via NASA HelioCloud on AWS | 190 MB | `spaceweather/omni_hourly/` | Solar activity (F10.7, Ap) that sets air drag in Earth orbit, and the history of solar storms and proton events used to check radiation estimates. | none |

**Used only to check our numbers**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [IM-1 Odysseus reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2im_im1_cru_rec_240216_240221_v01.bsp) | NASA JPL NAIF / PDS | 72 kB | `clps/clps_to2im_im1_cru_rec_240216_240221_v01.bsp` | Checks our trip and launch-time calculations against where IM-1 actually flew (February 2024). | none |
| [IM-2 Athena reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_prime1_im2_cru_rec_250227_250306_v01.bsp) | NASA JPL NAIF / PDS | 9.5 MB | `clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp` | Checks our trip and launch-time calculations against IM-2 (March 2025). | none |
| [Blue Ghost Mission 1 reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp) | NASA JPL NAIF / PDS | 24 MB | `clps/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp` | Checks the Earth-orbit loops and lunar orbit against Blue Ghost 1 (January to March 2025). | none |
| [Peregrine Mission One reconstructed trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp) | NASA JPL NAIF / PDS | 863 kB | `clps/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp` | Tests that the trip model notices an unmodelled push: Peregrine's propellant leak (January 2024). | none |
| [IM-1 Odysseus reconstructed descent trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2im_im1_edl_rec_240222_v01.bsp) | NASA JPL NAIF / PDS | 415 kB | `clps/clps_to2im_im1_edl_rec_240222_v01.bsp` | Reconstructed descent trajectory and touchdown instant for IM-1 Odysseus. | none |
| [IM-1 Odysseus landing site ephemeris (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2im_im1_ls_242022_v02.bsp) | NASA JPL NAIF / PDS | 8.2 kB | `clps/clps_to2im_im1_ls_242022_v02.bsp` | Landing site coordinates for IM-1 Odysseus from NAIF. | none |
| [IM-1 Odysseus post-touchdown surface position (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2im_im1_atls_242022_v01.bsp) | NASA JPL NAIF / PDS | 7.2 kB | `clps/clps_to2im_im1_atls_242022_v01.bsp` | Surface ephemeris for IM-1 Odysseus after touchdown. | none |
| [IM-1 Odysseus structure and instrument frame offsets (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to2im_im1_struct_v01.bsp) | NASA JPL NAIF / PDS | 8.2 kB | `clps/clps_to2im_im1_struct_v01.bsp` | Structure and frame offsets for IM-1 Odysseus instruments. | none |
| [IM-2 Athena reconstructed descent trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_prime1_im2_edl_rec_250306_v01.bsp) | NASA JPL NAIF / PDS | 15 MB | `clps/clps_prime1_im2_edl_rec_250306_v01.bsp` | Reconstructed descent trajectory and touchdown instant for IM-2 Athena. | none |
| [IM-2 Athena landing site ephemeris (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_prime1_im2_ls_250306_v01.bsp) | NASA JPL NAIF / PDS | 7.2 kB | `clps/clps_prime1_im2_ls_250306_v01.bsp` | Landing site coordinates for IM-2 Athena from NAIF. | none |
| [IM-2 Athena post-touchdown surface position (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_prime1_im2_atls_250306_v01.bsp) | NASA JPL NAIF / PDS | 7.2 kB | `clps/clps_prime1_im2_atls_250306_v01.bsp` | Surface ephemeris for IM-2 Athena after touchdown. | none |
| [Blue Ghost Mission 1 reconstructed descent trajectory (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to19d_bgm1_edl_rec_250302_v01.bsp) | NASA JPL NAIF / PDS | 58 kB | `clps/clps_to19d_bgm1_edl_rec_250302_v01.bsp` | Reconstructed descent trajectory and touchdown instant for Blue Ghost 1. | none |
| [Blue Ghost Mission 1 landing site ephemeris (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to19d_bgm1_ls_250302_v01.bsp) | NASA JPL NAIF / PDS | 8.2 kB | `clps/clps_to19d_bgm1_ls_250302_v01.bsp` | Landing site coordinates for Blue Ghost 1 from NAIF. | none |
| [Blue Ghost Mission 1 post-touchdown surface position (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/spk/clps_to19d_bgm1_atls_250302_v01.bsp) | NASA JPL NAIF / PDS | 8.2 kB | `clps/clps_to19d_bgm1_atls_250302_v01.bsp` | Surface ephemeris for Blue Ghost 1 after touchdown. | none |
| [IM-1 Odysseus frame kernel (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/clps_to2im_im1_v02.tf) | NASA JPL NAIF / PDS | 27 kB | `clps/clps_to2im_im1_v02.tf` | Frame definitions for IM-1 Odysseus and its landing site. | none |
| [IM-2 Athena frame kernel (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/clps_prime1_im2_v01.tf) | NASA JPL NAIF / PDS | 27 kB | `clps/clps_prime1_im2_v01.tf` | Frame definitions for IM-2 Athena and its landing site. | none |
| [Blue Ghost Mission 1 frame kernel (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/clps_to19d_bgm1_v01.tf) | NASA JPL NAIF / PDS | 33 kB | `clps/clps_to19d_bgm1_v01.tf` | Frame definitions for Blue Ghost 1 and its landing site. | none |
| [Peregrine Mission One frame kernel (CLPS SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/clps_to2ab_apm1_v02.tf) | NASA JPL NAIF / PDS | 25 kB | `clps/clps_to2ab_apm1_v02.tf` | Frame definitions for Peregrine Mission One. | none |
| [LRO reconstructed orbit, March to June 2025 (LRO SPICE archive)](https://naif.jpl.nasa.gov/pub/naif/pds/data/lro-l-spice-6-v1.0/lrosp_1000/data/spk/lrorg_2025074_2025166_v01.bsp) | NASA JPL NAIF / PDS | 7.7 MB | `validation/lro/lrorg_2025074_2025166_v01.bsp` | Checks the trip calculation in low lunar orbit against where the Lunar Reconnaissance Orbiter actually flew. | none |
| [Goldstone radar elevation model of the lunar south pole (~150 m)](https://pds-geosciences.wustl.edu/lunar/gdscc-l-dss14_dss13_dss15_dss25-5-v1/lram_10xx/data/south_pole_mosaic.img) ([data.nasa.gov](https://data.nasa.gov/dataset/goldstone-moon-dss14-dss13-dss15-dss25-5-altimetry-v1-0)) | NASA JPL Goldstone Solar System Radar / PDS Geosciences | 64 MB | `validation/goldstone/south_pole_mosaic.img` | An independent terrain measurement (radar, not laser) to check the skylines built from LOLA. | none |
| [Goldstone south pole elevation model label (projection and units)](https://pds-geosciences.wustl.edu/lunar/gdscc-l-dss14_dss13_dss15_dss25-5-v1/lram_10xx/data/south_pole_mosaic.lbl) ([data.nasa.gov](https://data.nasa.gov/dataset/goldstone-moon-dss14-dss13-dss15-dss25-5-altimetry-v1-0)) | NASA JPL Goldstone Solar System Radar / PDS Geosciences | 4.9 kB | `validation/goldstone/south_pole_mosaic.lbl` | Reads the Goldstone elevation model correctly. | none |
| [OSIRIS-REx sample return capsule, reconstructed from release to entry interface (OD 383a), 24 September 2023](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/orex/orex_spice/spice_kernels/spk/src_230924_230924_230930_od383a_v1.bsp) | NASA NAIF / PDS (OSIRIS-REx SPICE archive) | 58 kB | `validation/orex/src_230924_230924_230930_od383a_v1.bsp` | The entry state the capsule entry model starts from, to check its landing point against the measured one. | none |
| [NOAA GEFS 10 m wind at the Cape, one year of archived forecasts (reduced here)](https://noaa-gefs-pds.s3.amazonaws.com) | NOAA NCEP, via AWS Open Data | 481 kB | `hindcast/gefs_wind_florida.cache.jsonl` | Re-running the one-year check of the wind rules' shares against the Cape's weather station. The result itself is kept in the repository. | none |
| [Measured air at 30-70 km on OSIRIS-REx's entry day: TIMED/SABER and the Table Mountain lidar (originals)](https://cdaweb.gsfc.nasa.gov/sp_phys/data/timed/saber/level2a_netCDF/2023/267/) | NASA TIMED/SABER (CDAWeb) and NASA JPL Table Mountain Facility (NDACC) | 82 MB | `bulk/capsule_air/` | Re-making the two small profiles the capsule's atmosphere models are checked against. The profiles themselves are kept in the repository. | none |

**Large archives, fetched only on request (`polar-data sync --tier bulk`)**

| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |
|---|---|---|---|---|---|
| [KSC Advanced Ground Based Field Mill network, 1997-2012](https://data.ghrc.earthdata.nasa.gov/ghrcw-protected/kscmill__1/) ([data.nasa.gov](https://data.nasa.gov/dataset/ksc-advanced-ground-based-field-mill-v1-7b0b5)) | NASA MSFC GHRC DAAC | 1.5 TB | `bulk/kscmill/` | How often the electric field at Kennedy exceeds the launch limit, by month and hour: the history behind the field-mill launch rule. | NASA Earthdata Login (free) |
| [Combined GLM hourly thunder-hour data, 2019-2025](https://data.ghrc.earthdata.nasa.gov/ghrcw-protected/glmhth__1/) ([data.nasa.gov](https://data.nasa.gov/dataset/combined-geostationary-lightning-mapper-glm-hourly-thunder-hour-data-product)) | NASA MSFC GHRC DAAC | 77 GB | `bulk/glm_thunder_hours/` | How often lightning is seen near each launch pad, by month and hour, for dates beyond the weather forecast. | NASA Earthdata Login (free) |
| [NOAA GEFSv12 reforecast, 10 m wind at the pads, 2000-2019 (reduced here)](https://noaa-gefs-retrospective.s3.amazonaws.com) | NOAA PSL and EMC, via AWS Open Data | 759 kB | `hindcast/gefs_reforecast_wind.cache.jsonl` | Re-running the many-year check of the wind rules at the Cape and Vandenberg. Only the pads' grid points are read, by byte ranges, from a 50 GB archive; the result is kept in the repository. | none |
| [NOAA HRRR version 4, 10 m wind at the pads, 2021-2025 (reduced here)](https://noaa-hrrr-bdp-pds.s3.amazonaws.com) | NOAA NCEP, via AWS Open Data | 590 kB | `hindcast/hrrr_wind.cache.jsonl` | Re-running the check of HRRR's wind at the Cape and Vandenberg, read by byte ranges from a 100 GB archive. The result is kept in the repository. | none |
| [Hourly wind at the Cape (KXMR) and Vandenberg (KVBG) weather stations (ASOS)](https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py) | Iowa Environmental Mesonet (Iowa State University), from NWS ASOS | 10 MB | `hindcast/asos_*.csv` | The observed wind that every weather check is scored against; fetched by the three weather-check commands. | none |

<!-- required-data:end -->

## Data and credits

Every number traces to a public source, listed in full in `docs/data-sources.md`:

- **Terrain:** LOLA polar elevation models `LDEM_80S_20M`, `LDEM_80S_80M` and
  `LDEM_60S_60M`, and SLDEM2015 (LOLA with SELENE Terrain Camera), from the LOLA
  team via the PDS Geosciences Node; LROC NAC stereo terrain at Mons Mouton
  (NASA/GSFC/Arizona State University).
- **Sun and Earth positions, and frames:** NAIF SPICE kernels `de440`,
  `moon_pa_de440_200625`, `moon_de440_250416`, `pck00011` and `naif0012`, from
  NAIF / JPL.
- **CLPS missions:** NASA Science CLPS delivery pages, NASA news releases,
  LROC landing-site images (NASA/GSFC/Arizona State University) and the NAIF
  CLPS SPICE archive (flown trajectories, descents and landing sites), with a
  source and an access date on every record in `data/missions.json`.
- **Feature names and centres:** the IAU Gazetteer of Planetary Nomenclature
  (USGS Astrogeology) and the LPI Lunar South Pole Atlas.

## License

Apache License 2.0; see `LICENSE`.

---

**This is not a NASA product and is not endorsed by NASA** or any other space
agency. It was built for the NASA International Space Apps Challenge. Data
product and mission names are the public identifiers of the sources above, used
to cite them; no agency logo or insignia appears anywhere in it.
