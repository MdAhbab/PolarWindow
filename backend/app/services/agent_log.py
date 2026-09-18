"""Persistence for agent runs, behind a service boundary.

The orchestrator needs to write an audit row on every exit path, but letting it
import a repository directly would break the rule that agents reach the system
only through `tools.py`. Routing it through a service keeps that rule true and
keeps the distinction meaningful: `tools.py` is how an agent *reads the domain*,
this is how the platform *records what the agent did*. They are different
concerns and should not share a door.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.agent_runs import AgentRunRecord, AgentRunRepository, ToolCallRecord

__all__ = ["AgentRunRecord", "ToolCallRecord", "recent_runs", "record_run"]


async def record_run(session: AsyncSession, rec: AgentRunRecord) -> UUID:
    return await AgentRunRepository(session).create(rec)


async def recent_runs(
    session: AsyncSession, limit: int = 50, agent: str | None = None
) -> list[dict[str, Any]]:
    rows = await AgentRunRepository(session).recent(limit=limit, agent=agent)
    return [
        {
            "id": str(r.id),
            "agent": r.agent,
            "model": r.model,
            "status": r.status,
            "attempts": r.attempts,
            "latency_ms": round(r.latency_ms, 1),
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "created_at": r.created_at,
            "guard_failures": r.guard_failures,
            "tool_calls": [
                {
                    "seq": t.seq,
                    "tool": t.tool,
                    "args": t.args,
                    "latency_ms": round(t.latency_ms, 2),
                    "error": t.error,
                    "number_count": len(t.numbers or []),
                }
                for t in r.tool_calls
            ],
        }
        for r in rows
    ]
