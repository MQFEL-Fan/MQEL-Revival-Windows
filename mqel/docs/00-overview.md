# MQEL Revival — Overview

**Goal:** Build a compatible game server for *The Mighty Quest for Epic Loot*
(Ubisoft, 2014–2015, Opal engine, PC) so that the game becomes playable again
with the existing client files. A 1:1 restoration is impossible (no server-side
data or databases are known); the aim is a clean re-implementation of the
**client↔server protocol** with newly implemented game logic.

**Current status (2026-11-20, Windows):** the server runs on Windows 11. The
patched launcher logs in, the patcher installs the certificate-patched game
exe, the game connects over HTTPS (port 8443), loads the account and buys the
startup castle. Setup: **`05-windows-setup.md`**; public server with Steam
login: **`06-public-server.md`**.

**Public server (2026-11-20):** the server can run publicly under a static IP or
a DynDNS name. Players join from the internet with Steam login: launcher
8081, game over HTTPS on 8443, chat on 5222. The project website is on port 8088
(`http://<your host>:8088/`).
The admin page can link SteamIDs. A UI patch fixes the empty bling counter in
the lobby. Patch notes: `../PATCH_NOTES.md`.

**Initial findings (2026-10-13):**

- `main.348.1_232184_GameplayToolbox.7z` contains **no runnable server**, but
  something almost as valuable: the complete **.NET server assemblies**
  (`HyperQuest.GameServer.dll`, `*.Contracts.dll`, `Util.*.dll`) including
  XML documentation and PDBs. From these the **entire server API**
  (services, methods, parameters, DTOs) can be reconstructed.
- The client↔server protocol is **HTTP + JSON**, custom-built
  ("Argo" service framework, not WCF/REST standard). URL scheme, headers,
  auth and anti-cheat HMAC have been reconstructed statically
  (details: `30-protokoll.md`, `40-auth.md`).
- The game client consists of two processes: `MightyQuest.exe` (packed,
  contains the network/HTTP code) and `MightyQuestWorker.exe` (unpacked,
  simulation/replay, talks to the master via a named pipe).
- The server settings (`GameplaySettings/*.json`, ~8700 files) are in
  `0.36.1.34.0_104956_GameData.7z` and can be read by the re-implementation
  **directly from disk** — just like the original did (`GameplaySettingsPath`).

**Documentation structure** (file names are kept from the original German
version because code and tools reference them; the German originals are in
`de/`):

| File | Content |
|---|---|
| `05-windows-setup.md` | **Windows setup, daily use, server options, troubleshooting** |
| `06-public-server.md` | **Public server: Steam login, port forwarding, player pack, account import** |
| `10-quellen.md` | Sources: inventory of the 5 archives and what is inside |
| `20-architektur.md` | Architecture: processes, launcher flow, server components, dependencies |
| `30-protokoll.md` | Protocol: HTTP+JSON (URL scheme, verbs, headers, envelopes, versioning) |
| `31-services.md` | Service catalog (which services the game actually needs) |
| `40-auth.md` | Login flow, ConnectionToken, `[Authenticated]`, client HMAC (Murmur3) |
| `50-revival-plan.md` | Build plan and log of the dynamic analysis |
| `60-client.md` | Client folder, launcher, patcher, HTTPS, Steam |
| `70-bling-wirtschaft.md` | Bling economy (earned premium currency) |
| `80-wasd-keybinds.md` | **WASD movement and the KEYS panel** (helper DLL, distribution, settings) |
| `86-discord-events.md` | **Discord event announcements**: Cornelius posts every event start through a webhook (`discord_events.py`) |
| `87-ingame-market.md` | **Ingame Market** (player market: auctions for gear, order book for materials), in-game Bling shop, server update countdown |
| `88-decoration-loot.md` | **Decoration loot**: small gold/life force drops, rare materials, Bling Crystals (1 bling, 1%) |
| `89-coop-raids.md` | **Parties (up to 4) and Co-op Raids**: region 11, procedural raid castles 5-60 scaled to the party, live party panel, party bonus |
| `91-live-coop-research.md` | Research: what live co-op (several heroes in one castle) would need |
| `92-versions.md` | Display version (v1.1 = level 60, +0.1 / +0.0.1 / +0.0.0.1) on the ESC menu's Credits button |
| `93-region-sky.md` | How a region gets its sky (exe switch, original names only, relocations), recipe for new regions, `tools/check_sky_patch.py` |
| `95-preprod-2026-11-22.md` | **Preprod 2026-11-22**: All Heroes Pack, friends online dot, country flags from the login IP, yearly community events (`community_events.py`), competition popup fix (2015 UI scripts), comparison with the 2015 archives |
| `90-level60.md` | **Level-60 update** (this fork, MQFEL-PublicVersion60: level cap, skill ranks, region 10, castle heart 60, blacksmith, exe patch) |
| `CHECKLIST.md` | Feature checklist: what works, what is tested, what is missing |
| `analysis/api-gameserver.txt` | Complete API map (service → methods, parameters, verbs) |
| `analysis/api-common.txt` | API map of the shared contracts (Tracking, CrashReport, …) |
| `analysis/special-packs.md` | Special packs: content and shop value |
| `analysis/mqeloffline-captures/` | Response captures from MQELOffline_cpp |
| `00-overview-FR.md` | French version of the original overview |

**Tools** are in `../tools/` (see `../tools/README.md`):
`ildump.py` (IL disassembler), `dnbrowse.py` (type/string browser),
`cadecode.py` (custom attribute decoder), `apimap.py` (API map generator),
`callfinder.py` (caller search), `make_local_cert.py` (local HTTPS
certificate), `patch_ca.py` (bake a certificate into the game exe),
`patch_ui.py` (apply UI patches locally), `update_geoip.py` (country database).
