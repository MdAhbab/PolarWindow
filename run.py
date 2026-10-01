#!/usr/bin/env python3
"""POLAR WINDOW - Unified runner and environment manager.

Stops previous instances of frontend and backend, starts required local services
(Postgres and Redis; on a machine that has never run the app it creates a local
database in .local/pgdata), installs all backend & frontend dependencies, and runs
FastAPI (backend), the compute and feeds workers and Vite (frontend) together.
Once both answer, it downloads every dataset the app uses that is not already on
disk (SPICE kernels, LOLA terrain, GRAIL gravity, flown CLPS trajectories and the
rest; the list is backend/app/data/registry.py and the README's "Required data"
section), then restarts the backend if the new data is something it loads at
start-up.

The data can also travel without the internet (NASA's archive servers can send
30 kB/s): on a machine that has it,

    python3 run.py --export-data ~/polar-window-data.zip    (or a folder)

and on another, before anything is downloaded,

    python3 run.py --data-from ~/Downloads/polar-window-data.zip

--data-from takes a folder, a .zip, or the several .zip parts Google Drive gives
for a large folder. Every file is checked against the SHA-256 the export listed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

# Base Paths
ROOT_DIR = Path(__file__).resolve().parent
BE_DIR = ROOT_DIR / "backend"
#: Compute worker processes (each works out one job at a time).
COMPUTE_WORKERS = int(os.environ.get("POLAR_COMPUTE_WORKERS", "2"))
FE_DIR = ROOT_DIR / "frontend"
LOCAL_DIR = ROOT_DIR / ".local"
PGDATA_DIR = LOCAL_DIR / "pgdata"
PGLOG_FILE = LOCAL_DIR / "pg.log"
REDIS_DIR = LOCAL_DIR / "redis"


def configure_local_storage() -> None:
    """Keep downloads, interpreter installs and temporary files beside the project."""
    paths = {
        "TEMP": LOCAL_DIR / "tmp",
        "TMP": LOCAL_DIR / "tmp",
        "UV_CACHE_DIR": LOCAL_DIR / "cache" / "uv",
        "UV_PYTHON_INSTALL_DIR": LOCAL_DIR / "python",
        "UV_PYTHON_BIN_DIR": LOCAL_DIR / "tools",
        "npm_config_cache": LOCAL_DIR / "cache" / "npm",
        "MPLCONFIGDIR": LOCAL_DIR / "cache" / "matplotlib",
        "NUMBA_CACHE_DIR": LOCAL_DIR / "cache" / "numba",
        "XDG_CACHE_HOME": LOCAL_DIR / "cache",
        "SPACEPY": LOCAL_DIR / "cache" / "spacepy",
    }
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ["UV_PYTHON_INSTALL_REGISTRY"] = "false"
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if os.name == "nt":
        tools = LOCAL_DIR / "tools"
        bins = [tools / "pgsql" / "bin", *sorted(tools.glob("node-v*-win-x64"), reverse=True)]
        local_path = os.pathsep.join(str(p) for p in bins if p.is_dir())
        os.environ["PATH"] = local_path + os.pathsep + os.environ.get("PATH", "")


def npm_command() -> str:
    """Windows exposes npm through a .cmd launcher."""
    return shutil.which("npm.cmd" if os.name == "nt" else "npm") or "npm"


# Ensure standard user & homebrew bin directories are in PATH
EXTRA_PATHS = [
    str(Path.home() / ".local" / "bin"),
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
]
for p in EXTRA_PATHS:
    if os.path.isdir(p) and p not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

# PostgreSQL's server programs (initdb, pg_ctl) are often not on PATH: Homebrew's
# postgresql@16 is keg-only and Debian keeps them under /usr/lib/postgresql. They go
# last, newest first, so a PostgreSQL already on PATH is still the one used.
for pattern in ("opt/homebrew/opt/postgresql@*/bin", "usr/local/opt/postgresql@*/bin",
                "usr/lib/postgresql/*/bin"):
    for p in sorted((str(d) for d in Path("/").glob(pattern)), reverse=True):
        if p not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + p

#: The backend's own defaults (backend/app/config.py), used when .env does not set them.
DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/polar_window"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"

HOW_TO_INSTALL = {
    "uv": "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh",
    "npm": "Install Node.js 20 or newer (it brings npm): https://nodejs.org, or `brew install node`.",
    "postgres": "Install PostgreSQL 16 (`brew install postgresql@16` on macOS, "
    "`sudo apt install postgresql` on Debian or Ubuntu), or start the database with "
    "`docker compose up -d postgres redis`, then run this again.",
    "redis": "Install Redis (`brew install redis` or `sudo apt install redis-server`), or set "
    "PW_REDIS_ENABLED=false in .env: Redis only caches answers, the app works without it.",
}

# ANSI Color Codes
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(prefix: str, color: str, msg: str) -> None:
    print(f"{color}{BOLD}[{prefix}]{RESET} {msg}", flush=True)


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


def is_unix_socket_open(socket_path: str) -> bool:
    if not os.path.exists(socket_path):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.8)
        s.connect(socket_path)
        s.close()
        return True
    except OSError:
        return False


def get_pids_on_port(port: int) -> list[int]:
    """Return list of PIDs listening on a specific port using lsof."""
    if os.name == "nt":
        res = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False
        )
        return list({
            int(parts[-1]) for line in res.stdout.splitlines()
            if len(parts := line.split()) == 5 and parts[3] == "LISTENING"
            and parts[1].rsplit(":", 1)[-1] == str(port)
        })
    try:
        res = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            pids: list[int] = []
            for line in res.stdout.strip().splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
            return pids
    except FileNotFoundError:
        pass
    return []


def get_matching_pids(pattern: str) -> list[int]:
    """Find PIDs matching a command line pattern via pgrep."""
    try:
        res = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            my_pid = os.getpid()
            pids: list[int] = []
            for line in res.stdout.strip().splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid != my_pid:
                        pids.append(pid)
            return pids
    except FileNotFoundError:
        pass
    return []


def stop_pids(pids: set[int], desc: str) -> None:
    """Terminate and if needed kill a set of PIDs."""
    if not pids:
        return
    log("CLEANUP", YELLOW, f"Stopping previous {desc} processes: {sorted(pids)}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as err:
            log("CLEANUP", RED, f"Permission denied stopping PID {pid}: {err}")

    # Wait up to 2.5 seconds for graceful shutdown
    deadline = time.time() + 2.5
    remaining = set(pids)
    while time.time() < deadline and remaining:
        time.sleep(0.1)
        for pid in list(remaining):
            try:
                # 0 signal checks if process is alive
                os.kill(pid, 0)
            except ProcessLookupError:
                remaining.remove(pid)

    # Force kill any stubborn remnants
    for pid in remaining:
        try:
            log("CLEANUP", RED, f"Force killing PID {pid}")
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def stop_previous_instances(be_port: int = 8000, fe_port: int = 5173) -> None:
    """Find and stop any running backend and frontend processes."""
    log("CLEANUP", YELLOW, "Checking for previous instances...")

    # Port listeners
    port_pids: set[int] = set()
    port_pids.update(get_pids_on_port(be_port))
    port_pids.update(get_pids_on_port(fe_port))

    # Pattern matches
    pattern_pids: set[int] = set()
    pattern_pids.update(get_matching_pids("uvicorn app.main:app"))
    pattern_pids.update(get_matching_pids("app.workers.compute"))
    pattern_pids.update(get_matching_pids("app.workers.feeds"))
    pattern_pids.update(get_matching_pids("vite"))

    all_pids = port_pids | pattern_pids
    if all_pids:
        stop_pids(all_pids, "frontend/backend")
    else:
        log("CLEANUP", GREEN, "No previous instances found.")

    # Ensure ports are actually free
    for port in (be_port, fe_port):
        start_wait = time.time()
        while is_port_open(port):
            time.sleep(0.2)
            if time.time() - start_wait > 3.0:
                log("CLEANUP", RED, f"Warning: Port {port} still appears occupied.")
                break


def read_env() -> dict[str, str]:
    """The PW_* settings the backend will see: .env files, then the environment (it wins).

    A small reader, because this runs before the backend's own dependencies exist. Same order
    as backend/app/config.py: the repository's .env, then backend/.env (the backend's folder).
    """
    values: dict[str, str] = {}
    for path in (ROOT_DIR / ".env", BE_DIR / ".env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.removeprefix("export ").strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].strip()
            values[key] = value
    values.update({k: v for k, v in os.environ.items() if k.startswith("PW_")})
    return values


@dataclass(frozen=True)
class Database:
    """Where PW_DATABASE_URL points. ``host`` is a name, or a socket folder such as /tmp."""

    host: str
    port: int
    user: str
    password: str
    name: str

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Database":
        url = urllib.parse.urlsplit(env.get("PW_DATABASE_URL") or DEFAULT_DATABASE_URL)
        query = urllib.parse.parse_qs(url.query)
        return cls(
            host=query.get("host", [url.hostname or "localhost"])[0],
            port=int(query.get("port", [str(url.port or 5432)])[0]),
            user=urllib.parse.unquote(url.username or "postgres"),
            password=urllib.parse.unquote(url.password or ""),
            name=url.path.lstrip("/") or "polar_window",
        )

    @property
    def on_this_machine(self) -> bool:
        return self.host.startswith("/") or self.host in ("localhost", "127.0.0.1", "::1")

    @property
    def where(self) -> str:
        return f"{self.host} port {self.port}"

    def answers(self) -> bool:
        if self.host.startswith("/"):
            return is_unix_socket_open(f"{self.host}/.s.PGSQL.{self.port}")
        return is_port_open(self.port, "127.0.0.1" if self.host == "localhost" else self.host)


def start_local_postgres(db: Database) -> bool:
    """Start the project's own database in .local/pgdata, creating it on the first run."""
    pg_ctl, initdb = shutil.which("pg_ctl"), shutil.which("initdb")
    if pg_ctl is None or (initdb is None and not PGDATA_DIR.exists()):
        log("SERVICES", RED, f"PostgreSQL does not answer at {db.where} and its programs "
            f"were not found. {HOW_TO_INSTALL['postgres']}")
        return False
    env = {**os.environ, "LC_ALL": "C"}
    if not PGDATA_DIR.exists():
        assert initdb is not None
        log("SERVICES", YELLOW, f"Creating this project's own PostgreSQL database in {PGDATA_DIR} "
            "(first run; it takes connections from this machine only, without a password)...")
        PGDATA_DIR.parent.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            [initdb, "-D", str(PGDATA_DIR), "-U", db.user, "--auth=trust", "-E", "UTF8",
             "--locale=C"],
            env=env, capture_output=True, text=True, check=False,
        )
        if res.returncode != 0:
            log("SERVICES", RED, f"Could not create the database: {(res.stderr or res.stdout).strip()}")
            return False
    socket_dir = db.host if db.host.startswith("/") else "/tmp"
    log("SERVICES", YELLOW, f"Starting local PostgreSQL on port {db.port}...")
    PGLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    start_log = LOCAL_DIR / "pg-start.log"
    # The server inherits pg_ctl's handles on Windows. A PIPE keeps communicate()
    # waiting for EOF even after pg_ctl exits, so use a project-local file.
    with start_log.open("w", encoding="utf-8") as output:
        res = subprocess.run(
            [pg_ctl, "-D", str(PGDATA_DIR), "-l", str(PGLOG_FILE), "-o",
             f"-p {db.port}" + (" -h 127.0.0.1" if os.name == "nt" else f" -k {socket_dir}"), "-w", "start"],
            env=env, stdout=output, stderr=subprocess.STDOUT, check=False,
        )
    if res.returncode != 0:
        log("SERVICES", RED, f"Failed to start PostgreSQL ({start_log.read_text(encoding='utf-8').strip()}); "
            f"its log is {PGLOG_FILE}.")
        return False
    log("SERVICES", GREEN, "PostgreSQL started.")
    return True


