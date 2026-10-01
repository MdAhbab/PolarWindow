"""The dataset registry: one list behind run.py, the README table and provenance."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.kernels import ALL_KERNELS
from app.data import registry, sync


def test_ids_are_unique() -> None:
    ids = [d.id for d in registry.DATASETS]
    assert len(ids) == len(set(ids))


def test_every_kernel_is_registered_once() -> None:
    names = {d.dest.split("/", 1)[1] for d in registry.DATASETS if d.method == "kernel"}
    assert names == {k.name for k in ALL_KERNELS}


def test_downloadable_datasets_have_an_address() -> None:
    for d in registry.DATASETS:
        if d.method in ("file", "cmr", "kernel", "lola_regional", "lola_fine", "lola_rover"):
            assert d.urls, d.id
            assert all(u.startswith("https://") for u in d.urls), d.id
        if d.method == "cmr":
            assert d.cmr_collection and d.needs_key, d.id
        if d.method == "s3_prefix":
            assert d.s3_prefix and d.s3_suffix, d.id
        if d.method == "built":
            assert d.build and d.urls, d.id


def test_a_single_file_download_goes_to_a_file() -> None:
    """A folder or a pattern cannot be one download: such data is ``built`` or listed."""
    for d in registry.DATASETS:
        if d.method in ("file", "kernel"):
            assert not d.dest.endswith("/") and "*" not in d.dest, d.id


def test_catalogue_links_point_at_data_nasa_gov() -> None:
    for d in registry.DATASETS:
        if d.catalogue:
            assert d.catalogue.startswith("https://data.nasa.gov/dataset/"), d.id


def test_every_dataset_says_what_it_is_for() -> None:
    for d in registry.DATASETS:
        assert len(d.used_for) > 20, d.id


def test_readme_table_matches_the_registry() -> None:
    """Regenerate with `uv run polar-data readme --write` when this fails."""
    text = sync.README_PATH.read_text(encoding="utf-8")
    assert sync.readme_block(text) == sync.readme_table()


def test_built_data_is_found_by_its_pattern_and_never_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    asos = registry.by_id("iem:asos-archive")
    assert sync._sync_built(asos).status == "skipped"
    (tmp_path / "hindcast").mkdir()
    (tmp_path / "hindcast/asos_XMR_2021_2025.csv").write_text("station,valid,sknt\n")
    assert sync._sync_built(asos).status == "present"
