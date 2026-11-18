"""Trophäen (Kronen) für Angriffe auf Spielerburgen, wie TrophyManager im
Original-Server (HyperQuest.GameServer.dll).

Elo nach TrophiesSettings (Client-Daten: EloC 400, EloK 40,
NumberOfStarsTrophiesModifiers 0.2/0.5/1.0 für 1/2/3 Sterne). Die
Handicaps (HeroHandicapPerLevel, HeroLevelCastleLevelHandicap,
HeroHandicapGainFactor) fehlen in den Client-Daten und stehen auf 0.
Angreifer und Verteidiger ändern sich gegengleich, keiner fällt unter 0.

Je angegriffener Burg merkt sich der Angreifer (account[CASTLES]):
- Gain: Zeitpunkt des letzten Siegs mit Kronen. Solange die Sperre
  (AttackSettings.GainTrophyCooldownTimerDuration) läuft, bringt ein
  weiterer Sieg nur Kronen, wenn er mehr Sterne holt als bisher (Max), und
  nur für die zusätzlichen Sterne.
- Lose: je Held Zeitpunkt der letzten Niederlage mit Kronenverlust; solange
  LoseTrophyCooldownTimerDuration läuft, kostet eine weitere nichts.
- Max: beste Sterne innerhalb der laufenden Gewinn-Sperre.

Nur Spielerburgen zählen; Ubisoft-Burgen bringen und kosten nichts. Die
Ersatzspieler haben keinen echten Punktestand; ihrer richtet sich nach
dem Burg-Level (40 je Level über 1, plus eine feste Streuung je Burg).
"""

import datetime
import functools
import json
import os
import re

import castles
import loot


def castle_score(c):
    """Kronen des Burgbesitzers (Ersatzspieler: aus dem Burg-Level)."""
    if castles.castle_type(c) != castles.CASTLE_TYPE_USER:
        return 0
    if "TrophyScore" in c:
        return c["TrophyScore"]
    return max(0, 40 * (c.get("Level", 1) - 1) + c.get("AccountId", 0) % 21 - 10)


# Angreifer-Account: {Burg-Id: {"Gain": Zeit, "Lose": {Held: Zeit}, "Max": Sterne}}
CASTLES = "TrophyCastles"
COOLDOWNS = "TrophyCooldowns"  # alt: {Burg-Id: Zeit des letzten Siegs}
NEVER = "2015-01-01T00:00:00Z"


@functools.lru_cache(maxsize=None)
def settings():
    with open(os.path.join(loot.SETTINGS, "GeneralSettings", "TrophiesSettings.json"),
              encoding="utf-8-sig") as f:
        s = json.load(f)
    s.setdefault("HeroHandicapPerLevel", 0)
    s.setdefault("HeroLevelCastleLevelHandicap", 0)
    s.setdefault("HeroHandicapGainFactor", 0)
    s.setdefault("MaxGameHeroLevel", len(loot.xp_per_level()))
    return s


def _seconds(span):
    units = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * units[u.lower()] for n, u in re.findall(r"(\d+)([wdhmsWDHMS])", span))


def _cooldown(name):
    return datetime.timedelta(seconds=_seconds(loot.attack_settings().get(name, "1d")))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _active(stamp, name, now=None):
    """IsTrophyCooldownTimerActive: Zeitpunkt liegt zurück, Dauer noch nicht um."""
    if not stamp:
        return False
    now = now or _now()
    return _parse(stamp) < now and now - _parse(stamp) < _cooldown(name)


def record(account, castle_id):
    """Eintrag des Angreifers zu dieser Burg (Kopie; alte Siege aus
    COOLDOWNS übernommen)."""
    r = dict((account.get(CASTLES) or {}).get(str(castle_id)) or {})
    old = (account.get(COOLDOWNS) or {}).get(str(castle_id))
    if old and not r.get("Gain"):
        r["Gain"] = old
    r.setdefault("Lose", {})
    r.setdefault("Max", 0)
    return r


def gain_cooldown(account, castle_id):
    """(Start der Gewinn-Sperre oder None, beste Sterne in ihr) –
    CastleInfoSummary.TrophyCooldownTimer/VictoryConditionLevel."""
    r = record(account, castle_id)
    if _active(r.get("Gain"), "GainTrophyCooldownTimerDuration"):
        return r["Gain"], r["Max"]
    return None, 0


def _elo(account, defender_score, hero_level, castle_level, stars, previous):
    """GetTrophyScoreVariation: (Änderung Angreifer, Änderung Verteidiger)."""
    s = settings()
    max_hero = max([h.get("Level", 1) for h in account.get("Heroes") or []] or [hero_level])
    gap = max_hero - hero_level
    attacker = max(0, account.get("TrophyScore", 0) - gap * s["HeroHandicapPerLevel"])
    defender = defender_score - (hero_level - castle_level) * s["HeroLevelCastleLevelHandicap"]
    expectation = 1 / (1 + 10 ** ((defender - attacker) / s["EloC"]))
    factor = 1 - gap / (s["MaxGameHeroLevel"] - 1) * s["HeroHandicapGainFactor"]
    if stars == 0:
        change = -s["EloK"] * expectation * factor
    else:
        mods = s["NumberOfStarsTrophiesModifiers"]
        modifier = (1.0 if stars < previous else
                    mods[stars - 1] - (mods[previous - 1] if previous > 0 else 0))
        change = modifier * s["EloK"] * (1 - expectation) * factor
    return round(change), round(-change)  # round: wie MidpointRounding.ToEven


