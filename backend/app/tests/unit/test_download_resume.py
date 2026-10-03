"""Tests for resumable download verification and integrity checks (H1.5)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from app.data.download import Target, fetch


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.data.download.time.sleep", lambda _: None)


def test_resume_with_matching_validator_appends_206(tmp_path: Path) -> None:
    dest = tmp_path / "test.dat"
    part = tmp_path / "test.dat.part"
    meta = tmp_path / "test.dat.part.meta"
    part.write_bytes(b"0123")
    meta.write_text('{"validator": "\\"v1\\""}')

    url = "https://example.test/test.dat"
    target = Target(urls=(url,), dest=dest, min_bytes=5)

    with respx.mock(assert_all_called=True) as rx:
        rx.get(url, headers={"Range": "bytes=4-", "If-Range": '"v1"'}).mock(
            return_value=httpx.Response(
                206,
                headers={
                    "Content-Range": "bytes 4-9/10",
                    "Content-Length": "6",
                    "ETag": '"v1"',
                },
                content=b"456789",
            )
        )
        fetch(target)

    assert dest.read_bytes() == b"0123456789"
    assert not part.exists()
    assert not meta.exists()


def test_resume_when_validator_changed_rewrites_from_zero(tmp_path: Path) -> None:
    dest = tmp_path / "test.dat"
    part = tmp_path / "test.dat.part"
    meta = tmp_path / "test.dat.part.meta"
    part.write_bytes(b"0123-OLD-DATA")
    meta.write_text('{"validator": "\\"v1\\""}')

    url = "https://example.test/test.dat"
    target = Target(urls=(url,), dest=dest, min_bytes=5)

    with respx.mock(assert_all_called=True) as rx:
        rx.get(url, headers={"Range": "bytes=13-", "If-Range": '"v1"'}).mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Length": "10", "ETag": '"v2"'},
                content=b"0123456789",
            )
        )
        fetch(target)

    assert dest.read_bytes() == b"0123456789"
    assert not part.exists()
    assert not meta.exists()


def test_resume_with_wrong_content_range_start_restarts(tmp_path: Path) -> None:
    dest = tmp_path / "test.dat"
    part = tmp_path / "test.dat.part"
    meta = tmp_path / "test.dat.part.meta"
    part.write_bytes(b"0123")
    meta.write_text('{"validator": "\\"v1\\""}')

    url = "https://example.test/test.dat"
    target = Target(urls=(url,), dest=dest, min_bytes=5)

    with respx.mock(assert_all_called=True) as rx:
        # First attempt: returns 206 with mismatched start (0 instead of 4)
        rx.get(url, headers={"Range": "bytes=4-", "If-Range": '"v1"'}).mock(
            return_value=httpx.Response(
                206,
                headers={"Content-Range": "bytes 0-9/10", "Content-Length": "10"},
                content=b"0123456789",
            )
        )
        # Second attempt: restarted clean without Range header
        rx.get(url).mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Length": "10", "ETag": '"v1"'},
                content=b"0123456789",
            )
        )
        fetch(target)

    assert dest.read_bytes() == b"0123456789"
    assert not part.exists()
    assert not meta.exists()


def test_416_with_part_longer_than_remote_is_restarted_not_accepted(tmp_path: Path) -> None:
    dest = tmp_path / "test.dat"
    part = tmp_path / "test.dat.part"
    meta = tmp_path / "test.dat.part.meta"
    # Held part has 20 bytes, but remote file is only 10 bytes
    part.write_bytes(b"01234567890123456789")
    meta.write_text('{"validator": "\\"v1\\""}')

    url = "https://example.test/test.dat"
    target = Target(urls=(url,), dest=dest, min_bytes=5)

    with respx.mock(assert_all_called=True) as rx:
        # First attempt: GET Range 20- -> 416
        rx.get(url, headers={"Range": "bytes=20-", "If-Range": '"v1"'}).mock(
            return_value=httpx.Response(416)
        )
        # HEAD probe returns Content-Length 10
        rx.head(url).mock(return_value=httpx.Response(200, headers={"Content-Length": "10"}))
        # Second attempt: restarted clean
        rx.get(url).mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Length": "10", "ETag": '"v1"'},
                content=b"0123456789",
            )
        )
        fetch(target)

    assert dest.read_bytes() == b"0123456789"
    assert len(dest.read_bytes()) == 10
    assert not part.exists()
    assert not meta.exists()


def test_416_with_exact_length_is_accepted(tmp_path: Path) -> None:
    dest = tmp_path / "test.dat"
    part = tmp_path / "test.dat.part"
    meta = tmp_path / "test.dat.part.meta"
    part.write_bytes(b"0123456789")
    meta.write_text('{"validator": "\\"v1\\""}')

    url = "https://example.test/test.dat"
    target = Target(urls=(url,), dest=dest, min_bytes=5)

    with respx.mock(assert_all_called=True) as rx:
        rx.get(url, headers={"Range": "bytes=10-", "If-Range": '"v1"'}).mock(
            return_value=httpx.Response(416)
        )
        rx.head(url).mock(return_value=httpx.Response(200, headers={"Content-Length": "10"}))
        fetch(target)

    assert dest.read_bytes() == b"0123456789"
    assert not part.exists()
    assert not meta.exists()
