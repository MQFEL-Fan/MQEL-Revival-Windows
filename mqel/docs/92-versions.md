# Display version (ESC menu)

`server/versions.py` keeps the list of updates since the owner took over and
computes a display version. It is only a label: the client's own version and
the patcher's package versions keep their format.

## Rules

- **v1.1** = the level-60 update (everything up to level 60 unlocked).
- **Big feature:** +0.1 (the lower parts start again at 0).
- **Small feature:** +0.0.1.
- **Background fix:** +0.0.0.1 (shown only when not 0).

## History

| Version | Date | Kind | Update |
|---|---|---|---|
| v1.1 | 2026-11-21 | base | Level 60 update |
| v1.1.1 | 2026-11-21 | small | Level 60 fixes |
| v1.1.2 | 2026-11-21 | small | Castle upgrades for level 60 |
| v1.1.3 | 2026-11-21 | small | Discord status and a new launcher look |
| v1.2 | 2026-11-22 | big | Heroes pack, friends online and events all year |
| v1.2.1 | 2026-11-22 | small | Cornelius Richling joins our Discord |
| v1.3 | 2026-11-22 | big | The Ingame Market opens, and decorations drop loot |
| v1.3.1 | 2026-11-22 | small | Ingame Market fixes, more decoration loot, chat and clans |
| v1.4 | 2026-11-22 | big | Parties and Co-op Raids |
| v1.4.1 | 2026-11-22 | small | Co-op Raids update, one account per player and our privacy policy |
| v1.4.2 | 2026-11-22 | small | Raid bosses, Ingame Market collect and the version number |
| v1.4.3 | 2026-11-23 | small | Party raids: pick, ready, start together |
| v1.4.3.1 | 2026-11-23 | fix | Attack button crash fixed |
| v1.4.3.2 | 2026-11-23 | fix | Co-op Raids sky and banner emblem |
| v1.4.4 | 2026-11-23 | small | Back home at start, roomier region map, WASD optional |
| v1.4.4.1 | 2026-11-23 | fix | Steam login on the first start, party and market on Linux |
| v1.4.5 | 2026-11-23 | small | Setting Mod and a loot filter for your hero |
| v1.5 | 2026-11-23 | big | Orb numbers, inventory sort and a better Ingame Market |
| v1.5.0.1 | 2026-11-23 | fix | Orb numbers in attacks and inside the orb, Sort button |
| v1.5.0.2 | 2026-11-23 | fix | Ingame Market and Setting Mod buttons, windows above the building bar |
| v1.5.0.3 | 2026-11-24 | fix | Ingame Market: Buy now button no longer covers the next item |

Earlier updates (WASD key binds, "More castles" fix, bling counter) are part
of v1.1.

## Where it shows

The Game menu (ESC) is a native panel of the game, not HTML: it can't get a
new line under "Exit Game". The version is appended to its **Credits** button
("Credits - v1.4.2", every language): `level60._version_label` edits Oasis
text 11382 in the DataBin text files (`oasis_text_files`).

## New update

1. Add a line to `versions.HISTORY` (kind big / small / fix).
2. Restart the server: the DataBin version changes (its CRC covers
   `level60.py`, `raids.py` and `versions.py`), players get the new label
   from the launcher.

## Incident 2026-11-22: all texts empty

The first label used a JSON escape for a middle dot (backslash-u00b7). The
game's text reader can't read such escapes (the original files have none, all
special characters are raw UTF-8) and dropped the whole file: every Oasis
text in the game was empty (region names, buttons, quests). Fixed within
minutes: the label is plain " - v1.4.2", written as raw text. Rule: never
put JSON escapes into the Oasis files.
