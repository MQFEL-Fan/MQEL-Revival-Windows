#!/usr/bin/env python3
"""MQEL-Spielserver.

Lauscht auf {GameServerUrl}/{Service}.hqs/{Methode} und beantwortet die
Dienste des Clients (Account, Angriffe, Quests, Shop, Clans, ...) mit
einem Account je Token (players.py). Entstanden als Logging-Server
(Revival-Schritt C, docs/50-revival-plan.md): jeder Request wird weiterhin
(Methode, Pfad, Query, Argo-Header t/i/h/rnd/n/g, Body) nach STDOUT +
JSONL-File geloggt; Unbekanntes beantwortet er mit minimalem JSON bzw.
Overrides aus responses.json.

Start:
  python server/game_server.py --port 8081
  python server/game_server.py --port 8081 --responses server/responses.json

Client (Direktstart, CWD = client/GameData/Bin):
  MightyQuest_release.exe -server_url http://127.0.0.1:8081 -token test ^
    -email test@test -environmentName local -httpCompression 0

Antworten iterativ in responses.json erweitern (Server neu starten oder
gleiche Datei neu laden: wird pro Request neu eingelesen).
Nur Standardbibliothek, keine Dependencies.
"""

import argparse
import datetime
import http.cookies
import ipaddress
import json
import os
import random
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer

import account_state
from account_state import CURRENCY, PROFILES, ROOT

ADMIN_PAGE = os.path.join(ROOT, "server", "admin", "index.html")
WEBSITE = os.path.join(ROOT, "website")  # öffentliche Projektseite (--web-port)


class WebsiteHandler(SimpleHTTPRequestHandler):
    """Nur die Dateien aus website/, ohne Verzeichnislisten."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBSITE, **kwargs)

    https = None  # Port der HTTPS-Seite: dann leitet HTTP dorthin um
    timeout = 30

    def setup(self):
        super().setup()
        if isinstance(self.request, ssl.SSLSocket):  # Handshake im Verbindungs-Thread
            self.request.do_handshake()

    def do_GET(self):
        # Let's-Encrypt-Prüfung (certbot --webroot -w website) bleibt auf HTTP
        if (self.https and not isinstance(self.request, ssl.SSLSocket) and not self.path.startswith("/.well-known/acme-challenge/")):
            host = self.headers.get("Host", "").split(":")[0]
            port = "" if self.https == 443 else ":%d" % self.https
            self.send_response(301)
            self.send_header("Location", "https://%s%s%s" % (host, port, self.path))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.headers.get("Range") and self._send_range():
            return
        super().do_GET()

    def end_headers(self):
        # Videos (website/media): browsers and Discord stream and seek with
        # Range requests (_send_range)
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def _send_range(self):
        """206 Partial Content for "Range: bytes=a-b" on a file; False if
        the request isn't a simple byte range on an existing file."""
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        path = self.translate_path(self.path)
        if not m or not os.path.isfile(path) or not (m.group(1) or m.group(2)):
            return False
        size = os.path.getsize(path)
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
        else:  # "bytes=-N": the last N bytes
            start, end = max(0, size - int(m.group(2))), size - 1
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):  # player skipped ahead
                pass
        return True

    def list_directory(self, path):
        self.send_error(404)
import admin
import chat_log
import anticheat
import attack
import auth
import balance
import news
import notifications
import patcher
import castles
import castle_sale
import castle_stats
import competitions
import bling_shop
import special_packs
import steam_auth
import community_events
import discord_events
import discord_patch_notes
import free_trials
import iplog
import parties
import raids
import ingame_market
import guilds
import limits
import leagues
import presence
import players
import trophies
import geoip
import loot
import profiles
import replays
import server_stats
import tracking
import website

# Parallele Requests (Keep-Alive × N Connections) dürfen Log-Zeilen
# nicht zerreißen: ein Lock für alle Log-Appends (HTTP + Honeypot).
LOG_LOCK = threading.Lock()


