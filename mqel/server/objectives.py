"""Burg-Objectives (Quests "Defeat ..."): Abschluss nach einem Angriff.

Belegt durch einen Original-Mitschnitt (docs/analysis/mqeloffline-captures,
EndAttack auf Burg 101): der Server meldet ObjectiveCompleted 302 und
ObjectiveUnlocked 303 (Folgequest mit ObjectiveCompletedObjectiveRequirement
302); die Belohnung (Handwerksmaterial) kam als Inbox-Items.

Regeln aus ObjectiveSettings.json (DefeatCastleObjective):
- CastleId {CastleType Ubisoft, Id} = AccountId der angegriffenen Burg,
- CastleCompletedCondition: Angriff mit CompletionType TreasureRoom (0),
- DefenseIngredientDestroyedCondition: Kreatur/Deko der Spec getötet bzw.
  zerstört (Count Stück).
Nur Objectives im Status Unlocked werden abgeschlossen.
"""

import functools
import json
import os

import balance
import loot

COMPLETED, UNLOCKED = 2, 1          # ObjectiveStatus
COMPLETION_TREASURE_ROOM = 0        # AttackCompletionType
REWARD_CURRENCY = {"IGC": "InGameCoin", "LifeForce": "LifeForce",
                   "PremiumCash": "PremiumCash"}


def _short(type_name):
    return type_name.split(",")[0].rsplit(".", 1)[-1]


@functools.lru_cache(maxsize=None)
def definitions():
    path = os.path.join(loot.SETTINGS, "GeneralSettings", "ObjectiveSettings.json")
    with open(path, encoding="utf-8") as f:
        return {o["Id"]: o for o in json.load(f)["Objectives"]}


CASTLE_TYPE_NAMES = {0: "User", 1: "Ubisoft"}


def _conditions_met(obj, castle_id, castle_type, completion_type, destroyed):
    """destroyed: {"Creature"|"Decoration": {SpecContainerId: Anzahl}}.

    Zielburg entweder fest (CastleId {CastleType, Id}) oder beliebig von
    einer Art (CastleTypes, z. B. ["User"] bei 301 "Friendly Pillage")."""
    type_name = CASTLE_TYPE_NAMES.get(castle_type)
    cid = obj.get("CastleId")
    if cid is not None:
        if cid.get("CastleType") != type_name or cid.get("Id") != castle_id:
            return False
    elif type_name not in (obj.get("CastleTypes") or []):
        return False
    for c in obj.get("Conditions", []):
        kind = _short(c["$type"])
        if kind == "CastleCompletedCondition":
            if completion_type != COMPLETION_TREASURE_ROOM:
                return False
        elif kind == "DefenseIngredientDestroyedCondition":
            got = destroyed.get(c.get("ItemType"), {}).get(c["SpecContainerId"], 0)
            if got < c.get("Count", 1):
                return False
    return True


def completed_by_attack(account, castle_id, castle_type, completion_type,
                        destroyed):
    """Ids der Objectives, die dieser Angriff abschließt."""
    status = {o["ObjectiveId"]: o["Status"] for o in account.get("Objectives", [])}
    return [oid for oid, obj in definitions().items()
            if _short(obj["$type"]) == "DefeatCastleObjective"
            and status.get(oid) == UNLOCKED
            and _conditions_met(obj, castle_id, castle_type, completion_type,
                                    destroyed)]


# DefenseIngredientBuiltCondition.ItemType -> Liste im Burgraum
BUILT_LISTS = {"Room": None, "Creature": "Creatures", "Trap": "Traps",
               "Decoration": "Decorations"}
def _build_condition_met(c, draft, cp):
    kind = _short(c["$type"])
    rooms = draft["Rooms"]
    if kind == "ConstructionPointsBuiltCondition":
        return cp >= c.get("Count", 1)
    if kind == "BuildingRankCondition":
        n = sum(1 for r in rooms for b in r.get("Buildings") or []
                if b["SpecContainerId"] == c["SpecContainerId"]
                and b.get("Rank", 0) >= c.get("Rank", 1))
        return n >= c.get("Count", 1)
    if kind == "DefenseIngredientBuiltCondition":
        key = BUILT_LISTS.get(c.get("ItemType"), "?")
        n = len(rooms) if key is None else sum(len(r.get(key) or []) for r in rooms)
        return n >= c.get("Count", 1)
    if kind == "CastleValidityCondition":
        return True  # Gültigkeit prüft der Client (Annahme: gespeicherte Burg ist gültig)
    return False


