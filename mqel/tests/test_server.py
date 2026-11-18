"""End-to-End-Tests: Spielserver in einem leeren Spielerverzeichnis starten
und Anmeldung, Sanktionen, Bling-Shop und Webtool über HTTP prüfen.

    python3 -m unittest discover tests
"""

import datetime
import glob
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import anticheat  # noqa: E402
import auth  # noqa: E402
import balance  # noqa: E402
import bling_shop  # noqa: E402
import castles  # noqa: E402
import chat_log  # noqa: E402
import competitions  # noqa: E402
import free_trials  # noqa: E402
import game_server  # noqa: E402
import account_state  # noqa: E402
import limits  # noqa: E402
import loot  # noqa: E402
import objectives  # noqa: E402
import patcher  # noqa: E402
import special_packs  # noqa: E402
import steam_auth  # noqa: E402
import trophies  # noqa: E402
import profiles  # noqa: E402
import settings_archive  # noqa: E402
import xmpp_server  # noqa: E402
from profanity import filter_text  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def request(url, body=None, headers=None, method=None):
    """(Status, Header, Body-Text) ohne Weiterleitungen."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, dict(headers or {}, **(
        {"Content-Type": "application/json"} if data else {})), method=method)
    try:
        with OPENER.open(req, timeout=30) as r:
            return r.status, r.headers, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.proc = subprocess.Popen(
            [sys.executable, "-u", "server/game_server.py", "--port", str(cls.port),
             "--profile", "new", "--state", os.path.join(cls.tmp.name, "state"),
             "--log", os.path.join(cls.tmp.name, "log.jsonl")],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(300):
            try:
                socket.create_connection(("127.0.0.1", cls.port), 1).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Server startet nicht")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(10)
        cls.tmp.cleanup()

    def launcher(self, action, name, password):
        status, _, text = request(self.base + "/launcher/" + action,
                                  {"name": name, "password": password})
        self.assertEqual(status, 200)
        return json.loads(text)

    def register(self, name, password="geheim123"):
        r = self.launcher("register", name, password)
        self.assertIn("Token", r, r)
        return r["Token"]

    def game(self, token, method="GetAccountInformation"):
        return request(self.base + "/AccountService.hqs/" + method,
                       headers={"t": token}, method="GET")

    def admin(self, method, args, cookie=None):
        status, _, text = request(self.base + "/admin/api/" + method, args,
                                  {"Cookie": "admin_t=" + cookie} if cookie else None)
        return status, json.loads(text)

    def account_id(self, name, cookie=None):
        _, rows = self.admin("ListAccounts", {}, cookie)
        return next(r["Id"] for r in rows if r["Login"] == name)

    # --- Anmeldung ----------------------------------------------------------

    def test_register_and_login(self):
        token = self.register("alice")
        self.assertEqual(len(token), auth.TOKEN_LENGTH)  # Client kürzt auf 24
        self.assertEqual(self.game(token)[0], 200)
        self.assertEqual(self.launcher("register", "ALICE", "x" * 8), {"Error": "name_taken"})
        self.assertEqual(self.launcher("login", "alice", "falsch99"), {"Error": "bad_login"})
        self.assertEqual(self.launcher("login", "nobody", "geheim123"), {"Error": "bad_login"})
        self.assertEqual(self.launcher("register", "a b", "geheim123"), {"Error": "name_invalid"})
        self.assertEqual(self.launcher("register", "bob", "kurz"), {"Error": "password_short"})
        # neue Anmeldung macht das alte Token ungültig
        new = self.launcher("login", "alice", "geheim123")["Token"]
        self.assertEqual(self.game(new)[0], 200)
        status, _, text = self.game(token)
        self.assertEqual(status, 401)
        self.assertIn("InvalidConnectionTokenException", text)

    def test_client_start_drops_queued_notifications(self):
        # Meldungen aus der Offline-Zeit stecken im Account; die erste Anfrage
        # des Clients (i=0, beim Login parallel zu GetAccountInformation) darf
        # sie nicht zusätzlich ausliefern
        alice, bob = self.register("nora"), self.register("otto")
        nora = self.account_id("nora")

        def invite():
            request(self.base + "/FriendshipService.hqs/SendFriendshipInvitation",
                    {"friendAccountId": nora}, {"t": bob})

        def notes(i):
            _, _, text = request(self.base + "/ServerCommandService.hqs/SendCommands",
                                 {"commands": []}, {"t": alice, "i": str(i), "n": "0"})
            return [n["Index"] for n in json.loads(text).get("Notifications", [])]

        invite()
        self.assertEqual(notes(0), [])
        self.assertEqual(notes(1), [])
        invite()  # neue Meldung während der Sitzung kommt an, Zählung ab 1
        self.assertEqual(notes(2), [1])

    def test_chat_login_uses_session_token(self):
        token = self.register("chatty")
        _, _, text = request(self.base + "/AccountInformationService.hqs/GetAccountInformation",
                             {}, {"t": token, "Host": "127.0.0.1:%d" % self.port})
        info = json.loads(text)["Result"]["ClientSettings"]["XmppInfo"]
        password = auth.chat_password(token)
        self.assertEqual((info["Username"], info["Password"]), ("chatty", password))
        self.assertNotEqual(password, token)  # Mitlesen im Chat verrät das Token nicht
        old = xmpp_server.STATE_DIR
        xmpp_server.STATE_DIR = os.path.join(self.tmp.name, "state")
        try:
            self.assertTrue(xmpp_server.session_valid("chatty", password))
            self.assertFalse(xmpp_server.session_valid("chatty", token))
            self.assertFalse(xmpp_server.session_valid("alice", password))
            self.assertFalse(xmpp_server.session_valid("chatty", "x" * 24))
            self.assertFalse(xmpp_server.session_valid("chatty", ""))
        finally:
            xmpp_server.STATE_DIR = old

    def test_chat_moderation(self):
        token = self.register("loudy")
        state = os.path.join(self.tmp.name, "state")
        # Spielserver schreibt logins.json ins Profilverzeichnis
        state = os.path.dirname(glob.glob(os.path.join(state, "**", "logins.json"),
                                          recursive=True)[0])
        old = xmpp_server.STATE_DIR, xmpp_server.CHAT
        xmpp_server.STATE_DIR, xmpp_server.CHAT = state, chat_log.ChatLog(state)
        sent = []

        class Peer(xmpp_server.Session):
            def __init__(self, user, password):
                super().__init__(None, ("127.0.0.1", 0), os.path.join(self_.tmp.name, "x.log"))
                self.user, self.password = user, password

            def send(self, text):
                sent.append((self.user, text))
        self_ = self
        loud = Peer("loudy", auth.chat_password(token))
        other = Peer("other", "")
        room = "en-general-1@conference.x"
        xmpp_server.ROOMS[room] = {loud: ("loudy",), other: ("other",)}

        def say(text):
            sent.clear()
            loud.handle_message("<message to='%s' type='groupchat'><body>%s</body></message>"
                                % (room, text))
            return sorted(u for u, _ in sent)
        try:
            self.assertEqual(say("Hallo+du"), ["loudy", "other"])
            aid = self.account_id("loudy")
            _, d = self.admin("GetChatLog", {"accountId": aid})
            self.assertEqual([(e["Text"], e["AccountId"]) for e in d["Entries"]], [("Hallo du", aid)])
            self.assertEqual(self.admin("SetChatMute", {"accountId": aid, "hours": 1})[0], 200)
            self.assertEqual(say("nochmal"), ["loudy"])  # nur der Absender sieht es
            _, d = self.admin("GetChatLog", {"text": "NOCH"})
            self.assertTrue(d["Entries"][0]["Muted"])
            self.assertEqual([m["Login"] for m in d["Muted"]], ["loudy"])
            self.admin("SetChatMute", {"accountId": aid, "mute": False})
            self.assertEqual(say("wieder"), ["loudy", "other"])
            # Text nie im Stanza-Log
            loud.log("C->S", "<message><body>geheim</body></message>")
            with open(os.path.join(self.tmp.name, "x.log"), encoding="utf-8") as f:
                self.assertNotIn("geheim", f.read())
            # Sperre beendet die Chat-Sitzung
            self.admin("SetSanction", {"accountId": aid, "status": "ban"})
            with self.assertRaises(ConnectionResetError):
                say("weg")
        finally:
            xmpp_server.ROOMS.pop(room, None)
            xmpp_server.STATE_DIR, xmpp_server.CHAT = old

    def test_chat_log_retention(self):
        with tempfile.TemporaryDirectory() as d:
            log = chat_log.ChatLog(d)
            now = datetime.datetime.now(datetime.timezone.utc)
            log.append("r", "a", "a", "alt", now=now - datetime.timedelta(days=chat_log.RETENTION_DAYS + 1))
            log._purged_day = None
            log.append("r", "a", "a", "neu", now=now)
            self.assertEqual([e["Text"] for e in log.search()], ["neu"])

    def test_body_too_large(self):
        with socket.create_connection(("127.0.0.1", self.port), 5) as s:
            s.sendall(b"POST /AccountService.hqs/HealthCheck HTTP/1.1\r\nHost: x\r\n"
                      b"Content-Length: 999999999\r\n\r\n")
            self.assertIn(b" 413 ", s.recv(200))

    def test_unknown_token_rejected(self):
        self.assertEqual(self.game("x" * 24)[0], 401)
        self.assertEqual(request(self.base + "/AccountService.hqs/GetAccountInformation",
                                 method="GET")[0], 401)

    def test_login_body_not_logged(self):
        self.register("secretive", "supergeheim")
        with open(os.path.join(self.tmp.name, "log.jsonl"), encoding="utf-8") as f:
            self.assertNotIn("supergeheim", f.read())

    def test_display_name_codes(self):
        # Codes des finalen Clients (eigene Texte je Code), nicht die der alten DLL
        token = self.register("gina")
        def choose(name):
            status, _, text = request(self.base + "/AccountService.hqs/ChooseDisplayName",
                                      {"displayName": name}, {"t": token})
            return status, json.loads(text).get("Code") if status != 200 else None
        self.assertEqual(choose("a b")[1], 0x8002010c)
        self.assertEqual(choose("TheAdmin")[1], 0x80020110)
        self.assertEqual(choose("Gina99")[0], 200)
        other = self.register("hank")
        status, _, text = request(self.base + "/AccountService.hqs/ChooseDisplayName",
                                  {"displayName": "gina99"}, {"t": other})
        self.assertEqual(json.loads(text)["Code"], 0x8002010a)

    # --- Sanktionen ---------------------------------------------------------

    def test_ban_and_suspend(self):
        token = self.register("carol")
        aid = self.account_id("carol")
        self.assertEqual(self.admin("SetSanction", {"accountId": aid, "status": "ban"})[0], 200)
        self.assertEqual(self.game(token)[0], 401)  # Bann beendet die Sitzung
        self.assertEqual(self.launcher("login", "carol", "geheim123"), {"Error": "banned"})
        self.admin("SetSanction", {"accountId": aid, "status": "suspend", "hours": 2})
        r = self.launcher("login", "carol", "geheim123")
        self.assertEqual(r["Error"], "suspended")
        self.assertTrue(r["Until"])
        self.admin("SetSanction", {"accountId": aid, "status": "none"})
        self.assertIn("Token", self.launcher("login", "carol", "geheim123"))

    def test_maintenance(self):
        token = self.register("maint")
        self.assertEqual(request(self.base + "/launcher/maintenance", method="GET")[0], 200)
        status, r = self.admin("SetMaintenance", {"maintenance": True})
        try:
            self.assertEqual((status, r["Maintenance"]), (200, True))
            self.assertGreaterEqual(r["Sessions"], 1)
            self.assertEqual(request(self.base + "/launcher/maintenance", method="GET")[0], 503)
            self.assertEqual(self.game(token)[0], 401)  # Sitzung beendet
            self.assertEqual(self.launcher("login", "maint", "geheim123"), {"Error": "maintenance"})
            self.assertEqual(self.launcher("register", "frank", "geheim123"), {"Error": "maintenance"})
        finally:
            self.admin("SetMaintenance", {"maintenance": False})
        self.assertEqual(request(self.base + "/launcher/maintenance", method="GET")[0], 200)
        self.assertIn("Token", self.launcher("login", "maint", "geheim123"))

    def test_bling_ledger(self):
        token = self.register("ledger")
        aid = self.account_id("ledger")
        self.admin("UpdateWallet", {"accountId": aid, "PremiumCash": 70})
        request(self.base + "/blings/buy?t=%s&amount=500" % token, method="GET")
        self.admin("UpdateWallet", {"accountId": aid, "PremiumCash": -20})
        path = os.path.join(self.tmp.name, "state", "%d.blings.jsonl" % aid)
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([(r["Delta"], r["Source"]) for r in rows],
                         [(70, "admin:UpdateWallet"), (500, "blings/buy"),
                          (-20, "admin:UpdateWallet")])
        self.assertEqual(rows[-1]["Balance"] - rows[0]["Balance"], 480)

    def test_balance_admin(self):
        status, d = self.admin("GetBalance", {})
        self.assertEqual((status, d["Values"]["Enabled"], d["ClientVersion"]), (200, False, ""))
        status, d = self.admin("SetBalance", {"values": {"Mine": {"Capacity": 5000}}})
        self.assertEqual(status, 400)
        status, d = self.admin("SetBalance", {"values": {"Enabled": True, "Mine": {"Capacity": 50}}})
        try:
            self.assertEqual((status, d["Values"]["Mine"]["Capacity"]), (200, 50))
            self.assertRegex(d["ClientVersion"], "^B[0-9a-f]{8}$")
        finally:
            self.admin("SetBalance", {"values": {"Enabled": False}})
        self.assertEqual(self.admin("GetBalance", {})[1]["ClientVersion"], "")

    # --- Anticheat ----------------------------------------------------------

    def test_client_hack_flags(self):
        token = self.register("mallory")
        aid = self.account_id("mallory")
        # Zufallsbits allein sind kein Verdacht, SpeedHackInjected (128) schon
        request(self.base + "/AccountService.hqs/GetAccountInformation",
                headers={"t": token, "rnd": str(1 | 4 | 1024)}, method="GET")
        _, rows = self.admin("ListAccounts", {})
        self.assertEqual(next(r for r in rows if r["Id"] == aid)["Cheat"]["Flags"], [])
        request(self.base + "/AccountService.hqs/GetAccountInformation",
                headers={"t": token, "rnd": str(128 | 4 | 1024)}, method="GET")
        _, rows = self.admin("ListAccounts", {})
        self.assertEqual(next(r for r in rows if r["Id"] == aid)["Cheat"],
                         {"Failures": 0, "Flags": ["SpeedHackInjected"]})

    # --- Bling-Shop ---------------------------------------------------------

    def test_bling_shop_token_in_url(self):
        token = self.register("dave")
        self.assertEqual(request(self.base + "/blings/?t=" + token, method="GET")[0], 200)
        status, _, text = request(self.base + "/blings/?t=falsch", method="GET")
        self.assertNotIn("dave", text)

    # --- Webtool ------------------------------------------------------------

    def test_admin_login(self):
        self.register("erin", "adminpass")
        self.register("frank")
        # ohne Admin offen (lokales Netz), damit man den ersten ernennen kann
        status, _ = self.admin("SetAdmin", {"accountId": self.account_id("erin"), "admin": True})
        self.assertEqual(status, 200)
        try:
            self.assertEqual(self.admin("ListAccounts", {})[0], 401)
            status, headers, _ = request(self.base + "/admin/session",
                                         {"action": "login", "name": "frank", "password": "geheim123"})
            self.assertEqual(status, 401)  # kein Admin
            status, headers, text = request(self.base + "/admin/session",
                                            {"action": "login", "name": "erin", "password": "adminpass"})
            self.assertEqual(json.loads(text)["Name"], "erin")
            cookie = headers["Set-Cookie"].split(";")[0].split("=", 1)[1]
            # Statusabfrage der Seite (POST ohne action) meldet nicht ab
            status, _, text = request(self.base + "/admin/session", {},
                                      {"Cookie": "admin_t=" + cookie})
            self.assertEqual(json.loads(text), {"Name": "erin", "Required": True})
            self.assertEqual(self.admin("ListAccounts", {}, cookie)[0], 200)
            # Spielsitzung bleibt von der Webtool-Anmeldung unberührt
            self.assertEqual(self.launcher("login", "erin", "adminpass").get("Name"), "erin")
            self.assertEqual(self.admin("ListAccounts", {}, cookie)[0], 200)
            # Passwortwechsel behält das Admin-Recht
            erin = self.account_id("erin", cookie)
            self.admin("SetPassword", {"accountId": erin, "password": "neuespass"}, cookie)
            status, d = self.admin("GetAccountDetail", {"accountId": erin}, cookie)
            self.assertTrue(d["IsAdmin"])
        finally:
            _, h, _ = request(self.base + "/admin/session",
                              {"action": "login", "name": "erin", "password": "neuespass"})
            cookie = h["Set-Cookie"].split(";")[0].split("=", 1)[1]
            self.admin("SetAdmin", {"accountId": self.account_id("erin", cookie), "admin": False}, cookie)
        self.assertEqual(self.admin("ListAccounts", {})[0], 200)


class FreeTrialTest(unittest.TestCase):
    def test_schedule(self):
        self.assertIsNone(free_trials.current(datetime.date(2026, 10, 17)))
        e = free_trials.current(datetime.date(2026, 11, 3))
        self.assertEqual((free_trials.iso(e["Start"]), free_trials.iso(e["End"])),
                         ("2026-11-01T00:00:00Z", "2026-11-07T23:59:59Z"))
        self.assertEqual(free_trials.from_id(e["Id"]), e)  # Id trägt das ganze Event
        heroes = {free_trials.current(datetime.date(2027, m, 1))["Hero"] for m in range(1, 5)}
        self.assertEqual(heroes, {2, 3, 4, 5})  # reihum alle Helden
        self.assertEqual(free_trials.current(datetime.date(2026, 10, 17), forced=5)["Hero"], 5)

    def test_grant_reductions_and_buy(self):
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"), log=lambda m: None,
                                           profile="new")
            now = datetime.datetime(2026, 11, 2, 12, tzinfo=datetime.timezone.utc)
            hero_id = free_trials.current(now.date())["Hero"]
            s.account["Heroes"] = [h for h in s.account["Heroes"]
                                   if h["HeroSpecContainerId"] != hero_id]
            names = [n for n, _ in s.free_trials(now)]
            self.assertEqual(names, ["HeroUnlocked", "FreeTrialActivated"])
            self.assertEqual(s.free_trials(now), [])  # nur einmal je Event
            hero = next(h for h in s.account["Heroes"] if h["HeroSpecContainerId"] == hero_id)
            self.assertEqual(hero["ExpirationDate"], "2026-11-07T23:59:59Z")
            hero["Level"] = 10
            done = [f["PriceReductionConditionCompletedId"] for _, f in s.free_trials(now)]
            self.assertEqual(done, [1, 2])  # Level 5 und 10
            # Kauf zum reduzierten Preis (950 - 50 - 100), Held bleibt erhalten
            sku = next(x for x in s.data.skus.values() if x["ItemType"] == 1
                       and x["ItemId"] == hero_id and x.get("IsActive")
                       and x["Price"]["CurrencyType"] == 1)
            s.account["Wallet"]["PremiumCash"] = 1000
            s._buy_hero(sku)
            self.assertEqual(s.account["Wallet"]["PremiumCash"], 1000 - (950 - 150))
            self.assertNotIn("ExpirationDate", hero)
            self.assertEqual(hero["Level"], 10)

    def test_expiry_and_late_buy(self):
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"), log=lambda m: None,
                                           profile="new")
            utc = datetime.timezone.utc
            now = datetime.datetime(2026, 11, 2, 12, tzinfo=utc)
            hero_id = free_trials.current(now.date())["Hero"]
            s.account["Heroes"] = [h for h in s.account["Heroes"]
                                   if h["HeroSpecContainerId"] != hero_id]
            other = next(h for h in (2, 3, 4, 5) if h != hero_id)
            s.account["Heroes"].append(s._new_hero(other))
            s.free_trials(now)
            s.account["SelectedHeroId"] = hero_id
            hero = next(h for h in s.account["Heroes"] if h["HeroSpecContainerId"] == hero_id)
            hero["Level"] = 7
            s.expire_trials(now)  # läuft noch
            self.assertIn(hero, s.account["Heroes"])
            later = datetime.datetime(2026, 11, 8, tzinfo=utc)
            self.assertIsNone(free_trials.active(later))
            s.expire_trials(later)
            self.assertNotIn(hero_id, [h["HeroSpecContainerId"] for h in s.account["Heroes"]])
            self.assertEqual(s.account["SelectedHeroId"], other)
            # späterer Kauf zum vollen Preis holt den Helden mit Level zurück
            sku = next(x for x in s.data.skus.values() if x["ItemType"] == 1
                       and x["ItemId"] == hero_id and x.get("IsActive")
                       and x["Price"]["CurrencyType"] == 1)
            s.account["Wallet"]["PremiumCash"] = 1000
            s._buy_hero(sku)
            self.assertEqual(s.account["Wallet"]["PremiumCash"], 50)
            back = next(h for h in s.account["Heroes"] if h["HeroSpecContainerId"] == hero_id)
            self.assertEqual((back["Level"], back.get("ExpirationDate")), (7, None))
            self.assertEqual(s.account[s.EXPIRED_TRIALS], [])


    def test_patcher_versions(self):
        import patcher
        pkgs = patcher.packages(datetime.date(2026, 11, 3))
        self.assertEqual(sorted(p.rm_type for p in pkgs), [2, 7, 8, 10, 11])
        ui = pkgs.pop()
        self.assertEqual(len({p.version for p in pkgs}), 1)  # Daten- und CRC-Pakete gleich
        version = pkgs[0].version
        # UI-Patches als ganze Dateien, Steam-UI als Ausgangsstand
        old, new = ui.files("280139"), ui.files(ui.version)
        self.assertRegex(ui.version, r"^280139\.U[0-9a-f]{8}$")
        self.assertEqual(old.keys(), new.keys())
        self.assertTrue(all(old[k] != new[k] for k in old))
        self.assertRegex(version, r"^104956\.Halloween\.T\d+$")
        files = pkgs[1].files(version)[patcher.SETTINGS2]
        self.assertIn(b'"Id": %d' % free_trials.current(datetime.date(2026, 11, 3))["Id"],
                      __import__("settings_archive").read(files)[0])
        self.assertEqual(pkgs[0].files(version), pkgs[0].files("104956.Halloween"))


    def test_client_exe_and_crc_lists(self):
        import patcher, zlib
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "mq.exe")
            with open(exe, "wb") as f:
                f.write(b"MZ neue Exe")
            patcher.CLIENT_EXE = exe
            try:
                pkgs = {p.rm_type: p for p in patcher.packages(datetime.date(2026, 11, 3))}
                game, crc = pkgs[1], pkgs[9]
                self.assertEqual(game.version, "280139.X%08x" % zlib.crc32(b"MZ neue Exe"))
                self.assertEqual(crc.version, game.version)
                listed = json.loads(crc.files(crc.version)["crc/GameBinCRC.json"])
                entry = next(e for e in listed["RMPackagesCRCList"][0]["RMPackageFileCRCList"]
                             if e["InstallationRelativePath"] == "MightyQuest.exe")
                self.assertEqual(entry["FileCRCInfo"], {"CRC": zlib.crc32(b"MZ neue Exe"),
                                                        "FileSize": 11})
                # Steam-Stand: Liste unverändert
                self.assertEqual(crc.files("280139")["crc/GameBinCRC.json"],
                                 patcher._read(os.path.join(patcher.ROOT, "server", "data",
                                                            "crc", "GameBinCRC.json")))
                data_crc = pkgs[7].files(pkgs[7].version)["crc/DataBinCRC.json"]
                boot = pkgs[2].files(pkgs[2].version)["Bin/Boot.tsc"]
                self.assertIn(b'"CRC":%d' % zlib.crc32(boot), data_crc)
                # ältere eigene Exe (unbekannter Stand): ganze Exe und Liste
                self.assertEqual(game.installed_files("280139.X00000000"), {})
                self.assertIsNotNone(crc.installed_files("280139.X00000000"))
            finally:
                patcher.CLIENT_EXE = None


class BalanceTest(unittest.TestCase):
    """Bling-Mine über balance.py: Werte, Plündergrenze, Patcher-Versionen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        balance.load(os.path.join(self.tmp.name, "balance.json"))

    def tearDown(self):
        balance.load(os.path.join(self.tmp.name, "fehlt.json"))
        balance._data = {"Values": balance.defaults(), "History": {}, "Changed": None}
        self.tmp.cleanup()

    def mine_castle(self, amount):
        return {"Level": 10, "_MineStatuses": {"7": {"CumulatedAmount": amount}},
                "Rooms": [{"Buildings": [{"Id": 7, "SpecContainerId": balance.BLING_MINE}]}]}

    def test_off_is_original(self):
        self.assertEqual(castles.mine_rank(16, 1)["Capacity"], 25)
        self.assertEqual(loot.stealable_buildings(self.mine_castle(20), 0, 0)[7][1], 20)
        self.assertEqual(balance.client_version(), "")

    def test_mine_rules_and_patch(self):
        today = datetime.date(2026, 3, 10)
        before = next(p for p in patcher.packages(today) if p.rm_type == 2).version
        balance.update({"Enabled": True}, "2026-03-10T00:00:00Z")
        spec = castles.mine_rank(16, 1)
        self.assertEqual((spec["ProductionPeriod"], spec["Capacity"]), ("4h", 42))
        self.assertEqual(loot.stealable_buildings(self.mine_castle(20), 0, 0)[7][1], 1)
        balance.update({"Mine": {"ProductionHours": 1, "StealHours": 3}}, "x")
        self.assertEqual(loot.stealable_buildings(self.mine_castle(20), 0, 0)[7][1], 3)
        after = next(p for p in patcher.packages(today) if p.rm_type == 2).version
        self.assertEqual(after, before + "." + balance.client_version())
        files_on = patcher._data_bin_files(after)[patcher.SETTINGS_BIN]
        files_off = patcher._data_bin_files(before)[patcher.SETTINGS_BIN]
        self.assertEqual(files_off, patcher._settings_bin(""))
        content = settings_archive.read(files_on)[0]
        i = content.index(balance.MINE_FILE)
        self.assertIn(b'"ProductionPeriod":"1h"', content[i:i + 3000])
        self.assertIn(b'"Capacity":42,', content[i:i + 3000])
        s = content.index(b'"Code":"15522"')
        self.assertRegex(content[s:s + 300], rb'"Amount":500\b')
        self.assertEqual(balance.sku_price(account_state.GameData().skus["15522"])["Amount"], 500)
        o = content.index(balance.OBJECTIVE_FILE)
        text = content[o:content.index(b"\x00", o + len(balance.OBJECTIVE_FILE))]
        blings = re.findall(rb'"PremiumCash",\s*"Amount":(\d+)', text)
        self.assertEqual(blings, [b"200"] * 7 + [b"150"])
        self.assertEqual(objectives.rewards(304)[0]["PremiumCash"], 150)
        o = content.index(balance.LEAGUE_FILE)
        text = content[o:content.index(b"\x00", o + len(balance.LEAGUE_FILE))]
        self.assertIn(b'"Amount":200', text)  # Liga 6, Platz 1: 100 x 200 %
        self.assertEqual(competitions.reward(1, 5)["RewardItems"][0]
                         ["CurrencyAmount"]["Amount"], 50)
        # alter Stand bleibt bekannt (Deltas von dort), unbekannter nicht
        self.assertIsNotNone(patcher._version_parts(after))
        self.assertIsNone(patcher._version_parts(before + ".Bdeadbeef"))

    def test_bling_loot(self):
        account, now = {}, 1_000_000
        loot_table = {1: {"Gold": 0}, 2: {"Gold": 0}}
        loot.add_bling_drop(loot_table, account, now)  # aus: nichts
        self.assertFalse(any("PremiumCash" in x for x in loot_table.values()))
        balance.update({"Enabled": True, "Loot": {"Chance": 100, "Amount": 400,
                                                  "WeeklyCap": 600}}, "x")
        loot.add_bling_drop(loot_table, account, now)
        self.assertEqual(sum(x.get("PremiumCash", 0) for x in loot_table.values()), 400)
        loot.record_bling_loot(account, 400, now)
        table2 = {1: {}}
        loot.add_bling_drop(table2, account, now + 60)
        self.assertEqual(table2[1]["PremiumCash"], 200)  # Rest bis zur Grenze
        loot.record_bling_loot(account, 200, now + 60)
        table3 = {1: {}}
        loot.add_bling_drop(table3, account, now + 120)
        self.assertNotIn("PremiumCash", table3[1])
        # nach 7 Tagen wieder frei, alte Einträge fallen weg
        later = now + loot.BLING_LOOT_WINDOW + 61
        self.assertEqual(loot.bling_loot_left(account, later), 600)
        loot.record_bling_loot(account, 0, later)
        self.assertEqual(account[loot.BLING_LOOT], [])

    def test_bling_shop_pack(self):
        st = account_state.AccountState(os.path.join(self.tmp.name, "a.json"),
                                        log=lambda m: None, profile="new", account_id=7)
        balance.update({"Enabled": True}, "x")
        self.assertNotIn("EarlyHeroAccess", special_packs.pack(66))
        heroes = len(st.account["Heroes"])
        st.account["Wallet"]["PremiumCash"] = 3999
        self.assertEqual(st.buy_special_pack(66, 4000), "blings")
        st.account["Wallet"]["PremiumCash"] = 4100
        self.assertEqual(st.buy_special_pack(66, 4000), "ok")
        self.assertEqual(st.account["Wallet"]["PremiumCash"], 100)
        self.assertEqual(len(st.account["Heroes"]), heroes)  # kein Heldenzugang
        events = st.take_pack_events()
        self.assertEqual(events[0][0], "WalletUpdated")
        self.assertTrue(any(e[0] in ("HeroInventoryAdded", "BuyBackAdded") for e in events))
        self.assertEqual(st.buy_special_pack(66, 4000), "owned")
        self.assertEqual(dict(bling_shop.offers(None)).get(67), None)  # nur im Event
        self.assertEqual(dict(bling_shop.offers("Halloween"))[67], 1500)

    def test_ledger_kinds_and_play_time(self):
        st = account_state.AccountState(os.path.join(self.tmp.name, "a.json"),
                                        log=lambda m: None, profile="new", account_id=7)
        balance.update({"Enabled": True, "Achievements": {"1": 30}}, "x")
        st.account["CompletedAchievements"] = [1]
        with st.lock:
            st._check_achievements()
            st._save()
        with open(st.ledger, encoding="utf-8") as f:
            last = json.loads(f.readlines()[-1])
        self.assertEqual(last["Kinds"], {"achievements": 30})
        t = datetime.datetime(2026, 10, 17, 12, 0, tzinfo=datetime.timezone.utc)
        st.seen(t)
        st.seen(t + datetime.timedelta(minutes=6))   # zählt
        st.seen(t + datetime.timedelta(minutes=60))  # Pause, zählt nicht
        self.assertEqual(st.account[st.PLAY_TIME], {"2026-10-17": 360})

    def test_objective_blings_off(self):
        self.assertEqual(objectives.rewards(100)[0]["PremiumCash"], 50)

    def test_achievement_blings(self):
        st = account_state.AccountState(os.path.join(self.tmp.name, "a.json"),
                                        log=lambda m: None, profile="new", account_id=7)
        st.account["CompletedAchievements"] = [1, 2]
        st._check_achievements()
        self.assertEqual(st.account["Wallet"]["PremiumCash"], 0)  # aus: nichts
        before = st.account["Wallet"]["PremiumCash"]
        balance.update({"Enabled": True, "Achievements": {"2": 100}}, "x")
        st.events = []
        st._check_achievements()  # rückwirkend für schon erreichte
        self.assertEqual(st.account["Wallet"]["PremiumCash"] - before, 10 + 100)
        self.assertEqual(st.events[-1][0], "WalletUpdated")
        st.events = []
        st._check_achievements()  # nur einmal
        self.assertEqual(st.account["Wallet"]["PremiumCash"] - before, 110)
        self.assertEqual(st.events, [])

    def test_achievement_ui_patch(self):
        import ui_patches
        off = ui_patches.patched(patcher.GAME_DATA)
        self.assertNotIn(b"achievementBlings", off["Data/UI/Js/hyperquest.extensions.js"])
        self.assertNotIn(b"achievementBlings", off["Data/UI/Html/de/TopView.html"])
        # 10. Probe-Held: Kaufknopf geht gleich in den Kauf mit Trial-Rabatt
        self.assertIn(b'skuCode={{:SkuCode}}{{if !HeroModel.IsHeroOwned && HeroModel.IsInFreeTrial}}'
                      b'&isPremiumCashConfirmationPurchase=1{{/if}}" class="buy"',
                      off["Data/UI/Html/en/TopView.html"])
        v_off = patcher._ui_version()
        balance.update({"Enabled": True, "Achievements": {"1": 0, "2": 33}}, "x")
        on = ui_patches.patched(patcher.GAME_DATA)
        js = on["Data/UI/Js/hyperquest.extensions.js"]
        self.assertIn(b'"2": 33', js)
        self.assertNotIn(b'"1": 0', js)
        self.assertIn(b"~achievementBlings(Achievement.Id)", on["Data/UI/Html/de/TopView.html"])
        # alter UI-Stand: alle Dateien neu statt gar kein Patch
        self.assertNotEqual(patcher._ui_version(), v_off)
        self.assertEqual(patcher._game_ui_files(v_off), {})


