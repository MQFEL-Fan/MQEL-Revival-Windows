#!/usr/bin/env python3
"""MQEL Fake-XMPP-Server (ejabberd-Ersatz für den Revival-Betrieb).

Der Spiel-Client (XmppClient_Z, s. AccountServerController::GetXmppInfo)
verbindet direkt per TCP auf XmppInfo.Server:Port und erwartet:
  Stream -> Features(PLAIN) -> SASL-Auth -> neuer Stream ->
  Features(bind+session) -> Bind -> Session -> Roster/Presence/MUC.

Anmeldung: Benutzer = Login-Name, Passwort aus dem Sitzungs-Token des
Spielservers (auth.chat_password, XmppInfo.Password); geprüft gegen
logins.json im
Profilverzeichnis (--state). Ohne --state nimmt er jeden an (Entwicklung).
Loggt jede Stanza (Konsole + xmpp.log) und antwortet minimal
ejabberd-kompatibel. Nur Standardbibliothek.

Gebrauch:
  python server/xmpp_server.py --port 5222 --state server/state/new
  (statt --tcp-ports 5222 am Spielserver: Port wäre sonst belegt)

Client-Stub dazu: AccountInformation.ClientSettings.XmppInfo in
server/stubs/account-information.json (Server=127.0.0.1, Port=5222).
"""

import argparse
import base64
import binascii
import datetime
import hmac
import html
import json
import os
import random
import re
import signal
import socket
import threading
import urllib.parse

import auth
import chat_log
import limits
from profanity import filter_text

# Puffer für eine unvollständige Stanza (Chatzeilen sind kurz)
MAX_BUFFER = 64 * 1024
# Profilverzeichnis des Spielservers (logins.json) oder None: keine Prüfung
STATE_DIR = None
LOG_LOCK = threading.Lock()
AUTH_RE = re.compile(r"(<auth[^>]*>)[^<]*")
# Chattexte nicht ins Stanza-Log: sie stehen nur im Chat-Verlauf mit Löschfrist
BODY_RE = re.compile(r"(<body(?:filtered)?>)[^<]*")
# Chat-Verlauf und Stummschaltung (chat_log.py) oder None ohne --state
CHAT = None

TAG_RE = re.compile(r"<([a-zA-Z0-9_]+)(?::([a-zA-Z0-9_]+))?[\s/>]")
ID_RE = re.compile(r'''\bid\s*=\s*["']([^"']*)["']''')
TO_RE = re.compile(r'''\bto\s*=\s*["']([^"']*)["']''')
FROM_RE = re.compile(r'''\bfrom\s*=\s*["']([^"']*)["']''')
TYPE_RE = re.compile(r'''\btype\s*=\s*["']([^"']*)["']''')
STREAM_TO_RE = re.compile(r'''\bto\s*=\s*["']([^"']*)["']''')


# Chaträume (MUC): {Raum-JID: {Session: Nick}}; Nachrichten und Presence
# gehen an alle im Raum (auch an den Absender: der Client zeigt seine
# eigene Nachricht erst, wenn der Raum sie zurückschickt)
ROOMS = {}

ROOMS_LOCK = threading.Lock()
# Räume, denen ein Schreibender automatisch wieder beitritt (handle_message)
LANGS_PREFIX = ("en-", "de-", "fr-", "es-", "pl-", "pt-", "ru-", "zh-", "it-")


def _inner(stanza):
    """Inhalt zwischen Start- und End-Tag (leer bei selbstschließend)."""
    gt = stanza.find(">")
    if stanza[gt - 1] == "/":
        return ""
    return stanza[gt + 1:stanza.rfind("</")]


def _chat_body(m):
    text = urllib.parse.unquote_plus(html.unescape(m.group(1)))
    return (f"<body>{html.escape(text, quote=False)}</body>"
            f"<bodyfiltered>{html.escape(filter_text(text), quote=False)}"
            "</bodyfiltered>")


