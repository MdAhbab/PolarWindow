#!/usr/bin/env python3
"""POLAR WINDOW on a server: one command for an Ubuntu VM.

    python3 run_onVM.py

It installs Docker if the machine lacks it, stops what an earlier run left
(this project's containers, anything of ours started by run.py, and any
container holding a port we need), clears stopped containers, dangling images
and the build cache, builds both images afresh (the backend with its Python
packages, the dashboard with its Node packages), downloads every dataset the
app reads into ./data, starts the stack and waits until it answers.

What runs afterwards (docker-compose.yml, with the `web` profile):

    web       nginx on --port (80): the dashboard, and /api passed to the api
    api       FastAPI, reachable only through web and from this machine
    compute   the worker for trip, contact and launch answers
    feeds     the worker that fetches live weather and space weather
    postgres, redis   reachable from this machine only

Only `web` is open to the outside. The database, the cache and the api are
published on 127.0.0.1.

The data (about 1.2 GB, all public NASA data) is kept in ./data and is never
deleted by this script, so a second run is a check, not a download. The first
download can take a long time: some archive servers are slow. A copy from a
machine that has it is faster:

    python3 run.py --export-data ~/polar-window-data.zip        (there)
    python3 run_onVM.py --data-from ~/polar-window-data.zip     (here)

Other uses:

    python3 run_onVM.py --status        what is running and whether it is healthy
    python3 run_onVM.py --stop          stop the stack (the data and the database stay)
    python3 run_onVM.py --dry-run       print every command without running any

Standard library only: this runs before anything else is installed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
RUN_PIDS = ROOT / ".local" / "run.pids"

PROJECT = "polar-window"
IMAGES = ("polar-window-backend", "polar-window-web")
#: The uid the backend image runs as; ./data is mounted into it and written there.
CONTAINER_UID = 10001
#: Compose 2.24 added the optional env_file the compose file uses.
MIN_COMPOSE = (2, 24)
#: Images, build cache and the data together.
MIN_FREE_GB = 8.0
MIN_RAM_GB = 3.5

CYAN, GREEN, YELLOW, RED, BOLD, RESET = "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
if not sys.stdout.isatty():
    CYAN = GREEN = YELLOW = RED = BOLD = RESET = ""

DRY = False


def log(prefix: str, color: str, msg: str) -> None:
    print(f"{color}{BOLD}[{prefix}]{RESET} {msg}", flush=True)


def fail(msg: str, code: int = 1) -> NoReturn:
    log("STOP", RED, msg)
    sys.exit(code)


def shown(cmd: list[str]) -> str:
    return " ".join(c if re.fullmatch(r"[\w@%+=:,./-]+", c) else repr(c) for c in cmd)


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    always: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command from the repository's folder. ``always`` runs it under --dry-run too
    (for commands that only look)."""
    if DRY and not always:
        print(f"    $ {shown(cmd)}", flush=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    try:
        res = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError:
        if check:
            fail(f"`{cmd[0]}` was not found.")
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: not found")
    if check and res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip() if capture else ""
        fail(f"`{shown(cmd)}` failed with exit code {res.returncode}." + (f"\n{detail}" if detail else ""))
    return res


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------


def sudo() -> list[str]:
    return [] if os.geteuid() == 0 else ["sudo"]


def os_release() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            out[key] = value.strip().strip('"')
    except OSError:
        pass
    return out


def preflight() -> None:
    if not (ROOT / "docker-compose.yml").is_file() or not (ROOT / "backend").is_dir():
        fail(f"{ROOT} is not the POLAR WINDOW repository (docker-compose.yml is missing).")
    if not sys.platform.startswith("linux"):
        if DRY:
            log("CHECK", YELLOW, f"This is {sys.platform}, not Linux: showing the commands only.")
            return
        fail("This script is for an Ubuntu server. On your own machine use `python3 run.py`.")
    rel = os_release()
    if rel.get("ID") != "ubuntu":
        log("CHECK", YELLOW, f"Written for Ubuntu; this is {rel.get('PRETTY_NAME', 'another system')}. "
            "Docker must already be installed for it to work here.")
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < MIN_FREE_GB:
        log("CHECK", YELLOW, f"Only {free_gb:.1f} GB free here; the images and the data need about "
            f"{MIN_FREE_GB:.0f} GB. The build or the downloads may stop part-way.")
    try:
        kb = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))  # type: ignore[union-attr]
        if kb / 1e6 < MIN_RAM_GB:
            log("CHECK", YELLOW, f"{kb / 1e6:.1f} GB of memory; building the dashboard wants about "
                f"{MIN_RAM_GB:.0f} GB. If the build is killed, add swap "
                "(`sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile "
                "&& sudo swapon /swapfile`) and run this again.")
    except (OSError, AttributeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

_docker: list[str] | None = None


def docker() -> list[str]:
    """``docker`` as this user can run it: bare when the user may, else through sudo."""
    global _docker
    if _docker is None:
        if DRY and shutil.which("docker") is None:
            _docker = ["docker"]
        elif subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0:
            _docker = ["docker"]
        else:
            _docker = [*sudo(), "docker"]
    return _docker


def compose(*args: str) -> list[str]:
    return [*docker(), "compose", "--project-name", PROJECT, "--profile", "web", *args]


def compose_version() -> tuple[int, int] | None:
    if shutil.which("docker") is None:
        return None
    for base in (["docker"], [*sudo(), "docker"]):
        res = subprocess.run([*base, "compose", "version", "--short"], capture_output=True, text=True, check=False)
        m = re.search(r"(\d+)\.(\d+)", res.stdout or "")
        if res.returncode == 0 and m:
            return int(m.group(1)), int(m.group(2))
    return None


def install_docker() -> None:
    """Docker Engine and the compose plugin from Docker's own apt repository."""
    rel = os_release()
    if rel.get("ID") != "ubuntu" and not DRY:
        fail("Docker is missing and this is not Ubuntu, so it is not installed for you. Install Docker "
             f"Engine with the compose plugin ({MIN_COMPOSE[0]}.{MIN_COMPOSE[1]} or newer), then run this again.")
    log("DOCKER", YELLOW, "Installing Docker Engine and the compose plugin (apt, from download.docker.com)...")
    codename = rel.get("UBUNTU_CODENAME") or rel.get("VERSION_CODENAME") or ""
    arch = "amd64"
    if not DRY:
        arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=False).stdout.strip() or "amd64"
    s = sudo()
    apt_env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    run([*s, "apt-get", "update"], env=apt_env)
    run([*s, "apt-get", "install", "-y", "ca-certificates", "curl", "git"], env=apt_env)
    run([*s, "install", "-m", "0755", "-d", "/etc/apt/keyrings"])
    run([*s, "curl", "-fsSL", "https://download.docker.com/linux/ubuntu/gpg", "-o", "/etc/apt/keyrings/docker.asc"])
    run([*s, "chmod", "a+r", "/etc/apt/keyrings/docker.asc"])
    source = (f"deb [arch={arch} signed-by=/etc/apt/keyrings/docker.asc] "
              f"https://download.docker.com/linux/ubuntu {codename} stable\n")
    if DRY:
        print(f"    $ echo {source.strip()!r} | {shown([*s, 'tee', '/etc/apt/sources.list.d/docker.list'])}", flush=True)
    else:
        subprocess.run([*s, "tee", "/etc/apt/sources.list.d/docker.list"], input=source, text=True,
                       stdout=subprocess.DEVNULL, check=True)
    run([*s, "apt-get", "update"], env=apt_env)
    run([*s, "apt-get", "install", "-y", "docker-ce", "docker-ce-cli", "containerd.io",
         "docker-buildx-plugin", "docker-compose-plugin"], env=apt_env)
    run([*s, "systemctl", "enable", "--now", "docker"])
    log("DOCKER", GREEN, "Docker installed.")


