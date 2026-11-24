# WASD movement and the in-game Keybind panel

Status: works in game (tested 2026-11-20/21 on the Steam client 0.36.1.34.0).
Shipped to every player by the patcher (GameBin) and the UI patches (GameUI).
Patch notes: `PATCH_NOTES.md` (2026-11-21).

## For players

- **WASD moves your hero during attacks.** W is up the screen, diagonals
  work. Your mouse keeps working as usual: click a monster to attack it, aim
  abilities with the cursor.
- **The newest input wins.** Click a monster while walking: you attack it.
  Hold the attack and press WASD: you step in that direction, and when you
  let go of WASD you go back to attacking what's under your cursor.
- **Ctrl+WASD** moves without attacking, **Shift+WASD** holds the ground
  (the game's own modifier keys).
- **New players (since 2026-11-23, v1.4.4): WASD is off.** They keep the
  game's own keys (potion on Q, camera rotation on W/E). In **KEYS** they
  can tick "Move the hero with the keyboard"; at the next game start the
  WASD layout (camera on Left/Q and Right/E, Ability 5 on R) is applied
  once (`xinput_wasd.c`: `Enabled` defaults to 0 when there is no
  `WASD.ini`, and `apply_wasd_layout` only runs with WASD on). Players
  who already have a `WASD.ini` keep their settings.
- When on: Virtual cursor, click distance 10%, only during attacks.
- **KEYS** (lobby top bar, left of the gear) opens the key binds panel. It
  opens once by itself the first time only for players with WASD on; with
  WASD off the panel explains how to switch it on.
- **Click distance** in the panel sets how far from the hero the movement
  aims. Lower = shorter, more precise steps (default 10%).

## Why it needs a DLL

The game has no keyboard move action. Its key-bind list
(`Contracts.Common.Settings.ShortcutAction`) covers abilities, emotes, camera
orbit and building, but has no MoveUp/Down/Left/Right. The PC build also
ignores the gamepad stick for movement (tested 2026-11-20: the game polled
XInput slot 0 every frame, but full stick deflection and a real Steam
controller both did nothing). What does move the hero is holding the left
mouse button: the hero walks towards the cursor.

The helper DLL (source in `tools/wasd/`, built as `xinput9_1_0.dll`, shipped
as `GameData\Bin\mqelwasd9_1.dll`) is loaded by the game instead of the
Windows XInput DLL (static import of `MightyQuest.exe`; the patcher renames
that import, see "Linux / Proton" below). It passes all
XInput calls through to Windows and runs its own thread (about 120 checks per
second; the game polls XInput only while a controller is connected, so that
can't drive it). While WASD is held, the game "sees" the left button held at
a point next to the hero in that direction.

## How the movement works ("Virtual cursor", default)

The game is told the button is held at the WASD target. The real cursor stays
where it is and the player keeps using it:

- **Button:** `WM_LBUTTONDOWN`/`WM_LBUTTONUP` posted to the game window, and
  `GetKeyState`/`GetKeyboardState` report the left button as held.
- **Position:** hooks in the exe's import table (`GetCursorPos`) return the
  target, and the game window is subclassed so every `WM_MOUSEMOVE` reaching
  it carries the target's coordinates while WASD steers. The real mouse sends
  far more mouse moves than the DLL does, so without this rewrite fast mouse
  movement during fights pulled the hero towards the monster (fixed
  2026-11-21).
- **Real cursor never jumps:** the game pushes its cursor position back to
  Windows (`SetCursorPos`); that call is blocked while WASD steers and for
  150 ms after.

**The player's own input wins.** Low-level keyboard and mouse hooks see real
input before the game does:

- Real left click while moving: the held button is handed over with no gap
  (no button-up is sent), so the game retargets to the real cursor. WASD
  resumes 120 ms after the real button is released.
- Real left button held, then a new WASD press: WASD steers (the button stays
  held, only the position the game sees changes). When WASD is released, the
  game gets the real cursor back and the hero returns to the monster.
- Right click or any other key (abilities, potions): the fake button and
  position are released before the game handles the input, so it aims at the
  real cursor. WASD resumes 250 ms after release.
- Simulated input from other programs is ignored by these hooks.

**When it runs:** only during an attack (the UI patch reports attack start;
a reloaded lobby UI means the attack is over; "Only during attacks" in the
panel), while the game window has focus, no lobby text field (chat) has
focus, and Alt is not held.

**Target:** `Radius`% of the window height (default 10, "Click distance" in
the panel) from the hero position, which is assumed at the window's
horizontal center and `CenterY`% down (default 52).

"Real cursor" (`Mode=2`) moves the real cursor and presses the real button.
It can't share the cursor with aiming, so it's only a fallback.

## The Keybind panel (UI patch 12)

The game's own Settings window is a native engine panel (`OpenOpalPanel :
OptionPanel` in MQLog), not HTML, so it can't get a new button. The UI patch
adds a **KEYS** button to the lobby top bar instead
(`server/ui_mods/keybind_panel.html`, injected into every `TopView*.html`):

- **WASD movement:** on/off, the four keys (apply right away), method,
  click distance, "Only during attacks".
- **Conflict warning:** a move key that's also bound to a game action, with a
  **Use WASD layout** button.
- **Game key binds:** every action in `ShortcutsDictionary`, two key slots
  each. Click to rebind (hold Ctrl, Shift or Alt for a combination, Esc
  cancels), × to remove, then **Save key binds**.
- **First run:** the panel opens once by itself on the first lobby visit
  with the DLL installed (`LayoutOffered` in `WASD.ini`), with a short intro.
- **Diagnostics** line at the bottom (same numbers as `WASD.log`).

The game keeps its key binds in memory and writes `CustomUserSettings.json`
itself, so the panel can't change them while the game runs. Saved binds go to
`GameData\Config\Game\CustomUserSettings.wasd-pending.json`. At the next game
start the DLL merges them into `CustomUserSettings.json` before the game
reads it: only `ShortcutsDictionary` is replaced, and the previous file is
kept as `CustomUserSettings.json.wasd-backup`.

The panel talks to the DLL on `http://127.0.0.1:27631`. The DLL answers only
the game UI (`Origin: http://localhost`), so websites in a normal browser
can't use it. Each connection gets its own thread (Chromium opens idle
pre-connections that blocked the first request).

## WASD layout

| Action | Before | WASD layout |
|---|---|---|
| Move | mouse | **W A S D** + mouse |
| Rotate camera left | Left arrow, W, A | Left arrow, **Q** |
| Rotate camera right | Right arrow, E, D | Right arrow, **E** |
| Ability 5 (Q slot) | Q | **R** |

**Applied automatically once:** at the first game start with the DLL (before
the game reads its settings), the DLL sets these three actions' keyboard keys
in `CustomUserSettings.json` (backup: `CustomUserSettings.json.wasd-backup`)
and stores `LayoutApplied=1` in `WASD.ini`, so later changes by the player
are kept. If the file doesn't exist yet (the game's very first run), it
happens at the next start. The **Use WASD layout** button in the panel does
the same by hand.

