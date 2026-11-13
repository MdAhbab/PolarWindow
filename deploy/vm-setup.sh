#!/usr/bin/env bash
# POLAR WINDOW: prepare a fresh Ubuntu 24.04 VM for the public site.
#
#   sudo bash deploy/vm-setup.sh
#
# Installs Docker Engine with the compose plugin (from Docker's apt repository, as
# run_onVM.py does), nginx, certbot and a few tools; caps the size of every
# container's log; adds a 4 GB swap file if the machine has no swap; makes the
# folders the site uses. Safe to run again: each step checks first.
#
# It does NOT open firewall ports, touch DNS, start the app or create a database.
# Those are separate steps in docs/deploy-gcp.md, each one asked of the owner first.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
  echo "Written for Ubuntu; this is ${PRETTY_NAME:-another system}." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "== packages: nginx, certbot, tools"
apt-get update -q
apt-get install -y -q ca-certificates curl git jq nginx certbot dnsutils

echo "== Docker Engine and compose"
if ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  arch="$(dpkg --print-architecture)"
  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "== container logs: 10 MB x 5 files per container"
# Docker keeps every line by default; ten weeks of feeds-worker logs would fill the
# disk. Applies to containers created after this, so run it before the first start.
if [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
JSON
  systemctl restart docker
else
  echo "   /etc/docker/daemon.json exists; left as it is:"
  cat /etc/docker/daemon.json
fi
systemctl enable --now docker

echo "== swap"
# The dashboard build (npm, tsc, vite) is the largest memory user; run_onVM.py
# warns under 3.5 GB. On a 2 GB machine (e2-small) the swap carries the build and
# a trip job's peak; PW_SWAP_SIZE sets it (default 4G).
if [ -z "$(swapon --noheadings)" ]; then
  fallocate -l "${PW_SWAP_SIZE:-4G}" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show

echo "== folders"
mkdir -p /var/www/certbot /var/backups/polarwindow
chmod 700 /var/backups/polarwindow

echo "== versions"
docker --version
docker compose version
nginx -v
certbot --version
echo "Done. Next: docs/deploy-gcp.md, the stage after this one."
