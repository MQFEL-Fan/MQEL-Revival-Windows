"""Replays der Angriffe auf Spielerburgen (Kampfprotokoll, „Ansehen“).

Der Client zeichnet jeden Angriff auf und hängt die Aufzeichnung an
EndAttack hinter das JSON (ReplayController::StoreReplay, 0xdee700):
4 Byte Originalgröße, danach LZO-komprimiert. Der Verteidiger startet sie
über game://replay/start?attackId=… im Verteidigungslog
(DefendLogEntry.HasReplay); der Client ruft dann
ReplayService.GetReplay(attackId) und nimmt die Antwort als Stream im
selben Format (HandleGetReplayCalls, 0xdef100: entpacken, Größe prüfen),
danach StartReplayAttack(attackId) -> AttackInfo wie bei StartAttack. Die
Aufzeichnung enthält nur die Eingaben; Burg und Held müssen dem Stand beim
Angriff entsprechen, sonst bricht die Simulation ab ("The determinism has
been broken"). Daher wird die AttackInfo von StartAttack mitgespeichert."""
import json
import os
import re

_ID = re.compile(r"^[0-9a-fA-F]{24}$")  # BSON-ObjectId (AttackId)


class Replays:
    def __init__(self, directory):
        self.dir = directory

    def _path(self, attack_id):
        if not _ID.match(attack_id or ""):
            return None
        return os.path.join(self.dir, attack_id.lower() + ".hqr")

    def store(self, attack_id, data, attack_info):
        """Aufzeichnung und AttackInfo speichern; False, wenn nichts zu
        speichern ist."""
        path = self._path(attack_id)
        if not path or len(data) <= 4 or not attack_info:
            return False
        os.makedirs(self.dir, exist_ok=True)
        for target, content in ((path, data), (self._info_path(path),
                                json.dumps(attack_info).encode("utf-8"))):
            with open(target + ".tmp", "wb") as f:
                f.write(content)
            os.replace(target + ".tmp", target)
        return True

    @staticmethod
    def _info_path(path):
        return path[:-len(".hqr")] + ".json"

    def load(self, attack_id):
        path = self._path(attack_id)
        if not path or not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def load_info(self, attack_id):
        path = self._path(attack_id)
        if not path or not os.path.exists(self._info_path(path)):
            return None
        with open(self._info_path(path), encoding="utf-8") as f:
            return json.load(f)

    def remove(self, attack_ids):
        """Aufzeichnungen löschen, deren Eintrag aus dem Verteidigungslog
        gefallen ist."""
        for attack_id in attack_ids:
            path = self._path(attack_id)
            for target in (path, path and self._info_path(path)):
                if target and os.path.exists(target):
                    os.remove(target)