class LeagueBonusTest(unittest.TestCase):
    def test_attack_bonus(self):
        self.assertEqual(trophies.attack_bonus({}), 0.0)
        self.assertAlmostEqual(trophies.attack_bonus({"LeagueId": 4, "SubLeagueId": 1}), 0.09)


class ShieldTest(unittest.TestCase):
    def test_new_shield_replaces_old(self):
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"), log=lambda m: None,
                                           profile="new")
            now = datetime.datetime.now(datetime.timezone.utc)
            first = s.add_shield(3600, now)[-1][1]["ExpirableId"]
            out = s.add_shield(3600, now)
            self.assertEqual(out[0], ("ShieldExpired", {"ExpirableId": first}))
            shields = [x for x in s.account["Expirables"] if x["ExpirableType"] == "ShieldEnd"]
            self.assertEqual([x["Id"] for x in shields], [s.account["BuildInfo"]["ShieldEndExpirableId"]])


class MaterialMineTest(unittest.TestCase):
    def test_levels_theft_and_harvest(self):
        import attack
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"), log=lambda m: None,
                                           profile="new")
            room = {"Buildings": [{"Id": 999, "Rank": 1, "SpecContainerId": loot.MATERIAL_MINE}]}
            s.account["BuildInfo"]["Draft"]["Rooms"].append(room)
            # Stand von vor den Zutaten: volles Paket ohne Timer
            status = {"CumulatedAmount": 10, "IsActive": True, "IsDestroyed": False,
                      "ProductionExpirableId": account_state.NO_EXPIRABLE,
                      "ShieldExpirableId": account_state.NO_EXPIRABLE}
            s.account["BuildInfo"].setdefault("MineStatuses", {})["999"] = status
            now = datetime.datetime.now(datetime.timezone.utc)
            basic = set(__import__("item_drops").material_templates("Basic"))

            def rolled():
                return sum(i["TemplateId"] not in basic for i in status["CumulatedHeroItems"])

            s.material_mines(now)
            self.assertEqual((status["Productionlevel"], len(status["CumulatedHeroItems"])), (1, 10))
            for day, want in [(1, 2), (2, 4), (5, 10), (9, 10)]:
                s.material_mines(now + datetime.timedelta(hours=23 * day + 1))
                self.assertEqual(rolled(), want)
            self.assertEqual(status["Productionlevel"], 6)
            self.assertEqual(status["ProductionExpirableId"], account_state.NO_EXPIRABLE)

            c = {"Level": 5, "Rooms": [room], "_MineStatuses": {"999": dict(status)}}
            offer = loot.stealable_materials(c)
            self.assertEqual((len(offer[999][0]), offer[999][1]), (2, False))
            _, lost, destroyed = attack._pillaged_materials(
                {"material_mines": offer}, [{"CastleBuildingId": 999, "IsDestroyed": True}])
            s._pillage_material_mines(s.account["BuildInfo"]["MineStatuses"],
                                      {"material_mines": lost, "material_destroyed": destroyed,
                                       "mine_shield": 3600}, set(), now)
            self.assertEqual(status["CumulatedAmount"], 8)
            self.assertNotEqual(status["ShieldExpirableId"], account_state.NO_EXPIRABLE)
            self.assertNotEqual(status["ProductionExpirableId"], account_state.NO_EXPIRABLE)

            s.events = []
            s._cmd_HarvestMineBuildingCommand({"MineBuildingId": 999, "CurrencyType": 0})
            result = s.events[0][1]["Result"]
            self.assertEqual((result["EntityHarvestType"], len(result["HarvestedHeroItems"])),
                             ("CraftingMaterialMine", 8))
            self.assertEqual((status["Productionlevel"], status["CumulatedHeroItems"]), (1, []))


