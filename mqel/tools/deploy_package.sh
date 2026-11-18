#!/usr/bin/env bash
# Client-Archiv für den VPS: die Teile von client/ (nicht im Repo), die der
# Server liest - Regeln, UI-Dateien für die UI-Patches, Steam-Exe und Boot.tsc
# für den Patcher, Spieler-Exe, Launcher-Hintergrund. Der Code kommt per git.
#
# Gebrauch:  tools/deploy_package.sh [Ziel.tar.gz]   (Vorgabe mqel-client.tar.gz)
# Auf dem VPS (in /opt/mqel, dem git-Klon):  tar -xzf mqel-client.tar.gz
# Neu bauen nur, wenn sich client/ ändert (z. B. neue Spieler-Exe).
set -euo pipefail
cd "$(dirname "$0")/.."
out=$(realpath -m "${1:-mqel-client.tar.gz}")
tar -czf "$out" --owner=0 --group=0 \
    client/GameData/Data/GameplaySettings \
    client/GameData/Data/UI \
    client/GameData/Bin/Boot.tsc \
    client/GameData/Bin/MightyQuest.exe \
    client/GameData/Bin/MightyQuest_player.exe \
    client/Launcher/DefaultBackground.png
echo "$out ($(du -h "$out" | cut -f1))"
