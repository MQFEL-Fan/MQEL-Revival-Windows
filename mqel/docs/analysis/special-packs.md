# Special Packs: Content and Shop Value

Generated 2026-10-17 from `GeneralSettings/SpecialPackSettings.json` and
`ShopSettings/ShopSkuBaseSettings.json` as the basis for the pack prices
(docs/70-bling-wirtschaft.md). **Shop value** = sum of the lowest active
Bling prices of the individual items (inventory tab 200); items without a
Bling price do not count (column "no price"). Without the 4 dropped packs
16, 17, 19, 70. Early hero access is left out, emotes do not count.

**Pack only** = contents without an active shop price (incl. hero and castle
skins). **Proposal** (automatic, to be corrected): dropped if internal
(testers/QC/Golden Pony) or fully contained in another pack (exception: tiers
of the same series, e.g. Diamond ranks); premium 2500 for promo/limited packs
with pack-only content; large 1500 with pack-only content or shop value
≥ 1500; medium 800 from 500; otherwise small 300. Contained Blings are removed
when sold. Special case 72 Infinite Pack: the rule only counted the 7 inventory
tabs (1400). On top come 111 items across 21 castle level tiers
(`PerLevelShopSkus`): 47 of them worth 18,631 Blings together in the shop, 64
otherwise only for gold. Total value over 20,000, but it only comes with the
castle level. Proposal: its own tier **4000** (medium player ~6 months, heavy
player ~2 months), the flagship of the shop.

