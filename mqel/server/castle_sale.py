"""Kaufbare Burgen (CastleForSaleService): Startburg-Auswahl im Tutorial.

Quelle: GeneralSettings/CastlesForSaleSettings.json (SaleId -> Ubisoft-Burg
UbisoftCastleId, Texte, Icon) und die Burgdateien Castles/0010xx - BUY_*.
Form laut Original-Mitschnitten (docs/analysis/mqeloffline-captures,
CastleForSaleService.cpp:20/28): GetCastlesForSale -> {CastlesForSale:
[CastleForSaleInfoSummary]}, GetCastleForSaleBuildInfo -> BuildInfo mit der Burg als
Draft (UbisoftCastle, IsForSaleCastle).
"""

import functools
import glob
import json
import os

import castles

T = castles.T
SETTINGS = os.path.join(os.path.dirname(castles.CASTLES), "GeneralSettings",
                        "CastlesForSaleSettings.json")


@functools.lru_cache(maxsize=None)
def _sales():
    with open(SETTINGS, encoding="utf-8") as f:
        return {c["SaleId"]: c for c in json.load(f)["Castles"]}


@functools.lru_cache(maxsize=None)
def _castle(castle_id):
    path = glob.glob(os.path.join(castles.CASTLES, "%06d - *" % castle_id))
    with open(path[0], encoding="utf-8") as f:
        return json.load(f)


def sale_for_theme(theme_id):
    """SaleId der Startburg mit diesem Thema (oder None)."""
    return next((sid for sid, s in sorted(_sales().items())
                 if s.get("IsStartupCastle")
                 and _castle(s["UbisoftCastleId"]).get("ThemeId") == theme_id), None)


def _summary(sale):
    c = _castle(sale["UbisoftCastleId"])
    return {
        "$type": T("CastleInfoSummary"),
        "AttackerStatus": 0,
        "CastleHeartRank": 1,
        "CastleThemeId": c.get("ThemeId", 1),
        "CastleType": castles.CASTLE_TYPE_UBISOFT,
        "DefenderAccountSummary": {
            "$type": T("AccountSummary"),
            "AvatarId": 10,
            "CastleLevel": 1,
            "CountryCode": "",
            "DisplayName": c.get("AccountDisplayName", ""),
            "Id": c["AccountId"],
            "IsCastleAttackable": True,
            "LeagueId": 0,
            "OasisNameId": 0,
            "SpecialPacks": [],
            "SubLeagueId": 0,
            "TrophyScore": 0,
        },
        "FromMachineLearning": False,
        "IsBranded": False,
        "IsCastleAttackable": True,
        "IsNew": True,
        "IsShielded": False,
        "LastPublishedDate": c.get("ModificationDate", ""),
        "Level": 1,
        "TrophyScore": 0,
        "VictoryConditionLevel": 0,
        "WinRatioDifficulty": 0,
    }


def castles_for_sale(startup_only):
    out = []
    for sale_id, s in sorted(_sales().items()):
        if startup_only and not s.get("IsStartupCastle"):
            continue
        out.append({
            "$type": T("CastleForSaleInfoSummary"),
            # Werte wie in den Settings (Pink Castle = Modell 1, interaktiv,
            # nicht kaufbar); ein nicht existierender Modellindex lässt den
            # Client in der Startburg-Auswahl abstürzen
            "CastleModelIndex": s.get("CastleModelIndex", 0),
            "IsInteractive": s.get("IsInteractive", False),
            "SaleId": sale_id,
            "CastleInfoSummary": _summary(s),
            "CastleTitleOasisID": s["CastleTitleOasisID"],
            "CastleDescriptionOasisID": s["CastleDescriptionOasisID"],
            "FakePriceOasisID": s["FakePriceOasisID"],
            "CastleIconUrl": s["CastleIconUrl"],
            "CanBePurchased": s.get("CanBePurchased", False),
            "SpawnPlotId": s.get("SpawnPlotId", 0),
        })
    return {"$type": T("CastlesForSaleSelectionResult"), "CastlesForSale": out}


