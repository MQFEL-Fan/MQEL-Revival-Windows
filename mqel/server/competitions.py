"""Wöchentliche Zeitrennen auf Ubisoft-Burgen (UbisoftCompetitionService).

UbisoftCompetitionSettings: ab CompetitionReferenceDate läuft je
CompetitionDuration (eine Woche) eine Periode aus CompetitionSchedule
reihum, je Burg ein Wettbewerb. Gewertet wird die Bestzeit bis zur
Schatzkammer (ms) je Spieler; die Ersten bekommen nach Ende
AttackerRewardTable (Edelsteine) samt News, abgerechnet beim nächsten
CheckEndedUbisoftCompetitions des Spielers.

Id eines Wettbewerbs = Wochennummer * 1000 + Burg-Id (Burg-Ids < 1000).
Datei: state/<Profil>/competitions.json {Id: {AccountId: Bestzeit-ms}}.
"""

import datetime
import functools
import json
import os
import threading

import balance
import castles
import loot
import profiles

T = castles.T
SETTLED = "SettledCompetitions"  # Account-Feld: abgerechnete Wettbewerbs-Ids
# NewsType (Enum des Clients)
NEWS_NO_REWARDS, NEWS_REWARDS_WON = 13, 14


def _typed(item):
    """RewardItem mit $type auch am CurrencyAmount (Settings haben keins)."""
    if "CurrencyAmount" not in item:
        return item
    return {**item, "CurrencyAmount": {"$type": T("CurrencyAmount"), **item["CurrencyAmount"]}}


@functools.lru_cache(maxsize=None)
def settings():
    path = os.path.join(loot.SETTINGS, "GeneralSettings", "UbisoftCompetitionSettings.json")
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _ref():
    return datetime.datetime.fromisoformat(
        settings()["CompetitionReferenceDate"].replace("Z", "+00:00"))


