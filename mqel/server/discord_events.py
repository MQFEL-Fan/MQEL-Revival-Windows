"""In-game events on Discord: a webhook post by "Cornelius" every time an
event starts, with its end and the next event (docs/86-discord-events.md).

Events (one calendar, the same the game uses):
* boost weekends and "More Materials" (community_events.py)
* hero free trials (free_trials.py, day 1-7 of every month)
* seasonal events (patcher.EVENTS and Easter): Halloween, Christmas,
  New Year, Valentine's Day, Easter

Webhook URL: environment MQEL_DISCORD_WEBHOOK (server_config.bat) or the
file state/<profile>/discord_webhook.json {"url": "..."}. Without one
nothing is posted. The URL is a secret (anyone with it can post).

The game server runs announce_loop() in a thread: once a minute it checks
for events that are running and not yet announced (state/<profile>/
announced_events.json, so a restart doesn't post twice). Discord shows the
times in every reader's own time zone (<t:...> timestamps).
"""

import datetime
import json
import os
import random
import threading
import time
import urllib.request

import community_events
import free_trials
import patcher

UTC = datetime.timezone.utc
NAME = "Cornelius Richling"
AVATAR = ("https://static.wikia.nocookie.net/themightyquest/images/d/db/"
          "Profile_Cornelius_Richling.png/revision/latest?cb=20140905032322")
COLOR = 0xF2B632  # gold
CHECK_S = 60
LOOKAHEAD_DAYS = 400

# Cornelius' greetings for event posts, one picked at random each time. His
# voice from the game's tutorial texts (Oasis 13111-13128, 15428-15439):
# "buddy/pally/chum", "am I right?", fees, self-corrections, flattery.
GREETINGS = [
    "Attention, castle owners of Opulencia! Cornelius Richling here, with an offer you "
    "can't refuse (legally, you can, but why would you?).",
    "Oh hello there, buddy! Cornelius Richling, owner, founder and occasional brochure "
    "model, with some red-hot news for you!",
    "Never count out old Cornelius! I can smell the winds of change blowing over "
    "Opulencia, and they smell GOOD!",
    "Pally, I've been shopping your name around town, calling in favors, pulling "
    "strings, and look what I got you!",
    "A promise from your man Cornelius is cash in the bank, and today the bank is "
    "OPEN for business!",
    "Drop that loot sack for a second, chum! Cornelius Richling's Premium Talent "
    "Management & Real Estate Emporium has an announcement!",
    "I extort... ahem, I EXHORT all castle owners to listen closely: something "
    "wonderful is happening in Opulencia!",
    "Hey there, hot stuff! I can tell by your rakish good looks that you're ready "
    "for some excitement, am I right?",
    "Compadre, my sofa is reupholstered, my trophies are shined and my new "
    "self-portrait is hung. Time to share the good news!",
    "Listen up, you fierce, simply FIERCE castle-handlers! Your old buddy Cornelius "
    "has something special for you. No signing fee! This time.",
]

SEASONAL = {
    "Halloween": ("Halloween", "Spooky lobby, the Halloween Pack in the bling shop, "
                  "Halloween castles to raid and seasonal shop items."),
    "Christmas": ("Christmas", "A festive Opulencia and Christmas items in the shop."),
    "NewYearEve": ("New Year", "Fireworks over Opulencia and the Christmas items one last time."),
    "ValentinesDay": ("Valentine's Day", "Love is in the air, and so are the Valentine's items."),
    "Easter": ("Easter", "Easter look in the lobby and Easter items in the shop."),
}
BOOST_TEXT = {
    21: "+100 % gold from attacks and gold mines",
    22: "+100 % life force from attacks and life force mines",
    23: "+100 % XP for your heroes",
    24: "+100 % magic find: better loot quality",
    25: "+100 % bling mine production",
    26: "Material-O-Matics produce twice as fast",
}


# --- calendar ------------------------------------------------------------------

def _seasonal(year):
    out = []
    for group, (m1, d1), (m2, d2) in patcher.EVENTS:
        start = datetime.datetime(year, m1, d1, tzinfo=UTC)
        end_year = year + 1 if (m2, d2) < (m1, d1) else year
        end = datetime.datetime(end_year, m2, d2, tzinfo=UTC) + datetime.timedelta(days=1)
        out.append((start, end, group))
    sunday = patcher.easter_sunday(year)
    start = datetime.datetime.combine(sunday - datetime.timedelta(days=7), datetime.time(), UTC)
    out.append((start, start + datetime.timedelta(days=15), "Easter"))
    return [(s, e, "season:%s:%d" % (g, s.year)) + SEASONAL[g] for s, e, g in out]