def log_line(path, obj):
    try:
        with LOG_LOCK:
            limits.rotate_log(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[warn] log write failed: {e}", flush=True)

AMBIENT_HEADERS = ("t", "i", "h", "rnd", "n", "g", "v")
MAX_BODY_LOG = 1_000_000
MAX_BODY = 4_000_000  # Obergrenze je Request (EndAttack mit Replay bis ~200 KB)

BUILTIN_OVERRIDES = {
    # Boot: Client prüft meist zuerst, ob der Server lebt.
    "AccountService.hqs/HealthCheck": True,
    # Keepalive: annehmen, nichts tun (Tracking s. tracking.py)
    "UtilityService.hqs/KeepAlive": {},
    "CrashReportService.hqs/SendCrashReports": {},
}


# Antworten, die der Client ohne WrappedResponse-Hülle liest (Task-Callback
# deserialisiert direkt, z. B. UpdateGuildTask 0x7e7ae0 als Guild): mit
# Hülle kam ein leerer Clan an (ohne Emblem, Absturz im Chat-Panel 0xb8b034).
# GetBattleLog liest GuildBattleLog genauso (0x535bef)
UNWRAPPED = {"GuildService.hqs/UpdateGuild", "GuildService.hqs/GetBattleLog"}


def admin_web_allowed(address, tls, has_admins, nets):
    """Webtool /admin: aus dem lokalen Netz immer; von außen nur aus `nets`
    (--admin-net), per HTTPS (Passwort und Cookie nicht im Klartext) und
    erst, wenn es einen Admin gibt (sonst könnte sich jeder dort selbst
    ernennen)."""
    ip = ipaddress.ip_address(address)
    if ip.is_private or ip.is_loopback:
        return True
    return tls and has_admins and any(ip in net for net in nets)


def wrap_response(payload, notifications=(), global_notifications=()):
    """Client-Proxies parsen jede JSON-Antwort fest als WrappedResponse und
    übernehmen dessen `Result` (MightyQuest_release.exe 0x5cc280). Eine
    nackte DTO-Antwort ergibt dort ein NULL-Result.

    Der Wrapper selbst trägt KEIN `$type`: WrappedResponse fehlt in der
    Typ-Tabelle des Clients, und dessen Binärsuche liest bei Typnamen, die
    hinter dem letzten Eintrag sortieren, über das Tabellenende hinaus
    (Access Violation 0x1285040). Leere Antwort (void-Methoden) = `{}`.

    Ausstehende Server-Notifications reisen im selben Wrapper mit
    (`Notifications`, s. notifications.py), globale ohne Index in
    `GlobalNotifications`."""
    out = {} if payload in (None, {}) else {"Result": payload}
    if notifications:
        out["Notifications"] = list(notifications)
    if global_notifications:
        out["GlobalNotifications"] = list(global_notifications)
    return out


def load_responses(path):
    merged = dict(BUILTIN_OVERRIDES)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                merged.update(user)
            else:
                print(f"[warn] {path}: kein JSON-Objekt, ignoriere", flush=True)
        except Exception as e:  # Datei darf den Server nie killen
            print(f"[warn] {path} nicht ladbar: {e}", flush=True)
    return merged


# Freundes-News (hyperquest.enums.NewsType) und ihre NewsData-Klassen
NEWS_HERO_LEVEL_UP_FRIEND, NEWS_HERO_LEVEL_UP_OWN, NEWS_BOSS_KILLED_FRIEND = 9, 10, 17
NEWS_DATA = {9: "HeroLevelUpFriendNewsData", 10: "HeroLevelUpOwnNewsData",
             17: "BossKilledFriendNewsData"}
# HeroSpecContainerIds; die News-Vorlagen zeigen HeroName unübersetzt
HERO_NAMES = {2: "Knight", 3: "Archer", 4: "Mage", 5: "Runaway"}


def _notify_objectives(notify, quest):
    """Meldungen zu abgeschlossenen/freigeschalteten Objectives."""
    for oid in quest["completed"]:
        notifications.objective_completed(notify, oid)
    notifications.wallet_updated(notify, quest["wallet"])
    for name, fields in quest["inventory"]:
        notify.push(name, fields)
    if quest["hero"]:
        notifications.hero_xp_changed(notify, quest["hero"], quest["xp"],
                                      quest["level_changed"])
    for entry in quest["unlocked"]:
        notifications.objective_unlocked(notify, entry)


def _client_json(node):
    """Antwort-JSON für den Client: ohne Exponenten (s. _no_exponents) und
    Nicht-ASCII als UTF-8. Escapes wie \u00c9 versteht der JSON-Leser des
    Clients nicht (GetAccountInformation mit "É" in der Clan-Begrüßung:
    0x80030003, "Invalid AccountInformation", Network error)."""
    return json.dumps(_no_exponents(node), ensure_ascii=False).encode("utf-8")


def _no_exponents(node):
    """Gleitkommazahlen, die Python mit Exponent schreibt (z. B. -1.4e-07 in
    den Burgdaten von Burg 14), versteht der JSON-Leser des Clients nicht
    ("Expected character '}'", Angriff bricht ab). Winzige Werte werden 0,
    große als ganze Zahl geschrieben."""
    if isinstance(node, float):
        if "e" in repr(node):
            return 0.0 if abs(node) < 1 else int(node)
        return node
    if isinstance(node, dict):
        return {k: _no_exponents(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_no_exponents(v) for v in node]
    return node


def _display_name_blocked():
    """Gesperrte Anzeigenamen (DisplayNameSettings.AccountDisplayNameNoMatchRegex,
    .NET-Regex mit (?i) mitten im Muster: für Python ohne, dafür re.I)."""
    path = os.path.join(loot.SETTINGS, "GeneralSettings", "DisplayNameSettings.json")
    with open(path, encoding="utf-8-sig") as f:
        pattern = json.load(f)["AccountDisplayNameNoMatchRegex"]
    return re.compile(pattern.replace("(?i)", ""), re.I)


DISPLAY_NAME_BLOCKED = _display_name_blocked()

# Requests mit Passwort im Body (Launcher-Login, Admin-Webtool): Body wird
# weder ausgegeben noch ins Request-Log geschrieben
# Steam-Tickets in URLs (Login-Seite: ?steamID=…&ticket=…, Shop-URLs des
# Clients: steamTicket) melden an, solange sie gelten: nie in Konsole/Log
SECRET_QUERY = {"ticket", "steam_ticket", "steamticket"}


SECRET_QUERY_RE = re.compile(r"\b(%s)=[^&\s\"]*" % "|".join(SECRET_QUERY), re.I)


def redact_query(query_string):
    """Query ohne Werte der Schlüssel aus SECRET_QUERY (Groß-/Kleinschreibung
    egal)."""
    if not query_string:
        return query_string
    return "&".join(
        (k + "=(redacted)") if k.lower() in SECRET_QUERY else
        (k + "=" + v if sep else k)
        for k, sep, v in (part.partition("=") for part in query_string.split("&")))


SECRET_METHODS = {"login", "register", "SetPassword", "session", "steam", "steamnew"}

class GameHandler(BaseHTTPRequestHandler):
    server_version = "MQEL-Logging/0.1"
    timeout = 60  # Socket-Timeout: stille/langsame Verbindungen schließen

    def setup(self):
        super().setup()  # setzt das Timeout, gilt so auch für den Handshake
        if isinstance(self.connection, ssl.SSLSocket):
            try:
                self.connection.do_handshake()
            except (ssl.SSLError, OSError) as e:
                print(f"[tls] Handshake mit {self.client_address[0]} gescheitert: {e}",
                      flush=True)
                raise
    protocol_version = "HTTP/1.1"  # wie IIS-Original (Keep-Alive)

    def log_message(self, fmt, *args):  # STDOUT statt STDERR, ruhiger
        sys.stdout.write("[http] " + SECRET_QUERY_RE.sub(r"\1=(redacted)", fmt % args) + "\n")
        sys.stdout.flush()

    def _base_url(self):
        """Schema und Host dieser Anfrage, für URLs, die der Client wieder
        hierher schickt (HTTPS-Port: https, sonst Klartext auf dem Port)."""
        scheme = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
        return "%s://%s" % (scheme, self.headers.get("Host", ""))

    def _read_body(self):
        """Body (EndAttack trägt den Replay als Anhang, replays.py) oder None,
        wenn er über MAX_BODY liegt (dann ist 413 gesendet)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self.close_connection = True  # Rest des Bodys nicht lesen
            self.send_response(413)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            return None
        return self.rfile.read(length) if length > 0 else b""

    def _handle(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        service, method = "", ""
        if len(parts) >= 2:
            service, method = parts[-2], parts[-1]
        elif len(parts) == 1:
            service = parts[0]
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        logged_qs = redact_query(parsed.query)
        logged_path = parsed.path + ("?" + logged_qs if parsed.query else "")
        raw_body = self._read_body()
        if raw_body is None:
            return
        try:
            body_text = raw_body.decode("utf-8", errors="replace")
        except Exception:
            body_text = repr(raw_body)
        try:
            # EndAttack hängt hinter das JSON den binären Replay an
            body_json, end = (json.JSONDecoder().raw_decode(body_text)
                              if body_text.strip() else (None, 0))
            replay = raw_body[len(body_text[:end].encode("utf-8")):]
        except Exception:
            body_json, replay = None, b""

        ambient = {k: self.headers.get(k) for k in AMBIENT_HEADERS
                   if self.headers.get(k) is not None}
        # Formular des Launchers mit steam_ticket (Login-Seite, /launcher/steam)
        self._form = (urllib.parse.parse_qs(body_text)
                      if parts[-1] == "steam" and self.command == "POST" else {})
        if parts[-1] in SECRET_METHODS:  # Passwörter nie in Konsole/Log
            body_text, logged_json = "(redacted)", None
        else:
            logged_json = body_json
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "http_method": self.command,
            "raw_path": logged_path,
            "service": service,
            "method": method,
            "query": {k: (["(redacted)"] if k.lower() in SECRET_QUERY else v)
                      for k, v in query.items()},
            "ambient_headers": ambient,
            "all_headers": dict(self.headers),
            "body_text": body_text[:MAX_BODY_LOG],
            "body_json": logged_json,
            "body_truncated": len(raw_body) > MAX_BODY_LOG,
            "client": self.client_address[0],
        }

        # Discord-Präsenz (presence.py): fragt der WASD-Helfer alle paar
        # Sekunden ab, daher ohne Konsole und Log
        if parts and parts[0] == "presence" and self.command == "GET":
            status, data = presence.answer(self.server.players, parts[-1] if len(parts) > 1 else "",
                                           self.client_address[0])
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # Ingame Market und Update-Countdown (UI-Patch 16.): die Spiel-UI
        # fragt regelmäßig, ohne Konsole und Log
        if parts and parts[0] in ("market", "notice"):
            self._market(parts, query, body_json)
            return
        if parts and parts[0] == "party":
            self._party(parts, query, body_json)
            return

        # Online-Punkt der Freundesliste (presence.friends_online, UI-Patch
        # 14.): fragt die Spiel-UI alle 30 s, ohne Konsole und Log
        if parts == ["friends", "online"] and self.command == "GET":
            try:
                aid = int((query.get("a") or ["0"])[0])
            except ValueError:
                aid = 0
            status, data = presence.friends_online(self.server.players, aid,
                                                   self.client_address[0])
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # 1. Konsole (kompakt): das, was man beim Client-Test live braucht.
        q = f"?{logged_qs}" if parsed.query else ""
        b = body_text[:300].replace("\n", " ")
        print(f"\n>>> {self.command} /{service}/{method}{q}", flush=True)
        if ambient:
            print(f"    headers t/i/h/rnd/n/g/v: {ambient}", flush=True)
        if b:
            print(f"    body: {b}", flush=True)

        # 2. JSONL-File (voll): die eigentliche Spezifikationsquelle.
        # (geschrieben jeweils NACH der Antwort, inkl. Response-Summary)
        def _log():
            log_line(self.server.log_path, entry)
        self._entry = entry  # für _safe_handle, falls die Spiellogik wirft

        # 3. Antwort bestimmen.
        key = f"{service}/{method}"
        account_state.SOURCE.value = key  # Kontobuch der Blings
        if (parts[0] in ("patcher", "launcher")  # Launcher: ohne Spieler
                or service == "PatcherService.hqs"):
            self._launcher(parts, query, body_json, entry)
            _log()
            return
        if parts[0] == "blings":  # Test-Shop im Browser-Overlay: Token in der URL
            self._bling_shop(parts, query, entry)
            _log()
            return
        if parts[0] == "admin":  # Webtool (admin_web), lokales Netz oder --admin-net
            self._admin_web(parts, query, body_json, entry)
            _log()
            return
        if service == "AdminService.hqs":  # GameplayToolbox, nur mit HMAC
            self._admin(method, query, body_json, entry)
            _log()
            return
        self._timed = True  # nur Spielanfragen in die Antwortzeit (server_stats)
        # Spieler = Sitzungs-Token im Header t (vom Launcher-Login, auth.py);
        # unbekannt oder abgemeldet -> InvalidConnectionTokenException wie
        # AuthenticationInterceptor (Code aus der Registrierung des Clients)
        player = self.server.players.for_token(self.headers.get("t"), self.client_address[0])
        if player is None:
            self._send_service_exception(
                "Contracts.Common.Exceptions.InvalidConnectionTokenException, Contracts.Common",
                0x80010004, "Invalid connection token", entry, 401)
            _log()
            return
        flags = anticheat.hack_flags(self.headers.get("rnd"))
        if flags != player.hack_flags:  # wie AntiCheatManager: nur Änderungen
            player.hack_flags = flags
            player.tracker.track(player.account_id, tracking.CLIENT_HACK,
                                 anticheat.hack_fields(flags))
            print(f"    [anticheat] {player.name}: ClientHackFlags {flags}", flush=True)
        presence.note(player, key, body_json, self.client_address[0])
        raids.VIEWER.value = player.account_id  # raid castles for this player's party
        self.server.iplog.seen(player.account_id, self.client_address[0])
        try:  # Header n = höchster beim Client verarbeiteter Notification-Index
            player.notifications.ack(int(self.headers.get("n", "0")))
        except ValueError:
            pass
        notify = player.notifications
        overrides = load_responses(self.server.responses_path)
        state = player.state
        account_state.SOURCE.value = f"{key} ({player.name})"
        now = datetime.datetime.now(datetime.timezone.utc)
        # Bann/Sperre (Admin-Webtool): Anfragen abweisen wie
        # ConnectionManager.EnsureTokenIsValid. Codes wie im finalen Client
        # (Fehler-Dialoge nach Code registriert, 0xdbfa20): 0x80020108 Bann,
        # 0x80020109 Sperre; die ältere Server-DLL hat noch 0x80020008/09.
        # Ausnahme GetAccountInformation: im Original lehnte schon der
        # Launcher-Login ab, der Client verträgt dort keinen Fehler (Assert in
        # AccountServerController, dann "Network error"); seine Ban-/Sperr-
        # Dialoge (Banned/SuspendedAccountArgoErrorHandler) kommen erst bei
        # Fehlern im laufenden Spiel
        sanction = state.sanction(now)
        if sanction and key != "AccountInformationService.hqs/GetAccountInformation":
            if sanction["Status"] == 2:
                self._send_service_exception("Exceptions.AccountBannedException",
                                             0x80020108, "Your account is banned", entry, 426)
            else:
                until = datetime.datetime.strptime(sanction["Until"], "%Y-%m-%dT%H:%M:%SZ")
                seconds = int((until.replace(tzinfo=datetime.timezone.utc) - now).total_seconds())
                self._send_service_exception(
                    "Exceptions.AccountSuspendedException", 0x80020109,
                    "Your account is suspended until %s" % sanction["Until"], entry, 427,
                    ExpirationTotalSeconds=seconds)
            _log()
            return
        state.seen(now)
        for name, fields in state.reload_targeted_attacks(now):
            notify.push(name, fields)
        for name, fields in state.expire_consumables(now):
            notify.push(name, fields)
        for name, fields in state.expire_mine_shields(now):
            notify.push(name, fields)
        for name, fields in state.material_mines(now):
            notify.push(name, fields)
        for name, fields in state.expire_shield(now):
            notify.push(name, fields)
        for name, fields in state.expire_delegation(now):
            notify.push(name, fields)
        for name, fields in state.free_trials(now):
            notify.push(name, fields)
        if key == "AccountInformationService.hqs/GetAccountInformation":
            state.expire_trials(now)
            # Rückkauf läuft wie im Original nur hier ab (TimeManager.Expire
            # bei GetAccountInformation); ein BuyBackRemoved mitten in der
            # Sitzung verwarf der Client samt Antwort ("Could not send battle
            # results")
            state.expire_buyback(now)
            # Saisonabrechnung steckt danach schon im Account (ohne Meldungen)
            self._check_season(state, None)
            state.produce_mines()
            state.expire_boosts()
            state.expire_news()
            state.unlock_region_objectives()
            state.fix_tutorial_level()
            payload = state.snapshot()
            # Freunde, die echte Spieler sind, mit aktuellem Stand (Level,
            # Kronen, angreifbar); gespeichert ist der vom Tag der Freundschaft
            payload["Friends"] = [
                self._summary(p) if p else f
                for f, p in ((f, self.server.players.by_account_id(f["Id"]))
                             for f in payload.get("Friends") or [])]
            # Clan-Zugehörigkeit: Account.Guild (zweiter Teil des
            # Account-Lesers im Client, 0x542170); fehlt sie, gilt man als
            # clanlos, obwohl der Clan einen als Mitglied führt
            guild = self.server.guilds.account_guild(payload["AccountId"])
            # Bling-Shop (game://shop/showprimaryshop): der Client öffnet die
            # Shop-Adressen im eingebauten Browser-Overlay
            # (UiSettings.PrimaryShopWebBrowserSettings); mit leerem
            # PrimaryShopUrl bleibt der Knopf wirkungslos. Test-Shop des Servers.
            url = bling_shop.shop_url(self._base_url(), self.headers.get("t", ""))
            for key in ("PrimaryShopUrl", "PrimaryShopBlingsUrl",
                        "PrimaryShopPremiumPurchaseUrl"):
                payload["ClientSettings"][key] = url
            # Chat (server/xmpp_server.py, Port 5222) auf dem Rechner, den
            # der Client für den Spielserver anspricht; Benutzer = Login-Name,
            # Passwort aus dem Sitzungs-Token (auth.chat_password, prüft
            # xmpp_server.session_valid)
            host = self.headers.get("Host", "").rsplit(":", 1)[0]
            if host:
                payload["ClientSettings"]["XmppInfo"].update(
                    Enabled=True, Server=host, Domain=host,
                    ConferenceServer="conference." + host, Username=player.name,
                    Password=auth.chat_password(self.headers.get("t", "")))
            if guild:
                payload["Guild"] = guild
            # Special Packs (Infinite Pack): Freischaltung und Kontingente der
            # Pack-Artikel, siehe special_packs.py
            payload.pop(state.CONSUMED, None)
            payload.pop(state.SANCTION, None)
            payload.pop(state.ACHIEVEMENT_BLINGS, None)
            payload.pop(loot.BLING_LOOT, None)
            payload.pop(state.PLAY_TIME, None)
            payload.pop(state.SALE, None)
            payload.pop(state.MINE_CLOCK, None)
            payload.pop(state.FORGE_MAIN_HAND, None)
            payload.pop(state.VALIDATION_DURATION, None)
            payload.pop(state.FREE_TRIALS, None)
            payload.pop(state.EXPIRED_TRIALS, None)
            # Zeitfenster des laufenden Helden-Trials (AccountInformationBase.
            # HeroFreeTrialInfoPeriod); der Client zeigt damit Hinweis und Shop
            trial = free_trials.active(now)
            if trial:
                payload["HeroFreeTrialInfoPeriod"] = {  # Id = Event (Basisklasse)
                    "$type": castles.T("HeroFreeTrialInfoPeriod"), "Id": trial["Id"],
                    "UnlockStartTime": free_trials.iso(trial["Start"]),
                    "UnlockEndTime": free_trials.iso(trial["End"])}
            payload.pop(state.VALID_BLUEPRINT, None)
            payload.pop(state.VALIDATION_DELEGATION, None)
            payload.pop(state.DATES, None)
            payload.pop(state.RATINGS, None)
            payload.pop(state.STARS, None)
            state.corpse_ages(payload)
            payload.pop(state.CORPSES, None)
            payload.pop(state.BUYBACK_DUE, None)
            payload.pop(competitions.SETTLED, None)
            payload["ShopSkuModifiers"] = state.shop_sku_modifiers()
            notify.reset(int(self.headers.get("n", "0") or 0))
            player.competitions_week = None
            player.tracker.track(player.account_id, tracking.LOGIN,
                                 {"ClientIp": self.client_address[0]})
        elif key == "ServerCommandService.hqs/SendCommands":
            if isinstance(body_json, dict):
                had_ticket = state.delegation() is not None
                for name, fields in state.apply(body_json.get("commands")):
                    if name == "ShowMoreCastle":
                        fields["AttackSelectionResult"] = self._attack_selection(
                            state, fields["RegionId"])
                    notify.push(name, fields)
                if not had_ticket:
                    self._request_guild_validation(player)
            payload = {}
        elif key == "ThemeService.hqs/SetCurrentTheme":
            theme = (body_json or {}).get("themeId") if isinstance(body_json, dict) else None
            if state.set_theme(theme):
                notify.push("ThemeSelected", {"ThemeId": theme})
            else:
                print(f"    [warn] Theme {theme} nicht freigeschaltet", flush=True)
            payload = {}
        elif key == "AccountService.hqs/ChooseDisplayName":
            name = (body_json or {}).get("displayName", "")
            # Regel wie AccountManager: 3-16 druckbare ASCII-Zeichen ohne
            # Leerzeichen und "@". Codes wie im finalen Client (Texte nach
            # Code bei 0xc2cc80 in MightyQuest_profile.exe): 0x8002010a Name
            # vergeben, 0x8002010c Leerzeichen/@, 0x80020110 gesperrter Name;
            # die alte DLL hat noch 0x80020010/12
            if not re.fullmatch(r"[\x21-\x3f\x41-\x7e]{3,16}", name or ""):
                self._send_service_exception(
                    "Exceptions.InvalidDisplayNameException",
                    0x8002010c, "Invalid display name", entry)
                _log()
                return
            if DISPLAY_NAME_BLOCKED.search(name):
                self._send_service_exception(
                    "Exceptions.InvalidDisplayNameException",
                    0x80020110, "This display name is restricted.", entry)
                _log()
                return
            if self._display_name_taken(name, state.snapshot()["AccountId"]):
                self._send_service_exception(
                    "Exceptions.AccountCreation.DisplayNameAlreadyExistsException",
                    0x8002010a, "The display name already exists.", entry)
                _log()
                return
            state.choose_display_name(name)
            payload = {}
        elif key == "HeroService.hqs/ChooseFirstHero":
            payload = state.choose_first_hero(
                int((body_json or {}).get("heroSpecContainerId", 2)))
        elif key == "CastleForSaleService.hqs/GetCastlesForSale":
            startup = query.get("startupCastle", ["false"])[0].lower() == "true"
            payload = castle_sale.castles_for_sale(startup)
        elif key == "CastleForSaleService.hqs/GetCastleForSaleBuildInfo":
            try:
                sale_id = int((query.get("castleForSaleId") or query.get("saleId")
                               or ["0"])[0])
            except ValueError:
                sale_id = 0
            payload = castle_sale.build_info(sale_id)
            if payload is None:
                print(f"    [warn] Kaufburg {sale_id} unbekannt", flush=True)
                payload = {}
        elif key == "AttackSelectionService.hqs/GetAttackSelectionList":
            try:
                n = int(query.get("maxSuggestionCountByLevel", ["10"])[0])
            except ValueError:
                n = 10
            try:
                region = int(query.get("attackRegionId", ["0"])[0])
            except ValueError:
                region = 0
            payload = self._attack_selection(state, region, n)
        elif key == "AttackSelectionService.hqs/GetCastleInfo":
            q = {k: int(v[0]) for k, v in query.items()
                 if v and v[0].lstrip("-").isdigit()}
            snap = state.snapshot()
            hero = next((h for h in snap["Heroes"]
                         if h["HeroSpecContainerId"] == snap["SelectedHeroId"]),
                        snap["Heroes"][0])
            delegated = self._validation_castle(q.get("castleId", 0), snap)
            payload = castles.castle_info(q.get("castleId", 0),
                                          castles.ATTACK_TYPE_VALIDATION if delegated
                                          else q.get("attackType", 0),
                                          q.get("attackSource", 0), hero["Level"],
                                          snap,
                                          state.castle_rating(q.get("castleId", 0)),
                                          state.castle_stars(q.get("castleId", 0)),
                                          self._last_seen(q.get("castleId", 0)),
                                          self.server.castle_stats.info(q.get("castleId", 0)),
                                          delegated)
            if payload is None:
                print(f"    [warn] Burg {q.get('castleId')} unbekannt", flush=True)
                payload = {}
        elif key == "AccountInformationService.hqs/GetPublicProfileById":
            aid = query.get("accountId", ["0"])[0]
            other = (self.server.players.by_account_id(int(aid))
                     if aid.isdigit() else None)
            fake = profiles.fake_account(int(aid)) if aid.isdigit() else None
            if other is not None:
                payload = profiles.public_profile(
                    other.state.snapshot(), self.server.guilds.header(other.account_id))
            elif fake is not None:
                payload = profiles.public_profile(
                    fake, self.server.guilds.header(fake["AccountId"]))
            else:
                print(f"    [warn] Profil {aid} unbekannt", flush=True)
                payload = {}
        elif key == "AccountInformationService.hqs/Search":
            body = body_json if isinstance(body_json, dict) else {}
            try:
                n = int(body.get("maxResult") or 20)
            except (TypeError, ValueError):
                n = 20
            payload = profiles.search(
                str(body.get("q") or ""), n,
                [p.state.snapshot() for p in self.server.players.all()],
                self.server.guilds.header)
        elif key == "FriendshipService.hqs/SendFriendshipInvitation":
            fid = (body_json or {}).get("friendAccountId", 0) if isinstance(body_json, dict) else 0
            other = self.server.players.by_account_id(fid)
            fake = profiles.fake_account(fid)
            player.tracker.track(player.account_id, tracking.FRIENDSHIP_INVITATION_SENT,
                                 {"FriendAccountId": fid})
            if other is not None and other.account_id != state.account["AccountId"]:
                self._invite(player, other)
            elif fake is not None:
                # Dummy-Spieler nehmen sofort an
                summary = profiles.account_summary(fake)
                events = state.add_friend(summary)
                if events:
                    # Der Client streicht bei FriendshipAdded die offene
                    # Einladung und asserted, wenn er keine kennt; also
                    # erst die eigene Einladung melden
                    notify.push("FriendshipInvitationUpdated", {
                        "FriendshipInvitation": self._invitation(summary, True)})
                for type_name, fields in events:
                    notify.push(type_name, fields)
            else:
                print(f"    [warn] Freundschaft mit {fid}: Spieler unbekannt", flush=True)
            payload = {}
        elif method in ("AcceptFriendshipInvitation", "DeclineFriendshipInvitation",
                        "CancelFriendshipInvitation") and service == "FriendshipService.hqs":
            fid = (body_json or {}).get("friendAccountId", 0) if isinstance(body_json, dict) else 0
            other = self.server.players.by_account_id(fid)
            self._answer_invitation(player, other, fid, method)
            if method != "AcceptFriendshipInvitation":  # Annehmen: Tracking 603 beim FriendshipAdded (wie Original)
                player.tracker.track(player.account_id, tracking.FRIENDSHIP_ANSWERED[method],
                                     {"FriendAccountId": fid})
            payload = {}
        elif key == "FriendshipService.hqs/RemoveFriendship":
            fid = (body_json or {}).get("friendAccountId", 0) if isinstance(body_json, dict) else 0
            # Keine FriendshipRemoved-Meldung an den Entfernenden: der Client
            # streicht den Freund schon bei Erfolg (OnRemoveFriendshipSuccess)
            # und asserted sonst "friend not found"; die Meldung gilt dem
            # Entfernten, wenn er ein echter Spieler ist
            state.remove_friend(int(fid))
            player.tracker.track(player.account_id, tracking.FRIENDSHIP_REMOVED,
                                 {"FriendAccountId": int(fid)})
            other = self.server.players.by_account_id(int(fid))
            if other is not None:
                other.state.remove_friend(player.account_id)
                other.notifications.push("FriendshipRemoved",
                                         {"FriendAccountId": player.account_id})
            payload = {}
        elif key == "GuildService.hqs/SendInviteRequest":
            # "Recruit": Dummy-Spieler treten sofort bei
            rid = (body_json or {}).get("requestAccountId", 0) if isinstance(body_json, dict) else 0
            if profiles.fake_account(rid) is None:
                print(f"    [warn] Clan-Einladung an {rid}: nur Dummy-Spieler", flush=True)
            elif self.server.guilds.add_member(state.account["AccountId"], rid,
                                               datetime.datetime.now(datetime.timezone.utc)
                                               .strftime("%Y-%m-%dT%H:%M:%SZ")):
                guild = self.server.guilds.account_guild(rid)
                notify.push("GuildMemberJoined", {"Guild": guild, "JoinerId": rid})
            payload = {}
        elif key == "GuildService.hqs/SendJoinRequest":
            b = body_json if isinstance(body_json, dict) else {}
            # Wie CreateGuild: ohne Clan-Objekt beendet sich der Client
            gid, me = int(b.get("guildId", 0) or 0), state.account["AccountId"]
            if self.server.guilds.join(gid, me,
                                       datetime.datetime.now(datetime.timezone.utc)
                                       .strftime("%Y-%m-%dT%H:%M:%SZ")):
                # Der Client liest Guild und JoinerId (Leser 0x94a580)
                info = self.server.guilds.guild_info(gid)
                notify.push("GuildMemberJoined", {"Guild": info, "JoinerId": me})
                for m in (info or {}).get("Members") or []:
                    mid = (m.get("AccountSummary") or {}).get("Id")
                    other = self.server.players.by_account_id(mid) if mid and mid != me else None
                    if other is not None:
                        other.notifications.push("GuildMemberJoined", {"Guild": info, "JoinerId": me})
            payload = self.server.guilds.guild_info(gid) or {}
        elif key == "GuildService.hqs/RemoveMember":
            b = body_json if isinstance(body_json, dict) else {}
            me, member = state.account["AccountId"], int(b.get("memberAccountId", 0) or 0)
            left = self.server.guilds.remove_member(me, member)
            if left and member == me:
                # Felder laut Client-Leser (0x7d1e70)
                notify.push("GuildLeft", {"GuildId": left[0], "GuildStillExists": left[1]})
            elif left:
                # Rauswerfen: GuildMemberLeft hat außer Index/NotificationType
                # nur Objektfelder (ToString 0xa69cf0) -- der Clan ohne das
                # Mitglied, wie Guild bei GuildMemberJoined
                notify.push("GuildMemberLeft", {"Guild": self.server.guilds.guild_info(left[0])})
            payload = {}
        elif key == "GuildService.hqs/UpdateMemberTitle":
            b = body_json if isinstance(body_json, dict) else {}
            res = self.server.guilds.set_title(state.account["AccountId"],
                                               int(b.get("memberAccountId", 0) or 0),
                                               int(b.get("newTitle", 0) or 0))
            if res:
                # Felder laut Client-Leser (0x94a660)
                for aid, title in res[1]:
                    notify.push("GuildMemberTitleUpdated",
                                {"AccountId": aid, "GuildId": res[0], "Title": title})
            payload = {}
        elif key == "AttackService.hqs/StartAttack":
            body = body_json if isinstance(body_json, dict) else {}
            payload = attack.start_attack(
                state.snapshot(), body, player.attack, state.attack_boosts(),
                self._validation_castle(body.get("castleAccountId"), state.snapshot()))
            if payload and payload["UbisoftCompetitionId"]:
                # eigene Bestzeit im Wettbewerb (0: noch keine)
                payload["UbisoftCompetitionBestTime"] = dict(self.server.competitions.ranking(
                    payload["UbisoftCompetitionId"])).get(state.account["AccountId"], 0)
            if payload and payload["IsTargetedAttack"]:
                for name, fields in state.use_targeted_attack(now):
                    notify.push(name, fields)
                payload["TargetedAttackAvailableCount"] = state.snapshot()[
                    "TargetedAttackAvailableCount"]
            if payload is None:
                print("    [warn] StartAttack: Burg unbekannt", flush=True)
                payload = {}
            # für das Replay: Burg und Held zum Angriffszeitpunkt
            player.attack.current["info"] = json.loads(json.dumps(payload))
        elif key == "LossService.hqs/RemoveShield":
            for name, fields in state.expire_shield(now, remove=True):
                notify.push(name, fields)
            # void: ein Result (ShieldInfo geraten) ließ den Client-Leser
            # scheitern ("Expected character: '}'")
            payload = {}
        elif key == "AttackService.hqs/RateCastle":
            payload, castle_id = attack.rate_castle(player.attack)
            rating = (body_json or {}).get("castleRating", 0) if isinstance(body_json, dict) else 0
            if castle_id is not None and rating:
                state.rate_castle(castle_id, rating)
            message = ((body_json or {}).get("message") or "").strip() if isinstance(body_json, dict) else ""
            if castle_id is not None and message:
                snap = state.snapshot()
                self.server.castle_stats.comment(
                    castle_id, body_json.get("attackId", ""), snap["AccountId"],
                    snap.get("AvatarId", 10), message)
            field = CURRENCY[payload["CurrencyType"]]
            delta = state.earn(field, payload["Amount"])
            notifications.wallet_updated(notify, delta)
            if castle_id is not None:
                player.tracker.track(player.account_id, tracking.CASTLE_RATING,
                                     {"CastleAccountId": castle_id, "Rating": rating,
                                      "Comment": message})
            player.tracker.track(player.account_id, tracking.CASTLE_RATING_PRIZE,
                                 {"WalletDelta": delta})
            print(f"    [state] Bewertungsprämie: +{payload['Amount']} {field}",
                  flush=True)
        elif key == "AttackService.hqs/Resurrect":
            payload, cost = attack.resurrect(player.attack)
            delta = state.spend("InGameCoin", cost)
            notifications.wallet_updated(notify, delta)
            player.tracker.track(player.account_id, tracking.RESURRECTION,
                                 {"Cost": cost, "WalletDelta": delta})
            print(f"    [state] Wiederbelebung: -{cost} InGameCoin", flush=True)
        elif key == "AttackService.hqs/EndAttack":
            params = (body_json or {}).get("endAttackParams") or {}
            attack_id = player.attack.current.get("attack_id", "")
            attack_info = player.attack.current.get("info")
            cheats = anticheat.end_attack_violations(params, player.attack.current)
            for msg in cheats:
                player.tracker.track(player.account_id, tracking.CHEAT_FAILURE,
                                     {"CheatContext": anticheat.CHEAT_CONTEXT_END_ATTACK,
                                      "Message": msg})
                print(f"    [anticheat] {player.name}: {msg}", flush=True)
            raid = ((player.attack.current or {}).get("castle") or {}).get("_Raid")
            raid_castle = ((player.attack.current or {}).get("castle") or {}).get("AccountId")
            payload, gains = attack.end_attack(state.snapshot(), params, player.attack)
            if raid:
                self.server.parties.raid_done(player.account_id, raid_castle)
                try:
                    self._raid_bonus(player, raid, gains)
                except Exception as e:  # noqa: BLE001 - never break EndAttack
                    print(f"    [raid] Bonus fehlgeschlagen: {e!r}", flush=True)
            # Kommentar des vorigen Angreifers (der eigene kommt erst mit RateCastle)
            payload["LastComment"] = self.server.castle_stats.last_comment(
                gains["castle_id"], castles.T, state.account.get("ProfanityFiltering", False))
            changed = state.credit_attack(gains)
            # kein Wettbewerbs-Rekord aus einem verdächtigen Kampf
            if (gains["competition"] and gains["completion_type"] == 0 and not cheats
                    and not gains["practice"] and gains["duration_ms"]):
                result = self.server.competitions.record(
                    gains["competition"], state.account["AccountId"], gains["duration_ms"])
                payload["IsUbisoftCompetitionValid"] = result["valid"]
                payload["IsNewUbisoftCompetitionLeader"] = result["new_leader"]
            if (not gains["practice"] and not gains["validation"]
                    and gains["castle_type"] == castles.CASTLE_TYPE_USER):
                won = gains["completion_type"] == 0
                self.server.castle_stats.record(gains["castle_id"], not won,
                                                gains["duration_ms"])
            if gains["trophy_record"]:
                state.set_trophy_record(gains["castle_id"], gains["trophy_record"])
            if gains["trophies"]:
                score = state.add_trophies(gains["trophies"])
                notifications.trophy_score_changed(notify, score)
                self._notify_friends(state.snapshot(), "FriendTrophyScoreChanged",
                                     {"TrophyScore": score})
            # Rache verbraucht; DefendLogEntryUpdatedNotification kennt der
            # finale Client nicht (kein Leser, Fehler beim Kampfende)
            if gains["revenge"]:
                state.use_revenge(gains["revenge"])
            defender = (gains["defense"] and not gains["validation"]
                        and self.server.players.by_account_id(gains["castle_id"]))
            if defender:
                gains["defense"]["entry"]["HasReplay"] = self.server.replays.store(
                    attack_id, replay, attack_info)
                self._record_defense(defender, gains["defense"], state.snapshot(),
                                     gains["trophies"])
            if gains["validation"] and gains["completion_type"] == 0:
                seconds = gains["duration_ms"] / 1000
                for name, fields in state.validate_draft(seconds):
                    notify.push(name, fields)
                notifications.draft_validated(notify, state.account["AccountId"], seconds)
            if gains["delegated"] and gains["completion_type"] == 0:
                won = self._complete_validation(player, gains)
                # ohne Erfolg hat ein anderer die Burg schon validiert
                payload["CompletionReward"] = gains["completion_reward"] if won else []
                payload["IsCompletionRewardMissed"] = bool(
                    gains["completion_reward"]) and not won
            notifications.wallet_updated(notify, changed["wallet"])
            for name, fields in changed["inventory"]:
                notify.push(name, fields)
            if changed["hero"]:
                notifications.hero_xp_changed(notify, changed["hero"], gains["Xp"],
                                              changed["level_changed"])
                self._hero_level_news(player, changed["hero"], gains["Xp"],
                                      changed["level_changed"])
            if not gains["practice"]:
                quest = state.complete_castle_objectives(gains)
                _notify_objectives(notify, quest)
                self._hero_level_news(player, quest["hero"], quest["xp"],
                                      quest["level_changed"])
            region = state.complete_boss_region(gains)
            if region:
                self._boss_news(player, gains["castle_id"], region[0])
                notifications.attack_region_completed(notify, *region[:2])
                for entry in region[2]:
                    notifications.objective_unlocked(notify, entry)
                print(f"    [state] Region {region[0]} abgeschlossen, "
                      f"frei: {region[1]}", flush=True)
            for type_name, fields in state.record_attack(gains, params):
                notify.push(type_name, fields)
            for spell in state.take_unlocked_spells():
                notifications.spell_unlocked(notify, spell)
            player.tracker.track(
                player.account_id,
                tracking.TEST_ATTACK if gains["practice"] else tracking.ATTACK,
                {"CastleAccountId": gains["castle_id"],
                 "CompletionType": gains["completion_type"],
                 "DurationMs": gains["duration_ms"],
                 "WalletDelta": changed["wallet"], "Xp": gains["Xp"],
                 "Trophies": gains["trophies"], "Items": len(gains["items"]),
                 "IsValidation": bool(gains["validation"])})
            print(f"    [state] Angriff: +{gains['InGameCoin']} Gold, "
                  f"+{gains['LifeForce']} Lebenskraft, +{gains['Xp']} XP, "
                  f"{len(gains['items'])} Items",
                  flush=True)
        elif key == "ObjectiveService.hqs/CompleteClientObjective":
            oid = (body_json or {}).get("objectiveId") if isinstance(body_json, dict) else None
            quest = state.complete_client_objective(oid)
            _notify_objectives(notify, quest)
            self._hero_level_news(player, quest["hero"], quest["xp"],
                                  quest["level_changed"])
            for spell in state.take_unlocked_spells():
                notifications.spell_unlocked(notify, spell)
            payload = {}
        elif key == "SeasonalCompetitionService.hqs/GetSeasonalCompetition":
            self._check_season(state, notify)
            payload = leagues.page(
                state.snapshot(), [p.state.snapshot() for p in self.server.players.all()],
                query, self.server.guilds.header)
            if payload["PreviousLeagueInfo"]:
                state.mark_season_viewed()
        elif key == "SeasonalCompetitionService.hqs/CheckSeasonalCompetitionRewards":
            self._check_season(state, notify)
            payload = {}
        elif key == "UbisoftCompetitionService.hqs/GetUbisoftCompetitionInfo":
            try:
                cid = int(query.get("ubisoftCompetitionId", ["0"])[0])
            except ValueError:
                cid = 0
            payload = self.server.competitions.info(
                cid, state.snapshot(), [p.state.snapshot() for p in self.server.players.all()],
                self.server.guilds.header)
            if payload is None:
                print(f"    [warn] Wettbewerb {cid} unbekannt", flush=True)
                payload = {}
        elif key == "UbisoftCompetitionService.hqs/CheckEndedUbisoftCompetitions":
            self._check_competitions(state, notify)
            payload = {}
        elif key == "NewsService.hqs/GetNews":
            payload = state.snapshot().get("News") or {}
        elif service == "GuildService.hqs" and method in (
                "CreateGuild", "UpdateGuild", "GetGuildById",
                "GetLeaderboardPage", "SearchGuilds", "Search", "GetBattleLog"):
            g, account = self.server.guilds, state.snapshot()
            body = body_json if isinstance(body_json, dict) else {}
            own = g.guild_of(account["AccountId"])
            error = method in ("CreateGuild", "UpdateGuild") and "displayName" in body and g.name_error(
                body["displayName"], own and own["Id"])
            if error:
                self._send_service_exception(error, 0x80020000, "Invalid guild display name", entry)
                _log()
                return
            if method == "CreateGuild":
                payload = g.create(account, body, datetime.datetime.now(
                    datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            elif method == "UpdateGuild":
                payload = g.update(account, body)
            elif method in ("GetGuildById", "GetBattleLog"):
                try:
                    gid = int((query.get("guildId") or [body.get("guildId", 0)])[0])
                except ValueError:
                    gid = 0
                payload = g.guild_info(gid) if method == "GetGuildById" else g.battle_log(gid)
            elif method == "GetLeaderboardPage":
                payload = g.leaderboard(account)
            else:
                payload = g.search()
            if payload is None:
                payload = {}
        elif service == "TrackingService.hqs":  # Track, TrackBatch
            player.tracker.track_client(player.account_id, body_json)
            payload = {}
        elif key in overrides:
            payload = overrides[key]
            if isinstance(payload, str) and payload.startswith("$file:"):
                # Große Stubs als Datei auslagern (Pfad relativ zum Repo-Root).
                ref = payload[len("$file:"):]
                try:
                    with open(ref, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                except Exception as e:
                    print(f"    [warn] Stub-Datei {ref} nicht ladbar: {e}", flush=True)
                    payload = {}
        elif key == "ReplayService.hqs/StartReplayAttack":
            aid = (body_json or {}).get("attackId", "") if isinstance(body_json, dict) else ""
            info = self.server.replays.load_info(aid) or {}
            if not info:
                print(f"    [warn] keine AttackInfo zum Replay {aid!r}", flush=True)
            # ohne Result-Hülle: der Client liest die Antwort direkt als
            # AttackInfo (MQLog: "Unhandled member [Result] in class [AttackInfo]")
            self._send_raw(_client_json(info),
                           "application/json; charset=utf-8", entry)
            _log()
            return
        elif (service in ("ReplayService.hqs",)
                or method in ("GetReplay", "GetAttackAntiCheatJob")):
            # GetReplay: Aufzeichnung als Stream (replays.py);
            # sonst StreamGet mit leerem octet-stream
            data = b""
            if service == "ReplayService.hqs":
                aid = (query.get("attackId") or [(body_json or {}).get("attackId", "")
                       if isinstance(body_json, dict) else ""])[0]
                data = self.server.replays.load(aid) or b""
                if not data:
                    print(f"    [warn] kein Replay zu {aid!r}", flush=True)
            self._send_bytes(data)
            print(f"    <- 200 application/octet-stream ({len(data)} Bytes, {key})", flush=True)
            entry["response"] = {"status": 200,
                                 "content_type": "application/octet-stream",
                                 "preview": f"{len(data)} Bytes"}
            _log()
            return
        elif not service and self.command == "GET":
            self._send_text("MQEL game server up. Siehe requests.log.jsonl\n")
            entry["response"] = {"status": 200, "content_type": "text/plain",
                                 "preview": "up"}
            _log()
            return
        else:
            payload = {}  # Default: leeres JSON-Objekt (nullable DTO-Felder -> Defaults)

        if key in UNWRAPPED:
            # liest das DTO direkt, ohne WrappedResponse: Notifications
            # bleiben für den nächsten Request liegen
            body = _client_json(payload)
            notes = globals_ = None
        elif self.headers.get("i") == "0":
            # Erste Anfrage eines frisch gestarteten Clients (Zähler i beginnt
            # bei 0). Im Original gehören Notifications zur Verbindung, eine
            # neue beginnt leer (NotificationManager.AddNotifications nur an
            # verbundene Sitzungen); Offenes steckt im gleich geladenen
            # Account. Beim Login kommt diese Anfrage (TrackingCommand)
            # gleichzeitig mit GetAccountInformation und hätte sonst die alten
            # Meldungen vor dessen reset ausgeliefert (doppelt angewendet)
            notify.reset(int(self.headers.get("n", "0") or 0))
            notes = []
        else:
            notes = player.notifications.outgoing()
        if notes is not None:
            globals_ = competitions.refreshed(player)
            body = _client_json(wrap_response(payload, notes, globals_))
        if notes:
            print(f"    [notify] {', '.join(n['$type'].split(',')[0].rsplit('.', 1)[-1] + '#' + str(n['Index']) for n in notes)}",
                  flush=True)
        self.send_response(200)
        # Exakt wie ASP.NET-Original (der Client kennt nur dieses Literal;
        # vgl. Binary-Strings). Bloßes "application/json" riskiert CT-Mismatch.
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 'sl' sendet auch das Original (Timing-Verschleierung, s. 30-protokoll)
        self.send_header("sl", str(random.randint(0, 50)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
        print(f"    <- 200 application/json ({key}): {body[:200].decode('utf-8', 'replace')}", flush=True)
        entry["response"] = {
            "status": 200,
            "content_type": "application/json; charset=utf-8",
            "preview": body[:150].decode("utf-8", "replace"),
        }
        _log()

    def _check_season(self, state, notify):
        """Saison-/Tageswertung abrechnen (leagues.settle), mit Meldungen an
        `notify` (None: steht schon im gleich gelieferten Account)."""
        result = leagues.settle(state.snapshot(),
                                [p.state.snapshot() for p in self.server.players.all()])
        if result is None:
            return
        wallet, decorations, news = state.settle_league(result)
        self._track_season(state, result, wallet)
        if result["League"]:
            self._notify_friends(state.snapshot(), "FriendLeagueUpdated", {
                "LeagueId": result["League"][0], "SubLeagueId": result["League"][1]})
        if notify is None:
            return
        if wallet:
            notifications.wallet_updated(notify, wallet)
        if decorations:
            notify.push("CastleInventoryChanged", {"Actions": [
                {"$type": castles.T("CastleInventoryAddedAction"), "Type": 1,
                 "Count": 1, "ItemType": 13, "SpecId": spec} for spec in decorations]})
        if result["League"]:
            notifications.league_updated(notify, result["League"])
        for item in news:
            notify.push("NewsAdded", {"NewsItem": item})

    def _track_season(self, state, result, wallet):
        """Liga-Auf-/Abstieg und Weltrangliste ins Tracking."""
        p = self.server.players.by_account_id(state.account["AccountId"])
        prev = result["Previous"]
        if result["League"] and prev:
            order = [(l["Id"], s["Id"]) for l in trophies.league_settings()["Leagues"]
                     for s in l["SubLeagues"]]
            old, new = (prev["LeagueId"], prev["SubLeagueId"]), tuple(result["League"])
            if old != new and old in order and new in order:
                p.tracker.track(p.account_id, tracking.LEAGUE_PROMOTED
                                if order.index(new) > order.index(old)
                                else tracking.LEAGUE_DEMOTED,
                                {"From": list(old), "To": list(new),
                                 "LeagueRank": prev["LeagueRank"],
                                 "WorldRank": prev["WorldRank"], "WalletDelta": wallet})
        for item in result["News"]:
            if item.get("WorldRank"):
                p.tracker.track(p.account_id, tracking.WORLD_LEADERS,
                                {"WorldRank": item["WorldRank"]})

    def _check_competitions(self, state, notify):
        """Beendete Wettbewerbe abrechnen (Edelsteine, News)."""
        result = self.server.competitions.settle(state.snapshot(), self.server.guilds.header)
        if not result["Ids"]:
            return
        wallet, news = state.settle_competitions(result)
        if wallet:
            notifications.wallet_updated(notify, wallet)
        for item in news:
            notify.push("NewsAdded", {"NewsItem": item})

    @staticmethod
    def _invitation(summary, owner):
        """FriendshipInvitation mit dem Spieler summary (AccountSummary);
        owner: aus Sicht des Einladenden."""
        return {"$type": castles.T("FriendshipInvitation"),
                "CreationDate": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "FriendAccountId": summary["Id"], "FriendAvatarId": summary["AvatarId"],
                "FriendDisplayName": summary["DisplayName"],
                "HasAccepted": False, "HasDeclined": False,
                "IsCastleAttackable": True, "IsInvitationOwner": owner,
                "LeagueId": summary["LeagueId"]}

    def _summary(self, p):
        a = p.state.snapshot()
        return profiles.account_summary(a, self.server.guilds.header(a["AccountId"]))

    def _invite(self, sender, other):
        """Einladung an einen echten Spieler: bei beiden offen eintragen,
        dem Eingeladenen FriendInvite melden (Feld Invitation, Typ 1). Hat
        der schon den Absender eingeladen, gilt das als Annahme; eine eigene
        offene Einladung (erneutes Senden) wird nur ersetzt."""
        found = sender.state.take_invitation(other.account_id)
        if found is not None and not found["IsInvitationOwner"]:
            other.state.take_invitation(sender.account_id)
            return self._befriend(sender, other)
        mine = self._invitation(self._summary(other), True)
        theirs = self._invitation(self._summary(sender), False)
        sender.state.add_invitation(mine)
        other.state.add_invitation(theirs)
        sender.notifications.push("FriendshipInvitationUpdated", {"FriendshipInvitation": mine})
        other.notifications.push("FriendInvite", {"Invitation": theirs})
        print(f"    [state] Einladung {sender.account_id} -> {other.account_id}", flush=True)

    def _real_friends(self, player):
        """Freunde von player, die echte Spieler sind."""
        friends = (self.server.players.by_account_id(f["Id"])
                   for f in player.state.snapshot().get("Friends") or [])
        return [f for f in friends if f is not None]

    @staticmethod
    def _friend_news(player, news_type, about, **fields):
        """News (Typ news_type) über den Spieler about an player. Der Client
        braucht alle Felder des Contracts (sonst Absturz beim Laden)."""
        news = player.state.add_news({
            "$type": castles.T(NEWS_DATA[news_type]), "Type": news_type,
            "RequiresUserAction": False, "FriendAccountId": about.account_id,
            "FriendAvatarId": about.state.account.get("AvatarId", 10),
            "FriendDisplayName": about.state.account["DisplayName"],
            "FriendSpecialPacks": [], **fields})
        player.notifications.push("NewsAdded", {"NewsItem": news})

    def _hero_level_news(self, player, hero, xp, level_changed):
        """Held hat mit dem Aufstieg den höchsten Helden eines Freundes
        überholt (NewsManager.OnHeroLevelUp: Level = dessen Höchstlevel + 1):
        der Freund bekommt HeroLevelUpFriend, der Spieler HeroLevelUpOwn
        (Vorlagen in TopView.html)."""
        if not hero or not level_changed:
            return
        old = loot.level_for_xp(hero["XP"] - xp)
        name = HERO_NAMES.get(hero["HeroSpecContainerId"], "")
        for friend in self._real_friends(player):
            theirs = max((h["Level"] for h in friend.state.snapshot()["Heroes"]), default=None)
            if theirs is not None and old <= theirs < hero["Level"]:
                data = {"HeroName": name, "HeroLevel": hero["Level"],
                        "HeroSpecContainerId": hero["HeroSpecContainerId"]}
                self._friend_news(friend, NEWS_HERO_LEVEL_UP_FRIEND, player, **data)
                self._friend_news(player, NEWS_HERO_LEVEL_UP_OWN, friend, **data)

    def _boss_news(self, player, castle_id, region_id):
        """Bosssieg: Freunde bekommen BossKilledFriend mit dem Namen des
        Bosses (Besitzername der Boss-Burg)."""
        boss = castles.find_castle(castle_id) or {}
        for friend in self._real_friends(player):
            self._friend_news(friend, NEWS_BOSS_KILLED_FRIEND, player,
                              BossName=boss.get("AccountDisplayName", ""),
                              BossLevel=boss.get("Level", 1), AttackRegionId=region_id)

    def _befriend(self, a, b):
        """Freundschaft zwischen zwei echten Spielern: beide eintragen, je
        FriendshipAdded (und Errungenschaften) an beide."""
        for me, friend in ((a, b), (b, a)):
            for type_name, fields in me.state.add_friend(self._summary(friend)):
                me.notifications.push(type_name, fields)

    def _answer_invitation(self, player, other, fid, method):
        """Annehmen/Ablehnen (durch den Eingeladenen) oder Zurückziehen
        (durch den Einladenden): Einladung bei beiden austragen; der andere
        bekommt FriendshipAdded bzw. FriendshipInvitationDeclined/Cancelled."""
        if player.state.take_invitation(fid) is None:
            print(f"    [warn] {method}: keine Einladung mit {fid}", flush=True)
            return
        if other is None:
            return
        other.state.take_invitation(player.account_id)
        if method == "AcceptFriendshipInvitation":
            self._befriend(player, other)
        else:
            name = ("FriendshipInvitationDeclined" if method == "DeclineFriendshipInvitation"
                    else "FriendshipInvitationCancelled")
            other.notifications.push(name, {"FriendAccountId": player.account_id})
        print(f"    [state] {method}: {player.account_id} / {fid}", flush=True)

    def _attack_selection(self, state, region, n=10):
        """Burgauswahl der Region für GetAttackSelectionList und den Reroll
        (ShowMoreCastle)."""
        snap = state.snapshot()
        payload = castles.attack_selection(
            n, snap.get("CompletedAssignments") or [], region,
            (snap.get("CastleRerolls") or {}).get(str(region), 0),
            [f["Id"] for f in snap.get("Friends") or []], snap["AccountId"],
            competitions.current_ids(),
            castles.validation_castles(snap["AccountId"], self._may_validate(snap)),
            hero_level=next((h["Level"] for h in snap.get("Heroes") or []
                             if h["HeroSpecContainerId"] == snap.get("SelectedHeroId")), None))
        boss = [payload["BossCastle"]] if payload["BossCastle"] else []
        for group in payload["CastlesByLevel"] + [{"Castles": boss}]:
            for c in group["Castles"]:
                cid = c["DefenderAccountSummary"]["Id"]
                c["LastComment"] = self.server.castle_stats.last_comment(
                    cid, castles.T, snap.get("ProfanityFiltering", False))
                if c.get("CastleType") == castles.CASTLE_TYPE_USER:
                    # wie AttackSelectionManager: Sperre und beste Sterne darin
                    since, best = trophies.gain_cooldown(snap, cid)
                    c["TrophyCooldownTimer"] = since or trophies.NEVER
                    c["VictoryConditionLevel"] = best
                else:
                    c["VictoryConditionLevel"] = state.castle_stars(cid)
        return payload

    def _may_validate(self, viewer):
        """Prüfung für castles.validation_castle(s): darf viewer die Burg
        des Besitzers validieren? Clan-Ticket nur im selben Clan."""
        guild = self.server.guilds.guild_of(viewer["AccountId"])

        def may(owner_id, guild_only):
            return not guild_only or bool(guild and any(
                m["AccountId"] == owner_id for m in guild["Members"]))
        return may

    def _validation_castle(self, castle_id, viewer):
        """Burg castle_id im Stand ihres Validierungs-Tickets, wenn viewer
        sie validieren darf, sonst None."""
        owner = isinstance(castle_id, int) and self.server.players.by_account_id(castle_id)
        return owner and castles.validation_castle(
            owner.state.snapshot(), viewer["AccountId"], self._may_validate(viewer))

    def _request_guild_validation(self, player):
        """Neues Clan-Ticket: die Clanmitglieder bekommen
        CastleValidationRequested (Feld laut Strings bei
        CastleValidationRequestedNotification.cpp)."""
        ticket = player.state.delegation()
        guild = ticket and ticket["Guild"] and self.server.guilds.guild_of(player.account_id)
        for m in (guild or {}).get("Members", []):
            other = (m["AccountId"] != player.account_id
                     and self.server.players.by_account_id(m["AccountId"]))
            if other:
                other.notifications.push("CastleValidationRequested",
                                         {"RequestorAccountId": player.account_id})

    def _complete_validation(self, validator, gains):
        """Sieg in einer fremden Burg mit Validierungs-Ticket: Burg des
        Besitzers validiert (Meldungen an ihn), der Validierer bekommt die
        CompletionReward (nur beim bezahlten Ticket). False, wenn das Ticket
        nicht mehr offen war."""
        owner = self.server.players.by_account_id(gains["castle_id"])
        events = owner.state.complete_delegation(gains["duration_ms"] / 1000) if owner else []
        if not events:
            return False
        for name, fields in events:
            owner.notifications.push(name, fields)
        for reward in gains["completion_reward"]:
            notifications.wallet_updated(validator.notifications, validator.state.earn(
                reward["CurrencyType"], reward["Amount"]))
        print(f"    [state] {validator.account_id} validiert Burg {owner.account_id}",
              flush=True)
        return True

    def _notify_friends(self, account, name, fields):
        """Meldung über account an seine Freunde (echte Spieler), wie
        NotificationManager.OnTrophyScoreChanged/OnLeagueUpdated im Original
        (FriendAccountId = account)."""
        for f in account.get("Friends") or []:
            friend = self.server.players.by_account_id(f["Id"])
            if friend:
                friend.notifications.push(name, dict(fields, FriendAccountId=account["AccountId"]))

    def _record_defense(self, defender, defense, attacker, attacker_trophies):
        """Folgen eines Angriffs für den Besitzer der Spielerburg: Spielstand
        (record_defense) und Meldungen an ihn, sichtbar beim nächsten
        Request seines Clients."""
        before = self._defend_log_ids(defender)
        entry, score, corpses, deltas, notes = defender.state.record_defense(
            defense, profiles.account_summary(
                attacker, self.server.guilds.header(attacker["AccountId"])))
        self._record_guild_battle(entry, defender.state.snapshot(), attacker_trophies)
        stats = self.server.castle_stats.info(defender.account_id)
        defender.notifications.push("CastleAttacked", {
            "AttackCount": stats["AttackCount"], "DeathCount": defense["deaths"],
            "DefendLogEntry": entry, "HeroCorpses": corpses,
            "SuccessfulAttackCount": stats["SuccessfulAttackCount"],
            "WinRatio": stats["WinRatio"], "WinRatioDifficulty": stats["WinRatioDifficulty"]})
        if score is not None:
            notifications.trophy_score_changed(defender.notifications, score)
            self._notify_friends(defender.state.snapshot(), "FriendTrophyScoreChanged",
                                 {"TrophyScore": score})
        notifications.wallet_updated(defender.notifications, deltas)
        for name, fields in notes:
            defender.notifications.push(name, fields)
        if defense["shield"]:
            for name, fields in defender.state.add_shield(
                    defense["shield"], datetime.datetime.now(datetime.timezone.utc)):
                defender.notifications.push(name, fields)
        self.server.replays.remove(before - self._defend_log_ids(defender))

    def _record_guild_battle(self, entry, defender, attacker_trophies):
        """Verteidigungslog-Eintrag als BattleLogEntry (Felder laut Leser des
        finalen Clients) in die Clan-Kampflogs beider Seiten."""
        summary = profiles.account_summary(
            defender, self.server.guilds.header(defender["AccountId"]))
        battle = {k: v for k, v in entry.items() if k not in (
            "$type", "Level", "TrophyScoreVariation",
            "RevengeEnabled", "AttackerCastleLevel")}
        battle.update({
            "$type": castles.T("BattleLogEntry"), "HeroLevel": entry.get("Level", 1),
            "DefenderAccountSummary": summary,
            "CastleLevel": summary["CastleLevel"],
            "AttackerTrophyScoreVariation": attacker_trophies or 0,
            "DefenderTrophyScoreVariation": entry.get("TrophyScoreVariation", 0)})
        self.server.guilds.record_battle(battle)

    @staticmethod
    def _defend_log_ids(player):
        return {e.get("AttackId") for e in
                (player.state.snapshot().get("DefendLog") or {}).get("DefendLogEntries") or []}

    def _last_seen(self, castle_id):
        """LastSeenOnline des Burgbesitzers, wenn er ein echter Spieler ist."""
        c = castles.find_castle(castle_id)
        p = c and self.server.players.by_account_id(c.get("AccountId"))
        return p.state.snapshot().get("LastSeenOnline") if p else None

    def _send_bytes(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("sl", str(random.randint(0, 50)))
        self.end_headers()
        self.wfile.write(data)

    def _bling_shop(self, parts, query, entry):
        token = (query.get("t") or [""])[0]
        p = self.server.players.for_token(token)  # nur angemeldete Spieler
        if p is None:  # Bling-Shop im Spiel (UI-Patch 16.): Web-Token des Ingame Market
            p = self.server.market.player_for(token)
        if p is None:
            self._send_text("Unbekannter Spieler.\n")
            entry["response"] = {"status": 200, "content_type": "text/plain",
                                 "preview": "unknown"}
            return
        message = ""
        catalog = balance.enabled()
        if catalog and parts[-1] == "buy_pack":
            account_state.SOURCE.value = "bling-shop (%s)" % p.name  # Kontobuch
            try:
                pid = int((query.get("id") or ["0"])[0])
            except ValueError:
                pid = 0
            if pid == bling_shop.HERO_PACK_ID:
                price = (bling_shop.hero_pack(p.state.missing_heroes()) or (None,))[0]
            else:
                price = dict(bling_shop.offers(
                    patcher.seasonal_event(datetime.date.today()))).get(pid)
            if price is None:
                message = "This pack is not offered."
            else:
                result = (p.state.buy_hero_pack(price) if pid == bling_shop.HERO_PACK_ID
                          else p.state.buy_special_pack(pid, price))
                for name, fields in p.state.take_pack_events():
                    p.notifications.push(name, fields)
                if result == "ok":
                    p.tracker.track(p.account_id, tracking.SPECIAL_PACK_PURCHASED,
                                    {"SpecialPackId": pid, "Blings": price})
                    print(f"    [state] Bling-Shop: Pack {pid} für {price} Blings "
                          f"an {p.name!r}", flush=True)
                message = {"ok": "Purchased. Restart the game to see castle items and "
                                 "shop unlocks.",
                           "owned": "You already own this pack.",
                           "blings": "Not enough blings."}[result]
                if pid == bling_shop.HERO_PACK_ID and result == "ok":
                    message = "Purchased. Your new heroes are ready in the hero selection."
        elif catalog:
            pass  # kostenlose Test-Buchungen nur ohne Bling-Wirtschaft
        elif parts[-1] == "buy":
            try:
                amount = int((query.get("amount") or ["0"])[0])
            except ValueError:
                amount = 0
            if amount in bling_shop.PACKS:
                delta = p.state.earn("PremiumCash", amount)
                notifications.wallet_updated(p.notifications, delta)
                p.tracker.track(p.account_id, tracking.PREMIUM_CASH_PURCHASED,
                                {"Amount": amount, "WalletDelta": delta, "TestShop": True})
                message = "%d Blings gutgeschrieben." % amount
                print(f"    [state] Test-Shop: +{amount} PremiumCash für {p.name!r}",
                      flush=True)
        elif parts[-1] == "pack":
            event_pack = bling_shop.EVENT_PACKS.get(
                patcher.seasonal_event(datetime.date.today()))
            if event_pack and (query.get("id") or [""])[0] == str(event_pack[0]):
                if event_pack[0] not in p.state.snapshot().get("SpecialPacks", []):
                    p.tracker.track(p.account_id, tracking.SPECIAL_PACK_PURCHASED,
                                    {"SpecialPackId": event_pack[0], "TestShop": True})
                message = ("%s freigeschaltet. Bitte das Spiel neu starten, damit "
                           "Burginventar und Themen es zeigen."
                           if p.state.grant_special_pack(event_pack[0])
                           else "%s ist schon freigeschaltet.") % event_pack[1]
        elif parts[-1] == "infinite":
            if p.state.grant_special_pack(special_packs.infinite_pack_id()):
                p.tracker.track(p.account_id, tracking.SPECIAL_PACK_PURCHASED,
                                {"SpecialPackId": special_packs.infinite_pack_id(),
                                 "TestShop": True})
                message = ("Infinite Pack freigeschaltet. Bitte das Spiel neu "
                           "starten, damit der Shop es anzeigt.")
            else:
                message = "Infinite Pack ist schon freigeschaltet."
        for name, fields in p.state.take_pack_events():  # Test-Shop-Packs
            p.notifications.push(name, fields)
        if message:
            # Nach dem Buchen auf die Shop-Seite umleiten, damit Neuladen
            # nicht noch einmal bucht
            self.send_response(303)
            self.send_header("Location", "/blings?" + urllib.parse.urlencode(
                {"t": token, "m": message}))
            self.send_header("Content-Length", "0")
            self.end_headers()
            entry["response"] = {"status": 303, "content_type": "",
                                 "preview": message}
            return
        message = (query.get("m") or [""])[0]
        account = p.state.snapshot()
        if catalog:
            data = bling_shop.catalog_page(
                account.get("DisplayName"), token, account["Wallet"]["PremiumCash"],
                account.get("SpecialPacks", []),
                patcher.seasonal_event(datetime.date.today()), message,
                bling_shop.hero_pack(p.state.missing_heroes())).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            entry["response"] = {"status": 200, "content_type": "text/html",
                                 "preview": message or "catalog"}
            return
        owned = account.get("SpecialPacks", [])
        event_pack = bling_shop.EVENT_PACKS.get(
            patcher.seasonal_event(datetime.date.today()))
        data = bling_shop.page(account.get("DisplayName"), token,
                               account["Wallet"]["PremiumCash"], message,
                               special_packs.infinite_pack_id() in owned,
                               event_pack, bool(event_pack) and event_pack[0] in owned
                               ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        entry["response"] = {"status": 200, "content_type": "text/html",
                             "preview": message or "shop"}

    def _launcher(self, parts, query, body, entry):
        """Patcher-Dienst, Paket-Downloads und Login-Seite des Launchers
        (patcher.py)."""
        today = datetime.date.today()
        if parts[0] == "launcher":
            if parts[-1] == "background.png":
                with open(patcher.BACKGROUND, "rb") as f:
                    return self._send_raw(f.read(), "image/png", entry)
            if parts[-1] == "maintenance":
                # MaintenanceModeVerificationUrl: TaskCheckMaintenance zeigt bei
                # jedem Status außer 200 LocalLauncher/launcher-maintenance.html
                # (Antwort-Handler 0x4d6813 in PublicLauncher.exe, Body egal)
                on = self.server.admin.maintenance
                self.send_response(503 if on else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                entry["response"] = {"status": 503 if on else 200, "content_type": "",
                                     "preview": "maintenance" if on else "online"}
                return
            if parts[-1] == "steam":
                return self._launcher_steam(entry)
            if parts[-1] == "steamnew":
                result = self._launcher_steam_new(body if isinstance(body, dict) else {})
                return self._send_raw(json.dumps(result).encode("utf-8"),
                                      "application/json; charset=utf-8", entry)
            if parts[-1] in ("login", "register"):
                result = self._launcher_login(parts[-1], body if isinstance(body, dict) else {})
                return self._send_raw(json.dumps(result).encode("utf-8"),
                                      "application/json; charset=utf-8", entry)
            cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie["t"].value if "t" in cookie else None
            page = patcher.login_page(self.server.players.auth.resolve(
                urllib.parse.unquote(token) if token else None), self.server.news.html())
            return self._send_raw(page.encode("utf-8"), "text/html; charset=utf-8", entry)
        if parts[1:2] == ["files"]:
            data = patcher.archive_by_name(parts[-1], today)
            if data is None:
                self.send_error(404)
                entry["response"] = {"status": 404}
                return
            return self._send_raw(data, "application/octet-stream", entry)
        method = parts[-1]
        base = self._base_url() + "/patcher"
        if method in ("GetRMLauncherAndPackagesVersion", "GetRMPackagesVersion"):
            client, machine = patcher.parse_client_packages(query, body)
            build = (patcher.launcher_and_packages
                     if method == "GetRMLauncherAndPackagesVersion"
                     else patcher.server_packages)
            payload = build(client, base, today, machine)
        elif method in ("GetRMLauncherVersion", "GetRMLauncherVersionV2"):
            payload = patcher.launcher_patch()
        elif method == "HealthCheck":
            payload = True
        else:
            payload = {}
        self._send_raw(json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8", entry)

    def _launcher_login(self, action, body):
        """Anmeldung/Registrierung der Login-Seite: {"Token", "Name"} oder
        {"Error": Schlüssel (übersetzt die Seite), bei Sperre "Until"}.
        Bann/Sperre lehnt hier ab -- das Spiel selbst zeigt dafür nur
        "Network Error" (im Original prüfte auch der Login)."""
        players, auth_ = self.server.players, self.server.players.auth
        name = str(body.get("name") or "").strip()
        password = str(body.get("password") or "")
        known = name in players.index
        taken = any(n.casefold() == name.casefold() for n in players.index)
        if self.server.admin.maintenance and not auth_.is_admin(name):
            return {"Error": "maintenance"}  # Admins dürfen zum Testen rein
        try:
            if action == "register":
                if not auth.NAME_RE.fullmatch(name):
                    return {"Error": "name_invalid"}
                if taken or auth_.has_password(name):
                    return {"Error": "name_taken"}
                others = self.server.iplog.may_register(self.client_address[0])
                if others:  # schon ein Account von dieser IP (nicht freigegeben)
                    self.server.iplog.refused(self.client_address[0], name, others)
                    return {"Error": "multi_account"}
                auth_.set_password(name, password)
                players.get(name, self.client_address[0])  # Account anlegen
            elif not known:
                return {"Error": "bad_login"}
            elif self._sanction_error(name):  # vor dem ersten Passwort
                return self._sanction_error(name)
            elif not auth_.has_password(name):
                auth_.set_password(name, password)  # Altspieler: erstes Passwort
            elif not auth_.check(name, password, self.client_address[0]):
                return {"Error": "bad_login"}
            if body.get("proof"):  # Steam-Spieler: Account mit der SteamID verknüpfen
                auth_.link_steam(name, str(body["proof"]))
        except auth.AuthError as e:
            return {"Error": str(e)}
        self.server.iplog.seen(players.index.get(name), self.client_address[0])
        return {"Token": auth_.login(name), "Name": name}

    def _launcher_steam(self, entry):
        """Steam-Anmeldung der Login-Seite: Ziel des versteckten Formulars,
        das der Steam-Launcher mit steam_ticket abschickt. Antwort ist eine
        Seite im versteckten Iframe, die das Ergebnis an die Login-Seite
        weitergibt ({"SteamId"} oder {"Error"})."""
        auth_ = self.server.players.auth
        ticket = (self._form.get("steam_ticket") or [""])[0]
        key = "steam:" + self.client_address[0]  # jede Prüfung ruft Steam auf
        try:
            if auth_.throttle.blocked(key):
                raise steam_auth.SteamError("too_many_attempts")
            try:
                steam_id = steam_auth.verify(ticket)
            except steam_auth.SteamError as e:
                if str(e) not in ("steam_disabled", "steam_no_ticket", "steam_busy"):
                    auth_.throttle.fail(key)
                raise
            name = auth_.by_steam(steam_id)
            if name:
                result = self._launcher_session(name)
            else:  # neuer Spieler oder Altspieler, der seinen Account verknüpft
                result = {"Proof": auth_.steam_proof(steam_id)}
        except steam_auth.SteamError as e:
            result = {"Error": str(e)}
        page = ("<!doctype html><script>parent.steamResult(%s);</script>"
                % json.dumps(result).replace("<", "\\u003c"))
        self._send_raw(page.encode("utf-8"), "text/html; charset=utf-8", entry)

    def _launcher_steam_new(self, body):
        """Neuer Spieler per Steam: Account mit Namen vom Steam-Profil, ohne
        Passwort. body: {"proof"} der geprüften SteamID."""
        players, auth_ = self.server.players, self.server.players.auth
        proof = str(body.get("proof") or "")
        steam_id = auth_.steam_proof_id(proof)
        if steam_id is None:
            return {"Error": "steam_expired"}
        if self.server.admin.maintenance:
            return {"Error": "maintenance"}
        taken = lambda n: (n in players.index or auth_.has_password(n)
                           or any(x.casefold() == n.casefold() for x in players.index))
        name = steam_auth.account_name(steam_auth.persona(steam_id), steam_id, taken)
        others = self.server.iplog.may_register(self.client_address[0])
        if others:
            self.server.iplog.refused(self.client_address[0], name, others)
            return {"Error": "multi_account"}
        try:
            auth_.steam_create(name, proof)
        except auth.AuthError as e:
            return {"Error": str(e)}
        players.get(name, self.client_address[0])  # Account anlegen
        self.server.iplog.seen(players.index.get(name), self.client_address[0])
        return {"Token": auth_.login(name), "Name": name}

    def _launcher_session(self, name):
        """Sitzung für einen bekannten Spieler ohne Passwortprüfung (Steam):
        {"Token", "Name"} oder {"Error"} bei Wartung, Bann, Sperre."""
        auth_ = self.server.players.auth
        if self.server.admin.maintenance and not auth_.is_admin(name):
            return {"Error": "maintenance"}
        if name in self.server.players.index and self._sanction_error(name):
            return self._sanction_error(name)
        self.server.players.get(name, self.client_address[0])
        self.server.iplog.seen(self.server.players.index.get(name), self.client_address[0])
        return {"Token": auth_.login(name), "Name": name}

    def _sanction_error(self, name):
        """Fehler der Login-Seite zu Bann/Sperre des Spielers oder None."""
        now = datetime.datetime.now(datetime.timezone.utc)
        sanction = self.server.players.get(name).state.sanction(now)
        if not sanction:
            return None
        if sanction["Status"] == 2:
            return {"Error": "banned"}
        return {"Error": "suspended", "Until": sanction["Until"]}

    def _admin(self, method, query, body, entry):
        """AdminService.hqs (admin.py): ohne gültige HMAC-Signatur 404 wie
        der private Dienst des Originals."""
        if not admin.authorized(self.server.admin_keys,
                                admin.path_and_query(self.path), self.command,
                                self.headers):
            self._send_admin_error(404, "Not found", entry)
            return
        try:
            result = self.server.admin.call(method, query, body)
        except admin.AdminError as e:
            self._send_admin_error(e.status, str(e), entry)
            return
        if result is None:
            self._send_raw(b"", "application/json", entry)
        else:
            self._send_raw(json.dumps(result).encode("utf-8"), "application/json", entry)

    def _admin_web(self, parts, query, body, entry):
        """/admin: Seite server/admin/index.html; /admin/api/<Methode>:
        AdminService-Methode, Argumente aus Query bzw. JSON-Body, Antwort JSON
        (Fehler: {"Error": Text}); /admin/session: Anmeldung (Cookie admin_t).
        Zugang s. admin_web_allowed; sobald es einen Admin gibt
        (auth.set_admin) nur mit Anmeldung."""
        if not admin_web_allowed(self.client_address[0],
                                 isinstance(self.connection, ssl.SSLSocket),
                                 self.server.players.auth.has_admins(),
                                 self.server.admin_nets):
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            entry["response"] = {"status": 403, "content_type": "", "preview": "extern"}
            return
        auth_ = self.server.players.auth
        cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie["admin_t"].value if "admin_t" in cookie else ""
        if parts[1:2] == ["session"]:  # Anmeldung am Webtool (auth.admin_login)
            body = body if isinstance(body, dict) else {}
            if self.command == "POST" and body.get("action") == "login":
                try:
                    token = auth_.admin_login(str(body.get("name") or ""),
                                              str(body.get("password") or ""),
                                              self.client_address[0]) or ""
                except auth.AuthError:
                    return self._send_admin_json(429, {"Error": "Too many failed attempts, wait a minute"}, entry)
                if not token:
                    return self._send_admin_json(401, {"Error": "Wrong name or password, or no admin"}, entry)
            elif body.get("action") == "logout":
                auth_.admin_logout(token)
                token = ""
            # sonst nur Abfrage: wer ist angemeldet
            return self._send_admin_json(200, {"Name": auth_.admin_resolve(token),
                                               "Required": auth_.has_admins()}, entry,
                                         cookie=token if body.get("action") else None)
        if len(parts) >= 3 and auth_.has_admins() and not auth_.admin_resolve(token):
            # Ohne Admin bleibt das Webtool offen, damit man den ersten ernennen kann
            return self._send_admin_json(401, {"Error": "Login required"}, entry)
        if len(parts) < 3 or parts[1] != "api":
            with open(ADMIN_PAGE, "rb") as f:
                self._send_raw(f.read(), "text/html; charset=utf-8", entry)
            entry["response"] = {"status": 200, "content_type": "text/html",
                                 "preview": "admin"}
            return
        status = 200
        try:
            result = self.server.admin.call(parts[2], query, body)
        except admin.AdminError as e:
            status, result = e.status, {"Error": str(e)}
        self._send_admin_json(status, result, entry)

    def _send_admin_json(self, status, result, entry, cookie=None):
        """JSON-Antwort des Webtools; cookie: neues Webtool-Token ("" löscht)."""
        data = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cookie is not None:
            # Secure bei HTTPS: Cookies gelten für alle Ports des Hosts, sonst
            # ginge es auch an den Klartext-Port
            self.send_header("Set-Cookie", "admin_t=%s; Path=/admin; HttpOnly; SameSite=Strict%s%s"
                             % (cookie, "" if cookie else "; Max-Age=0",
                                "; Secure" if isinstance(self.connection, ssl.SSLSocket) else ""))
        self.end_headers()
        self.wfile.write(data)
        entry["response"] = {"status": status, "content_type": "application/json",
                             "preview": data[:150].decode("utf-8", "replace")}

    def _send_admin_error(self, status, message, entry):
        """ServiceException für Util.Client der Toolbox: wertet den Body nur
        bei Content-Type genau application/json aus."""
        # ServiceException ist abstrakt: konkreter Typ aus Contracts.Common
        kind = "NotFoundException" if status == 404 else "InvalidParameterException"
        data = json.dumps({"$type": "Contracts.Common.Exceptions.%s, Contracts.Common" % kind,
                           "Code": 0, "ErrorMessage": message,
                           "HttpStatusCode": status}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f"    <- {status} {message}", flush=True)
        entry["response"] = {"status": status, "content_type": "application/json",
                             "preview": message}

    def _send_raw(self, data, content_type, entry):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f"    <- 200 {content_type} ({len(data)} Bytes)", flush=True)
        entry["response"] = {"status": 200, "content_type": content_type,
                             "preview": data[:150].decode("utf-8", "replace")
                             if content_type.startswith(("application/json", "text"))
                             else ""}

    def _display_name_taken(self, name, own_id):
        """Anzeigename schon vergeben (ohne Groß-/Kleinschreibung) an einen
        anderen Spieler oder einen Ersatzspieler."""
        name = name.strip().casefold()
        others = [p.state.snapshot() for p in self.server.players.all()]
        names = [a.get("DisplayName") or "" for a in others
                 if a.get("AccountId") != own_id]
        names += [c["AccountDisplayName"] for c in castles.fake_player_castles()]
        return any(n.strip().casefold() == name for n in names)

    def _send_service_exception(self, type_name, code, message, entry, status=400, **extra):
        """ServiceException als JSON-Fehler (docs/30-protokoll.md, Fehler).
        Der Client liest bei jedem Status außer 503 den Body als
        ServiceException und nimmt deren Code als Task-Fehler (0x115f2d0);
        Code und Status laut <exception>-Doku der Contracts-XML."""
        full = type_name if "," in type_name else castles.T(type_name)
        data = json.dumps({"$type": full, "Code": code,
                           "ErrorMessage": message,
                           "Message": message, "HttpStatusCode": status,
                           **extra}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f"    <- {status} {type_name}", flush=True)
        entry["response"] = {"status": status, "content_type": "application/json",
                             "preview": type_name}

    def _market_reply(self, status, obj):
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        # marker for the UI mods (ingame_market.html, party.html): they only
        # keep an address whose reply carries it, so another program on
        # 127.0.0.1:8081 of the player's PC isn't taken for this server
        self.send_header("X-MQEL", "1")
        self.send_header("Access-Control-Expose-Headers", "X-MQEL")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _market(self, parts, query, body):
        """/notice (Update-Countdown) und /market/<action> (ingame_market.py).
        Aktionen per POST mit JSON {"w": Web-Token, ...}."""
        market = self.server.market
        q = {k: v[0] for k, v in query.items()}
        args = dict(q, **(body if isinstance(body, dict) else {}))
        action = parts[1] if len(parts) > 1 else ""
        if parts[0] == "notice":
            return self._market_reply(200, self.server.notice.get())
        if action == "icon":  # Item-Icons (das Spiel hat für die meisten keine Web-Kopie)
            path = ingame_market.icon_file("/".join(parts[2:]))
            if not path:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        try:
            if action == "session":
                try:
                    aid = int(args.get("a") or 0)
                except ValueError:
                    aid = 0
                token = market.session(aid, self.client_address[0])
                if not token:
                    return self._market_reply(403, {"Error": "Start the game to use the Ingame Market and parties."})
                p = self.server.players.by_account_id(aid)
                return self._market_reply(200, {"w": token, "Unlocked": market.unlocked(p.state.snapshot()),
                                            "Shop": "/blings?t=" + token,
                                            "Notice": self.server.notice.get()})
            aid = market.account_for(args.get("w"))
            if not aid:
                return self._market_reply(401, {"Error": "Session expired: close and reopen the window."})
            account_state.SOURCE.value = "ingame-market"
            if action == "overview":
                out = market.overview(aid)
            elif action == "items":
                out = market.items_market(aid, args.get("category", ""), args.get("class", ""),
                                      args.get("q", ""), args.get("currency", ""), args.get("sort", "ending"),
                                      args.get("desc") in ("1", "true", 1, True))
            elif action == "materials":
                out = market.materials_market(args.get("q", ""))
            elif self.command != "POST":
                return self._market_reply(405, {"Error": "POST only"})
            elif action == "sell_item":
                out = market.sell_item(aid, args.get("slot"), args.get("start"), args.get("buyNow"),
                                   args.get("currency"), args.get("hours", 24))
            elif action == "bid":
                out = market.bid(aid, args.get("id"), args.get("amount"))
            elif action == "buy_now":
                out = market.buy_now(aid, args.get("id"))
            elif action == "cancel":
                out = market.cancel(aid, args.get("id"))
            elif action == "sell_material":
                out = market.sell_material(aid, args.get("templateId"), args.get("qty"),
                                       args.get("price"), args.get("currency"))
            elif action == "buy_material":
                out = market.buy_material(aid, args.get("templateId"), args.get("qty"),
                                      args.get("price"), args.get("currency"))
            elif action == "collect":
                out = market.collect(aid, args.get("which"))
            elif action == "sort_inventory":  # lobby inventory sort (lobby_mods.html)
                out = market.sort_inventory(aid, args.get("tab", 0), args.get("by", "type"),
                                        args.get("desc") in ("1", "true", 1, True))
            else:
                return self._market_reply(404, {"Error": "Unknown action"})
        except ValueError as e:  # GEError und Prüfungen der Kontodaten
            return self._market_reply(400, {"Error": str(e)})
        if self.command == "POST":
            print(f"    [market] {action} by {aid}: {json.dumps(out)[:200]}", flush=True)
        return self._market_reply(200, out)

    def _party(self, parts, query, body):
        """/party/<action> (parties.py): GET state; POST invite/accept/
        decline/leave/kick/live. Same web token as the Ingame Market."""
        args = dict({k: v[0] for k, v in query.items()}, **(body if isinstance(body, dict) else {}))
        action = parts[1] if len(parts) > 1 else "state"
        aid = self.server.market.account_for(args.get("w"))
        if not aid:
            return self._market_reply(401, {"Error": "Session expired: close and reopen the window."})
        pt, players_ = self.server.parties, self.server.players

        def online(m):
            p = next((x for x in list(players_.players.values()) if x.account_id == m), None)
            return presence.online(p)

        def raid_of(m):
            p = next((x for x in list(players_.players.values()) if x.account_id == m), None)
            c = ((getattr(p, "attack", None) and p.attack.current) or {}).get("castle") or {}
            return c.get("AccountId") if raids.is_raid(c.get("AccountId")) else None
        try:
            if action == "state":
                out = pt.view(aid, online, raid_of)
                out["HomeRegion"] = raids.home_region(players_.by_account_id(aid).state.snapshot())
            elif action == "raids":   # castles the leader can pick (raids.menu)
                raids.VIEWER.value = aid
                out = {"Raids": raids.menu(aid)}
            elif self.command != "POST":
                return self._market_reply(405, {"Error": "POST only"})
            elif action == "invite":
                out = pt.invite(aid, int(args.get("target") or 0))
                target = players_.by_account_id(int(args.get("target") or 0))
            elif action == "accept":
                out = pt.accept(aid, args.get("party"))
            elif action == "decline":
                out = pt.decline(aid, args.get("party"))
            elif action == "leave":
                out = pt.leave(aid)
            elif action == "kick":
                out = pt.kick(aid, int(args.get("target") or 0))
            elif action == "live":
                pt.report(aid, args)
                out = pt.view(aid, online, raid_of)
            elif action == "select":
                cid = int(args.get("castle") or 0)
                if not raids.is_raid(cid):
                    return self._market_reply(400, {"Error": "Not a raid castle."})
                seed, _, _ = raids.seed_and_size(aid)
                c = raids.castle(cid, aid)
                out = pt.select_raid(aid, cid, seed, c["Level"], c["AccountDisplayName"])
            elif action == "ready":
                out = pt.ready(aid, str(args.get("yes", "1")) not in ("0", "false", "False"))
            else:
                return self._market_reply(404, {"Error": "Unknown action"})
        except ValueError as e:
            return self._market_reply(400, {"Error": str(e)})
        if action not in ("state", "live", "raids"):
            print(f"    [party] {action} by {aid}: {json.dumps(out)[:160]}", flush=True)
        return self._market_reply(200, out)

    def _raid_bonus(self, player, raid, gains):
        """Co-op raid cleared: when every party member has cleared this raid
        castle, each gets the party bonus (raids.bonus)."""
        if gains.get("completion_type") != 0 or gains.get("practice"):
            return
        key = "%d/%d" % (raid["Seed"], raid["Tier"])
        members = self.server.parties.record_clear(player.account_id, key)
        if not members:
            return
        import item_drops  # noqa: PLC0415
        gold, lf, mats = raids.bonus(raid["Tier"], len(members))
        for m in members:
            p = self.server.players.by_account_id(m)
            if p is None:
                continue
            delta = p.state.admin_wallet({"InGameCoin": gold, "LifeForce": lf})
            notifications.wallet_updated(p.notifications, delta)
            items = [("material", item_drops.material_item(q)["TemplateId"], 1)
                     for q, n in mats for _ in range(n)]
            for name, fields in p.state.admin_give(items):
                p.notifications.push(name, fields)
            self.server.parties.bonus[m] = {
                "Tier": raid["Tier"], "Gold": gold, "LifeForce": lf, "Items": len(items)}
        print(f"    [raid] Party-Bonus Raid {key} fuer {members}", flush=True)

    def _send_text(self, text: str):
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("sl", str(random.randint(0, 50)))
        self.end_headers()
        self.wfile.write(data)

    def _safe_handle(self):
        """Fehler der Spiellogik: Request trotzdem loggen (mit Body, für die
        Analyse) und mit 500 antworten statt die Verbindung abzubrechen."""
        self._entry, self._timed = None, False
        started = time.monotonic()
        try:
            self._handle()
        except Exception:
            tb = traceback.format_exc()
            print(tb, flush=True)
            if self._entry is not None:
                self._entry["response"] = {"status": 500, "error": tb[-500:]}
                log_line(self.server.log_path, self._entry)
            try:
                self.send_error(500)
            except Exception:
                pass
        finally:
            if self._timed:
                server_stats.REQUESTS.add(time.monotonic() - started)

    do_GET = _safe_handle
    do_POST = _safe_handle
    do_PUT = _safe_handle
    do_DELETE = _safe_handle

    def do_OPTIONS(self):  # CEF-UI / Browser-Preflight tolerieren
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, t, i, h, rnd, n, g, v")
        self.end_headers()


def _notice_watch(srv):
    """Geplantes Update (Admin "Schedule update"): zur Zeit schließt die UI
    das Spiel selbst; der Server beendet dann alle Sitzungen (einmal)."""
    done = None
    while True:
        time.sleep(5)
        try:
            at = (srv.notice.get() or {}).get("At")
            if at and at <= time.time() and done != at:
                done = at
                # no logout of the sessions any more: the game closes itself
                # (WASD helper /quit) and a kept session lets Steam players
                # back in at the first launcher start (the logout made them
                # start the launcher twice, 2026-11-22)
                print("[notice] Update-Zeit erreicht", flush=True)
                # erledigt: nach dem Neustart nicht noch einmal alle abmelden
                srv.notice.cancel()
        except Exception as e:  # noqa: BLE001
            print(f"[notice] {e}", flush=True)


class GameHTTPServer(ThreadingHTTPServer):
    """Höchstens limits.MAX_CONNECTIONS_PER_IP gleichzeitige Verbindungen
    je IP; weitere werden sofort geschlossen."""

    def __init__(self, *a, **kw):
        self.conn_limit = limits.ConnectionLimit()
        super().__init__(*a, **kw)

    def verify_request(self, request, client_address):
        return self.conn_limit.acquire(client_address[0])

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.conn_limit.release(client_address[0])


def tcp_honeypot(port, log_path):
    """Lauscht auf einem TCP-Port (z. B. XMPP 5222) und loggt nur:
    wer verbindet sich, was sind die ersten Bytes. Antwortet nichts."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", port))
    except OSError as e:
        print(f"[tcp:{port}] bind fehlgeschlagen ({e}) — Port evtl. belegt oder "
              f"Adminrechte nötig (Port 80). Fahre ohne fort.", flush=True)
        return
    srv.listen(20)
    print(f"[tcp:{port}] honeypot aktiv", flush=True)
    while True:
        conn, addr = srv.accept()
        try:
            conn.settimeout(3)
            try:
                data = conn.recv(4096)
            except socket.timeout:
                data = b""
            print(f"\n>>> TCP:{port} Verbindung von {addr[0]}:{addr[1]} "
                  f"({len(data)} Bytes)", flush=True)
            if data:
                print(f"    daten: {data[:300]!r}", flush=True)
            log_line(log_path, {
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "tcp_port": port, "client": addr[0],
                "data": data.decode("utf-8", errors="replace")[:4000],
            })
        finally:
            conn.close()


