# Bling-Wirtschaft (umgesetzt, Schalter im Webtool: Economy)

Stand 17.10.2026. Ziel: Blings (PremiumCash) werden eine **erspielte** Währung.
Echtgeld geht nicht (Rechte bei Ubisoft), Gratis-Blings (heutiger Test-Shop
`server/bling_shop.py`) entwerten das Spiel. Shop und Preise im Client bleiben
grundsätzlich, geändert wird vor allem, **woher** Blings kommen.

## Leitlinien

- Blings nur für Leistung und Fortschritt, **nicht für Anwesenheit**: keine
  Login-Boni, keine Serien (Streaks). Wer pausiert, holt es mit derselben
  Spielzeit auf.
- Maßvolles FOMO ist in Ordnung (Seasonal Events, Liga-Saison, Wettbewerbe),
  solange die Belohnungen klein sind und Aussetzen nicht weh tut.
- Helden bleiben hinter Blings (Langzeitziel); die Trial-Promos
  (`server/free_trials.py`, Rabatt über Level-Ziele) bleiben.
- Der Bling-Shop bleibt, verkauft aber statt Blings die früheren
  Echtgeld-Packs (Kosmetik usw.) **gegen Blings**, auch ältere.
- Blings vergibt nur der Server; Obergrenze je Account und Woche gegen
  Zweitaccount-Farmen.

## Bestandsaufnahme

### Ausgaben (ShopSettings/ShopSkuBaseSettings.json)

5095 SKUs, davon gut 2000 mit Bling-Preis (`CurrencyType` 1). Aktive SKUs:

| Art | Anzahl | Blings (min / typisch / max) | Einordnung |
|---|---|---|---|
| Hero | 14 | 798 / 1200 / 3012 | Langzeitziel |
| CastleTheme | 18 | 99 / 850 / 1500 | Kosmetik |
| Decoration | 60 | 15 / 90 / 10000 | Kosmetik |
| HeroUpgrade | 116 | 100 / 500 / 999 | Fortschritt |
| HeroEquipmentItem | 748 | 0 / 80 / 19998 | Fortschritt (vieles auch für Gold) |
| Building, Creature, Trap, …Upgrade | ~640 | meist 50–200 | Abkürzung |
| Consumable | 65 | 5 / 60 / 700 | Abkürzung |
| ForgeCrafted/-Reforged | je 120 | 15 / 60 / 120 | Abkürzung |
| InventoryTabs, Room, ShowMoreCastle | 47 | 5–200 | Komfort |

Dazu Zeit-Skips mit Blings (`GeneralSettings/TimeSettings.json`).

Helden: Der Shop zeigt alle Helden für **950 Blings** (Promo-SKUs „PM“),
keine Lebenskraft (im Spiel bestätigt). Die übrigen Helden-SKUs (1000
LifeForce, Daily Deal 798/1200, Featured 3012) stehen in den Daten, werden
aber nicht angeboten.

### Quellen im Original (ohne Echtgeld)

| Quelle | Menge | Datei |
|---|---|---|
| Ziele (Objectives) | einmalig 200 + 7 × 50 | ObjectiveSettings.json |
| Liga-Saisonende, vordere Plätze | 5–30 | SeasonalCompetitionSettings.json (`LeaderClosingPeriodRewards`) |
| Liga halten | 1–4 je Saison | dto. (`LeagueMaintainReward`) |
| Wettbewerbe / Challenges | 25 / 10 / 5 für Platz 1–3 | UbisoftCompetitionSettings.json, ChallengeSettings.json |
| Bling-Mine (Gebäude 16) | 1/h, Speicher 25, plünderbar | Buildings/000016 - BlingMine |
| Validierung delegierter Burgen | 3 | AttackerRewardSettings.json |
| Achievements (36) | **keine Blings** | AchievementSettings.json |

Unser Server zahlt alle diese Quellen heute schon aus (objectives.py,
leagues.py, competitions.py, castles.py für die Validierung, Mine über
`HarvestMineBuildingCommand` mit den Originalwerten 1/h, Speicher 25).
Produktion und Speicher der Mine stehen in den Gebäudedaten, die auch der
Client anzeigt: Änderung per Daten-Patch (DataBin, über den Patcher
umkehrbar).

Ohne Geld kamen im Original also nur wenige hundert Blings zusammen; ein Held
(~1000) war praktisch unerreichbar. Die Bling-Mine ist mit kleinem Speicher
genau das Abholen-nach-Zeitplan-Muster, das wir vermeiden wollen.

### Special Packs (GeneralSettings/SpecialPackSettings.json)