def ensure_docker(skip_install: bool) -> None:
    version = compose_version()
    if version is not None and version >= MIN_COMPOSE:
        log("DOCKER", GREEN, f"Docker with compose {version[0]}.{version[1]} is installed.")
    elif skip_install:
        fail(f"Docker with compose {MIN_COMPOSE[0]}.{MIN_COMPOSE[1]} or newer is needed (--skip-docker-install was given).")
    else:
        if version is not None:
            log("DOCKER", YELLOW, f"Compose {version[0]}.{version[1]} is older than {MIN_COMPOSE[0]}.{MIN_COMPOSE[1]}.")
        install_docker()
    if not DRY and run([*docker(), "info"], check=False, capture=True, always=True).returncode != 0:
        run([*sudo(), "systemctl", "start", "docker"], check=False)
        if run([*docker(), "info"], check=False, capture=True, always=True).returncode != 0:
            fail("The Docker daemon does not answer (`docker info`). Start it with `sudo systemctl start docker`.")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def read_env_keys() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.is_file():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                values[key[7:].strip() if key.startswith("export ") else key] = value.strip()
    return values


def ensure_env() -> None:
    """Make .env if there is none, and give it a signing secret if it has none.

    Nothing already set is changed. The secret keeps people signed in across a
    restart; it is written to .env only (mode 600), never printed.
    """
    if not ENV_FILE.exists():
        if DRY:
            log("SETTINGS", YELLOW, "Would create .env from .env.example.")
        else:
            text = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.is_file() else ""
            ENV_FILE.write_text(text, encoding="utf-8")
            log("SETTINGS", GREEN, "Created .env from .env.example. API keys are optional; add them there.")
    have = read_env_keys()
    if not have.get("PW_JWT_SECRET"):
        if DRY:
            log("SETTINGS", YELLOW, "Would add a random PW_JWT_SECRET to .env.")
        else:
            with ENV_FILE.open("a", encoding="utf-8") as fh:
                fh.write("\n# Signs session tokens. Made by run_onVM.py; keep it secret, keep it the same.\n"
                         f"PW_JWT_SECRET={secrets.token_urlsafe(48)}\n")
            log("SETTINGS", GREEN, "Added a session signing secret to .env.")
    if not DRY:
        try:
            ENV_FILE.chmod(0o600)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Stopping what is there