| Id | Name | Group | Content | Shop value | No price | Contained Blings | Pack only | Proposal |
|---|---|---|---|---|---|---|---|---|
| 1 | DoubleO - Chunk of Change | DoubleO | castle skin, 1 inventory tab | 200 | 1 castle skin | 1500 | 1 | 1000 (decided) |
| 2 | DoubleO - Legit Fan(Knight) | DoubleO | 6 equipment, 1 monster, 1 hero skin, castle skin, 1 inventory tab | 200 | 6 equipment, 1 creatures, 1 hero skin/boost, 1 castle skin | 5000 | 8 | large 1500 |
| 3 | DoubleO - Legit Fan(Archer) | DoubleO | 6 equipment, 1 monster, 1 hero skin, castle skin, 1 inventory tab | 200 | 6 equipment, 1 creatures, 1 hero skin/boost, 1 castle skin | 5000 | 8 | large 1500 |
| 4 | DoubleO - Legit Fan(Mage) | DoubleO | 6 equipment, 1 monster, 1 hero skin, castle skin, 1 inventory tab | 200 | 6 equipment, 1 creatures, 1 hero skin/boost, 1 castle skin | 5000 | 8 | large 1500 |
| 5 | DoubleO - High Roller | DoubleO | 12 equipment, 1 themes, 2 monsters, 3 hero skins, castle skin, 2 inventory tabs | 799 | 12 equipment, 2 creatures, 3 hero skins/boosts, 1 castle skin | 13000 | 16 | large 1500 |
| 6 | DoubleO - Special High Roller Retail | DoubleO | 12 equipment, 1 themes, 2 monsters, 3 hero skins, castle skin, 3 inventory tabs | 999 | 12 equipment, 2 creatures, 3 hero skins/boosts, 1 castle skin | 15000 | 16 | dropped (contained in 5) |
| 7 | DoubleO V2 - Chunk of change knight | DoubleOV2 | 3 equipment, 1 hero skin, castle skin, 1 inventory tab | 200 | 3 equipment, 1 hero skin/boost, 1 castle skin | 2500 | 5 | large 1500 (decided) |
| 8 | DoubleO V2 - Chunk of change Archer | DoubleOV2 | 3 equipment, 1 hero skin, castle skin, 1 inventory tab | 200 | 3 equipment, 1 hero skin/boost, 1 castle skin | 2500 | 5 | large 1500 (decided) |
| 9 | DoubleO V2 - New legit fan Mage | DoubleOV2 | 6 equipment, 1 monster, 1 hero skin, castle skin, 1 inventory tab | 200 | 6 equipment, 1 creatures, 1 hero skin/boost, 1 castle skin | 5000 | 8 | dropped (contained in 4) |
| 10 | DoubleO V2 - New High Roller | DoubleOV2 | 12 equipment, 1 themes, 2 monsters, 3 hero skins, castle skin, 2 inventory tabs | 799 | 12 equipment, 2 creatures, 3 hero skins/boosts, 1 castle skin | 13000 | 16 | dropped (contained in 5) |
| 11 | Diamond - Supply Pack | Diamond | 4 equipment | 0 | 4 equipment | 500 | 4 | dropped (contained in 14) |
| 12 | Diamond - Defender Pack | Diamond | 2 equipment, 1 themes, 1 monster | 850 | 2 equipment, 1 creatures | 1050 | 2 | dropped (contained in 14) |
| 13 | Diamond - Attacker Pack | Diamond | 3 equipment, 1 hero skin | 0 | 3 equipment, 1 hero skin/boost | 1050 | 4 | dropped (contained in 14) |
| 14 | Diamond - Ultimate Pack | Diamond | 9 equipment, 1 themes, 1 monster, 1 hero skin, 1 inventory tab, emotes | 1765 | 4 equipment, 1 creatures, 1 hero skin/boost | 6000 | 5 | large 1500 |
| 15 | Diamond - Pack Retail | Diamond | 1 equipment, 1 monster, 2 inventory tabs | 410 | 1 creatures | 2800 |  | small 300 |
| 18 | Diamond - Supply + Attack + Defend pack | Diamond | 4 equipment, 1 themes, 1 monster, 1 hero skin | 850 | 4 equipment, 1 creatures, 1 hero skin/boost | 2800 | 5 | dropped (contained in 14) |
| 20 | New Retail Pack | Diamond | 4 equipment, 1 themes, 1 monster, 1 hero skin | 850 | 4 equipment, 1 creatures, 1 hero skin/boost | 1050 | 5 | dropped (contained in 14) |
| 21 | Pets pack for testers | Diamond | 27 equipment | 29094 | 2 equipment |  |  | dropped (all 27 pets, individually in the shop; decided) |
| 22 | IGN Boost Pack | Diamond | 3 equipment | 0 | 3 equipment |  | 3 | dropped (contained in 11) |
| 23 | Free Hero Weekend - Archer + Knight + Boosts | Diamond | 4 equipment | 0 | 4 equipment |  | 4 | dropped (contained in 11) |
| 24 | Free Hero Weekend - Archer + Mage + Boosts | Diamond | 4 equipment | 0 | 4 equipment |  | 4 | dropped (contained in 11) |
| 25 | Free Hero Weekend - Knight + Mage + Boosts | Diamond | 4 equipment | 0 | 4 equipment |  | 4 | dropped (contained in 11) |
| 26 | Free Hero Weekend - Archer + Lil Arachbro | Diamond | 1 equipment | 500 |  |  |  | medium 800 |
| 27 | Free Hero Weekend - Knight + Lil Flameo | Diamond | 1 equipment | 575 |  |  |  | medium 800 |
| 28 | Free Hero Weekend - Mage + SnuggleMuffin | Diamond | 1 equipment | 500 |  |  |  | medium 800 |
| 29 | Wannabe packs - Geek Mage | Diamond | 2 equipment |  | dropped (contained in 45) |  |  | dropped (contained in 45) |
| 30 | Wannabe packs - Cute Mage | Diamond | 2 equipment |  | dropped (contained in 45) |  |  | dropped (contained in 45) |
| 31 | Wannabe packs - Gangsta Mage | Diamond | 2 equipment | 750 |  |  |  | dropped (contained in 45) |
| 32 | Wannabe packs - Gothic Mage | Diamond | 2 equipment |  | dropped (contained in 45) |  |  | dropped (contained in 45) |
| 33 | Wannabe packs - Geek Archer | Diamond | 2 equipment |  | dropped (contained in 29) |  |  | dropped (contained in 29) |
| 34 | Wannabe packs - Cute Archer | Diamond | 2 equipment |  | dropped (contained in 30) |  |  | dropped (contained in 30) |
| 35 | Wannabe packs - Gangsta Archer | Diamond | 2 equipment | 750 |  |  |  | dropped (contained in 31) |
| 36 | Wannabe packs - Gothic Archer | Diamond | 2 equipment |  | dropped (contained in 32) |  |  | dropped (contained in 32) |
| 37 | Wannabe packs - Geek Knight | Diamond | 2 equipment |  | dropped (contained in 29) |  |  | dropped (contained in 29) |
| 38 | Wannabe packs - Cute Knight | Diamond | 2 equipment |  | dropped (contained in 30) |  |  | dropped (contained in 30) |
| 39 | Wannabe packs - Gangsta Knight | Diamond | 2 equipment | 750 |  |  |  | dropped (contained in 31) |
| 40 | Wannabe packs - Gothic Knight | Diamond | 2 equipment |  | dropped (contained in 32) |  |  | dropped (contained in 32) |
| 41 | Wannabe packs - Geek Runaway | Diamond | 2 equipment |  | dropped (contained in 29) |  |  | dropped (contained in 29) |
| 42 | Wannabe packs - Cute Runaway | Diamond | 2 equipment |  | dropped (contained in 30) |  |  | dropped (contained in 30) |
| 43 | Wannabe packs - Gangsta Runaway | Diamond | 2 equipment | 750 |  |  |  | dropped (contained in 31) |
| 44 | Wannabe packs - Gothic Runaway | Diamond | 2 equipment |  | dropped (contained in 32) |  |  | dropped (contained in 32) |
| 45 | Wannabe packs - Geek + Cute + Gangsta + Gothic | Diamond | 8 equipment | 33000 |  |  |  | large 1500 |
| 46 | Watch_Dog Theme | Diamond | 1 themes |  | dropped (contained in 47) |  |  | dropped (contained in 47) |
| 47 | Watch_Dogs Pack | Diamond | 12 equipment, 1 themes, 1 inventory tab | 3245 | 1 |  | 1 | premium 2500 |
| 48 | Magic find boost X1 | Diamond | 1 equipment | 0 | 1 equipment |  | 1 | dropped (contained in 2) |
| 49 | SteamUnderwearPack | Diamond | 4 equipment |  | small 300 |  |  | small 300 |
| 50 | SteamAmulet | Diamond | 1 equipment |  | large 1500 |  |  | large 1500 |
| 51 | SteamPet | Diamond | 1 equipment |  | medium 800 |  |  | medium 800 |
| 52 | Diamond - Defender Pack - Summer Sale | Diamond | 2 equipment, 1 themes, 1 monster | 850 | 2 |  | 2 | dropped (contained in 12) |
| 53 | Diamond - Attacker Pack - Summer Sale | Diamond | 3 equipment, 1 hero skin | 0 | 4 |  | 4 | dropped (contained in 13) |
| 54 | Diamond - Supply + Attack + Defend pack - Summer Sale | Diamond | 4 equipment, 1 themes, 1 monster, 1 hero skin | 850 | 4 equipment, 1 creatures, 1 hero skin/boost | 500 | 5 | dropped (contained in 14) |
| 55 | Diamond - Ultimate Pack - Summer Sale | Diamond | 9 equipment, 1 themes, 1 monster, 1 hero skin, 1 inventory tab, emotes | 1765 | 4 equipment, 1 creatures, 1 hero skin/boost | 500 | 5 | dropped (contained in 14) |
| 56 | Limited Edition Pack | Diamond | 153 monsters, 110 traps | 33880 | 2 |  | 2 | dropped (value too high; decided) |
| 57 | Sick Creature Pack | Diamond | 67 monsters, 29 traps | 3007 | 40 |  | 40 | dropped (Sick Creatures were patched out; decided) |
| 58 | Attacker Pack Oct2014 - Marleyboned Mage | Diamond | 4 equipment, 1 inventory tab | 1149 | 2 |  | 2 | dropped (contained in 62) |
| 59 | Attacker Pack Oct2014 - Spider Pirate Archer | Diamond | 4 equipment, 1 inventory tab | 1000 | 2 |  | 2 | dropped (contained in 62) |
| 60 | Attacker Pack Oct2014 - Chewing Gum Runaway | Diamond | 4 equipment, 1 inventory tab | 900 | 2 |  | 2 | dropped (contained in 62) |
| 61 | Attacker Pack Oct2014 - Phoenix Dragon Knight | Diamond | 4 equipment, 1 inventory tab | 1240 | 2 |  | 2 | dropped (contained in 62) |
| 62 | Attacker Pack Oct2014 - Complete with 4 heroes | Diamond | 10 equipment, 4 inventory tabs | 4289 | 2 |  | 2 | dropped (contained in 66) |
| 63 | Defender Pack Oct2014 - Bronze | Diamond | 1 themes, 60 monsters, 61 traps, 19 decorations, material | 1619 |  |  |  | dropped (contained in 64) |
| 64 | Defender Pack Oct2014 - Silver | Diamond | 2 themes, 81 monsters, 71 traps, 40 decorations, material | 3849 |  |  |  | dropped (contained in 65) |
| 65 | Defender Pack Oct2014 - Gold | Diamond | 3 themes, 95 monsters, 77 traps, 63 decorations, material | 6299 |  |  |  | dropped (contained in 66) |
| 66 | The Big Pack - Oct2014 | Diamond | 10 equipment, 3 themes, 95 monsters, 77 traps, 63 decorations, 4 inventory tabs, material | 10588 | 2 |  | 2 | 4000 (value ~10,500; decided) |
| 67 | Halloween Pack Oct2014 | Diamond | 1 themes, 4 monsters, 20 decorations | 1899 |  |  |  | large 1500, only during Halloween (decided) |
| 68 | Magical Golden Pony | – | 55 equipment, 24 themes, 724 monsters, 109 traps, 20 decorations, 4 hero skins, 7 inventory tabs, material, 2 shop items | 138839 | 13 equipment, 304 creatures, 66 traps, 6 theme, 2 ShopSku, 4 hero skins/boosts, 1 material |  | 53 | dropped (internal, decided) |
| 69 | MoM Special pack | – | material, 1 shop item | 0 | 1 ShopSku, 1 material |  |  | small 300 |
| 71 | SpecialPackBundle | – | 1 equipment, 15 monsters, 5 traps, 55 decorations | 3494 |  |  |  | large 1500 |
| 72 | Infinite Pack Bundle | – | 7 inventory tabs, 75 shop items, items per castle level | 1400 |  |  |  | special tier 4000 (see above) |
| 73 | XP Boost Pack | – | 1 equipment | 0 | 1 equipment |  | 1 | dropped (contained in 11) |
| 74 | QC Team Only - All Beta Rewards | – | 9 equipment, 1 themes, 1 traps | 1500 | 9 |  | 9 | premium 2500 (beta QC rewards, decided) |
| 75 | Look Ma, I'm the best! | – | 52 decorations | 0 | 52 |  | 52 | premium 2500 |
