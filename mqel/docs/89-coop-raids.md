# Parties and co-op raids

Status: built and tested on a copy of the live data (2026-11-22). Code:
`server/parties.py`, `server/raids.py`, hooks in `castles.py`
(`find_castle`, `attack_selection`), `account_state.py` (region 11 open for
everyone), `level60.py` (region 11 data), `game_server.py` (`_party`,
`_raid_bonus`, `raids.VIEWER`), UI `server/ui_mods/party.html` (UI patch 17,
map styling `ui_patches.region11_css`).

## Changes after the first test (2026-11-22, evening)

- **36 raid castles + boss:** three different castles per tier (ids
  `61000 + tier * 10 + variant`, variant 0-2), all twelve tiers spread over
  the five rings of the 3D selection (up to 12 castles a ring), plus
  **Warlord's Keep** (61999, level 30): Little Spitaly's boss castle with
  swapped monsters, the region boss.
- **Sky:** the client picks the selection sky by counting the regions *with
  a boss* (region 10 = 8th = Region_8); without a boss region 11 got none
  and stayed black. With Warlord's Keep it is the 9th: Region_9 = Little
  Spitaly's sky, plus Little Spitaly's boss pictures. Goldmaw's Region_8
  now also uses Little Spitaly's sky (in gold colours): Upper Bestmount's
  sky dome sat under the camera ("bubble underneath").
- **No party scaling** while the co-op isn't live (`raids.PARTY_SCALING`
  False): every member faces the normal castle. The party bonus still grows
  with the party size.
- **Warning** before entering the region (click on the island, in-game
  dialog, party.html) and a small "Procedural" label on the island.
- **Map:** the bottom row (Little Spitaly, Bling's Landing, Heated Gardens,
  Friendzone, Competitions) moved left, the co-op island away from the edge
  (`ui_patches.BOTTOM_ROW`, `REGION11_LEFT`).
- **Party button:** two small Friends glyphs (four people) in the lobby
  bar's own colours (`png_tint.party_icon`).

## Changes (2026-11-23, v1.4.4): start region

- The client opens the region with the highest id at game start and on the
  Attack button. Since the co-op raids exist, that is region 11 (Status 3
  didn't change it). The client asked for
  `GetAttackSelectionList?attackRegionId=11` right after login.
- Fix in the lobby UI (`ui_mods/party.html`, `onRegionShown` on the game's
  `castleSelectionPopulatedEvent`): an automatic landing in region 11 is
  redirected with `game://attackSelection/showCastleSelection?regionId=N`:
  - at game start to the **home region** (`/party/state` -> `HomeRegion`,
    `raids.home_region`: the selected hero's region in progress, Status 2,
    highest id, without 1, 2 and 11);
  - later (Attack button) to the **last region** the player was in.
- A region clicked on the map (`attack-region-id`, within 30 s) or a party
  raid (`raidStart`) is kept, so entering the co-op raids on purpose works
  and you stay there after a raid.
- The lobby page reloads between scenes, so the last region lives in
  localStorage (`mqelLastRegion`) with a heartbeat (`mqelRegionBeat`,
  every 15 s). A heartbeat older than 90 s means a new game start, so the
  player goes home.
- Map: Upper Bestmount (9) and Stabbinshire (8) moved apart from
  Splendorado (`ui_patches.TOP_ROW`: 9 at left 890, 8 at left 1520).
- Sky details and the recipe for new regions: `docs/93-region-sky.md`.

## Fix (2026-11-23, v1.4.3.2): co-op sky and banner emblem

- **Sky:** with the self-made environment names ("Region_8" for region 10,
  "Region_9" for region 11) the co-op raids stayed black in the game, even
  though both entries exist in ENVIRONMENTSETTINGSCOLLECTION. The owner's
  screenshots dated the good Splendorado look (golden clouds all around,
  2026-11-21 12:49) to the first exe patch, which used the exe's own
  "Region_7"; the "bubble underneath" shots were older (05:48). The default
  case now only pushes the exe's own strings (the same addresses the cases
  of id 9 and id 3 push): id 10 -> "Region_7" (Upper Bestmount), id 11+ ->
  "Region_1" (Little Spitaly). No strings in the int3 padding any more.
  Rule: for the sky, only use names of the original regions.