def tls_cert(directory):
    """Selbstsigniertes Zertifikat für den HTTPS-Port (einmal erzeugt)."""
    cert = os.path.join(directory, "cert.pem")
    key = os.path.join(directory, "key.pem")
    if not os.path.exists(cert):
        os.makedirs(directory, exist_ok=True)
        ips = {"127.0.0.1"}
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.connect(("192.0.2.1", 9))
                ips.add(u.getsockname()[0])
        except OSError:
            pass
        san = ",".join("IP:" + ip for ip in sorted(ips))
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "3650", "-subj", "/CN=MQEL", "-addext",
                        "subjectAltName=" + san, "-keyout", key, "-out", cert],
                       check=True, capture_output=True)
    return cert, key


def _serve_website(host, port, ctx=None):
    try:
        web = ThreadingHTTPServer((host, port), WebsiteHandler)
    except OSError as e:  # Ports < 1024 brauchen Rechte (CAP_NET_BIND_SERVICE)
        print(f"  website:   Port {port} nicht verfügbar ({e})", flush=True)
        return False
    if ctx:
        web.socket = ctx.wrap_socket(web.socket, server_side=True,
                                     do_handshake_on_connect=False)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    print(f"  website:   {'https' if ctx else 'http'}://{host}:{port}/", flush=True)
    return True


