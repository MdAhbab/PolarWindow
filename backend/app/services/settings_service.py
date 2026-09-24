"""The project manager's settings: the AI assistant, the run log, the cache.

Stored in ``app_settings`` so a change applies to every process and survives a
restart. Every change can be undone: the AI settings have a reset to the
configured defaults, and the two clears only remove records that are rebuilt
(cached results) or that exist to be read and thrown away (the run log).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.repositories.app_settings import AppSettingRepository
from app.db.repositories.missions import MissionRepository
from app.db.repositories.sites import SiteRepository
from app.services import cache, site_service

AI_KEY = "ai_assistant"


class BadSetting(ValueError):
    """A settings change the service will not store, with the reason in words."""


@dataclass(frozen=True, slots=True)
class AiSettings:
    enabled: bool
    models: tuple[str, ...]
    models_light: tuple[str, ...]
    #: False while nothing is stored and the configured defaults apply.
    customised: bool


def _defaults() -> AiSettings:
    s = get_settings()
    return AiSettings(True, s.agent_models, s.agent_models_light, customised=False)


def _chain(stored: object, allowed: tuple[str, ...]) -> tuple[str, ...]:
    """A stored chain, keeping only models still configured, in the stored order."""
    if not isinstance(stored, list):
        return allowed
    kept = tuple(m for m in stored if isinstance(m, str) and m in allowed)
    return kept or allowed


async def ai_settings(session: AsyncSession) -> AiSettings:
    stored = await AppSettingRepository(session).get(AI_KEY)
    if not stored:
        return _defaults()
    s = get_settings()
    return AiSettings(
        enabled=bool(stored.get("enabled", True)),
        models=_chain(stored.get("models"), s.agent_models),
        models_light=_chain(stored.get("models_light"), s.agent_models_light),
        customised=True,
    )


def _check_chain(name: str, chain: list[str], allowed: tuple[str, ...]) -> tuple[str, ...]:
    if not chain:
        raise BadSetting(f"Keep at least one model in {name}.")
    unknown = [m for m in chain if m not in allowed]
    if unknown:
        raise BadSetting(
            f"{', '.join(unknown)} is not one of the configured models. "
            "Models are added in the server's environment settings, then ordered here."
        )
    if len(set(chain)) != len(chain):
        raise BadSetting(f"A model appears twice in {name}.")
    return tuple(chain)


async def save_ai_settings(
    session: AsyncSession, enabled: bool, models: list[str], models_light: list[str], by: str
) -> AiSettings:
    s = get_settings()
    chain = _check_chain("the main list", models, s.agent_models)
    light = _check_chain("the list for short explanations", models_light, s.agent_models_light)
    await AppSettingRepository(session).put(
        AI_KEY, {"enabled": enabled, "models": list(chain), "models_light": list(light)}, by
    )
    return AiSettings(enabled, chain, light, customised=True)


async def reset_ai_settings(session: AsyncSession) -> AiSettings:
    await AppSettingRepository(session).remove(AI_KEY)
    return _defaults()


async def clear_run_log(session: AsyncSession) -> tuple[int, int]:
    return await AgentRunRepository(session).clear()


async def clear_cache() -> int | None:
    """Every cached result, in Redis and in this process's memo."""
    site_service.clear_memo()
    return await cache.clear()


async def counts(session: AsyncSession) -> dict[str, Any]:
    kinds = await SiteRepository(session).count_by_kind()
    return {
        "missions": await MissionRepository(session).count(),
        "candidate_sites": kinds.get("candidate", 0),
        "mission_targets": kinds.get("mission_target", 0),
        "agent_runs": await AgentRunRepository(session).count(),
        "cached_results": await cache.count(),
    }
