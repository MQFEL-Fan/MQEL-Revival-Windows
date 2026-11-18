"""Chat-Moderation: Verlauf mit Löschfrist und Stummschaltung.

Der XMPP-Server (eigener Prozess) schreibt jede Raumnachricht nach
<Profil>/chat/chat-JJJJ-MM-TT.jsonl (Zeit, Raum, Login, Nick, Text; Muted, wenn
stummgeschaltet) und
löscht Tagesdateien, die älter als RETENTION_DAYS sind (DSGVO: Beleg für
Meldungen, keine Dauerspeicherung). Das Admin-Webtool liest sie und pflegt
<Profil>/chat_muted.json ({Login: Ende ISO oder null = unbefristet}); der
XMPP-Server liest die Datei neu, sobald sie sich ändert.
"""

import datetime
import glob
import json
import os
import threading

RETENTION_DAYS = 30
LOCK = threading.Lock()


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


class ChatLog:
    def __init__(self, state_dir):
        self.dir = os.path.join(state_dir, "chat")
        self.muted_path = os.path.join(state_dir, "chat_muted.json")
        self._muted, self._muted_mtime = {}, None
        self._purged_day = None

    # --- Verlauf --------------------------------------------------------------

    def _files(self):
        return sorted(glob.glob(os.path.join(self.dir, "chat-*.jsonl")))

    def purge(self, now=None):
        """Tagesdateien jenseits der Frist löschen (höchstens einmal je Tag)."""
        now = now or _now()
        if self._purged_day == now.date():
            return
        self._purged_day = now.date()
        cutoff = (now - datetime.timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        for path in self._files():
            if os.path.basename(path)[5:15] < cutoff:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def append(self, room, login, nick, text, muted=False, now=None):
        now = now or _now()
        entry = {"Time": _iso(now), "Room": room, "Login": login, "Nick": nick, "Text": text}
        if muted:
            entry["Muted"] = True
        with LOCK:
            self.purge(now)
            os.makedirs(self.dir, exist_ok=True)
            with open(os.path.join(self.dir, now.strftime("chat-%Y-%m-%d.jsonl")),
                      "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def search(self, login=None, text=None, room=None, limit=500):
        """Neueste zuerst; login/room genau, text ohne Groß-/Kleinschreibung."""
        self.purge()
        text = (text or "").lower()
        out = []
        for path in reversed(self._files()):
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if ((not login or e.get("Login") == login)
                        and (not room or e.get("Room") == room)
                        and (not text or text in e.get("Text", "").lower())):
                    out.append(e)
                    if len(out) >= limit:
                        return out
        return out

    # --- Stummschaltung -------------------------------------------------------

    def muted(self):
        """{Login: Ende oder None}, nur noch wirksame Einträge."""
        try:
            mtime = os.path.getmtime(self.muted_path)
        except OSError:
            self._muted, self._muted_mtime = {}, None
            return {}
        if mtime != self._muted_mtime:
            try:
                with open(self.muted_path, encoding="utf-8") as f:
                    self._muted = json.load(f)
            except (OSError, ValueError):
                self._muted = {}
            self._muted_mtime = mtime
        now = _now()
        return {k: v for k, v in self._muted.items() if v is None or _parse(v) > now}

    def is_muted(self, login):
        return login in self.muted()

    def set_mute(self, login, hours=None, mute=True):
        """hours None: unbefristet; mute False: aufheben."""
        with LOCK:
            m = self.muted()
            if not mute:
                m.pop(login, None)
            else:
                m[login] = _iso(_now() + datetime.timedelta(hours=hours)) if hours else None
            tmp = self.muted_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(m, f, indent=1)
            os.replace(tmp, self.muted_path)
            self._muted_mtime = None
        return m.get(login, False) if mute else False