75 Packs: 56 „Diamond“, 11 „DoubleO“/„DoubleOV2“, 8 einzelne (u. a. Infinite
Pack 72, Halloween 67). Inhalte: Ausrüstung (60 Packs), früher Heldenzugang
(39), Monster (24), Themes (19), Helden-Boosts (17), Inventar-Tabs (22),
Fallen, Dekorationen, Emotes, Materialien. **21 Packs enthalten selbst
Blings** (z. B. „Chunk of Change“ 1500), die beim Verkauf gegen Blings
herausfallen müssen.

## Entwurf (Zahlen zum Diskutieren)

Bezugsgröße ist **aktive Spielzeit**, nicht Kalenderzeit. Annahme
„normaler“ Spieler: etwa 4 Stunden pro Woche.

| Ziel | Zielzeit | ≈ Spielstunden |
|---|---|---|
| erstes Kosmetik-Teil (~100) | erste Tage | 2–3 h |
| zweiter Held (950) | 2–3 Wochen | ~10 h |
| jeder weitere Held | 1–2 Monate | 20–30 h |
| großes Pack | einige Wochen | 15–25 h |
| alles Premium | viele Monate | 200+ h |

Daraus zwei Einnahmeströme:

1. **Einmaliger Topf (~3000 Blings)**, verteilt auf Achievements (~1500) und
   Ziele (1550). Meilensteine entfallen (keine Client-UI). Trägt den Anfang,
   damit der zweite Held schnell kommt.
2. **Laufend ~30–40 Blings je Spielstunde**: seltene Bling-Beute beim Plündern
   (größter Anteil), dazu Liga und Wettbewerbe als kleiner Zuschlag
   (Original-Werte etwa verdoppelt), Seasonal Events mit kleinen Preisen.
   Bling-Mine siehe unten.

**Pack-Preise:** aus dem Inhalt abgeleitet, nicht aus dem alten Euro-Preis:
Summe der Bling-Preise der Einzelteile mit Paket-Rabatt, ohne enthaltene
Blings; Packs, die vor allem Abkürzungen enthalten, mit Aufschlag oder gar
nicht. Ohne Wert (entschieden 17.10.2026): **früher Heldenzugang** (Relikt der
Entwicklungszeit) fällt weg; **Emotes** bleiben drin, zählen aber nicht zum
Preis (praktisch Einzelspieler, sieht höchstens jemand im Replay). Damit
bleibt von 4 Packs nichts übrig, sie entfallen: 16 „Runaway Only“, 17 „Mage
Only“ (nur Heldenzugang), 19 „PC Gamer Bling Pack“, 70 „Steam Big Bling
Pack“ (nur Blings).

### Bling-Mine

Heute gibt unser Server beim Plündern den **ganzen Füllstand** her
(`loot.stealable_buildings`); Gold-/Lebenskraft-Minen nur die Produktion der
letzten Stunde (`mine_stealable`, `MinePeriodStealableAmountInSeconds`). Mit
großem Speicher wäre ein Wenigspieler sonst ein Jackpot und müsste doch
täglich abholen. Daher:

- Plünderbar höchstens eine Stunde Produktion (mindestens
  `PremiumCashMineLossAmount` = 1), der Rest bleibt dem Besitzer.
- Zerstören setzt nur den Ertrag dieses Angriffs auf null, nicht den Inhalt.
- Produktion 1/h, Speicher 42 (voll nach 42 h): belohnt bewusst Spieler, die
  alle 1–2 Tage abholen (~150–168 je Woche); wöchentlich nur 42 (entschieden
  09.11.2026).
- Preis 500 statt 999 Blings (`Mine.Price`, Daten-Patch der SKU 15522 in
  ShopSkuBaseSettings, Server bucht über `balance.sku_price`): bei Abholen
  alle 2–3 Tage nach ~3–5 Wochen verdient, für einen Mittelspieler etwa 3
  Wochen Einkommen; mit 999 waren es bis zu 24 Wochen.
- Bis zu drei Bling- und drei Material-Minen je Burg (BuildingInstanceRequirements,
  ab Burgherz 2), wie im Original: Shop-SKUs 15522 (Bling-Mine, 500 Blings, Original 999) und
  15699 (Material-Mine, 500 Blings) mit Kontingent 3 (`special_packs.SHOP_QUOTAS`);
  Pack-Minen (Infinite Pack, Material-O-Matic) zählen zur selben Grenze, die
  der Server beim Bauen prüft.

### Hochrechnung

