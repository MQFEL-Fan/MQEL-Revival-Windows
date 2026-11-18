"""Stellschrauben der Bling-Wirtschaft (docs/70-bling-wirtschaft.md), im
Webtool bearbeitbar (Seite Economy, admin.Get/SetBalance).

Gespeichert in state/<Profil>/balance.json. "Enabled" schaltet die neuen
Regeln; aus = Originalregeln, alle Werte bleiben gespeichert.

Jedes Feld hat eine Art (FIELDS): "server" wirkt nur im Server; "data"
zeigt auch der Client und kommt per Patcher in settings.bin (DataBin-Version
bekommt den Teil B<CRC> dieser Werte; jeder Stand bleibt in "History",
damit der Patcher auch von älteren Ständen aus Deltas bauen kann, und beim
Ausschalten zurück zum Original); "ui" kommt per UI-Patch (GameUI-Paket,
z. B. Achievement-Blings im Popup).
"""

import copy
import functools
import json
import os
import re
import threading
import zlib

import settings_archive

SETTINGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "client", "GameData", "Data", "GameplaySettings")
BLING_MINE = 16
BLING_MINE_SKU = "15522"  # Shop-SKU der Bling-Mine (Original 999 Blings)
ACHIEVEMENT_BLINGS_PER_POINT = 2  # Vorgabe: Punkte x 2 (zusammen ~1500)
# Vorgaben für Objective-Blings (Original 50): Bosse und Heist höher, zusammen
# 1550 statt 550 (ersetzt die gestrichenen Meilensteine)
OBJECTIVE_BLINGS = {5: 200, 100: 200, 101: 200, 99: 200, 103: 200, 102: 200,
                    104: 200, 304: 150}


@functools.lru_cache(maxsize=None)
def achievements():
    """[(Id, DebugName, Punkte)] aus AchievementSettings."""
    with open(os.path.join(SETTINGS, "GeneralSettings", "AchievementSettings.json"),
              encoding="utf-8-sig") as f:
        return [(a["Id"], a["DebugName"], a["Points"]) for a in json.load(f)["Achievements"]]


# Bling-Shop: Packs (SpecialPackSettings) und Preise, entschieden in
# docs/analysis/special-packs.md; 67 nur während Halloween (bling_shop)
SHOP_PACKS = {1: 1000, 2: 1500, 3: 1500, 4: 1500, 5: 1500, 7: 1500, 8: 1500,
              14: 1500, 15: 300, 26: 800, 27: 800, 28: 800, 45: 1500, 47: 2500,
              49: 300, 50: 1500, 51: 800, 66: 4000, 67: 1500, 69: 300, 71: 1500,
              72: 4000, 74: 2500, 75: 2500}


@functools.lru_cache(maxsize=None)
def pack_names():
    with open(os.path.join(SETTINGS, "GeneralSettings", "SpecialPackSettings.json"),
              encoding="utf-8-sig") as f:
        return {p["Id"]: p["DebugName"] for p in json.load(f)["SpecialPacks"]}


@functools.lru_cache(maxsize=None)
def objectives():
    """[(Id, DebugName, Original-Blings)] der Objectives mit Bling-Belohnung."""
    with open(os.path.join(SETTINGS, "GeneralSettings", "ObjectiveSettings.json"),
              encoding="utf-8-sig") as f:
        out = []
        for o in json.load(f)["Objectives"]:
            for r in (o.get("Reward") or {}).get("RewardItems", []):
                a = r.get("CurrencyAmount") or {}
                if a.get("CurrencyType") == "PremiumCash":
                    out.append((o["Id"], o["DebugName"], a["Amount"]))
        return out