- **Banner emblem:** boss buttons are 214 x 480 strips of four 120 px states
  (normal, hover, pressed, disabled), medallion ~104 px at x 113. The co-op
  emblem was a bare 92 px square stretched to the button width (far too
  big); now `ui_patches._medallion_strip` builds the same strip: friends
  icon on a purple disc with a gold rim.

## Fix (2026-11-23, v1.4.3.1): Attack button crash

The v1.4.3 sky patch replaced the exe's default case, whose old code
(`mov ecx,[global]` at +0 and +13) had base relocations at +2 and +15. The
one at +2 was left behind and now pointed into `mov ecx,[esp+8]; cmp eax,9`.
The exe uses ASLR (DYNAMICBASE), so the loader added the load delta into
those bytes and the game crashed as soon as the castle selection asked for
a sky (the Attack button). `patch_exe` now turns that relocation into a
padding entry (`_drop_relocation`), adds the two for the new name addresses,
and ships the patch only if the relocations in the patched code are exactly
those two (`_relocations_in`). Rule: when overwriting exe code, check the
.reloc entries inside the overwritten bytes.

## Changes (2026-11-23, v1.4.3)

- **Party raid flow:** the leader picks a raid in the party window (list of
  the party's raid castles, `/party/raids`, `raids.menu`), every member gets
  a Ready / No thanks prompt (also as a pop-up in the lobby), and when all
  are ready the server sets a start time (6 s); every game then opens the
  same castle at the same moment (UI: `NavigationController.requestNavigation`
  with `game://attack/startAttack?castleAccountId=...&castleMode=UbisoftCastle&attackSource=RegularSelection&attackRegionId=11...`,
  like the castle popup's Attack button). After everyone finished
  (EndAttack, `parties.raid_done`) the leader picks the next raid; a "No
  thanks" or someone leaving ends the round.
- **Locked castle:** while a raid is picked or running, the party's seed is
  fixed (`parties.raid_seed`): rerolls or someone finishing first no longer
  change the castle under the others.
- **The party window shows which raid** the members are in.
- **Invitations** pop up in the lobby with Join / No thanks.
- **Co-op warning:** not shown when you are in a party; "Don't show again"
  (browser storage of the game UI).
- **Live panel:** gold and life force now count (the game passes the
  currency type as a name, "IGC"); XP is not reported during an attack, so
  the panel shows gold, life force and items.
- **Start region:** region 11 is stored as completed (Status 3) for every
  hero; with Status 2 the client took it as the current region and every
  reload or game start opened the co-op raids.
- **Sky (finally):** the exe names the castle-selection sky in a switch over
  the region ids 1-9 (OO_None, Region_FriendsZone, Region_Competition,
  Region_1 ... Region_7; anything higher fell into the default case).
  `level60.patch_exe` now rewrites the default case: region 10 ->
  "Region_8" (Little Spitaly's sky in gold), region 11 -> "Region_9"
  (Little Spitaly's sky). The two names sit in the int3 padding in front of
  the function; both new absolute addresses get base relocations. The old
  patch (region 10 = case of region 9, Upper Bestmount's sky dome under the
  camera) is gone. Players get the patched exe from the launcher (GameBin).
- **Banner:** the co-op emblem (friends icon of the island, purple) instead
  of the boss medallion, level "5-60".

## Changes (2026-11-22, v1.4.2)

- **Levels:** three castles per 5-level bracket at different levels (5, 7,
  9, 10, 12, 14 ... 57, 59: 33 castles), ids `61000 + level * 10`.
- **Bosses at 15, 30, 45 and 60:** Warlord's Outpost (15, layout of story
  boss castle 15), Warlord's Fortress (30, castle 17), Warlord's Citadel (45,
  castle 19) in the list, Warlord's Keep (60, castle 20) as the region boss
  (`raids.BOSS_LEVELS`). The bosses keep their boss creature.
- **Random names** like the other regions: a story castle's name per
  castle (not region 10's "Gilded" copies).
- **Traps stay as in the layout:** swapping them left rail traps without
  rails and trap generators without traps.
- **More castles:** shop SKUs for regions 10 and 11 (ItemType 14, ItemId =
  region, copies of region 9's: 10 blings / 1,500 gold, codes 72101/72102
  and 72111/72112); without them the button didn't show.
- **Region banner picture:** Warlord's Keep shows Little Spitaly's boss
  medallion in purple (`ui_patches.boss10_css` / `popup10_css`).
- **Sky:** still black with Region_9; the Little Spitaly sky now also exists
  as Region_10 and Region_11 (whichever name the game looks up). Not yet
  verified in the game.
- **Party button** moved after the Notifications button (the notification
  list's arrow pointed at it).

## For players

- **Party button** (a group of four, after Clans): invite friends (up
  to 4 players), accept or decline invitations (red badge and a message
  when one arrives), leave; the leader can remove players. A leaving
  leader hands over to the next member; a party of one dissolves.
- **Co-op Raids** (region 11, purple island right of Competitions, label
  5-60): three raid castles at each level 5, 10, 15 ... 60 (36) and the
  boss castle Warlord's Keep.
- **Same castle for the party:** every member gets the identical castle and
  attacks it in their own game with their own loot.
- **Difficulty:** the normal castle for every member (party scaling, 55%
  more monsters per extra member, is built in but off until the co-op is
  live).
- **More castles** (the selection's reroll button, priced by the game):
  any member's reroll gives the whole party new raid castles.
- **Live party panel** (left side, during a raid): the other members'
  health bar, gold, XP and items picked up, "down!" when they fall,
  "loading" / "in the lobby" / "offline" otherwise. Updates every 3 s.
- **Party bonus:** when every member has cleared the same raid castle, each
  gets gold and life force (120 x tier x party size) and 2-4 crafting
  materials (Basic below 20, Exceptional below 40, Legendary below 55,
  Epic from 55), once per raid castle, with a message in the game.

## Not possible: seeing friends move in your castle

Each attack runs entirely inside one game (the server only gets the result
at the end), so other players can't appear in your castle. See the
research notes on live co-op (docs/91-live-coop-research.md) for what that
would need.

## How it works

- **Castle ids** 61005 ... 61060 (`RAID_BASE` + tier) are the same for
  everyone. `find_castle` builds the castle for the player of the current
  request (`raids.VIEWER`, set in `_handle` after the player is known):
  seed and size from the party, `seed = crc32("party-<id>/<sum of the
  members' region-11 rerolls>")`. Castle selection, castle popup and
  StartAttack all go through `find_castle`, so they agree.
- **Generator** (`raids._build`, cached): a story castle with 8+ rooms
  (not region bosses, not tutorial) as layout; every creature type swapped
  for a non-boss creature of similar construction points (+-30%); traps
  swapped at random; random theme; `level60._scaled` sets the level, the
  tiers and the castle heart. Party copies get new creature ids on the
  same spot (the game pushes them apart).
- **Region 11 data** (level60 edits, shipped with the DataBin version and
  written into the server's loose settings by `tools/apply_level60.py`):
  AttackAdvisorSettings entry (LevelMin 5, LevelMax 9 = the 5 rings of the
  3D selection, no boss, like the Friends region), the 3D scene of region 3
  (BossCastleModelsByRegion "11"), sky Region_9 = copy of Region_1, Oasis
  texts 16900 ("Co-op Raids") and 16910+ ("Co-op Raid N").
- **Party endpoints** `/party/state` (GET), `invite {target}`, `accept
  {party}`, `decline {party}`, `leave`, `kick {target}`, `live {Life,
  MaxLife, Gold, LifeForce, Xp, Items, State}` (POST), with the Ingame
  Market web token (`w`). Invitations to friends only, 15 minutes.
  `parties.json` keeps parties, invitations and raid clears; live status
  and bonus messages only in memory.
- **Live data** comes from the game UI's own events
  (heroLifeChangedEvent, walletCurrencyUpdatedInAttackEvent,
  heroXpChangedEvent, itemLootedEvent, startAttackEvent).

## Party button tile (2026-11-23, v1.4.5)

The party button now has the dark-blue tile of the 2015 lobby buttons
(Friends, Clans, Notifications): `png_tint.party_icon_tiled` cuts the
Friends glyph from the 2015 `BTNFRIENDS.PNG`, makes it a party of four and
draws it on the 2015 `BTNNOTIFICATIONS.PNG` tile (normal / hover /
pressed). The 2015 sprites are in
`server/data/steam/Data/Generated/Web/LOBBYBAR/BTN/` (the copies in
`client/` are the 2014 ones without tile).
