"""Turn one fetch into one stored snapshot and one line of health (ADR-8).

* An unchanged product (HTTP 304, or a body byte-identical to the last good
  one) adds no snapshot: health records the successful check, and the
  current snapshot stays current.
* A body the parser refuses is kept with status ``rejected`` and its reason,
  and the previous good snapshot stays current.
* Raw bodies are compressed with zstd. Up to 256 KB compressed they are kept
  in the row; above that, in a content-addressed file under
  ``data/feeds/raw/`` named by the body's SHA-256, referenced by ``raw_ref``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import zstandard as zstd
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.feeds import FeedRepository
from app.feeds.base import Parsed, ParseError, Product
from app.feeds.http import Fetched

MAX_INLINE_RAW = 256 * 1024
_compressor = zstd.ZstdCompressor(level=9)


@dataclass(frozen=True, slots=True)
class Outcome:
    ok: bool
    snapshot_id: int | None
    status: str  # "new" | "unchanged" | "rejected"
    message: str


def raw_path(root: Path, sha: str) -> Path:
    return root / sha[:2] / f"{sha}.zst"


def _store_raw(root: Path, body: bytes, sha: str) -> tuple[bytes | None, str | None]:
    packed = _compressor.compress(body)
    if len(packed) <= MAX_INLINE_RAW:
        return packed, None
    path = raw_path(root, sha)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(packed)
        tmp.replace(path)
    return None, str(path.relative_to(root.parent.parent))


async def record(
    session: AsyncSession,
    product: Product,
    got: Fetched,
    *,
    raw_root: Path,
    now: datetime | None = None,
) -> Outcome:
    """Store what ``got`` holds for ``product``. The caller commits."""
    repo = FeedRepository(session)
    now = now or datetime.now(UTC)
    if got.not_modified:
        last = await repo.latest_ok(product.provider, product.product, product.location_key)
        return Outcome(
            True, last.id if last else None, "unchanged", "not modified since last fetch"
        )

    sha = hashlib.sha256(got.body).hexdigest()
    same = await repo.find_same_body(product.provider, product.product, product.location_key, sha)
    if same is not None:
        return Outcome(True, same, "unchanged", "same body as the last good snapshot")

    parsed: Parsed | None = None
    issues: list[str] = []
    status = "ok"
    try:
        parsed = product.parse(got.body)
        issues = list(parsed.issues)
    except ParseError as exc:
        status = "rejected"
        issues = [f"rejected: {exc}"]
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        status = "rejected"
        issues = [f"rejected: the parser failed ({type(exc).__name__}: {exc})"]

    raw: bytes | None = None
    raw_ref: str | None = None
    if product.keep_raw or status == "rejected":
        raw, raw_ref = _store_raw(raw_root, got.body, sha)

    values = {
        "provider": product.provider,
        "product": product.product,
        "location_key": product.location_key,
        "issued_at": parsed.issued_at if parsed else None,
        "valid_from": parsed.valid_from if parsed else None,
        "valid_to": parsed.valid_to if parsed else None,
        "fetched_at": now,
        "url": got.url if not product.secret_params else product.public_url(),
        "http_status": got.status,
        "etag": got.etag,
        "last_modified": got.last_modified,
        "content_sha256": sha,
        "raw": raw,
        "raw_ref": raw_ref,
        "raw_bytes": len(got.body),
        "parsed": parsed.values if parsed else None,
        "parser_version": product.parser_version,
        "licence": product.licence,
        "status": status,
        "issues": issues,
    }
    sid = await repo.insert_snapshot(values)
    if status == "rejected":
        return Outcome(False, sid, "rejected", issues[0])
    if sid is None:  # a concurrent writer stored the identical body first
        sid = await repo.find_same_body(
            product.provider, product.product, product.location_key, sha
        )
        return Outcome(True, sid, "unchanged", "same body stored concurrently")
    return Outcome(True, sid, "new", f"{len(got.body)} bytes, {len(issues)} issues")