class BeltTest(unittest.TestCase):
    def test_belts_follow_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.json")
            s = account_state.AccountState(path, log=lambda m: None, profile="new")
            hero = s._new_hero(2)
            s.account["Heroes"].append(hero)
            tid = hero["EquippedConsumables"][0]["TemplateId"]
            s.account["Inventory"]["HeroItems"].append({
                "SlotIndex": 99, "StackCount": 3,
                "Item": {"$type": account_state.T("HeroConsumableItem"), "TemplateId": tid}})
            hero["EquippedConsumables"][0]["StackCount"] = 0  # veralteter Gürtel
            s._save()
            self.assertEqual(hero["EquippedConsumables"][0]["StackCount"], 3)
            # Trank im Kampf: Client erfährt den neuen Stapelstand
            ability = s.data.consumables[tid]["AbilityId"]
            self.assertEqual(s._use_consumables(2, [ability]),
                             [("HeroInventoryUpdated", {"SlotIndex": 99, "StackCount": 2})])
            self.assertEqual(s._use_consumables(2, [ability, ability]),
                             [("HeroInventoryRemoved", {"SlotIndex": 99})])

    def test_belt_refills_other_potion(self):
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"),
                                           log=lambda m: None, profile="new")
            hero = s._new_hero(2)
            hero["Level"] = 5
            s.account["Heroes"].append(hero)
            hero["EquippedConsumables"][0]["TemplateId"] = 2
            HC = account_state.T("HeroConsumableItem")
            for idx, tid, n in ((98, 2, 1), (99, 1, 4), (97, 3, 5)):  # 3 erst ab Level 9
                s.account["Inventory"]["HeroItems"].append(
                    {"SlotIndex": idx, "StackCount": n, "Item": {"$type": HC, "TemplateId": tid}})
            s._save()
            events = s._use_consumables(2, [s.data.consumables[2]["AbilityId"]])
            self.assertEqual([e[0] for e in events],
                             ["HeroInventoryRemoved", "HeroConsumableUnequip", "HeroConsumableEquip"])
            self.assertEqual(events[2][1]["ConsumableItem"]["TemplateId"], 1)
            self.assertEqual(events[2][1]["ConsumableItem"]["StackCount"], 4)
            # Trank 1 noch vorrätig: kein Wechsel
            self.assertEqual([e[0] for e in s._use_consumables(2, [s.data.consumables[1]["AbilityId"]])],
                             ["HeroInventoryUpdated"])


