# Bling Economy (implemented, switch in the web tool: Economy)

Status 2026-10-17. Goal: Blings (PremiumCash) become an **earned** currency.
Real money is not possible (rights belong to Ubisoft), and free Blings (the
current test shop `server/bling_shop.py`) devalue the game. The shop and prices
in the client basically stay; what changes is mainly **where** Blings come
from.

## Guidelines

- Blings only for achievement and progress, **not for attendance**: no
  login bonuses, no streaks. Whoever takes a break catches up with the same
  playing time.
- Moderate FOMO is fine (seasonal events, league season, competitions),
  as long as the rewards are small and skipping does not hurt.
- Heroes stay behind Blings (long-term goal); the trial promos
  (`server/free_trials.py`, discount via level goals) stay.
- The Bling shop stays, but instead of Blings it sells the former real-money
  packs (cosmetics etc.) **for Blings**, including older ones.
- Only the server awards Blings; a cap per account and week against
  alt-account farming.

## Inventory

### Spending (ShopSettings/ShopSkuBaseSettings.json)

5095 SKUs, of which a good 2000 have a Bling price (`CurrencyType` 1). Active SKUs:

| Kind | Count | Blings (min / typical / max) | Category |
|---|---|---|---|
| Hero | 14 | 798 / 1200 / 3012 | Long-term goal |
| CastleTheme | 18 | 99 / 850 / 1500 | Cosmetic |
| Decoration | 60 | 15 / 90 / 10000 | Cosmetic |
| HeroUpgrade | 116 | 100 / 500 / 999 | Progress |
| HeroEquipmentItem | 748 | 0 / 80 / 19998 | Progress (much also for gold) |
| Building, Creature, Trap, …Upgrade | ~640 | mostly 50–200 | Shortcut |
| Consumable | 65 | 5 / 60 / 700 | Shortcut |
| ForgeCrafted/-Reforged | 120 each | 15 / 60 / 120 | Shortcut |
| InventoryTabs, Room, ShowMoreCastle | 47 | 5–200 | Convenience |

Plus time skips with Blings (`GeneralSettings/TimeSettings.json`).

Heroes: the shop shows all heroes for **950 Blings** (promo SKUs "PM"),
no LifeForce (confirmed in game). The other hero SKUs (1000 LifeForce,
Daily Deal 798/1200, Featured 3012) are in the data but are not offered.

### Sources in the original (without real money)

| Source | Amount | File |
|---|---|---|
| Objectives | once 200 + 7 × 50 | ObjectiveSettings.json |
| League season end, top places | 5–30 | SeasonalCompetitionSettings.json (`LeaderClosingPeriodRewards`) |
| Keeping the league | 1–4 per season | same (`LeagueMaintainReward`) |
| Competitions / challenges | 25 / 10 / 5 for places 1–3 | UbisoftCompetitionSettings.json, ChallengeSettings.json |
| Bling mine (building 16) | 1/h, storage 25, lootable | Buildings/000016 - BlingMine |
| Validating delegated castles | 3 | AttackerRewardSettings.json |
| Achievements (36) | **no Blings** | AchievementSettings.json |

Our server already pays out all these sources (objectives.py, leagues.py,
competitions.py, castles.py for validation, the mine via
`HarvestMineBuildingCommand` with the original values 1/h, storage 25).
Production and storage of the mine are in the building data, which the client
also displays: changes via data patch (DataBin, reversible via the patcher).

Without money, the original therefore yielded only a few hundred Blings; a
hero (~1000) was practically unreachable. The Bling mine with its small
storage is exactly the collect-on-schedule pattern we want to avoid.

### Special packs (GeneralSettings/SpecialPackSettings.json)

75 packs: 56 "Diamond", 11 "DoubleO"/"DoubleOV2", 8 individual ones (e.g.
Infinite Pack 72, Halloween 67). Contents: equipment (60 packs), early hero
access (39), monsters (24), themes (19), hero boosts (17), inventory tabs
(22), traps, decorations, emotes, materials. **21 packs contain Blings
themselves** (e.g. "Chunk of Change" 1500), which must be removed when the
pack is sold for Blings.

## Design (numbers for discussion)

The reference is **active playing time**, not calendar time. Assumption
for a "normal" player: about 4 hours per week.

| Goal | Target time | ≈ playing hours |
|---|---|---|
| first cosmetic item (~100) | first days | 2–3 h |
| second hero (950) | 2–3 weeks | ~10 h |
| each further hero | 1–2 months | 20–30 h |
| big pack | a few weeks | 15–25 h |
| everything premium | many months | 200+ h |

From this, two income streams:

1. **One-time pot (~3000 Blings)**, split across achievements (~1500) and
   objectives (1550). Milestones are dropped (no client UI). Carries the
   start, so that the second hero comes quickly.
