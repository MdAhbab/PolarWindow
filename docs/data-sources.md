# Data sources

Every number and name on screen comes from one of the sources below. This file
is the research log for `data/missions.json` and the rulebook for anything
added to it later.

## Terrain and ephemeris

| Input | Product | Publisher | Used for |
|---|---|---|---|
| Polar DEM, 20 m | `LDEM_80S_20M` | LOLA team, PDS Geosciences Node | Fine horizon windows (20 km around each polar site) |
| Polar DEM, 80 m | `LDEM_80S_80M` | LOLA team, PDS Geosciences Node | Regional horizon, 20–50 km |
| Planetary ephemeris | `de440.bsp` | NAIF / JPL | Sun and Earth vectors |
| Lunar orientation | `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`, `pck00011.tpc` | NAIF / JPL | `MOON_ME` frame |
| Leap seconds | `naif0012.tls` | NAIF | UTC ↔ TDB |
| Feature names and centres | Gazetteer of Planetary Nomenclature | IAU / USGS Astrogeology | Mission targets with no published landing point |
| Candidate-site anchors | Lunar South Pole Atlas | LPI | The 15 candidate sites' anchors (`data/sites.json`) |

The polar DEM covers **80°S–90°S only**. Outside it, Sun and Earth are still
computed with SPICE, but against a smooth-Moon horizon, and every response says
`terrain_modelled: false` (ADR-6).

## CLPS missions (`data/missions.json`)

Compiled 2026-09-23. 20 deliveries, 64 payloads.

### Source precedence

1. **NASA Science CLPS delivery pages**
   (`science.nasa.gov/lunar-science/clps-deliveries/…`). These give payload
   manifests, targets and task orders. Each page's own "last updated" date is
   recorded in the source title.
2. **NASA news releases and articles** (`nasa.gov`). These give launch,
   landing, end of mission, status, and changes that postdate a delivery page.
3. **LROC** (`lroc.im-ldi.com`, NASA/GSFC/Arizona State University). This gives
   **actual landing coordinates**, measured from LRO images.
4. **IAU Gazetteer**, for the centre of a named target feature when no landing
   point is published.
5. Provider releases are not used as the only source for any field.

When two NASA pages disagree, the **newer** page wins, and the disagreement is
written into the record's `notes`. It is never silently resolved.

### Rules

- **Every record has at least one source, and every payload has a
  `source_url`.** The ingest fails otherwise.
- **A field with no source is `null` and listed in `unconfirmed_fields`.** The
  UI shows the word "Unconfirmed", never a guess.
- `unconfirmed_fields` containing `payloads` means the manifest is **known to be
  incomplete**: NASA counts more payloads than it names.
- **Dates carry their precision** (`minute`, `day`, `month`, `quarter`, `year`)
  and the **verbatim published phrase** (`as_published`, for example
  "late 2027"). A year-precision date is stored as 1 January of that year. The
  phrase, not the stored date, is what the UI shows.
- **Coordinate kinds:**
  - `actual_landing`: where the lander came to rest, from LROC. This applies to
    IM-1, IM-2 and Blue Ghost Mission 1.
  - `planned_target`: a landing point published before flight. None is in use
    yet; IM-2's intended site is kept in its notes.
  - `feature_centre`: the IAU centre of the named target (Mons Mouton,
    Reiner Gamma, Schrödinger, Sinus Viscositatis). **It is not a landing
    point**, and the UI says so. Missions that share a feature share one site.
- A region described only as "the lunar south pole", "the far side" or
  "the Gruithuisen Domes" (not a single IAU feature) gets **no coordinate**.

### Instrument-type classification

`instrument_types` is **this project's** classification. It is assigned from
each payload's sourced "Type of Instrument", "Key Measurement" or summary. It
exists so the payload filter works, and it is not a NASA taxonomy.

| Type | Assigned when the source describes… |
|---|---|
| `volatiles` | Hydrogen, water ice, volatile gases, or drilling for them (NSS, NIRVSS, PITMS, TRIDENT, MSOLO, PROSPECT, L-CIRiS, MoonRanger, VIPER) |
| `geology_geophysics` | Composition, seismology, magnetics, interior structure |
| `heat_flow` | Subsurface temperature or heat-flow probes |
| `radiation_space_weather` | Radiation dosimetry, energetic particles, magnetosphere imaging |
| `exosphere_dust` | The photoelectron sheath, plasma, dust adhesion, or lander exhaust alteration |
| `imaging` | Cameras and imaging radiometers |
| `landing_navigation` | Descent sensors, navigation beacons, GNSS reception |
| `communications` | Radio links as the demonstrated capability |
| `laser_retroreflector` | Passive retroreflectors (LRA, NGLR, MoonLIGHT) |
| `rover_mobility` | A rover, or a payload mounted on one |
| `technology_demo` | Engineering demonstrations (drills, arms, dust shields, gauges, solar cells) |
| `other` | Anything else (space biology, radio astronomy) |