class EquipTest(unittest.TestCase):
    def _state(self, d):
        s = account_state.AccountState(os.path.join(d, "a.json"),
                                       log=lambda m: None, profile="new")
        hero = s._new_hero(2)  # Knight, Level 1
        s.account["Heroes"].append(hero)
        return s, hero

    def _bag(self, s, idx, item):
        s.account["Inventory"]["HeroItems"].append(
            {"$type": account_state.T("AccountInventorySlot"), "SlotIndex": idx,
             "StackCount": 1, "Item": item})

    def test_default_equipment_never_in_bag(self):
        with tempfile.TemporaryDirectory() as d:
            s, hero = self._state(d)
            self._bag(s, 5, s._item_from_template(1, level=1))  # Longsword
            s._cmd_HeroEquipmentEquipCommand(
                {"HeroId": 2, "SourceSlotId": 5, "DestinationSlot": 8})
            self.assertEqual(hero["Equipment"]["MainHand"]["TemplateId"], 1)
            self.assertEqual(s._slots(), [])  # Default-Waffe verfällt
            with self.assertRaises(ValueError):  # Default-Schulter bleibt dran
                s._cmd_HeroEquipmentUnequipCommand(
                    {"HeroId": 2, "SourceSlot": 2, "DestinationSlotId": 6})
            # Altbestand: Default-Item in der Tasche, Slot leer -> zurück an den Helden
            self._bag(s, 7, hero["Equipment"]["Shoulders"])
            hero["Equipment"]["Shoulders"] = None
            self.assertTrue(s._drop_default_equipment())
            self.assertEqual(hero["Equipment"]["Shoulders"]["TemplateId"], 132)
            self.assertEqual(s._slots(), [])

    def test_equip_checks_level_and_class(self):
        with tempfile.TemporaryDirectory() as d:
            s, hero = self._state(d)
            self._bag(s, 5, s._item_from_template(1, level=10))
            self._bag(s, 6, s._item_from_template(37, level=1))  # Typ 9: kein Knight
            for idx in (5, 6):
                with self.assertRaises(ValueError):
                    s._cmd_HeroEquipmentEquipCommand(
                        {"HeroId": 2, "SourceSlotId": idx, "DestinationSlot": 8})
            self.assertEqual(len(s._slots()), 2)  # nichts verloren


