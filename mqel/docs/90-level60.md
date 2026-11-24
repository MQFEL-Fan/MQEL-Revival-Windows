# Level-60 update

Status: **released** 2026-11-21, tested in game. This folder becomes
**MQFEL-PublicVersion60**, the level-60 fork of MQEL-PublicVersion (which
stays at level 30). Switch off with `MQEL_LEVEL60=0` (see below).

Hero level cap 30 -> 60, skill ranks IV and V, trap-skill cooldowns, castle
heart up to rank 60, storages rank 6 (1,000,000), a new region (35-60) with
NPC castles and fake players, monsters and items up to level 60.

**Second pass (2026-11-21, to confirm in game):** skill ranks III-V that
were equal now grow (Hawk: Harass/Dive, Stunning Blow, Siren Stun,
Thunderclap, Teen Spirit, Runaway helper abilities), cooldown 10 -> 7.5 s
for all four trap skills, region-10 drops at the castle level (were capped
at 30), gold/life-force storage rank 6 with castle heart 60, Goldmaw's gold
dragon instead of the spider badge (and in the boss health bar).

**Third pass (2026-11-21, to confirm in game):** defense rating 750 at
castle heart 60 (was 675); Architect's Office ranks 7/8 (9 rooms at heart
40, 10 rooms at 50) with four room types players couldn't buy before;
gold/life force mines rank 12 (heart 38) and 13 (heart 52); one more gold,
life force and bling mine at heart 35 and 55; craftable boss "Goldmaw the
Insatiable" (gold Dragonificus with the Golden Glow Dragon picture, stronger,
castle heart 60, twice the price);
region-10 fake players get older region bosses (Goldmaw only in Goldmaw's
Hoard); the "35-60" badge on the region map no longer covers the dragon;
the WASD helper now loads under Linux/Proton (`mqelwasd9_1.dll`).

## How it is built

All data changes live in one module, `server/level60.py`. It edits the
gameplay-settings JSONs (the files inside the client's `settings.bin`):

- **Players** get them from the patcher: the DataBin package version gets a
  part `L<CRC of level60.py>` (e.g. `104956.L0d57b96f`), and the patcher
  builds `settings.bin` from the untouched Steam file plus these edits (plus
  the bling-economy edits on top, `balance.edit_content`). The DataBin
  package sends whole files (`.replace`), also over an unknown installed
  version: after any change to `level60.py` the client's old `L` version
  is unknown, and a delta can't start from it (before this, such clients
  silently kept the old data). About 5.4 MB; building takes ~1 min once.
- **Texts**: the client reads them from the loose files
  `Data/GameplaySettings/Oasis/oasis_<lang>.json` of the DataBin package,
  not from the copies inside `settings.bin`. `level60.oasis_text_files`
  adds the new texts (region, boss, castles, quest) to the Steam originals
  kept in `server/data/oasis/`; without `L` the originals go back.
- **The server** reads the loose copies in
  `client/GameData/Data/GameplaySettings`. `tools/apply_level60.py` writes
  the same edited files there, always from the untouched files inside
  `settings.bin`:

  ```
  python tools/apply_level60.py            apply
  python tools/apply_level60.py --check    list what would change
  python tools/apply_level60.py --restore  original files back
  ```

  Restart the server afterwards. After any change to `level60.py`, run it
  again (the data version changes with the file, players patch again).
- Switch off: environment variable `MQEL_LEVEL60=0` (no `L` part, no
  region 10 castles) and `tools/apply_level60.py --restore`.

`settings.bin` itself is never changed (the launcher's deltas start from
the Steam file).

## What changes

