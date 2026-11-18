#!/usr/bin/env python3
"""Ergänzt $type in allen DTO-Objekten des Account-Stubs.

Der Client-Deserialisierer löst Objekt-Parser per $type auf
("Cannot get object serializer [%s]"); ohne $type scheitert JEDES
nicht-leere Objekt (nur {} kommt durch). Format wie vom Client gesendet:
  "$type": "<FullName>, HyperQuest.GameServer.Contracts" (an ERSTER Stelle,
  wie Newtonsoft mit TypeNameHandling es emittiert).

Gebrauch:  python server/build_account_stub.py && python server/add_dollar_type.py [Pfad]
Liest/schreibt den Pfad (Default server/stubs/account-information.json).
"""

import json
import os
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB = os.path.join(ROOT, "server", "stubs", "account-information.json")
ASM = "HyperQuest.GameServer.Contracts"
P = "HyperQuest.GameServer.Contracts."


def T(name):
    return "%s%s, %s" % (P, name, ASM)


# Pfad (Tupel aus Keys; "*" = jedes Listenelement, "**" = Dict-Werte)
# -> DTO-Name. Pfade ohne Eintrag bekommen KEIN $type (Skalare, Dicts,
# Listen selbst, Enums, ObjectIds, Dates).
TYPES = {
    (): "AccountInformation",
    ("News",): "NewsResult",
    ("DefendLog",): "DefendLog",
    ("DefendLog", "OfflinePeriod"): "Period",
    ("ShopSkus",): "ShopSkuContainer",
    ("ClientSettings",): "ClientSettings",
    ("ClientSettings", "ClientTrackingSettings"): "ClientTrackingSettings",
    ("ClientSettings", "XmppInfo"): "XmppInfo",
    ("Wallet",): "Wallet",
    ("BuildInfo",): "BuildInfo",
    ("BuildInfo", "CastleStats"): "CastleStats",
    ("BuildInfo", "Draft"): "Castle",
    ("BuildInfo", "Draft", "Rooms", "*"): "CastleRoom",
    ("BuildInfo", "Draft", "Rooms", "*", "Buildings", "*"): "CastleBuilding",
    ("BuildInfo", "Draft", "Rooms", "*", "Creatures", "*"): "CastleCreature",
    ("BuildInfo", "Draft", "CreatureTiers", "*"): "DefenseIngredientTier",
    ("BuildInfo", "Draft", "TrapTiers", "*"): "DefenseIngredientTier",
    ("BuildInfo", "CreatureArchetypes", "*"): "DefenseIngredientArchetype",
    ("BuildInfo", "TrapArchetypes", "*"): "DefenseIngredientArchetype",
    ("BuildInfo", "InventoryRooms", "*"): "InventoryRoom",
    ("BuildInfo", "MineStatuses", "**"): "MineStatus",
    ("Heroes", "*"): "Hero",
    ("Heroes", "*", "Attributes"): "HeroAttributes",
    ("Heroes", "*", "AttackRegions", "*"): "AccountAttackRegion",
    ("Heroes", "*", "Equipment", "**"): "HeroEquipmentItem",
    ("Heroes", "*", "Equipment", "**", "Effects", "*"): "ItemEffect",
    ("Heroes", "*", "Equipment", "**", "PowerUp"): "ItemPowerUp",
    ("Inventory", "HeroItems", "*", "Item", "Effects", "*"): "ItemEffect",
    ("Inventory", "HeroItems", "*", "Item", "PowerUp"): "ItemPowerUp",
    ("Heroes", "*", "EquippedSpells", "*"): "HeroSpellSlot",
    ("Heroes", "*", "EquippedConsumables", "*"): "HeroConsumableSlot",
    ("Heroes", "*", "Stats"): "AccountHeroStats",
    ("Inventory",): "AccountInventory",
    ("Inventory", "ForgedItem"): "AccountForgedItem",
    ("Inventory", "ForgedItem", "Item"): "HeroEquipmentItem",
    ("Inventory", "HeroItems", "*"): "AccountInventorySlot",
    # Item ist polymorph (InventoryItem-Basis): Typ nach Type-Feld.
    ("BuyBack",): "AccountBuyBack",
    ("Stats",): "AccountStats",
    ("Objectives", "*"): "AccountObjective",
    ("AttackRegions", "*"): "AccountAttackRegion",
}


def typename_for(path, node):
    """DTO-Name für Pfad; Spezialfall polymorphe InventoryItems."""
    if (len(path) >= 4 and path[-3] == "HeroItems"
            and path[-1] == "Item"):
        # Client-Form ohne Type-Feld: Equipment hat immer ItemLevel.
        is_eq = isinstance(node, dict) and "ItemLevel" in node
        return "HeroEquipmentItem" if is_eq else "HeroConsumableItem"
    hit = TYPES.get(path)
    if hit is None and len(path) >= 1:
        # Dict-Werte (MineStatuses.<id>, Equipment.<slot>)
        hit = TYPES.get(path[:-1] + ("**",))
    return hit


def walk(node, path=()):
    if isinstance(node, dict):
        out = OrderedDict()
        tname = typename_for(path, node)
        if tname:
            out["$type"] = T(tname)
        for k, v in node.items():
            out[k] = walk(v, path + (k,))
        return out
    if isinstance(node, list):
        return [walk(v, path + ("*",)) for v in node]
    return node


def main():
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else STUB
    with open(path, encoding="utf-8") as f:
        d = json.load(f, object_pairs_hook=OrderedDict)
    d = walk(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    s = json.dumps(d)
    print(os.path.basename(path) + " mit $type (%d Objekte, %d Zeichen)" % (
        s.count('"$type"'), len(s)))


if __name__ == "__main__":
    main()