### Known gaps and conflicts, as of 2026-09-23

- **Griffin-1 (TO20A).** NASA's TO20A page names one payload (LRA). NASA's
  August 2026 update says five NASA payloads will ride on the Astrolab FLIP
  rover. The deliveries overview still reads "Astrobotic's Griffin lander … in
  2025"; the newer pages name Voyager Technologies and a late-2026 launch.
- **IM-3 (CP-11).** The CP-11 page names four NASA payloads; the August 2026
  update says five.
- **Blue Ghost Mission 2 (CS-3/4).** NASA counts three payloads and names one
  (LuSEE-Night).
- **CT-4, CS-8, CX-2, and the four June 2026 Moon Base awards.** Destinations,
  landers or names are unpublished, and are recorded as unconfirmed.
- **Blue Moon MK1 "Endurance" (CT-3).** In September 2025 NASA targeted launch
  "later this year". In August 2026 it was still in testing, so no date is
  asserted.
- **IM-1.** Landing and end of mission are known to the day ("seven days after
  landing"), not the hour. The surface window is therefore day-precision.

### Re-verification

Re-run the research against the pages above:
- before any public demo;
- at the **28 Oct 2026** full-statement checkpoint;
- whenever NASA announces a launch or landing.

Update `accessed` on every source you re-read. The API serves `data_version` (a
hash of each record), so a changed record is visible.

## Candidate sites (`data/sites.json`)

These are derived by `backend/app/data/ingest_sites.py` from LPI Lunar South
Pole Atlas anchors. The landing point is the most open-skied landable post in
the top elevation decile of a stated ring or disc around the anchor, with a
maximum slope of 12°. The anchor, search region, offset and rule are stored on
every site and returned by the API.

## The mission lifecycle (tracks T1–T4, E, H)

Three kinds of source feed the sections (Ready, Launch, Trip, Contact, Return and
space weather). Each number says which one it came from (`provenance`, invariant 10)
and, when it is live, how old it is (invariant 11).

### Files, fetched once (`backend/app/data/registry.py`)

Every file is listed once in the registry, with its URL, size, sha256 and what it is
used for; the README's "Required data" table is generated from it
(`uv run polar-data readme --write`) and `polar-data sync` downloads it. Tiers:
`core` (the product will not start without it), `lifecycle` (NASA's reconstructed
CLPS trajectories from NAIF, GRAIL gravity, EGM2008 Earth gravity from ICGEM,
JPL Horizons lunar orbiter states, DSN station kernels), `bulk` (large archives
fetched on demand: GLM thunder hours, KSC field mill, GEFSv12 reforecast, HRRR archive
on AWS, ASOS station archives) and `validation` (only for `make validate-*`: the
OSIRIS-REx capsule's reconstructed entry, the air measured at 30 to 70 km on its entry day
from TIMED/SABER and the Table Mountain lidar (`nasa:capsule-air`), Goldstone radar DEM,
IRBEM references).

### Cited catalogues (`data/catalogues/*.json`, ADR-10)

`launch_sites`, `vehicles` (with the injection accuracies printed in each vehicle's own user guide, listed below; assumed where unpublished), `weather_rules` (NASA FS-2020-05-568-KSC, verbatim),
`recovery_zones` (Launch Library 2 landing records), `ground_stations`, `relays`,
`landing_attempts`, `risk_scales` and `lessons`. Every record carries its sources and
the date it was compiled; `make catalogues` validates them. A value no source
publishes is absent with a reason, never filled in.

Injection accuracies in `vehicles`, row by row, with the page:

| Vehicle | Document | Sigma | Read from |
|---|---|---|---|
| Falcon 9 | Falcon 9 Launch Vehicle Payload User's Guide, Rev 2 (21 October 2015), section 3.6, Table 3-2, page 16 of 69 | 3, as printed | SpaceX's file as archived on 23 December 2016: `https://web.archive.org/web/20161223112909/http://www.spacex.com/sites/spacex/files/falcon_9_users_guide_rev_2.0.pdf` |
| Vulcan Centaur | Vulcan Launch Systems User's Guide, October 2023, section 2.3, Table 2.3-1, printed page 2-9 (page 22 of 85 in the PDF) | not stated; 3 assumed | `https://www.ulalaunch.com/docs/default-source/rockets/2023_vulcan_user_guide.pdf` |
| New Glenn | New Glenn Payload User's Guide, October 2018 (Rev C), section 2.6, Table 2-3, page 31 of 124 | 3, as printed | a copy on `yellowdragonblogdotcom.wordpress.com` uploaded in January 2019, because `blueorigin.com` answered every download with HTTP 429 |
| Falcon Heavy | none published, so none is entered | not applicable | not applicable |

Only Rev 2 (October 2015) of SpaceX's Falcon guide prints an orbit-insertion accuracy. The
guides of April 2020, September 2021 and May 2025 were read and have none, so it is the
accuracy the guide gave for the vehicle of 2015, not a figure for Block 5. Falcon 9's is not
carried over to Falcon Heavy. The Falcon 9 and New Glenn guides have low Earth orbit and
geosynchronous transfer orbit rows only. The Vulcan guide has seven rows, one of them for
lunar transfer and Earth escape.

### Computed once and committed

| File | Made by | From |
|---|---|---|
| `data/climatology/power_ws50m_*.json` | `make climatology` | NASA POWER hourly wind at 50 m, 2001–2024 |
| `data/climatology/glm_thunder_*.json` | `make thunder-climatology` | GLM thunder hours, GHRC DAAC (Earthdata token) |
| `data/hindcast/gefs_wind_florida.json` | `make hindcast-weather` | GEFS on AWS against the Cape's station (IEM) |
| `data/hindcast/gefs_reforecast_wind_*.json` | `make hindcast-reforecast` | GEFSv12 2000-2019 reforecast against pad stations (IEM) |
| `data/hindcast/hrrr_wind_*.json` | `make hindcast-hrrr` | HRRR v4 2021-2025 byte-range archive on AWS against pad stations |
| `data/radiation/*.json` | `make space-climate` | Oulu neutron monitor (NMDB), GOES events (NCEI), DONKI |
| `data/capsule/orex_check.json` | `make validate-capsule` | the entry model against OSIRIS-REx's landing under NRLMSIS 2.1, the air model chosen from the two profile files below |
| `data/capsule/saber_20230924.json` | `uv run python -m app.validation.capsule_air_data` | TIMED/SABER Level 2A version 2.08 limb profiles of 24 September 2023 (136 profiles, 28 to 49° N), from NASA's CDAWeb copy of the GATS archive, `https://cdaweb.gsfc.nasa.gov/sp_phys/data/timed/saber/level2a_netCDF/2023/267/`; the producer marks the files "Unvalidated" |
| `data/capsule/tmf_lidar_202309.json` | `uv run python -m app.validation.capsule_air_data` (needs `pyhdf`) | NASA JPL Table Mountain Facility Rayleigh lidar (34.4° N; NDACC), temperature and density profiles for nine nights from 19 to 30 September 2023, `https://www-air.larc.nasa.gov/pub/NDACC/PUBLIC/stations/table.mountain.ca/hdf/lidar/` |

### Live feeds (ADR-8; `make feeds`, listed at `GET /feeds`)

Only the feeds worker reaches these (an import contract forbids anything else from
importing `app.feeds`). Each product is recorded as a snapshot with its fetch time;
past its staleness budget its numbers are replaced by the reason.

| Provider | Products | Budget | Used by |
|---|---|---|---|
| NOAA SWPC | Kp (+ forecast), GOES protons and X-rays, solar wind and field, alerts, 3-day forecast, F10.7 | 1 h to 2 d | space weather, launch weather's space weather rule |
| NASA DONKI | CMEs, flares, particle events (last 30 days; `PW_NASA_API_KEY`, else DEMO_KEY) | 24 h, from the fetch | space weather, trip radiation |
| NOAA NOMADS | GEFS 24/48 h, HRRR, GEFS at each designed opportunity (`gefs_launch/{region}`), GFS-Wave off Florida | 6–18 h | launch weather, return |
| NOAA GOES GLM | lightning flashes near the pad, only when an opportunity is < 6 h away | 10 min | launch weather |
| NWS | alerts and the gridded forecast at the pads | 3–6 h | launch weather |
| NDBC | buoy 41009 | 3 h | recorded only (shown at `/feeds`) |
| Launch Library 2 | upcoming launches at the Florida and Vandenberg ranges | 12 h | launch weather (other launches from the range that day) |
| NASA DSN Now | which dishes are tracking what | 15 min | recorded only (shown at `/feeds`) |
| NASA JPL Horizons | active lunar orbiter state vectors (LRO, KPLO, Capstone, THEMIS) | 7 d | contact (orbiter line of sight) |

Not recorded, with the reason: GEOS-FP (host unreachable from here), ECMWF ENS/AIFS
(whole-globe fields, too heavy for a routine fetch), NGA's NAVAREA IV warnings (the
API returns an error page from this network).
