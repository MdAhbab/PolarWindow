"""What an adapter declares, and what its parser returns.

An adapter is a list of :class:`Product` s. Each product names its provider,
its place, where it is fetched from, how often, how long its data stays
usable (its staleness budget), its licence, and a *pure* parser from the body
bytes to :class:`Parsed` values in SI units. The parser checks the schema
and the physical range of every value it keeps; a body that fails raises
:class:`ParseError` and is stored as ``rejected`` while the previous good
snapshot stays current (ADR-8 point 5).
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.feeds import http

PUBLIC_DOMAIN = "US government work (public domain)"


class ParseError(ValueError):
    """The body is not what this parser expects; the snapshot is kept as rejected."""


@dataclass(frozen=True, slots=True)
class Parsed:
    values: dict[str, Any]
    issued_at: datetime | None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    #: Problems that did not reject the body: a value out of range dropped, say.
    issues: list[str] = field(default_factory=list)


Parser = Callable[[bytes], Parsed]
#: A product that needs more than one GET (a lookup, then the data; an index,
#: then byte ranges) supplies its own fetch. It receives the previous good
#: snapshot's ETag and Last-Modified, and returns the body the parser reads.
CustomFetch = Callable[[httpx.AsyncClient, str | None, str | None], Awaitable[http.Fetched]]


@dataclass(frozen=True, slots=True)
class Product:
    provider: str
    product: str
    url: str
    licence: str
    parser_version: str
    interval_s: int
    staleness_s: int
    parse: Parser
    location_key: str = ""
    params: dict[str, str] = field(default_factory=dict)
    #: Query parameters never written to the snapshot (API keys).
    secret_params: frozenset[str] = frozenset()
    headers: dict[str, str] = field(default_factory=dict)
    custom_fetch: CustomFetch | None = None
    #: Keep the raw body. Off for large binary extracts that the provider
    #: itself archives (GRIB on AWS open data): the snapshot records the
    #: object and byte ranges instead.
    keep_raw: bool = True
    #: Tokens this product costs from its provider's bucket.
    cost: float = 1.0

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.provider, self.product, self.location_key)

    def public_url(self) -> str:
        """The URL as stored: every secret parameter removed."""
        q = {k: v for k, v in self.params.items() if k not in self.secret_params}
        return str(httpx.URL(self.url, params=q)) if q else self.url


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """A provider's request allowance: bucket size and refill per hour."""

    name: str
    capacity: float
    per_hour: float


# ---------------------------------------------------------------------------
# Small helpers every parser uses
# ---------------------------------------------------------------------------


def utc(text: str) -> datetime:
    """Parse ISO-8601 (with or without Z/offset, with a space or T) as aware UTC."""
    t = text.strip().replace(" ", "T")
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def in_range(name: str, value: object, lo: float, hi: float, issues: list[str]) -> float | None:
    """``value`` as a float if it is finite and physically plausible, else None + an issue."""
    if value is None:
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        issues.append(f"{name}: not a number ({value!r})")
        return None
    if not math.isfinite(v) or not lo <= v <= hi:
        issues.append(f"{name}: {v} outside the physical range {lo}..{hi}; dropped")
        return None
    return v


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
