# Quellen-Inventar

Alle Dateien liegen in `cdn/` als `.7z`-Archive (Ubisoft „Release Management“-
Pakete, Stand ca. Juli 2015, Client-Version `0.36.1.34.0`).

| Archiv | Größe | Inhalt |
|---|---|---|
| `0.36.1.34.0_104956_GameData.7z` | ~930 MB | **Spieldaten**: `Bin/` (CEF, `mightyquest-ui.exe`, Engine-DLLs), `Config/Game/*.json`, `Data/GameplaySettings/` (~8700 `.json` — alle Item-/Spell-/KI-/Shop-Specs), `Data/Scripts/*.tsc` (Boot-/Init-Skripte), `Data/Generated/`, `Bigfiles/PC` |
| `0.36.1.34.0_276072_PublicLauncher.7z` | ~40 MB | **Launcher**: `PublicLauncher.exe` (Qt, Patching, startet das Spiel), `LauncherPatcher.exe`, `MQELDiagnostics.exe`, `Util.Common.Json.dll`, `PublicLauncherSettings.Template.json` |
| `0.36.1.34.0_280139_Game.7z` | ~26 MB | **Spiel-Binaries**: `MightyQuest.exe` (gepackt, UBX-Protektor), `MightyQuestWorker.exe` (ungepackt), je `*_profile.exe`-Variante |
| `0.36.1.34.0_280139_GameUI.7z` | ~4 MB | **UI-Assets**: `Data/UI/*` (Bilder, HTML-Lobbyseiten) |
| `main.348.1_232184_GameplayToolbox.7z` | ~18 MB | **Server-Seite + Admin-Tool**: `GameplayToolbox.exe` (WinForms: Castle Im-/Export, Account-Templates, braucht `GameServerUrl`), `HyperQuest.GameServer*.dll` (komplette Serverlogik als .NET-Assembly), `HyperQuest.GameServer.Contracts*.dll` + `.xml` (API-Verträge mit Doku), `Util.*.dll` (HTTP-Framework, JSON, Mongo/Couchbase/Redis), `Contracts.Common*.dll`, `app.config.template.json`, PDBs |

## Zur „GameplayToolbox“-Frage

`main.*.7z` enthält **keinen lauffähigen Gameserver** (keine Exe, kein Hosting,
keine Config mit ConnectionStrings). Es enthält aber:

1. `HyperQuest.GameServer.dll` (~8 MB) — die **komplette Server-Geschäftslogik**
   (Services-Implementierungen, Angriffsvalidierung, Castle-Verwaltung, …).
2. `HyperQuest.GameServer.Contracts.dll` + `.xml` — alle **DTOs und
   Service-Interfaces mit Dokumentation** (1388 Einträge).
3. `Util.Server.dll` / `Util.Client.dll` / `Util.Common.Service.dll` — das
   **HTTP+JSON-RPC-Framework** (URL-Aufbau, Routing, HMAC, Envelopes).
4. `GameplayToolbox.exe` — Admin-Client, der gegen einen laufenden Server
   spricht (Castle Im-/Export, Account-Templates, Reports).

Damit ist der Nachbau **ohne Raten** möglich: Protokoll, API und große Teile
der Regeln sind aus den Assemblies ablesbar. Was fehlt: Laufzeitdaten
(Accounts, Burgen, DB-Inhalte) und die Live-Betriebsservices
(Ubiservices-Login, Facebook, ejabberd-Chat, S3).

## Fremddaten

- **Länder-Datenbank** für den CountryCode neuer Spieler (`server/geoip.py`):
  [IP to Country Lite](https://db-ip.com) von DB-IP, Lizenz CC BY 4.0.
  Nicht im Repository; `python tools/update_geoip.py` lädt sie nach
  `server/data/geoip-country.csv.gz` (monatlich neu).
