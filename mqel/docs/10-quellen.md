# Source Inventory

All files are `.7z` archives in `cdn/` (Ubisoft "Release Management"
packages, as of about July 2015, client version `0.36.1.34.0`).

| Archive | Size | Content |
|---|---|---|
| `0.36.1.34.0_104956_GameData.7z` | ~930 MB | **Game data**: `Bin/` (CEF, `mightyquest-ui.exe`, engine DLLs), `Config/Game/*.json`, `Data/GameplaySettings/` (~8700 `.json` — all item/spell/AI/shop specs), `Data/Scripts/*.tsc` (boot/init scripts), `Data/Generated/`, `Bigfiles/PC` |
| `0.36.1.34.0_276072_PublicLauncher.7z` | ~40 MB | **Launcher**: `PublicLauncher.exe` (Qt, patching, starts the game), `LauncherPatcher.exe`, `MQELDiagnostics.exe`, `Util.Common.Json.dll`, `PublicLauncherSettings.Template.json` |
| `0.36.1.34.0_280139_Game.7z` | ~26 MB | **Game binaries**: `MightyQuest.exe` (packed, UBX protector), `MightyQuestWorker.exe` (unpacked), each with a `*_profile.exe` variant |
| `0.36.1.34.0_280139_GameUI.7z` | ~4 MB | **UI assets**: `Data/UI/*` (images, HTML lobby pages) |
| `main.348.1_232184_GameplayToolbox.7z` | ~18 MB | **Server side + admin tool**: `GameplayToolbox.exe` (WinForms: castle import/export, account templates, needs `GameServerUrl`), `HyperQuest.GameServer*.dll` (complete server logic as .NET assembly), `HyperQuest.GameServer.Contracts*.dll` + `.xml` (API contracts with docs), `Util.*.dll` (HTTP framework, JSON, Mongo/Couchbase/Redis), `Contracts.Common*.dll`, `app.config.template.json`, PDBs |

## About the "GameplayToolbox"

`main.*.7z` contains **no runnable game server** (no exe, no hosting, no config
with connection strings). It does contain:

1. `HyperQuest.GameServer.dll` (~8 MB) — the **complete server business logic**
   (service implementations, attack validation, castle management, …).
2. `HyperQuest.GameServer.Contracts.dll` + `.xml` — all **DTOs and service
   interfaces with documentation** (1388 entries).
3. `Util.Server.dll` / `Util.Client.dll` / `Util.Common.Service.dll` — the
   **HTTP+JSON RPC framework** (URL building, routing, HMAC, envelopes).
4. `GameplayToolbox.exe` — admin client that talks to a running server
   (castle import/export, account templates, reports).

This makes the re-implementation possible **without guessing**: protocol, API
and large parts of the rules can be read from the assemblies. What is missing:
runtime data (accounts, castles, database contents) and the live operation
services (Ubiservices login, Facebook, ejabberd chat, S3).

## Third-party data

- **Country database** for the CountryCode of new players (`server/geoip.py`):
  [IP to Country Lite](https://db-ip.com) by DB-IP, license CC BY 4.0.
  Not in the repository; `python tools\update_geoip.py` downloads it to
  `server/data/geoip-country.csv.gz` (updated monthly).
