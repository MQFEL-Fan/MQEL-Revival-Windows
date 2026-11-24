"""Patch notes on Discord: Cornelius Richling posts them to the patch-note
channel through a second webhook (docs/86-discord-events.md).

* Admin web tool, News (AdminService SaveNews/DeleteNews): a new entry is
  posted, an edited entry edits its Discord message, a deleted entry deletes
  it. Message ids: state/<profile>/discord_news_messages.json
  {news id: message id}. Entries that existed before the webhook stay as
  they are until someone edits them (then they are posted).
* backfill(): the released sections of PATCH_NOTES.md, oldest first (once,
  done 2026-11-22; sections whose title starts with "Next update" are not
  released yet and are skipped).

Webhook URL: environment MQEL_DISCORD_PATCH_WEBHOOK (server_config.bat) or
state/<profile>/discord_patch_webhook.json {"url": "..."}. Without one
nothing happens. Posting runs in a thread, the admin tool never waits for
Discord.
"""

import json
import os
import random
import re
import threading
import urllib.error
import urllib.request

import discord_events

NAME, AVATAR, COLOR = discord_events.NAME, discord_events.AVATAR, 0x4FA3E0
FOOTER = "Cornelius Real Estate · Some settling may occur."
# Cornelius' greetings for patch notes, one picked at random each time (his
# voice from the game's tutorial texts, see discord_events.GREETINGS).
GREETINGS = [
    "Attention, castle owners of Opulencia! Cornelius Richling here, with fresh "
    "renovations for every castle in the realm (no extra charge, this time).",
    "Oh hello there, buddy! Your old pal Cornelius didn't mess around and get you some "
    "fixer-upper, no sirree! Look what's new:",
    "Hot off the brochure press, pally! The contractors have finished, and the "
    "results are simply FIERCE:",
    "Welcome back to Cornelius Richling's Premium Talent Management & Real Estate "
    "Emporium! Owner, founder and sole employee, reporting some fine improvements:",
    "Now, chum, a few small renovations have been made to the kingdom. Nothing "
    "sub-prime about THESE, am I right?",
    "A promise from your man Cornelius is cash in the bank, and I promised you a "
    "better Opulencia! Here are the details:",
    "Never count out old Cornelius! I had a word with the builders, and they "
    "delivered (mostly on time):",
    "Compadre, read the fine print below. Some settling may occur, but mostly "
    "it's GOOD settling:",
    "I extort... ahem, I EXHORT you to read these patch notes, hot stuff. Your "
    "castle will thank you:",
    "Remember when your castle was a dump? That's over now. Cornelius brings you "
    "the latest upgrades:",
]
HOW_TO = "Restart your launcher to move right in."


def webhook_url(state_dir):
    url = os.environ.get("MQEL_DISCORD_PATCH_WEBHOOK", "").strip()
    if not url and state_dir:
        try:
            with open(os.path.join(state_dir, "discord_patch_webhook.json"), encoding="utf-8") as f:
                url = (json.load(f).get("url") or "").strip()
        except (OSError, ValueError):
            url = ""
    return url if url.startswith("https://discord.com/api/webhooks/") else ""


def _request(url, method, payload=None, voice=None):
    """Webhook call (voice: clip to attach); returns the answer JSON (or {})."""
    data, ctype = (discord_events.encode(payload, voice) if payload is not None
                   else (None, "application/json"))
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": ctype, "User-Agent": "DiscordBot (mqel-server, 1.0)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read()
    return json.loads(body) if body else {}


def send(url, payload, voice=None):
    return _request(url + "?wait=true", "POST", payload, voice)


def edit(url, message_id, payload):
    return _request("%s/messages/%s" % (url, message_id), "PATCH", payload)


def delete(url, message_id):
    return _request("%s/messages/%s" % (url, message_id), "DELETE")


