# Manual SPENVIS comparison

The account is signed in and the user's screenshot shows the `POLARWIND`
project. No SPENVIS radiation result has been acquired yet. These steps use
the prepared files in `data/validation/spenvis/`; the files are local and ignored
by Git. Regenerate them from `backend/` with `python -m app.validation.export_spenvis`.

## First run: IM-2

1. From **Model packages**, choose **Spacecraft trajectories**. Find the
   user-defined trajectory upload option. If it is unavailable, inspect
   **My account** for Advanced-user status. Do not create an unrelated orbit
   from guessed orbital elements.
2. Upload `data/validation/spenvis/im-2-passage-01.csv`. It contains 437 samples
   in UTC and Earth-fixed **GEO** Cartesian coordinates, in kilometres. The
   `-engine.csv` file is our comparison output, not a trajectory upload.
3. Confirm the displayed dates: **2025-02-27 01:00:08.518 UTC** through
   **2025-02-27 08:16:08.518 UTC**. The duration is **26,160 seconds**,
   **436 minutes**, **7 h 16 min**, or **0.3027777777777778 days**. Use the
   units shown by the form; do not leave a default one-year mission length.
4. Execute the trajectory step using the site's own navigation. Return to
   Model packages, expand **Radiation sources and effects**, and find the
   trapped-radiation model. Choose **AE8 MAX** and **AP8 MAX** and integral
   omnidirectional flux: electrons above **1 MeV**, protons above **10 MeV**.
5. Record the magnetic-field and B0 settings in the run report. Our IRBEM
   map calculation uses Jensen and Cain 1960 for AE8 MAX, GSFC 12/66 updated
   to 1970 for AP8 MAX, and McIlwain's moment for B0. A run using the
   flight-date IGRF field is a different field comparison. Do not change
   settings blindly if the page exposes different options.
6. Run the models and save the original report plus numerical flux/fluence
   outputs under `data/validation/spenvis/results/im-2/`. Keep the input file,
   dates, model choices, units and any warnings with the outputs. A plot or
   screenshot alone is insufficient for the numerical comparison.

Our reference integrated fluences for this passage are **1.0943897119728935e10
electrons/cm²** above 1 MeV and **8.554402166990067e5 protons/cm²** above 10 MeV.
These are engine predictions, not measured values or SPENVIS results. Compare
like-for-like settings and quantities; the implementation gate is a 5% relative
difference. If only sampled flux is exported, integrate it over the actual
sample times rather than comparing flux with fluence.

## Remaining passages

Each passage must be run independently. Do not integrate across missing
trajectory intervals. All prepared passages use solar-maximum maps.

| Trajectory file | Samples | Duration (seconds) | Duration (days) |
| --- | ---: | ---: | ---: |
| `blue-ghost-m1-passage-01.csv` | 429 | 25680 | 0.2972222222222222 |
| `blue-ghost-m1-passage-02.csv` | 974 | 58380 | 0.6756944444444445 |
| `blue-ghost-m1-passage-03.csv` | 958 | 57420 | 0.6645833333333333 |
| `blue-ghost-m1-passage-04.csv` | 950 | 56940 | 0.6590277777777778 |
| `im-2-passage-01.csv` | 437 | 26160 | 0.3027777777777778 |
| `peregrine-m1-passage-01.csv` | 437 | 26160 | 0.3027777777777778 |
| `peregrine-m1-passage-02.csv` | 430 | 25740 | 0.2979166666666667 |

Use `manifest.json` as the authoritative list of dates, durations, source
hashes and reference fluences.
IM-1's available reconstruction has no belt coverage and cannot supply this
validation run. Prepared inputs do not constitute a passed validation.

References already used to prepare the exporter:
[SPENVIS upload format](https://www.spenvis.oma.be/help/models/sapre_upl.html)
and [existing radiation comparison](validation.md).