@functools.lru_cache(maxsize=None)
def fields():
    """{(Bereich, Schlüssel): {Default, Min, Max, Kind, Label, Help}}."""
    out = {
        # Bling-Mine (Gebäude 16): 1 Bling je ProductionHours Stunden,
        # Speicher Capacity; plünderbar höchstens StealHours Stunden
        # Produktion (mindestens 1, wie PremiumCashMineLossAmount)
        ("Mine", "ProductionHours"): dict(Default=4, Min=1, Max=24, Kind="data",
                                          Label="Hours per bling", Help="Original: 1"),
        ("Mine", "Capacity"): dict(Default=42, Min=1, Max=1000, Kind="data",
                                   Label="Capacity", Help="Original: 25"),
        ("Mine", "Price"): dict(Default=500, Min=0, Max=5000, Kind="data",
                                Label="Price (blings)", Help="Shop price of a mine. Original: 999"),
        ("Mine", "StealHours"): dict(Default=1, Min=0, Max=168, Kind="server",
                                     Label="Lootable hours of production",
                                     Help="At least 1 bling; 0 = not lootable. Original: whole content"),
        # Seltene Bling-Beute: mit Chance trägt eine Kreatur Amount Blings;
        # höchstens WeeklyCap aus Beute in den letzten 7 Tagen (gleitend)
        ("Loot", "Chance"): dict(Default=40, Min=0, Max=100, Kind="server",
                                 Label="Chance per attack (%)",
                                 Help="Real attacks only (no practice, tutorial, competition)"),
        ("Loot", "Amount"): dict(Default=10, Min=1, Max=500, Kind="server",
                                 Label="Blings per drop", Help="Carried by one random creature"),
        ("Loot", "WeeklyCap"): dict(Default=600, Min=0, Max=10000, Kind="server",
                                    Label="Cap per 7 days", Help="Rolling window, not a fixed week"),
        # Liga (SeasonalCompetitionSettings) und Wettbewerbe
        # (UbisoftCompetitionSettings): alle Bling-Beträge mal Prozent
        ("Leagues", "BlingPercent"): dict(Default=200, Min=0, Max=1000, Kind="data",
                                          Label="League blings (%)",
                                          Help="All bling rewards of leagues. Original: 100"),
        ("Competitions", "BlingPercent"): dict(Default=200, Min=0, Max=1000, Kind="data",
                                               Label="Competition blings (%)",
                                               Help="Top 3 of a competition. Original: 100 (25/10/5)"),
    }
    for pid, price in SHOP_PACKS.items():
        out[("Shop", str(pid))] = dict(
            Default=price, Min=0, Max=20000, Kind="server", Label=pack_names()[pid],
            Help="Pack %d; 0 = not offered" % pid + (", Halloween only" if pid == 67 else ""))
    for oid, name, amount in objectives():
        out[("Objectives", str(oid))] = dict(
            Default=OBJECTIVE_BLINGS.get(oid, amount), Min=0, Max=5000, Kind="data",
            Label=name, Help="Original: %d" % amount)
    for aid, name, points in achievements():
        out[("Achievements", str(aid))] = dict(
            Default=points * ACHIEVEMENT_BLINGS_PER_POINT, Min=0, Max=5000, Kind="ui",
            Label=name, Help="%d points" % points)
    return out


def defaults():
    values = {"Enabled": False}
    for (section, key), f in fields().items():
        values.setdefault(section, {})[key] = f["Default"]
    return values


_lock = threading.Lock()
_path = None
_data = {"Values": defaults(), "History": {}, "Changed": None}


def load(path):
    """Stand aus path (fehlt: Vorgaben); unbekannte Schlüssel fallen weg."""
    global _path, _data
    _path = path
    values, history, changed = defaults(), {}, None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            stored = json.load(f)
        values["Enabled"] = bool(stored.get("Values", {}).get("Enabled"))
        for (section, key) in fields():
            v = (stored.get("Values", {}).get(section) or {}).get(key)
            if v is not None:
                values[section][key] = v
        history, changed = stored.get("History", {}), stored.get("Changed")
    _data = {"Values": values, "History": history, "Changed": changed}


def enabled():
    return bool(_data["Values"]["Enabled"])


def get(section, key):
    """Eingestellter Wert (wirkt nur bei enabled())."""
    return _data["Values"][section][key]


def _summary():
    return {"Values": copy.deepcopy(_data["Values"]),
            "Fields": [dict(f, Section=s, Key=k) for (s, k), f in fields().items()],
            "ClientVersion": client_version(), "Changed": _data["Changed"]}


def summary():
    with _lock:
        return _summary()


def update(new, now):
    """Neue Werte übernehmen (nur bekannte Felder, Grenzen geprüft);
    ValueError mit Text bei ungültigen Werten."""
    with _lock:
        values = copy.deepcopy(_data["Values"])
        if "Enabled" in new:
            values["Enabled"] = bool(new["Enabled"])
        for (section, key), f in fields().items():
            v = (new.get(section) or {}).get(key)
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
                raise ValueError("%s %s must be a whole number" % (section, f["Label"]))
            if not f["Min"] <= v <= f["Max"]:
                raise ValueError("%s %s must be between %d and %d"
                                 % (section, f["Label"], f["Min"], f["Max"]))
            values[section][key] = int(v)
        _data["Values"] = values
        _data["Changed"] = now
        cv = _data_values(values)
        if cv is not None:
            _data["History"][_crc(cv)] = cv
        if _path:
            os.makedirs(os.path.dirname(_path), exist_ok=True)
            tmp = _path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_data, f, indent=1)
            os.replace(tmp, _path)
        return _summary()


