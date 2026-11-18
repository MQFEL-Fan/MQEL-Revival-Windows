#!/usr/bin/env python3
"""Baut server/stubs/account-information.json:
Antwort für AccountInformationService.hqs/GetAccountInformation.

Quellen:
- Form:  HyperQuest.GameServer.Contracts.AccountInformation (+Base), per
  Reflection gedumpt (docs/analysis/dto-catalog.txt, server/gen_stub.ps1).
- Werte: client/.../AccountTemplates/000003 - FullAccount.json
  (Server-Template für ResetAccount/CreateFullyFunctionalAccount).

Gebrauch:  python server/build_account_stub.py
           python server/build_account_stub.py --template "<Datei>" --out <Pfad>
(z. B. frischer Account: "010031 - 1 Hero - Lvl 5.json" -> account-fresh.json;
danach jeweils add_dollar_type.py <Pfad>)
"""

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 010030: einziger Account mit VOLLSTAENDIGER Burg (Raeume mit Buildings und
# Creatures). 000003: Vollstaendigkeit bei Objectives/Wallet (Basis identisch:
# 4 Helden Lvl 30). Siehe docs/analysis/dto-catalog.txt (CastleRoom etc.).
TEMPLATE = os.path.join(ROOT, "client", "GameData", "Data", "GameplaySettings",
                        "AccountTemplates",
                        "010030 - FullAccount_30_FullUpdate.json")
TEMPLATE_OBJECTIVES = os.path.join(
    ROOT, "client", "GameData", "Data", "GameplaySettings",
    "AccountTemplates", "000003 - FullAccount.json")
SKELETON = os.path.join(ROOT, "server", "stubs", "account-information.json")
ZERO_OID = "000000000000000000000000"


BUILDINGS = os.path.join(ROOT, "client", "GameData", "Data", "GameplaySettings",
                         "Buildings")
GOLD_STORAGE, LIFEFORCE_STORAGE = 3, 4


def storage_capacity(spec_id, rank):
    """Lagerkapazität aus Buildings/<Spec>/Gameplay.json (Ranks[rank-1])."""
    import glob
    path = glob.glob(os.path.join(BUILDINGS, "%06d - *" % spec_id,
                                  "Gameplay.json"))[0]
    for comp in load_json(path):
        if comp["$type"].split(",")[0].endswith(".BuildingSpec"):
            ranks = comp["Ranks"]
            return ranks[max(1, min(rank, len(ranks))) - 1]["Capacity"]
    raise KeyError("keine Ranks für Building %d" % spec_id)


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def client_equipment_item(it):
    """HeroEquipmentItem in der Form des Update3-Clients.

    Die AccountTemplates der Client-Daten tragen Items bereits in genau
    dieser Form (ArchetypeId, PrimaryStatsModifiers, Effects{Id,Level,
    Type}); Werte werden 1:1 übernommen statt neu erfunden. Feldliste aus
    dem Client-Leser (MightyQuest_release.exe 0x679500): ArchetypeId,
    DyeTemplateId, Effects, IsBranded, IsSellable, ItemLevel, PowerUp,
    PrimaryStatsModifiers, TemplateId. Toolbox-Felder (SellPrice, Type,
    BaseStat*, Effect.Variation/AbsoluteValue) kennt der Client nicht.
    """
    out = {
        "ArchetypeId": it.get("ArchetypeId", 0),
        "DyeTemplateId": it.get("DyeTemplateId", 0),
        "Effects": [{"Id": e.get("Id", 0), "Level": e.get("Level", 0),
                     "Type": e.get("Type", 0)}  # ItemEffectType.Stat=0
                    for e in it.get("Effects", [])],
        "IsBranded": bool(it.get("IsBranded", False)),
        "IsSellable": bool(it.get("IsSellable", True)),
        "ItemLevel": it.get("ItemLevel", 0),
        "PrimaryStatsModifiers": list(it.get("PrimaryStatsModifiers", [])),
        "TemplateId": it.get("TemplateId", 0),
    }
    if it.get("PowerUp"):  # ItemPowerUp {Id, Level}; fehlt = kein PowerUp
        p = it["PowerUp"]
        out["PowerUp"] = {"Id": p.get("Id", 0), "Level": p.get("Level", 0)}
    return out


def client_inventory_item(item):
    """Inventar-Item: Consumable nur mit TemplateId, sonst Equipment."""
    if "Consumable" in item.get("$type", ""):
        return {"TemplateId": item.get("TemplateId", 0)}
    return client_equipment_item(item)


def build_hero(h, index):
    eq = h.get("Equipment") or {}
    slots = ("Back", "Body", "Costume", "Finger1", "Finger2", "Hands", "Head",
             "MainHand", "Neck", "OffHand", "Pet", "Shoulders")
    equipment = {}
    for s in slots:
        it = eq.get(s)
        if not it:
            equipment[s] = None
            continue
        equipment[s] = client_equipment_item(it)
    spells = []
    for i, sp in enumerate(h.get("EquippedSpells", [])):
        spells.append({
            "SlotIndex": sp.get("SlotIndex", i),
            "SpellSpecContainerId": sp.get("SpellSpecContainerId", 0),
        })
    consumables = []
    for i, c in enumerate(h.get("EquippedConsumables", [])):
        consumables.append({
            "SlotIndex": c.get("SlotIndex", i),
            "StackCount": c.get("StackCount", 1),
            "TemplateId": c.get("TemplateId", 0),
        })
    st = h.get("Stats", {})
    return {
        "HeroSpecContainerId": h.get("HeroSpecContainerId", 0),
        "XP": h.get("XP", 0),
        "Level": h.get("Level", 1),
        # Attribute stehen in keinem Template (Server berechnet sie aus
        # Hero-Spec + Level); 0 ist boot-fähig, Kampfwerte später.
        "Attributes": {"Energy": 0, "Magic": 0, "Power": 0, "Vitality": 0},
        "Equipment": equipment,
        "EquippedSpells": spells,
        "EquippedConsumables": consumables,
        "Stats": {
            "TimePlayed": st.get("TimePlayed", 0),
            "TotalCastlesLooted": st.get("TotalCastlesLooted", 0),
            "TotalCreaturesKilled": st.get("TotalCreaturesKilled", 0),
        },
        "HeroStatModifier": {},
        "OwnerSpecialPacks": [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=TEMPLATE,
                    help="AccountTemplate (Dateiname oder Pfad)")
    ap.add_argument("--out", default=SKELETON)
    args = ap.parse_args()
    template = args.template
    if not os.path.exists(template):
        template = os.path.join(os.path.dirname(TEMPLATE), template)
    t = load_json(template)
    skel = load_json(SKELETON)
    inv = t.get("Inventory", {})
    # Objectives: aus dem Template selbst, sonst aus 000003 (010030 hat
    # keine); ein Neu-Account (000001, ohne Helden) startet ohne.
    tf = (t if t.get("Objectives") or not inv.get("Heroes")
          else load_json(TEMPLATE_OBJECTIVES))

    heroes = [build_hero(h, i) for i, h in enumerate(inv.get("Heroes", []))]

    hero_items = []
    for s in inv.get("HeroItems", []):
        hero_items.append({
            "Item": client_inventory_item(s.get("Item", {})),
            "SlotIndex": s.get("SlotIndex", 0),
            "StackCount": s.get("StackCount", 1),
        })

    objectives = []
    t_obj = tf.get("Objectives", {})
    for key in sorted(t_obj, key=int):
        o = t_obj[key]
        objectives.append({
            "HasViewed": True,  # keine Tutorial-Overlays beim Boot
            "LastStatusDate": o.get("LastStatusDate", ""),
            "ObjectiveId": o.get("ObjectiveId", int(key)),
            "ProgressionCount": 0,
            "Status": o.get("Status", 0),
        })

    regions = [{"AttackRegionId": r, "Status": 2}  # Unlocked
               for r in t.get("UnlockedAttackRegions", [])]
    # Client (Update3) fuehrt Regionen PRO HELD (Hero.AttackRegions, vgl.
    # AttackSelectionController::GetCurrentHeroAttackRegions); ohne sie
    # Absturz beim Oeffnen der Angriffsauswahl. Account-Feld bleibt fuer
    # die neueren Contracts.
    for h in heroes:
        h["AttackRegions"] = [dict(r) for r in regions]

    mines = {}
    for key in sorted(t.get("MineStatuses", {}), key=int):
        m = t["MineStatuses"][key]
        mines[key] = {
            "CumulatedAmount": 0,
            "IsActive": bool(m.get("IsActive", False)),
            "IsDestroyed": False,
            "ProductionExpirableId": ZERO_OID,
            "ShieldExpirableId": ZERO_OID,
        }

    bp = t.get("CastleBlueprint", {}) or {}
    rooms = []
    for r in bp.get("Rooms", []):
        buildings = []
        for b in r.get("Buildings", []):
            buildings.append({
                "ExpirableId": ZERO_OID,
                "Id": b.get("Id", 0),
                "Orientation": b.get("Orientation", 0),
                "Rank": b.get("Rank", 0),
                "RoomZoneId": b.get("RoomZoneId", 0),
                "SkuCode": "",
                "SpecContainerId": b.get("SpecContainerId", 0),
                "X": b.get("X", 0),
                "Y": b.get("Y", 0),
            })
        creatures = []
        for c in r.get("Creatures", []):
            creatures.append({
                "AggroPropagationOffsetX": 0,
                "AggroPropagationOffsetZ": 0,
                "Id": c.get("Id", 0),
                "IsSleeping": False,
                "Orientation": c.get("Orientation", 0),
                "RoomZoneId": c.get("RoomZoneId", 0),
                "SkuCode": "",
                "SpecContainerId": c.get("SpecContainerId", 0),
                "X": c.get("X", 0),
                "Y": c.get("Y", 0),
            })
        rooms.append({
            "Buildings": buildings, "Creatures": creatures,
            "Decorations": [], "Traps": [], "Triggers": [],
            "Id": r.get("Id", 0),
            "Orientation": r.get("Orientation", 0),
            "SkuCode": "",
            "SpecContainerId": r.get("SpecContainerId", 0),
            "X": r.get("X", 0), "Y": r.get("Y", 0),
        })

    ranks = {b.get("SpecContainerId"): b.get("Rank", 1)
             for r in bp.get("Rooms", []) for b in r.get("Buildings", [])}
    gold_cap = storage_capacity(GOLD_STORAGE, ranks.get(GOLD_STORAGE, 1))
    lf_cap = storage_capacity(LIFEFORCE_STORAGE, ranks.get(LIFEFORCE_STORAGE, 1))

    def tier(spec):
        return {"SpecContainerId": spec, "Specialization": 0, "Tier": 1}

    def archetype(spec):
        return {"AvailableCount": 1, "SpecContainerId": spec,
                "Specialization": 0, "Tier": 1}  # Client: Tier > 0 (UiHelper:347)

    resp = {
        "News": {"LastViewedNewsId": "", "News": []},
        "CompletedAchievements": [],
        "DefendLog": {"DefendLogEntries": [],
                      "OfflinePeriod": {"EndDateTime": "", "StartDateTime": ""}},
        "Expirables": [],
        "CountryCode": t.get("CountryCode", "DE"),
        "ShopSkus": {"ShopSkus": [], "Version": ""},
        "ClientSettings": {
            "AccountCacheValidation": False,
            "ClientTrackingSettings": {
                # 0 = Timer wird nie angelegt, Neustart assertet
                # ("Cannot find timer 0", TrackingController -> TimeController).
                # Sekunden (TrackingSettings 1m / 5m): der TrackingController
                # vergleicht ClientIdleInterval mit derselben Uhr wie
                # IdleTimeThresholds (30 s) und gibt GameStateTrackingInterval
                # unverändert an TimeController (0xe79e40).
                "ClientIdleInterval": 60, "EnableProfiling": False,
                "GameStateTrackingInterval": 300,
                "GlanceViewDurationTriggerInSeconds": 0,
                "IdleTimeThresholds": {},
            },
            "FriendReferalUrl": "",
            "PrimaryShopUrl": "",
            # Chat: Client validiert XmppInfo direkt nach GetAccountInformation
            # ("Invalid XmppInfo in AccountInformation") und baut ohne gueltige
            # Info keine Session auf -> spaeter OPAL ASSERT in
            # ChatController::LeaveRoom. Experiment-Reihe:
            #  Enabled=true  -> Account-Task wirft SOFORT 0x80030003, kein Netz.
            #  Enabled=false -> Task ok, weiter bis Lobby (s. docs).
            # Darum vorerst disabled (Revival-Strategie "Chat aus"), bis der
            # Rest des Boots steht; Objekt bleibt non-null (Getter asserts!).
            "XmppInfo": {"ConferenceServer": "127.0.0.1",
                         "Domain": "127.0.0.1", "Enabled": False,
                         "Password": "test", "Port": 5222,
                         "Server": "127.0.0.1", "Username": "test"},
        },
        "TargetedAttackAvailableCount": 5,  # = TargetedAttackMaxCount; <Max startet Reload-Timer ohne Expirable ("Cannot find timer 0")
        "IsCastleAttackable": True,
        "AccountId": 1,
        "SpecialPacks": [],
        # Neu-Account: Name wird im Tutorial gewählt (Assignment 30)
        "DisplayName": "" if t.get("ShouldResetDisplayName") else "Reviver",
        "GamerScore": 0,
        "TrophyScore": t.get("TrophyScore", 0),
        "SelectedHeroId": (inv["Heroes"][0].get("HeroSpecContainerId", 2)
                           if inv.get("Heroes") else None),
        "Privileges": t.get("Privileges", 1),
        "Wallet": {
            "InGameCoin": t.get("IGC", 0),
            "InGameCoinStorageCapacity": gold_cap,
            "LifeForce": t.get("LifeForce", 0),
            "LifeForceStorageCapacity": lf_cap,
            "PremiumCash": t.get("PremiumCash", 0),
        },
        "BuildInfo": {
            "ArchitectOfficeRank": 0,
            "BuildingNextIndex": 0,
            "CastleHeartRank": 0,
            # Client dereferenziert BuildInfo.CastleStats ungeprüft
            # (VisualPlayerMiniCastleHandler::RefreshCastleUIElements,
            # Absturz 0xc5b28e bei fehlendem Objekt).
            "CastleStats": {"AttackCount": 0, "HeroesKilled": 0,
                            "MaxConstructionPoints": 1000,
                            "SuccessfulAttackCount": 0,
                            "TotalConstructionPoints": 0, "TrapCount": 0},
            "CastleType": 0,  # User
            "CreatureArchetypes": [archetype(c.get("SpecContainerId", 0))
                                   for c in inv.get("Creatures", [])],
            "CreatureNextIndex": 0,
            "DecorationNextIndex": 0,
            "Draft": {
                "AccountDisplayName": "Reviver",
                "AccountId": 1,
                "CreationDate": "",
                # Client liest die Stufe hieraus (UiHelper:347 "Tier is out
                # of bound 0" trotz Archetyp-Tier) -> je Archetyp Tier 1.
                "CreatureTiers": [tier(c.get("SpecContainerId", 0))
                                  for c in inv.get("Creatures", [])],
                "LayoutId": 1,  # 000001 - DefaultLayout
                "ModificationDate": "",
                "OasisNameId": 0,
                "Rooms": rooms,
                "ThemeId": 1,  # 0 = "No castle theme found" (CastleThemeHelper:242)
                "TrapTiers": [tier(x.get("SpecContainerId", 0))
                              for x in inv.get("Traps", [])],
            },
            "HeroCorpses": [],
            "InventoryDecorations": [],
            "InventoryRooms": [
                {"AvailableCount": r.get("AvailableCount", 0),
                 "Level": r.get("Level", 0),
                 "SpecContainerId": r.get("SpecContainerId", 0)}
                for r in inv.get("Rooms", [])
            ],
            "InventoryThemes": [],
            "IsDraftPublished": True,
            "IsRollbackAvailable": False,
            "Level": t.get("CastleLevel", 1),
            "MineStatuses": mines,
            "OwnerSpecialPacks": [],
            "RoomNextIndex": 0,
            "ShieldEndExpirableId": ZERO_OID,
            "TimerDuration": 0,
            "TotalAttackCount": 0,
            "TotalSuccessfulAttackCount": 0,
            "TrapArchetypes": [archetype(x.get("SpecContainerId", 0))
                               for x in inv.get("Traps", [])],
            "TrapNextIndex": 0,
            "TriggerNextIndex": 0,
            "WorkersAvailable": 0,
            "WorkersCabinRank": 0,
        },
        "Heroes": heroes,
        "Inventory": {
            # Leere Schmiede: null. Ein Objekt hält das Schmiede-Fenster
            # für laufend und liest ForgedItem.Item (Absturz bei null).
            "ForgedItem": None,
            "HeroItems": hero_items,
            "InventoryTabCount": inv.get("InventoryTabCount", 2),
            "PendingSharedItems": [],
        },
        "BuyBack": {"BuyBackItems": []},
        "Friends": [],
        "FriendshipInvitations": [],
        "RecommendedFriends": [],
        "Stats": {
            "AttackTotalIGCWon": 0, "CastlesDefeated": {},
            "ChallengeCreated": 0, "ChallengeParticipated": 0,
            "ChallengeWon": 0, "CurrencyAccumulation": {},
            "DefeatCastleStrike": 0, "DefeatFriendsCastleStrike": 0,
            "KilledCreatures": {}, "TotalCastlesLooted": 0,
            "TotalCreaturesKilled": 0, "TotalItemsLooted": 0,
        },
        "CompletedAssignments": t.get("CompletedAssignments", []),
        "UnlockedSpells": [],  # account_state schaltet ausgerüstete Zauber frei
        "UnlockedEmotes": inv.get("UnlockedEmotes", []),
        "Objectives": objectives,
        "Challenges": [],
        "AttackRegions": regions,
        "ActiveConsumables": [],
        "AvatarId": int(t.get("AvatarId", 0)),
        "ProfanityFiltering": bool(t.get("ProfanityFiltering", False)),
        "LeagueId": 0,
        "SubLeagueId": 0,
        "UnlockedAvatars": [],
    }

    # Form-Treue: exakt die Keys des per Reflection erzeugten Skeletts.
    extra = set(resp) - set(skel)
    missing = set(skel) - set(resp) - {"$type"}  # add_dollar_type-Lauf
    assert not extra, "unerwartete Keys: %s" % sorted(extra)
    assert not missing, "fehlende Keys: %s" % sorted(missing)

    # Neu-Account (noch kein Held): Feld weglassen wie das Original
    # (MQELOffline-Nachbau); 0 = ungültiger Held, Absturz in der Burgauswahl
    if resp["SelectedHeroId"] is None:
        del resp["SelectedHeroId"]
        resp["Privileges"] = 9  # Wert des Originals vor der Heldenwahl

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(resp, f, ensure_ascii=False)
    print("geschrieben: %s (%d Zeichen, %d Helden, %d Objectives, "
          "%d Raeume)" % (args.out, len(json.dumps(resp)),
                          len(heroes), len(objectives), len(rooms)))


if __name__ == "__main__":
    main()
