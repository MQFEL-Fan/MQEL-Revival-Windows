"""Discord Rich Presence: what a player is doing in the game.

The server sees every game request, so it keeps a short activity per player
(note()). The WASD helper DLL in the game (tools/wasd/discord_presence.c)
asks for it at GET /presence/<login name> (plain HTTP, the patcher port)
every few seconds and passes it to the local Discord client (Discord IPC,
SET_ACTIVITY). Only a request from the IP of that player's last game
request gets an answer, and only while the player is active.

Answer (text/plain): first line the Discord application id, then the
activity as JSON; 204 without activity or without application id
(MQEL_DISCORD_APP_ID, see docs/85-discord-presence.md).
"""

import functools
import json
import os
import re
import threading
import time

APP_ID = os.environ.get("MQEL_DISCORD_APP_ID", "").strip()
INVITE = "https://discord.gg/hxFANB2kky"
STALE_S = 300            # no game request for 5 minutes: no activity
LARGE_IMAGE = "logo"     # art asset names in the Discord application
LARGE_TEXT = "The Mighty Quest for Epic Loot"

LOBBY = "In the lobby"
CHOOSING = "Choosing a castle to attack"
BUILDING = "Editing their castle"
SHOPPING = "Shopping"
BLACKSMITH = "At the blacksmith"
HEROES = "Gearing up their hero"
LEADERBOARDS = "Checking the leaderboards"

# SendCommands: command type (without "Command") -> activity
_COMMANDS = (
    (re.compile(r"^(Add|Update|Remove)Castle(Room|Creature|Trap|Decoration|Trigger)$|"
                r"^(Add|Upgrade|Update|Move)Building$|^Boost"), BUILDING),
    (re.compile(r"^(Forge|Craft|Reforge|Upgrade)HeroItem|Forge|Reforge|Blacksmith"), BLACKSMITH),
    (re.compile(r"^Buy|Purchase|^Sell"), SHOPPING),
    (re.compile(r"Equip|HeroItem|Consumable|Skill|SelectHero"), HEROES),
)

_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def _english():
    import loot  # noqa: PLC0415
    path = os.path.join(loot.SETTINGS, "Oasis", "OASIS_EN.JSON")
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)["Translations"]
    except (OSError, ValueError, KeyError):
        return {}


def castle_name(castle_id):
    """Name of a castle as the player sees it (Ubisoft castles by their
    Oasis text, player and fake-player castles by the owner)."""
    import castles  # noqa: PLC0415
    try:
        c = castles.find_castle(int(castle_id))
    except (TypeError, ValueError):
        c = None
    if not c:
        return None
    oid = c.get("OasisNameId") or c.get("OasisName")
    return (_english().get(str(oid)) if oid else None) or c.get("AccountDisplayName")


def _set(player, details, state=None, start=None):
    with _lock:
        cur = getattr(player, "presence", None) or {}
        if cur.get("details") != details or cur.get("state") != state:
            cur = {"details": details, "state": state, "start": start or int(time.time())}
        player.presence = cur


def _command_activity(body):
    for cmd in (body or {}).get("commands") or []:
        kind = str(cmd.get("$type", "")).split(",")[0].rsplit(".", 1)[-1]
        kind = kind[:-len("Command")] if kind.endswith("Command") else kind
        for pattern, activity in _COMMANDS:
            if pattern.search(kind):
                return activity
    return None


def note(player, key, body, ip=None):
    """Update the activity of `player` from a game request (service/method
    key like "AttackService.hqs/StartAttack", body JSON)."""
    player.presence_seen = time.time()
    player.presence_ip = ip
    body = body if isinstance(body, dict) else {}
    if key == "AttackService.hqs/StartAttack":
        if body.get("castleAccountId") == player.account_id:
            _set(player, "Testing their castle")
            return
        name = castle_name(body.get("castleAccountId")) or "a castle"
        state = "Competition" if body.get("ubisoftCompetitionId") else None
        _set(player, "Attacking %s" % name, state)
    elif key == "AttackService.hqs/EndAttack":
        _set(player, LOBBY)
    elif key.startswith("AttackSelectionService.hqs/"):
        if not (getattr(player, "presence", None) or {}).get("details", "").startswith("Attacking"):
            _set(player, CHOOSING)
    elif key == "ServerCommandService.hqs/SendCommands":
        activity = _command_activity(body)
        if activity:
            _set(player, activity)
    elif key.startswith(("LeagueService.hqs/", "GuildService.hqs/GetLeaderboard")):
        _set(player, LEADERBOARDS)
    elif key == "AccountInformationService.hqs/GetAccountInformation":
        _set(player, LOBBY)


def activity(player):
    """Discord activity of `player` or None (inactive)."""
    p = getattr(player, "presence", None)
    if not p or time.time() - getattr(player, "presence_seen", 0) > STALE_S:
        return None
    try:
        level = player.state.snapshot()["BuildInfo"]["Level"]
    except (KeyError, TypeError, AttributeError):
        level = None
    out = {"details": p["details"][:128],
           "timestamps": {"start": p["start"]},
           "assets": {"large_image": LARGE_IMAGE, "large_text": LARGE_TEXT},
           "buttons": [{"label": "Join the server", "url": INVITE}]}
    state = p.get("state") or ("Castle level %d" % level if level else None)
    if state:
        out["state"] = state[:128]
    return out


ONLINE_S = 180  # online: a game request in the last 3 minutes (KeepAlive/Track ~1/min)


def online(player):
    """True while `player`'s game talks to the server."""
    return player is not None and time.time() - getattr(player, "presence_seen", 0) <= ONLINE_S


def friends_online(players, account_id, ip):
    """(status, body) for GET /friends/online?a=<AccountId> (friend list in
    the game, ui_patches 14.): {"<friend id>": true/false} for the friends
    of that account. Only for a request from the IP of the account's last
    game request (or from the server PC itself), else 403."""
    import ipaddress  # noqa: PLC0415
    p = next((x for x in list(players.players.values()) if x.account_id == account_id), None)
    try:
        local = ipaddress.ip_address(ip).is_loopback
    except ValueError:
        local = False
    if p is None or not (local or getattr(p, "presence_ip", None) == ip):
        return 403, b"{}"
    loaded = {x.account_id: x for x in list(players.players.values())}
    out = {str(f["Id"]): online(loaded.get(f["Id"]))
           for f in p.state.snapshot().get("Friends") or []}
    return 200, json.dumps(out, separators=(",", ":")).encode("utf-8")


def answer(players, name, ip):
    """(status, body) for GET /presence/<name>."""
    if not APP_ID:
        return 204, b""
    p = players.players.get(name) if name else None
    if p is None or getattr(p, "presence_ip", None) != ip:
        return 204, b""
    a = activity(p)
    if a is None:
        return 204, b""
    return 200, (APP_ID + "\n" + json.dumps(a, separators=(",", ":"))).encode("utf-8")