def _markdown(text):
    """PATCH_NOTES.md markdown for an embed: ### headings as bold lines,
    joined wrapped lines (Discord keeps single line breaks)."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        if lines[0].startswith("#"):
            out.append("**%s**" % lines[0].lstrip("# ").strip())
            lines = lines[1:]
            if not lines:
                continue
        items, cur = [], ""
        for line in lines:
            if re.match(r"\s*([-*]|\d+\.)\s", line) or not cur:
                if cur:
                    items.append(cur)
                cur = line.strip()
            else:
                cur += " " + line.strip()
        items.append(cur)
        out.append("\n".join(items))
    return "\n\n".join(out)


def message(title, text, date=None, how_to=True):
    """Webhook payload for a patch note (how_to: closing line; the
    PATCH_NOTES.md sections have their own "How to get it")."""
    desc = random.choice(GREETINGS) + "\n\n" + (_markdown(text) if text else "")
    if how_to:
        desc += "\n\n*" + HOW_TO + "*"
    embed = {"title": title[:256], "color": COLOR, "description": desc[:4096],
             "footer": {"text": FOOTER}}
    if date:
        embed["timestamp"] = "%sT12:00:00Z" % date
    return {"username": NAME, "avatar_url": AVATAR, "embeds": [embed]}


# --- PATCH_NOTES.md ---------------------------------------------------------------

def sections(path):
    """[(date, title, body)] of the released sections, oldest first."""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    out = []
    for part in re.split(r"^## ", s, flags=re.M)[1:]:
        head, body = part.split("\n", 1)
        if head.lower().startswith("next update"):
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2}):\s*(.*)", head.strip())
        date, title = (m.group(1), m.group(2)) if m else (None, head.strip())
        body = re.sub(r"\*Short version for Discord/Steam:\*.*?(?=^---|\Z)", "", body,
                      flags=re.S | re.M)
        body = re.sub(r"^---\s*$", "", body, flags=re.M).strip()
        out.append((date, title, body))
    return list(reversed(out))


def backfill(url, path, log=print):
    """Post every released section of PATCH_NOTES.md, oldest first."""
    ids = []
    for date, title, body in sections(path):
        name = "Patch %s: %s" % (date, title) if date else title
        ids.append(send(url, message(name, body, date, how_to=False)).get("id"))
        log("[discord] Patch-Note gesendet: %s" % name)
    return ids


# --- admin news -> Discord ----------------------------------------------------------

class NewsNotifier:
    """news.News.listener: posts, edits and deletes the Discord messages of
    the launcher news."""

    def __init__(self, state_dir, log=print, api=None):
        self.state_dir, self.log = state_dir, log
        self.api = api or {"send": send, "edit": edit, "delete": delete}
        self.path = os.path.join(state_dir, "discord_news_messages.json")
        self.lock = threading.Lock()
        try:
            with open(self.path, encoding="utf-8") as f:
                self.ids = json.load(f)
        except (OSError, ValueError):
            self.ids = {}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.ids, f, indent=1)
        os.replace(tmp, self.path)

    def handle(self, action, item):
        """action "save" (item = news entry) or "delete" (item = {"Id"})."""
        url = webhook_url(self.state_dir)
        if not url:
            return
        key = str(item["Id"])
        with self.lock:
            try:
                mid = self.ids.get(key)
                if action == "delete":
                    if mid:
                        self.api["delete"](url, mid)
                        del self.ids[key]
                        self.log("[discord] News %s gelöscht" % key)
                else:
                    payload = message(item["Title"], item.get("Text", ""), item.get("Date"))
                    if mid:
                        try:
                            self.api["edit"](url, mid, payload)
                            self.log("[discord] News %s geändert" % key)
                            return
                        except urllib.error.HTTPError as err:
                            if err.code != 404:  # message deleted in Discord: post again
                                raise
                    self.ids[key] = self.api["send"](
                        url, payload, discord_events.voice_file()).get("id")
                    self.log("[discord] News %s gesendet: %s" % (key, item["Title"]))
                self._save()
            except (OSError, ValueError) as err:
                self.log("[discord] News %s nicht gesendet: %s" % (key, err))

    def __call__(self, action, item):
        threading.Thread(target=self.handle, args=(action, dict(item)), daemon=True,
                         name="discord-news").start()
