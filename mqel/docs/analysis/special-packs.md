# Special Packs: Inhalt und Shop-Wert

Erzeugt 17.10.2026 aus `GeneralSettings/SpecialPackSettings.json` und
`ShopSettings/ShopSkuBaseSettings.json` als Grundlage für die Pack-Preise
(docs/70-bling-wirtschaft.md). **Shop-Wert** = Summe der niedrigsten aktiven
Bling-Preise der Einzelteile (Inventar-Tab 200); Teile ohne Bling-Preis zählen
nicht (Spalte „ohne Preis“). Ohne die 4 entfallenden Packs 16, 17, 19, 70.
Früher Heldenzugang ist weggelassen, Emotes zählen nicht.

**nur im Pack** = Inhalte ohne aktiven Shop-Preis (inkl. Helden- und
Burg-Skins). **Vorschlag** (automatisch, zum Korrigieren): entfällt, wenn
intern (Tester/QC/Golden Pony) oder ganz in einem anderen Pack enthalten
(Ausnahme: Stufen derselben Reihe, z. B. Diamond-Ränge); Premium 2500 für
Promo-/Limited-Packs mit Pack-Inhalten; groß 1500 bei Pack-Inhalten oder
Shop-Wert ≥ 1500; mittel 800 ab 500; sonst klein 300. Enthaltene Blings
fallen beim Verkauf heraus. Sonderfall 72 Infinite Pack: Die Regel zählte nur die
7 Inventar-Tabs (1400). Dazu kommen 111 Artikel über 21 Burg-Level-Stufen
(`PerLevelShopSkus`): 47 davon im Shop zusammen 18.631 Blings wert, 64 sonst
nur gegen Gold. Gesamtwert über 20.000, kommt aber erst mit dem Burg-Level.
Vorschlag: eigene Stufe **4000** (Mittelspieler ~6 Monate, Vielspieler ~2
Monate), das Flaggschiff des Shops.