# --- Client-Daten: settings.bin (Patcher, DataBin) ----------------------------

def _data_values(values):
    """Werte der Art "data" oder None (aus = Original)."""
    if not values["Enabled"]:
        return None
    out = {"%s.%s" % k: values[k[0]][k[1]] for k, f in fields().items() if f["Kind"] == "data"}
    out["Revision"] = DATA_REVISION
    return out


# Feste Daten-Änderungen bei Enabled; erhöhen ändert die DataBin-Version.
# 2: Special Packs ohne EarlyHeroAccess (Helden nur für Blings)
DATA_REVISION = 2


def _crc(cv):
    return "%08x" % zlib.crc32(json.dumps(cv, sort_keys=True).encode())


def client_version():
    """Versionsteil "B<CRC>" der aktiven data-Werte, "" ohne."""
    cv = _data_values(_data["Values"])
    return "" if cv is None else "B" + _crc(cv)


def history(crc):
    """data-Werte zu einem Versionsteil (ohne "B") oder None. Der aktive
    Stand zählt immer, auch ungespeichert (z. B. neue Felder mit Vorgabe)."""
    cv = _data_values(_data["Values"])
    if cv is not None and _crc(cv) == crc:
        return cv
    return _data["History"].get(crc)


MINE_FILE = b"BUILDINGS\\000016 - BLINGMINE\\GAMEPLAY.JSON\x00"
SKU_FILE = b"SHOPSETTINGS\\SHOPSKUBASESETTINGS.JSON\x00"
OBJECTIVE_FILE = b"GENERALSETTINGS\\OBJECTIVESETTINGS.JSON\x00"


def _file_span(content, name):
    """(Beginn, Ende) des JSON-Texts der Archivdatei name."""
    start = content.find(name)
    if start < 0 or content.count(name) != 1:
        raise RuntimeError("settings.bin: %r nicht eindeutig gefunden" % name)
    begin = start + len(name)
    return begin, content.index(b"\x00", begin)


def _objective_text(text, cv):
    """ObjectiveSettings-Text mit den Bling-Beträgen aus cv (ältere Stände
    in History haben keine: Original)."""
    for oid, _, original in objectives():
        head = re.compile(rb'"Id":%d,\s*"DebugName"' % oid)
        heads = list(head.finditer(text))
        if len(heads) != 1:
            raise RuntimeError("settings.bin: Objective %d nicht eindeutig" % oid)
        amount = re.compile(rb'("CurrencyType":"PremiumCash",\s*"Amount":)(\d+)')
        m = amount.search(text, heads[0].end())
        nxt = text.find(b'"DebugName"', heads[0].end())
        if m is None or (nxt >= 0 and m.start() > nxt):
            raise RuntimeError("settings.bin: Blings von Objective %d fehlen" % oid)
        text = (text[:m.start(2)] + b"%d" % cv.get("Objectives.%d" % oid, original)
                + text[m.end(2):])
    return text


LEAGUE_FILE = b"GENERALSETTINGS\\SEASONALCOMPETITIONSETTINGS.JSON\x00"
COMPETITION_FILE = b"GENERALSETTINGS\\UBISOFTCOMPETITIONSETTINGS.JSON\x00"
PACK_FILE = b"GENERALSETTINGS\\SPECIALPACKSETTINGS.JSON\x00"
EARLY_HEROES = re.compile(rb',\s*"EarlyHeroAccess":\s*\[[^\]]*\]')
BLING_AMOUNT = re.compile(rb'("CurrencyType":(?:"PremiumCash"|1),\s*"Amount":)(\d+)')


def _mine_text(text, cv):
    for old, new in ((b'"ProductionPeriod":"1h"',
                      b'"ProductionPeriod":"%dh"' % cv["Mine.ProductionHours"]),
                     (b'"Capacity":25,', b'"Capacity":%d,' % cv["Mine.Capacity"])):
        if text.count(old) != 1:
            raise RuntimeError("settings.bin: %r nicht eindeutig" % old)
        text = text.replace(old, new)
    return text