def completed_by_build(account):
    """Ids der freigeschalteten BuildObjectives, die die eigene Burg
    erfüllt (Bau-Quests, ClientSideCompletion: der Client hakt sie ab und
    bucht die Belohnung selbst, ohne den Server zu benachrichtigen)."""
    import castles
    draft = account["BuildInfo"]["Draft"]
    cp = castles.total_construction_points(draft)
    status = {o["ObjectiveId"]: o["Status"] for o in account.get("Objectives", [])}
    return [oid for oid, obj in definitions().items()
            if _short(obj["$type"]) == "BuildObjective"
            and status.get(oid) == UNLOCKED
            and all(_build_condition_met(c, draft, cp) for c in obj.get("Conditions", []))]


def _requirements_met(obj, done, account):
    regions = {r["AttackRegionId"] for h in account.get("Heroes", [])
               for r in h.get("AttackRegions") or [] if r.get("Status", 0) >= 2}
    for r in obj.get("Requirements", []):
        kind = _short(r["$type"])
        if kind == "ObjectiveCompletedObjectiveRequirement":
            if r["ObjectiveId"] not in done:
                return False
        elif kind == "AttackRegionUnlockedObjectiveRequirement":
            if r["AttackRegionId"] not in regions:
                return False
        else:
            return False  # unbekannte Voraussetzung: nicht freischalten
    return True


def newly_unlocked(account, just_completed=(), regions=()):
    """Objectives, die durch `just_completed` bzw. die frisch
    freigeschalteten Angriffsregionen `regions` freigeschaltet werden (nur
    solche, deren Voraussetzungen darauf verweisen; z. B. 101 "Defeat
    Durrrr" mit Region 5)."""
    known = {o["ObjectiveId"] for o in account.get("Objectives", [])}
    done = {o["ObjectiveId"] for o in account.get("Objectives", [])
            if o["Status"] == COMPLETED} | set(just_completed)

    def triggered(r):
        kind = _short(r["$type"])
        return (kind == "ObjectiveCompletedObjectiveRequirement"
                and r["ObjectiveId"] in just_completed
                or kind == "AttackRegionUnlockedObjectiveRequirement"
                and r["AttackRegionId"] in regions)

    out = []
    for oid, obj in definitions().items():
        reqs = obj.get("Requirements", [])
        if oid in known or not any(triggered(r) for r in reqs):
            continue
        if _requirements_met(obj, done, account):
            out.append(oid)
    return out


def rewards(objective_id):
    """(Währungen {Wallet-Feld: Betrag}, Xp, Items in Client-Form).

    Handwerksmaterial als HeroConsumableItem (so liegt es im Inventar der
    Account-Vorlagen, TemplateId = Material-Id)."""
    currency, xp, items = {}, 0, []
    reward = definitions()[objective_id].get("Reward") or {}
    for r in reward.get("RewardItems", []):
        kind = _short(r["$type"])
        if kind == "CurrencyAmountRewardItem":
            a = r["CurrencyAmount"]
            field = REWARD_CURRENCY[a["CurrencyType"]]
            amount = a["Amount"]
            if field == "PremiumCash":
                amount = balance.objective_blings(objective_id, amount)
            currency[field] = currency.get(field, 0) + amount
        elif kind == "XpRewardItem":
            xp += r["Xp"]
        elif kind == "CraftingMaterialsRewardItem":
            items += [("consumable", m["Id"], m.get("Quantity", 1))
                      for m in r["CraftingMaterials"]]
        elif kind == "InventoryItemRewardItem":
            items.append(("equipment", r["Item"]["TemplateId"],
                          r["Item"].get("ItemLevel", 1)))
    return currency, xp, items
