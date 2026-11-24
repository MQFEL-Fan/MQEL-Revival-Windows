"""Yearly in-game event calendar (community events), every year again.

The game data has two kinds of community events besides the hero trials
(free_trials.py) and the seasonal shop articles (patcher.seasonal_event):

* Boost events (CommunityEventBoostSettings, ids 21-26): +100 % gold,
  life force, XP, magic find, bling mine, or material mines twice as fast.
  Ubisoft ran them on weekends (Fri 17:00 to Mon 05:00 UTC, e.g.
  2015-02-20, all six at once; DimCommunityEvent.csv of the 2015 data).
* Loot event 1 "More Materials" (CommunityEventLootSettings), 2014-07-01
  10:00 to 2014-09-25 22:00 UTC.

Calendar here (UTC, no admin needed):
* Boost weekend every month: the weekend of the third Friday, Fri 17:00 to
  Mon 05:00. The boost rotates by month: Jan gold, Feb life force, Mar XP,
  Apr magic find, May bling mine, Jun material mines, Jul gold ... One
  "Everything x2" weekend a year (all six at once, like February 2015): the
  third weekend of December.
* "More Materials": every year Jul 1 10:00 to Sep 25 22:00 (original dates).

The launcher gets the dates in settings2.bin (patcher.settings2, version
parts .E<key> and .M<year>); the client shows the event and the server
applies it: attack rewards (attack_factors), gold/life force/bling mines
(mine_factor), material mines (material_period_factor) and loot
(more_materials).
"""

import datetime
import functools
import json
import os

from loot import SETTINGS

UTC = datetime.timezone.utc
# boost event ids in the game data, in rotation order
ROTATION = (21, 22, 23, 24, 25, 26)
ALL_BOOSTS_MONTH = 12      # third weekend of December: all six boosts
BOOST_NAMES = {21: "Gold", 22: "Life force", 23: "XP", 24: "Magic find",
               25: "Bling mine", 26: "Material mines"}
LOOT_WINDOW = ((7, 1, 10), (9, 25, 22))  # (month, day, hour) start / end
MORE_MATERIALS = 2.0       # material drops x2 during "More Materials"

# per game_server.py --boost-event erzwungenes Event (Test): Boost-Id
# (21-26) oder 0 = alle; läuft ab jetzt 2 Tage
FORCED_BOOST = None


def _load(name):
    with open(os.path.join(SETTINGS, "CommunityEventSettings", name), encoding="utf-8-sig") as f:
        return json.load(f)


@functools.lru_cache(maxsize=1)
def boost_specs():
    """{Id: BoostCommunityEvent} from the game data."""
    return {e["Id"]: e for e in _load("CommunityEventBoostSettings.json")["BoostCommunityEvents"]}


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def boost_window(year, month):
    """(start, end) of the month's boost weekend: third Friday 17:00 to
    Monday 05:00 UTC."""
    first = datetime.date(year, month, 1)
    friday = first + datetime.timedelta(days=(4 - first.weekday()) % 7 + 14)
    start = datetime.datetime.combine(friday, datetime.time(17, 0), UTC)
    return start, start + datetime.timedelta(days=2, hours=12)


def boosts_of(month):
    """Boost ids of the month's weekend."""
    if month == ALL_BOOSTS_MONTH:
        return list(ROTATION)
    return [ROTATION[(month - 1) % len(ROTATION)]]


def boost_key(start, ids):
    """Version key of a boost weekend: start day and the boost (0 = all),
    e.g. 2026112021; fits in 32 bits, from_key restores it."""
    return int(start.strftime("%Y%m%d")) * 100 + (0 if len(ids) > 1 else ids[0])


def from_key(key):
    day, boost = divmod(int(key), 100)
    if boost and boost not in ROTATION:
        raise ValueError("boost event %d: unknown boost" % key)
    date = datetime.datetime.strptime(str(day), "%Y%m%d").date()
    if FORCED_BOOST is not None:
        start = datetime.datetime.combine(date, datetime.time(0, 0), UTC)
        end = start + datetime.timedelta(days=2)
    else:
        start, end = boost_window(date.year, date.month)
        if start.date() != date:
            raise ValueError("boost event %d: not a boost weekend" % key)
    ids = [boost] if boost else list(ROTATION)
    return {"Key": int(key), "Ids": ids, "Start": start, "End": end}