def week(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return int((now - _ref()).total_seconds() // settings()["CompetitionDuration"])


def refreshed(player, now=None):
    """GlobalNotifications für die nächste Antwort: CompetitionsRefreshed
    nach dem Login und bei jedem Wochenwechsel. Darauf ruft der Client
    CheckEndedUbisoftCompetitions auf (sonst nie; im Spiel bestätigt)."""
    w = week(now)
    if player.competitions_week == w:
        return []
    player.competitions_week = w
    return [{"$type": T("CompetitionsRefreshedNotification"),
             "Id": "%024x" % w, "NotificationType": "CompetitionsRefreshed"}]


def castle_ids(w):
    periods = settings()["CompetitionSchedule"]["Periods"]
    return periods[w % len(periods)]["CastleIds"]


def current_ids(now=None):
    """{Burg-Id: Wettbewerbs-Id} der laufenden Woche."""
    w = week(now)
    return {cid: w * 1000 + cid for cid in castle_ids(w)}


def split(competition_id):
    """(Woche, Burg-Id) oder None, wenn die Id keinen Wettbewerb benennt."""
    w, cid = divmod(int(competition_id or 0), 1000)
    return (w, cid) if w > 0 and cid in castle_ids(w) else None


def remaining_seconds(w, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    end = _ref() + datetime.timedelta(seconds=(w + 1) * settings()["CompetitionDuration"])
    return max(0, int((end - now).total_seconds()))


def reward(rank, participants):
    """Reward für Platz `rank` (1-basiert) bei `participants` Teilnehmern."""
    for tier in settings()["AttackerRewardTable"]:
        if tier["MinParticipantCount"] <= participants <= tier["MaxParticipantCount"]:
            rewards = tier["RewardsByAttackerRank"]
            if not 0 < rank <= len(rewards):
                return None
            r = balance.scale_reward(rewards[rank - 1], "Competitions")
            # Ohne $type verwirft der Client-Leser das Objekt (Spalte "Reward" leer)
            return {"$type": T("Reward"), **r,
                    "RewardItems": [_typed(i) for i in r.get("RewardItems") or []]}
    return None


def _min_participants():
    return min(t["MinParticipantCount"] for t in settings()["AttackerRewardTable"])


class Competitions:
    def __init__(self, path, log=print):
        self.path, self.log = path, log
        self.lock = threading.Lock()
        self.data = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def _save(self):
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)

    def ranking(self, competition_id):
        """[(AccountId, ms)] nach Bestzeit."""
        times = self.data.get(str(competition_id)) or {}
        return sorted(((int(a), ms) for a, ms in times.items()), key=lambda x: (x[1], x[0]))

    def record(self, competition_id, account_id, ms, now=None):
        """Sieg in einem laufenden Wettbewerb werten. Liefert
        {valid, best_ms, new_leader}; nicht laufende Ids zählen nicht."""
        parts = split(competition_id)
        if not parts or parts[0] != week(now) or ms <= 0:
            return {"valid": False, "best_ms": 0, "new_leader": False}
        with self.lock:
            leader = (self.ranking(competition_id) or [(None, 0)])[0][0]
            times = self.data.setdefault(str(competition_id), {})
            old = times.get(str(account_id))
            if old is None or ms < old:
                times[str(account_id)] = ms
                self._save()
            best = times[str(account_id)]
            new_leader = (self.ranking(competition_id)[0][0] == account_id
                          and leader != account_id)
        self.log(f"    [state] Wettbewerb {competition_id}: {ms} ms, Bestzeit {best} ms"
                 + (", neuer Erster" if new_leader else ""))
        return {"valid": True, "best_ms": best, "new_leader": new_leader}

    def _entry(self, rank, account, ms, participants, friend_ids, header):
        return {"$type": T("UbisoftCompetitionLeaderboardEntry"),
                "AccountSummary": profiles.account_summary(account, header(account["AccountId"])),
                "IsFriend": account["AccountId"] in friend_ids,
                "Rank": rank, "Score": ms,
                "Reward": reward(rank, participants)}

    def info(self, competition_id, me, players, header, now=None):
        """UbisoftCompetitionInfo für den Spieler `me` (Snapshot);
        players: Snapshots aller Spieler. None bei unbekannter Id."""
        parts = split(competition_id)
        if not parts:
            return None
        w, cid = parts
        c = castles.find_castle(cid) or {}
        by_id = {a["AccountId"]: a for a in players}
        ranking = [(a, ms) for a, ms in self.ranking(competition_id) if a in by_id]
        n = len(ranking)
        friend_ids = {f["Id"] for f in me.get("Friends") or []}
        entries = [self._entry(i, by_id[a], ms, n, friend_ids, header)
                   for i, (a, ms) in enumerate(ranking, 1)]
        mine = next((e for e in entries if e["AccountSummary"]["Id"] == me["AccountId"]), None)
        tiers = settings()["AttackerRewardTable"]
        return {"$type": T("UbisoftCompetitionInfo"),
                "UbisoftCompetitionId": int(competition_id),
                "CastleId": cid, "CastleLevel": c.get("Level", 1),
                "CastleName": c.get("AccountDisplayName", ""),
                "CastleType": castles.CASTLE_TYPE_UBISOFT,
                "OasisNameId": c.get("OasisName", 0),
                "BestScore": entries[0]["Score"] if entries else 0,
                "CurrentUserLeaderboardEntry": mine,
                "GlobalLeaderboard": entries[:settings()["MaxLeaderboardEntries"]],
                "FriendLeaderboard": [e for e in entries
                                      if e["IsFriend"] or e is mine],
                "MaxReward": reward(1, max(n, 1)) if tiers else None,
                "MinParticipantRequired": _min_participants(),
                "ParticipantCount": n,
                "RemainingTime": remaining_seconds(w, now),
                "UbisoftCompetitionWasEnded": w < week(now)}

    def settle(self, me, header, now=None):
        """Beendete Wettbewerbe, an denen `me` teilgenommen hat und die noch
        nicht abgerechnet sind: {Ids, Rewards [Reward], News [NewsData]}."""
        done = set(me.get(SETTLED) or [])
        current = week(now)
        out = {"Ids": [], "Rewards": [], "News": []}
        for key in list(self.data):
            parts = split(key)
            if not parts or parts[0] >= current or int(key) in done:
                continue
            ranking = [a for a, _ in self.ranking(key)]
            if me["AccountId"] not in ranking:
                continue
            rank = ranking.index(me["AccountId"]) + 1
            won = reward(rank, len(ranking))
            c = castles.find_castle(parts[1]) or {}
            out["Ids"].append(int(key))
            if won:
                out["Rewards"].append(won)
            out["News"].append({
                "$type": T("CompetitionEndedRewardsWonNewsData" if won
                           else "CompetitionEndedNoRewardsNewsData"),
                "Type": NEWS_REWARDS_WON if won else NEWS_NO_REWARDS,
                "RequiresUserAction": False, "Rank": rank,
                "UbisoftCompetitionId": int(key),
                "DisplayNameOasisId": c.get("OasisName", 0),
                "CastleAccountSummary": castles.castle_summary(c)["DefenderAccountSummary"]
                if c else None})
        return out
