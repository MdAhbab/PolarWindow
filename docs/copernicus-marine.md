# Copernicus Marine wave subset

The Return section can read a user-downloaded regional NetCDF subset from
[Global Ocean Waves Analysis and Forecast](https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_WAV_001_027).
This supplies significant wave height at the next designed droneship zone and
time. NOAA still supplies wind. A wave estimate alone does not establish a
launch provider's recovery limits or demonstrate forecast skill.

On 1 October 2026 the corrected local subset was imported and checked with
the actual downloaded data: nine time steps, 85 latitude rows and 121 longitude
columns spanning 28–35° N, 80–70° W and 1–2 October UTC. Its significant wave
height is 0.80 m at 30° N, 75° W on 1 October 12:00 UTC and 0.97 m at 32° N,
74° W. The Return quantity preserves the source and valid time. A query outside
the region is rejected. Source SHA-256:
`fa8d29501610fca57a63aa2e6ea3f6ce591bd370595bad77700fa0dafc23b12f`.
The earlier download containing only `VHM0_WW` remains unused.

## Download and import

1. Sign in to the Marine Data Store and open the product's **Download** form.
2. Choose the **3-hourly** dataset `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`.
3. **Clear all** variables, then select **Sea surface wave significant height —
   VHM0 [m]**. `VHM0_WW` is only the wind-wave component and cannot substitute
   for total significant wave height.
4. For the Florida test subset set **N 35, S 28, W -80, E -70** and **1 October
   2026 00:00** through **2 October 2026 00:00**. These are the dataset's UTC
   valid times. Future opportunities need their own covering time range.
5. Save the original `.nc` under `data/copernicus/`. Keep the original filename.
6. From `backend/`, install the optional decoder and import the file:

```powershell
uv sync --extra dev --extra marine
.\.venv\Scripts\python.exe -m app.feeds.import_copernicus ..\data\copernicus\your-file.nc
```

The importer checks the exact variable, units, dimensions and coordinate/time
axes, decodes NetCDF packing and missing values, preserves source metadata and
SHA-256, and atomically writes `data/copernicus/waves.json`. It rejects subsets
over two million cells. Raw files and normalized data are ignored by Git; no
password or access token is needed by the importer or application.

## Selection limits

The application uses the nearest available three-hour step within 90 minutes
and nearest grid cell within 20 km. The requested zone must lie inside the
downloaded bounds. Land/missing cells, dates outside the subset, and imports
older than 24 hours are rejected; NOAA remains the fallback. No download is
scheduled automatically: acquire a new subset when new coverage is needed.

The source's valid time and local import time are retained separately. The
subset creation timestamp does not prove the forecast's issuance time, so the
answer explicitly leaves issuance unknown. Imports do not create observations
or independent forecast validation.
