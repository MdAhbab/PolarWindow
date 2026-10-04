# Architecture Decision Records

Index of architecture decisions for POLAR WINDOW.

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](0001-precompute-vs-on-demand.md) | Precompute horizon masks; compute timelines on demand | Accepted (amended 2026-09-23) |
| [ADR-0002](0002-frontend-data-fetching.md) | TanStack Query for frontend data fetching | Accepted (amended 2026-09-23) |
| [ADR-0003](0003-agent-orchestration.md) | A single bounded function-calling loop, not a graph | Accepted (amended 2026-09-23) |
| [ADR-0004](0004-tile-serving.md) | Pre-render static PNG tiles at seed time; keep rio-tiler as the builder | Accepted (amended 2026-09-23) |
| [ADR-0005](0005-clps-mission-data.md) | CLPS mission data is a curated, cited file, ingested at seed time | Accepted |
| [ADR-0006](0006-mission-targets-as-sites.md) | Mission targets are sites with published coordinates; smooth-Moon horizon outside the polar DEM | Accepted (amended by ADR-19) |
| [ADR-0007](0007-project-manager-sign-in-and-settings.md) | One stakeholder, the project manager; one-click sign-in; admin tasks live in their Settings | Accepted (amended by ADR-17) |
| [ADR-0008](0008-live-feeds.md) | Live feeds are fetched by one process and kept as forecasts of record | Accepted |
| [ADR-0009](0009-uncertainty-envelope.md) | One number shape, and an uncertainty envelope for every kind of answer | Accepted |
| [ADR-0010](0010-catalogues-and-mission-schema-v2.md) | Cited catalogues, and mission schema v2 | Accepted |
| [ADR-0011](0011-trajectory-engine.md) | The trip engine is ours, checked against GMAT and flown missions | Accepted |
| [ADR-0012](0012-heavy-compute.md) | Heavy work runs as jobs in Postgres; every answer records what it used | Accepted |
| [ADR-0013](0013-engine-versions.md) | A version per engine | Accepted |
| [ADR-0014](0014-weather-rules.md) | Launch weather is a list of rules, each with its own evidence; never one number | Accepted (amended 2026-09-29) |
| [ADR-0015](0015-radiation-screening.md) | Radiation numbers are screening estimates, and say where to confirm them | Accepted |
| [ADR-0016](0016-communications.md) | Contact is geometry first; planned relays are ranges; DSN load is not modelled | Accepted (amended 2026-09-29) |
| [ADR-0017](0017-project-manager-data.md) | The project manager's records have a name on every change | Accepted (amends ADR-7) |
| [ADR-0018](0018-kernel-pinning.md) | Kernels and data files are dated and pinned | Accepted |
| [ADR-0019](0019-terrain-outside-the-pole.md) | Real terrain models for mission targets outside 80°S (LOLA 60S and SLDEM2015) | Accepted |
