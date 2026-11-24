# MQEL Revival server (Windows), level-60 fork

A server for The Mighty Quest for Epic Loot (Steam client 0.36.1.34.0):
game server, chat server, launcher login with Steam, patcher and website.

**MQFEL-PublicVersion60**: this fork raises the level cap to 60 (skill ranks
IV/V, castle heart 60, region Splendorado with the boss Goldmaw, gear and
blacksmith up to 60). All of it is in `server/level60.py`; see
[docs/90-level60.md](docs/90-level60.md). A player going back from this
server to a level-30 server must let Steam verify the game files first.

## Quick start

1. Settings: copy `server_config.example.bat` to `server_config.bat` and fill
   in the Steam Web API key, bind address and public host.
2. Start: `start_servers.bat` (game server 8081/8443, chat 5222, website).
3. Stop: `stop_servers.bat`.
4. Play: start the game from Steam; the launcher logs in and patches the game
   (exe, UI patches, WASD helper). `launch_game.bat` starts the game directly
   for local tests.

Admin panel: `http://<server>:8081/admin`.

## Folder layout

| Path | What |
|---|---|
| `server/` | game server, chat server, patcher, UI patches (`ui_patches.py`, `ui_mods/`) |
| `client/` | game files the server reads (gameplay settings, UI, exe) |
| `tools/` | setup and admin tools (`setup_public_server.ps1`, `link_steam.py`, `import_account.py`, `wasd/` ...), see `tools/README.md` |
| `website/` | public website (downloads, patch notes) |
| `player-pack/`, `player-pack.zip` | files players need (built by `tools/setup_public_server.ps1`) |
| `tests/` | server tests: `python -m unittest tests.test_server` |
| `docs/` | documentation, start with `docs/00-overview.md` |

## Files you supply yourself (not in this repository)

This repository holds only the server code, tools and documentation. Game
files belong to Ubisoft and are not included; copy them from your own Steam
install of the game (client 0.36.1.34.0):

| Where | What |
|---|---|
| `client/` | the game's files (`GameData/...`), read by the server and the patcher |
| `server/data/oasis/` | the game's text files `oasis_<lang>.json`, see the README there |
| `server/data/steam/` | the original Steam UI files the UI patches start from, see the README there |
| `website/media/` | optional video and picture for the website's video page |

Secrets stay out of the repository: `server_config.bat` (Steam Web API key,
Discord webhooks), `server/state/` (accounts, certificate key) and the log
files are in `.gitignore`. Replace `your-server.example.com` in
`website/PublicLauncherSettings.json` (and the website pages) with your own
server address.

Tests: `python -m unittest tests.test_server` (needs the files above; all 99
pass with them).

## Documentation

- `docs/05-windows-setup.md`: setup, daily use, troubleshooting
- `docs/06-public-server.md`: public server, Steam login, port forwarding
- `docs/80-wasd-keybinds.md`: WASD movement and the Setting Mod panel
- `docs/86-discord-events.md`: Discord event and patch-note posts
- `docs/87-ingame-market.md`: Ingame Market (auctions and market)
- `docs/89-coop-raids.md`: parties and Co-op Raids
- `docs/90-level60.md`: level 60, Splendorado, castle upgrades
- `docs/92-versions.md`: version numbers
- `docs/96-loot-filter.md`, `docs/97-inventory-sort-orbs.md`: loot filter, inventory sort, orb numbers
- `PATCH_NOTES.md`: patch notes for players