| Area | File(s) | Change |
|---|---|---|
| Hero levels | `HEROSETTINGS.JSON` | `XpPerLevel` 30 -> 60 entries: XP per level grows 6 % per level from the step 29->30 (381,060), level 60 at 34.2 million XP; `LevelRequirements` 60 entries |
| Skills | `Abilities/<skill>/GAMEPLAY.JSON`, `UI.JSON` | every hero skill (48) gets 5 ranks (the skill tree draws 5 slots; the data had 2-3). New ranks unlock every 12 levels after the last one (max 60), e.g. Volley 12/24/36/48/60 |
| Skill power | new specs `Effects/Missiles/Buffs/...` ids from 700000 | ranks point to their own effect/missile/buff specs (Volley rank 1 effect 34, rank 2 effect 35); the new ranks get new specs whose numbers continue the step between the previous ranks when they grow in size (Volley arrow damage 6, 8, 10, 12, 14; Caltrops defense debuff -10 % -> -12.5 % -> -15 %) |
| Skill tooltips | `Abilities/<skill>/UI.JSON` | tooltips take their numbers from specs by tag (`TaggedSpec` "Caltrops damage 3" = `Tag` of the rank-3 buff); new specs get the rank's tag ("Caltrops damage 4", "... 5") and the rank IV/V tooltips point to them; tags inside the skill's own ranks too (Stunning Blow "damage multiplier 3") |
| Missing values | `extrapolate`, `_DEFAULTS` | a value only the last rank has counts with its default in the previous one: Stunning Blow rank I has no `Multiplier` (= 1.0), rank II 1.2 -> 1.4, 1.6, 1.8 (also Siren Stun's missile 1.0/1.4 -> 1.8 ...). Before, ranks III-V copied rank II |
| Hawk: Harass, Hawk: Dive | `Abilities/000157`, `000065`, new `Creatures/7000xx - GhostHawk_R4/_R5` | the skill spawns the GhostHawk (creature 1089) and uses its ability by slot, one slot per rank (Harass: Attack/Spell6/Spell7 = HawkScratch 1-3, Dive: Spell1/3/5 = HawkDive 1-3); the damage is in those abilities, so ranks IV/V copied rank III. The exe knows only the slots Attack, Spell1-Spell10 (enum strings in MightyQuest.exe) and the GhostHawk fills all but one, so ranks IV/V spawn their own GhostHawk copy whose ability in rank III's slot is continued (`_slot_ranks`, `SpecForge.entity_variant`): Harass damage 0.2/0.25/0.3/0.35/0.4 x hero DPS per second (stun stays 2 s), Dive 0.4-0.6 forward, 0.6-1.0 backward |
| Flat skills | `BOOST_STEP`, `SpecForge.boost_level` | skills whose last two original ranks have the same numbers (also through the specs they reference) have no step to continue: Thunderclap (both ranks 0.2 x hero DPS). New ranks get +15 % per rank on the damage values (StatValueSpec `Multiplier`, tagged "... damage" values) in boosted copies of the specs (tags "<tag> R3" ...): 0.23, 0.26, 0.29. Electric Charge and Shockwave have no damage value and no number in the tooltip and stay as they are |
| Teen Spirit | `Abilities/001306`, `TEEN_SPIRIT` | all 3 ranks used buff 731 (+10 % damage, 5 s bonus) while the rank-II tooltip showed buff 732 (+12 %, 6 s): rank II uses 732 (copy of buff 683 that references 732), ranks III-V continue 731 -> 732: +14/16/18 %, 7/8/9 s; its UI had 2 tooltip ranks for 3 skill ranks and now has 5 |
| Runaway helper abilities | `Abilities/001316/1317` (Siren Stun), `1331/1332` (Headbang), `1333/1334` (Dancing Blades) | abilities a skill reaches through its specs with one level per skill rank (`_sub_abilities`) get 5 levels as well (Siren Stun cleave 1.4, 1.8, 2.2, 2.6, 3.0) |
| Trap skills | `Abilities/001370-001373` (Runaway, Mage, Knight, Archer = Hawk: Hack) | cooldown 0.5 s -> 10 s at rank I, 9.375, 8.75, 8.125, 7.5 s at rank V (`TRAP_COOLDOWN`); the trap disable stays 5 s (Hawk: Hack `Effects/000499`, `DeactivateTrapOperationSpec`), the Knight's skill destroys a trap |
| Castle heart | `Buildings/000001`, `SHOPSKUBASESETTINGS.JSON` | ranks 31-60: defense rating (`MaxConstructionPoints`) evenly from 375 at 30 to 750 at 60 (`HEART_CP_TOP`, +12.5 per rank: 500 at 40, 625 at 50; was +10, 675 at 60); upgrade SKUs life force (currency 4) 72,600 +13,700 per rank (469,900 at 60, below the 500,000 storage) or blings 600 +25 per rank; the unused SKUs for 31/32 are activated |
| Monsters, traps | `Creatures/*`, `Traps/*` (`Tiers`) | tier tables continued with their own level step up to 60, so monsters in level 35-60 castles reach the castle level (stats grow per level: `HealthPerLevel`, `PhysicalDamagePerLevel`); single-tier level-design elites/traps (level >= 10) get a tier every 4 levels |
| Items | `HEROITEMTEMPLATES.JSON` | gear templates whose range ended at 30 go to 60 (item stats grow per item level); default gear, cosmetics and fixed-level items (LevelMin = LevelMax) keep their range |
| Shop gear | `HEROITEMTEMPLATES.JSON`, `SHOPSKUBASESETTINGS.JSON` | every shop item at level 30 (the "Exceptional ..." series, 34) continues at 33, 36 ... 60: new fixed-level templates (ids from 90001, same name/look/effects) and SKUs (codes from 70000); gold price grows linearly to 2.3x at 60 (max 448,500), bling price stays |
| Region boss | new `Creatures/001200 - LD_Goldmaw` | copy of the Black Dragon (432, one tier at level 34): name Goldmaw the Insatiable, one tier at level 60, 1.5x health; replaces 432 in Goldmaw's Hoard |
| Quest | `ObjectiveSettings.json`, Oasis 16785-16787 | objective 105 "All That Glitters" / "Defeat Goldmaw the Insatiable." like 104 (Dragonificus): unlocked with region 10 (also at login), done by killing Goldmaw and reaching the treasure room; 250 blings (balance default, admin-adjustable), 25,000 gold, 25,000 life force, 1,000,000 XP |
| Castle selection | `VISUALATTACKSELECTIONSETTINGS.JSON` | region 10 uses region 9's boss castle models (without an entry the 3D selection stays black) |
| Sky | game exe (`level60.patch_exe`) | the exe picks the castle-selection sky in a switch over region ids 1-9 ("Region_1" ... "Region_7" are fixed strings in the exe); region 10 fell into the default case (black). The patch (5 bytes + one base relocation, found by pattern, applied to the exe the patcher ships) lets id 10 use region 9's case (Upper Bestmount's golden sky). The data entry `Region_8` stays but is not used |
| Blacksmith prices | `SHOPSKUBASESETTINGS.JSON` | craft (ItemType 16), reforge (17) and upgrade (24) prices per rarity and item level only went to 30: items above 30 had no price buttons and could not be upgraded/reforged again. Continued to 60 with the last step (bling prices stay) |
| Castle heart value | `CASTLEITEMVALUESETTINGS.JSON` | value per heart rank continued to 60; new building ranks (storages 6, Architect's Office 7/8, mines 12/13) = rank before + its bling price; craftable Goldmaw = 2x Dragonificus |
| Storages rank 6 | `Buildings/000003`, `000004` (`GAMEPLAY`, `UI`, `VISUAL`), `SHOPSKUBASESETTINGS.JSON` | gold and life force storage rank 6: capacity 500,000 -> 1,000,000, needs castle heart rank 60 (the upgrade 59 -> 60 makes it buyable); the unused SKUs 10017/10031 (gold) and 12368/12382 (blings) are activated: 250,000 gold (payable with a full rank-5 storage) or 1,200 blings. Icons/visual lists to rank 6 (life force storage had 7 already) |
| Architect's Office | `Buildings/000013` (`GAMEPLAY`, `UI`, `VISUAL`), `SHOPSKUBASESETTINGS.JSON` | ranks 7/8 (`ARCHITECT_RANKS`): `MaxRooms` 9 with castle heart 40, 10 with 50 (rank 6: 8 rooms at 29). Rank 7: the unused SKUs 10123/12462, now 350,000 gold or 1,250 blings; rank 8: new SKUs 72002/72003, 450,000 gold or 1,500 blings (both below the 500,000 storage cap). The client limits rooms (`CannotPlaceMoreRooms`), the server doesn't |
| New room types | `Rooms/007093`, `007098`, `007094`, `007102` (`GAMEPLAY`; `UI` of 7093/7094), `SHOPSKUBASESETTINGS.JSON` | rooms from Ubisoft's PVE castles with shop icons whose SKUs were inactive (`ARCHITECT_ROOMS`): Cross Chamber 04 and Linear Chamber 07 with office rank 7 (10,000 gold), Cross Chamber 05 and Junction Chamber 04 with rank 8 (20,000 gold). The game's atlas picture (`LayerName`) of both cross chambers is a wardrobe; without `LayerName` the client shows their icon files (`ShopIconUrl`, the room layout) like for decorations and pets (`ROOMS_ICON_FILE`) |
| Mines | `Buildings/000005`, `000006` (`GAMEPLAY`, `UI`, `VISUAL`), `000016`, `SHOPSKUBASESETTINGS.JSON` | gold/life force mines rank 12 with castle heart 38 (58 per 5 min = 696/h, capacity 36,000) and 13 with 52 (68 = 816/h, 50,000) (`MINE_RANKS`; rank 11: 588/h, 24,000), the unused SKUs 10051/10052, 10065/10066, 12402/12403, 12416/12417: 150,000 / 250,000 gold or 1,200 / 1,600 blings (ranks 9-11: 40,000 / 56,000 / 75,000; 97,000 for rank 12 was too cheap for +12,000 capacity). `BuildingInstanceRequirements` one more gold, life force and bling mine with heart 35 and 55 (`MINE_INSTANCE_HEARTS`; gold/life force 4 -> 6, bling 3 -> 5); the bling mine's shop quota (`special_packs.SHOP_QUOTAS`, SKU 15522) grows with them |
| Craftable boss | new `Creatures/001201 - Goldmaw_Craftable_Boss`, `SHOPSKUBASESETTINGS.JSON`, Oasis 16783 (name) / 16851 | **Goldmaw the Insatiable** (the region boss's name): copy of Dragonificus Terribilis (1067) with the gold overlay; 1.5x health, 1.3x damage, defense rating 30 (26); needs **crafting lab rank 15** (`CraftingBuildingRequirementSpec` building 10 rank 15 instead of 14; the card's lock shows "15"). SKU 72022: 2x Dragonificus' (SKU 14698): 258,000 life force, 90/10/6 materials |
| Crafting lab rank 15 | `Buildings/000010 - SummoningPortal` (`GAMEPLAY`, `UI`, `VISUAL`), `SHOPSKUBASESETTINGS.JSON` | rank 15 needs castle heart 60 (`portal_rank15`; rank 14: heart 30); the unused SKUs 10443/12470 ("NOT USED", 999,999) now 300,000 gold or 1,000 blings |
| Craftable Goldmaw's picture | DataBin files `Data/Generated/shopicons/ui/common/creaturesicons(inv)/rares/missflameo*.png`, `Data/Generated/Web/UI/COMMON/CREATURESICONS(INV)/RARES/MISSFLAMEO.PNG` (`dragon_icon_files`, patcher `_data_bin_files`) | crafting-lab cards are file sets `Generated/shopicons/<LayerName as path>_<330x192/200x200/96x96>.png` plus `<...>lock_<size>.png` (silhouette while locked); a missing file shows a **wardrobe** (that was the broken card: the pet picture had no lock file). The launcher can't add files safely (`.new` fails if the file exists, `.replace` if it's missing), so the game's only unused complete set, "missflameo" (in `DataBinCRC.json`), gets Dragonificus' card tinted gold (`png_tint.tint_gold`, picture area only) and Dragonificus' lock silhouette; `LayerName` `UI_Common_CreaturesIcons_Rares:missflameo` |
| Boss pictures | `UI/UIGLOBALSETTINGS.JSON` | `RegionBossPictureLayerNames` (square badge over the boss castle in the 3D selection; without "10" the client showed the spider), `CastlePopupRegionBossPictureLayerNames` (castle popup) and `BossPictureLayerNames` (boss health bar portrait, by creature; without 1200 a skeleton): region 10 / Goldmaw get Upper Bestmount's gold dragon (`squareBossesIcons:20`, `hud_AurferousCircle`). Not in the exe, as assumed before |
| Castle heart icons/model | `Buildings/000001` `UI.JSON` (`Ranks`, 30 icons), `VISUAL.JSON` (`VisualProgression`, 31) | continued to rank 60: the client read rank 31's icon from an empty slot and crashed opening the heart (crash dump: MightyQuest.exe+0x85f2ef, `rep movsd` from a null entry + 0x108) |
| Region 10 range in the client | `ATTACKADVISORSETTINGS.JSON` | LevelMax 39 for the client (`CLIENT_LEVEL_MAX`): the 3D selection puts the hero's tower on ring min(hero level, LevelMax) - LevelMin, with 60 a level-60 hero stood 25 rings above the castles outside the sky sphere. Labels show 35-60 (`ui_patches` 14.), the server uses `REGION_LEVELS` (`castles.attack_selection`) |
| Blacksmith | `FORGESETTINGS.JSON`, `FORGECRAFTINGMATERIALSSETTINGS.JSON` | `MaxForgeItemLevel` 30 -> 60 (upgrade/craft up to 60); materials per level 31-60 (+5 per 5 levels) |
| Item crafting | `HEROITEMTEMPLATES.JSON`, `SHOPSKUBASESETTINGS.JSON` | the 4 craftable items (pike, staff, crossbow, hammer, every 5 levels to 30) at 35 ... 60: life force +33,000 per step (250,000 at 60), more materials |
| Castle level 31-60 | `BUILDSETTINGS.JSON` | `MaxBoostedCreaturePerCastleLevel` up to 60 |
| XP | `ATTACKERREWARDSETTINGS.JSON` | creature XP multiplier per castle level (was the level, max 36): from 31 on XP needed / (50 attacks x 250 creature CP) - 32 at 31, 73 at 45, 175 at 60 - so ~50 attacks (like 29 -> 30) on castles of the hero's level per level. Castles below the hero still give less (original XpModifierTable: 5 levels below = 10 %) |
| Monster strength | `Creatures/*` `TierModifiers` | new tiers get the abilities/passives of the old last tier (before: none); tiers from level 35 +22 % health and damage (`MONSTER_BOOST`) |
| Shop | `SHOPSETTINGS.JSON` | level filters 36-41, 42-47, 48-53, 54-60 (hero) and 36-40 ... 56-60 (castle) |
| Ranges | forge, drops, resurrection, potion limit, heart bonus, blacksmith requirement | last range that ended at 30/35 now ends at 60; `LootTransfereCostsPerLevel` continued |
| Region | `ATTACKADVISORSETTINGS.JSON`, `OASIS_*.JSON` | region 10 **Splendorado** (levels 35-60), boss **Goldmaw the Insatiable** (castle "Goldmaw's Hoard", id 60999), unlocked by beating Upper Bestmount's boss; Friends/Competitions up to 60 |

Server code:

- `castles.py`: the 3D castle selection has 5 level rings (`CirclesRadius`)
  and puts a group on ring "Level - LevelMin" (castles 20 levels above
  LevelMin ended up far below the tower). Region 10 has castles at levels
  35, 37, 40, 43, 45, 47, 50, 53, 55, 57, 60 (two each, `REGION_CASTLE_LEVELS`,
  plus fake players); `_rings` spreads them over the 5 rings (35/37/40,
  43/45, 47/50, 53/55, 57/60; group Level 35-39), the castles keep their own
  level. Level 60: 2 castles + 2 fake players + boss.
- `castles.py`: region 10's NPC castles from `level60.region_castles()`:
  two per level 35-59 ("Gilded <name>", copies of the level 24-33 PVE
  castles at the new level, ids 60000 + level*10 + n) and the boss castle
  (Black Dragon layout, level 60). Their creatures and traps get the highest
  tier up to the castle level. Fake players come from these like from every
  PVE castle; fake players' castle heart rank is now the castle level (at
  least 30).
- `castles.py`: fake players' throne room comes from a boss castle (the
  only throne rooms with room for the Architect's Office), so every
  region-10 fake player had the Black Dragon (35-47) or Goldmaw (50-60). Now
  their throne gets the older region bosses in turn
  (`level60.OLD_REGION_BOSSES`: Count Snotula, Red Dragon, Durrrr, Captain
  Clubbage, Marleybone, Stabbington, Black Dragon) at the castle level's
  tier; Goldmaw only in Goldmaw's Hoard.
- `account_state.py`: a beaten boss region opens the next one at login too
  (players who beat Upper Bestmount before the update get region 10);
  item effect level stays 1-4.
- `ui_patches.py` patch 13: CSS for region 10 on the region map (Glimmering
  Valley island tinted gold, 210x420, in the gap between Upper Bestmount and
  Stabbinshire) and Goldmaw's gold medallion in the castle selection
  (`castleSelectorModule.css`, `bossId-60999`). Position:
  `REGION10_LEFT/TOP` (base coordinates of the 1920x1008 map). The tint is
  baked into the images (`png_tint.py`, data URIs). **Built from the Steam
  UI files in `server/data/steam/`**: `client/` holds the 2014 UI (map
  1600x840, other positions and images); patching from it replaced the
  Steam map with the old one (small map, cut islands). The "35-60" badge
  and the checkmark sit left of / above the dragon medallion like on Upper
  Bestmount (`_medallion_center`); centered, the badge covered the dragon.
- `item_drops.py`: item level of drops = castle level -1/0/+1
  (`ItemLevelTable`), at most the hero level and 60 (was capped at 30, so
  region 10 dropped level-30 gear).
- `patcher.py`: DataBin version part `L<CRC>`; `settings_archive.py` can
  now change, add and rebuild archive files (`splice`, `add_files`,
  `repack`).

Tests: `tests/test_server.py`, `Level60Test`.

## Known limits / to check in game

- **All UI patches start from the 2014 UI in `client/`** (not only this
  update; also in MQEL-PublicVersion): TopView.html, lobbyWalletModule.js,
  hyperquest.extensions.js, CastleCompetitionPopUpModule.js and (anchor
  missing, shipped unpatched) forgeModule.js / playerInteractionModule.js
  replace newer Steam files with 2014 versions. Only the two region-map
  CSS files use the Steam base so far (`server/data/steam/`).

- **Region map position** of the new island: set from the screenshot's
  gap; adjust `REGION10_LEFT/TOP` in `server/ui_patches.py` if needed.
- **Region 10 shows 5 levels at a time** (around the hero's level), not all
  of 35-59 at once (5 rings in the 3D selection).
- **Goldmaw** uses the Black Dragon model with the yellow weapon-glow
  material as a permanent overlay (no gold dragon model exists). The
  region-map island carries Upper Bestmount's dragon medallion (pasted,
  `png_tint.paste_ellipse`), the castle popup and selection banner a gold
  Dragonificus medallion.
- **Storage upgrades** right after the castle-heart upgrade that meets
  their requirement are not sent by the client until the game restarts
  (seen for gold storage 3 and life-force storage 5; same session pattern).
- **Skill tooltips** of ranks IV/V copy rank III's text and point to the
  new ranks' tags. Where the original data has no tag for a value (Headbang
  "damage multiplier", "enemy health multiplier"), the tooltip shows
  nothing there on every rank, as before.
