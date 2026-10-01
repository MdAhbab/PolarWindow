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
  Browser download remains pending because no browser is connected.
- [SPENVIS registration](https://www.spenvis.oma.be/registration.php) rejects
  Gmail and similar addresses. An affiliation email, title, city, organisation,
  organisation URL and country are required. Registration is pending those
  details and browser access; a SPENVIS validation run has not been performed.
- [Copernicus Marine registration instructions](https://help.marine.copernicus.eu/en/articles/4220332-how-to-register-for-copernicus-marine-service):
  registration and data access are free. An existing Copernicus Data Space
  account can also sign in. Registration, email verification and password
  setup remain pending browser access and the user's verification steps.

Account passwords, tokens and verification links belong in private local
configuration, never in the repository.
