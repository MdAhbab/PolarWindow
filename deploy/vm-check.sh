#!/usr/bin/env bash
# POLAR WINDOW: the checks after a start or an update, on the VM.
#
#   sudo bash deploy/vm-check.sh            the stack on this machine
#   sudo bash deploy/vm-check.sh --site     also the public site through nginx and TLS
#
# Prints PASS or FAIL per line and exits 1 if any FAIL. Reads only, with one
# exception: asking for im-1's trip queues a trip job if, and only if, the stored
# answer is not found, which is exactly the failure it looks for.
set -uo pipefail

REPO="${PW_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
SITE="https://polarwindow.ahbab.tech"
cd "$REPO"
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails + 1)); }
sql() { docker compose exec -T postgres psql -U postgres -d polar_window -At -c "$1"; }

echo "== 1. ports: the database, cache, api and dashboard on 127.0.0.1 only"
for port in 5432 6379 8000 8080; do
  addrs="$(ss -ltnH "sport = :$port" | awk '{print $4}' | sort -u)"
  if [ -z "$addrs" ]; then
    fail "port $port: nothing listens"
  elif echo "$addrs" | grep -qv '^127\.0\.0\.1:'; then
    fail "port $port listens beyond this machine: $(echo $addrs)"
  else
    pass "port $port: $(echo $addrs)"
  fi
done

echo "== 2. containers"
docker compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'
for svc in postgres redis api compute feeds web; do
  state="$(docker compose ps --format '{{.State}}' "$svc" 2>/dev/null)"
  [ "$state" = "running" ] && pass "$svc running" || fail "$svc: ${state:-not created}"
done

echo "== 3. /healthz"
body="$(curl -s --max-time 10 http://127.0.0.1:8000/healthz)"
status="$(echo "$body" | jq -r '.status // "no answer"' 2>/dev/null || echo 'no answer')"
case "$status" in
  ok) pass "healthz: ok" ;;
  degraded) pass "healthz: degraded (feeds still filling, or a feed failing): $(echo "$body" | jq -c '{redis, feeds}')" ;;
  *) fail "healthz: $status $(echo "$body" | jq -c '{db, kernels: .kernels.missing}' 2>/dev/null)" ;;
esac
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8080/)"
[ "$code" = "200" ] && pass "dashboard on 127.0.0.1:8080: 200" || fail "dashboard on 127.0.0.1:8080: $code"

echo "== 4. catalogue bytes match the keys of the stored answers (B1)"
now_st="$(sha256sum data/catalogues/ground_stations.json | cut -c1-16)"
now_veh="$(sha256sum data/catalogues/vehicles.json | cut -c1-16)"
db_st="$(sql "select params->>'stations' from jobs where kind='trip' and status='done' order by id desc limit 1")"
db_veh="$(sql "select params->>'vehicles' from jobs where kind='trip' and status='done' order by id desc limit 1")"
[ -n "$db_st" ] && [ "$now_st" = "$db_st" ] && pass "ground_stations $now_st = stored" || fail "ground_stations file $now_st, stored jobs $db_st"
[ -n "$db_veh" ] && [ "$now_veh" = "$db_veh" ] && pass "vehicles $now_veh = stored" || fail "vehicles file $now_veh, stored jobs $db_veh"

echo "== 5. a stored answer is served with no new job (im-1's trip)"
before="$(sql "select count(*) from jobs where kind='trip'")"
code="$(curl -s -o /tmp/pw-trip.json -w '%{http_code}' --max-time 30 http://127.0.0.1:8000/api/v1/missions/im-1/trip)"
after="$(sql "select count(*) from jobs where kind='trip'")"
src="$(jq -r '.data.source // "?"' /tmp/pw-trip.json 2>/dev/null)"
if [ "$code" = "200" ] && [ "$before" = "$after" ] && [ "$src" != "none" ]; then
  pass "trip im-1: HTTP 200, source $src, trip jobs $before before and after"
else
  fail "trip im-1: HTTP $code, source $src, trip jobs $before -> $after (202 and a new job: the key missed)"
fi

echo "== 6. the dashboard asks /api/v1 on its own origin, never localhost"
if docker compose exec -T web sh -c 'grep -l "localhost:8000" /usr/share/nginx/html/assets/*.js' >/dev/null 2>&1; then
  fail "a built file names localhost:8000"
else
  pass "no built file names localhost:8000"
fi
if docker compose exec -T web sh -c "grep -l '\"/api/v1\"' /usr/share/nginx/html/assets/*.js" >/dev/null 2>&1; then
  pass "the bundle's API base is \"/api/v1\""
else
  fail "the bundle's API base is not \"/api/v1\""
fi

echo "== 7. the job queue"
sql "select kind, status, count(*) from jobs where status in ('queued','running') or created_at > now() - interval '1 hour' group by 1,2 order by 1,2" | sed 's/^/      /'
queued="$(sql "select count(*) from jobs where status='queued'")"
[ "${queued:-0}" -le 10 ] && pass "$queued jobs queued" || fail "$queued jobs queued (stored answers were missed?)"

if [ "${1:-}" = "--site" ]; then
  echo "== 8. the public site"
  for path in / /healthz /api/v1/missions; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$SITE$path")"
    [ "$code" = "200" ] && pass "$SITE$path: 200" || fail "$SITE$path: $code"
  done
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "http://polarwindow.ahbab.tech/")"
  [ "$code" = "301" ] && pass "http:// redirects to https:// (301)" || fail "http://: $code"
  hsts="$(curl -sI --max-time 15 "$SITE/" | grep -i '^strict-transport-security' | tr -d '\r')"
  [ -n "$hsts" ] && pass "$hsts" || fail "no Strict-Transport-Security header"
  end="$(echo | openssl s_client -connect polarwindow.ahbab.tech:443 -servername polarwindow.ahbab.tech 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null)"
  [ -n "$end" ] && pass "certificate: $end" || fail "no certificate read on port 443"
fi

echo
if [ "$fails" -eq 0 ]; then echo "ALL PASS"; else echo "$fails FAIL"; exit 1; fi