class HeroLevelTest(unittest.TestCase):
    def test_admin_raises_level(self):
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"),
                                           log=lambda m: None, profile="new")
            s.account["Heroes"].append(s._new_hero(5))
            hero, xp, changed = s.admin_hero_level(5, 5)
            self.assertEqual((hero["Level"], changed), (5, True))
            self.assertEqual(hero["XP"], loot.xp_per_level()[4])
            self.assertEqual(s.admin_hero_level(5, 3)[1:], (0, False))  # nie abwärts


class BoostTest(unittest.TestCase):
    def test_activation_frees_slot_in_client(self):
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"),
                                           log=lambda m: None, profile="new")
            s.account["Inventory"]["HeroItems"].append({
                "SlotIndex": 7, "StackCount": 1,
                "Item": {"$type": account_state.T("HeroConsumableItem"), "TemplateId": 1116}})
            s.events = []
            s._cmd_ActivateConsumableCommand({"ConsumableTemplateId": 1116,
                                              "InventorySlotIndex": 7})
            self.assertEqual([n for n, _ in s.events],
                             ["HeroInventoryRemoved", "ConsumableActivated", "ExpirableAdded"])
            self.assertNotIn(7, s._occupied())


class LimitsTest(unittest.TestCase):
    def test_login_throttle(self):
        with tempfile.TemporaryDirectory() as d:
            a = auth.Auth(d)
            a.set_password("dave", "geheim123")
            for _ in range(limits.MAX_FAILURES):
                self.assertFalse(a.check("dave", "falsch", "10.0.0.1"))
            # gesperrt, auch mit richtigem Passwort und von anderer IP
            with self.assertRaises(auth.AuthError):
                a.check("dave", "geheim123", "10.0.0.2")
            with self.assertRaises(auth.AuthError):
                a.check("other", "x", "10.0.0.1")
            a.set_password("eve", "geheim123")
            self.assertTrue(a.check("eve", "geheim123", "10.0.0.3"))

    def test_connection_limit(self):
        c = limits.ConnectionLimit(2)
        self.assertTrue(c.acquire("1.2.3.4") and c.acquire("1.2.3.4"))
        self.assertFalse(c.acquire("1.2.3.4"))
        self.assertTrue(c.acquire("5.6.7.8"))
        c.release("1.2.3.4")
        self.assertTrue(c.acquire("1.2.3.4"))


