# Architecture

## Client processes

```text
PublicLauncher.exe
  │  -server_url <GameServerUrl> -token <LoginToken> -email <Mail>
  │  -environmentName <Env> -httpCompression <0/1> [-steamid … -steamticket …]
  ▼
MightyQuest.exe  (UBX-packed, see box below; contains: HTTP client
  │               (WinHTTP/libcurl), CEF UI binding, master logic)
  │  -compipe <NamedPipe> (+ same args)
  ▼
MightyQuestWorker.exe  (unpacked, normal .text)
  │  simulation/gameplay, GameServer DTO serializer (Argo-generated,
  │  path …\GameServerProxies\Contracts\HW_ANTICHEAT_MASTER\…),
  │  writes attack JSON + replay files
  │  (cf. string "[JsonDirectory] [attackInfoJsonPath]
  │   [replayCommandFilePath] [endAttackParamsPath]")
  │  NO sockets (named pipes only: PeekNamedPipe/SetNamedPipeHandleState)
  ▼ (pipe)
MightyQuest.exe  ──HTTP──▶ GameServerUrl
mightyquest-ui.exe (CEF render process for the lobby/shop UI)
```

Evidence:

- Launcher strings: `..\GameData\Bin\MightyQuest.exe`, args `-email`,
  `-environmentName`, `-httpCompression`, `-server_url`, `-token`,
  `-steamid`, `-steamticket` (`PublicLauncher.exe`, also worker imports).
- `Init_Game.tsc`: `NetworkInit` → `ServerSignIn` (engine steps, details in
  the packed master).
- Worker PDB path: `…\Startup\MightyQuest_original.pdb` vs. master —
  master was packed afterwards; worker was not.

> **Box: "UBX" and the unpacked variants.**
> `MightyQuest.exe` has the PE sections `.UBX0`/`.UBX1`: `.text`,
> `.rdata`, `.data` and `.UBX0` are empty (`SizeOfRawData = 0`, pure
> placeholders), the complete payload (~7.9 MB, entropy 7.98 ≈
> encrypted) is in `.UBX1` (flags RWE), which also contains the entry point.
> The import table is a stub (1 function per DLL), plus a TLS callback
> (runs before the entry point — a typical unpacker/anti-debug technique).
> This is the classic pattern of a **PE packer/protector** (cf. UPX with
> `.UPX0`/`.UPX1`), except that "UBX" is not documented anywhere publicly
> (not UPX/Themida/VMProtect) — so most likely an **Ubisoft-internal build
> protection step**, especially since no other binary in the package
> (launcher, worker, UI, tools) is packed like this.
> **In practice it does not matter:** the same package contains
> `MightyQuest_release.exe` (38 MB) and `MightyQuest_profile.exe` (27 MB) —
> **unpacked full builds** with ~29 MB `.text`, a complete import table
> (WINHTTP, WS2_32, libcef, …) and ~115,000 plain-text strings including
> the complete Argo HTTP stack (`Argo::HttpSessionCurl`, `ArgoServiceTask`,
> all `*.hqs` service names). Static analysis of the client is therefore done
> on the `_release` variant; `MightyQuest.exe` only matters for live
> operation (it unpacks itself into memory at runtime — a memory dump is
> possible). On Windows the revival uses a certificate-patched
> `MightyQuest_profile.exe` as the player exe (`05-windows-setup.md`).

## Server side (original)

```text
IIS / ASP.NET (System.Web)
  ServiceHttpHandler  (IHttpHandler; route = AppRelativeCurrentExecutionFilePath
  │                     → Castle Windsor component "~/<ServiceName>")
  ServiceRequestProcessor (per service; map "/<MethodName>" → processor;
  │                        optional HMAC on the private port)
  ├─ GetHttpJsonRequestProcessor    (GET,  query → typed params)
  ├─ PostHttpJsonRequestProcessor   (POST, JSON body {"param":…} → DTO)
  ├─ GetHttpStreamRequestProcessor  (GET,  replay/binary download)
  ├─ PostHttpStreamRequestProcessor (POST, replay upload + JSON)
  └─ GetHttpHtmlRequestProcessor    (Facebook OAuth callback)
        │ Castle DynamicProxy interceptor chain per call:
        ▼
  AuthenticationInterceptor ([Authenticated]: ConnectionToken via header "t",
        optional client HMAC "h"/"i"), CheckServiceVersionInterceptor ("v"),
        cache/profiling/validation interceptors
        ▼
  HyperQuest.GameServer.* (business/DAL/assembler)
        ▼
  MongoDB (primary DAL) → migrated to Couchbase (accounts, castles, challenges,
    presence, …), Redis/BookSleeve (cache, locks, Lua scripts, e.g.
    `as:castle:*`), ejabberd via XML-RPC (chat/presence, CookComputing),
    AWS S3 (account archives, crash reports), MySQL (DistributionService),
    Facebook Graph API, SleepyGiant/Ubiservices (account backend).
```

- The toolkit's `app.config.template.json` shows the server config:
  `BranchName`, `GameEnvironmentName`, `GameServerUrl`,
  `GameplaySettingsPath`, `NewsSettingsPath`, `RootSettingsPath`,
  `HMACAccessKeyID`, `HMACSecret` — the server reads its **game rules as
  JSON from disk** (the same files as in `GameData.7z`).
- `GameServerFacility`/`GameServerInstaller` (Castle Windsor) wire everything
  together; `GameServerBloombergInterface` = crash reporting (irrelevant for
  the revival).

## Server side (revival)

A single Python 3 process (`server/game_server.py`, standard library; only
`tools/make_local_cert.py` needs `cryptography`) serves:

- the game API (`/<Service>.hqs/<Method>`) on HTTP 8081 and HTTPS 8443,
- the launcher login page (`/launcher/`), the patcher (`/patcher`) and the
  admin web tool (`/admin`),
- persistence as JSON files in `server/state/<profile>/`.

A second process, `server/xmpp_server.py`, is a minimal XMPP chat server on
port 5222. On Windows both are started by `start_servers.bat` and stopped by
`stop_servers.bat`.

## External dependencies (original) and revival strategy

| Dependency | Purpose | Strategy |
|---|---|---|
| Ubiservices/SleepyGiant login, launcher website | `LoginToken` (cookie `t`), shop purchases | **Replaced**: own login page + `ValidateToken`; tokens issued by our server |
| MongoDB / Couchbase / Redis | Persistence | **Replaced**: JSON files per account in `server/state/` |
| ejabberd (chat/presence) | Lobby chat, guilds | **Replaced**: own minimal XMPP server (`server/xmpp_server.py`) |
| Facebook OAuth | Account linking, avatars | **Disabled** |
| S3 (AWS) | Archives, crash reports | **Stubbed** (store locally / ignore) |
| `http://localhost/gamedata/` | Lobby/shop UI (CEF loads `http://localhost/gamedata/…`, see `WebviewManager::Initialize`) | **Not needed**: the client serves the prefix itself (CEF handler in `CEFClient_Z.cpp` → `../Data`); confirmed in game, no web server needed |
| Bloomberg crash reporting | Crash reports | **Ignored** |
| Steamworks (`steam_api.dll`) | Steam tickets, achievements | Optional; Steam login supported (`server/steam_auth.py`), direct start without Steam possible |
