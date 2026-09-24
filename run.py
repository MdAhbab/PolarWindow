#!/usr/bin/env python3
"""POLAR WINDOW - Unified runner and environment manager.

Stops previous instances of frontend and backend, starts required local services
(Postgres and Redis), installs all backend & frontend dependencies, and runs
FastAPI (backend) and Vite (frontend) together.
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


def run_stack(be_port: int = 8000, fe_port: int = 5173) -> None:
    """Run backend and frontend processes simultaneously and handle termination."""
    stop_event = threading.Event()
    procs: list[subprocess.Popen] = []

    # Backend Command
    be_cmd = ["uv", "run", "uvicorn", "app.main:app", "--reload", "--port", str(be_port)]
    # Frontend Command
    fe_cmd = ["npm", "run", "dev"]

    log("RUN", CYAN, f"Starting Backend on http://localhost:{be_port} (Docs: http://localhost:{be_port}/api/v1/docs)...")
    be_proc = subprocess.Popen(
        be_cmd,
        cwd=BE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        preexec_fn=os.setsid,  # Run in distinct process group for clean subtree termination
    )
    procs.append(be_proc)

    log("RUN", GREEN, f"Starting Frontend on http://localhost:{fe_port}...")
    fe_proc = subprocess.Popen(
        fe_cmd,
        cwd=FE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        preexec_fn=os.setsid,
    )
    procs.append(fe_proc)

    # Start output streaming threads
    be_thread = threading.Thread(
        target=stream_process_output,
        args=(be_proc, "BACKEND", CYAN, stop_event),
        daemon=True,
    )
    fe_thread = threading.Thread(
        target=stream_process_output,
        args=(fe_proc, "FRONTEND", GREEN, stop_event),
        daemon=True,
    )
    be_thread.start()
    fe_thread.start()

    log("SYSTEM", BOLD, f"Both servers running! Press Ctrl+C to stop.")

    def shutdown(signum=None, frame=None):
        if stop_event.is_set():
            return
        stop_event.set()
        log("SYSTEM", YELLOW, "\nShutting down backend and frontend...")

        for proc in procs:
            if proc.poll() is None:
                try:
                    # Kill whole process group
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

        # Give processes up to 3 seconds to exit cleanly
        start_time = time.time()
        for proc in procs:
            while proc.poll() is None and time.time() - start_time < 3.0:
                time.sleep(0.1)
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

        log("SYSTEM", GREEN, "All servers stopped. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Monitor processes
    while not stop_event.is_set():
        time.sleep(0.5)
        for name, proc in [("Backend", be_proc), ("Frontend", fe_proc)]:
            ret = proc.poll()
            if ret is not None and not stop_event.is_set():
                log("SYSTEM", RED, f"{name} process exited with code {ret}")
                shutdown()


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

    # 4. Run frontend and backend together
    run_stack(be_port=args.backend_port, fe_port=args.frontend_port)


if __name__ == "__main__":
    main()
