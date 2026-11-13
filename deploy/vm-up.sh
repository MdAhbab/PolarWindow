#!/usr/bin/env bash
# POLAR WINDOW: build and start (or update) the stack on the VM.
#
#   sudo bash deploy/vm-up.sh            build both images, then start or update
#   sudo bash deploy/vm-up.sh --no-build start or update with the images already built
#
# Run from anywhere; it works in the repository that holds it. Uses the .env made
# from deploy/env.production.example (docs/deploy-gcp.md, stage 5) and stops if it
# still has a CHANGE_ME placeholder or does not keep the services on 127.0.0.1.
#
# `docker compose up -d` runs, in order: postgres and redis; `migrate` (alembic
# upgrade head, then exits); `data` (checks the data and the database seed, then
# exits); api, compute, feeds and web. A service whose image did not change keeps
# running. The database volume and ./data are never removed here.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
BUILD=1
[ "${1:-}" = "--no-build" ] && BUILD=0

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi
if [ ! -f .env ]; then
  echo "No .env in $REPO. Make it from deploy/env.production.example first." >&2
  exit 1
fi
if grep -q 'CHANGE_ME' .env; then
  echo ".env still has placeholders (grep -n CHANGE_ME .env). Fill them in first." >&2
  exit 1
fi
for want in 'PW_BIND_ADDR=127.0.0.1' 'PW_WEB_ADDR=127.0.0.1' 'PW_WEB_PORT=8080' \
            'COMPOSE_PROJECT_NAME=polar-window' 'COMPOSE_PROFILES=web' 'PW_ENV=prod'; do
  if ! grep -qx "$want" .env; then
    echo ".env must contain the line: $want" >&2
    exit 1
  fi
done

# The commit every answer is stamped with (the image has no git).
commit="$(sudo -u "$(stat -c %U "$REPO")" git -C "$REPO" rev-parse --short=12 HEAD)"
if grep -q '^PW_CODE_VERSION=' .env; then
  sed -i "s/^PW_CODE_VERSION=.*/PW_CODE_VERSION=${commit}/" .env
else
  printf '\n# Set by deploy/vm-up.sh: the commit the services run.\nPW_CODE_VERSION=%s\n' "$commit" >> .env
fi

# Every service writes under ./data as uid 10001; the group stays the repository
# owner's, with write access, so `git pull` can still update the tracked files there
# (the same as run_onVM.py's prepare_data_dir).
gid="$(stat -c %g "$REPO")"
chown -R "10001:${gid}" data
chmod -R g+rwX data
find data -type d -exec chmod g+s {} +

if [ "$BUILD" = 1 ]; then
  echo "== building the images (backend: Python packages; web: the dashboard)"
  # Two services name the two images; migrate, data and the workers reuse the api's.
  docker compose build --pull api web
fi

echo "== starting (commit ${commit})"
docker compose up -d --remove-orphans

echo "== waiting for the one-off steps (migrate, data)"
for svc in migrate data; do
  cid="$(docker compose ps -a -q "$svc")"
  code="$(docker wait "$cid")"
  echo "   $svc exited with $code"
  if [ "$code" != "0" ]; then
    echo "   see: sudo docker compose logs $svc" >&2
    exit 1
  fi
done

echo "== waiting for the api to answer /healthz (200: ok or degraded; 503: down)"
answered=0
for _ in $(seq 1 60); do
  if body="$(curl -fsS --max-time 5 http://127.0.0.1:8000/healthz 2>/dev/null)"; then
    echo "   $(echo "$body" | jq -c '{status, db, redis, kernels: .kernels.loaded, feeds}')"
    answered=1
    break
  fi
  sleep 5
done
docker compose ps
if [ "$answered" != 1 ]; then
  echo "The api did not answer 200 within 5 minutes:" >&2
  curl -sS --max-time 5 http://127.0.0.1:8000/healthz >&2 || true
  echo "see: sudo docker compose logs --tail 80 api" >&2
  exit 1
fi
