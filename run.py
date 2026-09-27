#!/usr/bin/env python3
"""POLAR WINDOW - Unified runner and environment manager.

Stops previous instances of frontend and backend, starts required local services
(Postgres and Redis), installs all backend & frontend dependencies, and runs
FastAPI (backend) and Vite (frontend) together. Once both answer, it downloads
every dataset the app uses that is not already on disk (SPICE kernels, LOLA
terrain, GRAIL gravity, flown CLPS trajectories and the rest; the list is
backend/app/data/registry.py and the README's "Required data" section), then
restarts the backend if the new data is something it loads at start-up.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# Base Paths
ROOT_DIR = Path(__file__).resolve().parent
BE_DIR = ROOT_DIR / "backend"
FE_DIR = ROOT_DIR / "frontend"
LOCAL_DIR = ROOT_DIR / ".local"
PGDATA_DIR = LOCAL_DIR / "pgdata"
PGLOG_FILE = LOCAL_DIR / "pg.log"
REDIS_DIR = LOCAL_DIR / "redis"

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


def ensure_postgres() -> None:
    """Ensure PostgreSQL is accessible on port 5433 or unix socket."""
    is_up = is_port_open(5433) or is_unix_socket_open("/tmp/.s.PGSQL.5433")
    if is_up:
        log("SERVICES", GREEN, "PostgreSQL is running (port 5433 / /tmp socket).")
        return

    if not PGDATA_DIR.exists():
        log("SERVICES", YELLOW, f"No local pgdata directory found at {PGDATA_DIR}. Assuming external DB.")
        return

    log("SERVICES", YELLOW, "Starting local PostgreSQL server on port 5433...")
    pg_ctl = subprocess.run(["which", "pg_ctl"], capture_output=True, text=True, check=False)
    pg_ctl_bin = pg_ctl.stdout.strip() if pg_ctl.returncode == 0 else "pg_ctl"

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    PGLOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        pg_ctl_bin,
        "-D", str(PGDATA_DIR),
        "-l", str(PGLOG_FILE),
        "-o", "-p 5433 -k /tmp",
        "start",
    ]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        log("SERVICES", RED, f"Failed to start PostgreSQL: {res.stderr or res.stdout}")
    else:
        log("SERVICES", GREEN, "PostgreSQL started successfully.")


def ensure_redis() -> None:
    """Ensure Redis is accessible on port 6380."""
    if is_port_open(6380):
        log("SERVICES", GREEN, "Redis is running (port 6380).")
        return

    log("SERVICES", YELLOW, "Starting local Redis server on port 6380...")
    REDIS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "redis-server",
        "--port", "6380",
        "--dir", str(REDIS_DIR),
        "--daemonize", "yes",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        log("SERVICES", RED, f"Failed to start Redis: {res.stderr or res.stdout}")
    else:
        log("SERVICES", GREEN, "Redis started successfully.")


def install_dependencies() -> None:
    """Install backend and frontend requirements."""
    log("INSTALL", YELLOW, "Installing backend dependencies with uv...")
    res_be = subprocess.run(["uv", "sync", "--extra", "dev"], cwd=BE_DIR, check=False)
    if res_be.returncode != 0:
        log("INSTALL", RED, "Backend dependency installation returned a non-zero exit code.")
        sys.exit(res_be.returncode)
    log("INSTALL", GREEN, "Backend dependencies up to date.")

    log("INSTALL", YELLOW, "Installing frontend dependencies with npm...")
    res_fe = subprocess.run(["npm", "install"], cwd=FE_DIR, check=False)
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

    def _spawn(self, name: str, cmd: list[str], cwd: Path, color: str) -> None:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,  # own process group, so the whole subtree stops together
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
        cmd = ["uv", "run", "uvicorn", "app.main:app", "--reload", "--port", str(self.be_port)]
        self._spawn("backend", cmd, BE_DIR, CYAN)

    def start_compute(self) -> None:
        log("RUN", CYAN, "Starting the compute worker (trip, contact and launch answers)...")
        self._spawn("compute", ["uv", "run", "python", "-m", "app.workers.compute"], BE_DIR, CYAN)

    def start_feeds(self) -> None:
        log("RUN", CYAN, "Starting the feeds worker (weather, space weather, DSN Now)...")
        self._spawn("feeds", ["uv", "run", "python", "-m", "app.workers.feeds"], BE_DIR, CYAN)

    def start_frontend(self) -> None:
        log("RUN", GREEN, f"Starting Frontend on http://localhost:{self.fe_port}...")
        cmd = ["npm", "run", "dev", "--", "--port", str(self.fe_port), "--strictPort"]
        self._spawn("frontend", cmd, FE_DIR, GREEN)

    def _stop(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
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
            if "compute" in self.procs:
                self._stop(self.procs["compute"])
                self.start_compute()
        finally:
            self.restarting.clear()

    def shutdown(self, signum=None, frame=None) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        log("SYSTEM", YELLOW, "\nShutting down the backend, the workers and the frontend...")
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
    stream_process_output(proc, "DATA", YELLOW, stack.stop_event)
    code = proc.wait()
    if stack.stop_event.is_set():
        return
    if code == 0:
        log("DATA", GREEN, "All datasets present.")
    elif code == 10:
        log("DATA", GREEN, "New data downloaded.")
        stack.restart_backend("the new data")
    else:
        log("DATA", RED, "Some datasets could not be downloaded (listed above). "
            "The app keeps working with what is present; re-run to resume.")


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
        description="Run Polar Window frontend and backend simultaneously with dependency checks."
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
        "--data-tier",
        action="append",
        choices=("core", "lifecycle", "validation", "bulk"),
        help="Which datasets to sync (repeatable; default core, lifecycle, validation). "
        "'bulk' needs PW_EARTHDATA_TOKEN.",
    )
    args = parser.parse_args()

    print(f"{BOLD}{CYAN}=== POLAR WINDOW RUNNER ==={RESET}\n")

    # 1. Stop previous instances
    stop_previous_instances(be_port=args.backend_port, fe_port=args.frontend_port)

    # 2. Ensure supporting services (Postgres & Redis)
    ensure_postgres()
    ensure_redis()

    # 3. Install requirements
    if not args.skip_install:
        install_dependencies()
    else:
        log("INSTALL", YELLOW, "Skipping dependency installation (--skip-install).")

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
