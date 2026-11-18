"""Statistik (AccountStats, Helden-Stats) und Errungenschaften.

Die Regeln stehen in GeneralSettings/AchievementSettings.json; gezählt
hat der Originalserver. Hier zählt der Server, was EndAttack und die
Mine-Ernte melden, und berechnet den Fortschritt daraus:

  DefeatCastle      AccountStats.CastlesDefeated {CastleDifficulty: n}
  KillEntities      AccountStats.KilledCreatures {Spec: n} (Spinnen,
                    Vampire, Bosse über CreatureIds bzw. Rank "Boss")
  DrinkPotion       AccountStats.TotalPotionsConsumed
  LootItems         AccountStats.TotalItemsLooted
  CurrencyAccum.    AccountStats.CurrencyAccumulation {"IGC": Gold}
  DefeatCastleStr.  Siege in Folge (DefeatCastleStrike, bei Freunden
                    DefeatFriendsCastleStrike gegen Burgen von Freunden)
  KillHeroes        BuildInfo.CastleStats.HeroesKilled (Verteidigung)
  BuildEntities     Kreaturen bzw. Räume in der Burg (aktueller Entwurf)
  ReachLevel        Helden-Level
  FriendsCount      Account.Friends
  Equipment         belegte Ausrüstungsplätze eines Helden

Die Stat-Tabs im Profil zeigen TotalCastlesLooted (Siege),
DefeatCastleStrike, TotalCreaturesKilled, AttackTotalIGCWon, die
Challenge-Werte (bleiben 0) und CastleStats.HeroesKilled.
"""

import datetime
import functools
import glob
import json
import os

import castles
import loot

DIFFICULTY_NAMES = {v: k for k, v in castles.DIFFICULTY.items()}


def _kind(spec):
    return spec["$type"].split(",")[0].split(".")[-1].replace("Achievement", "")


@functools.lru_cache(maxsize=None)
def creature_rank(spec_id):
    """Rank einer Kreatur ("Boss", "Captain", "Elite"; sonst "")."""
    path = glob.glob(os.path.join(loot.SETTINGS, "Creatures", "%06d - *" % spec_id,
                                  "Gameplay.json"))
    if not path:
        return ""
    with open(path[0], encoding="utf-8") as f:
        return next((comp["Rank"] for comp in json.load(f)
                     if isinstance(comp.get("Rank"), str)), "")


def record_attack(account, gains, params):
    """Zählt einen Angriff (keine Validierung) in AccountStats und den
    Helden-Stats; gains aus attack.end_attack."""
    stats = account["Stats"]
    hero = next((h for h in account["Heroes"]
                 if h["HeroSpecContainerId"] == gains["hero"]), {})
    hero_stats = hero.get("Stats") or {}
    won = gains["completion_type"] == 0
    killed = gains["destroyed"]["Creature"]
    n_killed = len(params.get("KilledCreatureIds") or [])

    by_spec = stats.setdefault("KilledCreatures", {})
    for spec, n in killed.items():
        by_spec[str(spec)] = by_spec.get(str(spec), 0) + n
    stats["TotalCreaturesKilled"] = stats.get("TotalCreaturesKilled", 0) + n_killed
    stats["TotalItemsLooted"] = stats.get("TotalItemsLooted", 0) + len(gains["items"])
    stats["AttackTotalIGCWon"] = stats.get("AttackTotalIGCWon", 0) + gains["InGameCoin"]
    add_gold(account, gains["InGameCoin"])
    stats["TotalPotionsConsumed"] = (stats.get("TotalPotionsConsumed", 0)
                                     + len(gains.get("consumables_used") or []))
    if hero_stats:
        hero_stats["TotalCreaturesKilled"] = hero_stats.get("TotalCreaturesKilled", 0) + n_killed
        hero_stats["TimePlayed"] = hero_stats.get("TimePlayed", 0) + round(
            params.get("AttackFrameCount", 0) * params.get("AttackFrameDuration", 0))

    if won:
        name = DIFFICULTY_NAMES[castles.difficulty(gains["castle_level"], gains["hero_level"])]
        defeated = stats.setdefault("CastlesDefeated", {})
        defeated[name] = defeated.get(name, 0) + 1
        stats["TotalCastlesLooted"] = stats.get("TotalCastlesLooted", 0) + 1
        stats["DefeatCastleStrike"] = stats.get("DefeatCastleStrike", 0) + 1
        if any(f["Id"] == gains["castle_id"] for f in account.get("Friends") or []):
            stats["DefeatFriendsCastleStrike"] = stats.get("DefeatFriendsCastleStrike", 0) + 1
        if hero_stats:
            hero_stats["TotalCastlesLooted"] = hero_stats.get("TotalCastlesLooted", 0) + 1
    else:
        stats["DefeatCastleStrike"] = 0
        stats["DefeatFriendsCastleStrike"] = 0


