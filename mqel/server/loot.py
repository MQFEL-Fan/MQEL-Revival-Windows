"""Beute für PVE-Angriffe aus den GameplaySettings des Clients.

Belegt aus den Daten:
- Nur Kreaturen lassen in PVE etwas fallen (Traps: PVEDroppableLootTypeMask 0,
  AttackerRewardSettings.AllowDecorationLoot false).
- XP je Kreatur = ConstructionPoints * XpLootBaseCpMultiplier(Burg-Level)
  * XpLootPerLevelCpMultiplier * XpModifierTable(Levelabstand).
- Heilkugel-Fragmente = LootableSpec.HealthOrbFragmentsLootBase
  * HealthOrbFragmentsModifierTable(Levelabstand).
- Schatzkammer = TreasureRoom{Min,Max}{Gold,LifeForce}Ratio der Gesamtbeute.
- Helden-Level aus HeroSettings.XpPerLevel (kumulative Schwellen).

Gold/Lebenskraft je Kreatur = ConstructionPoints * Total{Gold,LifeForce}Modifier
* (1 + LEVEL_STEP * (Burg-Level - 1)). Geeicht an Original-Mitschnitten
(MQELOffline_cpp, AttackService): Tutorialburg 2 (Level 1, 30.6 CP) brachte
KillsGold 33 = KillsLifeForce 33; Burg 101 (Level 3, 79 CP) KillsGold 133,
KillsLifeForce 119, Schatzkammer je 46. Die Formel selbst ist nicht bekannt.
"""

import balance
import functools
import glob
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, "client", "GameData", "Data", "GameplaySettings")

LEVEL_STEP = 0.25

# Buildings/<Id>: Lager (Truhen der Schatzkammer) und Minen -> Wallet-Feld
STORAGES = {3: "InGameCoin", 4: "LifeForce"}          # GoldStorage, LifeForceStorage
MINES = {5: "InGameCoin", 6: "LifeForce", 16: "PremiumCash"}  # Gold/LifeForce/Bling
MATERIAL_MINE = 17  # Material-O-Matic (CraftingMaterialMine)


def _load(*parts):
    with open(os.path.join(SETTINGS, *parts), encoding="utf-8") as f:
        return json.load(f)


@functools.lru_cache(maxsize=None)
def rewards():
    return _load("GeneralSettings", "AttackerRewardSettings.json")


@functools.lru_cache(maxsize=None)
def xp_per_level():
    return _load("GeneralSettings", "HeroSettings.json")["XpPerLevel"]


@functools.lru_cache(maxsize=None)
def _creature_spec(spec_id):
    """ConstructionPoints, HealthOrbFragmentsLootBase, Rank einer Kreatur."""
    path = glob.glob(os.path.join(SETTINGS, "Creatures",
                                  "%06d - *" % spec_id, "Gameplay.json"))
    spec = {"cp": 0, "orbs": 0, "rank": "Grunt"}
    if path:
        with open(path[0], encoding="utf-8") as f:
            for comp in json.load(f):
                t = comp["$type"].split(",")[0].rsplit(".", 1)[-1]
                if t == "DynamicCpZoneMemberSpec":
                    spec["cp"] = comp.get("ConstructionPoints", 0)
                elif t == "LootableSpec":
                    spec["orbs"] = comp.get("HealthOrbFragmentsLootBase", 0)
                elif t == "CreatureSpec":
                    spec["rank"] = comp.get("Rank", "Grunt")
    return spec


def creature(spec_id):
    """(ConstructionPoints, HealthOrbFragmentsLootBase) einer Kreatur."""
    s = _creature_spec(spec_id)
    return s["cp"], s["orbs"]


def creature_rank(spec_id):
    """Grunt/Captain/Elite/Boss (CreatureSpec.Rank, Default Grunt)."""
    return _creature_spec(spec_id)["rank"]


def level_modifier(table, hero_level, castle_level):
    """Wert aus einer {Minus5Levels..Plus6Levels}-Tabelle.

    "PlusN" = Held N Level über der Burg (weniger Ertrag), "MinusN" darunter.
    """
    diff = hero_level - castle_level
    if diff == 0:
        return table["SameLevel"]
    if diff > 0:
        n = min(diff, 6)
        return table["Plus1Level" if n == 1 else "Plus%dLevels" % n]
    n = min(-diff, 5)
    return table["Minus1Level" if n == 1 else "Minus%dLevels" % n]


