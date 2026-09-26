"""Typed application settings. Every environment variable this service reads
appears here exactly once, with a type and a default.

Nothing else in the codebase calls ``os.environ``. That rule is what makes
``.env.example`` trustworthy and what makes a misconfiguration a startup error
with a field name rather than a ``KeyError`` three layers down at request time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

#: Bumped whenever a change to core/ alters the numbers. Stamped onto every
#: precomputed row and every cache key, and reported in `meta`, so stale
#: geometry can never be served as current -- it becomes a visible mismatch
#: rather than a silent wrong answer.
#:
#: hz-2: projection scale factor in the site frame; per-tier DEM error.
#: vis-2: hourly-knot ephemeris interpolation; window-edge (open) flags;
#:        survival sized on the longest night; adjacent-run coalescing.
ENGINE_VERSION = "hz-2/vis-2"

#: One version per engine (ADR-13). The surface engine keeps ``ENGINE_VERSION``
#: above so its cache keys, stored masks and goldens are untouched; every
#: lifecycle answer instead names the engines it depends on (its *closure*), so
#: a change to the trip propagator invalidates trip and contact answers and
#: nothing else.
#:
#: traj: trip propagator and transfer design     ecl: shadow along the trip
#: wx:   launch and recovery weather rules       rad: radiation screening
#: link: link budget                              net: contact graph and routing
#: los:  rover-to-lander line of sight
ENGINES: dict[str, str] = {
    "hz": "hz-2",
    "vis": "vis-2",
    "traj": "traj-1",
    "ecl": "ecl-1",
    "wx": "wx-1",
    "rad": "rad-1",
    "link": "link-1",
    "net": "net-1",
    "los": "los-1",
}


def engine_closure(*names: str) -> str:
    """The versions an answer depends on, in a stable order: ``"traj-1+vis-2"``."""
    unknown = [n for n in names if n not in ENGINES]
    if unknown:
        raise KeyError(f"unknown engine(s) {unknown}; known: {sorted(ENGINES)}")
    return "+".join(ENGINES[n] for n in sorted(set(names)))


_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_prefix="PW_",
        extra="ignore",
        frozen=True,
    )

    # --- service -----------------------------------------------------------
    env: Literal["dev", "test", "prod"] = "dev"
    #: Demo mode with the network assumed gone: the model is never called
    #: (agents answer from measurements), kernel and DEM downloads are refused
    #: with a loud error, and responses say `meta.source = "offline"`. Accepts
    #: the bare `OFFLINE=1` the build guide uses as well as `PW_OFFLINE`.
    offline: bool = Field(default=False, validation_alias=AliasChoices("PW_OFFLINE", "OFFLINE"))
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    #: Origins allowed to call the API. The Vite dev server's two spellings are
    #: both here because "works in curl, fails in the browser" is the single
    #: most common wasted hour in a hackathon.
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    )

    # --- data on disk ------------------------------------------------------
    data_dir: Path = _REPO_ROOT / "data"

    @property
    def kernel_dir(self) -> Path:
        return self.data_dir / "kernels"

    @property
    def dem_dir(self) -> Path:
        return self.data_dir / "dem"

    @property
    def regional_dem_path(self) -> Path:
        return self.dem_dir / "regional_80m.npz"

    @property
    def tile_dir(self) -> Path:
        return self.data_dir / "tiles"

    @property
    def sites_seed_path(self) -> Path:
        return self.data_dir / "sites.json"

    @property
    def missions_path(self) -> Path:
        return self.data_dir / "missions.json"

    def fine_dem_path(self, site_id: str) -> Path:
        return self.dem_dir / "fine" / f"{site_id}.npz"

    #: Download kernels at startup if missing. Off by default: a container that
    #: silently pulls 114 MB at boot turns a fast, obvious failure into a slow
    #: mystery. The seed step downloads them; the API only checks.
    download_kernels_on_start: bool = False

    # --- stores ------------------------------------------------------------
    #: Defaults match docker-compose and `.env.example`. A machine with its own
    #: Postgres or Redis overrides them in `.env`, never by editing this file.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/polar_window"
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True

    # --- compute -----------------------------------------------------------
    #: Default timeline sampling step. 900 s over a 708 h window is 2,835
    #: samples, matching the frontend's TRACK_STEP_H = 0.25 exactly so the two
    #: implementations can be diffed sample-for-sample. See ADR-1.
    default_step_s: int = 900
    min_step_s: int = 300
    max_step_s: int = 7200

    #: Longest window the API will compute in one request. Two years keeps a
    #: pathological request from occupying the SPICE thread for a minute.
    max_window_days: int = 730

    #: Mask resolution. 0.25 deg = 1440 rays; see ADR-1 for the justification.
    azimuth_step_deg: float = 0.25
    max_range_m: float = 50_000.0
    fine_dem_radius_m: float = 20_000.0

    #: The window that `/sites` summaries and coarse filters are computed over.
    #: Stated in every response that uses it, because a filter answered against
    #: a different window than the one on screen is a lie of omission.
    reference_window_start: datetime = datetime(2027, 3, 14, tzinfo=UTC)
    reference_window_days: float = 29.53

    # --- cache -------------------------------------------------------------
    #: Computed windows kept in-process, so the three payloads for one window
    #: share one geometry run. ~0.3 MB each; see site_service._Memo.
    geometry_memo_entries: int = 32
    cache_ttl_timeline_s: int = 3600
    cache_ttl_windows_s: int = 86_400
    cache_ttl_metrics_s: int = 86_400
    #: How long a single-flight loser waits for the winner before computing it
    #: itself. Longer than a cold compute, shorter than a user's patience.
    singleflight_wait_s: float = 5.0

    # --- sign-in -----------------------------------------------------------
    #: Signs session tokens (HS256). Empty means a random secret per process:
    #: tokens then stop working when the API restarts, and the dashboard signs
    #: in again on its own. Set it anywhere more than one process serves.
    jwt_secret: str = ""
    jwt_ttl_s: int = 12 * 3600
    #: The one-click sign-in the landing page uses: a project manager's token
    #: with no user name or password. Right for a judged demo, wrong anywhere
    #: real, so it can be turned off.
    demo_sign_in: bool = True

    # --- agents ------------------------------------------------------------
    gemini_api_key: str = ""
    #: Models to try, in order. A run moves to the next one when a model is
    #: over its quota (429), not served to this key (403, 404) or down (5xx),
    #: and a model that failed is skipped until its quota resets. Nothing older
    #: than Gemini 2.5. The Flash models come first for tool use and structured
    #: answers; the Flash-Lite models, with far larger daily quotas on the free
    #: tier, keep the agents answering once those run out. Override with a
    #: comma-separated PW_AGENT_MODELS.
    agent_models: Annotated[tuple[str, ...], NoDecode] = (
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
    )
    #: The same, lightest first: the Explainer writes one paragraph from facts
    #: it is handed, with no search, so a Flash-Lite model is enough.
    agent_models_light: Annotated[tuple[str, ...], NoDecode] = (
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-2.5-flash",
    )
    agent_timeout_s: float = 20.0
    agent_max_rounds: int = 4
    agent_max_tool_calls: int = 8
    agent_max_output_tokens: int = 2048
    #: None leaves the model's default. Gemini 3 is tuned for its default
    #: temperature, and lowering it is documented to cause looping.
    agent_temperature: float | None = None

    @property
    def agents_enabled(self) -> bool:
        """Agents degrade to deterministic summaries without a key.

        Deliberately not a startup error: the four key numbers are the product,
        and they must work on a laptop with no API key at all.
        """
        return bool(self.gemini_api_key) and not self.offline

    @property
    def agent_model(self) -> str:
        """The first choice, for the `meta` of responses that ran no model."""
        return self.agent_models[0]

    @field_validator("cors_origins", "agent_models", "agent_models_light", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return tuple(s.strip() for s in v.split(",") if s.strip())
        return v

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand(cls, v: object) -> object:
        return Path(str(v)).expanduser().resolve() if v else v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