class SteamAuthTest(unittest.TestCase):
    ID = "76561198000000001"

    def test_new_steam_account_has_no_password(self):
        with tempfile.TemporaryDirectory() as d:
            a = auth.Auth(d)
            proof = a.steam_proof(self.ID)
            self.assertEqual(a.steam_proof_id(proof), self.ID)
            a.steam_create("Hero", proof)
            self.assertEqual(a.by_steam(self.ID), "Hero")
            # Beweis ist verbraucht; ohne Passwort keine Anmeldung per Name
            self.assertIsNone(a.steam_proof_id(proof))
            self.assertTrue(a.has_password("Hero"))
            self.assertFalse(a.check("Hero", "geheim123", "10.0.0.1"))
            self.assertFalse(a.check("Hero", "", "10.0.0.1"))
            # übersteht Neustart; der Admin kann ein Passwort setzen
            self.assertEqual(auth.Auth(d).by_steam(self.ID), "Hero")
            a.set_password("Hero", "geheim123")
            self.assertTrue(a.check("Hero", "geheim123"))
            self.assertEqual(a.by_steam(self.ID), "Hero")

    def test_link_existing_account(self):
        with tempfile.TemporaryDirectory() as d:
            a = auth.Auth(d)
            a.set_password("old", "geheim123")
            a.link_steam("old", a.steam_proof(self.ID))
            self.assertEqual(a.by_steam(self.ID), "old")
            self.assertTrue(a.check("old", "geheim123"))
            # eine SteamID gehört zu einem Account und umgekehrt
            a.set_password("other", "geheim123")
            with self.assertRaises(auth.AuthError):
                a.link_steam("other", a.steam_proof(self.ID))
            with self.assertRaises(auth.AuthError):
                a.link_steam("old", a.steam_proof("76561198000000002"))
            self.assertEqual(a.by_steam(self.ID), "old")
            a.delete("old")
            self.assertIsNone(a.by_steam(self.ID))

    def test_proof_unknown_or_expired(self):
        with tempfile.TemporaryDirectory() as d:
            a = auth.Auth(d)
            a.set_password("old", "geheim123")
            for proof in ("", "erfunden"):
                with self.assertRaises(auth.AuthError):
                    a.link_steam("old", proof)
                with self.assertRaises(auth.AuthError):
                    a.steam_create("neu", proof)
            proof = a.steam_proof(self.ID)
            a.steam_proofs[proof] = (self.ID, a.steam_proofs[proof][1] - auth.STEAM_PROOF_S - 1)
            with self.assertRaises(auth.AuthError):
                a.steam_create("neu", proof)
            # bestehender Name wird nicht überschrieben
            with self.assertRaises(auth.AuthError):
                a.steam_create("old", a.steam_proof(self.ID))

    def test_account_name(self):
        free = lambda n: False
        name = steam_auth.account_name
        self.assertEqual(name("Testuser", self.ID, free), "Testuser")
        self.assertEqual(name("Jörg der Große!", self.ID, free), "Jorg_der_Groe")
        self.assertEqual(name("日本語", self.ID, free), "Steam_000001")
        self.assertEqual(name("", self.ID, free), "Steam_000001")
        self.assertEqual(name("ab", self.ID, free), "Steam_000001")
        taken = {"hero", "hero_2"}
        self.assertEqual(name("Hero", self.ID, lambda n: n.lower() in taken), "Hero_3")
        long = name("x" * 40, self.ID, free)
        self.assertTrue(auth.NAME_RE.fullmatch(long), long)
        self.assertTrue(auth.NAME_RE.fullmatch(name("y" * 40, self.ID, lambda n: n == "y" * 20)))

    def test_ticket_checks(self):
        for ticket in ("", "xyz", "12"):
            with self.assertRaises(steam_auth.SteamError):
                steam_auth.verify(ticket)

    def test_ticket_only_once(self):
        ticket = "0123456789abcdef" * 4
        steam_auth._use_once(ticket)
        with self.assertRaises(steam_auth.SteamError) as e:
            steam_auth._use_once(ticket.upper())
        self.assertEqual(str(e.exception), "steam_reused")
        steam_auth._use_once("fedcba9876543210" * 4)

    def test_global_call_limit(self):
        saved = list(steam_auth._calls)
        try:
            steam_auth._calls[:] = [time.monotonic()] * steam_auth.MAX_CALLS_PER_MIN
            with self.assertRaises(steam_auth.SteamError) as e:
                steam_auth._count_call()
            self.assertEqual(str(e.exception), "steam_busy")
            self.assertEqual(steam_auth.persona(self.ID), "")  # ohne Aufruf
            steam_auth._calls[:] = [time.monotonic() - 61] * steam_auth.MAX_CALLS_PER_MIN
            steam_auth._count_call()
        finally:
            steam_auth._calls[:] = saved

    def test_profane_persona(self):
        if steam_auth.profanity.PATTERN is None:
            self.skipTest("keine Schimpfwortliste")
        bad = next(w for w in ("fuck", "shit", "cunt")
                   if steam_auth.profanity.filter_text(w) != w)
        self.assertEqual(steam_auth.account_name(bad, self.ID, lambda n: False), "Steam_000001")
        self.assertEqual(steam_auth.account_name(bad + " you", self.ID, lambda n: False),
                         "Steam_000001")

    def test_unlink_and_password_flags(self):
        with tempfile.TemporaryDirectory() as d:
            a = auth.Auth(d)
            a.steam_create("Hero", a.steam_proof(self.ID))
            self.assertFalse(a.has_hash("Hero"))
            with self.assertRaises(auth.AuthError):  # Admin braucht Passwort
                a.set_admin("Hero", True)
            self.assertEqual(a.steam_id("Hero"), self.ID)
            self.assertTrue(a.unlink_steam("Hero"))
            self.assertFalse(a.unlink_steam("Hero"))
            self.assertIsNone(a.by_steam(self.ID))
            self.assertIsNone(auth.Auth(d).by_steam(self.ID))

    def test_tickets_not_logged(self):
        qs = "steamID=7656&ticket=14000000ABCD&locale=en&steamTicket=99&x"
        red = game_server.redact_query(qs)
        self.assertNotIn("ABCD", red)
        self.assertNotIn("=99", red)
        self.assertIn("steamID=7656", red)
        self.assertIn("locale=en", red)
        line = 'GET /launcher/?steamID=1&ticket=14000000ABCD HTTP/1.1'
        self.assertNotIn("ABCD", game_server.SECRET_QUERY_RE.sub(r"\1=(redacted)", line))