def _base_cp_multiplier(level):
    for row in rewards()["XpLootBaseCpMultiplierTable"]:
        if row["MinLevel"] <= level <= row["MaxLevel"]:
            return row["XpLootBaseCpMultiplier"]
    return 0


def creature_loot(castle, hero_level, rare_ratio=0.0):
    """{Entity-Id: {Gold, LifeForce, Xp, HealthOrbFragments}} der Burg.
    rare_ratio: Loot-O-Meter-Bonus auf Gold und Lebenskraft
    (castles.rare_ratio)."""
    r = rewards()
    level = castle["Level"]
    xp_mod = level_modifier(r["XpModifierTable"], hero_level, level)
    orb_mod = level_modifier(r["HealthOrbFragmentsModifierTable"],
                             hero_level, level)
    xp_per_cp = (_base_cp_multiplier(level) * r["XpLootPerLevelCpMultiplier"]
                 * xp_mod)
    level_factor = (1 + LEVEL_STEP * (level - 1)) * (1 + rare_ratio)
    out = {}
    for room in castle.get("Rooms") or []:
        for c in room.get("Creatures") or []:
            cp, orbs = creature(c["SpecContainerId"])
            out[c["Id"]] = {
                "Gold": round(cp * level_factor * r["TotalGoldModifier"]),
                "LifeForce": round(cp * level_factor
                                   * r["TotalLifeForceModifier"]),
                "Xp": round(cp * xp_per_cp),
                "HealthOrbFragments": round(orbs * orb_mod),
            }
    return out


@functools.lru_cache(maxsize=None)
def attack_settings():
    return _load("GeneralSettings", "AttackSettings.json")


def loss_ponderation(hero_level, castle_level, table="LossPonderationTable"):
    """Zeile der AttackSettings.LossPonderationTable bzw.
    MineLossPonderationTable (Verlustanteil und Schild des Verteidigers) wie
    AttackSettingsExtensions.GetLossPonderation/GetMineLossPonderation im
    Original-Server: Abstand = Heldenlevel des Angreifers - Burglevel des
    Verteidigers, Zeile mit genau diesem AttackerDefenderLevelDiff (ohne
    Angabe 0), darunter die erste, darüber die letzte."""
    rows = sorted(attack_settings()[table], key=lambda r: r.get("AttackerDefenderLevelDiff", 0))
    diff = hero_level - castle_level
    exact = next((r for r in rows if r.get("AttackerDefenderLevelDiff", 0) == diff), None)
    if exact:
        return exact
    return rows[0] if diff < rows[0].get("AttackerDefenderLevelDiff", 0) else rows[-1]


def mine_stealable(status, castle_level, hero_level):
    """(Beute, geschützt) einer Mine eines echten Spielers wie
    MineManager.CalculateMineStealableAmount/-MaxStealableAmount im
    Original: Minenschild MineShieldedAmoutDrop, leer (oder Rang 0)
    MineEmptyAmountDrop – beides kostet den Besitzer nichts (geschützt) –,
    sonst höchstens der Anteil nach MineLossPonderationTable an der
    Produktion von MinePeriodStealableAmountInSeconds (Vorgabe 1 h,
    _HourlyProduction aus castles.player_castle), höchstens der Füllstand.
    Zerstörte Minen bleiben plünderbar."""
    s = attack_settings()
    if status.get("_Shielded"):
        return s["MineShieldedAmoutDrop"], True
    production = status.get("_HourlyProduction", 0)
    if not production or not status.get("CumulatedAmount"):
        return s["MineEmptyAmountDrop"], True
    share = loss_ponderation(hero_level, castle_level,
                             "MineLossPonderationTable").get("AttackCastlePercentageLoss", 0)
    # wie im Original: Math.Floor(Math.Round(Anteil * Produktion, 1) + 0.5), mindestens 1
    maximum = max(1, int(round(share * production, 1) + 0.5))
    return min(maximum, status["CumulatedAmount"]), False


def treasure_room(total_gold, total_lifeforce, castle=None, hero_level=1):
    """(Gold, Lebenskraft) der Schatzkammer. Burg eines echten Spielers
    (_Wallet): ein Anteil seines Wallets nach loss_ponderation, den er
    beim Plündern verliert (LootManager.CalculateTreasureRoomStealableAmount
    im Original-Server); sonst generiert als Anteil der Kreaturen-Beute."""
    wallet = (castle or {}).get("_Wallet")
    if wallet is not None:
        share = loss_ponderation(hero_level, castle["Level"]).get("AttackCastlePercentageLoss", 0)
        return int(wallet["InGameCoin"] * share), int(wallet["LifeForce"] * share)
    r = rewards()
    return (round(total_gold * r["TreasureRoomMaxGoldRatio"]),
            round(total_lifeforce * r["TreasureRoomMaxLifeForceRatio"]))