def main():
    ap = argparse.ArgumentParser(description="MQEL-Spielserver")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--profile", default="full", choices=sorted(PROFILES),
                    help="Account: full (4 Helden Lvl 30) oder fresh (1 Ritter Lvl 5)")
    ap.add_argument("--state", default=None,
                    help="Spielerverzeichnis statt server/state/<profil>/ (Tests)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--admin-net", action="append", default=[], type=ipaddress.ip_network,
                    help="Netz (CIDR), aus dem das Webtool /admin auch von außen "
                         "erreichbar ist, nur per HTTPS (--tls-port); mehrfach möglich")
    ap.add_argument("--names-as-tokens", action="store_true",
                    help="Entwicklung: Login-Name als -token annehmen (Client ohne Launcher)")
    ap.add_argument("--log", default="server/requests.log.jsonl",
                    help="JSONL-Logdatei (wird angehängt)")
    ap.add_argument("--responses", default="server/responses.json",
                    help="Optionale JSON-Datei mit Antwort-Overrides")
    ap.add_argument("--tcp-ports", default="",
                    help="Kommagetrennte TCP-Ports für Honeypot-Listener, "
                         "z. B. --tcp-ports 5222 (XMPP-Versuche nachweisen)")
    ap.add_argument("--seasonal-event", default=None,
                    help="Saison-Event für den Launcher-Patch erzwingen, z. B. "
                         "Halloween (sonst nach Datum, patcher.EVENTS)")
    ap.add_argument("--free-trial", type=int, default=None, choices=sorted(free_trials.HEROES),
                    help="Helden-Trial ab heute erzwingen (Held 2 Ritter, 3 Bogenschützin, "
                         "4 Magier, 5 Runaway; sonst nach Datum, free_trials.py)")
    ap.add_argument("--boost-event", type=int, default=None, choices=[0, 21, 22, 23, 24, 25, 26],
                    help="Boost-Wochenende ab heute erzwingen (Test): 21 Gold, 22 Lebenskraft, "
                         "23 XP, 24 Magic Find, 25 Bling-Mine, 26 Material-Minen, 0 alle "
                         "(sonst nach Kalender, community_events.py)")
    ap.add_argument("--free-trial-minutes", type=int, default=None,
                    help="erzwungenes Trial endet so viele Minuten nach dem "
                         "Serverstart (Test des Ablaufs)")
    ap.add_argument("--client-exe", default=None,
                    help="Spiel-Exe, die der Patcher als MightyQuest.exe verteilt "
                         "(z. B. gepatchte MightyQuest_profile.exe, tools/patch_ca.py)")
    ap.add_argument("--keep-unknown-versions", action="store_true",
                    help="installierte Paketstände, die dieser Server nicht kennt (Client "
                         "von einem anderen Server gepatcht), als aktuell melden statt "
                         "sie zu überspringen/patchen")
    ap.add_argument("--web-port", type=int, default=None,
                    help="Projektseite aus website/ auf eigenem Port (z. B. 80)")
    ap.add_argument("--web-tls-port", type=int, default=None,
                    help="Projektseite zusätzlich per HTTPS (z. B. 443, braucht --web-cert/--web-key); "
                         "HTTP leitet dann dorthin um")
    ap.add_argument("--web-cert", default=None, help="Zertifikatskette der Projektseite (fullchain.pem)")
    ap.add_argument("--web-key", default=None, help="Schlüssel der Projektseite (privkey.pem)")
    ap.add_argument("--tls-cert", default=None,
                    help="Zertifikatskette für --tls-port statt des selbstsignierten")
    ap.add_argument("--tls-key", default=None, help="Schlüssel zu --tls-cert")
    ap.add_argument("--tls-port", type=int, default=None,
                    help="zusätzlich HTTPS auf diesem Port (die Ship-Exe "
                         "MightyQuest.exe beendet sich bei http-Server-URL)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    for p in [x.strip() for x in args.tcp_ports.split(",") if x.strip()]:
        t = threading.Thread(target=tcp_honeypot, args=(int(p), args.log),
                             daemon=True)
        t.start()
    srv = GameHTTPServer((args.host, args.port), GameHandler)
    srv.log_path = args.log
    srv.responses_path = args.responses
    patcher.FORCED_EVENT = args.seasonal_event
    patcher.CLIENT_EXE = args.client_exe
    patcher.KEEP_UNKNOWN_VERSIONS = args.keep_unknown_versions
    free_trials.FORCED_HERO = args.free_trial
    community_events.FORCED_BOOST = args.boost_event
    if args.free_trial and args.free_trial_minutes:
        free_trials.FORCED_END = (datetime.datetime.now(datetime.timezone.utc)
                                  + datetime.timedelta(minutes=args.free_trial_minutes)
                                  ).replace(microsecond=0)
    log = lambda m: print(m, flush=True)
    state_dir = args.state or os.path.join(ROOT, "server", "state", args.profile)
    srv.players = players.Players(state_dir, args.profile, log=log,
                                  names_as_tokens=args.names_as_tokens)
    castles.register_players(srv.players)
    # Länder-Datenbank im Hintergrund laden, der erste neue Spieler wartet sonst
    threading.Thread(target=geoip.load, daemon=True).start()

    def account_lookup(account_id):
        p = srv.players.by_account_id(account_id)
        return p.state.snapshot() if p else profiles.fake_account(account_id)

    guild_path = os.path.join(state_dir, "guilds.json")
    srv.replays = replays.Replays(os.path.join(state_dir, "replays"))
    srv.guilds = guilds.Guilds(guild_path, account_lookup, log=log)
    balance.load(os.path.join(state_dir, "balance.json"))
    website.write()
    srv.admin_nets = args.admin_net
    srv.admin_keys = admin.load_keys(os.path.join(state_dir, "admin_hmac.json"))
    # News im Webtool -> Patch-Note-Kanal auf Discord (discord_patch_notes.py)
    srv.news = news.News(os.path.join(state_dir, "news.json"),
                         discord_patch_notes.NewsNotifier(
                             state_dir, log=lambda m: print(m, flush=True)))
    server_stats.CPU.start()  # Mittelwerte für den Server-Tab im Webtool
    srv.admin = admin.AdminService(srv.players, srv.guilds,
                                   os.path.join(state_dir, "maintenance.json"),
                                   chat_log.ChatLog(state_dir), srv.news)
    srv.competitions = competitions.Competitions(
        os.path.join(state_dir, "competitions.json"), log=log)
    srv.castle_stats = castle_stats.CastleStats(
        os.path.join(state_dir, "castle_stats.json"), log=log)
    # Discord: Cornelius kündigt jedes Event an (discord_events.py, Webhook)
    discord_events.start(state_dir, log=lambda m: print(m, flush=True))
    # Ingame Market (ingame_market.py, UI-Patch 16.) und Update-Countdown
    srv.market = ingame_market.Market(state_dir, srv.players, log=log)
    srv.notice = ingame_market.Notice(state_dir)
    srv.admin.notice = srv.notice
    srv.admin.market = srv.market
    # Parties und Co-op-Raids (parties.py, raids.py, UI-Patch 17.)
    srv.parties = parties.Parties(os.path.join(state_dir, "parties.json"), srv.players, log=log)
    # IP je Account, Mehrfach-Accounts nur von freigegebenen IPs (iplog.py)
    srv.iplog = iplog.IpLog(os.path.join(state_dir, "ip_log.json"), log=log)
    srv.admin.iplog = srv.iplog
    raids.PARTIES, raids.PLAYERS = srv.parties, srv.players
    threading.Thread(target=_notice_watch, args=(srv,), daemon=True).start()
    print(f"Account-Profil: {args.profile} ({state_dir}, "
          f"{len(srv.players.index)} Spieler)", flush=True)
    if not srv.players.auth.has_admins():
        print("WARNUNG: kein Admin eingetragen, das Webtool /admin ist im lokalen "
              "Netz ohne Anmeldung offen (dort einen Spieler zum Admin machen)",
              flush=True)
    log_line(args.log, {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "server_start": True,
        "code": "http11+sl+charset+resplog+dollar-type-ready+loglock",
        "port": args.port,
    })
    print(f"MQEL game server: http://{args.host}:{args.port}/", flush=True)
    print(f"  log:       {args.log}", flush=True)
    print(f"  responses: {args.responses} (pro Request neu geladen)", flush=True)
    print(f"Anmeldung über den Launcher (http://{args.host}:{args.port}/launcher/)", flush=True)
    if args.names_as_tokens:
        print("Client direkt z.B.: MightyQuest_release.exe -server_url "
              f"http://{args.host}:{args.port} -token test -email test@test "
              "-environmentName local -httpCompression 0  (CWD=client/GameData/Bin)",
              flush=True)
    if args.web_tls_port:
        if not (args.web_cert and args.web_key):
            ap.error("--web-tls-port braucht --web-cert und --web-key")
        web_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            web_ctx.load_cert_chain(args.web_cert, args.web_key)
        except OSError as e:  # noch kein Zertifikat (erster certbot-Lauf): nur HTTP
            print(f"  website:   kein HTTPS, Zertifikat fehlt ({e})", flush=True)
        else:
            if _serve_website(args.host, args.web_tls_port, web_ctx):
                WebsiteHandler.https = args.web_tls_port
    if args.web_port:
        _serve_website(args.host, args.web_port)
    if args.tls_port:
        tls = GameHTTPServer((args.host, args.tls_port), GameHandler)
        for k, v in vars(srv).items():
            if k not in vars(tls):
                setattr(tls, k, v)
        if bool(args.tls_cert) != bool(args.tls_key):
            ap.error("--tls-cert und --tls-key nur zusammen")
        cert, key = ((args.tls_cert, args.tls_key) if args.tls_cert
                     else tls_cert(os.path.join(ROOT, "server", "state", "tls")))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        # Launcher und Shop (Chromium von 2015) kommen mit TLS 1.0/1.1, das
        # Spiel mit 1.2; OpenSSL 3 erlaubt die alten Versionen nur auf
        # SECLEVEL 0. Nur ECDHE-Suiten (Forward Secrecy)
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+AES:@SECLEVEL=0")
        # Handshake erst im Verbindungs-Thread (GameHandler.setup): sonst
        # blockiert ein langsamer Client accept(), und Fehler gehen verloren
        tls.socket = ctx.wrap_socket(tls.socket, server_side=True,
                                     do_handshake_on_connect=False)
        threading.Thread(target=tls.serve_forever, daemon=True).start()
        print(f"  https:     https://{args.host}:{args.tls_port}/ (Zertifikat {cert})",
              flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstop.", flush=True)


if __name__ == "__main__":
    main()
