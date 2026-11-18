# Architektur

## Client-Prozesse

```text
PublicLauncher.exe
  │  -server_url <GameServerUrl> -token <LoginToken> -email <Mail>
  │  -environmentName <Env> -httpCompression <0/1> [-steamid … -steamticket …]
  ▼
MightyQuest.exe  (UBX-verpackt, s. Kasten unten; enthält: HTTP-Client
  │               (WinHTTP/libcurl), CEF-UI-Anbindung, Master-Logik)
  │  -compipe <NamedPipe> (+ gleiche Args)
  ▼
MightyQuestWorker.exe  (ungepackt, .text normal)
  │  Simulation/Gameplay, GameServer-DTO-Serializer (Argo-generiert,
  │  Pfad …\GameServerProxies\Contracts\HW_ANTICHEAT_MASTER\…),
  │  schreibt Angriffs-JSON + Replay-Dateien
  │  (vgl. String "[JsonDirectory] [attackInfoJsonPath]
  │   [replayCommandFilePath] [endAttackParamsPath]")
  │  KEINE Sockets (nur Named Pipes: PeekNamedPipe/SetNamedPipeHandleState)
  ▼ (Pipe)
MightyQuest.exe  ──HTTP──▶ GameServerUrl
mightyquest-ui.exe (CEF-Renderprozess für die Lobby-/Shop-UI)
```

Belege:

- Launcher-Strings: `..\GameData\Bin\MightyQuest.exe`, Args `-email`,
  `-environmentName`, `-httpCompression`, `-server_url`, `-token`,
  `-steamid`, `-steamticket` (`PublicLauncher.exe`, ebenso Worker-Importe).
- `Init_Game.tsc`: `NetworkInit` → `ServerSignIn` (Engine-Steps, Details im
  gepackten Master).
- Worker-PDB-Pfad: `…\Startup\MightyQuest_original.pdb` vs. Master —
  Master nachträglich verpackt; Worker nicht.

> **Kasten: „UBX“ und die unverpackten Varianten.**
> `MightyQuest.exe` trägt die PE-Sektionen `.UBX0`/`.UBX1`: `.text`,
> `.rdata`, `.data` und `.UBX0` sind leer (`SizeOfRawData = 0`, reine
> Platzhalter), die komplette Nutzlast (~7,9 MB, Entropie 7,98 ≈
> verschlüsselt) liegt in `.UBX1` (Flags RWE), die auch den Entry-Point
> enthält. Die Import-Tabelle ist ein Stub (1 Funktion pro DLL), dazu ein
> TLS-Callback (läuft vor dem Entry-Point — typische
> Entpacker-/Anti-Debug-Technik). Das ist das klassische Muster eines
> **PE-Packers/-Protektors** (vgl. UPX mit `.UPX0`/`.UPX1`), nur dass „UBX“
> öffentlich nirgends dokumentiert ist (kein UPX/Themida/VMProtect) —
> also mit hoher Wahrscheinlichkeit ein **Ubisoft-interner
> Build-Schutzschritt**, zumal kein anderes Binary im Paket (Launcher,
> Worker, UI, Tools) so verpackt ist.
> **Praktisch egal:** Im selben Paket liegen `MightyQuest_release.exe`
> (38 MB) und `MightyQuest_profile.exe` (27 MB) — **unverpackte
> Voll-Builds** mit ~29 MB `.text`, vollständiger Import-Tabelle
> (WINHTTP, WS2_32, libcef, …) und ~115.000 Klartext-Strings inkl.
> des kompletten Argo-HTTP-Stacks (`Argo::HttpSessionCurl`,
> `ArgoServiceTask`, alle `*.hqs`-Service-Namen). Statische Analyse des
> Clients läuft daher gegen die `_release`-Variante; `MightyQuest.exe`
> ist nur für den Live-Betrieb relevant (entpackt sich zur Laufzeit in
> den Speicher — Memory-Dump möglich).

