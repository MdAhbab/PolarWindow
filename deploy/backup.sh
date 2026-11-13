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
# On 13 November the database was 73 MB and its dump 60 MB (measured on the PC). The
# raw feed bodies do not compress, so dumps grow with the database (docs/deploy-gcp.md,
# "Staying up"); 7 days are kept. Set PW_BACKUP_KEEP_DAYS to change that.
set -euo pipefail

REPO="${PW_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
DEST="${PW_BACKUP_DIR:-/var/backups/polarwindow}"
KEEP_DAYS="${PW_BACKUP_KEEP_DAYS:-7}"

cd "$REPO"
mkdir -p "$DEST"
chmod 700 "$DEST"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$DEST/polar_window-$stamp.dump"

docker compose exec -T postgres pg_dump -U postgres -d polar_window -Fc > "$out.part"
# A dump pg_restore cannot list is no backup.
docker compose exec -T postgres pg_restore -l < "$out.part" > /dev/null
mv "$out.part" "$out"
chmod 600 "$out"
echo "backup: $out ($(du -h "$out" | cut -f1))"

find "$DEST" -maxdepth 1 -name 'polar_window-*.dump' -mtime +"$KEEP_DAYS" -print -delete
find "$DEST" -maxdepth 1 -name 'polar_window-*.dump.part' -mmin +120 -delete
df -h "$DEST" | tail -1
