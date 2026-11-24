# Client Folder (`client/`)

Ready-to-play tree, assembled from the release archives (GameData extraction
+ merge steps, see `BUILD.md`). The GameplayToolbox is deliberately **not**
included (server/admin tool, not needed by players). Windows setup:
`05-windows-setup.md`.

## Layout

```text
client/
  BUILD.md                 How the tree was built (package → target)
  GameData/                ← 0.36.1.34.0_104956_GameData.7z + …_GameUI.7z
    Bin/                   Engine binaries, CEF, Boot.tsc, gear.ini
      MightyQuest.exe            ← from the Game package (packed ship binary)
      MightyQuest_release.exe    ← unpacked, for analysis/debugging
      MightyQuest_profile.exe    ← unpacked (profiling build; base of the player exe)
      MightyQuestWorker*.exe     ← simulation worker (3 variants)
      mightyquest-ui.exe         CEF render process (lobby/shop UI)
      steam_api.dll, libcef.dll, …
    Config/Game/*.json     Engine/user settings (e.g. UserSettings.json)
    Data/GameplaySettings/ ~8700 rule JSONs (items, spells, shop, …)
    Data/Scripts/*.tsc     Boot/init scripts (boot via Bin/Boot.tsc)
    Data/Generated/        Generated assets
    Data/UI/               ← from the GameUI package (lobby images, HTML)
    Bigfiles/PC            Bigfile packages (included via Boot.tsc)
    version.GameData.txt   Package ID "104956"
    version.GameUI.txt     Package ID "280139"
    version.Game.txt       Package ID "280139" (copied from the Game package)
  Launcher/                ← 0.36.1.34.0_276072_PublicLauncher.7z
    PublicLauncher.exe     Qt launcher (patch check, login page, game start)
    PublicLauncherSettings.json   ← generated from the template (local URLs, see below)
    PublicLauncherSettings.Template.json (original template for reference)
    LocalLauncher/         Launcher web UI (HTML/JS/CSS)
    Installer/Prerequisites/ DirectX/VC redists (for player setup)
    LauncherPatcher.exe, MQELDiagnostics.exe, 7z.exe, …
    version.PublicLauncher.txt   Package ID "276072"
  LauncherData/            Launcher runtime data (partly generated)
    InstalledPackages.json Package state (RMClientPackagesVersion, see below)
  Temp/_Launcher/
    LauncherPatcher.exe    Copy (the launcher expects it at
                           ..\Temp\_Launcher\LauncherPatcher.exe)
```

## Ways to start

1. **Via the launcher (player way, works on Windows):**
   `Launcher/PublicLauncher.exe` (or from Steam) with
   `PublicLauncherSettings.json`: `LauncherWebSiteUrl` (login page),
   `PatcherServiceUrl` (version check / patches), `GameServerUrl` (our server,
   `https://…:8443`), `MaintenanceModeVerificationUrl`.
   The launcher starts `..\GameData\Bin\MightyQuest.exe`.
2. **Direct start (revival/debug way):** CWD = `GameData/Bin`,
   `MightyQuest_release.exe -server_url http://127.0.0.1:PORT -token <t>
   -email <mail> -environmentName local -httpCompression 0`
   (more args: `-steamid/-steamticket` only for Steam,
   `-gameLanguage`, `-attackInputMode`, …). The launcher is bypassed. On
   Windows `launch_game.bat` gets a valid token first (see
   `05-windows-setup.md`).

## Launcher and patcher (`server/patcher.py`)

`PublicLauncherSettings.json` points to the game server:
`LauncherWebSiteUrl` = `/launcher/` (login page, sets cookie `t` = token),
`PatcherServiceUrl` = `/patcher`, `MaintenanceModeVerificationUrl` =
`/launcher/maintenance` (empty = no maintenance check). The launcher fetches
this URL at startup via GET (`TaskCheckMaintenance`, response handler
0x4d6813): status 200 = normal, any other status shows the local
`LocalLauncher/launcher-maintenance.html`; the body is not read
(`ProxyMaintenanceInfoModel` with StartTime/EndTime is not used on this path).
In maintenance mode (web tool, `admin.SetMaintenance`, stored in
`state/<profile>/maintenance.json`) the server answers with 503.
`LauncherData/InstalledPackages.json` is an `RMClientPackagesVersion` (enums as
numbers); the Steam installation lists among others GameBin (1) 280139,
DataBin (2) 104956, DataBF (4) per bigfile. The launcher discards an unknown
format.

