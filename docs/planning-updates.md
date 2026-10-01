# Planning updates — 1 October 2026

Launch wind evidence now follows the lead and limit that were actually tested.
GEFS checks apply only within three hours of the scored 24/48-hour leads, and
changing the threshold cannot borrow the published threshold's verification.
The selected forecast step's lead is used, rather than the time from now to
launch: an older forecast may have a different lead for the same valid time.
HRRR reports the selected lead's event/hit/false-alarm counts, rather than
pooling all leads, and refuses to extrapolate validation beyond its recorded
1–18-hour range. The station observations are at 10 m: the rule-height wind
is still inferred, and the answer states that limitation. This changes the
interpretation of the existing hindcasts, not their measured scores.

Rover sight uses native terrain, in this order when a complete neighbourhood
fits: LROC NOBILE04 stereo (3 m), NOBILE03 (4 m), LOLA LDEM_875S_5M (5 m), the site's existing
20 m LOLA window, and the regional 80 m model. The lander's ground must also be
known. A stereo gap remains unknown;
it is never filled with fabricated height. The 3 m product's height-error
allowance is 4.43 m, the conservative sum of its reported 2.72 m precision
and 1.71 m registration RMS. NOBILE03 uses 4.12 m (3.70 m precision plus
0.42 m registration RMS); 5 m LOLA keeps the existing assumed 2 m error.
Finer horizontal spacing does not promise better vertical accuracy.

The API's job key includes the chosen terrain file and its SHA-256. A download
therefore creates a new answer instead of reusing the coarser answer, and the
terrain map uses the same file as the sight calculation. Downloads publish
only complete files; incomplete downloads are excluded from data exports.
The small NOBILE03 footprint is retained as measured, without padding it.

Fetch missing terrain with `python -m app.data.rover_terrain` from `backend/`,
or use `polar-data sync --tier lifecycle`. The normal runner includes this
step after the site seed. Large rasters stay in ignored `data/dem/`; source
definitions, download code and validation travel with the branch. Use
`polar-data export` to share the downloaded files themselves.

Local coverage checked on 1 October: seven native 5 m windows were fetched.
The NOBILE04 crops at both IM-2 and Griffin-1 contain nodata at the lander's
ground. NOBILE03 has known ground at IM-2 and supports the 500 m/1 km
neighbourhoods with native 4 m posts; 2 km/5 km requests correctly fall back
to 20 m because its footprint is too small. Griffin-1 still uses 20 m.
NOBILE01 was also
sampled at these points and has the same limitation; its narrow footprint
does not cover a 6 km neighbourhood at Griffin-1. The finer-terrain support
is implemented; finer usable ground at Griffin-1 remains a data gap.

Validation against a separately written metre-by-metre ray test achieved
100% agreement outside the uncertainty band at IM-2 (20 m at 2 km),
Griffin-1 (20 m at 500 m/2 km), and Shackleton rim (native 5 m at 500 m/2 km).
At IM-2's native 4 m/500 m neighbourhood every cell remains uncertain with
the conservative 4.12 m height error, so no outside-band agreement score can
be claimed there. Finer horizontal spacing alone does not guarantee a more
confident sight decision. This checks
the sight algorithm, not the terrain against independent measurements.

Pad-limit launch windows must have two converged endpoint designs with valid
coasts (the nominal lower bound through 120 minutes), 3.5–6.5-day flights,
and a span shorter than half a day containing the nominal instant. A failed
endpoint produces a nominal instant with an explicit unresolved-window reason.
The lunar arrival inclination stays independent of the climb heading. A pad's
range does not prove vehicle payload capacity or steering capability: planned
windows still require evidence of published windows on direct lunar flights.

Lifecycle engines advance to `wx-3`, `los-3`, and `lw-7` so stored answers do
not retain the old interpretation.

## Sources and external account work