class AdminWebAccessTest(unittest.TestCase):
    NETS =[ipaddress.ip_network("93.184.0.0/16")]

    def test_local_always(self):
        for ip in ("127.0.0.1", "192.168.0.10", "10.1.2.3"):
            self.assertTrue(game_server.admin_web_allowed(ip, False, False, []))

    def test_external_only_listed_net_tls_with_admin(self):
        allowed = game_server.admin_web_allowed
        self.assertTrue(allowed("93.184.2.7", True, True, self.NETS))
        self.assertFalse(allowed("93.184.2.7", False, True, self.NETS))  # Klartext
        self.assertFalse(allowed("93.184.2.7", True, False, self.NETS))  # kein Admin
        self.assertFalse(allowed("8.8.8.8", True, True, self.NETS))  # fremdes Netz


class CastleTest(unittest.TestCase):
    def test_limited_decoration_quota(self):
        # "[CE]"-Deko (Kontingent aus den Burg-Level-Paketen) zählt beim Setzen
        # mit; früher nach jedem Login wieder kaufbar
        with tempfile.TemporaryDirectory() as d:
            s = account_state.AccountState(os.path.join(d, "a.json"), log=lambda m: None,
                                           profile="new")
            s.account[s.SALE] = 1  # Startburg 1: Level 1 bringt 4 Deko-Kontingente
            mod = next(m for m in s.shop_sku_modifiers()
                       if m["LimitedQuantityMax"] and s.data.skus[m["SkuCode"]]["ItemType"] == 13)
            sku = s.data.skus[mod["SkuCode"]]
            field = account_state.CURRENCY[sku["Price"]["CurrencyType"]]
            s.account["Wallet"][field] = 10 ** 6
            room = 1
            s.account["BuildInfo"]["Draft"]["Rooms"].append({"Id": room})

            def place(i):
                s._cmd_AddCastleDecorationCommand({
                    "SkuCode": sku["Code"], "SpecContainerId": sku["ItemId"],
                    "RoomId": room, "Id": 9000 + i})
            for i in range(mod["LimitedQuantityMax"]):
                place(i)
            with self.assertRaises(ValueError):
                place(99)
            again = next(m for m in s.shop_sku_modifiers() if m["SkuCode"] == sku["Code"])
            self.assertEqual(again["LimitedQuantityConsumed"], mod["LimitedQuantityMax"])

    def test_huge_account_id(self):
        # früher Rekursion bis zum Stapelüberlauf (SendFriendshipInvitation)
        self.assertIsNone(castles.find_castle(10 ** 18))
        self.assertIsNone(profiles.fake_account(10 ** 18))

    def test_tutorial_castle_until_assignment_150(self):
        # Assignment 150 richtet die Auswahl auf Burg 3 aus; danach ausgeblendet
        def ids(done):
            r = castles.attack_selection(10, done, 3)
            return {c["DefenderAccountSummary"]["Id"]
                    for g in r["CastlesByLevel"] for c in g["Castles"]}
        self.assertIn(3, ids([]))
        self.assertNotIn(3, ids([150]))