The server delivers **no game data**, only xdelta deltas (VCDIFF) against the
files of the Steam installation. Package DataBin (version `104956` = Steam,
`104956.<group>` = event) changes the group `OrdinaryDay` in `Bin/Boot.tsc` to
the seasonal event by date (`patcher.EVENTS`, Easter is movable); force it with
`game_server.py --seasonal-event Halloween`. The launcher then starts
`GameData\Bin\MightyQuest.exe` with `-token/-email/-server_url`.
Confirmed in testing (plain-text tree, without Steam mode): the launcher
downloads `2_104956_104956.Halloween.7z` without asking, applies it, the game
shows the Halloween decoration; after the event ends the server offers the way
back `104956.Halloween → 104956`. In Steam mode the launcher refuses patches
("Please update via the Steam client") unless `steam-launcher-patch.cmd` is
applied (see below).

Package CommunityEventSettings (10, same version names) appends to
`Data/GameplaySettings/settings2.bin` a `SkuCommunityEvent` (Id 9000) with the
inactive catalog SKUs of the event (`patcher.EVENT_SKU_KEYWORDS`); the client
unlocks SKUs from SkuCommunityEvents within the time window (that is also how
the Daily Deals worked). The client computes times in 32 bit, the end must be
before 2038. Forward and backward path of both packages confirmed in the
launcher (2026-10-15: `104956 → 104956.Halloween → 104956`, decoration and
shop items come and go). Deltas only fit the reported state: anyone who
changes files or `InstalledPackages.json` by hand can get package state and
file out of sync; after a failed patch the launcher deletes the package entry,
and then the server no longer patches the package (add the entry with the
actual state by hand, or let Steam verify the files). Confirmed for Halloween:
creature variants in the lab and the four barricades in the shop. Not visible:
"Knight Halloween Batwings" (ShopContext 6) and `Halloween_Theme_2013`
(`PrivateTheme`) — leftovers from 2013; the Halloween Pack Oct2014 (pack 67)
contains exactly creatures, barricades and theme 6.

**Game exe and checksums:** after a patch the launcher (`TaskRepair`) checks
every file against `..\GameData\crc\{GameBin,DataBin,
CommunityEventSettings}CRC.json` (CRC32 + size). With a hand-replaced
`MightyQuest.exe` ("CRC mismatch!") it finds no package and crashes (null
pointer 0x4d91a1); a second start went through. That is why the server
distributes the exe itself: `game_server.py --client-exe <exe>` delivers
package GameBin (1, version `280139.X<CRC32>`) as `MightyQuest.exe.replace`
(the launcher deletes the old file and renames, 0x4e2d72; so it fits any
installed exe). Every changed package comes with its checksum list with the
new values (GameCRC 9, DataCRC 7, CommunityEventSettingsCRC 11, same version,
also `.replace`). The lists are not in any archive; the templates are those of
a Steam installation in `server/data/crc/`. The distributed exe is built by
`tools/patch_ca.py MightyQuest_profile.exe <root.pem> --out
<player exe> --no-fps` (own CA, FPS counter off). On Windows the local build
is `server\state\tls\MightyQuest_local.exe`, picked up automatically by
`start_servers.bat`. The UI patches (`server/ui_patches.py`) come as package
GameUI (8, version `280139.U<CRC32>`, whole files via `.replace`); GameUI has
no checksum list. `tools/patch_ui.py` applies the same patches locally.
GameBin also carries the WASD helper as `mqelwasd9_1.dll`, and the exe's
import of `XINPUT9_1_0.dll` is renamed to it (version `280139.V<CRC32>`;
before 2026-11-21 `xinput9_1_0.dll`, `.W`), `.new` or `.replace` depending on
the installed version, not in the checksum list; details in
`80-wasd-keybinds.md`.

