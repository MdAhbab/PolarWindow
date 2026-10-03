# Validation audit — 1 October 2026

This audit distinguishes successful execution from a passed scientific
requirement. The branch has the wind, terrain, pad-limit launch, radiation
and Copernicus integrations. Independent evidence does not yet support
calling every project validation complete.

## Rover terrain and visibility

The metre-by-metre brute ray check passes for every classified case. The
stronger GDAL reference check does not pass overall: Griffin-1 at 500 m
agrees on 221/252 common-grid targets (87.70%, required 99%). Four other
covered cases exceed 99%; the square reference crop of IM-2's native 4 m
DEM contains nodata, so this reference case remains unresolved. Its separate
brute-ray check has no classified cells under the 4.12 m height error either.
This uses GDAL 3.9.3's public C API, with
matched pixel centres within the requested radius, lunar curvature and the
same local raster inputs.
Physical controls for flat ground, a wall and the lunar horizon pass.

Source hashes, uncertainty counts and native-sampler diagnostics are in
[the checked JSON](validation-evidence/2026-10-01-viewshed-gdal.json).
Run from `backend/`: `python -m app.validation.validate_viewshed_gdal`.
A failed or unresolved case deliberately gives exit code 1. It writes
rasters and a report under ignored `data/validation/viewshed-gdal/`.
Reproduction requires the source terrain assets, not only the Git checkout.

No finer complete Griffin-1 DEM was found in the downloaded stereo products.
The native source and uncertainty support are implemented; this coverage
gap and the GDAL discrepancy remain open.

## Launch timing and windows

The fresh launch runner gives reconstructed TLI-to-liftoff errors of +15 s
(IM-1), −11 s (Blue Ghost M1) and −4 s (IM-2). Direct-transfer designs using
each flight's measured climb azimuth miss liftoff by +0.2 min and approximately
0.0 min. Held-out climb directions miss by −15.8 min and +17.5 min, so the
10-minute predictive requirement is not met for both direct flights.

Designs at pad azimuth limits yield IM-1 −105.5/+300.0 min and IM-2
−163.3/+269.3 min relative to liftoff. These are geometric feasibility ranges,
not validated operational Falcon 9 windows. The published instantaneous
windows already cited in `validation.md` do not establish vehicle capability
throughout those intervals. Passing regression tests preserves these known
limitations; it does not close the scientific window requirement.

Run: `python -m app.validation.validate_launch`. Its structured stderr output
is saved in [the checked JSON](validation-evidence/2026-10-01-launch.json).

## Radiation and marine data

The actual downloaded IM-2 SPENVIS AP-8 MAX / AE-8 MAX spectra meet the 5%
comparison gate with rad-5: proton +2.56%, electron +1.09%.

Update, 3 October 2026: the four Blue Ghost and two Peregrine passages have
now been run by hand in SPENVIS and compared. Electrons pass on all six (+0.40%
to +1.27%). Protons pass on four (+1.97% to +4.50%) and **fail on two**: Blue
Ghost passage 2 at +5.75% and Peregrine passage 1 at +5.40%. So five of the
seven passages meet the gate and two do not.

The proton excess is the same on every passage and has one cause. IRBEM works
out the shell value L with the dipole moment of the map's own field, where
McIlwain's definition and SPENVIS use a fixed 31,165.3 nT. That puts the
engine's L about 0.4% low, which on the proton belt's outer slope reads about
5% more flux. Recomputing L with the fixed moment brings all six proton
differences inside ±1.5%. That is a diagnosis: rad-5 has not been changed, and
the two failures stand until the engine is. The table and the working are in
[the radiation validation](validation.md); the steps are in
[the manual validation instructions](spenvis-manual-validation.md).

The downloaded Copernicus VHM0 NetCDF has been decoded and integrated. It
covers 28–35°N, 80–70°W, 1–2 October 2026 UTC; the checked source and probes
are described in [the import instructions](copernicus-marine.md).
It cannot validate all future return windows or provide marine observations
outside that subset. The app retains its NOAA fallback there.

## Lunar Pathfinder sources