# ---------------------------------------------------------------------------


def stop_runner_processes() -> None:
    """Stop what an earlier `python3 run.py` on this machine left running (its pid file)."""
    if not RUN_PIDS.is_file():
        return
    try:
        recorded = json.loads(RUN_PIDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    pids: list[int] = []
    for entry in recorded.values() if isinstance(recorded, dict) else []:
        pid = entry.get("pid") if isinstance(entry, dict) else None
        if isinstance(pid, int) and pid > 1 and Path(f"/proc/{pid}").exists():
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                continue
            if cwd.startswith(str(ROOT)):  # ours, not a pid the system has since reused
                pids.append(pid)
    if not pids:
        return
    log("CLEANUP", YELLOW, f"Stopping processes an earlier run.py left: {sorted(pids)}")
    if DRY:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.killpg(os.getpgid(pid), sig)
            except (ProcessLookupError, PermissionError):
                pass
        deadline = time.time() + 10
        while time.time() < deadline and any(Path(f"/proc/{p}").exists() for p in pids):
            time.sleep(0.3)
        if not any(Path(f"/proc/{p}").exists() for p in pids):
            break
    RUN_PIDS.unlink(missing_ok=True)


def containers_on_port(port: int) -> list[tuple[str, str]]:
    res = run([*docker(), "ps", "--filter", f"publish={port}", "--format", "{{.ID}}\t{{.Names}}"],
              check=False, capture=True)
    rows = [line.split("\t", 1) for line in (res.stdout or "").splitlines() if "\t" in line]
    return [(r[0], r[1]) for r in rows]


def port_holder(port: int) -> str | None:
    """The process listening on a TCP port, in words, or None when it is free."""
    res = subprocess.run(["ss", "-H", "-ltnp", f"sport = :{port}"], capture_output=True, text=True, check=False)
    line = (res.stdout or "").strip().splitlines()
    if not line:
        return None
    m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line[0])
    return f"{m.group(1)} (pid {m.group(2)})" if m else "another program"


def stop_previous(ports: list[int], *, stop_all: bool, fresh_db: bool) -> None:
    log("CLEANUP", YELLOW, "Stopping what an earlier run left...")
    down = ["down", "--remove-orphans"] + (["--volumes"] if fresh_db else [])
    run(compose(*down), check=False)
    stop_runner_processes()
    if stop_all:
        ids = (run([*docker(), "ps", "-q"], check=False, capture=True).stdout or "").split()
        if ids:
            log("CLEANUP", YELLOW, f"Stopping every running container on this machine ({len(ids)}), as asked.")
            run([*docker(), "stop", *ids], check=False)
    for port in ports:
        for cid, name in containers_on_port(port):
            log("CLEANUP", YELLOW, f"Container {name} holds port {port}; stopping it.")
            run([*docker(), "stop", cid], check=False)
    if DRY or not sys.platform.startswith("linux"):
        return
    for port in ports:
        holder = port_holder(port)
        if holder:
            hint = ("choose another port with --port, or stop it (a web server: "
                    "`sudo systemctl disable --now nginx apache2`)" if port not in (8000, 5432, 6379)
                    else "stop it (a database or cache installed on this machine: "
                    "`sudo systemctl disable --now postgresql redis-server`)")
            fail(f"Port {port} is in use by {holder}, which is not a container and was not started by this "
                 f"project. To go on, {hint}, then run this again.")


