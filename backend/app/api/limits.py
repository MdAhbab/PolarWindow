"""Request limits: how large a request body may be, and how often a caller may write.

Two ASGI middlewares, both inside CORS so a refusal reaches the browser with
its headers and its problem detail (``ui.still_works`` included):

- :class:`BodyLimit` refuses a request body over ``max_body_bytes`` with 413,
  from ``Content-Length`` before anything is read, or while reading a body
  sent without one. The largest body the API takes (a risk with every text
  field full) is under 20 KB.
- :class:`RateLimit` counts requests that are not reads, per client address,
  in a sliding minute, and answers 429 with ``Retry-After`` past the limit:
  signing in, the AI assistant (each call spends model quota), the site
  comparison (computed on the request) and every other change each have their
  own allowance. Reads are never limited here.

The counts live in this process: one API process serves this product. Behind
more than one, the limit per process is the limit per client times the number
of processes, which is still a limit.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import orjson
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1 import deps

READS = frozenset({"GET", "HEAD", "OPTIONS"})
ERROR_BASE = deps.ERROR_BASE


def _problem_body(status: int, type_: str, title: str, detail: str, still_works: str) -> bytes:
    return orjson.dumps(
        {
            "detail": {
                "type": f"{ERROR_BASE}/{type_}",
                "title": title,
                "status": status,
                "detail": detail,
                "ui": {"still_works": still_works, "retryable": True, "action": None},
            }
        }
    )


async def _send_problem(
    send: Send, status: int, body: bytes, headers: dict[str, str] | None = None
) -> None:
    raw = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    raw += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": body})


def _too_large(limit: int) -> tuple[str, str, str, str]:
    return (
        "too-large",
        "That request is too large",
        f"A request body may be at most {limit:,} bytes.",
        "Nothing was changed. Everything can still be read, and a shorter entry will work.",
    )


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in READS:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                n = int(declared)
            except ValueError:
                n = self.max_bytes + 1
            if n > self.max_bytes:
                await _send_problem(send, 413, _problem_body(413, *_too_large(self.max_bytes)))
                return
            await self.app(scope, receive, send)
            return

        seen = 0

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    # FastAPI passes an HTTPException raised while reading the
                    # body through as itself, so this becomes the same 413.
                    raise deps.problem(413, *_too_large(self.max_bytes))
            return message

        await self.app(scope, counted, send)


#: Allowance names, by what the request does.
SIGN_IN, AGENTS, COMPARE, WRITES = "sign_in", "agents", "compare", "writes"

_WORDS = {
    SIGN_IN: ("sign-ins", "Signing in again in a minute will work."),
    AGENTS: ("questions to the AI assistant", "Every number and section can still be read."),
    COMPARE: ("site comparisons", "Each site's own numbers can still be read."),
    WRITES: ("changes", "Nothing was changed by this request; everything can still be read."),
}


def allowance(method: str, path: str, prefix: str) -> str | None:
    """Which allowance a request counts against; None for a read."""
    if method in READS:
        return None
    p = path[len(prefix) :] if path.startswith(prefix) else path
    if p == "/auth/demo":
        return SIGN_IN
    if p.startswith("/agents/"):
        return AGENTS
    if p == "/compare":
        return COMPARE
    return WRITES


class RateLimit:
    """A sliding minute per (allowance, client address)."""

    def __init__(
        self,
        app: ASGIApp,
        per_minute: dict[str, int],
        prefix: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.prefix = prefix
        self.clock = clock
        self._seen: dict[tuple[str, str], deque[float]] = {}
        self._calls = 0

    def _prune(self, now: float) -> None:
        for key in [k for k, q in self._seen.items() if not q or q[-1] <= now - 60]:
            del self._seen[key]

    def check(self, kind: str, client: str) -> float | None:
        """Seconds until this caller may try again, or None when allowed (and counted)."""
        limit = self.per_minute.get(kind)
        if not limit:
            return None
        now = self.clock()
        self._calls += 1
        if self._calls % 1000 == 0:
            self._prune(now)
        q = self._seen.setdefault((kind, client), deque())
        while q and q[0] <= now - 60:
            q.popleft()
        if len(q) >= limit:
            return max(0.0, q[0] + 60 - now)
        q.append(now)
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        kind = allowance(scope["method"], scope["path"], self.prefix)
        if kind is not None:
            client: Any = scope.get("client")
            wait = self.check(kind, client[0] if client else "unknown")
            if wait is not None:
                what, still = _WORDS[kind]
                limit = self.per_minute[kind]
                body = _problem_body(
                    429,
                    "too-many-requests",
                    "Too many requests",
                    f"At most {limit} {what} a minute from one address.",
                    still,
                )
                await _send_problem(send, 429, body, {"Retry-After": str(max(1, math.ceil(wait)))})
                return
        await self.app(scope, receive, send)