- **Electric Charge, Shockwave** (Mage): ranks I-V are equal (no damage
  value; the original ranks I/II were equal too).
- **Drops**: a hero below the castle level gets items of their own level
  (original rule: at most the hero level).
- **Craftable Goldmaw** uses Dragonificus' model with the gold overlay and
  a gold-tinted Dragonificus card (icon set "missflameo"); check the card,
  locked ("15") and unlocked. Steam's "verify files" restores the original
  missflameo pictures until the launcher patches again.
- **Cross Chamber 04/05 cards**: the game has no card picture for them;
  they showed the wardrobe, which is the game's invalid icon
  (`UIGLOBALSETTINGS` `DefaultIconLayerName` `UI_Invalid:InvalidIcon`). Room
  cards come only from the packed texture atlas (`LayerName`): loose card
  files (`Generated/shopicons`, tried 2026-11-21 as `.R1` transparent and
  `.R2` RGB) are not read. So they use the atlas picture of the most similar
  cross room (`ROOM_ATLAS_PICTURE`): Cross Chamber 04 -> Cross Hall 01 (plus
  shape), Cross Chamber 05 -> Cross Hall 06 (hook-shaped inner wall). The
  exact layouts would need new textures in the Bigfiles. Old installs keep
  the unused `.R1/.R2` files in `shopicons/icoshop/rooms`.
- **New room types** were never sold by Ubisoft (inactive SKUs); they are
  used in PVE castles, so they render, but check placing them.
- **Players' own castle defenders** can't be upgraded past their current
  tiers (no shop items for the new tiers), so their monsters stay at the
  old levels.
- **Balance** (XP curve, castle heart prices, new skill values) is a first
  pass: values continue the original curves.
- Going back to a server without the update: the launcher doesn't know the
  `L` data version; let Steam verify the game files first.
