"""The dataset registry: one list behind run.py, the README table and provenance."""

from __future__ import annotations

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
        if d.method in ("file", "cmr", "kernel", "lola_regional", "lola_fine"):
            assert d.urls, d.id
            assert all(u.startswith("https://") for u in d.urls), d.id
        if d.method == "cmr":
            assert d.cmr_collection and d.needs_key, d.id
        if d.method == "s3_prefix":
            assert d.s3_prefix and d.s3_suffix, d.id


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
