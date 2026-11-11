# External reference data

Public datasets fetched on 2026-11-10 and 2026-11-11. Two folders are read by the app (see *State*
below); the rest are for features that are planned but not built yet. The files are not in git (see `.gitignore`);
this page is the record of what is here and where it came from. When a feature starts
using one of these, move its entry into the data registry (`backend/app/data/registry.py`)
so `polar-data sync` fetches it like the rest.

| Folder | What it is | Source | Size | Intended use |
|---|---|---|---|---|
| `pgda_illumination/` | Average sunlight (`AVGVISIB_*`), average Earth visibility (`*_EARTH`), permanent shadow (`LPSR_*`) and sky visibility (`SKYV_*`) for the south pole at 60 m (85–90°S), 120 m (75–90°S) and 240 m (65–90°S). GeoTIFF. | NASA GSFC PGDA product 69, <https://pgda.gsfc.nasa.gov/products/69>. Cite Mazarico et al. (2011), Icarus. | ~270 MB | Independent check on the sunlight and Earth-contact hours the app computes. |
| `pgda_lola_5m/` | 5 m terrain for nine south-pole sites (01, 04, 06, 07, 11, 20, 20v2, 23, 42): elevation (`surf`), slope (`slp`), elevation uncertainty (`toterr`), plus region outlines for five of them. | NASA GSFC PGDA product 78, <https://pgda.gsfc.nasa.gov/products/78>. Cite Barker et al. (2021), PSS 203, 105119. | ~1.6 GB | Sharper skylines and slope at priority sites. The per-site error clones and point clouds were not fetched. |
| `diviner_prp/` | Diviner Polar Resource Product, south: annual average and maximum surface temperature and depth to stable water ice, on a triangular mesh. | PDS Geosciences, `lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/`. Cite Paige et al. (2010), Science. | 605 MB | Temperature and ice context on the Surface step. The north file was not fetched. |
| `clps_lister/` | LISTER heat-flow probe data from Blue Ghost Mission 1 (regolith temperature and thermal conductivity to 1 m), with its documents. | PDS Geosciences, <https://pds-geosciences.wustl.edu/missions/clps/to19d_lister.htm>, DOI 10.17189/tyf3-jm93. | 4 MB | Link a flown mission to what it returned. |
| `clps_lra/` | Laser Retroreflector Array archive for IM-1 and IM-2. | PDS Geosciences, `clps/urn-nasa-pds-lra/`. | 1.5 MB | As above. |
| `periodic_orbits/` | Earth–Moon periodic orbit families: halo (L1, L2, north and south), distant retrograde, butterfly, Lyapunov (L1, L2). JSON as returned. | JPL Three-Body Periodic Orbits API, <https://ssd-api.jpl.nasa.gov/doc/periodic_orbits.html>. | 9 MB | Real relay-orbit options for scenarios. |
| `usaspending_clps/` | NASA contract awards whose description matches "Commercial Lunar Payload Services": recipient, amount, dates. | USAspending API, <https://api.usaspending.gov>. | small | Contract value beside a mission. A keyword match: check each row before quoting it. |
| `nasa_images/` | Image records (title, date, credit, preview link) per mission. Metadata only, no image files. | NASA Image and Video Library API, <https://images.nasa.gov>. | small | Imagery on mission cards. Text-search matches, not curated: some rows show a different mission. |
| `cgi_moon_kit/` | Colour maps (1k, 2k, 4k) and height maps of the whole Moon. | NASA SVS CGI Moon Kit, <https://svs.gsfc.nasa.gov/4720>. | 54 MB | Texture and relief for the 3D Moon. |
| `robbins_craters/` | Lunar crater database, about 1.3 million craters larger than 1–2 km (zip; the CSV inside is 238 MB). | USGS Astrogeology, <https://astrogeology.usgs.gov/search/map/moon_crater_database_v1_robbins>. Cite Robbins (2019), JGR Planets. | 96 MB | Crater context around a site. |
| `papers/` | Barker et al., improved LOLA elevation maps for south pole landing sites. | NASA NTRS 20205009660. | 10 MB | Method and error estimates behind `pgda_lola_5m/`. |
| `artemis3_regions/` | NASA abstract on the nine Artemis III candidate regions (2026). Names and reasoning only. | NASA NTRS 20250011660. | 0.6 MB | Context. No coordinates are published in it. |

## State on 2026-11-11

Everything in the table is on disk and complete (2.5 GB, no failed file):
`bash data/external/_tools/fetch_external.sh data/external` from the repository root fetches
the lot and skips what is already there.

Two folders are now read by the app. Their registry entries
(`backend/app/data/registry.py`) are still to be added, so `polar-data sync` does not fetch
them yet and the features say so when a file is missing:

- `diviner_prp/` gives the ground temperature to the power and temperature model
  (`POST /sites/{id}/energy`, ADR-21). Build its index once with
  `python -m app.data.diviner build` from `backend/`.
- `pgda_lola_5m/` and `pgda_illumination/` give slope and average sunlight to the landing
  ellipse (`POST /sites/{id}/dispersion`, ADR-22).

## Looked for and not fetched

- **Artemis III region coordinates.** NASA has published the nine names and a map image, not a coordinate table or outline file.
- **NASA LSP launch vehicle performance** (<https://elvperf.ksc.nasa.gov>). An interactive query form with no bulk file or API.
- **Peregrine payload archives** (NSS, NIRVSS) on PDS. Cruise-only data from a mission that did not land; left out as low value.