**Player setup from the Steam installation** (confirmed 2026-10-17, and on
Windows 11 on 2026-11-20): let Steam verify/repair the installation (this also
resets `LauncherData/InstalledPackages.json` to the Steam state, the depot
contains it), replace `Launcher/PublicLauncherSettings.json` with the version
containing our URLs, and run `steam-launcher-patch.cmd` in the installation
folder. Then start the game from Steam: the patcher brings exe, UI patches,
data and checksum lists, and the game starts. For HTTPS with a self-signed
certificate, additionally the `certutil` import for the launcher/shop (see
below).

**Steam mode** (`SteamAPI_Init` successful, flag `[Launcher+0x61]`, e.g. with
`steam_appid.txt` or started from Steam): when building its state machine the
launcher wires "version old" (game, launcher, repair) directly to `TaskExit`
(`jne` at VA 0x4e10a7/0x4e1135/0x4e1225) and shows dialog 0x4def05 ("Please
update via the Steam client") before that. `steam-launcher-patch.cmd`
(batch/PowerShell hybrid, patches the player's exe, no Ubisoft file on the
website) sets the three `jne` to `nop` and 0x4def05 to `ret`; since then the
launcher patches and starts from Steam too (tested 2026-10-19).

**Steam login** (`server/steam_auth.py`, environment variable
`MQEL_STEAM_API_KEY`, Steam Web API key): the login page has a hidden
`<form>` (target: hidden iframe, `POST /launcher/steam`) and triggers an
artificial `submit` after 0.8 s (only without cookie `t`; checked after the
page has cleared an expired cookie, 2026-11-23: checked before, an expired
login skipped Steam and the launcher had to be started twice); the Steam launcher intercepts it, appends
`steam_ticket` (hex, `GetAuthSessionTicket`) and sends it (without Steam the
ticket stays empty and the page stays silent). The server verifies the ticket
with `ISteamUserAuth/AuthenticateUserTicket` (appid 239220). Known SteamID →
logged in immediately. Unknown → proof (`proof`, 10 min, in memory only):
"Play as a new Steam player" creates an account without a password (name from
the Steam profile, `logins.json`: `SteamId` without `Hash`), or an existing
player logs in once with name + password and thereby links their account. An
account has at most one SteamID and vice versa. Confirmed in testing: the
ticket arrives, Steam returns the SteamID. On Windows, set the key before
starting the servers, e.g. `setx MQEL_STEAM_API_KEY <key>` (new console
needed); without it, name + password login still works.

Steam achievements are set by the game exe itself (`SteamUserStats`
SetAchievement/StoreStats, `SteamId` in `AchievementSettings.json`): live on
`AchievementCompleted` and by reconciling the ones already completed; in
testing all 13 arrived retroactively at the first fight.

`server/settings_archive.py` reads/writes the archive format of
`settings.bin`/`settings2.bin`: encrypted (key stream 0x116ae60)
LZO1X + u32 size, inside a folder tree of JSON files with CRC32 at the end.
Changes at the end of the file leave the beginning byte-for-byte identical
(small xdelta).

Original ship config (Steam): `LauncherWebSiteUrl`
`https://launcher.themightyquest.com/mqel-live/launcher/load/`, `GameServerUrl`
`https://gs.themightyquest.com/mqel-live.gameserver`, `PatcherServiceUrl`
`https://gs.themightyquest.com/mqel-live.distribution`,
`MaintenanceModeVerificationUrl` `https://launcher.themightyquest.com/mqel-live/launcher/`,
`EnvironmentName` `mqel-live`, `HttpCompression` `true`, window 822×588,
view 9/12 787×552, `TwitterFeedName` `Sir_Painhammer`.

**The ship exe needs https:** the final `MightyQuest.exe` compares the server
URL with `"https"` and otherwise runs the script `Exit` (from the memory dump:
ship image base 0x460000, check at 0x7e9b4a, `strncmp(url, "https", 5)`).
The server therefore also serves HTTPS with `--tls-port 8443` (self-signed
certificate in `server/state/tls/`). That alone does not help: the exe only
trusts embedded CAs (DigiCert High Assurance EV Root, COMODO RSA, AddTrust)
and reads neither `SSL_CERT_FILE` (OpenSSL default paths are never loaded) nor
a CA file for curl. Practically nobody issues under these roots any more.
So it does not run without modifying the (packed) exe — hence the patched
`MightyQuest_profile.exe` below.

**HTTPS with `MightyQuest_profile.exe`** (tested 2026-10-17, and on Windows
2026-11-20): the exe (libcurl + OpenSSL 1.0.1e, TLS 1.2) sets
`SSL_VERIFYPEER`/`VERIFYHOST` for `https` URLs (0xfe0f89) and loads its four
PEM roots unpacked from `.rdata` (0xfe145d ff.). `tools/patch_ca.py` replaces
one of them (default: AddTrust) with our own certificate, e.g. the game
server's `server/state/tls/cert.pem` (created by `tools/make_local_cert.py`
on Windows — no OpenSSL needed; valid only for its IPs). With `GameServerUrl` =
`https://…:8443` the game then runs encrypted. The chat (5222) stays plain
text (no STARTTLS). Launcher and Bling shop (CEF, Chromium July 2015) speak
TLS 1.0/1.1 (the server allows it, ECDHE only — hence the harmless
`DeprecationWarning: ssl.TLSVersion.TLSv1` in the log) and verify against the
Windows certificate store: a self-signed certificate must be imported there
(`certutil -addstore -user Root server\state\tls\cert.pem`); with a domain and
Let's Encrypt this is not needed (still untested).