2. **Ongoing ~30–40 Blings per playing hour**: rare Bling loot when raiding
   (largest share), plus league and competitions as a small bonus
   (original values roughly doubled), seasonal events with small prizes.
   Bling mine see below.

**Pack prices:** derived from the content, not from the old euro price:
sum of the Bling prices of the individual items with a pack discount, without
contained Blings; packs that mainly contain shortcuts with a surcharge or not
at all. Without value (decided 2026-10-17): **early hero access** (a relic of
the development period) is dropped; **emotes** stay in but do not count
towards the price (practically single-player, at most someone sees them in a
replay). This leaves nothing in 4 packs, so they are dropped: 16 "Runaway
Only", 17 "Mage Only" (hero access only), 19 "PC Gamer Bling Pack", 70 "Steam
Big Bling Pack" (Blings only).

### Bling mine

Currently our server gives away the **whole fill level** when raiding
(`loot.stealable_buildings`); gold/LifeForce mines only the production of the
last hour (`mine_stealable`, `MinePeriodStealableAmountInSeconds`). With large
storage an occasional player would otherwise be a jackpot and would still have
to collect daily. Therefore:

- Lootable is at most one hour of production (at least
  `PremiumCashMineLossAmount` = 1), the rest stays with the owner.
- Destroying only sets the yield of this attack to zero, not the content.
- Production 1/h, storage 42 (full after 42 h): deliberately rewards players
  who collect every 1–2 days (~150–168 per week); weekly only 42 (decided
  2026-11-09).
- Price 500 instead of 999 Blings (`Mine.Price`, data patch of SKU 15522 in
  ShopSkuBaseSettings, the server books via `balance.sku_price`): earned after
  ~3–5 weeks when collecting every 2–3 days, about 3 weeks of income for an
  average player; with 999 it was up to 24 weeks.
- Up to three Bling and three material mines per castle
  (BuildingInstanceRequirements, from castle heart 2), as in the original:
  shop SKUs 15522 (Bling mine, 500 Blings, original 999) and 15699 (material
  mine, 500 Blings) with quota 3 (`special_packs.SHOP_QUOTAS`); pack mines
  (Infinite Pack, Material-O-Matic) count towards the same limit, which the
  server checks when building.

### Projection

Assumptions: loot 25 Blings per playing hour; one-time pot 2500 over the
first ~60 playing hours (~42/h, until it is empty); league/competitions 5–60
per week; mine 42 per week.

| Player | Playing time/week | Blings/week at first | after that | 2nd hero (950) | further heroes |
|---|---|---|---|---|---|
| Light | 1 h | ~115 | ~72 | ~8 weeks | ~13 weeks |
| Medium | 4 h | ~330 (15 weeks) | ~160 | ~3 weeks | ~6 weeks |
| Heavy | 15 h | ~1090 (4 weeks) | ~470 | < 1 week | ~2 weeks |
| Extreme | 40 h | pot empty after ~1.5 weeks | ~700 (cap) | < 1 week | ~1.5 weeks |

Everything premium (heroes, 18 themes, decorations, packs) roughly
30,000–40,000: years for a medium player, ~1.5 years for a heavy player.

### Cap

**Weekly cap instead of daily cap** (a daily cap rewards daily play): at most
600 Blings from loot in the last 7 days. Only affects extreme players and farm
accounts. One-time pot and league are not capped (finite or rare).

### Shortcuts

In playing time (25 Blings/h): time skip 5 min / 1 h / 24 h = 5 / 50 / 850
Blings ≈ 12 min / 2 h / 34 h; monster or trap directly 50–200 ≈ 2–8 h;
material pack 50–200 ≈ 2–8 h; inventory tab 200 ≈ 8 h; delegating validation
10 ≈ 25 min. With earned Blings the original prices limit themselves:
**lock nothing, raise nothing**, no price patch needed. Gold/LifeForce for
Blings does not exist in the data.

### Pack selection (decided 2026-10-17)

A fixed price per pack instead of the sum of the individual items; list with
content and decision in `docs/analysis/special-packs.md`. **23 packs on
offer**, prices 300–4000 (top: 66 The Big Pack and 72 Infinite Pack at 4000
each); Halloween (67) only during the event; 74 Beta QC rewards as premium
2500. Dropped: internal packs (21 all pets, 68 Golden Pony), duplicates and
promo copies, 56 Limited Edition (value too high), 57 Sick Creatures (stay
patched out). Can still be adjusted until go-live.

**All Heroes Pack** (2026-11-22, `bling_shop.HERO_PACK_ID` 900, not a
SpecialPack): every hero the player doesn't own yet, price = missing heroes
x 950 x `HeroPack.Percent` (default 70 %), rounded to 50: 2,000 for three,
1,350 for two, not offered for one. Details: docs/95-preprod-2026-11-22.md.

## Implementation

