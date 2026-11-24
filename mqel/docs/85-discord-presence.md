# Discord Rich Presence

Status: built 2026-11-21, tested without the game on Windows (DLL ->
server -> Discord pipe). Application created and its id set in
`server_config.bat` (2026-11-21); to confirm in game. Linux (Wine/Proton)
path built, not tested (no Linux machine here).

Discord shows what the player is doing, e.g. "Attacking Black Dragon ·
Castle level 60", "Editing their castle", "Shopping", with the time since it
started and a "Join the server" button (https://discord.gg/hxFANB2kky).

## How it works

```
game requests --> game server (presence.note) --> per-player activity
WASD helper DLL --GET /presence/<login>--> game server (presence.answer)
WASD helper DLL --Discord IPC pipe, SET_ACTIVITY--> local Discord client
```

- **Server** (`server/presence.py`, hooked into `game_server.py`): every game
  request updates the player's activity:

  | Request | Activity |
  |---|---|
  | `GetAccountInformation`, `EndAttack` | In the lobby |
  | `AttackSelectionService/*` | Choosing a castle to attack |
  | `StartAttack` | Attacking <castle name> (own castle: Testing their castle; competitions: state "Competition") |
  | `SendCommands` with castle room/creature/trap/decoration/building commands | Editing their castle |
  | `SendCommands` with buy/sell commands | Shopping |
  | `SendCommands` with forge/reforge commands | At the blacksmith |
  | `SendCommands` with equip/item/skill commands | Gearing up their hero |
  | `LeagueService/*`, guild leaderboards | Checking the leaderboards |

  Second line: "Castle level N" unless the activity has its own. After 5
  minutes without a game request the activity is dropped.
  `GET /presence/<login name>` (plain HTTP, port 8081, no console/log lines)
  answers `200` with `<application id>\n<activity JSON>`, or `204`. It only
  answers requests from the IP of that player's last game request, so others
  can't look up what someone is doing.
- **Client** (`tools/wasd/discord_presence.c`, compiled into the WASD helper,
  `mqelwasd9_1.dll`): reads the login name from the game's command line
  (`-email <name>@...`) and the server from
  `Launcher\PublicLauncherSettings.json` (`PatcherServiceUrl`), polls every
  10 s and sends changes to Discord (handshake opcode 0, `SET_ACTIVITY`
  opcode 1) over:
  - **Windows**: the named pipe `\\.\pipe\discord-ipc-0..9`;
  - **Linux (Wine/Proton)**: Discord's Unix socket. The DLL detects Wine
    (`ntdll!wine_get_version`), looks for `discord-ipc-0..9` in
    `$XDG_RUNTIME_DIR` (Wine passes the Linux environment through), its
    `app/com.discordapp.Discord/` (Flatpak, Steam Deck), `snap.discord/`
    (Snap) and Vesktop folders, then `$TMPDIR` and `/tmp`, converts the path
    with `kernel32!wine_get_dos_file_name` and connects through Winsock's
    `AF_UNIX` (Wine 6+ / Proton 7+). Status "no AF_UNIX (old Wine)" if the
    Wine version can't. Discord clears the activity when the
  game exits. Status in the KEYS panel diagnostics / `WASD.log` field
  `discord` ("no Discord", "Discord refused", "showing", ...).
  `WASD.ini` `DiscordPresence=0` turns it off.

## Setup (once)

1. https://discord.com/developers/applications -> **New Application**, name it
   as players should see it ("The Mighty Quest for Epic Loot" or "MQEL").
   The name is the "Playing ..." title.
2. **Rich Presence -> Art Assets**: upload a square picture (512x512 or
   larger) named **`logo`** (`presence.LARGE_IMAGE`): `launcher-mockups/logo.png`
   (the game logo cut out of the launcher art with "Rebirth" in the website's
   font, made by `tools/discord_logo.ps1`, `-Size 1024` gives `logo-1024.png`
   for the app icon); without it the
   presence shows without a picture. Nothing else in the application is
   needed (no OAuth2, interactions, URLs or bot).
3. Copy the **Application ID** (General Information) into
   `server_config.bat`: `set MQEL_DISCORD_APP_ID=<id>` and restart the
   server. Without it the server answers 204 and nothing shows.

The application id is not a secret (every client sends it to Discord).

## Limits

- **Linux / Steam Deck**: needs Wine/Proton with `AF_UNIX` support and
  Discord's socket visible to the game. Steam's container runtime
  (pressure-vessel) may hide `$XDG_RUNTIME_DIR`; then nothing shows (status
  "no Discord"), as with any game.
- Discord's own setting "Share your detected activities" (Activity Privacy)
  must be on.
- Players who share one public IP (same home) and play at the same time:
  each still gets only their own login's activity; the IP check only keeps
  outsiders out.
- The helper DLL needs the launcher update (GameBin) to arrive; the panel's
  version check doesn't cover presence.