## Known pitfalls

- `Data/UI/Js` + `Data/UI/scripts` from `0.36.1.34.0_280139_GameUI.7z`
  must be extracted too, otherwise the lobby loads forever (272× 404 in
  `static.log`). `http://localhost/gamedata/` is served by the client itself
  (CEF handler `CEFClient_Z.cpp` → `../Data`); a web server on port 80
  is not needed (former `server/static_server.py` removed).
- Data (GameData 104956) and exe (branch Update3) do not match exactly
  (`Unhandled member` warnings, e.g. `Spec.IsVisible`,
  `GeneralSettings.*`).
- **Our client is the final released version**: byte-identical to the final
  Steam depot, built one day before its release (comparison by the project
  owner, 2026-10-16). The server DLLs from the GameplayToolbox archive are
  almost 17 months older (the toolbox's copy, not the live server). Proven by
  build numbers (archive file names) and the newest file dates inside: client
  `280139` (Game/GameUI, 2015-07-21), launcher `276072` (2015-05-22), toolbox
  `main.348.1_232184` (2014-02-27); GameData `104956` counts independently
  (2015-07-17); the server was developed further after that, the final client
  knows fields that are missing there (`MineDestroyedTimeBonusCount`,
  `TrophyScoreRestart*`, `LoseTrophyCooldownTimer`,
  `CastleInfoSummary.TrophyCooldownTimer`). Consequence: game rules and
  formulas from the server code (dnSpy export, local in `decompiled/`); in
  case of differences the client always wins (field readers in the binary,
  `tools/client_members.py -t`), not the contracts.
- Older clients such as `0.23.0.59.0` do not match the server; use the
  0.36.1.34.0 (Steam) client.
- **`client/GameData/Data/UI/Js` and `Css` are the May 2014 UI** (277 files
  differ from GameUI 280139, 103 old files only there); only the TopView
  pages are 2015. The players' Steam install has the 2015 UI. Never patch
  the 2014 copies: `ui_patches.original()` takes the file from
  `server/data/steam/Data/UI` when it is there, so put the 2015 original of
  every newly patched file there first (from
  `0.36.1.34.0_280139_GameUI.7z`, extracted in
  `mqel/ubisoft-mighty-quest-extracted/`). The 2014 competition popup
  shipped this way hung forever (docs/95-preprod-2026-11-22.md).
- `GameplaySettings/CSV/Dim*.csv` (added 2026-11-22 from GameData 104956):
  Ubisoft's analytics tables, reference only (the game doesn't read them).