## Server-Seite (Original)

```text
IIS / ASP.NET (System.Web)
  ServiceHttpHandler  (IHttpHandler; Route = AppRelativeCurrentExecutionFilePath
  │                     → Castle-Windsor-Komponente "~/<ServiceName>")
  ServiceRequestProcessor (pro Service; Map "/<MethodName>" → Prozessor;
  │                        optional HMAC auf Privat-Port)
  ├─ GetHttpJsonRequestProcessor    (GET,  Query → typisierte Params)
  ├─ PostHttpJsonRequestProcessor   (POST, JSON-Body {"param":…} → DTO)
  ├─ GetHttpStreamRequestProcessor  (GET,  Replay-/Binär-Download)
  ├─ PostHttpStreamRequestProcessor (POST, Replay-Upload + JSON)
  └─ GetHttpHtmlRequestProcessor    (Facebook-OAuth-Callback)
        │ Castle DynamicProxy-Interceptor-Kette pro Call:
        ▼
  AuthenticationInterceptor ([Authenticated]: ConnectionToken via Header "t",
        optional Client-HMAC "h"/"i"), CheckServiceVersionInterceptor ("v"),
        Cache-/Profiling-/Validation-Interceptor
        ▼
  HyperQuest.GameServer.* (Business/DAL/Assembler)
        ▼
  MongoDB (Primär-DAL) → migriert auf Couchbase (Accounts, Burgen, Challenges,
    Presence, …), Redis/BookSleeve (Cache, Locks, Lua-Skripte, z. B.
    `as:castle:*`), ejabberd per XML-RPC (Chat/Presence, CookComputing),
    AWS S3 (Account-Archive, CrashReports), MySQL (DistributionService),
    Facebook Graph API, SleepyGiant/Ubiservices (Account-Backend).
```

- `app.config.template.json` des Toolkits zeigt die Server-Config:
  `BranchName`, `GameEnvironmentName`, `GameServerUrl`,
  `GameplaySettingsPath`, `NewsSettingsPath`, `RootSettingsPath`,
  `HMACAccessKeyID`, `HMACSecret` — der Server liest seine **Game-Regeln als
  JSON von Platte** (dieselben Dateien wie in `GameData.7z`).
- `GameServerFacility`/`GameServerInstaller` (Castle Windsor) verdrahten alles;
  `GameServerBloombergInterface` = Crash-Reporting (für Revival irrelevant).

## Externe Abhängigkeiten (Original) und Revival-Strategie

| Abhängigkeit | Wofür | Strategie |
|---|---|---|
| Ubiservices/SleepyGiant-Login, Launcher-Website | `LoginToken` (Cookie `t`), Shop-Kauf | **Ersetzen**: eigene Login-Seite + `ValidateToken`-Stub; Token frei vergeben |
| MongoDB / Couchbase / Redis | Persistenz | **Ersetzen**: eigene Persistenz (SQLite/Postgres o. ä.); Datenmodell aus `Entities.xml` + DAL-Nutzung ableitbar |
| ejabberd (Chat/Presence) | Lobby-Chat, Gilden | **Stubben/deaktivieren** (`ChatEnabled=false` in Settings) oder Standard-XMPP |
| Facebook OAuth | Login-Verknüpfung, Avatare | **Deaktivieren** |
| S3 (AWS) | Archive, CrashReports | **Stubben** (lokal speichern / ignorieren) |
| `http://localhost/gamedata/` | Lobby-/Shop-UI (CEF lädt `http://localhost/gamedata/…`, s. `WebviewManager::Initialize`) | **Entfällt**: der Client bedient das Präfix selbst (CEF-Handler in `CEFClient_Z.cpp` → `../Data`); im Spiel bestätigt, kein Webserver nötig |
| Bloomberg-Crashreporting | Crash-Reports | **Ignorieren** |
| Steamworks (`steam_api.dll`) | Steam-Tickets | Optional; Direktstart ohne Steam möglich |
