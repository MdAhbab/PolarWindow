#!/usr/bin/env bash
# POLAR WINDOW: one database backup, and old ones removed.
#
#   sudo bash deploy/backup.sh
#
# Run daily by deploy/systemd/polarwindow-backup.timer, and by hand before every
# update. Writes /var/backups/polarwindow/polar_window-<UTC time>.dump (pg_dump
# custom format, compressed), checks that pg_restore can read it, and deletes dumps
# older than KEEP_DAYS. Restore one with the commands in docs/deploy-gcp.md
# ("Restore a backup").
#
# The raw feed bodies do not compress, so a dump is close to the database's size
# (docs/deploy-gcp.md, "Staying up"). On 24 November the dumps filled the VM's 20 GB
# disk and the site stopped. So the backups together stay under MAX_MB, the oldest
# dump going first and the newest always kept, and a run without room is skipped.
set -euo pipefail

REPO="${PW_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
DEST="${PW_BACKUP_DIR:-/var/backups/polarwindow}"
KEEP_DAYS="${PW_BACKUP_KEEP_DAYS:-7}"
#: Every file in DEST together, in MB.
MAX_MB="${PW_BACKUP_MAX_MB:-2048}"
#: Room left free on the disk after a dump, for the database, the feeds and the logs.
RESERVE_MB="${PW_BACKUP_RESERVE_MB:-512}"

cd "$REPO"
mkdir -p "$DEST"
chmod 700 "$DEST"

# A run that stopped part way leaves its .part behind: no backup, only lost room.
find "$DEST" -maxdepth 1 -name 'polar_window-*.dump.part' -mmin +120 -delete

total_mb() { du -sm "$DEST" | cut -f1; }
# This script's dumps, oldest first. Other files (a dump brought from elsewhere) count
# towards MAX_MB but are never deleted.
dumps() {
  find "$DEST" -maxdepth 1 -name 'polar_window-*.dump' -printf '%T@ %p\n' | sort -n | cut -d' ' -f2-
}
# Delete the oldest dumps until the backups and $1 MB more fit under MAX_MB.
trim_to() {
  local old
  while (( $(total_mb) + $1 > MAX_MB )) && (( $(dumps | wc -l) > 1 )); do
    old="$(dumps | sed -n 1p)"
    rm -f -- "$old"
    echo "backup: removed $old to stay under ${MAX_MB} MB"
  done
}

# A new dump needs about as much room as the last one; a fifth more to be safe.
last_bytes="$(find "$DEST" -maxdepth 1 -name 'polar_window-*.dump' -printf '%T@ %s\n' |
  sort -n | tail -1 | cut -d' ' -f2)"
est_mb=$(( ${last_bytes:-0} * 12 / 10 / 1048576 ))
trim_to "$est_mb"

need_mb=$(( est_mb + RESERVE_MB ))
free_mb=$(( $(df --output=avail -B1 "$DEST" | tail -1) / 1048576 ))
if (( free_mb < need_mb )); then
  echo "backup: skipped, ${free_mb} MB free and ${need_mb} MB needed" \
    "(the last dump with a fifth more, and ${RESERVE_MB} MB to spare)" >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$DEST/polar_window-$stamp.dump"
# Whatever stops this run, its partial dump goes with it.
trap 'rm -f "$out.part"' EXIT

docker compose exec -T postgres pg_dump -U postgres -d polar_window -Fc > "$out.part"
# A dump pg_restore cannot list is no backup.
docker compose exec -T postgres pg_restore -l < "$out.part" > /dev/null
mv "$out.part" "$out"
chmod 600 "$out"
echo "backup: $out ($(du -h "$out" | cut -f1))"

find "$DEST" -maxdepth 1 -name 'polar_window-*.dump' -mtime +"$KEEP_DAYS" -print -delete
trim_to 0
echo "backup: $(total_mb) MB kept in $DEST"
df -h "$DEST" | tail -1