def add_gold(account, amount):
    """Gesammeltes Gold (Angriffe, Minen) für die Greedy-Errungenschaften."""
    acc = account["Stats"].setdefault("CurrencyAccumulation", {})
    acc["IGC"] = acc.get("IGC", 0) + amount


def progress(account, spec):
    """(erreicht, benötigt) einer Errungenschaft."""
    stats = account.get("Stats") or {}
    kind, need = _kind(spec), spec.get("Count", 1)
    if kind == "DefeatCastle":
        got = sum((stats.get("CastlesDefeated") or {}).get(d, 0)
                  for d in spec.get("CastleDifficulties") or [])
    elif kind == "KillEntities":
        killed = stats.get("KilledCreatures") or {}
        if spec.get("CreatureIds"):
            got = sum(killed.get(str(c), 0) for c in spec["CreatureIds"])
        elif spec.get("BossCreaturesOnly"):
            got = sum(n for c, n in killed.items() if creature_rank(int(c)) == "Boss")
        else:
            got = stats.get("TotalCreaturesKilled", 0)
    elif kind == "DrinkPotion":
        got = stats.get("TotalPotionsConsumed", 0)
    elif kind == "LootItems":
        got = stats.get("TotalItemsLooted", 0)
    elif kind == "CurrencyAccumulation":
        got = (stats.get("CurrencyAccumulation") or {}).get(spec.get("CurrencyType", "IGC"), 0)
    elif kind == "DefeatCastleStrike":
        got = stats.get("DefeatFriendsCastleStrike" if spec.get("IsFriend")
                        else "DefeatCastleStrike", 0)
    elif kind == "KillHeroes":
        got = ((account.get("BuildInfo") or {}).get("CastleStats") or {}).get("HeroesKilled", 0)
    elif kind == "BuildEntities":
        rooms = ((account.get("BuildInfo") or {}).get("Draft") or {}).get("Rooms") or []
        got = (len(rooms) if spec.get("EntityType") == "Room"
               else sum(len(r.get("Creatures") or []) for r in rooms))
    elif kind == "FriendsCount":
        got = len(account.get("Friends") or [])
    elif kind == "ReachLevel":
        # je geforderter Held: erreicht, wenn ein passender Held das Level hat
        heroes = account.get("Heroes") or []
        reqs = spec.get("Heroes") or []
        got = sum(any(h.get("Level", 1) >= r["Level"] for h in heroes
                      if r.get("HeroSpecContainerId") in (None, h["HeroSpecContainerId"]))
                  for r in reqs)
        need = len(reqs)
    elif kind == "Equipment":
        parts = spec.get("EquippedParts") or []
        got = max([sum(1 for p in parts if (h.get("Equipment") or {}).get(p))
                   for h in account.get("Heroes") or []] or [0])
        need = len(parts)
    else:
        got = 0
    return min(got, need), need


# Abschlussdaten {Id: Datum}; Account.CompletedAchievements ist im Client
# List<int>, daher nur serverseitig (GetAccountInformation entfernt das Feld)
DATES = "AchievementDates"


def completion_date(account, achievement_id):
    return (account.get(DATES) or {}).get(str(achievement_id))


def complete(account, specs, now=None):
    """Neu erfüllte Errungenschaften als erledigt eintragen (GamerScore
    dazu); liefert [(Id, Punkte)] für die AchievementCompleted-Meldungen."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    done = set(account.get("CompletedAchievements") or [])
    out = []
    for spec in specs:
        if spec["Id"] in done:
            continue
        got, need = progress(account, spec)
        if got >= need:
            account.setdefault("CompletedAchievements", []).append(spec["Id"])
            account.setdefault(DATES, {})[str(spec["Id"])] = now.strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            account["GamerScore"] = account.get("GamerScore", 0) + spec.get("Points", 0)
            out.append((spec["Id"], spec.get("Points", 0)))
    return out
