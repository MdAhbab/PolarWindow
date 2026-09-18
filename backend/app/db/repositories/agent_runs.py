"""Agent run and tool-call persistence.

Every exit path writes a row, including timeouts and total outages. The demo
shows this table as evidence the agent layer is real and bounded; a missing row
for a failure would quietly turn it into evidence of something else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AgentRun, AgentToolCall


@dataclass(slots=True)
class ToolCallRecord:
    seq: int
    tool: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    numbers: list[float] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None


@dataclass(slots=True)
class AgentRunRecord:
    agent: str
    model: str
    status: str
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    attempts: int = 1
    guard_failures: list[dict[str, Any]] | None = None
    error: str | None = None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    id: uuid.UUID | None = None
    created_at: datetime | None = None


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, rec: AgentRunRecord) -> uuid.UUID:
        run = AgentRun(
            agent=rec.agent,
            model=rec.model,
            status=rec.status,
            request=rec.request,
            response=rec.response,
            prompt_tokens=rec.prompt_tokens,
            completion_tokens=rec.completion_tokens,
            latency_ms=rec.latency_ms,
            attempts=rec.attempts,
            guard_failures=rec.guard_failures,
            error=rec.error,
        )
        run.tool_calls = [
            AgentToolCall(
                seq=tc.seq,
                tool=tc.tool,
                args=tc.args,
                result=tc.result,
                numbers=tc.numbers,
                latency_ms=tc.latency_ms,
                error=tc.error,
            )
            for tc in rec.tool_calls
        ]
        self._s.add(run)
        await self._s.flush()
        return run.id

    async def recent(self, limit: int = 50, agent: str | None = None) -> list[AgentRunRecord]:
        stmt = (
            select(AgentRun)
            .options(selectinload(AgentRun.tool_calls))
            .order_by(desc(AgentRun.created_at))
            .limit(limit)
        )
        if agent:
            stmt = stmt.where(AgentRun.agent == agent)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [
            AgentRunRecord(
                id=r.id,
                agent=r.agent,
                model=r.model,
                status=r.status,
                request=r.request,
                response=r.response,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                latency_ms=r.latency_ms,
                attempts=r.attempts,
                guard_failures=r.guard_failures,
                error=r.error,
                created_at=r.created_at,
                tool_calls=[
                    ToolCallRecord(
                        seq=t.seq,
                        tool=t.tool,
                        args=t.args,
                        result=t.result,
                        numbers=list(t.numbers or []),
                        latency_ms=t.latency_ms,
                        error=t.error,
                    )
                    for t in r.tool_calls
                ],
            )
            for r in rows
        ]