The official [SSTL Service Guide V004](https://www.sstl.co.uk/getmedia/9efe3cc5-6b5b-4fd1-bbd7-443bc2d21848/Lunar-Pathfinder-Service-Guide-V004.pdf),
page 22, publishes an indicative baseline inclination of 54.856°, RAAN of
0° and argument of pericenter of 86.322°. The document calls these subject
to change and does not specify the reference plane or epoch. The catalogue
now records these values and their provenance. The ESA slides' 46.8°
inclination remains conflicting, so existing sensitivity ranges are retained.
Downloading both documents does not resolve the operational orbit.

The unchanged PDF is stored locally at
`data/validation/external-sources/sstl-lunar-pathfinder-service-guide-v004.pdf`:
SHA-256 `9c8b1be07ac6af6e0a4bcf86af59c8f13ec9161e55681413b9a235843cd9ddddf`.

## Wind archive recheck

Raw forecast caches were absent from this checkout. The tracked historical
benchmark reports are preserved, and both scorers now refuse to replace a
report when no raw cache exists. Fresh NOAA archives and IEM station records
have been collected and scored into a separate validation directory.

Use `python -m app.validation.validate_weather hrrr --hours 1` or
`python -m app.validation.validate_weather gefs --hours 2` to fetch and score;
`--score-only` reuses cached raw evidence. These commands write
`data/validation/weather/{hrrr,gefs}/{florida,vandenberg}.json` and preserve
the normal `data/hindcast/` benchmark JSONs. An empty archive exits with a
clear error. Wind at the 49 m rule height remains inferred from 10 m
station observations using a neutral profile, not directly measured.

HRRR's complete requested sample is 1,826 runs (00/12 UTC every second day,
2021–2025). These are fresh scores, with IEM KXMR/KVBG observations and
2000–2019 station climatology; fewer valid matches result from unavailable
forecast or station records. Speed error skill is better than a monthly/hourly
typical-wind reference, but that does not prove threshold-event reliability.

| Station | Lead | Matched cases | Speed-error skill | Above-limit events | Brier skill |
|---|---:|---:|---:|---:|---:|
| KXMR | 1 h | 1744 | 26.4% | 3 | insufficient events |
| KXMR | 6 h | 1733 | 18.6% | 8 | insufficient events |
| KXMR | 12 h | 1746 | 14.8% | 5 | insufficient events |
| KXMR | 18 h | 1744 | 18.0% | 9 | insufficient events |
| KVBG | 1 h | 1728 | 42.4% | 30 | 0.163 |
| KVBG | 6 h | 1739 | 28.4% | 11 | 0.123 |
| KVBG | 12 h | 1749 | 30.8% | 33 | −0.013 |
| KVBG | 18 h | 1740 | 21.9% | 9 | insufficient events |

At least 10 above-limit events are required for a Brier skill claim. None of
the Florida leads and Vandenberg's 18 h lead satisfy that minimum. The complete
reports are saved as checked [Florida](validation-evidence/2026-10-01-hrrr-florida.json)
and [Vandenberg](validation-evidence/2026-10-01-hrrr-vandenberg.json) snapshots.

GEFS's complete requested sample is 2,435 days (every third day, 2000–2019),
with all five members at both leads and stations present. All planned HRRR
initializations also have all requested forecast values. Valid station matches
are fewer than cached forecasts: the scoring requires a usable observation
within 30 minutes. Florida's matched GEFS cases span 2006–2019; Vandenberg's
span 2000–2019. Download coverage is not an event-count denominator.

| Station | Lead | Matched cases | Above-limit events | Brier skill | CRPS skill |
|---|---:|---:|---:|---:|---:|
| KXMR | 24 h | 1473 | 1 | insufficient events | −97.5% |
| KXMR | 48 h | 1492 | 3 | insufficient events | −99.2% |
| KVBG | 24 h | 1582 | 96 | 0.273 | 31.3% |
| KVBG | 48 h | 1589 | 98 | 0.185 | 31.9% |

Both stations fail the unchanged GEFS gate. Florida has too few events for
a Brier skill claim and negative speed-distribution skill. Its pooled 20%
probability bin has 56 cases and no observed above-limit events. Vandenberg
exceeds the 0.1 Brier skill minimum at both leads, but its pooled calibration
fails the 0.1 tolerance: the 40% bin observes 58.3% (36 cases), and the 100%
bin observes 87.0% (46 cases). Overall skill is not calibrated probability.
The reports retain month-block 95% intervals and the five-member fair CRPS
diagnostic; no failed score is promoted to a stronger claim.

Checked GEFS snapshots: [Florida](validation-evidence/2026-10-01-gefs-florida.json)
and [Vandenberg](validation-evidence/2026-10-01-gefs-vandenberg.json).
[The input manifest](validation-evidence/2026-10-01-weather-inputs.json)
records SHA-256 hashes of the decoded forecast-point caches, original IEM
observation CSVs and score snapshots, plus planned/available sample counts.
Original GRIB byte ranges were decoded and discarded; reproduction downloads
them from the NOAA archives again. Large local data assets remain ignored by Git.

## Code checks

60 targeted tests pass: launch reconstruction/limits, weather evidence and
hindcast scoring, catalogue/relay parsing, terrain selection, viewshed
geometry, GDAL physical controls, and preservation of reports with an empty
archive. Ruff and mypy pass on the changed validation/forecast modules;
all 10 import-boundary contracts pass. GDAL reference exit code 1 is the
documented scientific failure, separate from these passing code tests.