Everything else stays as it was. `tools/wasd/CustomUserSettings.json` is a
ready-made file with this layout (copying it also resets the player's other
settings in that file, such as window size and audio).

## Distribution (patcher)

While `tools/wasd/bin/xinput9_1_0.dll` exists, `server/patcher.py` ships it in
the GameBin package next to the exe as `mqelwasd9_1.dll` (also without
`--client-exe`), and changes the exe's import `XINPUT9_1_0.dll` to that name
(`patcher.wasd_import`, same length, in place). Version
`280139.V<CRC32 of exe + DLL>` (before 2026-11-21: `.W`, shipped as
`xinput9_1_0.dll`; that file stays in old installs, unused).

The helper also forwards Discord Rich Presence (`discord_presence.c`,
compiled into the same DLL): see `85-discord-presence.md`.

### Linux / Proton

Wine (Proton, Steam Deck) loads its **own built-in** `xinput9_1_0.dll` even
when a DLL with that name sits next to the exe, unless the user sets a DLL
override (`WINEDLLOVERRIDES="xinput9_1_0=n,b" %command%`). So with the `.W`
versions the helper never ran on Linux and the KEYS panel said it was not
running. Wine has no built-in `mqelwasd9_1.dll`, so it loads the shipped
one; the helper then loads the real XInput by its system path (Wine's
built-in there). Paths are fine under Wine (the DLL finds `WASD.ini` and
`..\Config\Game\CustomUserSettings.json` from the exe's path).

The launcher's `.replace` deletes the old file first and aborts if it's
missing ("Cannot remove file"); `.new` aborts if the file exists ("should not
exist") (PublicLauncher 0x4e0ab1 / 0x4e0c97). So the DLL comes as `.new`
unless the installed GameBin is already a `.W` version, then as `.replace`.
It isn't listed in `GameBinCRC.json` (the launcher ignores files without an
entry).

**Testers who copied the DLL by hand:** the patcher now ships
`mqelwasd9_1.dll`, so a hand-copied `xinput9_1_0.dll` no longer blocks the
`.new`; it is simply unused.

To stop shipping it: delete or rename `tools/wasd/bin/xinput9_1_0.dll` and
restart the server. Players keep the DLL they have.

## Settings (`GameData\Bin\WASD.ini`)

| Key | Default | Meaning |
|---|---|---|
| `Enabled` | 1 | WASD movement on |
| `Up`, `Left`, `Down`, `Right` | 87, 65, 83, 68 | Windows virtual-key codes (W A S D) |
| `Mode` | 1 | 1 virtual cursor, 2 real cursor |
| `AttackOnly` | 1 | only during attacks |
| `Radius` | 10 | click distance, % of window height (4–40) |
| `CenterY` | 52 | hero position, % down the window (20–80) |
| `LayoutOffered` | 0 | the first-run panel was shown |
| `LayoutApplied` | 0 | the WASD layout was written into `CustomUserSettings.json` |
| `AcceptInjected`, `ForceKeys` | 0 | tests only |

Diagnostics: `GameData\Bin\WASD.log`, rewritten every 5 seconds (key frames,
moved frames, presses, hand-overs to the real mouse, key pauses, rewritten
mouse moves, hooks installed, and why WASD was blocked). Same numbers at the
bottom of the KEYS panel and at `GET /debug`.

Uninstall: deleting the file no longer works (the shipped exe imports
`mqelwasd9_1.dll` and won't start without it); stop shipping it on the
server instead (see above), then players get the exe without the import
change.

## Control endpoint

| Request | Effect |
|---|---|
| `GET /state` | enabled, keys, mode, radius, layoutOffered, layoutApplied, attackOnly, inAttack, pendingBinds |
| `POST /config` | `enabled=1&up=87&left=65&down=83&right=68&mode=1&attackonly=1&radius=10&layoutoffered=1` (any subset) |
| `GET /binds` | `ShortcutsDictionary` object (the pending one if any) |
| `POST /binds` | new `ShortcutsDictionary` object, saved as pending |
| `POST /binds/discard` | delete pending binds |
| `POST /typing` | `1`/`0`: a text field has focus (pauses WASD) |
| `POST /attack` | `1`/`0`: attack started / ended |
| `POST /quit` | close the game (server update countdown at 0, docs/87): WM_CLOSE like Alt+F4, process ended after 2 s |
| `GET /debug` | diagnostics |

## Build and test

`tools\wasd\build.bat` needs the MSVC Build Tools (2019 or 2022) and builds
the 32-bit DLL (the game is 32-bit) into `tools\wasd\bin\`. Test programs
(32-bit, built next to a copy of the DLL):

- `test_host.c`: loads the DLL like the game, keeps the endpoint running.
- `test_window.c`: a window that presses W (SendInput) and logs the button
  messages, `GetCursorPos` and `GetKeyState`; with `WASD.ini`
  `AcceptInjected=1` it also tests the hand-over to the real mouse
  (`test_window.exe prio`: click first, then WASD). Don't run it while
  someone uses the PC: it sends real input.
- `test_subclass.c`: with `ForceKeys=1`, checks that mouse moves posted to the
  window arrive at the WASD target (no input simulated).

## Known limits

- While WASD steers, the game's idea of the cursor is the WASD target, so
  hover highlights show there until you click or press a key.
- The hero is assumed at the window center (`CenterY`); with unusual camera
  angles the direction can be slightly off.
- Ending an attack isn't reported by the UI (the end events don't fire); the
  lobby UI reloads after an attack and resets it, which is enough.

## Setting Mod (2026-11-23, v1.4.5)

The KEYS button is now **SETTING MOD** (stacked under MARKET in one
column, ui_patches 18). The panel's first section, **Loot pick-up by
Player**, applies the pet's loot filter to the hero too (WASD.ini
`LootPlayer`, `POST /config lootplayer=1`, exe patch `loot_filter.py`).
Details: docs/96-loot-filter.md.

## Game icon (2026-11-23, v1.5)

The helper gives the game window the exe's icon (`WM_SETICON`, big and
small) and subclasses Unicode windows with the W functions; `WASD.log`
field `iconSet`. See docs/97-inventory-sort-orbs.md.