- **Settings** (`server/balance.py`, `state/<profile>/balance.json`):
  switch `Enabled` (default off) and the values, in the web tool under
  **Economy** (admin.Get/SetBalance, limits checked). So far: Bling mine.
- **Client values** (marked "client" in the web tool) are delivered by the
  patcher in `settings.bin`: DataBin version `….B<CRC>`; every state stays in
  `History`, so that deltas also work from older states. settings.bin is
  always in the DataBin package (original if off), so that switching off
  returns to the original. Own LZO packer (settings_archive.lzo_compress):
  ~4 MB delta, build ~17 s on the first request.
- **Bling mine:** castles.mine_rank delivers ProductionPeriod/Capacity from
  balance when Enabled; loot.stealable_buildings limits the loot to StealHours
  of production (at least 1). A newly built Bling mine starts empty as in the
  original (MineManager.AddMineStatus); harvesting reports EntityHarvestType
  PremiumCashMine (only in the final client).
- **Achievements:** amount per achievement in the web tool (default points × 2,
  ~1500 in total, kind "UI"). Paid once per achievement at the amount valid at
  that time, also retroactively for already reached ones as soon as the Bling
  economy is on (`AchievementBlingsPaid` in the account, ledger source
  `achievements`). Lobby counter: UI patch 11 (the 0.36 TopView puts
  `.premiumAmount` in `#lobby-index-premium-wallet`, the wallet module
  looked inside `#modules-lobby-wallet-container`, so the number stayed empty).
  Display: UI patch 9 (ui_patches.py) puts "+N" with the
  Bling symbol under the points in the popup; the amounts are in the helper
  `achievementBlings` (hyperquest.extensions.js), so every change changes the
  GameUI version. Older GameUI states get all files anew (before: no patch
  at all).
- **Objectives:** Bling amount per objective with a Bling reward (8 of them,
  kind "client"): default 200 for Snottingham and the six bosses, 150 for
  Heist Part 2 (original 200 + 7 × 50 = 550, now 1550). The client displays
  them itself (ObjectiveSettings in settings.bin, repacked together with the
  mine); objectives.rewards pays the same amount. Already completed objectives
  get nothing retroactively.
- **Bling loot:** in real attacks (not practice, tutorial, competition)
  a random creature carries `Loot.Amount` Blings (default 10;
  DefenseIngredientLoot.PremiumCash) with `Loot.Chance` (default 40 %).
  Credited on kill (KilledCreatureIds; the client does not report a separate
  id list for Blings), shown in the report under TotalPremiumCash.
  Cap `Loot.WeeklyCap` (600) in a sliding 7-day window
  (`BlingLootLog` in the account); the remaining budget already caps the drop.
- **League and competitions:** one percentage factor each on all Bling amounts
  (default 200 %, kind "client"): SeasonalCompetitionSettings and
  UbisoftCompetitionSettings in settings.bin; the server calculates the same
  (balance.scale_reward in leagues.settle and competitions.reward).
- **Bling shop:** when Enabled, `/blings` (button "Purchase blings") shows the
  packs as cards with content and price (Economy section Shop, 0 = not on
  offer; 67 Halloween only during the event). Purchase:
  AccountState.buy_special_pack debits and unlocks (ledger `bling-shop`);
  equipment, consumables and materials go into the inventory (if there is no
  room, into the buy-back for free) and are reported as notifications. The
  free test bookings only exist while the economy is switched off.
  Hero access: when Enabled, EarlyHeroAccess is missing in the packs, in the
  server (special_packs.pack) and in settings.bin (balance.DATA_REVISION 2),
  so that heroes only come for Blings; heroes already created stay.

## Way back

1. **Switch on the server** (like maintenance mode), initially off; off =
   current rules.
2. **Price changes in the client** only via patcher packages (deltas against
   the Steam files); remove the package = original prices at the next start.
3. **Ledger:** every Bling credit and every pack purchase with its source,
   for evaluating the balance and for targeted corrections.
   **Implemented:** `state/<profile>/<AccountId>.blings.jsonl`, one line per
   change {Time, Delta, Balance, Source}; Source = request
   (`Service/Method (player)`), for commands with `cmd:<Name>`, for the
   web tool `admin:<Method>` (AccountState._book on save, source per thread in
   account_state.SOURCE).
4. **Backup of the game state** when switching (emergency only).

**Rule when switching back:** players keep everything earned, including
Blings. Corrections only go forward (income, prices). Things are only taken
away in case of abuse (bug, exploit, alt accounts), targeted via the ledger.
If intervention is ever needed: exchange at an announced rate or freeze,
never delete without replacement.

## Open questions

- Achievements: the client knows no reward (only title, description, points).
  Decided: hard-code, amounts per achievement id in the server and via UI
  patch as a line "+N Blings" in the popup
  (`template-achievement-completed-popup`).
- Bling loot: the report shows it (`TotalPremiumCash`), but there is no
  visible drop in combat; left as is.