def _hero_level(account, hero_id):
    hero = next((h for h in account.get("Heroes") or []
                 if h["HeroSpecContainerId"] == hero_id), None)
    return hero["Level"] if hero else 1


def variation(account, c, hero_id=None):
    """Vorschau für Burgfenster und AttackInfo wie GetAttackTrophyScoreVariation:
    (Gewinn bei 3 Sternen, Verlust bei Niederlage, Verlust ohne Sperre),
    Verluste als positive Zahl."""
    if castles.castle_type(c) != castles.CASTLE_TYPE_USER:
        return 0, 0, 0
    hero_id = hero_id or account.get("SelectedHeroId")
    level = _hero_level(account, hero_id)
    r = record(account, c.get("AccountId"))
    gain_on = _active(r.get("Gain"), "GainTrophyCooldownTimerDuration")
    lose_on = _active(r["Lose"].get(str(hero_id)), "LoseTrophyCooldownTimerDuration")
    score = account.get("TrophyScore", 0)
    if not gain_on:
        win = _elo(account, castle_score(c), level, c["Level"], 3, 0)[0]
    elif 3 > r["Max"]:
        win = _elo(account, castle_score(c), level, c["Level"], 3, r["Max"])[0]
    else:
        win = 0
    lose_free = min(-_elo(account, castle_score(c), level, c["Level"], 0, 0)[0], score)
    return win, 0 if lose_on else lose_free, lose_free


def lose_cooldown(account, castle_id, hero_id):
    """Start der Verlust-Sperre dieses Helden gegen die Burg oder None."""
    stamp = record(account, castle_id)["Lose"].get(str(hero_id))
    return stamp if _active(stamp, "LoseTrophyCooldownTimerDuration") else None


def settle(account, c, hero_id, stars):
    """Kronen nach dem Angriff wie TrophyManager.OnEndAttackContribution:
    (Änderung Angreifer, Änderung Verteidiger, neuer Burg-Eintrag). Beide
    gedeckelt, sodass keiner unter 0 fällt."""
    now = _now()
    level = _hero_level(account, hero_id)
    r = record(account, c.get("AccountId"))
    gain_on = _active(r.get("Gain"), "GainTrophyCooldownTimerDuration", now)
    lose_on = _active(r["Lose"].get(str(hero_id)), "LoseTrophyCooldownTimerDuration", now)
    previous = r["Max"]
    change = (0, 0)
    if stars == 0:
        if not lose_on:
            change = _elo(account, castle_score(c), level, c["Level"], 0, 0)
            r["Lose"] = dict(r["Lose"], **{str(hero_id): _stamp(now)})
    elif gain_on:
        if stars > previous:
            change = _elo(account, castle_score(c), level, c["Level"], stars, previous)
    else:
        change = _elo(account, castle_score(c), level, c["Level"], stars, 0)
        r["Gain"] = _stamp(now)
    if not gain_on or stars >= previous:
        r["Max"] = stars
    attacker = max(change[0], -account.get("TrophyScore", 0))
    defender = max(change[1], -castle_score(c))
    return attacker, defender, r


def attack_bonus(account):
    """AttackBonus der Unterliga des Angreifers (z. B. 0.09 = +9 % Gold und
    Lebenskraft aus Kreaturen; Original: SeasonalCompetitionManager.
    GetAttackBonus, LootManager.SeparateLootAmount)."""
    league = ((account or {}).get("LeagueId"), (account or {}).get("SubLeagueId"))
    for lg in league_settings()["Leagues"]:
        for sub in lg["SubLeagues"]:
            if (lg["Id"], sub["Id"]) == league:
                return sub.get("AttackBonus", 0.0)
    return 0.0


@functools.lru_cache(maxsize=None)
def league_settings():
    """SeasonalCompetitionSettings der Client-Daten (Ligen, Saisonplan)."""
    path = os.path.join(loot.SETTINGS, "GeneralSettings",
                        "SeasonalCompetitionSettings.json")
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def league_of(score):
    """(LeagueId, SubLeagueId) zu einem Kronenstand: die Unterliga, deren
    ScoreFrom..ScoreTo ihn enthält (Unranked 1/1 ab 0, Boss offen nach
    oben)."""
    for league in league_settings()["Leagues"]:
        for sub in league["SubLeagues"]:
            if sub.get("ScoreFrom", 0) <= score <= sub.get("ScoreTo", score):
                return league["Id"], sub["Id"]
    return 1, 1


def account_league(a):
    """(LeagueId, SubLeagueId) eines Accounts: die für die Saison
    festgelegte Liga (nur am Saisonende neu, leagues.settle); Ersatzspieler
    und Accounts ohne Liga nach ihren Kronen."""
    if a.get("LeagueId"):
        return a["LeagueId"], a.get("SubLeagueId", 1)
    return league_of(a.get("TrophyScore", 0))
