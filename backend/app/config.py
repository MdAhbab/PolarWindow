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
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Bumped whenever a change to core/ alters the numbers. Stamped onto every
#: precomputed row and every cache key, and reported in `meta`, so stale
#: geometry can never be served as current -- it becomes a visible mismatch
#: rather than a silent wrong answer.
ENGINE_VERSION = "hz-1/vis-1"

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
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    #: Origins allowed to call the API. The Vite dev server's two spellings are
    #: both here because "works in curl, fails in the browser" is the single
    #: most common wasted hour in a hackathon.
    #: Vite picks the next free port when 5173 is taken, so both are listed --
    #: "works in curl, fails in the browser" is the single most common wasted
    #: hour in a hackathon, and it is always this.
    cors_origins: tuple[str, ...] = (
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

    def fine_dem_path(self, site_id: str) -> Path:
        return self.dem_dir / "fine" / f"{site_id}.npz"

    #: Download kernels at startup if missing. Off by default: a container that
    #: silently pulls 114 MB at boot turns a fast, obvious failure into a slow
    #: mystery. The seed step downloads them; the API only checks.
    download_kernels_on_start: bool = False

    # --- stores ------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://postgres@/polar_window?host=/tmp&port=5433"
    redis_url: str = "redis://localhost:6380/0"
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
    cache_ttl_timeline_s: int = 3600
    cache_ttl_windows_s: int = 86_400
    cache_ttl_metrics_s: int = 86_400
    #: How long a single-flight loser waits for the winner before computing it
    #: itself. Longer than a cold compute, shorter than a user's patience.
    singleflight_wait_s: float = 5.0

    # --- agents ------------------------------------------------------------
    gemini_api_key: str = ""
    agent_model: str = "gemini-3.8-flash"
    agent_model_light: str = "gemini-3.5-flash-lite"
    agent_timeout_s: float = 20.0
    agent_max_rounds: int = 4
    agent_max_tool_calls: int = 8
    agent_max_output_tokens: int = 2048

    @property
    def agents_enabled(self) -> bool:
        """Agents degrade to deterministic summaries without a key.

        Deliberately not a startup error: the four key numbers are the product,
        and they must work on a laptop with no API key at all.
        """
        return bool(self.gemini_api_key)

    @field_validator("cors_origins", mode="before")
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