def _archetypes(tiers):
    return [{"$type": T("DefenseIngredientArchetype"), "AvailableCount": 0,
             "SpecContainerId": t["SpecContainerId"], "Specialization": 0,
             "Tier": t.get("Tier", 1), "AutoLevelUp": t.get("AutoLevelUp", True)}
            for t in tiers]


def _next_index(c, key):
    return 1 + max([e["Id"] for r in c.get("Rooms") or [] for e in r.get(key) or []]
                   or [0])


def build_info(sale_id):
    """BuildInfo der Burg zu `sale_id` (Vorschau in der Auswahl), oder None."""
    sale = _sales().get(sale_id)
    if sale is None:
        return None
    c = _castle(sale["UbisoftCastleId"])
    draft = {"$type": T("UbisoftCastle")}
    draft.update(c)
    return {
        "$type": T("BuildInfo"),
        "Draft": draft,
        "CastleType": castles.CASTLE_TYPE_UBISOFT,
        "Level": 1,
        "CreatureArchetypes": _archetypes(c.get("CreatureTiers") or []),
        "TrapArchetypes": _archetypes(c.get("TrapTiers") or []),
        "InventoryThemes": [c.get("ThemeId", 1)],
        "RoomNextIndex": 1 + max([r["Id"] for r in c.get("Rooms") or []] or [0]),
        "CreatureNextIndex": _next_index(c, "Creatures"),
        "TrapNextIndex": _next_index(c, "Traps"),
        "DecorationNextIndex": _next_index(c, "Decorations"),
        "TriggerNextIndex": 1,
        "BuildingNextIndex": _next_index(c, "Buildings"),
    }


# Startburg nach dem Kauf: Thronsaal (Raum 21) + Herz-Raum (25) mit Herz,
# Lagern und Deko -- Aufbau laut Original-Mitschnitt der
# CastleBoughtNotification (ServerCommandService.cpp:103); die gekaufte
# Burg bestimmt nur das Thema.
_STARTER_ROOMS = [
    {"X": 4, "Y": 3, "Id": 1, "SpecContainerId": 21},
    {"X": 3, "Y": 3, "Id": 3, "SpecContainerId": 25, "Buildings": [
        {"Rank": 1, "RoomZoneId": 12, "X": 3, "Y": 3, "Orientation": 2, "Id": 1, "SpecContainerId": 1},
        {"Rank": 1, "RoomZoneId": 11, "Id": 2, "SpecContainerId": 3},
        {"Rank": 1, "RoomZoneId": 13, "Id": 3, "SpecContainerId": 4},
        {"RoomZoneId": 7, "X": 3, "Orientation": 3, "Id": 4, "SpecContainerId": 13},
        {"RoomZoneId": 4, "X": 3, "Orientation": 3, "Id": 6, "SpecContainerId": 10},
        {"RoomZoneId": 6, "X": 3, "Y": 3, "Orientation": 2, "Id": 7, "SpecContainerId": 8},
        {"RoomZoneId": 3, "Y": 3, "Orientation": 1, "Id": 8, "SpecContainerId": 9}]},
]


def bought_castle(sale_id, account_id, display_name, now):
    """Felder der BuildInfo nach dem Kauf von `sale_id` (oder None)."""
    sale = _sales().get(sale_id)
    if sale is None:
        return None
    theme = _castle(sale["UbisoftCastleId"]).get("ThemeId", 1)
    rooms = json.loads(json.dumps(_STARTER_ROOMS))
    for r in rooms:
        r["$type"] = T("CastleRoom")
        for b in r.get("Buildings", []):
            b["$type"] = T("CastleBuilding")
    return {
        "Draft": {"$type": T("Castle"), "AccountId": account_id,
                  "AccountDisplayName": display_name, "LayoutId": 1,
                  "CreationDate": now, "ModificationDate": now,
                  "Rooms": rooms, "ThemeId": theme},
        "Level": 1,
        "InventoryThemes": [2, theme],
        "RoomNextIndex": 4, "CreatureNextIndex": 40, "TrapNextIndex": 5,
        "DecorationNextIndex": 32, "TriggerNextIndex": 1, "BuildingNextIndex": 9,
        "CastleHeartRank": 1,
    }
