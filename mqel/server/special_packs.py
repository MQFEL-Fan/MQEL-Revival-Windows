"""Special Packs (GeneralSettings/SpecialPackSettings.json), vor allem das
Infinite Pack (ShopSettings.InfinitePackId = 72).

Das Infinite Pack war ein Echtgeld-Kauf (ProductPageUrl
"blings/infinite_pack"); hier schaltet es der Test-Shop frei. Der
Shop-Reiter "Infinite Pack" (Cornelius' Emporium, Kategorie
UnifiedShopPremiumPack) zeigt die Pack-Artikel: SKUs mit IsLocked und
IsLimitedQuantity, Preis 1 Gold. Freischaltung und Kontingent kommen je
Account aus Account.ShopSkuModifiers (zweiter Account-Leser 0x542170,
Elemente ShopSkuModifier 0x8c9b00):
  SkuCode, Unlock, LimitedQuantityMax, LimitedQuantityConsumed,
  LimitedQuantityNextUnlockCastleLevelRequirement,
  LimitedQuantityNextUnlockQuantity.
Kontingent: PerLevelShopSkus {Burg-Level: [{SkuCode, Amount}]} summiert bis
zum aktuellen Burg-Level (wer später kauft, bekommt die erreichten Stufen
nachträglich).
"""

import functools
import json
import os

import balance
import level60
import loot

# Shop-Artikel ohne Pack mit eigenem Kontingent (im Original 1, hier bis zur
# Instanzgrenze des Gebäudes): Bling-Mine "Permanent", Material-Mine
SHOP_QUOTAS = {"15522": 3, "15699": 3}

T = lambda name: f"HyperQuest.GameServer.Contracts.{name}, HyperQuest.GameServer.Contracts"


@functools.lru_cache(maxsize=None)
def _settings():
    path = os.path.join(loot.SETTINGS, "GeneralSettings", "SpecialPackSettings.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def infinite_pack_id():
    return _settings()["InfinitePackId"]


def pack(pack_id):
    """Pack aus SpecialPackSettings; bei eingeschalteter Bling-Wirtschaft
    ohne EarlyHeroAccess wie in den gepatchten Client-Daten
    (balance.DATA_REVISION 2: Helden nur für Blings)."""
    p = next(p for p in _settings()["SpecialPacks"] if p["Id"] == pack_id)
    if balance.enabled() and "EarlyHeroAccess" in p:
        p = {k: v for k, v in p.items() if k != "EarlyHeroAccess"}
    return p


def castle_level_packs(sale_id):
    """CastleLevelUpShopSkuPacks {Burg-Level: [{SkuCode, Amount}]}: Kontingente
    der Kreaturen/Fallen in Cornelius' Shop (SKUs "[CE] ...", IsLimitedQuantity;
    ohne Kontingent bleibt der Reiter leer). Je gekaufter Startburg
    (CastlesForSaleSettings), sonst die allgemeine Liste aus ShopSettings."""
    general = os.path.join(loot.SETTINGS, "GeneralSettings")
    with open(os.path.join(general, "CastlesForSaleSettings.json"), encoding="utf-8") as f:
        sale = next((c for c in json.load(f)["Castles"] if c["SaleId"] == sale_id), {})
    if "CastleLevelUpShopSkuPacks" in sale:
        return sale["CastleLevelUpShopSkuPacks"]
    with open(os.path.join(general, "ShopSettings.json"), encoding="utf-8") as f:
        return json.load(f)["CastleLevelUpShopSkuPacks"]


def modifiers(pack_ids, castle_level, consumed, level_packs=None):
    """ShopSkuModifiers aller Packs und der Burg-Level-Kontingente
    (level_packs wie PerLevelShopSkus); consumed {SkuCode: Anzahl}."""
    out = {}

    def mod(code):
        return out.setdefault(code, {
            "$type": T("ShopSkuModifier"), "SkuCode": code, "Unlock": False,
            "LimitedQuantityMax": 0, "LimitedQuantityConsumed": consumed.get(code, 0),
            "LimitedQuantityNextUnlockCastleLevelRequirement": 0,
            "LimitedQuantityNextUnlockQuantity": 0})

    def per_level(table):
        for level in sorted(table, key=int):
            for s in table[level]:
                m = mod(s["SkuCode"])
                if int(level) <= castle_level:
                    m["LimitedQuantityMax"] += s["Amount"]
                elif not m["LimitedQuantityNextUnlockCastleLevelRequirement"]:
                    m["LimitedQuantityNextUnlockCastleLevelRequirement"] = int(level)
                    m["LimitedQuantityNextUnlockQuantity"] = s["Amount"]

    for pid in pack_ids:
        p = pack(pid)
        for s in p.get("ShopSkus", []):
            m = mod(s["SkuCode"])
            m["Unlock"] = m["Unlock"] or bool(s.get("Unlock"))
            m["LimitedQuantityMax"] += s.get("Amount", 0)
        per_level(p.get("PerLevelShopSkus", {}))
    per_level(level_packs or {})
    for code, quota in SHOP_QUOTAS.items():
        m = mod(code)
        m["LimitedQuantityMax"] += quota
        # Level-60-Update: one more bling mine with castle heart 35 and 55
        if code == balance.BLING_MINE_SKU and level60.ENABLED:
            for heart in level60.MINE_INSTANCE_HEARTS:
                if heart <= castle_level:
                    m["LimitedQuantityMax"] += 1
                elif not m["LimitedQuantityNextUnlockCastleLevelRequirement"]:
                    m["LimitedQuantityNextUnlockCastleLevelRequirement"] = heart
                    m["LimitedQuantityNextUnlockQuantity"] = 1
    return list(out.values())

