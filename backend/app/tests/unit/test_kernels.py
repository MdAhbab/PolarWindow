"""Kernel verification: the failure messages are part of the product.

A missing or truncated kernel is the most common way this project breaks, so
the message it raises is asserted on as a string: it must name the file, where
it came from, and the command that fixes it. A truncated SPK is worse than a
missing one -- it can furnsh and then return wrong vectors -- so it must be
refused before use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.kernels import KernelError, KernelSpec, missing, verify, verify_all


def spec(**overrides: object) -> KernelSpec:
    base: dict[str, object] = {
        "name": "de440.bsp",
        "url": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp",
        "kind": "SPK",
        "min_bytes": 1_000,
        "why": "Planetary ephemeris.",
    }
    base.update(overrides)
    return KernelSpec(**base)  # type: ignore[arg-type]


def test_missing_kernel_names_the_file_the_url_and_the_fix(tmp_path: Path) -> None:
    with pytest.raises(KernelError) as err:
        verify(spec(), tmp_path)
    text = str(err.value)
    assert "de440.bsp" in text
    assert "naif.jpl.nasa.gov" in text
    assert "make kernels" in text


def test_truncated_kernel_is_refused_before_use(tmp_path: Path) -> None:
    (tmp_path / "de440.bsp").write_bytes(b"\0" * 10)
    with pytest.raises(KernelError, match="truncated"):
        verify(spec(), tmp_path)


def test_checksum_mismatch_is_refused(tmp_path: Path) -> None:
    (tmp_path / "de440.bsp").write_bytes(b"\0" * 2_000)
    with pytest.raises(KernelError, match="checksum"):
        verify(spec(sha256="0" * 64), tmp_path)


def test_every_problem_is_reported_at_once(tmp_path: Path) -> None:
    """Five missing kernels are one round trip, not five."""
    specs = [spec(name=f"k{i}.bsp") for i in range(3)]
    with pytest.raises(KernelError) as err:
        verify_all(tmp_path, specs)
    assert "3 of 3" in str(err.value)
    assert missing(tmp_path, specs) == ["k0.bsp", "k1.bsp", "k2.bsp"]
