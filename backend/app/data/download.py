"""One way to download a file for this project: resumable, retried, verified.

Every dataset the product uses (``registry.py``) comes through here, so the
failure modes are handled once:

* **Slow or dropped connections.** NAIF and PDS serve large files over links
  that stall; a 31 MB Earth-orientation kernel was measured arriving at
  30 kB/s. Downloads resume from the ``.part`` file with an HTTP ``Range``
  request instead of starting over, and a stall (no bytes for ``stall_s``) is
  a retry, not a hang.
* **Moved files.** NAIF moves superseded kernels to ``a_old_versions/``; each
  dataset may name mirrors, tried in order.
* **Truncation and corruption.** A file is renamed into place only after its
  size floor and (when pinned) its SHA-256 pass. A partial file never has the
  final name, so nothing downstream can load half a kernel.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

#: Identifies the project to data providers (NWS and others ask for this).
USER_AGENT = "PolarWindow/0.1 (+https://github.com/MdAhbab/PolarWindow)"


class DownloadFailed(RuntimeError):
    """Every address was tried and none produced a verified file."""


@dataclass(frozen=True, slots=True)
class Target:
    urls: tuple[str, ...]
    dest: Path
    min_bytes: int = 1
    sha256: str | None = None
    headers: tuple[tuple[str, str], ...] = ()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verified(target: Target) -> bool:
    """Is the final file present, big enough and (if pinned) the right bytes?"""
    p = target.dest
    if not p.exists() or p.stat().st_size < target.min_bytes:
        return False
    return target.sha256 is None or sha256_of(p) == target.sha256


def fetch(
    target: Target,
    *,
    attempts: int = 6,
    stall_s: float = 60.0,
    progress: Callable[[int, int], None] | None = None,
    client: httpx.Client | None = None,
) -> Path:
    """Download ``target`` unless it is already verified. Returns the final path."""
    if verified(target):
        return target.dest
    target.dest.parent.mkdir(parents=True, exist_ok=True)
    part = target.dest.with_name(target.dest.name + ".part")
    errors: list[str] = []
    own = client is None
    http = client or httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(connect=20.0, read=stall_s, write=30.0, pool=30.0),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        for url in target.urls:
            for attempt in range(1, attempts + 1):
                try:
                    _stream(http, url, part, dict(target.headers), progress)
                    break
                except (httpx.HTTPError, OSError) as exc:
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (
                        401,
                        403,
                        404,
                        410,
                    ):
                        errors.append(f"{url}: HTTP {exc.response.status_code}")
                        break  # a missing or forbidden file will not appear on retry
                    wait = min(60.0, 2.0**attempt)
                    errors.append(f"{url} (attempt {attempt}): {type(exc).__name__}: {exc}")
                    log.warning("  %s: %s; retrying in %.0f s", target.dest.name, exc, wait)
                    time.sleep(wait)
            else:
                continue
            if not part.exists():
                continue
            size = part.stat().st_size
            if size < target.min_bytes:
                errors.append(f"{url}: got {size:,} bytes, expected at least {target.min_bytes:,}")
                part.unlink(missing_ok=True)
                continue
            if target.sha256 is not None:
                got = sha256_of(part)
                if got != target.sha256:
                    errors.append(f"{url}: sha256 {got} != pinned {target.sha256}")
                    part.unlink(missing_ok=True)
                    continue
            part.replace(target.dest)
            return target.dest
    finally:
        if own:
            http.close()
    raise DownloadFailed(f"Could not download {target.dest.name}.\n  " + "\n  ".join(errors[-8:]))


def _stream(
    http: httpx.Client,
    url: str,
    part: Path,
    headers: dict[str, str],
    progress: Callable[[int, int], None] | None,
) -> None:
    have = part.stat().st_size if part.exists() else 0
    req_headers = dict(headers)
    if have:
        req_headers["Range"] = f"bytes={have}-"
    with http.stream("GET", url, headers=req_headers) as resp:
        if resp.status_code == 416:  # already complete
            return
        resp.raise_for_status()
        if have and resp.status_code != 206:
            have = 0  # server ignored Range: start over
        total = have + int(resp.headers.get("content-length", 0) or 0)
        mode = "ab" if have else "wb"
        written = have
        with part.open(mode) as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
                written += len(chunk)
                if progress is not None:
                    progress(written, total)