def ensure_database(db: Database) -> None:
    """Create the database named in PW_DATABASE_URL if the server does not have it yet."""
    psql, createdb = shutil.which("psql"), shutil.which("createdb")
    if psql is None or createdb is None:
        return  # cannot look; the migrations say so if it is missing
    env = {**os.environ, "LC_ALL": "C"}
    if db.password:
        env["PGPASSWORD"] = db.password
    conn = ["-h", db.host, "-p", str(db.port), "-U", db.user]
    res = subprocess.run(
        [psql, *conn, "-d", "postgres", "-Atc", "SELECT datname FROM pg_database"],
        env=env, capture_output=True, text=True, check=False, timeout=30,
    )
    if res.returncode != 0:
        log("SERVICES", RED, f"PostgreSQL answers at {db.where} but would not let user "
            f"'{db.user}' in: {res.stderr.strip()}. Set PW_DATABASE_URL in .env to a user and "
            "database that exist there, or to port 5433, where this script makes its own.")
        return
    if db.name in res.stdout.split():
        return
    made = subprocess.run([createdb, *conn, db.name], env=env, capture_output=True, text=True,
                          check=False, timeout=30)
    if made.returncode == 0:
        log("SERVICES", GREEN, f"Created the database '{db.name}'.")
    else:
        log("SERVICES", RED, f"Could not create the database '{db.name}': {made.stderr.strip()}")


