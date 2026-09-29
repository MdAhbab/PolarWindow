"""Passing the downloaded data on without the internet: ``polar-data export`` and ``import``."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.data import share


def _data(root: Path) -> list[str]:
    files = {
        "kernels/de440.bsp": b"\x00spk" * 1000,
        "dem/fine/site-1.npz": b"npz" * 300,
        "hindcast/gefs_reforecast_wind.cache.jsonl": b'{"a": 1}\n' * 50,
        "tiles/3/1/2.png": b"png",
    }
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(body)
    return sorted(files)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True)  # noqa: S603, S607 -- a throwaway repository


def _same(a: Path, b: Path, files: list[str]) -> bool:
    return all((a / f).read_bytes() == (b / f).read_bytes() for f in files)


@pytest.mark.parametrize("name", ["copy", "copy.zip"])
def test_an_export_comes_back_whole(tmp_path: Path, name: str) -> None:
    src, dst = tmp_path / "a", tmp_path / "b"
    files = _data(src)
    done = share.export(src, tmp_path / name, files, commit="abc")
    assert sorted(done.copied) == files
    back = share.import_([tmp_path / name], dst)
    assert sorted(back.copied) == files
    assert not (back.bad or back.missing or back.kept)
    assert _same(src, dst, files)
    again = share.import_([tmp_path / name], dst)
    assert again.present == len(files) and not again.copied


def test_a_second_export_into_the_same_folder_copies_only_what_changed(tmp_path: Path) -> None:
    src = tmp_path / "a"
    files = _data(src)
    share.export(src, tmp_path / "copy", files)
    (src / "tiles/3/1/2.png").write_bytes(b"new png")
    done = share.export(src, tmp_path / "copy", files)
    assert done.copied == ["tiles/3/1/2.png"]
    assert done.present == len(files) - 1


def test_drive_parts_with_the_folder_name_in_front_are_read_together(tmp_path: Path) -> None:
    """Drive splits a big folder into several zips; only one of them holds MANIFEST.json."""
    src, dst, downloads = tmp_path / "a", tmp_path / "b", tmp_path / "Downloads"
    files = _data(src)
    folder = tmp_path / "polar-window-data"
    share.export(src, folder, files)
    downloads.mkdir()
    names = [*files, share.MANIFEST]
    for i, part in enumerate((names[:2], names[2:]), start=1):
        with zipfile.ZipFile(downloads / f"polar-window-data-20260930T0000Z-00{i}.zip", "w") as z:
            for rel in part:
                z.write(folder / rel, arcname=f"polar-window-data/{rel}")
    done = share.import_([downloads], dst)
    assert sorted(done.copied) == files
    assert _same(src, dst, files)


def test_a_damaged_file_is_not_used(tmp_path: Path) -> None:
    src, dst = tmp_path / "a", tmp_path / "b"
    files = _data(src)
    share.export(src, tmp_path / "copy", files)
    (tmp_path / "copy/kernels/de440.bsp").write_bytes(b"cut short")
    done = share.import_([tmp_path / "copy"], dst)
    assert done.bad == ["kernels/de440.bsp"]
    assert not (dst / "kernels/de440.bsp").exists()
    assert not list(dst.rglob("*.import-part"))


def test_a_file_already_here_is_never_replaced(tmp_path: Path) -> None:
    src, dst = tmp_path / "a", tmp_path / "b"
    files = _data(src)
    share.export(src, tmp_path / "copy", files)
    (dst / "kernels").mkdir(parents=True)
    (dst / "kernels/de440.bsp").write_bytes(b"mine")
    done = share.import_([tmp_path / "copy"], dst)
    assert done.kept == ["kernels/de440.bsp"]
    assert (dst / "kernels/de440.bsp").read_bytes() == b"mine"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "a/../../x", "c:/x", "a\\b"])
def test_a_manifest_cannot_write_outside_data(tmp_path: Path, path: str) -> None:
    copy = tmp_path / "copy"
    copy.mkdir()
    row = {"path": path, "size": 1, "sha256": "0" * 64}
    (copy / share.MANIFEST).write_text(json.dumps({"format": 1, "files": [row]}))
    with pytest.raises(share.ShareError, match="outside data/"):
        share.import_([copy], tmp_path / "data")
    assert not (tmp_path / "outside.txt").exists()


def test_a_copy_without_a_manifest_is_refused(tmp_path: Path) -> None:
    (tmp_path / "loose").mkdir()
    (tmp_path / "loose/de440.bsp").write_bytes(b"x")
    with pytest.raises(share.ShareError, match="MANIFEST.json"):
        share.import_([tmp_path / "loose"], tmp_path / "data")


def test_a_copy_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    (tmp_path / "copy").mkdir()
    (tmp_path / "copy" / share.MANIFEST).write_text(json.dumps({"format": 2, "files": []}))
    with pytest.raises(share.ShareError, match="newer"):
        share.import_([tmp_path / "copy"], tmp_path / "data")


def test_what_is_never_shared() -> None:
    assert not share.keep(".sync-state.json")
    assert not share.keep("kernels/polar-window.tm")
    assert not share.keep("kernels/de440.bsp.part")
    assert not share.keep("kernels/orbiters/lro-12-0123456789ab.bsp")
    assert share.keep("kernels/de440.bsp")
    assert share.keep("tiles/3/1/2.png")


def test_only_what_git_ignores_is_exported(tmp_path: Path) -> None:
    """Tracked files travel with the repository; files neither tracked nor ignored are drafts."""
    repo = tmp_path / "repo"
    data = repo / "data"
    (data / "kernels").mkdir(parents=True)
    (repo / ".gitignore").write_text("data/kernels/\n")
    (data / "kernels/de440.bsp").write_bytes(b"spk")
    (data / "kernels/polar-window.tm").write_text("kernel list")
    (data / "missions.json").write_text("{}")
    (data / "draft.json").write_text("{}")
    _git(repo, "init", "-q")
    _git(repo, "add", ".gitignore", "data/missions.json")
    assert share.shareable(data, repo) == ["kernels/de440.bsp"]
