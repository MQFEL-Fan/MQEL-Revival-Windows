"""Steam-Anmeldung: Ticket des Launchers -> SteamID.

Im Steam-Modus hängt der Launcher an jedes abgeschickte Formular der
Login-Seite das Feld steam_ticket (ISteamUser::GetAuthSessionTicket, Hex,
launcher.js _formWithSteamTicket). Der Server prüft es bei Steam
(ISteamUserAuth/AuthenticateUserTicket) und erhält die SteamID. Ohne Prüfung
wäre die SteamID fälschbar, deshalb gibt es ohne Web-API-Key keine
Steam-Anmeldung (Umgebungsvariable MQEL_STEAM_API_KEY).
"""

import json
import os
import hashlib
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import profanity

APP_ID = 239220  # The Mighty Quest for Epic Loot (steam_appid.txt des Launchers)
API_URL = "https://api.steampowered.com/ISteamUserAuth/AuthenticateUserTicket/v1/"
PROFILE_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
TICKET_RE = re.compile(r"[0-9A-Fa-f]{16,4096}")
# Jedes Ticket gilt nur einmal: ein abgefangenes oder von einem anderen
# Server derselben appid weitergereichtes Ticket meldet nicht noch einmal an
# (GetAuthSessionTicket bindet nicht an einen Dienst). Nur im Speicher; der
# Launcher holt für jede Anmeldung ein neues.
SEEN_S = 7 * 86400
_seen = {}  # SHA-256 des Tickets -> Zeitpunkt (monotonic)
_seen_lock = threading.Lock()
# Höchstens so viele Aufrufe an die Steam-Web-API je Minute, über alle IPs:
# viele gültig aussehende Tickets von wechselnden IPs sollen das
# Tageskontingent des Keys nicht aufbrauchen (die Bremse je IP greift nur
# bei Fehlschlägen, game_server._launcher_steam)
MAX_CALLS_PER_MIN = 60
_calls = []  # Zeitpunkte (monotonic) der letzten Minute
MAX_BASE = 20  # Platz für den Zähler bei Namenskollision (Namen sind 3-24 lang)


class SteamError(Exception):
    """Fehler mit Schlüssel für die Login-Seite (dort übersetzt)."""


def enabled():
    return bool(os.environ.get("MQEL_STEAM_API_KEY"))


def verify(ticket):
    """SteamID (Text) des Ticket-Inhabers oder SteamError."""
    key = os.environ.get("MQEL_STEAM_API_KEY")
    if not key:
        raise SteamError("steam_disabled")
    if not TICKET_RE.fullmatch(ticket or ""):
        raise SteamError("steam_no_ticket")
    _use_once(ticket)
    _count_call()
    url = API_URL + "?" + urllib.parse.urlencode(
        {"key": key, "appid": APP_ID, "ticket": ticket})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise SteamError("steam_http_%d" % e.code)
    except (OSError, ValueError):
        raise SteamError("steam_unreachable")
    response = data.get("response", {})
    params = response.get("params")
    if not params or params.get("result") != "OK":
        raise SteamError("steam_invalid")
    return str(params["steamid"])


def _use_once(ticket):
    digest = hashlib.sha256(ticket.lower().encode("ascii")).hexdigest()
    now = time.monotonic()
    with _seen_lock:
        for d in [d for d, t in _seen.items() if now - t >= SEEN_S]:
            del _seen[d]
        if digest in _seen:
            raise SteamError("steam_reused")
        _seen[digest] = now


def _count_call():
    now = time.monotonic()
    with _seen_lock:
        _calls[:] = [t for t in _calls if now - t < 60]
        if len(_calls) >= MAX_CALLS_PER_MIN:
            raise SteamError("steam_busy")
        _calls.append(now)


def persona(steam_id):
    """Profilname der SteamID (GetPlayerSummaries) oder "" (best effort)."""
    try:
        _count_call()
    except SteamError:
        return ""
    url = PROFILE_URL + "?" + urllib.parse.urlencode(
        {"key": os.environ.get("MQEL_STEAM_API_KEY", ""), "steamids": steam_id})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            players = json.load(r).get("response", {}).get("players", [])
        return str(players[0].get("personaname", "")) if players else ""
    except (OSError, ValueError, AttributeError):
        return ""


def account_name(persona_name, steam_id, taken):
    """Login-Name für einen neuen Steam-Account aus dem Profilnamen:
    ASCII ohne Sonderzeichen (auth.NAME_RE), mindestens 3 Zeichen und ohne
    Schimpfwort (sonst Steam_<letzte Ziffern>), bei Kollision (taken(name), Groß-/Kleinschreibung
    egal) mit Zähler."""
    folded = unicodedata.normalize("NFKD", persona_name or "")
    base = re.sub(r"[^A-Za-z0-9_.\-]+", "_", folded.encode("ascii", "ignore").decode()
                  .replace(" ", "_")).strip("_.-")[:MAX_BASE]
    words = re.sub(r"[_.\-]", " ", base)  # „_“ zählt sonst als Wortzeichen
    if len(base) < 3 or profanity.filter_text(words) != words:
        base = "Steam_" + steam_id[-6:]
    name, n = base, 1
    while taken(name):
        n += 1
        name = "%s_%d" % (base, n)
    return name
