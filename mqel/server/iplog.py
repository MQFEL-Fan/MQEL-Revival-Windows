"""IP addresses per account and the multiple-account rule (admin Players
tab, docs/06-public-server.md "Multiple accounts").

- Every launcher login and game request records the player's IP (first and
  last time, count). Kept in <state>/ip_log.json, written at most every
  SAVE_S seconds.
- A new account (launcher registration, new Steam player) is refused when
  another account already played from the same IP, unless the IP is on the
  whitelist (admin tool, Players > Multiple accounts) or the request comes
  from the server PC (loopback). The whitelist lives in the same file, so
  no address is written into the code or docs.
"""
import ipaddress
import json
import os
import threading
import time

SAVE_S = 60


class IpLog:
    def __init__(self, path, log=print):
        self.path = path
        self.log = log
        self.lock = threading.Lock()
        self._dirty = 0.0
        try:
            with open(path, encoding="utf-8") as f:
                self.db = json.load(f)
        except (OSError, ValueError):
            self.db = {}
        self.db.setdefault("Accounts", {})    # account id -> {ip: {First, Last, Count}}
        self.db.setdefault("Whitelist", [])   # IPs allowed to have several accounts
        self.db.setdefault("Refused", [])     # last refused registrations

    def _save(self, force=False):
        if not force and time.time() - self._dirty < SAVE_S:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.db, f)
        os.replace(tmp, self.path)
        self._dirty = time.time()

    @staticmethod
    def _local(ip):
        try:
            a = ipaddress.ip_address(ip)
            return a.is_loopback
        except ValueError:
            return True

    def seen(self, account_id, ip):
        if not ip or not account_id:
            return
        now = int(time.time())
        with self.lock:
            ips = self.db["Accounts"].setdefault(str(int(account_id)), {})
            e = ips.get(ip)
            if e is None:
                ips[ip] = {"First": now, "Last": now, "Count": 1}
                self._save(force=True)
                return
            if now - e["Last"] >= 60:
                e["Last"] = now
                e["Count"] += 1
                self._save()

    def accounts_on(self, ip):
        with self.lock:
            return sorted(int(a) for a, ips in self.db["Accounts"].items() if ip in ips)

    def whitelisted(self, ip):
        return self._local(ip) or ip in self.db["Whitelist"]

    def may_register(self, ip):
        """None if a new account may be made from ip, else the account ids
        already playing from it."""
        if self.whitelisted(ip):
            return None
        others = self.accounts_on(ip)
        return others or None

    def refused(self, ip, name, others):
        with self.lock:
            self.db["Refused"].append({"Time": int(time.time()), "Ip": ip, "Name": name, "Accounts": others})
            del self.db["Refused"][:-200]
            self._save(force=True)
        self.log(f"    [iplog] Registrierung {name!r} abgelehnt: IP hat schon Account(s) {others}")

    def set_whitelist(self, ips):
        clean = []
        for ip in ips:
            ip = str(ip).strip()
            if not ip:
                continue
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                raise ValueError("Not an IP address: %s" % ip)
            if ip not in clean:
                clean.append(ip)
        with self.lock:
            self.db["Whitelist"] = clean
            self._save(force=True)
        return clean

    def account_ips(self, account_id):
        """[{Ip, First, Last, Count, Others: [account ids], Whitelisted}]."""
        with self.lock:
            ips = dict(self.db["Accounts"].get(str(int(account_id)), {}))
            all_ = {a: set(v) for a, v in self.db["Accounts"].items()}
        out = []
        for ip, e in sorted(ips.items(), key=lambda kv: -kv[1]["Last"]):
            others = sorted(int(a) for a, s in all_.items() if ip in s and a != str(int(account_id)))
            out.append(dict(e, Ip=ip, Others=others, Whitelisted=self.whitelisted(ip)))
        return out

    def shared(self):
        """{account id: [other account ids sharing a non-whitelisted IP]}."""
        with self.lock:
            by_ip = {}
            for a, ips in self.db["Accounts"].items():
                for ip in ips:
                    by_ip.setdefault(ip, set()).add(int(a))
        out = {}
        for ip, accs in by_ip.items():
            if len(accs) < 2 or self.whitelisted(ip):
                continue
            for a in accs:
                out.setdefault(a, set()).update(accs - {a})
        return {a: sorted(v) for a, v in out.items()}

    def flush(self):
        with self.lock:
            self._save(force=True)