class AntiCheatTest(unittest.TestCase):
    CUR = {"treasure": (100, 50), "buildings": {7: ("InGameCoin", 30, False, False)}}

    def test_honest(self):
        params = {"AttackFrameCount": 300, "AttackFrameDuration": 0.0333,
                  "TreasureRoomOpenFrameCount": 250, "KilledCreatureIds": [1, 2],
                  "TreasureRoomLootedGold": 100, "CastleRating": 5,
                  "PillagedMines": [{"CastleBuildingId": 7, "StolenAmount": 30},
                                    {"CastleBuildingId": 9, "StolenAmount": 0}]}
        cur = dict(self.CUR, started=time.monotonic() - 11)
        self.assertEqual(anticheat.end_attack_violations(params, cur), [])

    def test_violations(self):
        params = {"AttackFrameCount": 300, "AttackFrameDuration": 0.0333,
                  "TreasureRoomOpenFrameCount": 301, "LootedGoldCreatureIds": [1, 1],
                  "TreasureRoomLootedGold": 101, "CastleRating": 6,
                  "PillagedMines": [{"CastleBuildingId": 7, "StolenAmount": 31},
                                    {"CastleBuildingId": 8, "StolenAmount": 5}]}
        # Kampf von 10 s Spielzeit eine Sekunde nach dem Start beendet
        cur = dict(self.CUR, started=time.monotonic() - 1)
        self.assertEqual(len(anticheat.end_attack_violations(params, cur)), 7)


class ProfanityTest(unittest.TestCase):
    def test_filter(self):
        self.assertEqual(filter_text("what the fuck!"), "what the ****!")
        self.assertEqual(filter_text("Du Arschloch"), "Du *********")
        self.assertEqual(filter_text("sh1t"), "****")
        # nur ganze Wörter, harmlose Wörter anderer Sprachen bleiben
        self.assertEqual(filter_text("Assassin con amigo"), "Assassin con amigo")

    def test_chat_body(self):
        # der Client schickt den Text URL-kodiert
        m = xmpp_server.re.match(r"<body>(.*)</body>", "<body>Hallo+Claude+%3C3+shit</body>")
        self.assertEqual(xmpp_server._chat_body(m),
                         "<body>Hallo Claude &lt;3 shit</body>"
                         "<bodyfiltered>Hallo Claude &lt;3 ****</bodyfiltered>")


if __name__ == "__main__":
    unittest.main()
