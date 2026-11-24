# Windows Setup (working configuration)

Status: 2026-11-20. This is the setup that is confirmed working on Windows 11:
the launcher logs in, the patcher installs the game exe, the game connects over
HTTPS, loads the account and buys the startup castle.

All paths below are relative to the project folder (`MQEL-Windows-Build\`).

## How it fits together

```text
Steam / PublicLauncher.exe (patched with steam-launcher-patch.cmd)
  │  reads Launcher\PublicLauncherSettings.json
  │
  ├─ http://127.0.0.1:8081/launcher/          login page (sets the session token)
  ├─ http://127.0.0.1:8081/patcher            installs MightyQuest_local.exe,
  │                                           UI patches and checksum lists
  ├─ http://127.0.0.1:8081/launcher/maintenance
  ▼
GameData\Bin\MightyQuest.exe  (= MightyQuest_local.exe from the patcher)
  │  -server_url https://127.0.0.1:8443 -token <session token> -email <name>@mqel.local
  ├─ HTTPS 127.0.0.1:8443   game server (server\game_server.py)
  └─ XMPP  127.0.0.1:5222   chat server (server\xmpp_server.py, plain text)
```

Why HTTPS is needed: the final `MightyQuest.exe` refuses any `http://` server
URL and only trusts four CA certificates baked into the exe, none of which issue
certificates any more. The fix is to bake our own self-signed certificate into
the unpacked `MightyQuest_profile.exe` (`tools\patch_ca.py`) and let the patcher
hand that exe to the launcher as `MightyQuest.exe` (details: `60-client.md`).

## Prerequisites

- **Python 3.9+** from <https://www.python.org/downloads/> (tested with 3.15),
  "Add to PATH" enabled. `start_servers.bat` also accepts the `py` launcher.
- **`cryptography`** package, only for creating the certificate:
  `python -m pip install cryptography`
- **7-Zip** is optional (the patcher uses it to build archives if present).
- Game client 0.36.1.34.0 (Steam depot / full client). Older clients
  (e.g. 0.23.0.59.0) do not work.
- DirectX June 2010 runtime and VC++ 2010/2012 x86 redistributables
  (`Launcher\Installer\Prerequisites\` of the full client, or
  `..\directx_Jun2010_redist\`) if the game does not start.

## One-time setup

### 1. Server data

`client\GameData\Data\GameplaySettings\` must contain the ~8700 gameplay JSON
files (incl. `GeneralSettings\SpecialPackSettings.json`). If the server stops
with `FileNotFoundError` for a settings file, extract the gameplay settings
archive into that folder.

### 2. Certificate and patched game exe

Run from the project folder (PowerShell or cmd):

```bat
python tools\make_local_cert.py
python tools\patch_ca.py <path>\MightyQuest_profile.exe server\state\tls\cert.pem --out server\state\tls\MightyQuest_local.exe --no-fps
```

- `make_local_cert.py` writes `server\state\tls\cert.pem` + `key.pem`
  (CN=MQEL, valid 10 years, for `127.0.0.1`, `localhost` and this PC's LAN IP;
  add more with `--ip 192.168.1.50`; `--force` replaces an existing one).
  No OpenSSL installation is needed.
- `MightyQuest_profile.exe` is the unpacked build from the Game package
  (`0.36.1.34.0_280139_Game.7z`, ~27 MB). Do **not** use the packed 8 MB
  `MightyQuest.exe` — `patch_ca.py` needs the four embedded certificates.
- `--no-fps` removes the always-on FPS counter of the profile build.

`start_servers.bat` detects `server\state\tls\MightyQuest_local.exe` and then
enables HTTPS on port 8443 and the exe distribution automatically.

### 3. Point the game installation at the local server

In the game installation folder (Steam install or a copy such as
`client-steam\`):

1. Let Steam verify the game files first (resets
   `LauncherData\InstalledPackages.json` to the Steam state, so the patcher's
   deltas apply).
2. Replace `Launcher\PublicLauncherSettings.json` with:

   ```json
   {
     "LauncherWebSiteUrl": "http://127.0.0.1:8081/launcher/",
     "GameServerUrl": "https://127.0.0.1:8443",
     "PatcherServiceUrl": "http://127.0.0.1:8081/patcher",
     "BackgroundImageUrl": "http://127.0.0.1:8081/launcher/background.png",
     "MaintenanceModeVerificationUrl": "http://127.0.0.1:8081/launcher/maintenance",
     "EnvironmentName": "mqel-live",
     "EnableConsoleWin": false,
     "LogLevel": 0,
     "WindowWidth": 822,
     "WindowHeight": 600,
     "ViewTop": 0,
     "ViewLeft": 0,
     "ViewWidth": 787,
     "ViewHeight": 552,
     "HttpCompression": "false",
     "TwitterFeedName": "",
     "TwitterFeedWidgetID": ""
   }
   ```

   (`website\PublicLauncherSettings.json` is the same file for the public
   server domain; for a LAN server replace `127.0.0.1` with the server's IP and
   create the certificate with `--ip <that IP>`.)
3. Copy `steam-launcher-patch.cmd` into the installation folder and
   double-click it. It patches `Launcher\PublicLauncher.exe` so that the
   launcher accepts our updates even when started from Steam (otherwise it
   shows "Please update via the Steam client" and exits).
4. Optional, only for the in-game Bling shop over HTTPS: import the certificate
   into the Windows user store so CEF trusts it:
   `certutil -addstore -user Root server\state\tls\cert.pem`

## Daily use

| Step | Command |
|---|---|
| Start servers | `start_servers.bat` (game server 8081 + 8443, XMPP 5222; each in its own minimized window, so you can close the starter window) |
| Play | Start the game from Steam (or `Launcher\PublicLauncher.exe`), log in or register on the launcher page, click Play |
| Stop servers | `stop_servers.bat` (finds the Python processes by command line) |

First start after a server change: the launcher downloads the patched exe,
UI patches and checksum lists, then starts the game.

### Useful URLs

- Login page: <http://127.0.0.1:8081/launcher/>
- Admin web tool: <http://127.0.0.1:8081/admin> (from the local machine; from
  other networks only via HTTPS and `--admin-net <CIDR>`)
- Game server (HTTPS): <https://127.0.0.1:8443>

### Direct launch without the launcher (debugging)

`launch_game.bat` (→ `launch_game.ps1`) logs in at `/launcher/login`, gets a
real session token and starts the client:

```powershell
launch_game.bat
launch_game.bat -ClientDir "E:\...\client-steam\GameData\Bin"
launch_game.bat -ServerUrl https://127.0.0.1:8443
```

The default `-ClientDir` is `client-debug\GameData\Bin`; adjust it to your
client folder. Note: the packed ship `MightyQuest.exe` exits on `http://`
URLs, so either use the patched exe with `https://127.0.0.1:8443` or an
unpacked build (`MightyQuest_release.exe`/`_profile.exe`) with
`http://127.0.0.1:8081`. A fake token such as `-token test` only works because
`start_servers.bat` passes `--names-as-tokens` (then the account *name* is
accepted as token from 127.0.0.1).

Logging in again (launcher page or script) ends the previous session — one
session per account.

## Server options (`server\game_server.py`)

`start_servers.bat` runs:

```bat
python -u server\game_server.py --host 127.0.0.1 --port 8081 --profile new --names-as-tokens ^
       --tls-port 8443 --client-exe server\state\tls\MightyQuest_local.exe
```

| Option | Meaning |
|---|---|
| `--host`, `--port` | HTTP listen address (default `127.0.0.1:8081`); use `0.0.0.0` for LAN play |
| `--tls-port 8443` | additional HTTPS port (required by the ship exe) |
| `--tls-cert`, `--tls-key` | real certificate chain instead of the self-signed one |
| `--client-exe <exe>` | game exe that the patcher installs as `MightyQuest.exe` |
| `--profile full\|fresh\|new` | account template / state folder `server\state\<profile>\` |
| `--state <dir>` | use a different player directory (tests) |
| `--names-as-tokens` | dev only: accept a login name as `-token` |
| `--admin-net <CIDR>` | allow `/admin` from that network (HTTPS only) |
| `--seasonal-event <Name>` | force a seasonal event, e.g. `Halloween` |
| `--free-trial <hero>` / `--free-trial-minutes` | force a hero trial (2 Knight, 3 Archer, 4 Mage, 5 Runaway) |
| `--keep-unknown-versions` | report unknown installed package versions as current |
| `--web-port`, `--web-tls-port`, `--web-cert`, `--web-key` | serve the project website from `website\` |
| `--log`, `--responses`, `--tcp-ports` | request log, response overrides, honeypot ports |

## Files and logs

| Path | Content |
|---|---|
| `game_server.log`, `xmpp_server.log` | console output of the two servers (project folder) |
| `server\requests.log.jsonl` | every request/response (JSONL) |
| `server\state\new\` | player state: `<AccountId>.json`, `players.json`, `logins.json`, `balance.json`, tracking logs; delete = reset |
| `server\state\tls\` | `cert.pem`, `key.pem`, `MightyQuest_local.exe` |
| `client\GameData\Bin\MQLog.txt`, `NetworkLog.Txt` | game client logs |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `start_servers.bat`: "Something is already listening on port 8081" | servers already running; run `stop_servers.bat` first |
| Game closes right after the Ubisoft logo | server URL is `http://` with the ship exe, or the exe does not contain our certificate → check that the patcher installed `MightyQuest_local.exe` and `GameServerUrl` is `https://127.0.0.1:8443` |
| `[tls] Handshake ... failed: WinError 10054` in the log | a client that does not trust our certificate (unpatched exe, or the launcher/CEF without `certutil` import); harmless if the game itself connects |
| `401 InvalidConnectionTokenException` | client was started with a token the server did not issue; use the launcher or `launch_game.bat` |
| "Please update via the Steam client" | `steam-launcher-patch.cmd` not applied |
| Launcher hangs at "Checking Game Packages Version..." / patch errors | `InstalledPackages.json` does not match the files; let Steam verify the files and start again |
| Launcher crashes after a patch ("CRC mismatch") | exe was replaced by hand; let the patcher deliver it (`--client-exe`) instead |
| Lobby loads forever | `Data\UI\Js` and `Data\UI\scripts` from the GameUI package are missing |
| `FileNotFoundError` for a settings JSON on server start | gameplay settings not extracted (step 1) |
| `[http] Request timed out` lines | idle keep-alive connections closing; harmless |
| `DeprecationWarning: ssl.TLSVersion.TLSv1` | intentional (the 2015 CEF only speaks TLS 1.0/1.1); harmless |
| `pip install cryptography` fails | use `python -m pip install --user cryptography`, or the same Python that runs the server |

## Next: public server

To let other people join over the internet with their Steam account, see
[06-public-server.md](06-public-server.md) (`server_config.bat`,
`tools\setup_public_server.ps1`, router port forwarding, `player-pack.zip`).
