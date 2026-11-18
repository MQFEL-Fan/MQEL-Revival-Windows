"""Angriffsstatistik je Spielerburg (alle Angreifer zusammen).

Daraus die Burgvorschau: "Castle's Win" (Siegquote der Burg = Anteil der
Angriffe, die sie abgewehrt hat) samt Schwierigkeit nach
CastleSettings.CastleWinRatioDifficultyTable, Angriffszahlen und die
mittlere Dauer erfolgreicher Angriffe. Test-Angriffe und Validierungen
zählen nicht. Dazu der letzte Kommentar eines Angreifers (RateCastle),
den Angriffsauswahl und EndAttack als LastComment zeigen.
Datei: state/<Profil>/castle_stats.json.
"""

import functools
import json
import os
import threading

import loot
from profanity import filter_text

# CastleWinRatioDifficulty: None 0, Easy 1, Medium 2, Hard 3
_DIFFICULTIES = ["None", "Easy", "Medium", "Hard"]


@functools.lru_cache(maxsize=None)
def _settings():
    path = os.path.join(loot.SETTINGS, "GeneralSettings", "CastleSettings.json")
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def difficulty(ratio):
    """CastleWinRatioDifficulty zu einer Siegquote der Burg."""
    table = _settings()["CastleWinRatioDifficultyTable"]
    for i, name in enumerate(_DIFFICULTIES[1:], 1):
        row = table[name]
        if row.get("WinRatioFrom", 0) <= ratio < row.get("WinRatioTo", 1) or (
                ratio >= 1 and row.get("WinRatioTo") == 1):
            return i
    return 0


class CastleStats:
    def __init__(self, path, log=print):
        self.path, self.log = path, log
        self.lock = threading.Lock()
        self.data = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def _entry(self, castle_id):
        s = self.data.setdefault(str(castle_id), {})
        for k in ("Attacks", "CastleWins", "WinDurationMs"):
            s.setdefault(k, 0)
        return s

    def _save(self):
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)

    def record(self, castle_id, castle_won, duration_ms):
        """Einen Angriff zählen; duration_ms nur bei Sieg des Angreifers."""
        with self.lock:
            s = self._entry(castle_id)
            s["Attacks"] += 1
            if castle_won:
                s["CastleWins"] += 1
            else:
                s["WinDurationMs"] += int(duration_ms)
            self._save()
        self.log(f"    [state] Burg {castle_id}: {s['CastleWins']}/{s['Attacks']} abgewehrt")

    def comment(self, castle_id, attack_id, account_id, avatar_id, text):
        """Kommentar zur Burg merken (ersetzt den vorigen)."""
        with self.lock:
            self._entry(castle_id)["LastComment"] = {
                "AttackId": attack_id, "AccountId": account_id,
                "AvatarId": avatar_id, "Raw": text}
            self._save()
        self.log(f"    [state] Burg {castle_id}: Kommentar von {account_id}: {text!r}")

    def last_comment(self, castle_id, T, filtered=False):
        """CastleAttackComment für LastComment, oder None; filtered: für
        Betrachter mit Schimpfwortfilter (das Original filterte beim
        Speichern nach der Option des Burgbesitzers)."""
        c = (self.data.get(str(castle_id)) or {}).get("LastComment")
        return c and {"$type": T("CastleAttackComment"), "AttackId": c["AttackId"],
                      "AccountId": c["AccountId"], "AvatarId": c["AvatarId"],
                      "Comment": {"$type": T("ProfanityProofCastleComment"),
                                  "Raw": filter_text(c["Raw"]) if filtered else c["Raw"]}}

    def info(self, castle_id):
        """Felder für CastleInfo: Zahlen, Siegquote, Schwierigkeit,
        mittlere Siegdauer (ms). Ohne Angriffe: Standardquote."""
        s = self.data.get(str(castle_id))
        if not s or not s["Attacks"]:
            default = _settings()["WinRatioDefaultValue"]
            return {"AttackCount": 0, "SuccessfulAttackCount": 0,
                    "WinRatio": default, "WinRatioDifficulty": difficulty(default),
                    "AverageDuration": 0}
        ratio = s["CastleWins"] / s["Attacks"]
        won = s["Attacks"] - s["CastleWins"]
        return {"AttackCount": s["Attacks"], "SuccessfulAttackCount": won,
                "WinRatio": round(ratio, 4), "WinRatioDifficulty": difficulty(ratio),
                "AverageDuration": s["WinDurationMs"] // won if won else 0}
