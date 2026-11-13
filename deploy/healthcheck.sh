#!/usr/bin/env bash
# POLAR WINDOW: a health check every few minutes (deploy/systemd/polarwindow-health.timer).
#
#   sudo bash deploy/healthcheck.sh
#
# Asks the api's /healthz on this machine (the real route: /healthz and
# /api/v1/healthz; /api/v1/health does not exist). It answers 200 when "ok" or
# "degraded" and 503 when "down" (no Sun and Earth positions, or no database;
# backend/app/services/health_service.py).
#
# - No answer at all three checks in a row: the api is restarted, once, and that is
#   written to the journal. A 503 is only written down: a restart does not bring
#   back a missing kernel file or a stopped database, and docker restarts a container
#   whose process exits.
# - The site through nginx and TLS, and the disk, are written down too.
# Read the results with: journalctl -t polarwindow-health --since today
set -uo pipefail

REPO="${PW_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
SITE="${PW_SITE:-https://polarwindow.ahbab.tech}"
STATE=/run/polarwindow-health.misses
say() { logger -t polarwindow-health "$*"; echo "$*"; }

code="$(curl -s -o /tmp/pw-health.json -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/healthz)"
if [ "$code" = "000" ]; then
  misses=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
  echo "$misses" > "$STATE"
  say "api: no answer ($misses in a row)"
  if [ "$misses" -ge 3 ]; then
    say "api: restarting after $misses checks with no answer"
    (cd "$REPO" && docker compose restart api) || say "api: restart failed"
    echo 0 > "$STATE"
  fi
else
  echo 0 > "$STATE"
  status="$(jq -r '.status // "?"' /tmp/pw-health.json 2>/dev/null || echo '?')"
  if [ "$code" != "200" ] || [ "$status" != "ok" ]; then
    say "api: HTTP $code, status $status: $(jq -c '{db, redis, kernels: .kernels.missing, feeds}' /tmp/pw-health.json 2>/dev/null)"
  fi
fi

site="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$SITE/healthz")"
[ "$site" = "200" ] || say "site: $SITE/healthz answered HTTP $site"

used="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
[ "${used:-0}" -lt 85 ] || say "disk: / is ${used}% full (docs/deploy-gcp.md, 'Disk')"
exit 0