## Open points (generated at runtime / to verify)

- `Config/Synergy/Game.ini` (`ReadGameConfigFile ..\Config\Synergy\Game.ini`
  in `Init_Game.tsc`) is not in any package — probably generated or optional.
  A dynamic test shows whether/what is missing.
- `GameData/Config/Game/{CustomUserSettings,EngineSettings}.json`
  (+ `.bak`) are created at runtime.
- `LauncherData/Background.png` (loaded via `BackgroundImageUrl`),
  `LauncherData/Awesomium/` (browser cache) are created at runtime.
- The window values in `PublicLauncherSettings.json` are estimates
  (template placeholders); correct them on the running launcher if needed.
- Player setup additionally needs: DirectX (Installer/Prerequisites),
  VC++ 2010/2012 x86, and the Steam client for Steam tickets if used.

**Launcher background** (`client/Launcher/DefaultBackground.png`, 822x600,
served at `/launcher/background.png`): `tools/launcher_background.ps1 -Art
<picture>` puts a picture into the torn-paper frame and writes 5 candidates
plus previews with the login/news boxes into `launcher-mockups/` (the frame
is kept as `launcher-mockups/frame.png`). To use one, copy its
`background-*.png` over `DefaultBackground.png`; the launcher loads it at its
next start. Installed 2026-11-21: `6-logo-close` (logo close-up, no blur, original
brightness); the original is `launcher-mockups/frame.png`. The script darkens
a band at the bottom (`FooterBand`, from y 522): the launcher's version line
is drawn by its local page (`Launcher/LocalLauncher/launcher.html`, `footer`
`.version-label`, white 10 px without shadow) and can't be restyled from the
server, so the picture gives it a dark background instead. The server reads
the file on every request: a new background needs no restart. The Discord
button in the login page (`patcher.LOGIN_PAGE`) links to
https://discord.gg/hxFANB2kky.

**Launcher news** (the box under the login): `state/<profile>/news.json`,
held in memory by the running server; change it with the Admin web tool or
the HMAC-signed `AdminService.hqs/SaveNews` (key `state/<profile>/admin_hmac.json`),
not by editing the file while the server runs. They show at the next
launcher start, no restart needed. The website's patch notes are written by hand
(since 2026-11-22 on their own page, `website/patch-notes.html`: one note
per slide, newest first). For a new patch: add an
`<article class="slide card" id="note-N">` at the top of the track and a
line in the "All patch notes" list (renumber the `note-` ids and
`data-go` indexes), and replace the card under "Latest patch" in
`website/index.html` (also the count on its link). The page is served as
is, no restart. Keep the website, `PATCH_NOTES.md` and the News entry in
step; the News entry also goes to the Discord patch-note channel
(docs/86-discord-events.md).

**Website video** (2026-11-22): served from this PC, `website/media/mqfel-rebirth-patches.mp4`
(H.264 web copy with faststart, 63 MB, plus a `.jpg` poster; the H.265 master and the
Resolve project "MQFEL Rebirth - Patch Montage 2026-11-22" are in `mqel/media`,
edit script `_temp60/video/build_montage.py`, Resolve link `tools/resolve_mcp/`). The main
page plays it in `#video`; `website/video.html` has Open Graph video tags, so the page link
(or the .mp4 link) plays inline on Discord. The website handler (`WebsiteHandler` in
game_server.py) answers HTTP Range requests (206 Partial Content), which video players
and Discord need to stream and seek. A new video: replace the file under the same name
(or update the paths in `index.html` and `video.html`), no restart needed.


**Chat rooms after a server restart (2026-11-22):** a game that lost its
general chat room during a restart kept sending to that room without
joining it again, and the chat server dropped the messages silently (Enter
did nothing). `xmpp_server.handle_message` now puts a sender who isn't in
the room back in (nick = login, player data from the message) and delivers
the message.

**Clans:** RecruitmentMode JoinRequest (1, "approval") is not implemented
(the clan window is native; the JoinRequest format is unknown), so such
clans take players at once like ImmediateJoin (2); Closed (3) refuses.
GuildMemberJoined now also goes to the other members.
