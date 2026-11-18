#!/bin/sh
# certbot-Deploy-Hook: neues Zertifikat dorthin kopieren, wo der Dienst
# (Benutzer mqel) es lesen darf, und den Spielserver neu starten.
# Installation: cp server/systemd/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/mqel.sh
set -e
dir=/opt/mqel/server/state/tls/le
install -d -o mqel -g mqel -m 700 "$dir"
install -o mqel -g mqel -m 600 "$RENEWED_LINEAGE/fullchain.pem" "$RENEWED_LINEAGE/privkey.pem" "$dir/"
systemctl restart mqel-game