def _boosts(year):
    out = []
    for month in range(1, 13):
        start, end = community_events.boost_window(year, month)
        ids = community_events.boosts_of(month)
        if len(ids) > 1:
            title = "Everything x2 weekend"
            text = "All boosts at once: " + "; ".join(BOOST_TEXT[i] for i in ids) + "."
        else:
            title = "%s boost weekend" % community_events.BOOST_NAMES[ids[0]]
            text = BOOST_TEXT[ids[0]] + "."
        out.append((start, end, "boost:%d" % community_events.boost_key(start, ids), title, text))
    start, end = community_events.loot_window(year)
    out.append((start, end, "loot:%d" % year, "More Materials",
                "Double crafting materials from player castles and from your gear's bonus."))
    return out


def _trials(year):
    out = []
    for month in range(1, 13):
        e = free_trials.current(datetime.date(year, month, 1))
        hero = free_trials.HEROES[e["Hero"]]
        out.append((e["Start"], e["End"] + datetime.timedelta(seconds=1), "trial:%d" % e["Id"],
                    "%s free trial" % hero,
                    "Play the %s for free for a week; level it up to get it cheaper "
                    "in the shop." % hero))
    return out


def calendar(now, days=LOOKAHEAD_DAYS):
    """[(start, end, key, title, text)] of the events that end after `now`
    and start within `days`, by start."""
    out = []
    for year in (now.year - 1, now.year, now.year + 1, now.year + 2):
        out += _seasonal(year) + _boosts(year) + _trials(year)
    limit = now + datetime.timedelta(days=days)
    return sorted({e[2]: e for e in out if e[1] > now and e[0] < limit}.values())


def running(now):
    return [e for e in calendar(now) if e[0] <= now]


def next_event(now):
    return next((e for e in calendar(now) if e[0] > now), None)


# --- messages ------------------------------------------------------------------

def _ts(dt, style="F"):
    return "<t:%d:%s>" % (int(dt.timestamp()), style)


def _event_field(e):
    return {"name": e[3], "value": "%s\nUntil %s (%s)" % (e[4], _ts(e[1]), _ts(e[1], "R")),
            "inline": False}


def _next_field(now):
    n = next_event(now)
    if not n:
        return []
    return [{"name": "Next event: " + n[3],
             "value": "%s\nStarts %s (%s)" % (n[4], _ts(n[0]), _ts(n[0], "R")), "inline": False}]


def event_message(event, now):
    """Webhook payload for an event that just started."""
    lines = [random.choice(GREETINGS), "**%s** has begun!" % event[3]]
    return {"username": NAME, "avatar_url": AVATAR,
            "embeds": [{"title": "Event started: " + event[3], "color": COLOR,
                        "description": "\n\n".join(lines),
                        "fields": [_event_field(event)] + _next_field(now),
                        "footer": {"text": "Cornelius Real Estate · Some settling may occur."}}]}


def intro_message(now):
    """Cornelius introduces himself (first test of the webhook)."""
    active = running(now)
    text = (
        "Greetings, lucky winners of the Opulencia Lottery! The name is **Cornelius "
        "Richling**: owner, founder and occasional brochure model of Cornelius "
        "Richling's Real Estate Emporium and of Cornelius' Emporium, where you "
        "picked up that charming starter castle of yours.\n\n"
        "From now on I'll personally ring this little bell every time something "
        "exciting happens in Opulencia: boost weekends, free heroes, Halloween "
        "frights, Christmas cheer, all of it, the very moment it starts, and I'll "
        "even tell you what's next. Consider it a complimentary service. No refunds.")
    fields = [dict(_event_field(e), name="Happening right now: " + e[3]) for e in active] or [
        {"name": "Right now", "value": "No event running. Quiet days are great for "
                                       "redecorating!", "inline": False}]
    return {"username": NAME, "avatar_url": AVATAR,
            "embeds": [{"title": "A word from your favourite real estate tycoon",
                        "color": COLOR, "description": text,
                        "thumbnail": {"url": AVATAR},
                        "fields": fields + _next_field(now),
                        "footer": {"text": "Cornelius Real Estate · Some settling may occur."}}]}


