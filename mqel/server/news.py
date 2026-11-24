"""News auf der Launcher-Seite (patcher.login_page), gepflegt im
Admin-Webtool (AdminService GetNews/SaveNews/DeleteNews). Gespeichert in
<state>/news.json als Liste {Id, Date, Title, Text}, neueste zuerst."""

import datetime
import html
import json
import os
import threading

SHOWN = 5  # Einträge auf der Launcher-Seite


class News:
    def __init__(self, path, listener=None):
        self.path = path
        # listener(action, item): "save"/"delete" nach jeder Änderung
        # (discord_patch_notes.NewsNotifier)
        self.listener = listener
        self.lock = threading.Lock()
        self.items = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.items = json.load(f)

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def all(self):
        with self.lock:
            return [dict(i) for i in self.items]

    def save(self, title, text, date=None, item_id=None):
        """Eintrag anlegen oder (item_id) ändern; Datum YYYY-MM-DD, Vorgabe heute."""
        title, text = str(title).strip(), str(text).strip()
        if not title:
            raise ValueError("title missing")
        date = str(date or datetime.date.today().isoformat())
        datetime.date.fromisoformat(date)
        with self.lock:
            item = next((i for i in self.items if i["Id"] == item_id), None) if item_id else None
            if item_id and item is None:
                raise ValueError("unknown news %s" % item_id)
            if item is None:
                item = {"Id": max([i["Id"] for i in self.items] + [0]) + 1}
                self.items.append(item)
            item.update(Date=date, Title=title, Text=text)
            self.items.sort(key=lambda i: (i["Date"], i["Id"]), reverse=True)
            self._save()
            item = dict(item)
        if self.listener:
            self.listener("save", item)
        return item

    def delete(self, item_id):
        with self.lock:
            self.items = [i for i in self.items if i["Id"] != item_id]
            self._save()
        if self.listener:
            self.listener("delete", {"Id": item_id})

    def html(self):
        """HTML der neuesten Einträge für die Launcher-Seite ('' ohne News)."""
        return "".join(
            '<div class="n"><span class="d">%s</span> <b>%s</b><p>%s</p></div>' % (
                html.escape(i["Date"]), html.escape(i["Title"]),
                html.escape(i["Text"]).replace("\n", "<br>"))
            for i in self.all()[:SHOWN])