| Id | Name | Gruppe | Inhalt | Shop-Wert | ohne Preis | enthaltene Blings | nur im Pack | Vorschlag |
|---|---|---|---|---|---|---|---|---|
| 1 | DoubleO - Chunk of Change | DoubleO | Burg-Skin, 1 Inventar-Tab | 200 | 1 Burg-Skin | 1500 | 1 | 1000 (entschieden) |
| 2 | DoubleO - Legit Fan(Knight) | DoubleO | 6 Ausrüstung, 1 Monster, 1 Helden-Skin, Burg-Skin, 1 Inventar-Tab | 200 | 6 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost, 1 Burg-Skin | 5000 | 8 | groß 1500 |
| 3 | DoubleO - Legit Fan(Archer) | DoubleO | 6 Ausrüstung, 1 Monster, 1 Helden-Skin, Burg-Skin, 1 Inventar-Tab | 200 | 6 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost, 1 Burg-Skin | 5000 | 8 | groß 1500 |
| 4 | DoubleO - Legit Fan(Mage) | DoubleO | 6 Ausrüstung, 1 Monster, 1 Helden-Skin, Burg-Skin, 1 Inventar-Tab | 200 | 6 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost, 1 Burg-Skin | 5000 | 8 | groß 1500 |
| 5 | DoubleO - High Roller | DoubleO | 12 Ausrüstung, 1 Themes, 2 Monster, 3 Helden-Skin, Burg-Skin, 2 Inventar-Tab | 799 | 12 Ausrüstung, 2 Creatures, 3 Helden-Skin/Boost, 1 Burg-Skin | 13000 | 16 | groß 1500 |
| 6 | DoubleO - Special High Roller Retail | DoubleO | 12 Ausrüstung, 1 Themes, 2 Monster, 3 Helden-Skin, Burg-Skin, 3 Inventar-Tab | 999 | 12 Ausrüstung, 2 Creatures, 3 Helden-Skin/Boost, 1 Burg-Skin | 15000 | 16 | entfällt (in 5 enthalten) |
| 7 | DoubleO V2 - Chunk of change knight | DoubleOV2 | 3 Ausrüstung, 1 Helden-Skin, Burg-Skin, 1 Inventar-Tab | 200 | 3 Ausrüstung, 1 Helden-Skin/Boost, 1 Burg-Skin | 2500 | 5 | groß 1500 (entschieden) |
| 8 | DoubleO V2 - Chunk of change Archer | DoubleOV2 | 3 Ausrüstung, 1 Helden-Skin, Burg-Skin, 1 Inventar-Tab | 200 | 3 Ausrüstung, 1 Helden-Skin/Boost, 1 Burg-Skin | 2500 | 5 | groß 1500 (entschieden) |
| 9 | DoubleO V2 - New legit fan Mage | DoubleOV2 | 6 Ausrüstung, 1 Monster, 1 Helden-Skin, Burg-Skin, 1 Inventar-Tab | 200 | 6 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost, 1 Burg-Skin | 5000 | 8 | entfällt (in 4 enthalten) |
| 10 | DoubleO V2 - New High Roller | DoubleOV2 | 12 Ausrüstung, 1 Themes, 2 Monster, 3 Helden-Skin, Burg-Skin, 2 Inventar-Tab | 799 | 12 Ausrüstung, 2 Creatures, 3 Helden-Skin/Boost, 1 Burg-Skin | 13000 | 16 | entfällt (in 5 enthalten) |
| 11 | Diamond - Supply Pack | Diamond | 4 Ausrüstung | 0 | 4 Ausrüstung | 500 | 4 | entfällt (in 14 enthalten) |
| 12 | Diamond - Defender Pack | Diamond | 2 Ausrüstung, 1 Themes, 1 Monster | 850 | 2 Ausrüstung, 1 Creatures | 1050 | 2 | entfällt (in 14 enthalten) |
| 13 | Diamond - Attacker Pack | Diamond | 3 Ausrüstung, 1 Helden-Skin | 0 | 3 Ausrüstung, 1 Helden-Skin/Boost | 1050 | 4 | entfällt (in 14 enthalten) |
| 14 | Diamond - Ultimate Pack | Diamond | 9 Ausrüstung, 1 Themes, 1 Monster, 1 Helden-Skin, 1 Inventar-Tab, Emotes | 1765 | 4 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost | 6000 | 5 | groß 1500 |
| 15 | Diamond - Pack Retail | Diamond | 1 Ausrüstung, 1 Monster, 2 Inventar-Tab | 410 | 1 Creatures | 2800 |  | klein 300 |
| 18 | Diamond - Supply + Attack + Defend pack | Diamond | 4 Ausrüstung, 1 Themes, 1 Monster, 1 Helden-Skin | 850 | 4 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost | 2800 | 5 | entfällt (in 14 enthalten) |
| 20 | New Retail Pack | Diamond | 4 Ausrüstung, 1 Themes, 1 Monster, 1 Helden-Skin | 850 | 4 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost | 1050 | 5 | entfällt (in 14 enthalten) |
| 21 | Pets pack for testers | Diamond | 27 Ausrüstung | 29094 | 2 Ausrüstung |  |  | entfällt (alle 27 Pets, einzeln im Shop; entschieden) |
| 22 | IGN Boost Pack | Diamond | 3 Ausrüstung | 0 | 3 Ausrüstung |  | 3 | entfällt (in 11 enthalten) |
| 23 | Free Hero Weekend - Archer + Knight + Boosts | Diamond | 4 Ausrüstung | 0 | 4 Ausrüstung |  | 4 | entfällt (in 11 enthalten) |
| 24 | Free Hero Weekend - Archer + Mage + Boosts | Diamond | 4 Ausrüstung | 0 | 4 Ausrüstung |  | 4 | entfällt (in 11 enthalten) |
| 25 | Free Hero Weekend - Knight + Mage + Boosts | Diamond | 4 Ausrüstung | 0 | 4 Ausrüstung |  | 4 | entfällt (in 11 enthalten) |
| 26 | Free Hero Weekend - Archer + Lil Arachbro | Diamond | 1 Ausrüstung | 500 |  |  |  | mittel 800 |
| 27 | Free Hero Weekend - Knight + Lil Flameo | Diamond | 1 Ausrüstung | 575 |  |  |  | mittel 800 |
| 28 | Free Hero Weekend - Mage + SnuggleMuffin | Diamond | 1 Ausrüstung | 500 |  |  |  | mittel 800 |
| 29 | Wannabe packs - Geek Mage | Diamond | 2 Ausrüstung |  | entfällt (in 45 enthalten) |  |  | entfällt (in 45 enthalten) |
| 30 | Wannabe packs - Cute Mage | Diamond | 2 Ausrüstung |  | entfällt (in 45 enthalten) |  |  | entfällt (in 45 enthalten) |
| 31 | Wannabe packs - Gangsta Mage | Diamond | 2 Ausrüstung | 750 |  |  |  | entfällt (in 45 enthalten) |
| 32 | Wannabe packs - Gothic Mage | Diamond | 2 Ausrüstung |  | entfällt (in 45 enthalten) |  |  | entfällt (in 45 enthalten) |
| 33 | Wannabe packs - Geek Archer | Diamond | 2 Ausrüstung |  | entfällt (in 29 enthalten) |  |  | entfällt (in 29 enthalten) |
| 34 | Wannabe packs - Cute Archer | Diamond | 2 Ausrüstung |  | entfällt (in 30 enthalten) |  |  | entfällt (in 30 enthalten) |
| 35 | Wannabe packs - Gangsta Archer | Diamond | 2 Ausrüstung | 750 |  |  |  | entfällt (in 31 enthalten) |
| 36 | Wannabe packs - Gothic Archer | Diamond | 2 Ausrüstung |  | entfällt (in 32 enthalten) |  |  | entfällt (in 32 enthalten) |
| 37 | Wannabe packs - Geek Knight | Diamond | 2 Ausrüstung |  | entfällt (in 29 enthalten) |  |  | entfällt (in 29 enthalten) |
| 38 | Wannabe packs - Cute Knight | Diamond | 2 Ausrüstung |  | entfällt (in 30 enthalten) |  |  | entfällt (in 30 enthalten) |
| 39 | Wannabe packs - Gangsta Knight | Diamond | 2 Ausrüstung | 750 |  |  |  | entfällt (in 31 enthalten) |
| 40 | Wannabe packs - Gothic Knight | Diamond | 2 Ausrüstung |  | entfällt (in 32 enthalten) |  |  | entfällt (in 32 enthalten) |
| 41 | Wannabe packs - Geek Runaway | Diamond | 2 Ausrüstung |  | entfällt (in 29 enthalten) |  |  | entfällt (in 29 enthalten) |
| 42 | Wannabe packs - Cute Runaway | Diamond | 2 Ausrüstung |  | entfällt (in 30 enthalten) |  |  | entfällt (in 30 enthalten) |
| 43 | Wannabe packs - Gangsta Runaway | Diamond | 2 Ausrüstung | 750 |  |  |  | entfällt (in 31 enthalten) |
| 44 | Wannabe packs - Gothic Runaway | Diamond | 2 Ausrüstung |  | entfällt (in 32 enthalten) |  |  | entfällt (in 32 enthalten) |
| 45 | Wannabe packs - Geek + Cute + Gangsta + Gothic | Diamond | 8 Ausrüstung | 33000 |  |  |  | groß 1500 |
| 46 | Watch_Dog Theme | Diamond | 1 Themes |  | entfällt (in 47 enthalten) |  |  | entfällt (in 47 enthalten) |
| 47 | Watch_Dogs Pack | Diamond | 12 Ausrüstung, 1 Themes, 1 Inventar-Tab | 3245 | 1 |  | 1 | Premium 2500 |
| 48 | Magic find boost X1 | Diamond | 1 Ausrüstung | 0 | 1 Ausrüstung |  | 1 | entfällt (in 2 enthalten) |
| 49 | SteamUnderwearPack | Diamond | 4 Ausrüstung |  | klein 300 |  |  | klein 300 |
| 50 | SteamAmulet | Diamond | 1 Ausrüstung |  | groß 1500 |  |  | groß 1500 |
| 51 | SteamPet | Diamond | 1 Ausrüstung |  | mittel 800 |  |  | mittel 800 |
| 52 | Diamond - Defender Pack - Summer Sale | Diamond | 2 Ausrüstung, 1 Themes, 1 Monster | 850 | 2 |  | 2 | entfällt (in 12 enthalten) |
| 53 | Diamond - Attacker Pack - Summer Sale | Diamond | 3 Ausrüstung, 1 Helden-Skin | 0 | 4 |  | 4 | entfällt (in 13 enthalten) |
| 54 | Diamond - Supply + Attack + Defend pack - Summer Sale | Diamond | 4 Ausrüstung, 1 Themes, 1 Monster, 1 Helden-Skin | 850 | 4 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost | 500 | 5 | entfällt (in 14 enthalten) |
| 55 | Diamond - Ultimate Pack - Summer Sale | Diamond | 9 Ausrüstung, 1 Themes, 1 Monster, 1 Helden-Skin, 1 Inventar-Tab, Emotes | 1765 | 4 Ausrüstung, 1 Creatures, 1 Helden-Skin/Boost | 500 | 5 | entfällt (in 14 enthalten) |
| 56 | Limited Edition Pack | Diamond | 153 Monster, 110 Fallen | 33880 | 2 |  | 2 | entfällt (Gegenwert zu hoch; entschieden) |
| 57 | Sick Creature Pack | Diamond | 67 Monster, 29 Fallen | 3007 | 40 |  | 40 | entfällt (Sick Creatures wurden rausgepatcht; entschieden) |
| 58 | Attacker Pack Oct2014 - Marleyboned Mage | Diamond | 4 Ausrüstung, 1 Inventar-Tab | 1149 | 2 |  | 2 | entfällt (in 62 enthalten) |
| 59 | Attacker Pack Oct2014 - Spider Pirate Archer | Diamond | 4 Ausrüstung, 1 Inventar-Tab | 1000 | 2 |  | 2 | entfällt (in 62 enthalten) |
| 60 | Attacker Pack Oct2014 - Chewing Gum Runaway | Diamond | 4 Ausrüstung, 1 Inventar-Tab | 900 | 2 |  | 2 | entfällt (in 62 enthalten) |
| 61 | Attacker Pack Oct2014 - Phoenix Dragon Knight | Diamond | 4 Ausrüstung, 1 Inventar-Tab | 1240 | 2 |  | 2 | entfällt (in 62 enthalten) |
| 62 | Attacker Pack Oct2014 - Complete with 4 heroes | Diamond | 10 Ausrüstung, 4 Inventar-Tab | 4289 | 2 |  | 2 | entfällt (in 66 enthalten) |
| 63 | Defender Pack Oct2014 - Bronze | Diamond | 1 Themes, 60 Monster, 61 Fallen, 19 Deko, Material | 1619 |  |  |  | entfällt (in 64 enthalten) |
| 64 | Defender Pack Oct2014 - Silver | Diamond | 2 Themes, 81 Monster, 71 Fallen, 40 Deko, Material | 3849 |  |  |  | entfällt (in 65 enthalten) |
| 65 | Defender Pack Oct2014 - Gold | Diamond | 3 Themes, 95 Monster, 77 Fallen, 63 Deko, Material | 6299 |  |  |  | entfällt (in 66 enthalten) |
| 66 | The Big Pack - Oct2014 | Diamond | 10 Ausrüstung, 3 Themes, 95 Monster, 77 Fallen, 63 Deko, 4 Inventar-Tab, Material | 10588 | 2 |  | 2 | 4000 (Wert ~10.500; entschieden) |
| 67 | Halloween Pack Oct2014 | Diamond | 1 Themes, 4 Monster, 20 Deko | 1899 |  |  |  | groß 1500, nur während Halloween (entschieden) |
| 68 | Magical Golden Pony | – | 55 Ausrüstung, 24 Themes, 724 Monster, 109 Fallen, 20 Deko, 4 Helden-Skin, 7 Inventar-Tab, Material, 2 Shop-Artikel | 138839 | 13 Ausrüstung, 304 Creatures, 66 Traps, 6 Theme, 2 ShopSku, 4 Helden-Skin/Boost, 1 Material |  | 53 | entfällt (intern, entschieden) |
| 69 | MoM Special pack | – | Material, 1 Shop-Artikel | 0 | 1 ShopSku, 1 Material |  |  | klein 300 |
| 71 | SpecialPackBundle | – | 1 Ausrüstung, 15 Monster, 5 Fallen, 55 Deko | 3494 |  |  |  | groß 1500 |
| 72 | Infinite Pack Bundle | – | 7 Inventar-Tab, 75 Shop-Artikel, Artikel je Burg-Level | 1400 |  |  |  | Sonderstufe 4000 (s. u.) |
| 73 | XP Boost Pack | – | 1 Ausrüstung | 0 | 1 Ausrüstung |  | 1 | entfällt (in 11 enthalten) |
| 74 | QC Team Only - All Beta Rewards | – | 9 Ausrüstung, 1 Themes, 1 Fallen | 1500 | 9 |  | 9 | Premium 2500 (Beta-QC-Belohnungen, entschieden) |
| 75 | Look Ma, I'm the best! | – | 52 Deko | 0 | 52 |  | 52 | Premium 2500 |