def ensure_postgres(env: dict[str, str]) -> None:
    """Make sure the database in PW_DATABASE_URL answers and exists.

    One on this machine is started from .local/pgdata (created on the first run when
    PostgreSQL's programs are installed); one elsewhere is only checked.
    """
    db = Database.from_env(env)
    if db.answers():
        log("SERVICES", GREEN, f"PostgreSQL is running ({db.where}).")
    elif not db.on_this_machine:
        log("SERVICES", RED, f"PostgreSQL at {db.where} does not answer; check PW_DATABASE_URL.")
        return
    elif not start_local_postgres(db):
        return
    ensure_database(db)


def ensure_redis(env: dict[str, str]) -> None:
    """Start Redis on the port in PW_REDIS_URL if it is on this machine and not running."""
    if env.get("PW_REDIS_ENABLED", "true").strip().lower() in ("0", "false", "no", "off"):
        log("SERVICES", YELLOW, "Redis is switched off (PW_REDIS_ENABLED=false); answers are not cached.")
        return
    url = urllib.parse.urlsplit(env.get("PW_REDIS_URL") or DEFAULT_REDIS_URL)
    host, port = url.hostname or "localhost", url.port or 6379
    if is_port_open(port, "127.0.0.1" if host == "localhost" else host):
        log("SERVICES", GREEN, f"Redis is running (port {port}).")
        return
    if host not in ("localhost", "127.0.0.1", "::1"):
        log("SERVICES", RED, f"Redis at {host}:{port} does not answer; check PW_REDIS_URL.")
        return
    server = shutil.which("redis-server")
    if server is None and os.name == "nt":
        memurai = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Memurai" / "memurai.exe"
        if memurai.is_file():
            server = str(memurai)
    if server is None:
        log("SERVICES", YELLOW, f"Redis is not running and not installed. {HOW_TO_INSTALL['redis']}")
        return
    log("SERVICES", YELLOW, f"Starting local Redis on port {port}...")
    REDIS_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.Popen(
            [server, "--bind", "127.0.0.1", "--port", str(port), "--dir", str(REDIS_DIR),
             "--save", "", "--appendonly", "no", "--logfile", str(REDIS_DIR / "redis.log")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if is_port_open(port):
                log("SERVICES", GREEN, "Redis started (cache only, project-local logs).")
                return
            time.sleep(0.2)
        log("SERVICES", RED, f"Redis did not start; check {REDIS_DIR / 'redis.log'}.")
        return
    res = subprocess.run(
        [server, "--port", str(port), "--dir", str(REDIS_DIR), "--daemonize", "yes"],
        capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:
        log("SERVICES", RED, f"Failed to start Redis: {res.stderr or res.stdout}")
    else:
        log("SERVICES", GREEN, "Redis started.")


def check_tools() -> None:
    """Stop early, with the way to install it, when a program the runner needs is missing."""
    missing = [tool for tool in ("uv", "npm") if shutil.which(tool) is None]
    for tool in missing:
        log("SETUP", RED, f"`{tool}` was not found. {HOW_TO_INSTALL[tool]}")
    if missing:
        sys.exit(1)


def install_dependencies() -> None:
    """Install backend and frontend requirements."""
    log("INSTALL", YELLOW, "Installing backend dependencies with uv...")
    res_be = subprocess.run(["uv", "sync", "--extra", "dev"], cwd=BE_DIR, check=False)
    if res_be.returncode != 0:
        log("INSTALL", RED, "Backend dependency installation returned a non-zero exit code.")
        sys.exit(res_be.returncode)
    log("INSTALL", GREEN, "Backend dependencies up to date.")

    log("INSTALL", YELLOW, "Installing frontend dependencies with npm...")
    res_fe = subprocess.run([npm_command(), "ci", "--no-audit", "--no-fund"], cwd=FE_DIR, check=False)
    if res_fe.returncode != 0:
        log("INSTALL", RED, "Frontend dependency installation returned a non-zero exit code.")
        sys.exit(res_fe.returncode)
    log("INSTALL", GREEN, "Frontend dependencies up to date.")


def stream_process_output(proc: subprocess.Popen, prefix: str, color: str, stop_event: threading.Event) -> None:
    """Stream stdout/stderr of a child process with a colored prefix."""
    if proc.stdout is None:
        return
    try:
        for line in iter(proc.stdout.readline, ""):
            if stop_event.is_set() and not line:
                break
            line_str = line.rstrip("\r\n")
            if line_str:
                print(f"{color}{BOLD}[{prefix}]{RESET} {line_str}", flush=True)
    except Exception:
        pass


def wait_until_live(be_port: int, fe_port: int, timeout_s: float = 240.0) -> bool:
    """True once the API answers /healthz (any status) and the frontend port is open."""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_s
    api_up = False
    while time.time() < deadline:
        if not api_up:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{be_port}/healthz", timeout=2)  # noqa: S310
                api_up = True
            except urllib.error.HTTPError:
                api_up = True  # 503 "down" still means the process is serving
            except OSError:
                pass
        if api_up and is_port_open(fe_port):
            return True
        time.sleep(1.0)
    return False


class Stack:
    """The backend and frontend processes, with a backend restart for new data."""

    def __init__(self, be_port: int, fe_port: int) -> None:
        self.be_port = be_port
        self.fe_port = fe_port
        self.stop_event = threading.Event()
        self.restarting = threading.Event()
        self.procs: dict[str, subprocess.Popen] = {}
        self.data_proc: subprocess.Popen | None = None

    def _spawn(self, name: str, cmd: list[str], cwd: Path, color: str) -> None:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            encoding="utf-8",
            errors="replace",
        )
        self.procs[name] = proc
        threading.Thread(
            target=stream_process_output,
            args=(proc, name.upper(), color, self.stop_event),
            daemon=True,
        ).start()

    def start_backend(self) -> None:
        log("RUN", CYAN, f"Starting Backend on http://localhost:{self.be_port} "
            f"(Docs: http://localhost:{self.be_port}/api/v1/docs)...")
        cmd = ["uv", "run", "uvicorn", "app.main:app", "--port", str(self.be_port)]
        # Uvicorn's Windows reload sends a console Ctrl+C event, which can also
        # stop the runner and data downloader sharing that console.
        if os.name != "nt":
            cmd.append("--reload")
        self._spawn("backend", cmd, BE_DIR, CYAN)

    def start_compute(self) -> None:
        # Jobs are claimed with SKIP LOCKED, so workers never take the same one; two let a
        # long launch calendar and a contact answer be worked out side by side.
        log("RUN", CYAN, f"Starting {COMPUTE_WORKERS} compute workers "
            "(trip, contact and launch answers)...")
        for i in range(1, COMPUTE_WORKERS + 1):
            self._spawn(f"compute-{i}", ["uv", "run", "python", "-m", "app.workers.compute"],
                        BE_DIR, CYAN)

    def start_feeds(self) -> None:
        log("RUN", CYAN, "Starting the feeds worker (weather, space weather, DSN Now)...")
        self._spawn("feeds", ["uv", "run", "python", "-m", "app.workers.feeds"], BE_DIR, CYAN)

    def start_frontend(self) -> None:
        log("RUN", GREEN, f"Starting Frontend on http://localhost:{self.fe_port}...")
        cmd = [npm_command(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(self.fe_port), "--strictPort"]
        self._spawn("frontend", cmd, FE_DIR, GREEN)

    def _stop(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
            proc.wait(timeout=10)
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        deadline = time.time() + 3.0
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass

    def restart_backend(self, why: str) -> None:
        self.restarting.set()
        try:
            log("DATA", YELLOW, f"Restarting the backend so it uses {why}...")
            self._stop(self.procs["backend"])
            self.start_backend()
            workers = [n for n in self.procs if n.startswith("compute")]
            for n in workers:
                self._stop(self.procs.pop(n))
            if workers:
                self.start_compute()
        finally:
            self.restarting.clear()

    def shutdown(self, signum=None, frame=None) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        log("SYSTEM", YELLOW, "\nShutting down the backend, the workers and the frontend...")
        if self.data_proc is not None:
            self._stop(self.data_proc)
        for proc in self.procs.values():
            self._stop(proc)
        log("SYSTEM", GREEN, "All servers stopped. Goodbye!")
        sys.exit(0)

    def monitor(self) -> None:
        while not self.stop_event.is_set():
            time.sleep(0.5)
            if self.restarting.is_set():
                continue
            for name, proc in list(self.procs.items()):
                ret = proc.poll()
                if ret is not None and not self.stop_event.is_set() and not self.restarting.is_set():
                    log("SYSTEM", RED, f"{name.title()} process exited with code {ret}")
                    self.shutdown()


def sync_data(stack: Stack, tiers: list[str]) -> None:
    """Download every dataset the app uses, once the app is already usable.

    Runs ``polar-data sync`` (backend/app/data/sync.py), which reads the list in
    backend/app/data/registry.py -- the same list the README's "Required data"
    section is generated from. Exit 10 means the API should reload new kernels,
    terrain or seeded sites; the backend is restarted for it.
    """
    if not wait_until_live(stack.be_port, stack.fe_port):
        log("DATA", RED, "The app did not come up within 4 minutes; skipping the data sync.")
        return
    log("DATA", CYAN, "App is live. Checking and downloading the datasets it uses "
        "(see README 'Required data')...")
    cmd = ["uv", "run", "polar-data", "sync"]
    for t in tiers:
        cmd += ["--tier", t]
    proc = subprocess.Popen(
        cmd, cwd=BE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    stack.data_proc = proc
    stream_process_output(proc, "DATA", YELLOW, stack.stop_event)
    code = proc.wait()
    stack.data_proc = None
    if stack.stop_event.is_set():
        return
    if code == 0:
        log("DATA", GREEN, "All datasets present.")
    elif code == 10:
        log("DATA", GREEN, "New data downloaded.")
        stack.restart_backend("the new data")
    else:
        log("DATA", RED, "Some datasets could not be downloaded (listed above). "
            "The app keeps working with what is present; re-run to resume, or copy the data "
            "from a machine that has it: `python3 run.py --export-data <folder or .zip>` there, "
            "then `python3 run.py --data-from <that folder or .zip>` here.")


def polar_data(args: list[str]) -> int:
    """Run ``polar-data`` (backend/app/data/sync.py) with its output shown under [DATA]."""
    proc = subprocess.Popen(
        ["uv", "run", "polar-data", *args],
        cwd=BE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    stream_process_output(proc, "DATA", YELLOW, threading.Event())
    return proc.wait()


def import_data(sources: list[str]) -> None:
    """Copy in a shared copy of the data before the app starts, so it starts with it."""
    paths = [str(Path(s).expanduser().resolve()) for s in sources]
    log("DATA", CYAN, f"Copying in the shared data from {', '.join(paths)}...")
    if polar_data(["import", *paths]) in (0, 10):
        log("DATA", GREEN, "Shared data copied in. Anything it lacks is downloaded once the app is up.")
    else:
        log("DATA", YELLOW, "The shared copy could not be used in full (see above). What is "
            "still missing is downloaded once the app is up.")


def migrate() -> None:
    """Bring the database schema up to date (idempotent; new tables for new features)."""
    log("DB", CYAN, "Applying database migrations...")
    res = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=BE_DIR, check=False)
    if res.returncode != 0:
        log("DB", RED, "Migrations failed; the app may miss newer tables (see the output above).")


def run_stack(
    be_port: int = 8000,
    fe_port: int = 5173,
    *,
    data: bool = True,
    data_tiers: list[str] | None = None,
    feeds: bool = True,
) -> None:
    """Run backend, workers and frontend together; then fetch any missing data in the background."""
    stack = Stack(be_port, fe_port)
    migrate()
    stack.start_backend()
    stack.start_compute()
    if feeds:
        stack.start_feeds()
    else:
        log("RUN", YELLOW, "Not starting the feeds worker (--no-feeds): live data stays as stored.")
    stack.start_frontend()
    signal.signal(signal.SIGINT, stack.shutdown)
    signal.signal(signal.SIGTERM, stack.shutdown)
    log("SYSTEM", BOLD, "Both servers starting. Press Ctrl+C to stop.")
    if data:
        threading.Thread(target=sync_data, args=(stack, data_tiers or []), daemon=True).start()
    else:
        log("DATA", YELLOW, "Skipping the data sync (--no-data).")
    stack.monitor()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run POLAR WINDOW: its services, backend, workers and frontend together."
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip running uv sync and npm install before starting.",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8000,
        help="Backend port (default: 8000)",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=5173,
        help="Frontend port (default: 5173)",
    )
    parser.add_argument(
        "--no-data",
        action="store_true",
        help="Do not check or download datasets after the app starts.",
    )
    parser.add_argument(
        "--no-feeds",
        action="store_true",
        help="Do not start the feeds worker (no outbound fetches of weather or space weather).",
    )
    parser.add_argument(
        "--data-from",
        nargs="+",
        metavar="PATH",
        help="Before starting, copy in data shared from another machine: the folder, the .zip, "
        "or the .zip parts Google Drive gives (made there with --export-data).",
    )
    parser.add_argument(
        "--export-data",
        metavar="PATH",
        help="Copy the downloaded data to a folder or a .zip (a name ending in .zip) for "
        "sharing, then exit. The app is not started or stopped.",
    )
    parser.add_argument(
        "--data-tier",
        action="append",
        choices=("core", "lifecycle", "validation", "bulk"),
        help="Which datasets to sync (repeatable; default core, lifecycle, validation). "
        "'bulk' needs PW_EARTHDATA_TOKEN.",
    )
    args = parser.parse_args()

    print(f"{BOLD}{CYAN}=== POLAR WINDOW RUNNER ==={RESET}\n")
    configure_local_storage()
    check_tools()

    if args.export_data:
        out = Path(args.export_data).expanduser().resolve()
        log("DATA", CYAN, f"Exporting the downloaded data to {out}...")
        sys.exit(polar_data(["export", str(out)]))

    # 1. Stop previous instances
    stop_previous_instances(be_port=args.backend_port, fe_port=args.frontend_port)

    # 2. Ensure supporting services (Postgres & Redis), as .env configures them
    env = read_env()
    ensure_postgres(env)
    ensure_redis(env)

    # 3. Install requirements
    if not args.skip_install:
        install_dependencies()
    else:
        log("INSTALL", YELLOW, "Skipping dependency installation (--skip-install).")

    # 3b. Data shared from another machine goes in before the backend loads anything.
    if args.data_from:
        import_data(args.data_from)

    # 4. Run frontend and backend together; once both answer, download any
    #    missing datasets in the background (README "Required data").
    run_stack(
        be_port=args.backend_port,
        fe_port=args.frontend_port,
        data=not args.no_data,
        data_tiers=args.data_tier,
        feeds=not args.no_feeds,
    )


if __name__ == "__main__":
    main()
