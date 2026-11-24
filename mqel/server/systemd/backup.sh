#!/bin/sh
# Offsite-Backup von server/state nach Cloudflare R2 (S3-kompatibel) per rclone.
# Läuft über mqel-backup.timer; Zugangsdaten in /etc/mqel-backup.env (siehe
# mqel-backup.service). Alte Stände löscht eine Lifecycle-Regel im R2-Bucket.
# Die Spielstände werden atomar ersetzt (os.replace), Packen im Betrieb ist sicher.
set -eu
src=/path/mqel/mqelrevival/server/state/
name="mqel-state-$(date -u +%Y%m%d-%H%M%S).tar.gz"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# tls/: kommt von certbot neu; *.tmp: halbe Schreibvorgänge.
# Exit 1 = "Datei während des Lesens geändert" (Logs), kein Fehler.
tar -czf "$tmp/$name" -C "$src" --exclude=./tls --exclude='*.tmp' . || [ $? -eq 1 ]
rclone copyto --s3-no-check-bucket "$tmp/$name" "r2:$R2_BUCKET/$name"
echo "hochgeladen: $name ($(du -h "$tmp/$name" | cut -f1))"