def prune(keep_cache: bool) -> None:
    log("CLEANUP", YELLOW, "Removing stopped containers and dangling images" +
        ("..." if keep_cache else ", the build cache and this project's old images..."))
    run([*docker(), "container", "prune", "--force"], check=False)
    run([*docker(), "image", "prune", "--force"], check=False)
    if not keep_cache:
        run([*docker(), "image", "rm", "--force", *IMAGES], check=False, capture=True)
        run([*docker(), "builder", "prune", "--force"], check=False)


# ---------------------------------------------------------------------------
# Building, data, starting
# ---------------------------------------------------------------------------


def stack_env(port: int) -> dict[str, str]:
    commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=False).stdout.strip()
    return {
        **os.environ,
        "PW_WEB_PORT": str(port),
        # Only the dashboard is open to the outside.
        "PW_BIND_ADDR": "127.0.0.1",
        # nginx sets X-Forwarded-For itself (frontend/nginx.conf), and the api is not
        # reachable from outside, so the api may believe it: limits are per visitor.
        "PW_FORWARDED_ALLOW_IPS": "*",
        "PW_CODE_VERSION": commit,
    }


def prepare_data_dir() -> None:
    if not DRY:
        DATA_DIR.mkdir(exist_ok=True)
    # Every service writes there as the image's user. The group stays this user's, with
    # write access, so `git pull` can still update the files the repository keeps in data/.
    gid = str(os.getgid())
    run([*sudo(), "chown", "-R", f"{CONTAINER_UID}:{gid}", str(DATA_DIR)], check=False)
    run([*sudo(), "chmod", "-R", "g+rwX", str(DATA_DIR)], check=False)
    run([*sudo(), "find", str(DATA_DIR), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"], check=False)


def build(env: dict[str, str], keep_cache: bool) -> None:
    log("BUILD", CYAN, "Building the backend image (Python packages) and the dashboard image (Node packages)...")
    # Two services name the two images; the workers and the data step reuse the api's.
    run(compose("build", "--pull", *([] if keep_cache else ["--no-cache"]), "api", "web"), env=env)
    log("BUILD", GREEN, "Images built.")


def import_data(sources: list[str], env: dict[str, str]) -> None:
    for src in sources:
        path = Path(src).expanduser().resolve()
        if not path.exists() and not DRY:
            fail(f"--data-from: {path} does not exist.")
        # Only what was named is shown to the container, read-only.
        inside = "/import" if path.is_dir() else f"/import/{path.name}"
        log("DATA", CYAN, f"Copying in the shared data from {path}...")
        res = run(compose("run", "--rm", "--no-deps", "--volume", f"{path}:{inside}:ro", "data",
                          "polar-data", "import", inside), env=env, check=False)
        if res.returncode not in (0, 10):
            log("DATA", YELLOW, "The shared copy could not be used in full; what is missing is downloaded next.")


def fetch_data(env: dict[str, str], with_validation: bool) -> None:
    log("DATA", CYAN, "Applying the database migrations, then checking and downloading the datasets "
        "(README, 'Required data'). The first time this is the long step...")
    res = run(compose("run", "--rm", "data"), env=env, check=False)
    if res.returncode != 0:
        log("DATA", YELLOW, "The data step reported a problem (above). The app still starts and says what "
            "is missing on /healthz; run this script again to resume the downloads.")
    if with_validation:
        log("DATA", CYAN, "Fetching the datasets that only check our numbers (--with-validation)...")
        run(compose("run", "--rm", "data", "polar-data", "sync", "--tier", "validation"), env=env, check=False)


def start(env: dict[str, str]) -> None:
    log("RUN", CYAN, "Starting the stack...")
    run(compose("up", "--detach", "--remove-orphans"), env=env)


def health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:  # 503 with a body still says what is wrong
        try:
            return json.loads(err.read().decode("utf-8"))
        except ValueError:
            return None
    except (OSError, ValueError):
        return None


def wait_until_up(port: int, timeout_s: float = 300.0) -> dict | None:
    log("RUN", CYAN, "Waiting for the app to answer...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        body = health(port)
        if body is not None:
            return body
        time.sleep(3)
    return None


def open_firewall(port: int) -> None:
    if shutil.which("ufw") is None:
        return
    status = run([*sudo(), "ufw", "status"], check=False, capture=True).stdout or ""
    if "Status: active" in status:
        log("NETWORK", YELLOW, f"The firewall (ufw) is on; allowing port {port}.")
        run([*sudo(), "ufw", "allow", f"{port}/tcp"], check=False)


def addresses(port: int) -> list[str]:
    res = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=False)
    suffix = "" if port == 80 else f":{port}"
    return [f"http://{ip}{suffix}/" for ip in (res.stdout or "").split() if ":" not in ip][:3]


def report(port: int, body: dict | None) -> None:
    run(compose("ps"), check=False)
    if body is None:
        log("RUN", RED, "The app did not answer within 5 minutes. Look at "
            f"`{shown(compose('logs', '--tail', '80', 'api', 'web'))}`.")
        sys.exit(1)
    kernels = body.get("kernels", {}) if isinstance(body.get("kernels"), dict) else {}
    log("RUN", GREEN, f"The app answers. Status: {body.get('status')}; database {body.get('db')}; "
        f"cache {body.get('redis')}; Sun and Earth positions "
        f"{'loaded' if kernels.get('loaded') else 'NOT loaded: ' + ', '.join(kernels.get('missing', []) or ['see /healthz'])}.")
    if body.get("status") != "ok":
        log("RUN", YELLOW, "\"degraded\" usually means some live feeds are still being fetched for the first "
            "time; it settles within a few minutes. /healthz says exactly what is missing.")
    print()
    log("OPEN", BOLD, "The dashboard:")
    for url in addresses(port) or [f"http://<this machine's address>{'' if port == 80 else f':{port}'}/"]:
        print(f"    {url}")
    print("    (On a cloud VM use its public address, and allow the port in the provider's firewall.)")
    print()
    print(f"    Logs:    {shown(compose('logs', '--follow', 'api'))}")
    print("    Stop:    python3 run_onVM.py --stop")
    print("    Update:  git pull && python3 run_onVM.py")


# ---------------------------------------------------------------------------


def main() -> None:
    global DRY
    p = argparse.ArgumentParser(description="Run POLAR WINDOW on an Ubuntu server with Docker.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--port", type=int, default=80, help="Port the dashboard is served on (default 80).")
    p.add_argument("--data-from", nargs="+", metavar="PATH",
                   help="Copy in data exported on another machine (`python3 run.py --export-data`): a folder or a .zip.")
    p.add_argument("--with-validation", action="store_true",
                   help="Also download the datasets used only to check our numbers (about 180 MB).")
    p.add_argument("--keep-cache", action="store_true",
                   help="Reuse Docker's build cache instead of building both images from nothing.")
    p.add_argument("--fresh-db", action="store_true",
                   help="Also delete the database (saved answers, settings, the activity log). The data in ./data stays.")
    p.add_argument("--stop-all-docker", action="store_true",
                   help="Stop every running container on this machine, not only this project's and those on our ports.")
    p.add_argument("--skip-docker-install", action="store_true", help="Never install Docker; stop if it is missing.")
    p.add_argument("--pull", action="store_true", help="`git pull --ff-only` before building.")
    p.add_argument("--stop", action="store_true", help="Stop the stack and exit.")
    p.add_argument("--status", action="store_true", help="Show what is running and whether it is healthy, then exit.")
    p.add_argument("--dry-run", action="store_true", help="Print the commands without running them.")
    args = p.parse_args()
    DRY = args.dry_run

    print(f"{BOLD}{CYAN}=== POLAR WINDOW on a server ==={RESET}\n")
    preflight()

    if args.status:
        run(compose("ps"), check=False)
        body = health(args.port)
        print(json.dumps(body, indent=2) if body else "The app does not answer on this port.")
        sys.exit(0 if body else 1)
    if args.stop:
        run(compose("down", "--remove-orphans"), check=False)
        log("RUN", GREEN, "Stopped. The data in ./data and the database are kept.")
        return

    ensure_docker(args.skip_docker_install)
    if args.pull:
        run(["git", "pull", "--ff-only"])
    ensure_env()

    env = stack_env(args.port)
    # The ports the stack publishes: the dashboard to everyone, the rest to this machine.
    stop_previous([args.port, 8000, 5432, 6379], stop_all=args.stop_all_docker, fresh_db=args.fresh_db)
    prune(args.keep_cache)
    prepare_data_dir()
    build(env, args.keep_cache)
    if args.data_from:
        import_data(args.data_from, env)
    fetch_data(env, args.with_validation)
    start(env)
    open_firewall(args.port)
    if DRY:
        log("DRY RUN", GREEN, "Nothing was run.")
        return
    report(args.port, wait_until_up(args.port))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        log("STOP", YELLOW, "Interrupted. Nothing is lost: run this again to carry on (downloads resume).")
        sys.exit(130)