def boost_event(now):
    """Boost weekend running at `now` (datetime, UTC) or None:
    {"Key", "Ids", "Start", "End"}."""
    if FORCED_BOOST is not None:
        ids = [FORCED_BOOST] if FORCED_BOOST else list(ROTATION)
        start = datetime.datetime.combine(now.date(), datetime.time(0, 0), UTC)
        return {"Key": boost_key(start, ids), "Ids": ids, "Start": start,
                "End": start + datetime.timedelta(days=2)}
    start, end = boost_window(now.year, now.month)
    if not start <= now < end:
        return None
    ids = boosts_of(now.month)
    return {"Key": boost_key(start, ids), "Ids": ids, "Start": start, "End": end}


def loot_window(year):
    (m1, d1, h1), (m2, d2, h2) = LOOT_WINDOW
    return (datetime.datetime(year, m1, d1, h1, tzinfo=UTC),
            datetime.datetime(year, m2, d2, h2, tzinfo=UTC))


def more_materials(now):
    """True while "More Materials" runs."""
    start, end = loot_window(now.year)
    return start <= now < end


def _specs(now):
    event = boost_event(now)
    return [boost_specs()[i] for i in event["Ids"]] if event else []


def _field(spec, name):
    return float(spec.get(name) or 0)


def attack_factors(now):
    """Extra factors for an attack like the boost potions
    (AccountState.BOOST_FIELDS keys): {"Gold": 1, ...}."""
    out = {}
    for s in _specs(now):
        for key, field in (("Gold", "AttackIncreasedGold"), ("LifeForce", "AttackIncreasedLifeForce"),
                           ("Xp", "IncreasedXp"), ("MagicFind", "IncreasedChance")):
            if _field(s, field):
                out[key] = out.get(key, 0) + _field(s, field)
    return out


MINE_FIELDS = {5: "MineIncreasedGold", 6: "MineIncreasedLifeForce", 16: "MineIncreasedPremiumCash"}


def mine_factor(building_spec, now):
    """Production factor of a gold (5), life force (6) or bling (16) mine at
    `now` (1 = normal, 2 = boost +100 %)."""
    field = MINE_FIELDS.get(building_spec)
    return 1 + sum(_field(s, field) for s in _specs(now)) if field else 1


def material_period_factor(now):
    """Production period factor of the material mines (Material-O-Matic) at
    `now` (0.5 during their boost)."""
    f = 1.0
    for s in _specs(now):
        if s.get("MineProductionPeriodModifier"):
            f *= float(s["MineProductionPeriodModifier"])
    return f


# --- settings2.bin (patcher) --------------------------------------------------

def boost_settings_json(event):
    """CommunityEventBoostSettings with the event's boosts in its window
    (CRLF like settings2.bin); other boosts keep their 2013/2015 dates."""
    data = _load("CommunityEventBoostSettings.json")
    for e in data["BoostCommunityEvents"]:
        if event and e["Id"] in event["Ids"]:
            e["EventStartTime"], e["EventEndTime"] = iso(event["Start"]), iso(event["End"])
    return json.dumps(data, indent=4).replace("\n", "\r\n")


def loot_settings_json(year):
    """CommunityEventLootSettings with "More Materials" in `year`."""
    data = _load("CommunityEventLootSettings.json")
    start, end = loot_window(year)
    for e in data["LootCommunityEvents"]:
        if e["Id"] == 1:
            e["EventStartTime"], e["EventEndTime"] = iso(start), iso(end)
    return json.dumps(data, indent=4).replace("\n", "\r\n")


def calendar(year):
    """[(start, end, name)] of the year's events (website, admin, docs)."""
    out = []
    for month in range(1, 13):
        start, end = boost_window(year, month)
        ids = boosts_of(month)
        name = ("Everything x2 weekend" if len(ids) > 1
                else "%s boost weekend" % BOOST_NAMES[ids[0]])
        out.append((start, end, name))
    start, end = loot_window(year)
    out.append((start, end, "More Materials"))
    return sorted(out)
