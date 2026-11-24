# Loot filter for the hero, Setting Mod, party button tile (v1.4.5)

Date: 2026-11-23. Code: `server/loot_filter.py` (exe patch),
`tools/wasd/xinput_wasd.c` (WASD helper: `LootPlayer`),
`server/ui_mods/keybind_panel.html` (Setting Mod panel),
`server/ui_patches.py` (patch 18), `server/png_tint.py`
(`party_icon_tiled`). Test: `Level60Test.test_exe_loot_filter_patch`.

## What players see

- The **KEYS** button in the lobby top bar is now **SETTING MOD**. It and
  **MARKET** are stacked in one column (MARKET on top, SETTING MOD
  below, 88 px wide together instead of 74 + 46 side by side), so the top
  bar takes less room than before and nothing overlaps.
- The Setting Mod panel (former key binds panel) starts with a new section
  **Loot pick-up by Player**: "Apply the pet's loot filter to my hero too".
  It takes effect at once (no restart).
- With it on, the choice under the game's **Settings > Gameplay > Loot
  pick-up by Pet** also applies to the hero. Example: "Pick-up currencies
  and Epic, Legendary, Exceptional and Magic items" leaves Basic equipment
  and weapons on the ground for the pet **and** the hero.
- Never filtered: gold, life force, blings, crafting materials, dyes,
  potions/consumables, health orbs, XP. Only hero items (equipment and
  weapons, loot type 3).
- "Pick-up everything" filters nothing, with or without the checkbox.
- The party button (patch 17) now sits on the same dark-blue tile as
  Friends, Clans and Notifications (normal, hover, pressed).

The Settings window itself is a native engine panel whose layout is packed
in the game's bigfiles, so the new option lives in our HTML panel.

## How the game loots (findings, MightyQuest.exe 280139)

- Pet: data-driven behaviour in `settings.bin`
  (`GENERALSETTINGS\CREATURESSETTINGS.JSON` → `PetBehavior`): targets by
  `HeroItemLootSelectionSpec.HeroItemQualityMask` (Basic 1, Magic 2,
  Exceptional 4, Legendary 8, Epic 16), gated by
  `ConditionAttackUserSettingsBehaviorSpec.MinHeroItemQualityToPickUp`.
  The pet only *walks* to items; it doesn't filter what gets collected.
- Collection: every looter has a `LootComponent` (`Sources\LootComponent.cpp`,
  vtable 0x1a62e78). Its update (0xf0ca80) queries entities within
  `ATTACKSETTINGS.LootAttractionDistance` (2) and hands them to
  `CollectLoot` (0xf0bdd0): per entity the loot drop component
  `[entity+0xbc]`, loot data `[comp+0x84]`, type `[data+0x14]`
  (1 gold, 3 hero item, 4 XP, 5 health orb, 3/6/10 go to the inventory),
  item `[data+8]`.
- Quality of an item: the function the pet's selection uses
  (thunk 0x42f167 → 0xeddf90, cdecl `(item, [world+0x46cc])`, returns
  0 Basic … 4 Epic).
- User setting live in the attack: `[[[world+0x46b0]+0x114]+4]`
  (AttackUserSettings, the same value the pet's condition reads at
  0xea3410; 0 = everything, 1 = Magic and up … 4 = Epic only). In
  CustomUserSettings.json: `AttackUserSettings.MinHeroItemQualityToPickUp`.
- Forced pull (0xf0b250): when the world flag `[[world+0x46e0]+0x16]` is set
  (end-of-castle vacuum), loot flies to the hero
  (`[[world+0x46b0]+0x124]`) at `LootForcedAttractionVelocity`.

## The exe patch (`loot_filter.patch_exe`)

Applied by `patcher._patched_exe` after `level60.patch_exe`, found by byte
patterns, unchanged when anything doesn't match exactly once (other exe,
already patched, no room). Code in int3 padding near CollectLoot (~180
bytes); the absolute IAT address gets a base relocation (ASLR).

- `CollectLoot`: `mov ebp,[esi+0xbc]` → `call hook_collect; nop`. The hook
  loads ebp and zeroes it for a filtered item; the game's own `test ebp,ebp;
  je next` skips it. The item stays on the ground.
- Forced pull: `mov esi,ecx; cmp byte [esi+0x71],0` → `call hook_pull; nop`.
  For a filtered item the hook sets ZF, the game takes its "not yet"
  branch (only ticks the timer): the item doesn't fly after the hero.
- `filter(comp)`: type 3, setting > 0, quality < setting, and the player
  option on. The option comes from the WASD helper:
  `XInputGetCapabilities(0x4D51454C "MQEL", 0, buf)` returns `0x4D510001`
  (on) or `0x4D510000` (off). Without the helper (real XInput) the call
  fails: off, the game behaves exactly as before.

## WASD helper

- `WASD.ini` `[WASD] LootPlayer=0|1` (default 0).
- `POST /config` takes `lootplayer=0|1`; `GET /state` returns
  `"lootPlayer"` and `"lootFilter":true` (the panel shows the checkbox only
  with a helper that knows it, else "restart the launcher").
- `GET /debug` / `WASD.log`: `lootPlayer`, `lootAsks` (how often the exe
  asked; grows while hero items lie within reach in an attack).

## To test in game

1. Settings > Gameplay: "Pick-up currencies and Epic, Legendary,
   Exceptional and Magic items". Setting Mod: tick "Apply the pet's loot
   filter to my hero too".
2. Attack a low castle: Basic (white) equipment stays on the ground when
   the hero walks over it; gold, life force, materials and potions are
   still collected; Magic and better items still are.
3. Untick: the hero picks Basic items up again (no restart).
4. `WASD.log`: `lootAsks` grows during the attack.

## Top bar buttons, v1.5.0.2 (2026-11-23)

- **INGAME MARKET** (two lines, 102 x 34 px) moved out of the stacked
  column into the free space right of the trophy score, just left of the
  hero portraits (`ui_patches.MARKET_ANCHOR` = `<div class="buy-level-up"`,
  unique in all 30 TopView files).
- **SETTING MOD** (two lines) is now the only button in
  `#mqel-mod-buttons` and fills the column (80 x 34 px).