def ts():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def session_valid(user, password):
    """Hat user eine Sitzung des Spielservers mit diesem Chat-Passwort
    (auth.chat_password)? logins.json wird bei jeder Anmeldung neu gelesen,
    der Spielserver schreibt sie."""
    if STATE_DIR is None:
        return True
    try:
        with open(os.path.join(STATE_DIR, "logins.json"), encoding="utf-8") as f:
            sessions = json.load(f).get("sessions", {})
    except (OSError, ValueError):
        return False
    return bool(password) and any(
        hmac.compare_digest(auth.chat_password(t), password)
        for t, name in sessions.items() if name == user)


class Session:
    def __init__(self, conn, addr, log_path):
        self.conn = conn
        self.addr = addr
        self.log_path = log_path
        self.buf = b""
        self.domain = "mqel.local"
        self.user = "test"
        self.password = None
        self.resource = "mqel"
        self.streams_opened = 0
        self.authed = False
        self.jid = None
        self.send_lock = threading.Lock()

    def log(self, direction, data):
        data = AUTH_RE.sub(r"\1(redacted)", data)  # Token nicht ins Log
        data = BODY_RE.sub(r"\1(text)", data)
        line = f"\n[XMPP {direction}] {data[:500]!r}"
        print(line, flush=True)
        try:
            with LOG_LOCK:
                limits.rotate_log(self.log_path)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": ts(), "dir": direction,
                                        "data": data[:4000]},
                                       ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[warn] log write failed: {e}", flush=True)

    def send(self, text):
        self.log("S->C", text)
        with self.send_lock:
            self.conn.sendall(text.encode("utf-8"))

    def full_jid(self):
        return self.jid or f"{self.user}@{self.domain}/{self.resource}"

    def _occupant_presence(self, room, nick, extra, to, self_=False, gone=False):
        status = "<status code='110'/>" if self_ else ""
        role = "none" if gone else "participant"
        typ = " type='unavailable'" if gone else ""
        return (f"<presence from='{room}/{nick}' to='{to}'{typ}>{extra}"
                f"<x xmlns='http://jabber.org/protocol/muc#user'>"
                f"<item affiliation='member' role='{role}'/>{status}</x></presence>")

    def join_room(self, room, nick, extra):
        with ROOMS_LOCK:
            occ = ROOMS.setdefault(room, {})
            others = [(s, n, e) for s, (n, e) in occ.items() if s is not self]
            occ[self] = (nick, extra)
        for s, n, e in others:
            self.send(self._occupant_presence(room, n, e, self.full_jid()))
            s.send(self._occupant_presence(room, nick, extra, s.full_jid()))
        self.send(self._occupant_presence(room, nick, extra, self.full_jid(), self_=True))
        # keine Nachricht ohne <body> (auch kein leeres <subject/>): dann
        # liefert der Nachrichten-Handler des Clients 0, und libstrophe
        # meldet ihn ab -- danach kommt keine Chat-Nachricht mehr an

    def leave_room(self, room):
        with ROOMS_LOCK:
            occ = ROOMS.get(room) or {}
            nick, extra = occ.pop(self, (None, ""))
            rest = list(occ)
            if not occ:
                ROOMS.pop(room, None)
        if nick is None:
            return
        for s in [self] + rest:
            try:
                s.send(self._occupant_presence(room, nick, "", s.full_jid(),
                                               self_=s is self, gone=True))
            except OSError:
                pass

    def update_presence(self, extra):
        """Presence ohne Empfänger (Keepalive alle 20 s, <show>away/dnd)
        wie bei einem normalen MUC-Server an alle Räume des Spielers
        verteilen; daraus liest der Client den PresenceStatus."""
        with ROOMS_LOCK:
            targets = []
            for room, occ in ROOMS.items():
                if self in occ:
                    nick = occ[self][0]
                    occ[self] = (nick, extra)
                    targets.append((room, nick, list(occ)))
        for room, nick, members in targets:
            for s in members:
                try:
                    s.send(self._occupant_presence(room, nick, extra, s.full_jid(),
                                                   self_=s is self))
                except OSError:
                    pass

    def leave_all(self):
        with ROOMS_LOCK:
            rooms = [r for r, occ in ROOMS.items() if self in occ]
        for r in rooms:
            self.leave_room(r)

    def stream_id(self):
        return "%08x" % random.getrandbits(32)

    def handle_stream_open(self, stanza):
        m = STREAM_TO_RE.search(stanza)
        if m:
            self.domain = m.group(1)
        self.streams_opened += 1
        self.send(f"<?xml version='1.0'?>"
                  f"<stream:stream xmlns='jabber:client' "
                  f"xmlns:stream='http://etherx.jabber.org/streams' "
                  f"from='{self.domain}' id='{self.stream_id()}' version='1.0'>")
        if not self.authed:
            self.send("<stream:features>"
                      "<mechanisms xmlns='urn:ietf:params:xml:ns:xmpp-sasl'>"
                      "<mechanism>PLAIN</mechanism>"
                      "</mechanisms>"
                      "</stream:features>")
        else:
            self.send("<stream:features>"
                      "<bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'/>"
                      "<session xmlns='urn:ietf:params:xml:ns:xmpp-session'/>"
                      "</stream:features>")

    def handle_auth(self, stanza):
        """SASL PLAIN: \0Name\0Token; nur gültige Sitzungen des Spielservers."""
        user = password = None
        m = re.search(r"<auth[^>]*>([^<]*)</auth>", stanza)
        if m:
            try:
                raw = base64.b64decode(m.group(1).strip()).split(b"\x00")
                if len(raw) >= 3:
                    user = raw[1].decode("utf-8", errors="replace")
                    password = raw[2].decode("utf-8", errors="replace")
            except (binascii.Error, ValueError):
                pass
        if not user or not session_valid(user, password):
            self.send("<failure xmlns='urn:ietf:params:xml:ns:xmpp-sasl'>"
                      "<not-authorized/></failure>")
            raise ConnectionResetError(f"Anmeldung abgelehnt ({user!r})")
        self.user, self.password = user, password
        self.authed = True
        self.send("<success xmlns='urn:ietf:params:xml:ns:xmpp-sasl'/>")

    def iq_id(self, stanza):
        m = ID_RE.search(stanza)
        return m.group(1) if m else "0"

    def handle_iq(self, stanza):
        qid = self.iq_id(stanza)
        if "<bind" in stanza:
            m = re.search(r"<resource>([^<]*)</resource>", stanza)
            if m and m.group(1).strip():
                self.resource = m.group(1).strip()
            self.jid = f"{self.user}@{self.domain}/{self.resource}"
            self.send(f"<iq type='result' id='{qid}'>"
                      f"<bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'>"
                      f"<jid>{self.jid}</jid></bind></iq>")
        elif "<session" in stanza:
            self.send(f"<iq type='result' id='{qid}'/>")
        elif "jabber:iq:roster" in stanza:
            self.send(f"<iq type='result' id='{qid}'>"
                      f"<query xmlns='jabber:iq:roster'/></iq>")
        elif "jabber:iq:version" in stanza:
            self.send(f"<iq type='result' id='{qid}'>"
                      f"<query xmlns='jabber:iq:version'>"
                      f"<name>mqel-revival</name><version>0.1</version>"
                      f"</query></iq>")
        else:
            # Unbekannte IQ: leeres result (verhindert Client-Timeouts).
            self.send(f"<iq type='result' id='{qid}'/>")

    def handle_presence(self, stanza):
        m = TO_RE.search(stanza)
        to = m.group(1) if m else ""
        if "/" in to and ("http://jabber.org/protocol/muc" in stanza
                          or "conference." in to):
            room, nick = to.split("/", 1)
            if 'type="unavailable"' in stanza or "type='unavailable'" in stanza:
                self.leave_room(room)
            else:
                # Spielerdaten (accountId, castleLevel, ...) mitschicken;
                # ohne x-Element des Clients
                extra = re.sub(r"<x\b.*?(/>|</x>)", "", _inner(stanza), flags=re.S)
                self.join_room(room, nick, extra)
        elif not to:
            if re.search(r"type=['\"]unavailable", stanza):
                self.leave_all()
            else:
                self.update_presence(_inner(stanza))
        # sonstige gerichtete Presence: keine Antwort nötig.

    def handle_message(self, stanza):
        m, t = TO_RE.search(stanza), TYPE_RE.search(stanza)
        room = m.group(1).split("/")[0] if m else ""
        if not t or t.group(1) != "groupchat":
            return
        with ROOMS_LOCK:
            occ = ROOMS.get(room) or {}
            nick = occ.get(self, (None,))[0]
            targets = list(occ)
        if nick is None and room.startswith(tuple(LANGS_PREFIX)) and "@conference." in room:
            # Der Client schreibt in einen Raum, dem er (nach einem Neustart
            # des Spielservers) nicht mehr beigetreten ist: sein Join kam nie
            # an, Nachrichten verschwanden still (2026-11-22). Wieder
            # aufnehmen, mit den Spielerdaten aus der Nachricht.
            extra = re.sub(r"<body>.*?</body>|<bodyfiltered>.*?</bodyfiltered>", "",
                           _inner(stanza), flags=re.S)
            self.join_room(room, self.user, extra)
            with ROOMS_LOCK:
                occ = ROOMS.get(room) or {}
                nick = occ.get(self, (None,))[0]
                targets = list(occ)
        if nick is None:
            return
        # Sitzung beendet (Sperre, Abmeldung im Admin-Tool): nichts mehr senden
        if not session_valid(self.user, self.password):
            raise ConnectionResetError(f"Sitzung von {self.user!r} beendet")
        body = re.sub(r"<bodyfiltered>.*?</bodyfiltered>", "", _inner(stanza),
                      flags=re.S)
        # der Client schickt den Text URL-kodiert („Hallo+Claude“) und zeigt
        # <bodyfiltered> (beim Original von CleanSpeak gefiltert) an, wenn
        # die Option „Profanity filter“ an ist
        body = re.sub(r"<body>(.*?)</body>", _chat_body, body, count=1,
                      flags=re.S)
        text = re.search(r"<body>(.*?)</body>", body, flags=re.S)
        text = html.unescape(text.group(1)) if text else ""
        muted = CHAT is not None and CHAT.is_muted(self.user)
        if CHAT is not None:
            CHAT.append(room, self.user, nick, text, muted=muted)
        if muted:  # still: nur der Absender sieht seine Nachricht
            targets = [self]
        for s in targets:
            try:
                s.send(f"<message from='{room}/{nick}' to='{s.full_jid()}' "
                       f"type='groupchat'>{body}</message>")
            except OSError:
                pass

    def dispatch(self, stanza):
        s = stanza.strip()
        if not s:
            return
        if s.startswith("<stream:stream"):
            self.handle_stream_open(s)
        elif s.startswith("<auth"):
            self.handle_auth(s)
        elif s.startswith("<starttls"):
            # Plaintext weiterfahren; Client kennt "STARTTLS not supported".
            self.send("<failure xmlns='urn:ietf:params:xml:ns:xmpp-tls'/>")
        elif s.startswith("</stream:stream"):
            raise ConnectionResetError("client closed stream")
        elif not self.authed:
            raise ConnectionResetError("Stanza vor der Anmeldung")
        elif s.startswith("<iq"):
            self.handle_iq(s)
        elif s.startswith("<presence"):
            self.handle_presence(s)
        elif s.startswith("<message"):
            self.handle_message(s)
        else:
            print(f"[XMPP] unbekannte Stanza (ignoriert): {s[:120]!r}",
                  flush=True)

    def extract_stanzas(self):
        """Zieht komplette Stanzas aus dem Puffer (Stream-Open ist nie
        geschlossen und wird separat erkannt)."""
        out = []
        while True:
            text = self.buf.decode("utf-8", errors="replace")
            stripped = text.lstrip()
            if not stripped:
                if len(self.buf) > 0:
                    self.send(" ")  # Whitespace-Keepalive beantworten
                self.buf = b""
                break
            if stripped.startswith("<?xml"):
                end = stripped.find("?>")
                if end == -1:
                    break
                self.buf = stripped[end + 2:].encode("utf-8", errors="replace")
                continue
            if stripped.startswith("<stream:stream"):
                end = stripped.find(">")
                if end == -1:
                    break
                out.append(stripped[:end + 1])
                self.buf = stripped[end + 1:].encode("utf-8", errors="replace")
                continue
            if stripped.startswith("</stream:stream"):
                out.append("</stream:stream>")
                idx = stripped.find(">")
                self.buf = stripped[idx + 1:].encode("utf-8", errors="replace")
                continue
            m = TAG_RE.match(stripped)
            if not m:
                # Whitespace-Keepalive? -> mit Space antworten.
                if stripped.strip() == "":
                    self.buf = b""
                    self.send(" ")
                    break
                print(f"[XMPP] nicht parsbar, Puffer verworfen: "
                      f"{stripped[:120]!r}", flush=True)
                self.buf = b""
                break
            lname, suffix = m.group(1), m.group(2)
            name = lname + (":" + suffix if suffix else "")
            gt = stripped.find(">", m.end())
            if gt != -1 and stripped[gt - 1] == "/":
                # Selbstschließend (<presence/>, <x …/>): endet am ersten '>'.
                out.append(stripped[:gt + 1])
                self.buf = stripped[gt + 1:].encode("utf-8", errors="replace")
                continue
            close = f"</{name}>"
            idx = stripped.find(close)
            if idx == -1:
                break  # unvollständig -> mehr lesen
            end = idx + len(close)
            out.append(stripped[:end])
            self.buf = stripped[end:].encode("utf-8", errors="replace")
        return out

    def run(self):
        print(f"[XMPP] Verbindung von {self.addr[0]}:{self.addr[1]}",
              flush=True)
        self.conn.settimeout(120)
        try:
            while True:
                try:
                    chunk = self.conn.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                self.log("C->S", chunk.decode("utf-8", errors="replace"))
                self.buf += chunk
                if len(self.buf) > MAX_BUFFER:
                    raise ConnectionResetError("Stanza zu groß")
                for stanza in self.extract_stanzas():
                    self.log("C->S stanza", stanza)
                    self.dispatch(stanza)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f"[XMPP] Ende ({e})", flush=True)
        finally:
            self.leave_all()
            try:
                self.conn.close()
            except OSError:
                pass