- [Native LROC NOBILE04 terrain and published error figures](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_NOBILE04).
- [Native LROC NOBILE03 terrain and published error figures](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_NOBILE03).
- [LOLA 5 m product label](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_875s_5m.lbl).
- [ESA Lunar Pathfinder / Moonlight slides](https://spacefinland.fi/documents/60305973/0/ESA%2B-%2BMoonlight_LP_and_LCNS_Slides%2B%281%29.pdf/d5399da8-26d6-016b-2cda-703c8ac70f16?t=1695736353872):
  page 1 was inspected with the document reader. It gives 673.4/7331.8 km
  perilune/apolune altitudes, 46.8° inclination and a rounded 10-hour period.
  Its 2025 launch schedule is historical, not a current launch forecast.
  Browser download completed on 1 October. The unchanged three-page PDF is
  saved locally as `data/validation/external-sources/esa-moonlight-lunar-pathfinder.pdf`
  (802,079 bytes; SHA-256
  `01358401e32fc50695b43a26636178cb29de8dbce153bf69e71ea12ed97b8691`).
  Page 1 was extracted and rendered for visual verification. The inclination
  disagreement with the supplier paper is still unresolved; downloading the
  source does not remove that uncertainty. The earlier HTTP 403 attempt did
  not save a file; the later browser download did.
- [SPENVIS registration](https://www.spenvis.oma.be/registration.php) rejects
  Gmail and similar addresses. An affiliation email, title, city, organisation,
  organisation URL and country are required. The user has now supplied a
  university affiliation email. The user supplied screenshots confirming a
  successful password change and an authenticated `POLARWIND` project on
  the Model packages page. Advanced-user access was enabled and the user
  uploaded the IM-2 trajectory and ran AP-8 MAX/AE-8 MAX. Both downloaded raw
  spectra now pass the 5% comparison with `rad-5` (+2.56% proton, +1.09% electron).
  Only this passage has been checked in SPENVIS. After the user reported
  allowing the site, the browser tool still rejected reading the page because
  of its saved blocked-site preference. Continuing UI work requires clearing
  that exact site block. Private account setup details stay in ignored
  `.local/account-setup.json`.
- [Copernicus Marine registration instructions](https://help.marine.copernicus.eu/en/articles/4220332-how-to-register-for-copernicus-marine-service):
  registration and data access are free. Registration details were prepared
  in the browser; the user approved the privacy policy and terms, and the
  registration reached email verification. The user completed the account
  update; the connected browser subsequently showed a signed-in account on
  the data store. A `VHM0` wave subset was requested through the official
  global-wave download form for 28–35° N, 80–70° W, 1–2 October 2026.
  The first request reported download completion, but no local NetCDF file
  was verified and a later download-event wait timed out. Browser access
  review then denied the Copernicus request. Account access was confirmed;
  manual download is needed while that origin remains blocked. The local
  NetCDF importer and Return integration are implemented. A first verified
  download contained `VHM0_WW` rather than total `VHM0` and was correctly
  rejected. The corrected `VHM0` subset was subsequently downloaded and
  imported successfully: nine 3-hour steps, 85 latitude rows and 121 longitude
  columns, 1–2 October 2026 UTC. At 30° N, 75° W on 1 October 12:00 UTC it
  gives 0.80 m, and Return's quantity includes the Copernicus source and valid
  time. Queries outside coverage are rejected. The original file's SHA-256 is
  `fa8d29501610fca57a63aa2e6ea3f6ce591bd370595bad77700fa0dafc23b12f`.
  NOAA GFS-Wave remains the fallback and wind source. See
  [import instructions and coverage limits](copernicus-marine.md).

## Native radiation execution and SPENVIS preparation

The earlier loader looked only for `libirbem.so`, so the installed Windows
SpacePy wheel was reported unavailable. It now checks the platform's bundled
library names (including the Windows wheel's `libirbem.dll.a`) and loads its
bundled Fortran runtime without importing SpacePy or modifying the system PATH.
Load failures remain a declared unavailable input rather than an uncaught DLL
exception. The engine advances to `rad-4` to recompute cached unavailable results.

The radiation validation runner was executed on native Windows on 1 October.
After comparing the user's downloaded SPENVIS spectra, engine `rad-5` adds
the published 0.3°/year SAA longitudinal drift compensation. This resolves the
IM-2 implementation comparison within the 5% gate. It is not fitted to the
reference output, and the factor-of-two model uncertainty remains. Corrected
magnetic shells agree to rounding with NASA SPDF's AE8/AP8 implementation;
flight-date IGRF shells remain a different configuration (IM-2 proton −22.7%).
Updated tables and primary references are in `validation.md`.

From `backend/`, run `python -m app.validation.export_spenvis` to prepare inputs
in ignored `data/validation/spenvis/`. The command exports reconstructed belt
passages for IM-2, Blue Ghost 1 and Peregrine; IM-1 has no reconstructed belt
coverage. Each continuous passage is a separate UTC/Earth-fixed Cartesian-km
upload, accompanied by its duration, source/file hashes, solar phase, sampled
engine flux and integrated fluence. No missing trajectory gap is integrated.
The exporter manifest says `prepared_not_run` because export does not execute
SPENVIS. The separate downloaded-output comparison records
`passed_for_this_passage` for IM-2.

SPENVIS trajectory uploads require Advanced-user status (editable in My Account).
For a comparison, use AE8/AP8 integral omnidirectional electrons above 1 MeV
and protons above 10 MeV, the manifest's solar phase, the exact passage duration,
and recorded field/B0 settings. Keep the original model report and raw outputs;
only then compare integrated fluences with the 5% implementation-comparison gate.
Preparing these files or agreeing with SPDF does not satisfy that gate.

The unchanged downloaded PDF, generated trajectories, and account screenshots
stay in ignored local data; reproducible export code and source/status notes are
tracked in Git. Passwords and tokens are not included in the export.

Account passwords, tokens and verification links belong in private local
configuration, never in the repository.

## Verification of the radiation and Marine changes

On native Windows, 41 targeted unit/integration tests passed, including the
actual IM-2 SPENVIS regression, packed NetCDF/missing-cell decoding, import
rejection guards, and the Trip and Return API checks. Ruff and targeted mypy
checks passed; all ten import-boundary contracts were kept and the dependency
lock was consistent. The actual corrected Copernicus download was separately
decoded and checked through Return's wave quantity builder. The restarted app's
API and frontend responded successfully. Griffin-1's next designed opportunity
is 13 October, outside the imported 1–2 October subset, so it correctly retains
NOAA wave evidence. Live provider failures remain visible in health status.