def level_for_xp(xp):
    """Helden-Level zu kumulativer XP (Schwellen aus HeroSettings)."""
    table = xp_per_level()
    level = 1
    for i, need in enumerate(table):
        if xp >= need:
            level = i + 1
    return level


def stealable_buildings(castle, total_gold, total_lifeforce, hero_level=1):
    """{Building-Id: (Wallet-Feld, Betrag, ist_Lager, geschützt)} der
    plünderbaren Gebäude. Lager teilen sich die Schatzkammer-Beute
    (treasure_room). Gold-/Lebenskraft-Minen echter Spieler (_MineStatuses)
    nach mine_stealable; Bling-Minen geben ihren Füllstand her, Minen von
    Ubisoft-Burgen UbisoftCastleMineAmountDrop. geschützt: der Besitzer
    verliert nichts (Minenschild, leere Mine)."""
    statuses = castle.get("_MineStatuses")
    tr_gold, tr_lf = treasure_room(total_gold, total_lifeforce, castle, hero_level)
    storage_amount = {"InGameCoin": tr_gold, "LifeForce": tr_lf}
    # Ubisoft-Burgen: je Gold-/Lebenskraft-Mine pauschal
    # UbisoftCastleMineAmountDrop (nur finale AttackSettings; die DLL von 2014
    # kennt keine Minenbeute bei Ubisoft-Burgen, der Client liest den Wert nicht)
    drop = attack_settings()["UbisoftCastleMineAmountDrop"]
    mine_amount = {"InGameCoin": drop, "LifeForce": drop, "PremiumCash": 0}
    out = {}
    for room in castle.get("Rooms") or []:
        for b in room.get("Buildings") or []:
            spec = b["SpecContainerId"]
            if spec in STORAGES:
                field = STORAGES[spec]
                out[b["Id"]] = (field, storage_amount[field], True, False)
            elif spec in MINES:
                field = MINES[spec]
                if statuses is None:
                    out[b["Id"]] = (field, mine_amount[field], False, False)
                    continue
                s = statuses.get(str(b["Id"])) or {}
                if field == "PremiumCash":
                    amount = (0 if s.get("IsDestroyed") or not s.get("IsActive", True)
                              else s.get("CumulatedAmount", 0))
                    if balance.enabled():  # nur ein paar Stunden Produktion
                        steal = balance.get("Mine", "StealHours")
                        steal = steal and max(1, steal // balance.get("Mine", "ProductionHours"))
                        amount = min(amount, steal)
                    out[b["Id"]] = (field, amount, False, False)
                else:
                    amount, protected = mine_stealable(s, castle["Level"], hero_level)
                    out[b["Id"]] = (field, amount, False, protected)
    return out


def stealable_materials(castle):
    """{Building-Id: (Zutaten, geschützt)} der Material-O-Matics
    (AttackSettings.CraftingMaterialMine*ItemDropCount): volles Paket gibt
    so viele seiner Zutaten her, die der Besitzer verliert; leer oder mit
    Minenschild ebenso viele Basic-Zutaten, die ihn nichts kosten. Burgen
    ohne Minenstände (keine Spielerburg) wie leer."""
    import item_drops  # item_drops importiert loot
    s = attack_settings()
    statuses = castle.get("_MineStatuses") or {}
    out = {}
    for room in castle.get("Rooms") or []:
        for b in room.get("Buildings") or []:
            if b["SpecContainerId"] != MATERIAL_MINE:
                continue
            st = statuses.get(str(b["Id"])) or {}
            pack = st.get("CumulatedHeroItems") or []
            if pack and not st.get("_Shielded"):
                n = min(s["CraftingMaterialMineItemDropCount"], len(pack))
                out[b["Id"]] = ([dict(i) for i in random.sample(pack, n)], False)
            else:
                out[b["Id"]] = ([item_drops.material_item("Basic") for _ in
                                 range(s["CraftingMaterialMineEmptyItemDropCount"])], True)
    return out


# --- Seltene Bling-Beute (balance "Loot") -------------------------------------

BLING_LOOT = "BlingLootLog"  # Account: [[Unix-Zeit, Blings], ...]
BLING_LOOT_WINDOW = 7 * 86400


def bling_loot_left(account, now):
    """Blings, die in den letzten 7 Tagen aus Beute noch gehen."""
    recent = sum(n for t, n in account.get(BLING_LOOT) or []
                 if t > now - BLING_LOOT_WINDOW)
    return max(0, balance.get("Loot", "WeeklyCap") - recent)


def add_bling_drop(creature_loot, account, now, rng=random):
    """Legt mit Loot.Chance die Blings auf eine zufällige Kreatur
    (DefenseIngredientLoot.PremiumCash); gedeckelt auf das Restbudget."""
    if not balance.enabled() or not creature_loot:
        return
    if rng.random() * 100 >= balance.get("Loot", "Chance"):
        return
    amount = min(balance.get("Loot", "Amount"), bling_loot_left(account, now))
    if amount > 0:
        creature_loot[rng.choice(sorted(creature_loot))]["PremiumCash"] = amount


def record_bling_loot(account, amount, now):
    """Beute-Blings ins gleitende Fenster eintragen (alte fallen weg)."""
    log = [e for e in account.get(BLING_LOOT) or [] if e[0] > now - BLING_LOOT_WINDOW]
    if amount:
        log.append([int(now), amount])
    account[BLING_LOOT] = log


# --- Decoration drops (2026-11-22, docs/88-decoration-loot.md) -----------------
# The client spawns AttackInfo.DecorationLoot when a decoration is destroyed
# (AllowDecorationLoot, switched on by level60.attacker_rewards) and reports
# what was picked up (LootedGold/LifeForce/HeroItemDecorationIds); blings
# count when the decoration is destroyed (DestroyedDecorationIds).

DECO_CHANCE = 0.75               # chance per decoration (not crystals) for a small gold/life force drop
DECO_AMOUNT = (0.20, 0.50)       # of an average creature's gold/life force in this castle (always less)
DECO_ITEM_CHANCE = 0.004         # rare: a basic crafting material instead (~1 in 250)
BLING_CRYSTALS = {237, 238}      # DEC_000_Bling_Crystal_01/02 (green)
CRYSTAL_BLING_CHANCE = 0.01      # 1 bling, at most CRYSTAL_BLING_MAX per attack
CRYSTAL_BLING_MAX = 2


def decoration_loot(castle, creature_loot, account, now, rng=random):
    """({Decoration-Id: DefenseIngredientLoot fields}, {Decoration-Id: [items]}).
    Bling crystals: 1% for 1 bling each, at most 2 per attack, within the
    weekly bling loot cap (only with the bling economy on)."""
    import item_drops  # noqa: PLC0415 (item_drops imports loot)
    gold = [x["Gold"] for x in creature_loot.values() if x.get("Gold")]
    lf = [x["LifeForce"] for x in creature_loot.values() if x.get("LifeForce")]
    avg_gold = sum(gold) / len(gold) if gold else 5
    avg_lf = sum(lf) / len(lf) if lf else 5
    chance = DECO_CHANCE
    blings_left = (min(CRYSTAL_BLING_MAX, bling_loot_left(account, now))
                   if balance.enabled() else 0)
    out, items = {}, {}
    for room in castle.get("Rooms") or []:
        for d in room.get("Decorations") or []:
            entry = {"Gold": 0, "LifeForce": 0, "Xp": 0, "HealthOrbFragments": 0, "PremiumCash": 0}
            if d.get("SpecContainerId") in BLING_CRYSTALS:
                # Bling Crystal: only its bling chance, no gold/life force
                if blings_left > 0 and rng.random() < CRYSTAL_BLING_CHANCE:
                    entry["PremiumCash"] = 1
                    blings_left -= 1
                    out[d["Id"]] = entry
                continue
            r = rng.random()
            if r < DECO_ITEM_CHANCE:
                items[d["Id"]] = [item_drops.material_item("Basic")]
            elif r < chance:
                if rng.random() < 0.5:
                    entry["Gold"] = max(1, round(avg_gold * rng.uniform(*DECO_AMOUNT)))
                else:
                    entry["LifeForce"] = max(1, round(avg_lf * rng.uniform(*DECO_AMOUNT)))
            if entry["Gold"] or entry["LifeForce"] or entry["PremiumCash"] or d["Id"] in items:
                out[d["Id"]] = entry
    return out, items
