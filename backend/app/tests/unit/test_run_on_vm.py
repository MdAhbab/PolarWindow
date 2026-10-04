"""run_onVM.py: what it would run on a server, checked without a server.

Docker is not needed here: the script's dry run prints every command instead of
running it, and the settings it hands to docker compose are plain values.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import types

ROOT_DIR = Path(__file__).resolve().parents[4]
SCRIPT = ROOT_DIR / "run_onVM.py"


@pytest.fixture(scope="module")
def vm() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("pw_run_on_vm", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pw_run_on_vm"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_only_the_dashboard_is_open_to_the_outside(vm: types.ModuleType) -> None:
    env = vm.stack_env(8080)
    assert env["PW_WEB_PORT"] == "8080"
    assert env["PW_BIND_ADDR"] == "127.0.0.1"
    # nginx names the visitor itself (frontend/nginx.conf), so the api may believe it.
    assert env["PW_FORWARDED_ALLOW_IPS"] == "*"


def test_every_compose_call_names_the_project_and_the_web_profile(
    vm: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vm, "_docker", ["docker"])
    cmd = vm.compose("up", "--detach")
    assert cmd[:6] == ["docker", "compose", "--project-name", "polar-window", "--profile", "web"]
    assert cmd[-2:] == ["up", "--detach"]


def test_the_compose_file_has_what_the_script_relies_on() -> None:
    text = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    assert "profiles: ['web']" in text
    assert "${PW_WEB_PORT:-80}:80" in text
    for port in ("5432:5432", "6379:6379", "8000:8000"):
        assert f"${{PW_BIND_ADDR:-0.0.0.0}}:{port}" in text
    assert "FORWARDED_ALLOW_IPS: ${PW_FORWARDED_ALLOW_IPS:-127.0.0.1}" in text
    nginx = (ROOT_DIR / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    # Set, not appended: a visitor cannot forge the address the api counts limits by.
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "proxy_add_x_forwarded_for" not in nginx


def test_a_dry_run_prints_the_steps_in_order_and_runs_nothing(tmp_path: Path) -> None:
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--dry-run", "--port", "8080", "--keep-cache"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    steps = [
        "down --remove-orphans",
        "container prune --force",
        "image prune --force",
        "build --pull api web",
        "run --rm data",
        "up --detach --remove-orphans",
    ]
    positions = [out.find(s) for s in steps]
    assert all(p >= 0 for p in positions), dict(zip(steps, positions, strict=True))
    assert positions == sorted(positions)
    # --keep-cache: the build cache and the old images are left alone.
    assert "builder prune" not in out
    assert "--no-cache" not in out
    assert "Nothing was run." in out


def test_the_signing_secret_is_added_once_and_never_printed(
    vm: types.ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PW_ENV=dev\n", encoding="utf-8")
    monkeypatch.setattr(vm, "ENV_FILE", env_file)
    monkeypatch.setattr(vm, "DRY", False)
    vm.ensure_env()
    first = vm.read_env_keys()["PW_JWT_SECRET"]
    assert len(first) >= 32
    assert first not in capsys.readouterr().out
    vm.ensure_env()
    assert vm.read_env_keys()["PW_JWT_SECRET"] == first
    assert env_file.read_text(encoding="utf-8").count("PW_JWT_SECRET=") == 1
