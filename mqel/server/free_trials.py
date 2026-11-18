"""Helden zum Probespielen (Hero Free Trial), wie im finalen Client.

Ein Trial ist ein Community-Event (CommunityEventFreeTrialSettings in
settings2.bin): im Zeitfenster bekommt jeder Spieler die Helden des Events,
die er noch nicht besitzt, mit Hero.ExpirationDate = Eventende
(FreeTrialActivatedNotification, Regel aus FreeTrialManager.TryUnlockHero).
Ziele (PriceReductionConditions, z. B. Heldenlevel 5) senken den Kaufpreis;
erreichte stehen in Hero.PriceReductionIds
(FreeTrialPriceConditionCompleted). Gekauft wird wie sonst per BuyCommand.

Termine: jeden Monat Tag 1-7 (DAYS) ein Held, reihum Ritter, Bogenschützin,
Magier, Runaway; game_server.py --free-trial <Held-Id> erzwingt ein Event
ab heute (Test). Der Launcher holt die Event-Daten beim Start
(patcher.settings2), der Server schaltet nach denselben Daten frei.
"""

import datetime
import functools
import json
import os

from loot import SETTINGS

HEROES = {2: "Knight", 3: "Archer", 4: "Mage", 5: "Runaway"}
ROTATION = (2, 3, 4, 5)
DAYS = 7  # Länge eines Events; reihum jeweils ab dem Monatsersten
# Ziele des Original-Events (Heldenlevel 5/10/12/15, zusammen 650 Blings)
CONDITION_IDS = (1, 2, 3, 4)

# per game_server.py --free-trial erzwungener Held (sonst nach Datum) und
# optional dessen Ende (--free-trial-minutes, Test des Ablaufs)
FORCED_HERO = None
FORCED_END = None


def _settings():
    with open(os.path.join(SETTINGS, "CommunityEventSettings",
                           "CommunityEventFreeTrialSettings.json"), encoding="utf-8-sig") as f:
        return json.load(f)


@functools.lru_cache(maxsize=1)
def conditions():
    """{Id: PriceReductionCondition} aus den Spieldaten."""
    return {c["Id"]: c for c in _settings()["PriceReductionConditions"]}


def event_id(start, hero):
    """Id eines Events: Beginn (JJJJMMTT) und Held, z. B. 202611013; passt in
    32 Bit und trägt alles, um das Event wiederherzustellen (from_id)."""
    return int(start.strftime("%Y%m%d")) * 10 + hero


def from_id(event_id_):
    """Event zur Id (event_id); ValueError bei unbekanntem Helden."""
    day, hero = divmod(event_id_, 10)
    if hero not in HEROES:
        raise ValueError("Trial %d: unbekannter Held" % event_id_)
    start = datetime.datetime.strptime(str(day), "%Y%m%d").date()
    end = start + datetime.timedelta(days=DAYS - 1)
    utc = datetime.timezone.utc
    end = datetime.datetime.combine(end, datetime.time(23, 59, 59), utc)
    if FORCED_END and hero == FORCED_HERO:
        end = FORCED_END
    return {"Id": event_id_, "Hero": hero,
            "Start": datetime.datetime.combine(start, datetime.time(0, 0), utc),
            "End": end}


def current(today, forced=None):
    """Laufendes Event am Tag `today` oder None:
    {"Id", "Hero", "Start", "End"} (Start/End als datetime, UTC)."""
    forced = forced or FORCED_HERO
    if forced:
        return from_id(event_id(today, int(forced)))
    if today.day > DAYS:
        return None
    months = today.year * 12 + today.month - 1
    return from_id(event_id(today.replace(day=1), ROTATION[months % len(ROTATION)]))


def active(now):
    """Event, das zum Zeitpunkt `now` (datetime, UTC) läuft, oder None."""
    event = current(now.date())
    return event if event and event["Start"] <= now <= event["End"] else None


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def settings_json(event):
    """CommunityEventFreeTrialSettings mit genau diesem Event (Text wie in
    settings2.bin, CRLF)."""
    data = _settings()
    data["HeroFreeTrialCommunityEvents"] = [{
        "HeroSpecContainerIds": [event["Hero"]],
        "IconUrl": "freeTrial/heroes/%s.png" % HEROES[event["Hero"]],
        "PriceReductionConditionIds": list(CONDITION_IDS),
        "Id": event["Id"],
        "DebugName": "%s free trial" % HEROES[event["Hero"]],
        "EventStartTime": iso(event["Start"]),
        "EventEndTime": iso(event["End"])}]
    return json.dumps(data, indent=4).replace("\n", "\r\n")


def reached(hero, condition):
    """Hat der Probe-Held das Ziel erreicht? Nur Heldenlevel-Ziele; Burgen
    plündern/Kreaturen töten nutzt kein Event der Spieldaten."""
    if condition["$type"].split(",")[0].endswith("HeroLevelUpPriceReductionContition"):
        return hero["Level"] >= condition["Level"]
    return False


def price_reduction(hero, currency_name):
    """Summe der erreichten Rabatte des Helden in dieser Währung."""
    conds = conditions()
    return sum(r["Amount"] for cid in hero.get("PriceReductionIds") or []
               for r in conds.get(cid, {}).get("PriceReduction", [])
               if r["CurrencyType"] == currency_name)