conn_limit = limits.ConnectionLimit()


def _serve(conn, addr, log_path):
    try:
        Session(conn, addr, log_path).run()
    finally:
        conn_limit.release(addr[0])


def main():
    ap = argparse.ArgumentParser(description="MQEL Fake-XMPP-Server")
    ap.add_argument("--port", type=int, default=5222)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--log", default="server/xmpp.log",
                    help="Stanza-Logdatei (wird angehängt)")
    ap.add_argument("--state", default=None,
                    help="Profilverzeichnis des Spielservers (logins.json), "
                         "z. B. server/state/new; ohne: jede Anmeldung gilt")
    args = ap.parse_args()
    global STATE_DIR
    STATE_DIR = args.state
    global CHAT
    if STATE_DIR is not None:
        CHAT = chat_log.ChatLog(STATE_DIR)
    if STATE_DIR is None:
        print("WARNUNG: ohne --state prüft der Chat keine Anmeldung "
              "(jeder kann jeden Namen nutzen)", flush=True)

    stop = threading.Event()

    def _request_stop(signum, frame):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _request_stop)
        except ValueError:
            pass  # nicht im Main-Thread (z. B. eingebettet): Timeout-Loop + KeyboardInterrupt genügen
    if hasattr(signal, "SIGBREAK"):  # Windows: Strg+Pause
        try:
            signal.signal(signal.SIGBREAK, _request_stop)
        except ValueError:
            pass

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(20)
    srv.settimeout(0.5)  # accept() periodisch aufwecken -> Ctrl+C wirkt immer
    print(f"MQEL fake XMPP: {args.host}:{args.port}/ (log: {args.log})",
          flush=True)
    print("Beenden mit Strg+C.", flush=True)
    try:
        while not stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            if not conn_limit.acquire(addr[0]):
                conn.close()
                continue
            t = threading.Thread(target=_serve, args=(conn, addr, args.log),
                                 daemon=True)
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        print("\nstop.", flush=True)


if __name__ == "__main__":
    main()
