# Region sky: how a new region gets its background

Status: works in game (owner confirmed 2026-11-23: Co-op Raids, region 11,
shows Little Spitaly's full 3D sky; v1.4.3.2). Code: `server/level60.py`
`patch_exe` (with `_drop_relocation`, `_add_relocation`, `_relocations_in`);
check tool: `tools/check_sky_patch.py`.

## How the game picks the sky

The castle selection (and the Home view) of a region is drawn inside a sky
box: a 3D model around the camera, so the background stays all around when
the camera turns 360 degrees. Which sky box a region uses is decided in
**two steps**:

1. **The exe turns the region id into a name.** A function in
   `MightyQuest.exe` (build 280139: VA `0xdb5f90`, found by the byte pattern
   `level60._SKY_SWITCH` = `mov eax,[esp+8]; dec eax; push esi; cmp eax,8;
   ja ...`) is a `switch` over the region ids 1-9:

   | Region id | Name | Region |
   |---|---|---|
   | 1 | `Region_FriendsZone` | The Friendzone |
   | 2 | `Region_Competition` | Competitions |
   | 3 | `Region_1` | Little Spitaly |
   | 4 | `Region_2` | Heated Gardens |
   | 5 | `Region_3` | Bling's Landing |
   | 6 | `Region_4` | Nova Gloatia |
   | 7 | `Region_5` | Glimmering Valley |
   | 8 | `Region_6` | Stabbinshire |
   | 9 | `Region_7` | Upper Bestmount |

   Every id above 9 falls into the switch's **default case**, which
   returned an empty name: no sky, the castle selection is black.
2. **The name selects the sky box.** It is looked up in
   `Data/GameplaySettings/GeneralSettings/ENVIRONMENTSETTINGSCOLLECTION.JSON`
   (modes `AttackSelection` and `Home`, field `SkyBoxFileName` plus fog and
   light colors).

## What works and what doesn't (learned the hard way)

- **Only the original names work.** v1.4.3 made the default case return the
  new names `Region_8` / `Region_9` and added environment entries with
  those names (copies of `Region_1`). Splendorado and the Co-op Raids stayed
  black in the game, even though the entries were in the settings. The fix
  (v1.4.3.2) returns the exe's own strings, the same addresses the
  original cases push: `Region_7` for region 10, `Region_1` for region 11
  and up. **Rule: a new region reuses the sky of an original region.** The
  extra environment entries (`Region_8` ... `Region_11`) are harmless but
  unused.
- **Environment edits change every region that uses the name.** Tinting
  `Region_1` would also tint Little Spitaly.
- **Overwriting exe code needs a relocation check.** The exe is loaded at a
  random address (ASLR, `DYNAMICBASE`), and Windows corrects every absolute
  address listed in `.reloc`. The old default code had two such addresses
  (at +2 and +15). The v1.4.3 patch left the entry at +2 in place, and it
  then pointed into the middle of the new instructions. Windows "corrected"
  those bytes into garbage, and the game crashed on the Attack button
  (v1.4.3.1 fix). `patch_exe` now removes stale entries (`_drop_relocation`,
  turns them into padding entries), adds entries for the new addresses
  (`_add_relocation`), and **refuses to ship** the patch unless the
  relocations inside the patched bytes are exactly the expected ones
  (`_relocations_in`). If anything doesn't match, players get the
  unpatched exe (black sky, but no crash).
- The "bubble underneath" (the sky dome below the camera, 2026-11-21) came
  from an earlier attempt and is gone.

## The patched default case (22 of the old 23 bytes)

```
mov ecx,[esp+8]          ; output string, like every case
cmp eax,9                ; eax = region id - 1  -> 9 = region 10
mov eax,<"Region_7">     ; address taken from the case of region 9
je  +5
mov eax,<"Region_1">     ; address taken from the case of region 3
push eax
jmp short <case of region 9: call the string constructor>
int3                     ; the old ret byte
```

Relocations: one for each `mov eax,imm32` (+8 and +15); the stale one at
+2 is dropped.

## Recipe: a new region (id 12, 13, ...)

**Default:** do nothing. Every id from 11 up gets Little Spitaly's sky
(`Region_1`) automatically.

**Another sky for all ids from 11 up:** change which case's string the
second `mov` takes. In `patch_exe`, `sky_11` is read from the case of
region 3 (`table + 4 * 2`); use `table + 4 * (k - 1)` for the sky of
region id `k` (see the table above) and update the expected text in the
`want` check.

**Different skies for 11, 12, ...:** the 22-byte default case has no room
for more compares. Put a small lookup in a code cave (the `int3` padding
after the jump table; check that it is free with
`tools/check_sky_patch.py` or a disassembler), jump there from the default
case, and give each new absolute address a relocation with
`_add_relocation`. Extend `_relocations_in`'s expected set to cover every
address. This is untested; test it in-game before shipping.

**Checklist before the restart:**

1. `python tools/check_sky_patch.py` prints the sky name of every region and
   `OK`. It exits with 1 if the patch wasn't applied or a relocation is
   wrong.
2. The launcher only downloads the new exe when the GameBin version
   changes. It is a checksum of the patched exe, so it changes by itself.
   Compute it with the server's own `--client-exe`
   (`patcher.CLIENT_EXE = r"server\state\tls\MightyQuest_local.exe"`;
   without it `_game_version()` measures the Steam exe instead).
3. In game: the castle selection of the new region shows a sky all around
   (turn the camera), and the Attack button doesn't crash.

## The rest of a new region (pointers)

- Region data: `level60.attack_regions` (AttackAdvisorSettings), models,
  `shop_skus` (ItemType 14 entries for the region's skus), boss pictures in
  `ui_global`.
- Map island and banner: `ui_patches.region10_css` / `region11_css`
  (island position, level label); boss medallion in the banner:
  `ui_patches._medallion_strip` (214 x 480 strip of four 120 px states,
  medallion about 104 px at x 113, like the original `PANEL_*CIRCLE.PNG`).
- Start region: the client opens the region with the **highest id** at
  game start. For a story region that is right; a special region (like the
  co-op raids) must be excluded in `raids.home_region` and redirected in
  `ui_mods/party.html` (`onRegionShown`, now only for region 11).
- Region status: special regions open for everyone get Status 3 in
  `AccountState._complete_attack_regions`.
