# MQEL Revival server (Windows)

A replacement server for *The Mighty Quest for Epic Loot* (Ubisoft, 2014-2015).
It includes the game server, the chat server, the launcher login (with Steam
login), the patcher that updates the players' game, an admin web page and a
project website. It's a non-commercial fan project, not affiliated with
Ubisoft.

Steam client 0.36.1.34.0. Current server version: **v1.5.0.3**. Everything
lives in the [`mqel/`](mqel/) folder; the paths below are relative to it.

What this fork adds (see [`mqel/PATCH_NOTES.md`](mqel/PATCH_NOTES.md)):

- **Level 60**: skill ranks IV/V, castle heart 60, region Splendorado with
  the boss Goldmaw, castle upgrades ([docs/90-level60.md](mqel/docs/90-level60.md)).
  A player going back to a level-30 server must let Steam verify the game files first.
- **Ingame Market**: auctions and a market between players ([docs/87](mqel/docs/87-ingame-market.md)).
- **Parties and Co-op Raids** with Warlord bosses ([docs/89](mqel/docs/89-coop-raids.md)).
- **WASD movement, Setting Mod panel, loot filter for the hero, inventory
  sort, health/mana numbers on the orbs** ([docs/80](mqel/docs/80-wasd-keybinds.md),
  [docs/96](mqel/docs/96-loot-filter.md), [docs/97](mqel/docs/97-inventory-sort-orbs.md)).
- **Decoration loot, All Heroes Pack, events all year, Discord Rich Presence,
  Discord event and patch-note posts** ([docs/86](mqel/docs/86-discord-events.md)).

## Not in this repository

Ubisoft's game files are not included: you copy them from your own Steam
install (`client/`, `server/data/oasis/`, `server/data/steam/`). See
"Files you supply yourself" in [`mqel/README.md`](mqel/README.md).
No keys are included either: put yours in `server_config.bat` (ignored by git).

## Quick start (play on this PC)

1. Install **Python 3.9+** (<https://www.python.org/downloads/>, tick "Add to
   PATH"), then:
   ```bat
   python -m pip install cryptography
   ```
2. Create the certificate and the patched game exe (one time):
   ```bat
   powershell -ExecutionPolicy Bypass -File tools\setup_public_server.ps1 -PublicHost 127.0.0.1 -SkipFirewall
   ```
3. Start the servers: `start_servers.bat`. Stop them with `stop_servers.bat`.
4. Prepare the game (Steam, app 239220):
   - Copy `PublicLauncherSettings.json` into the game's
     `Launcher\` folder.
   - Copy `website\steam-launcher-patch.cmd` into the game folder and
     double-click it.
5. Start the game from Steam. Register an account on the launcher page. The
   launcher downloads the server's game update and starts the game.
6. Make yourself admin, **right after the first start**: open
   <http://127.0.0.1:8081/admin> on this PC. Until an admin exists, it opens
   without a login from this PC and your local network (never from the
   internet). Give your account admin rights there; from then on it asks for
   your login.

Details: [docs/05-windows-setup.md](docs/05-windows-setup.md)

## Public server (friends join over the internet, Steam login)

1. Copy `server_config.example.bat` to `server_config.bat` and fill in:
   - your Steam Web API key
   - `MQEL_BIND=0.0.0.0`
   - your public IP or DynDNS name
   - `MQEL_WEB_PORT=8088`
2. Run `tools\setup_public_server.ps1` (without `-PublicHost`, it reads it from
   `server_config.bat`).
3. Forward TCP 8081, 8443, 5222 and 8088 in your router to this PC.
4. `start_servers.bat`, then send players the website address `http://<host>:8088/`.

Details: [docs/06-public-server.md](docs/06-public-server.md)

## Folders

| Path | Content |
|---|---|
| `server\` | Python server (`game_server.py`, `xmpp_server.py`, admin page) |
| `server\state\` | Player data, created on the first start. `tls\MightyQuest_base.exe` is the unpacked game exe the setup patches. |
| `client\` | Game data the server reads (gameplay settings, UI files) |
| `tools\` | Setup and admin tools (certificate, exe patch, account import, SteamID linking, firewall) |
| `website\` | Project website and player downloads |
| `docs\` | Documentation (`00-overview.md` is the index) |
| `PATCH_NOTES.md` | Patch notes |
| `tests\` | `python -m unittest discover tests` |

Never share `server_config.bat` (Steam key), `server\state\` (accounts and
the certificate's private key) or the log files.
