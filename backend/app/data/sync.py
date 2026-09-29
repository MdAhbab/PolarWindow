"""``polar-data``: download and build every dataset in ``registry.py``.

    polar-data list                      what is on disk and what is not
    polar-data sync                      core, lifecycle and validation data
    polar-data sync --tier bulk          also the large archives (needs keys)
    polar-data readme                    print the README "Required data" table
    polar-data export PATH               copy what is on disk to a folder or a .zip, to share
    polar-data import PATH [PATH ...]    bring in such a copy (a folder, a .zip, Drive's parts)
    polar-data sync --from PATH          import a copy first, then download what is still missing

``run.py`` calls ``polar-data sync`` once the API and the frontend are up, so
the app is usable while the rest downloads. Everything here is idempotent: a
verified file is never fetched twice, and an interrupted download resumes.
Where NASA's servers are slow or out of reach, one machine that has everything
can ``export`` it and others ``import`` it (``data/share.py``); each file is
checked against the SHA-256 the export listed.

Exit codes
----------
0   everything requested is present
2   something could not be fetched (the summary says what, and why)
10  everything is present *and* something the running API reads (kernels,
    terrain, the seeded database) changed, so the API should be restarted to
    use it. ``run.py`` restarts the backend on this code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.core import kernels as kernel_mod
from app.data import download, share
from app.data.registry import DATASETS, TIERS, Dataset, Tier, in_tiers

log = logging.getLogger("polar-data")

STATE_FILE = ".sync-state.json"
EXIT_OK, EXIT_FAILED, EXIT_RESTART = 0, 2, 10


@dataclass(slots=True)
class Outcome:
    dataset: str
    status: str  # "present" | "fetched" | "built" | "skipped" | "failed"
    detail: str = ""
    changed_api_data: bool = False


def _path(d: Dataset) -> Path:
    return get_settings().data_dir / d.dest


def _kernel_spec(d: Dataset) -> kernel_mod.KernelSpec:
    name = d.dest.split("/", 1)[1]
    for spec in kernel_mod.ALL_KERNELS:
        if spec.name == name:
            return spec
    raise KeyError(name)


def is_present(d: Dataset) -> bool | None:
    """True/False where it can be checked from disk; None for database-built data."""
    s = get_settings()
    if d.method == "kernel":
        return not kernel_mod.missing(s.kernel_dir, (_kernel_spec(d),))
    if d.method == "lola_regional":
        return s.regional_dem_path.exists()
    if d.method == "lola_fine":
        fine = s.dem_dir / "fine"
        return fine.exists() and any(fine.glob("*.npz"))
    if d.method == "seed":
        return None
    if d.method == "built":
        if any(c in d.dest for c in "*?["):
            return any(s.data_dir.glob(d.dest))
        p = _path(d)
        return p.is_dir() and any(p.iterdir()) if d.dest.endswith("/") else p.is_file()
    if d.method in ("cmr", "s3_prefix"):
        p = _path(d)
        return p.exists() and any(p.iterdir())
    return download.verified(_target(d))


def _target(d: Dataset) -> download.Target:
    return download.Target(urls=d.urls, dest=_path(d), min_bytes=d.min_bytes, sha256=d.sha256)


# ---------------------------------------------------------------------------
# One step per method
# ---------------------------------------------------------------------------


def _progress(name: str) -> Callable[[int, int], None]:
    last = [0.0]

    def report(done: int, total: int) -> None:
        now = time.monotonic()
        if now - last[0] >= 5.0:
            last[0] = now
            pct = f"{100 * done / total:.0f}%" if total else f"{done / 1e6:.0f} MB"
            log.info("  %s: %s", name, pct)

    return report


def _sync_kernel(d: Dataset) -> Outcome:
    s = get_settings()
    spec = _kernel_spec(d)
    if not kernel_mod.missing(s.kernel_dir, (spec,)):
        return Outcome(d.id, "present")
    # Through the downloader (resume, retries, mirrors), then the kernel
    # module's own verification: one definition of "a good kernel".
    download.fetch(
        download.Target(
            urls=d.urls, dest=s.kernel_dir / spec.name, min_bytes=spec.min_bytes, sha256=spec.sha256
        ),
        progress=_progress(spec.name),
    )
    kernel_mod.verify(spec, s.kernel_dir)
    return Outcome(d.id, "fetched", changed_api_data=True)


def _sync_file(d: Dataset) -> Outcome:
    if not d.urls:
        return Outcome(d.id, "skipped", "no download address yet; see the README")
    if download.verified(_target(d)):
        return Outcome(d.id, "present")
    download.fetch(_target(d), progress=_progress(Path(d.dest).name))
    return Outcome(d.id, "fetched")


def _sync_lola_regional(d: Dataset) -> Outcome:
    s = get_settings()
    if s.regional_dem_path.exists():
        return Outcome(d.id, "present")
    from app.data.ingest_lola import ensure_regional_dem

    ensure_regional_dem()
    return Outcome(d.id, "fetched", changed_api_data=True)


def _run(cmd: list[str]) -> None:
    backend = Path(__file__).resolve().parents[2]
    log.info("  $ %s", " ".join(cmd))
    subprocess.run(cmd, cwd=backend, check=True)  # noqa: S603 -- fixed argv, no shell


def _sync_seed(d: Dataset) -> Outcome:
    """Migrate, load missions, and build skylines and numbers for sites that lack them."""
    from app.workers.precompute import sites_needing_work

    py = sys.executable
    _run([py, "-m", "alembic", "upgrade", "head"])
    _run([py, "-m", "app.data.ingest_missions"])
    todo = asyncio.run(sites_needing_work())
    if not todo:
        return Outcome(d.id, "present", "every site has its skyline and numbers")
    log.info("  %d site(s) need a skyline or numbers: %s", len(todo), ", ".join(todo))
    _run([py, "-m", "app.workers.precompute", "--sites", *todo])
    s = get_settings()
    if not (s.tile_dir.exists() and any(s.tile_dir.rglob("*.png"))):
        _run([py, "-m", "app.data.ingest_lola", "tiles", "--max-zoom", "5"])
    return Outcome(d.id, "built", f"{len(todo)} site(s)", changed_api_data=True)


def _sync_cmr(d: Dataset) -> Outcome:
    """Every file in an Earthdata collection, listed through CMR (bulk tier only)."""
    import httpx

    s = get_settings()
    if not s.earthdata_token:
        return Outcome(d.id, "skipped", f"needs {d.needs_key}: set PW_EARTHDATA_TOKEN (see README)")
    assert d.cmr_collection is not None
    dest = _path(d)
    dest.mkdir(parents=True, exist_ok=True)
    auth = (("Authorization", f"Bearer {s.earthdata_token}"),)
    fetched = 0
    search_after: str | None = None
    with httpx.Client(timeout=60.0, headers={"User-Agent": download.USER_AGENT}) as cmr:
        while True:
            headers = {"CMR-Search-After": search_after} if search_after else {}
            r = cmr.get(
                "https://cmr.earthdata.nasa.gov/search/granules.json",
                params={"collection_concept_id": d.cmr_collection, "page_size": 200},
                headers=headers,
            )
            r.raise_for_status()
            entries = r.json()["feed"]["entry"]
            for g in entries:
                links = [
                    x["href"]
                    for x in g.get("links", [])
                    if x.get("rel", "").endswith("/data#") and x["href"].startswith("https")
                ]
                if not links:
                    continue
                name = links[0].rsplit("/", 1)[-1]
                target = download.Target(urls=(links[0],), dest=dest / name, headers=auth)
                if not download.verified(target):
                    download.fetch(target)
                    fetched += 1
            search_after = r.headers.get("CMR-Search-After")
            if not entries or not search_after:
                break
    return Outcome(d.id, "fetched" if fetched else "present", f"{fetched} new file(s)")


def _sync_s3_prefix(d: Dataset) -> Outcome:
    """Every object under a public S3 prefix (no account), resumable per file."""
    import re

    import httpx

    assert d.s3_prefix is not None and d.urls
    base = d.urls[0].rstrip("/")
    dest = _path(d)
    dest.mkdir(parents=True, exist_ok=True)
    keys: list[tuple[str, int]] = []
    token: str | None = None
    with httpx.Client(timeout=60.0, headers={"User-Agent": download.USER_AGENT}) as s3:
        while True:
            params = {"list-type": "2", "prefix": d.s3_prefix, "max-keys": "1000"}
            if token:
                params["continuation-token"] = token
            r = s3.get(base + "/", params=params)
            r.raise_for_status()
            body = r.text
            for key, size in re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", body, re.S):
                if d.s3_suffix is None or key.endswith(d.s3_suffix):
                    keys.append((key, int(size)))
            m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", body)
            if not m:
                break
            token = m.group(1)
    if not keys:
        raise download.DownloadFailed(f"no objects under {base}/{d.s3_prefix}")
    fetched = 0
    for key, size in keys:
        target = download.Target(
            urls=(f"{base}/{key}",), dest=dest / key.rsplit("/", 1)[-1], min_bytes=size
        )
        if not download.verified(target):
            download.fetch(target)
            fetched += 1
    return Outcome(
        d.id, "fetched" if fetched else "present", f"{fetched} of {len(keys)} file(s) new"
    )


def _sync_built(d: Dataset) -> Outcome:
    if is_present(d):
        return Outcome(d.id, "present")
    return Outcome(
        d.id,
        "skipped",
        f"made by `{d.build}` (hours of downloads), or copied from a shared data folder "
        "with `polar-data import`",
    )


_STEPS = {
    "kernel": _sync_kernel,
    "file": _sync_file,
    "lola_regional": _sync_lola_regional,
    "lola_fine": None,  # built by the seed step, which knows the sites
    "seed": _sync_seed,
    "cmr": _sync_cmr,
    "s3_prefix": _sync_s3_prefix,
    "built": _sync_built,
}


def sync(tiers: tuple[Tier, ...]) -> list[Outcome]:
    s = get_settings()
    if s.offline:
        log.warning("OFFLINE=1: nothing will be downloaded; listing what is on disk")
        return [
            Outcome(d.id, "present" if is_present(d) else "skipped", "offline")
            for d in in_tiers(tiers)
        ]
    outcomes: list[Outcome] = []
    for d in in_tiers(tiers):
        step = _STEPS[d.method]
        if step is None:
            continue
        log.info("[%s] %s", d.tier, d.title)
        try:
            outcomes.append(step(d))
        except Exception as exc:  # one dataset failing must not stop the others
            log.error("  failed: %s", exc)
            outcomes.append(Outcome(d.id, "failed", f"{type(exc).__name__}: {exc}"))
        log.info("  -> %s %s", outcomes[-1].status, outcomes[-1].detail)
    if any(o.dataset.startswith("kernel:") and o.status == "fetched" for o in outcomes):
        kernel_mod.write_metakernel(s.kernel_dir, kernel_mod.loadable(s.kernel_dir))
    _write_state(outcomes)
    return outcomes


def _write_state(outcomes: list[Outcome]) -> None:
    path = get_settings().data_dir / STATE_FILE
    previous: dict[str, object] = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text())
        except ValueError:
            previous = {}
    datasets = dict(previous.get("datasets", {}))  # type: ignore[call-overload]
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for o in outcomes:
        datasets[o.dataset] = {"status": o.status, "detail": o.detail, "at": now}
    path.write_text(json.dumps({"updated": now, "datasets": datasets}, indent=2) + "\n")


# ---------------------------------------------------------------------------
# README table
# ---------------------------------------------------------------------------

README_BEGIN = "<!-- required-data:begin (generated by `polar-data readme`; do not edit) -->"
README_END = "<!-- required-data:end -->"

_TIER_HEADINGS: dict[Tier, str] = {
    "core": "Needed to start (fetched first)",
    "lifecycle": "Needed by the launch, trip and contact sections",
    "validation": "Used only to check our numbers",
    "bulk": "Large archives, fetched only on request (`polar-data sync --tier bulk`)",
}


def _size(n: int) -> str:
    if n <= 0:
        return "-"
    for unit, div in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= div:
            return f"{n / div:.0f} {unit}" if n / div >= 10 else f"{n / div:.1f} {unit}"
    return f"{n} B"


def readme_table() -> str:
    lines = [README_BEGIN, ""]
    for tier in TIERS:
        rows = in_tiers((tier,))
        if not rows:
            continue
        lines += [f"**{_TIER_HEADINGS[tier]}**", ""]
        lines += ["| Dataset | Provider | Size | Goes to `data/` | Needed for | Account |"]
        lines += ["|---|---|---|---|---|---|"]
        for d in rows:
            title = f"[{d.title}]({d.source})" if d.source else d.title
            if d.catalogue:
                title += f" ([data.nasa.gov]({d.catalogue}))"
            if not d.address_confirmed:
                title += " *(download address not yet confirmed: the host was unreachable)*"
            account = d.needs_key or "none"
            lines.append(
                f"| {title} | {d.provider} | {_size(d.size_bytes)} | `{d.dest}` | "
                f"{d.used_for} | {account} |"
            )
        lines.append("")
    lines.append(README_END)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


README_PATH = Path(__file__).resolve().parents[3] / "README.md"


def readme_block(text: str) -> str:
    """The generated block as it currently stands in ``text``."""
    start = text.index(README_BEGIN)
    end = text.index(README_END) + len(README_END)
    return text[start:end]


def write_readme(path: Path = README_PATH) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(readme_block(text), readme_table()), encoding="utf-8")


def _list() -> int:
    for d in DATASETS:
        state = is_present(d)
        mark = {True: "present", False: "missing", None: "database"}[state]
        print(f"{mark:9} {d.tier:10} {d.id:36} {_size(d.size_bytes):>7}  {d.dest}")
    return EXIT_OK


def _commit() -> str | None:
    head = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=README_PATH.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return head.stdout.strip() or None


def _export(out: Path) -> int:
    s = get_settings()
    files = share.shareable(s.data_dir, README_PATH.parent)
    if not files:
        log.error("Nothing to export: data/ holds no downloaded files yet (run `polar-data sync`).")
        return EXIT_FAILED
    log.info("Checking and copying %d files from %s to %s ...", len(files), s.data_dir, out)
    done = share.export(s.data_dir, out, files, commit=_commit())
    log.info(
        "Exported %d files (%s): %d copied, %d unchanged since the last export.",
        done.files,
        _size(done.total_bytes),
        len(done.copied),
        done.present,
    )
    log.info("Share %s (for example in a Google Drive folder). To use it on another machine:", out)
    log.info("  python3 run.py --data-from <that folder, the .zip, or the .zip parts Drive gives>")
    return EXIT_OK


def _import(sources: list[Path]) -> tuple[int, bool]:
    """Exit code and whether data the running API loads at start-up arrived."""
    s = get_settings()
    try:
        done = share.import_(sources, s.data_dir)
    except (share.ShareError, OSError) as exc:
        log.error("Shared copy not used: %s", exc)
        return EXIT_FAILED, False
    if any(p.startswith("kernels/") for p in done.copied):
        kernel_mod.write_metakernel(s.kernel_dir, kernel_mod.loadable(s.kernel_dir))
    log.info(
        "Shared copy: %d of %d files copied in, %d already here, %d not in what was given.",
        len(done.copied),
        done.files,
        done.present,
        len(done.missing),
    )
    for rel in done.kept[:10]:
        log.info("  kept yours (it differs from the shared copy): %s", rel)
    for rel in done.bad[:10]:
        log.warning("  damaged in the shared copy, not used (it will be downloaded): %s", rel)
    if len(done.bad) > 10:
        log.warning("  ... and %d more damaged files", len(done.bad) - 10)
    changed = any(p.startswith(("kernels/", "dem/", "tiles/")) for p in done.copied)
    return (EXIT_FAILED if done.bad else EXIT_OK), changed


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="polar-data", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("sync", help="download and build what is missing")
    sp.add_argument(
        "--tier",
        action="append",
        choices=TIERS,
        help="repeatable; default core, lifecycle and validation",
    )
    sp.add_argument(
        "--from",
        dest="sources",
        type=Path,
        nargs="+",
        metavar="PATH",
        help="first copy in a shared copy made by `polar-data export`",
    )
    ep = sub.add_parser("export", help="copy what is on disk to a folder or a .zip, to share it")
    ep.add_argument("path", type=Path, help="a folder, or a file name ending in .zip")
    ip = sub.add_parser("import", help="bring in a copy made by `polar-data export`")
    ip.add_argument(
        "paths", type=Path, nargs="+", help="the folder, the .zip, or the parts Drive downloaded"
    )
    sub.add_parser("list", help="show what is on disk")
    rp = sub.add_parser("readme", help="print the README table")
    rp.add_argument("--write", action="store_true", help="rewrite the table in README.md")
    args = p.parse_args(argv)

    if args.cmd == "list":
        raise SystemExit(_list())
    if args.cmd == "readme":
        if args.write:
            write_readme()
        else:
            print(readme_table())
        raise SystemExit(EXIT_OK)

    if args.cmd == "export":
        raise SystemExit(_export(args.path.expanduser()))
    if args.cmd == "import":
        code, changed = _import([p.expanduser() for p in args.paths])
        raise SystemExit(EXIT_RESTART if code == EXIT_OK and changed else code)

    imported = False
    if args.sources:
        imported = _import([p.expanduser() for p in args.sources])[1]
    tiers: tuple[Tier, ...] = tuple(args.tier or ("core", "lifecycle", "validation"))
    outcomes = sync(tiers)
    failed = [o for o in outcomes if o.status == "failed"]
    skipped = [o for o in outcomes if o.status == "skipped"]
    log.info(
        "data: %d present, %d fetched or built, %d skipped, %d failed",
        sum(o.status == "present" for o in outcomes),
        sum(o.status in ("fetched", "built") for o in outcomes),
        len(skipped),
        len(failed),
    )
    for o in skipped + failed:
        log.info("  %s %s: %s", o.status, o.dataset, o.detail)
    if failed:
        raise SystemExit(EXIT_FAILED)
    if imported or any(o.changed_api_data for o in outcomes):
        raise SystemExit(EXIT_RESTART)
    raise SystemExit(EXIT_OK)


if __name__ == "__main__":
    main()
