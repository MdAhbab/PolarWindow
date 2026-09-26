"""Per-engine versions (ADR-13): the surface keys never move; lifecycle keys name their closure."""

from __future__ import annotations

import pytest

from app.config import ENGINE_VERSION, ENGINES, engine_closure
from app.services import cache


def test_surface_version_is_the_pair_of_surface_engines() -> None:
    assert f"{ENGINES['hz']}/{ENGINES['vis']}" == ENGINE_VERSION


def test_closure_is_order_free_and_deduplicated() -> None:
    assert engine_closure("vis", "traj") == engine_closure("traj", "vis", "traj")


def test_unknown_engine_is_an_error() -> None:
    with pytest.raises(KeyError):
        engine_closure("warp")


def test_lifecycle_key_changes_with_closure_and_parts() -> None:
    a = cache.make_lifecycle_key("contact", engine_closure("vis", "net"), site="x")
    b = cache.make_lifecycle_key("contact", engine_closure("vis", "net", "link"), site="x")
    c = cache.make_lifecycle_key("contact", engine_closure("vis", "net"), site="y")
    assert len({a, b, c}) == 3
    assert a.startswith("pw:net-1+vis-2:")


def test_surface_key_format_is_unchanged() -> None:
    assert cache.make_key("metrics", site="x").startswith(f"pw:{ENGINE_VERSION}:")