def _sku_text(text, cv):
    """Shop-Preis der Bling-Mine (ältere Stände ohne den Wert: Original)."""
    if "Mine.Price" not in cv:
        return text
    sku = re.compile(rb'"Code":"%s",.*?"Amount":(\d+)' % BLING_MINE_SKU.encode(), re.S)
    m = sku.search(text)
    if m is None or b'"Code"' in text[m.start() + 1:m.start(1)]:
        raise RuntimeError("settings.bin: Preis der Bling-Mine nicht gefunden")
    return text[:m.start(1)] + b"%d" % cv["Mine.Price"] + text[m.end(1):]


def _percent_text(key):
    """Bearbeiter: alle Bling-Beträge mal cv[key] Prozent (ältere Stände
    ohne den Wert: Original)."""
    def edit(text, cv):
        pct = cv.get(key, 100)
        if not BLING_AMOUNT.search(text):
            raise RuntimeError("settings.bin: keine Blings für %s" % key)
        return BLING_AMOUNT.sub(lambda m: m.group(1) + b"%d" % scaled(int(m.group(2)), pct),
                                text)
    return edit


def _pack_text(text, cv):
    """Special Packs ohne frühen Heldenzugang (ab Revision 2)."""
    if cv.get("Revision", 1) < 2:
        return text
    if not EARLY_HEROES.search(text):
        raise RuntimeError("settings.bin: EarlyHeroAccess nicht gefunden")
    return EARLY_HEROES.sub(b"", text)


def settings_bin(original, cv):
    """settings.bin mit den data-Werten cv (Bling-Mine, Objective-, Liga- und
    Wettbewerbs-Blings). Neu gepackt wird ab der ersten geänderten Datei."""
    content, _, _ = settings_archive.read(original)
    edits = sorted((_file_span(content, name), fn) for name, fn in (
        (MINE_FILE, _mine_text), (SKU_FILE, _sku_text), (OBJECTIVE_FILE, _objective_text),
        (LEAGUE_FILE, _percent_text("Leagues.BlingPercent")),
        (COMPETITION_FILE, _percent_text("Competitions.BlingPercent")),
        (PACK_FILE, _pack_text)))
    first = edits[0][0][0]
    tail, pos = b"", first
    for (begin, end), fn in edits:
        tail += content[pos:begin] + fn(content[begin:end], cv)
        pos = end
    return settings_archive.replace_packed(original, first, tail + content[pos:-4])


def mine_rank(spec_id, spec):
    """MineBuildingRankSpec der Bling-Mine mit den eingestellten Werten."""
    if spec is None or spec_id != BLING_MINE or not enabled():
        return spec
    return dict(spec, ProductionPeriod="%dh" % get("Mine", "ProductionHours"),
                ProductionValue=1, Capacity=get("Mine", "Capacity"))


def sku_price(sku):
    """Preis der SKU ({CurrencyType, Amount} oder None), Bling-Mine mit dem
    eingestellten Preis."""
    price = sku.get("Price")
    if sku["Code"] == BLING_MINE_SKU and enabled():
        return dict(price, Amount=get("Mine", "Price"))
    return price


# --- Achievements ------------------------------------------------------------

def achievement_blings(achievement_id):
    """Blings für das Achievement (0, wenn aus)."""
    if not enabled():
        return 0
    return _data["Values"]["Achievements"].get(str(achievement_id), 0)


def ui_achievement_blings():
    """{Id: Blings} für den UI-Patch (leer, wenn aus; ohne Nullen)."""
    if not enabled():
        return {}
    return {int(k): v for k, v in _data["Values"]["Achievements"].items() if v}


# --- Objectives --------------------------------------------------------------

def objective_blings(objective_id, original):
    """Blings für das Objective (original, wenn aus oder ohne Feld)."""
    if not enabled():
        return original
    return _data["Values"].get("Objectives", {}).get(str(objective_id), original)


# --- Liga und Wettbewerbe ----------------------------------------------------

def scaled(amount, percent):
    return int(amount * percent / 100 + 0.5)


def scale_reward(reward, section):
    """Kopie von reward (RewardItems) mit Bling-Beträgen mal
    section.BlingPercent; unverändert, wenn aus."""
    if not reward or not enabled():
        return reward
    pct = get(section, "BlingPercent")
    out = copy.deepcopy(reward)
    for r in out.get("RewardItems") or []:
        a = r.get("CurrencyAmount")
        if a and a.get("CurrencyType") in ("PremiumCash", 1):
            a["Amount"] = scaled(a["Amount"], pct)
    return out


# --- Bling-Shop --------------------------------------------------------------

def shop_prices():
    """{Pack-Id: Blings} der angebotenen Packs (leer, wenn aus)."""
    if not enabled():
        return {}
    return {int(k): v for k, v in _data["Values"]["Shop"].items() if v}
