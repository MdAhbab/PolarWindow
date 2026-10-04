from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import types

ROOT_DIR = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def pw_run() -> types.ModuleType:
    import sys

    spec = importlib.util.spec_from_file_location("pw_run", ROOT_DIR / "run.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pw_run"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_database_from_env_default(pw_run: types.ModuleType) -> None:
    db = pw_run.Database.from_env({})
    assert db.host == "localhost"
    assert db.port == 5432
    assert db.name == "polar_window"
    assert db.user == "postgres"


def test_database_from_env_custom_query_params(pw_run: types.ModuleType) -> None:
    env = {
        "PW_DATABASE_URL": "postgresql+asyncpg://postgres:secret@/polar_window?host=/tmp&port=5433"
    }
    db = pw_run.Database.from_env(env)
    assert db.host == "/tmp"  # noqa: S108
    assert db.port == 5433
    assert db.name == "polar_window"
    assert db.user == "postgres"
    assert db.password == "secret"


def test_read_env_quoting_and_comments(
    pw_run: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_env = tmp_path / ".env"
    fake_env.write_text(
        """
        # A comment line
        export PW_FOO=bar # inline comment
        PW_SINGLE='quoted value'
        PW_DOUBLE="double quoted # value"
        INVALID_LINE_NO_EQUALS
        EMPTY_VAL=
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(pw_run, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(pw_run, "BE_DIR", tmp_path / "backend")
    env = pw_run.read_env()
    assert env["PW_FOO"] == "bar"
    assert env["PW_SINGLE"] == "quoted value"
    assert env["PW_DOUBLE"] == "double quoted # value"
    assert env["EMPTY_VAL"] == ""


def test_pid_file_round_trip(
    pw_run: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pids_file = tmp_path / "run.pids"
    monkeypatch.setattr(pw_run, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(pw_run, "RUN_PIDS_FILE", pids_file)

    assert pw_run.load_run_pids() == {}

    data = {
        "backend": {"pid": 12345, "pgid": 12345, "cmd": "uv run uvicorn app.main:app --port 8000"}
    }
    pw_run.save_run_pids(data)
    assert pids_file.is_file()
    assert pw_run.load_run_pids() == data

    pw_run.save_run_pids({})
    assert not pids_file.exists()


def test_recorded_pid_with_changed_command_is_not_signalled(
    pw_run: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pids_file = tmp_path / "run.pids"
    pids_file.write_text(
        json.dumps(
            {
                "backend": {
                    "pid": 99999,
                    "pgid": 99999,
                    "cmd": "uv run uvicorn app.main:app --port 8000",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pw_run, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(pw_run, "RUN_PIDS_FILE", pids_file)

    signalled: list[int] = []

    def fake_kill(pid: int, sig: int) -> None:
        if sig == 0:
            return
        signalled.append(pid)

    monkeypatch.setattr("os.kill", fake_kill)
    monkeypatch.setattr(pw_run, "get_process_cmdline", lambda pid: "python some_other_app.py")
    monkeypatch.setattr(pw_run, "get_pids_on_port", lambda port: [])
    monkeypatch.setattr(pw_run, "get_matching_pids", lambda pat: [])
    monkeypatch.setattr(pw_run, "is_port_open", lambda port: False)

    pw_run.stop_previous_instances(be_port=8000, fe_port=5173)

    assert 99999 not in signalled


def test_fallback_refuses_foreign_cwd(
    pw_run: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pw_run, "RUN_PIDS_FILE", tmp_path / "nonexistent.pids")
    monkeypatch.setattr(pw_run, "LOCAL_DIR", tmp_path)

    monkeypatch.setattr(pw_run, "get_pids_on_port", lambda port: [8888] if port == 5173 else [])
    monkeypatch.setattr(pw_run, "get_matching_pids", lambda pat: [])
    monkeypatch.setattr(pw_run, "get_process_cmdline", lambda pid: "foreign_vite")
    monkeypatch.setattr(pw_run, "get_process_cwd", lambda pid: Path("/other/project"))
    monkeypatch.setattr(pw_run, "is_port_open", lambda port: False)

    signalled: list[int] = []
    monkeypatch.setattr("os.kill", lambda pid, sig: signalled.append(pid))

    with pytest.raises(SystemExit) as exc_info:
        pw_run.stop_previous_instances(be_port=8000, fe_port=5173)

    assert exc_info.value.code == 1
    assert 8888 not in signalled


def test_shutdown_raises_system_exit(
    pw_run: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pw_run, "RUN_PIDS_FILE", tmp_path / "run.pids")
    monkeypatch.setattr(pw_run, "LOCAL_DIR", tmp_path)

    stack = pw_run.Stack(be_port=8000, fe_port=5173)
    with pytest.raises(SystemExit) as exc_info:
        stack.shutdown(1)

    assert exc_info.value.code == 1