Annahmen: Beute 25 Blings je Spielstunde; einmaliger Topf 2500 über die
ersten ~60 Spielstunden (~42/h, bis er leer ist); Liga/Wettbewerbe 5–60 je
Woche; Mine 42 je Woche.

| Spieler | Spielzeit/Woche | Blings/Woche anfangs | danach | 2. Held (950) | weitere Helden |
|---|---|---|---|---|---|
| Wenig | 1 h | ~115 | ~72 | ~8 Wochen | ~13 Wochen |
| Mittel | 4 h | ~330 (15 Wochen) | ~160 | ~3 Wochen | ~6 Wochen |
| Viel | 15 h | ~1090 (4 Wochen) | ~470 | < 1 Woche | ~2 Wochen |
| Extrem | 40 h | Topf nach ~1,5 Wochen leer | ~700 (Grenze) | < 1 Woche | ~1,5 Wochen |

Alles Premium (Helden, 18 Themes, Dekorationen, Packs) grob 30.000–40.000:
Mittelspieler Jahre, Vielspieler ~1,5 Jahre.

### Obergrenze

**Wochengrenze statt Tagesgrenze** (eine Tagesgrenze belohnt tägliches
Spielen): höchstens 600 Blings aus Beute in den letzten 7 Tagen. Trifft nur
Extremspieler und Farm-Accounts. Einmaliger Topf und Liga sind nicht
begrenzt (endlich bzw. selten).

### Abkürzungen

In Spielzeit (25 Blings/h): Zeit-Skip 5 min / 1 h / 24 h = 5 / 50 / 850
Blings ≈ 12 min / 2 h / 34 h; Monster oder Falle direkt 50–200 ≈ 2–8 h;
Materialpaket 50–200 ≈ 2–8 h; Inventar-Tab 200 ≈ 8 h; Validierung
delegieren 10 ≈ 25 min. Bei erspielten Blings begrenzen sich die
Originalpreise selbst: **nichts sperren, nichts verteuern**, kein Preis-Patch
nötig. Gold/Lebenskraft gegen Blings gibt es in den Daten nicht.

### Pack-Auswahl (entschieden 17.10.2026)

Je Pack ein fester Preis statt Summe der Einzelteile; Liste mit Inhalt und
Entscheidung in `docs/analysis/special-packs.md`. **23 Packs im Angebot**,
Preise 300–4000 (Spitze: 66 The Big Pack und 72 Infinite Pack je 4000);
Halloween (67) nur während des Events; 74 Beta-QC-Belohnungen als
Premium 2500. Entfallen: interne Packs (21 alle Pets, 68 Golden Pony),
Duplikate und Promo-Kopien, 56 Limited Edition (Gegenwert zu hoch),
57 Sick Creatures (bleiben rausgepatcht). Kann bis zum Livegang noch
nachjustiert werden.

## Umsetzung

- **Stellschrauben** (`server/balance.py`, `state/<Profil>/balance.json`):
  Schalter `Enabled` (Vorgabe aus) und die Werte, im Webtool unter
  **Economy** (admin.Get/SetBalance, Grenzen geprüft). Bisher: Bling-Mine.
- **Client-Werte** (im Webtool mit „client“ markiert) kommen per Patcher in
  `settings.bin`: DataBin-Version `…​.B<CRC>`; jeder Stand bleibt in
  `History`, damit Deltas auch von älteren Ständen gehen. settings.bin ist
  immer im DataBin-Paket (Original, wenn aus), damit Ausschalten zurück zum
  Original führt. Eigener LZO-Packer (settings_archive.lzo_compress): ~4 MB
  Delta, Bau ~17 s beim ersten Abruf.
- **Bling-Mine:** castles.mine_rank liefert bei Enabled ProductionPeriod/
  Capacity aus balance; loot.stealable_buildings begrenzt die Beute auf
  StealHours Produktion (mindestens 1). Eine neu gebaute Bling-Mine startet
  leer wie im Original (MineManager.AddMineStatus); Ernten meldet
  EntityHarvestType PremiumCashMine (nur im finalen Client).
- **Achievements:** Betrag je Achievement im Webtool (Vorgabe Punkte × 2,
  zusammen ~1500, Art „UI“). Ausgezahlt einmal je Achievement zum dann
  gültigen Betrag, auch rückwirkend für schon erreichte, sobald die
  Bling-Wirtschaft an ist (`AchievementBlingsPaid` im Account, Kontobuch
  Quelle `achievements`). Anzeige: UI-Patch 9 (ui_patches.py) setzt im
  Popup unter die Punkte „+N“ mit Bling-Symbol; die Beträge stecken im
  Helfer `achievementBlings` (hyperquest.extensions.js), daher ändert jede
  Änderung die GameUI-Version. Ältere GameUI-Stände bekommen alle Dateien
  neu (vorher: gar kein Patch mehr).
