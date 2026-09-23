"""SPICE kernel acquisition, caching and verification.

This module is the single most common way this project breaks, so it is built
to fail in the most useful way possible: loudly, early, naming the exact file,
its size, its source URL and the command that fixes it.

It is the one module in ``core/`` permitted to touch the network, and it is
never called from a request path -- only from application startup and from the
``fetch-kernels`` CLI. Everything else in ``core/`` stays pure.

Design notes
------------
* Kernels are content-addressed by SHA256 where NAIF publishes a stable file.
  A truncated download is worse than a missing one, because ``furnsh`` on a
  partial SPK succeeds and then returns wrong vectors, so every cached file is
  size-checked and (when a digest is known) hash-checked before use.
* The metakernel is generated, not committed. Hand-written metakernels drift
  from the files actually on disk, and the resulting error surfaces hundreds of
  lines later as an opaque SPICE(NOLOADEDFILES).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

NAIF_GENERIC = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels"


class KernelError(RuntimeError):
    """Raised when a kernel is missing, truncated or unverifiable.

    The message is user-facing: it is surfaced through ``/healthz`` and, from
    there, into the UI's error panel. It must always say what to run next.
    """


@dataclass(frozen=True, slots=True)
class KernelSpec:
    """One SPICE kernel we require.

    Attributes
    ----------
    name:
        Filename on disk, inside the kernel directory.
    url:
        Canonical NAIF URL. Printed verbatim in error messages so a human can
        fetch it by hand when the automated path is blocked by a proxy.
    kind:
        NAIF kernel type, used only to group the generated metakernel.
    min_bytes:
        A floor, not an exact size. NAIF occasionally reissues these files, so
        an exact-size check would be brittle; a floor still catches the
        truncated-download failure that actually happens.
    sha256:
        Optional pinned digest. When present it is enforced.
    why:
        One line explaining what breaks without it. This is what makes the
        error message actionable rather than merely accurate.
    """

    name: str
    url: str
    kind: str
    min_bytes: int
    sha256: str | None = None
    why: str = ""


# The minimum set that makes MOON_ME work. Each entry's `why` is the sentence a
# person reads at 2 a.m. when the demo will not start.
REQUIRED_KERNELS: tuple[KernelSpec, ...] = (
    KernelSpec(
        name="naif0012.tls",
        url=f"{NAIF_GENERIC}/lsk/naif0012.tls",
        kind="LSK",
        min_bytes=5_000,
        sha256="678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b",
        why="Leapseconds. Without it every UTC -> ET conversion fails and no "
        "timestamp can be interpreted at all.",
    ),
    KernelSpec(
        name="de440.bsp",
        url=f"{NAIF_GENERIC}/spk/planets/de440.bsp",
        kind="SPK",
        min_bytes=100_000_000,
        sha256="a4ce9bf9b3282becc9f4b2ac3cebe03a2ae7599981aabd7265fd8482fff7c4b5",
        why="Planetary ephemeris. Without it there are no Sun or Earth "
        "positions, so sunlight and Earth-contact hours cannot be computed.",
    ),
    KernelSpec(
        name="pck00011.tpc",
        url=f"{NAIF_GENERIC}/pck/pck00011.tpc",
        kind="PCK",
        min_bytes=100_000,
        sha256="3dff7b1dbeceaa01f25467767d3fa25816051c85d162d1edf04acb310ee28bb1",
        why="Body constants: the Moon's radii and orientation model. Without "
        "it the lunar body-fixed frame has no shape to attach to.",
    ),
    KernelSpec(
        name="moon_pa_de440_200625.bpc",
        url=f"{NAIF_GENERIC}/pck/moon_pa_de440_200625.bpc",
        kind="PCK",
        min_bytes=10_000_000,
        sha256="60cd55aa401ea2ea97360636f567554bfe4e37bb829f901b4460a455dfaf783f",
        why="Lunar principal-axis orientation. Without it MOON_PA -- and "
        "therefore MOON_ME -- cannot be realised, so azimuths are meaningless.",
    ),
    KernelSpec(
        name="moon_de440_250416.tf",
        url=f"{NAIF_GENERIC}/fk/satellites/moon_de440_250416.tf",
        kind="FK",
        min_bytes=5_000,
        sha256="a47c71e9c9f33796bdafb2c9d69a7ee447b6016ecad80f71cd6f3e479f9cf768",
        why="Frame kernel defining MOON_ME relative to MOON_PA. Without it "
        "SPICE knows the Moon's spin but not the mean-Earth frame the site "
        "coordinates are expressed in.",
    ),
)

METAKERNEL_NAME = "polar-window.tm"


_DIGESTS: dict[tuple[str, int, int], str] = {}


def _sha256(path: Path) -> str:
    """The file's SHA-256, computed once per (path, size, mtime).

    ``/healthz`` verifies every kernel on each call; re-hashing the 120 MB
    ephemeris there would make a liveness probe take half a second. A changed
    file changes its size or mtime and is hashed again.
    """
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _DIGESTS:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _DIGESTS[key] = h.hexdigest()
    return _DIGESTS[key]


def verify(spec: KernelSpec, directory: Path) -> Path:
    """Check one kernel on disk, returning its path.

    Raises
    ------
    KernelError
        If the file is absent, too small to be complete, or fails its pinned
        digest. The message names the fix.
    """
    path = directory / spec.name
    if not path.exists():
        raise KernelError(
            f"SPICE kernel missing: {spec.name}\n"
            f"  expected at : {path}\n"
            f"  download    : {spec.url}\n"
            f"  sha256      : {spec.sha256 or 'not pinned'}\n"
            f"  needed for  : {spec.why}\n"
            f"  fix         : make kernels   (or: uv run polar-kernels fetch)"
        )

    size = path.stat().st_size
    if size < spec.min_bytes:
        raise KernelError(
            f"SPICE kernel looks truncated: {spec.name}\n"
            f"  on disk     : {size:,} bytes\n"
            f"  expected    : at least {spec.min_bytes:,} bytes\n"
            f"  path        : {path}\n"
            f"  needed for  : {spec.why}\n"
            f"  fix         : delete the file and re-run `make kernels`.\n"
            f"  note        : a partial SPK can furnsh without error and then "
            f"return wrong vectors, which is why this is checked."
        )

    if spec.sha256 is not None:
        actual = _sha256(path)
        if actual != spec.sha256:
            raise KernelError(
                f"SPICE kernel failed its checksum: {spec.name}\n"
                f"  expected sha256 : {spec.sha256}\n"
                f"  actual sha256   : {actual}\n"
                f"  path            : {path}\n"
                f"  fix             : delete the file and re-run `make kernels`."
            )
    return path


def verify_all(directory: Path, specs: Iterable[KernelSpec] = REQUIRED_KERNELS) -> list[Path]:
    """Verify every required kernel, reporting *all* problems at once.

    Reporting one missing kernel at a time turns a five-minute fix into five
    round trips, so the failures are collected and raised together.
    """
    paths: list[Path] = []
    problems: list[str] = []
    for spec in specs:
        try:
            paths.append(verify(spec, directory))
        except KernelError as exc:
            problems.append(str(exc))
    if problems:
        raise KernelError(
            f"{len(problems)} of {len(tuple(specs))} SPICE kernels are not usable.\n\n"
            + "\n\n".join(problems)
        )
    return paths


def missing(directory: Path, specs: Iterable[KernelSpec] = REQUIRED_KERNELS) -> list[str]:
    """Names of kernels that are absent or unusable. Never raises.

    Used by ``/healthz``, which must report a problem rather than become one.
    """
    out: list[str] = []
    for spec in specs:
        try:
            verify(spec, directory)
        except KernelError:
            out.append(spec.name)
    return out


def download(spec: KernelSpec, directory: Path, *, timeout: float = 600.0) -> Path:
    """Fetch one kernel to disk, atomically.

    Downloads to ``<name>.part`` and renames on success, so an interrupted
    fetch can never leave a truncated file that later furnshes.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / spec.name
    partial = directory / f"{spec.name}.part"

    log.info("fetching %s (%s) from %s", spec.name, spec.kind, spec.url)
    try:
        with httpx.stream("GET", spec.url, timeout=timeout, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            written = 0
            with partial.open("wb") as fh:
                for chunk in resp.iter_bytes(1 << 20):
                    fh.write(chunk)
                    written += len(chunk)
                    if total and written % (32 << 20) < (1 << 20):
                        log.info("  %s: %.0f%%", spec.name, 100 * written / total)
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise KernelError(
            f"Could not download {spec.name}: {exc}\n"
            f"  url : {spec.url}\n"
            f"  fix : download it by hand into {directory} and re-run.\n"
            f"  note: NAIF is occasionally unreachable from corporate networks; "
            f"a browser download of the URL above works when curl does not."
        ) from exc

    if partial.stat().st_size < spec.min_bytes:
        got = partial.stat().st_size
        partial.unlink(missing_ok=True)
        raise KernelError(
            f"Download of {spec.name} finished early: got {got:,} bytes, "
            f"expected at least {spec.min_bytes:,}. Re-run `make kernels`."
        )

    shutil.move(str(partial), str(target))
    log.info("  %s: done (%s bytes)", spec.name, f"{target.stat().st_size:,}")
    return target


def ensure(
    directory: Path,
    *,
    allow_download: bool = True,
    specs: Iterable[KernelSpec] = REQUIRED_KERNELS,
) -> list[Path]:
    """Make every required kernel present and valid.

    With ``allow_download=False`` this is a pure check -- which is what the API
    process uses, because a container that silently downloads 114 MB at boot
    turns a fast failure into a slow mystery.
    """
    specs = tuple(specs)
    if not allow_download:
        return verify_all(directory, specs)

    for spec in specs:
        try:
            verify(spec, directory)
        except KernelError:
            download(spec, directory)
    return verify_all(directory, specs)


def write_metakernel(directory: Path, specs: Iterable[KernelSpec] = REQUIRED_KERNELS) -> Path:
    """Generate the metakernel from the files actually on disk.

    Generated rather than committed: a committed metakernel drifts from the
    kernel set and the resulting failure appears far from its cause.
    """
    specs = tuple(specs)
    verify_all(directory, specs)
    mk = directory / METAKERNEL_NAME
    # PATH_VALUES has a 255-character limit in SPICE; using a symbol keeps the
    # per-file entries short regardless of how deep the container path is.
    lines = [
        "KPL/MK",
        "",
        "  Generated by app/core/kernels.py. Do not edit; re-run `make kernels`.",
        "",
        "\\begindata",
        "",
        f"PATH_VALUES  = ( '{directory}' )",
        "PATH_SYMBOLS = ( 'KERNELS' )",
        "",
        "KERNELS_TO_LOAD = (",
    ]
    lines.extend(f"    '$KERNELS/{spec.name}'," for spec in specs)
    lines.append(")")
    lines.extend(["", "\\begintext", ""])
    mk.write_text("\n".join(lines), encoding="utf-8")
    return mk


def manifest(directory: Path, specs: Iterable[KernelSpec] = REQUIRED_KERNELS) -> dict[str, object]:
    """Describe the kernel set for ``/healthz`` and for golden-test provenance."""
    entries: list[dict[str, object]] = []
    for spec in specs:
        path = directory / spec.name
        entries.append(
            {
                "name": spec.name,
                "kind": spec.kind,
                "present": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "url": spec.url,
            }
        )
    return {
        "directory": str(directory),
        "kernels": entries,
        "missing": missing(directory, specs),
    }


def main(argv: list[str] | None = None) -> None:
    """``polar-kernels fetch|verify``: the command the error messages name.

    ``fetch`` downloads whatever is missing or corrupt, verifies every digest
    and writes the metakernel. Under ``OFFLINE=1`` it refuses to download and
    only verifies, so a demo machine with the network gone fails loudly here
    rather than hanging on NAIF.
    """
    import argparse

    from app.config import get_settings

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(prog="polar-kernels", description=main.__doc__)
    p.add_argument("action", choices=("fetch", "verify"))
    args = p.parse_args(argv)
    s = get_settings()
    try:
        if args.action == "fetch":
            if s.offline:
                log.warning("OFFLINE=1: not downloading; verifying what is on disk")
            ensure(s.kernel_dir, allow_download=not s.offline)
            mk = write_metakernel(s.kernel_dir)
            log.info("kernels verified by sha256; metakernel at %s", mk)
        else:
            verify_all(s.kernel_dir)
            log.info("all %d kernels present and verified by sha256", len(REQUIRED_KERNELS))
    except KernelError as exc:
        raise SystemExit(str(exc)) from exc