# --- sending -------------------------------------------------------------------

def webhook_url(state_dir):
    url = os.environ.get("MQEL_DISCORD_WEBHOOK", "").strip()
    if not url and state_dir:
        try:
            with open(os.path.join(state_dir, "discord_webhook.json"), encoding="utf-8") as f:
                url = (json.load(f).get("url") or "").strip()
        except (OSError, ValueError):
            url = ""
    return url if url.startswith("https://discord.com/api/webhooks/") else ""


# Cornelius' voice lines from the game (tools/extract_audio.py, see
# docs/86-discord-events.md): one random clip is attached to each new post,
# Discord shows it as an audio player under the message. Empty folder = no
# audio.
VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "voices", "cornelius")
VOICE_TYPES = {".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


def voice_file():
    """Path of a random Cornelius voice clip or None."""
    try:
        files = [f for f in os.listdir(VOICE_DIR) if os.path.splitext(f)[1].lower() in VOICE_TYPES]
    except OSError:
        return None
    return os.path.join(VOICE_DIR, random.choice(sorted(files))) if files else None


def encode(payload, voice=None):
    """(body, content type) for a webhook call: JSON, or multipart with the
    voice clip as files[0] ("cornelius<ext>") and payload_json."""
    if not voice:
        return json.dumps(payload).encode("utf-8"), "application/json"
    ext = os.path.splitext(voice)[1].lower()
    with open(voice, "rb") as f:
        audio = f.read()
    boundary = "mqel%032x" % random.getrandbits(128)
    payload = dict(payload, attachments=[{"id": 0, "filename": "cornelius" + ext,
                                          "description": "Cornelius Richling"}])
    parts = [
        b"--" + boundary.encode(),
        b'Content-Disposition: form-data; name="payload_json"',
        b"Content-Type: application/json", b"", json.dumps(payload).encode("utf-8"),
        b"--" + boundary.encode(),
        ('Content-Disposition: form-data; name="files[0]"; filename="cornelius%s"' % ext).encode(),
        ("Content-Type: %s" % VOICE_TYPES[ext]).encode(), b"", audio,
        b"--" + boundary.encode() + b"--", b""]
    return b"\r\n".join(parts), "multipart/form-data; boundary=" + boundary


def post(url, payload, voice=None):
    """POST to the webhook (with an optional voice clip); returns the HTTP
    status (exceptions pass)."""
    body, ctype = encode(payload, voice)
    req = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "wait=true", data=body, method="POST",
        headers={"Content-Type": ctype, "User-Agent": "DiscordBot (mqel-server, 1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


class Announcer:
    def __init__(self, state_dir, log=print, send=post):
        self.state_dir, self.log, self.send = state_dir, log, send
        self.path = os.path.join(state_dir, "announced_events.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.done = set(json.load(f))
        except (OSError, ValueError):
            self.done = set()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(self.done), f, indent=1)
        os.replace(tmp, self.path)

    def mark(self, keys):
        self.done.update(keys)
        self._save()

    def tick(self, now=None):
        """Post every running, not yet announced event; returns their keys."""
        url = webhook_url(self.state_dir)
        if not url:
            return []
        now = now or datetime.datetime.now(UTC)
        posted = []
        for e in running(now):
            if e[2] in self.done:
                continue
            try:
                self.send(url, event_message(e, now), voice_file())
            except OSError as err:
                self.log("[discord] Event %s nicht gesendet: %s" % (e[2], err))
                break  # try again next minute
            posted.append(e[2])
            self.mark([e[2]])
            self.log("[discord] Event angekündigt: %s" % e[3])
        return posted


def start(state_dir, log=print):
    """Announcer thread (daemon), only with a webhook URL."""
    if not webhook_url(state_dir):
        return None
    a = Announcer(state_dir, log)

    def loop():
        while True:
            try:
                a.tick()
            except Exception as err:  # noqa: BLE001 - the thread must keep running
                log("[discord] Fehler: %s" % err)
            time.sleep(CHECK_S)
    threading.Thread(target=loop, daemon=True, name="discord-events").start()
    log("[discord] Event-Ankündigungen aktiv")
    return a