- **Ziele (Objectives):** Bling-Betrag je Ziel mit Bling-Belohnung (8 Stück,
  Art „client“): Vorgabe 200 für Snottingham und die sechs Bosse, 150 für
  Heist Part 2 (Original 200 + 7 × 50 = 550, jetzt 1550). Der Client zeigt
  sie selbst an (ObjectiveSettings in settings.bin, mit der Mine neu
  gepackt); objectives.rewards zahlt denselben Betrag. Schon abgeschlossene
  Ziele bekommen nichts nach.
- **Bling-Beute:** Bei echten Angriffen (ohne Übung, Tutorial, Wettbewerb)
  trägt mit `Loot.Chance` (Vorgabe 40 %) eine zufällige Kreatur
  `Loot.Amount` Blings (Vorgabe 10; DefenseIngredientLoot.PremiumCash).
  Gutgeschrieben beim Töten (KilledCreatureIds; eine eigene Id-Liste für
  Blings meldet der Client nicht), im Bericht unter TotalPremiumCash.
  Grenze `Loot.WeeklyCap` (600) im gleitenden 7-Tage-Fenster
  (`BlingLootLog` im Account); das Restbudget deckelt schon den Drop.
- **Liga und Wettbewerbe:** je ein Prozentfaktor auf alle Bling-Beträge
  (Vorgabe 200 %, Art „client“): SeasonalCompetitionSettings bzw.
  UbisoftCompetitionSettings in settings.bin, der Server rechnet gleich
  (balance.scale_reward in leagues.settle und competitions.reward).
- **Bling-Shop:** bei Enabled zeigt `/blings` (Knopf „Purchase blings“) die
  Packs als Karten mit Inhalt und Preis (Economy-Abschnitt Shop, 0 = nicht im
  Angebot; 67 Halloween nur im Event). Kauf: AccountState.buy_special_pack
  bucht ab und schaltet frei (Kontobuch `bling-shop`); Ausrüstung,
  Verbrauchsgüter und Material kommen ins Inventar (ohne Platz kostenlos in
  den Rückkauf) und werden als Notifications gemeldet. Die kostenlosen
  Test-Buchungen gibt es nur noch bei ausgeschalteter Wirtschaft.
  Heldenzugang: bei Enabled fehlt EarlyHeroAccess in den Packs, im Server
  (special_packs.pack) und in settings.bin (balance.DATA_REVISION 2), damit
  Helden nur für Blings kommen; schon angelegte Helden bleiben.

## Weg zurück

1. **Schalter auf dem Server** (wie der Wartungsmodus), zunächst aus; aus =
   heutige Regeln.
2. **Preisänderungen im Client** nur über Patcher-Pakete (Deltas auf die
   Steam-Dateien); Paket entfernen = Originalpreise beim nächsten Start.
3. **Kontobuch:** jede Bling-Gutschrift und jeder Pack-Kauf mit Quelle, zur
   Auswertung der Balance und für gezielte Korrekturen.
   **Umgesetzt:** `state/<Profil>/<AccountId>.blings.jsonl`, eine Zeile je
   Änderung {Time, Delta, Balance, Source}; Source = Anfrage
   (`Dienst/Methode (Spieler)`), bei Commands mit `cmd:<Name>`, beim
   Webtool `admin:<Methode>` (AccountState._book beim Speichern, Quelle je
   Thread in account_state.SOURCE).
4. **Sicherung des Spielstands** beim Umschalten (nur Notfall).

**Regel beim Zurückschalten:** Spieler behalten alles Erspielte, auch Blings.
Korrigiert wird nur nach vorn (Einnahmen, Preise). Weggenommen wird nur bei
Missbrauch (Bug, Exploit, Zweitaccounts), gezielt über das Kontobuch. Muss
doch einmal eingegriffen werden: Umtausch zu einem angekündigten Kurs oder
Einfrieren, nie ersatzlos streichen.

## Offene Fragen

- Achievements: Client kennt keine Belohnung (nur Titel, Beschreibung,
  Punkte). Entschieden: hardcoden, Beträge je Achievement-Id im Server und
  per UI-Patch als Zeile „+N Blings“ im Popup
  (`template-achievement-completed-popup`).
- Bling-Beute: der Bericht zeigt sie (`TotalPremiumCash`), einen sichtbaren
  Drop im Kampf nicht; so belassen.
