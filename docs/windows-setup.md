# Native Windows setup

Run the frontend, API, compute workers and feeds worker from PowerShell:

```powershell
Set-Location F:\Projects\NASA\PolarWindow
python run.py --skip-install
```

Omit `--skip-install` when installing or updating dependencies. The backend uses
Python 3.12 through uv even if the Python launching the runner is another version.
Open http://localhost:5173 and choose **Open dashboard**. The API documentation
is at http://localhost:8000/api/v1/docs. Ctrl+C stops the application workers and
frontend; PostgreSQL and the cache remain available for the next run.

## Requirements

- Python and uv on PATH. uv installs the project's Python 3.12 in `.local/python/`.
- Node.js and npm. This checkout's frontend test dependencies require Node 22.22.2
  or newer within the Node 22 release line, or a supported newer major version.
- PostgreSQL 16. Portable binaries in `.local/tools/pgsql/bin/` are discovered
  automatically; database files are created in `.local/pgdata/`.
- Redis or Memurai for caching, or `PW_REDIS_ENABLED=false` to run without caching.
- Internet access for the first dataset download and live data providers.

The local setup on this machine uses PostgreSQL on port 5432 and a separate
Memurai cache on port 6380, configured in the ignored `.env`. The cache disables
disk persistence and writes its log in `.local/redis/`.

## Storage and datasets

The runner keeps temporary files and Python/npm/science-library caches in
`.local/`. Frontend packages live in `frontend/node_modules/`, backend packages
in `backend/.venv/`, and NASA datasets in `data/`. Keep the checkout on the drive
where these files should be stored. The runner uses existing executable programs
on PATH; it does not relocate system installations.

The default data sync downloads core, lifecycle and validation datasets and builds
the landing sites' terrain masks and measurements. The first setup takes longer
than later runs. These are required for live calculations; the recorded frontend
snapshot is a separate preview option.

Large bulk archives are optional and are not downloaded by default. The compact
climatology and validation results already in the repository let you explore the
app without fetching those archives.

No API key is required for the core calculations. A Gemini key enables model-backed
assistants; without it, deterministic summaries remain available. A NASA API key
raises DONKI rate limits above `DEMO_KEY`. An Earthdata token is only needed for
protected bulk archives. Keep keys in `.env`, which Git ignores.

The frontend labels saved snapshots, missing inputs and stale or failing feeds.
Even with local services running, an external provider may be unavailable.

## Reusing a teammate's downloaded data

On a machine with the datasets:

```powershell
python run.py --export-data F:\polar-window-data.zip
```

On this machine:

```powershell
python run.py --skip-install --data-from F:\polar-window-data.zip
```

The importer verifies the archive and the normal sync fetches anything still missing.
