"""Share the downloaded data without the internet: ``polar-data export`` and ``import``.

Everything under ``data/`` that git ignores (SPICE kernels, terrain, gravity, flown trajectories,
the weather-check caches and the rest) is fetched once from NASA's and NOAA's servers, some of
which send 30 kB/s. ``export`` copies it to a folder or to one ``.zip``, with ``MANIFEST.json``:
every file with its size and SHA-256. ``import`` copies a shared copy back one file at a time and
keeps a file only when its SHA-256 matches the list, so a download from a shared drive that broke
half-way is caught, not loaded.

``import`` takes a folder, a ``.zip``, or several ``.zip`` files: Google Drive splits a large
folder into ``<name>-001.zip``, ``<name>-002.zip`` and so on when it is downloaded, and only one
part carries ``MANIFEST.json``. A file already in ``data/`` is never replaced; if it differs from
the shared copy it is kept and listed. What the copy does not have, ``polar-data sync`` downloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, Final

from app.core.kernels import METAKERNEL_NAME

MANIFEST: Final[str] = "MANIFEST.json"
FORMAT: Final[int] = 1
_CHUNK: Final[int] = 1 << 20

#: Never shared: the sync log, partial downloads, the kernel list (it holds this machine's
#: absolute path and is rewritten on load), and orbiter kernels made from this machine's own
#: recorded feed snapshots (their names carry snapshot ids another database does not have).
_SKIP_NAMES: Final[frozenset[str]] = frozenset({".sync-state.json", ".DS_Store", METAKERNEL_NAME})
_SKIP_SUFFIXES: Final[tuple[str, ...]] = (".part", ".import-part")
_SKIP_DIRS: Final[tuple[str, ...]] = ("kernels/orbiters/",)
#: Already compressed, so stored in a ``.zip`` as they are.
_STORED: Final[frozenset[str]] = frozenset(
    {".npz", ".png", ".zip", ".gz", ".bz2", ".zst", ".xlsx", ".pdf", ".nc", ".hdf"}
)


class ShareError(Exception):
    """The shared copy cannot be used as given; the message says why, in plain words."""


@dataclass(frozen=True, slots=True)
class Entry:
    #: Relative to ``data/``, with ``/`` separators.
    path: str
    size: int
    sha256: str


@dataclass(slots=True)
class Summary:
    files: int = 0
    total_bytes: int = 0
    copied: list[str] = field(default_factory=list)
    #: Already here with the same SHA-256 (import), or unchanged since the last export.
    present: int = 0
    #: Here already but different from the shared copy: kept as it is.
    kept: list[str] = field(default_factory=list)
    #: Listed in the manifest but not in what was given (a Drive part not downloaded).
    missing: list[str] = field(default_factory=list)
    #: In the copy, but its bytes do not match the manifest: not used.
    bad: list[str] = field(default_factory=list)


def keep(rel: str) -> bool:
    """False for files that are never shared (see ``_SKIP_*``)."""
    name = PurePosixPath(rel).name
    return (
        name not in _SKIP_NAMES
        and not name.endswith(_SKIP_SUFFIXES)
        and not rel.startswith(_SKIP_DIRS)
    )


def shareable(data_dir: Path, repo_root: Path) -> list[str]:
    """Files under ``data_dir`` that were downloaded or built here: the ones git ignores.

    Files git tracks travel with the repository, and files neither tracked nor ignored are
    work in progress; neither is exported. A data folder outside the repository
    (``PW_DATA_DIR``) is exported whole.
    """
    data_dir, repo_root = data_dir.resolve(), repo_root.resolve()
    if not data_dir.is_relative_to(repo_root):
        names = [p.relative_to(data_dir).as_posix() for p in data_dir.rglob("*") if p.is_file()]
    else:
        argv = ["git", "ls-files", "-z", "--others", "--ignored", "--exclude-standard"]
        listed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            [*argv, "--", str(data_dir)], cwd=repo_root, capture_output=True, check=True
        ).stdout.decode()
        prefix = data_dir.relative_to(repo_root).as_posix() + "/"
        names = [n[len(prefix) :] for n in listed.split("\0") if n.startswith(prefix)]
    return sorted(n for n in names if keep(n) and (data_dir / n).is_file())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy(src: IO[bytes], dest: Path) -> tuple[str, int]:
    """Stream ``src`` into ``dest``; the SHA-256 and size of what was written."""
    h, n = hashlib.sha256(), 0
    with dest.open("wb") as out:
        for chunk in iter(lambda: src.read(_CHUNK), b""):
            h.update(chunk)
            out.write(chunk)
            n += len(chunk)
    return h.hexdigest(), n


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _previous(folder: Path) -> dict[str, str]:
    """Path to SHA-256 from an earlier export into ``folder``, if there is one."""
    try:
        return {e.path: e.sha256 for e in _entries((folder / MANIFEST).read_bytes())}
    except (OSError, ShareError):
        return {}


def export(
    data_dir: Path, out: Path, files: Sequence[str], *, commit: str | None = None
) -> Summary:
    """Copy ``files`` (relative to ``data_dir``) to ``out``: a folder, or one ``.zip``.

    Into a folder that already holds an export, only files whose SHA-256 changed are copied
    again, so re-exporting into a synced drive folder uploads only the difference.
    """
    entries = [
        Entry(rel, (data_dir / rel).stat().st_size, _sha256(data_dir / rel)) for rel in files
    ]
    total = sum(e.size for e in entries)
    text = json.dumps(
        {
            "format": FORMAT,
            "made_by": "polar-data export",
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": commit,
            "total_bytes": total,
            "files": [{"path": e.path, "size": e.size, "sha256": e.sha256} for e in entries],
        },
        indent=1,
    )
    summary = Summary(files=len(entries), total_bytes=total)
    if out.suffix.lower() == ".zip":
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
            for e in entries:
                stored = PurePosixPath(e.path).suffix.lower() in _STORED
                z.write(
                    data_dir / e.path,
                    arcname=e.path,
                    compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
                    compresslevel=None if stored else 1,
                )
                summary.copied.append(e.path)
            z.writestr(MANIFEST, text + "\n")
        os.replace(tmp, out)
        return summary
    out.mkdir(parents=True, exist_ok=True)
    before = _previous(out)
    for e in entries:
        dest = out / e.path
        if before.get(e.path) == e.sha256 and dest.is_file() and dest.stat().st_size == e.size:
            summary.present += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        shutil.copyfile(data_dir / e.path, tmp)
        os.replace(tmp, dest)
        summary.copied.append(e.path)
    # Last, so a folder that holds a manifest holds every file it lists.
    (out / MANIFEST).write_text(text + "\n", encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _safe(rel: object) -> str:
    """``rel`` if it is a plain relative path inside ``data/``; never ``..`` or absolute."""
    if (
        not isinstance(rel, str)
        or not rel
        or rel.startswith("/")
        or "\\" in rel
        or ":" in rel
        or any(part in ("", ".", "..") for part in rel.split("/"))
    ):
        raise ShareError(f"MANIFEST.json lists a path outside data/: {rel!r}")
    return rel


def _entries(raw: bytes) -> list[Entry]:
    try:
        doc = json.loads(raw)
        fmt = int(doc["format"])
        rows = doc["files"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ShareError(f"MANIFEST.json cannot be read ({type(exc).__name__})") from exc
    if fmt > FORMAT:
        raise ShareError(
            f"the copy was made by a newer POLAR WINDOW (format {fmt}); update this checkout first"
        )
    out: list[Entry] = []
    for row in rows:
        try:
            size, sha = int(row["size"]), str(row["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ShareError("MANIFEST.json has a damaged row") from exc
        if len(sha) != 64 or size < 0:
            raise ShareError(f"MANIFEST.json has a damaged row for {row.get('path')!r}")
        out.append(Entry(_safe(row.get("path")), size, sha))
    return out


def _match(name: str, wanted: Mapping[str, Entry]) -> str | None:
    """The manifest path a zip member stands for: its longest ending that the manifest lists.

    A Drive download puts the shared folder's name in front of every path
    (``polar-window-data/kernels/de440.bsp``); a ``.zip`` made by ``export`` does not.
    """
    parts = name.split("/")
    for i in range(len(parts)):
        rel = "/".join(parts[i:])
        if rel in wanted:
            return rel
    return None


def import_(sources: Sequence[Path], data_dir: Path) -> Summary:
    """Copy into ``data_dir`` every file of a shared copy that is not here yet."""
    with ExitStack() as stack:
        roots: list[Path] = []
        zips: list[zipfile.ZipFile] = []
        for src in sources:
            if src.is_dir():
                roots += [src, *sorted(c for c in src.iterdir() if c.is_dir())]
                zips += [stack.enter_context(zipfile.ZipFile(z)) for z in sorted(src.glob("*.zip"))]
            elif src.is_file() and zipfile.is_zipfile(src):
                zips.append(stack.enter_context(zipfile.ZipFile(src)))
            else:
                raise ShareError(f"{src} is neither a folder nor a .zip file")

        raw: bytes | None = next(
            ((r / MANIFEST).read_bytes() for r in roots if (r / MANIFEST).is_file()), None
        )
        for z in zips:
            if raw is not None:
                break
            names = [n for n in z.namelist() if n == MANIFEST or n.endswith("/" + MANIFEST)]
            if names:
                raw = z.read(min(names, key=len))
        if raw is None:
            raise ShareError(
                "no MANIFEST.json in what was given: the copy must be made by `polar-data export` "
                "(or `python3 run.py --export-data`)"
            )
        entries = [e for e in _entries(raw) if keep(e.path)]
        wanted = {e.path: e for e in entries}
        in_zip: dict[str, tuple[zipfile.ZipFile, str]] = {}
        for z in zips:
            for name in z.namelist():
                rel = None if name.endswith("/") else _match(name, wanted)
                if rel is not None:
                    in_zip.setdefault(rel, (z, name))

        summary = Summary(files=len(entries), total_bytes=sum(e.size for e in entries))
        for e in entries:
            dest = data_dir / e.path
            if dest.exists():
                same = (
                    dest.is_file() and dest.stat().st_size == e.size and _sha256(dest) == e.sha256
                )
                if same:
                    summary.present += 1
                else:
                    summary.kept.append(e.path)
                continue
            src_file = next((r / e.path for r in roots if (r / e.path).is_file()), None)
            if src_file is not None:
                opened: IO[bytes] = src_file.open("rb")
            elif e.path in in_zip:
                z, name = in_zip[e.path]
                opened = z.open(name)
            else:
                summary.missing.append(e.path)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".import-part")
            with opened:
                sha, n = _copy(opened, tmp)
            if sha != e.sha256 or n != e.size:
                tmp.unlink(missing_ok=True)
                summary.bad.append(e.path)
                continue
            os.replace(tmp, dest)
            summary.copied.append(e.path)
        return summary
