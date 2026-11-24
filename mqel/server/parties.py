"""Parties for the co-op raids (raids.py, UI ui_mods/party.html, guide
docs/89-coop-raids.md): up to MAX_SIZE friends. The leader invites friends,
an invited player accepts or declines; anyone can leave, the leader can
kick (a leaving leader hands over to the next member). Live raid status
(health, gold, XP, items, state) comes from each member's game UI every
few seconds and is shown to the others.

Stored in <state>/parties.json (parties and invites; live status only in
memory).
"""
import json
import os
import threading
import time

MAX_SIZE = 4
INVITE_TTL = 15 * 60
LIVE_TTL = 20            # seconds a live status counts as current


class PartyError(ValueError):
    pass


class Parties:
    def __init__(self, path, players, log=print):
        self.path = path
        self.players = players
        self.log = log
        self.lock = threading.RLock()
        self.live = {}       # account id -> {..., "Time"}
        self.bonus = {}      # account id -> last party bonus (shown once)
        try:
            with open(path, encoding="utf-8") as f:
                self.db = json.load(f)
        except (OSError, ValueError):
            self.db = {}
        self.db.setdefault("NextId", 1)
        self.db.setdefault("Parties", {})   # id -> {Id, Leader, Members, Created}
        self.db.setdefault("Invites", {})   # account id -> [{From, Party, Time}]
        self.db.setdefault("Clears", {})    # party id -> {"seed/tier": [account ids]}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.db, f)
        os.replace(tmp, self.path)

    # -- lookups --

    def party_of(self, account_id):
        aid = int(account_id)
        return next((p for p in self.db["Parties"].values() if aid in p["Members"]), None)

    def members(self, account_id):
        p = self.party_of(account_id)
        return list(p["Members"]) if p else [int(account_id)]

    def _account(self, account_id):
        p = self.players.by_account_id(int(account_id))
        return p.state.snapshot() if p else None

    def _name(self, account_id):
        a = self._account(account_id)
        return (a or {}).get("DisplayName") or str(account_id)

    def _friends(self, account_id):
        a = self._account(account_id) or {}
        return {int(f["Id"]) for f in a.get("Friends") or []}

    # -- actions --

    def invite(self, account_id, target):
        aid, tid = int(account_id), int(target)
        with self.lock:
            if tid == aid:
                raise PartyError("You can't invite yourself.")
            if tid not in self._friends(aid):
                raise PartyError("You can only invite friends.")
            p = self.party_of(aid)
            if p and p["Leader"] != aid:
                raise PartyError("Only the party leader can invite.")
            if p and len(p["Members"]) >= MAX_SIZE:
                raise PartyError("Your party is full (%d players)." % MAX_SIZE)
            if self.party_of(tid) and self.party_of(tid) is p:
                raise PartyError("Already in your party.")
            if not p:
                pid = str(self.db["NextId"])
                self.db["NextId"] += 1
                p = self.db["Parties"][pid] = {"Id": pid, "Leader": aid, "Members": [aid],
                                               "Created": int(time.time())}
            lst = [i for i in self.db["Invites"].get(str(tid), [])
                   if i["Party"] != p["Id"] and time.time() - i["Time"] < INVITE_TTL]
            lst.append({"From": aid, "Party": p["Id"], "Time": int(time.time())})
            self.db["Invites"][str(tid)] = lst
            self._save()
        self.log(f"    [party] {aid} lädt {tid} in Party {p['Id']} ein")
        return {"Party": p["Id"]}

    def accept(self, account_id, party_id):
        aid = int(account_id)
        with self.lock:
            inv = [i for i in self.db["Invites"].get(str(aid), []) if i["Party"] == str(party_id)]
            p = self.db["Parties"].get(str(party_id))
            if not inv or not p or time.time() - inv[0]["Time"] > INVITE_TTL:
                raise PartyError("This invitation has expired.")
            if len(p["Members"]) >= MAX_SIZE:
                raise PartyError("That party is full.")
            self._leave(aid)
            p = self.db["Parties"].get(str(party_id))
            if not p:
                raise PartyError("That party no longer exists.")
            p["Members"].append(aid)
            self.db["Invites"][str(aid)] = [i for i in self.db["Invites"].get(str(aid), [])
                                            if i["Party"] != str(party_id)]
            self._save()
        self.log(f"    [party] {aid} tritt Party {party_id} bei")
        return {"Party": str(party_id)}

    def decline(self, account_id, party_id):
        with self.lock:
            self.db["Invites"][str(int(account_id))] = [
                i for i in self.db["Invites"].get(str(int(account_id)), []) if i["Party"] != str(party_id)]
            self._save()
        return {"Declined": True}

    def _leave(self, aid):
        p = self.party_of(aid)
        if not p:
            return
        p["Members"].remove(aid)
        p["Raid"] = None   # someone left: the party picks a new raid
        if len(p["Members"]) <= 1:
            # a party of one is no party: dissolve, drop its invites
            del self.db["Parties"][p["Id"]]
            for k, lst in self.db["Invites"].items():
                self.db["Invites"][k] = [i for i in lst if i["Party"] != p["Id"]]
            self.db["Clears"].pop(p["Id"], None)
        elif p["Leader"] == aid:
            p["Leader"] = p["Members"][0]

    def leave(self, account_id):
        with self.lock:
            self._leave(int(account_id))
            self._save()
        return {"Left": True}

    def kick(self, account_id, target):
        aid, tid = int(account_id), int(target)
        with self.lock:
            p = self.party_of(aid)
            if not p or p["Leader"] != aid:
                raise PartyError("Only the party leader can remove players.")
            if tid not in p["Members"] or tid == aid:
                raise PartyError("Not in your party.")
            self._leave(tid)
            self._save()
        return {"Kicked": True}

    # -- party raid: the leader picks, everyone readies, all start together --
    # party["Raid"] = {"Castle", "Seed", "Level", "Name", "Ready": [ids],
    #                  "Start": unix time or None, "Done": [ids], "Round"}

    START_DELAY = 6

    def select_raid(self, account_id, castle_id, seed, level, name):
        aid = int(account_id)
        with self.lock:
            p = self.party_of(aid)
            if not p or len(p["Members"]) < 2:
                raise PartyError("Make a party first (invite a friend).")
            if p["Leader"] != aid:
                raise PartyError("Only the party leader picks the raid.")
            old = p.get("Raid") or {}
            if old.get("Start") and not old.get("Over"):
                raise PartyError("Your party is in a raid: wait until everyone has finished.")
            p["Raid"] = {"Castle": int(castle_id), "Seed": seed, "Level": level, "Name": name,
                         "Ready": [aid], "Start": None, "Done": [], "Round": old.get("Round", 0) + 1}
            self._save()
        self.log(f"    [party] Party {p['Id']}: Raid {castle_id} gewählt")
        return {"Raid": p["Raid"]}

    def ready(self, account_id, yes):
        aid = int(account_id)
        with self.lock:
            p = self.party_of(aid)
            r = (p or {}).get("Raid")
            if not r or r.get("Start"):
                raise PartyError("No raid is waiting for you.")
            if not yes:
                p["Raid"] = None
                p["LastNo"] = self._name(aid)
                self._save()
                return {"Raid": None}
            if aid not in r["Ready"]:
                r["Ready"].append(aid)
            if all(m in r["Ready"] for m in p["Members"]):
                r["Start"] = time.time() + self.START_DELAY
            self._save()
            return {"Raid": r}

    def raid_seed(self, account_id):
        """Seed of the party's chosen raid (locked while it runs) or None."""
        p = self.party_of(account_id)
        r = (p or {}).get("Raid")
        return r["Seed"] if r and not r.get("Over") else None

    def raid_done(self, account_id, castle_id):
        """A member finished the party's raid castle; when all did, the
        leader can pick the next one."""
        aid = int(account_id)
        with self.lock:
            p = self.party_of(aid)
            r = (p or {}).get("Raid")
            if not r or r["Castle"] != int(castle_id) or not r.get("Start"):
                return
            if aid not in r["Done"]:
                r["Done"].append(aid)
            if all(m in r["Done"] for m in p["Members"]):
                r["Over"] = True
            self._save()

    # -- live raid status --

    def report(self, account_id, data):
        keep = ("Life", "MaxLife", "Gold", "LifeForce", "Xp", "Items", "State", "Castle")
        entry = {k: data.get(k) for k in keep if k in data}
        entry["Time"] = time.time()
        self.live[int(account_id)] = entry

    # -- raid clears (party bonus) --

    def record_clear(self, account_id, key):
        """Member cleared raid `key` ("seed/tier"); returns the party members
        when every member has now cleared it (bonus due), else None."""
        aid = int(account_id)
        with self.lock:
            p = self.party_of(aid)
            if not p or len(p["Members"]) < 2:
                return None
            done = self.db["Clears"].setdefault(p["Id"], {}).setdefault(key, [])
            if aid not in done:
                done.append(aid)
            due = all(m in done for m in p["Members"]) and "rewarded" not in done
            if due:
                done.append("rewarded")
            self._save()
            return list(p["Members"]) if due else None

    # -- view --

    def view(self, account_id, online, raid_of):
        """State for the UI. online(account id) -> bool; raid_of(account id)
        -> castle id of the running raid attack or None."""
        aid = int(account_id)
        with self.lock:
            p = self.party_of(aid)
            now = time.time()
            members = []
            for m in (p["Members"] if p else [aid]):
                a = self._account(m) or {}
                hero = next((h for h in a.get("Heroes") or []
                             if h["HeroSpecContainerId"] == a.get("SelectedHeroId")), {})
                live = self.live.get(m)
                members.append({"Id": m, "Name": a.get("DisplayName") or str(m),
                                "Level": hero.get("Level", 1), "Hero": hero.get("HeroSpecContainerId"),
                                "Leader": bool(p and p["Leader"] == m), "Me": m == aid,
                                "Online": online(m), "Raid": raid_of(m),
                                "Live": live if live and now - live.get("Time", 0) < LIVE_TTL else None})
            invites = [{"Party": i["Party"], "From": self._name(i["From"]), "FromId": i["From"],
                        "Size": len((self.db["Parties"].get(i["Party"]) or {}).get("Members") or [])}
                       for i in self.db["Invites"].get(str(aid), [])
                       if now - i["Time"] < INVITE_TTL and i["Party"] in self.db["Parties"]]
            in_party = set(p["Members"]) if p else {aid}
            friends = [{"Id": f, "Name": self._name(f), "Online": online(f),
                        "InParty": f in in_party, "Busy": bool(self.party_of(f)) and f not in in_party}
                       for f in sorted(self._friends(aid))]
        friends.sort(key=lambda x: (not x["Online"], x["Name"].lower()))
        raid = dict(p["Raid"]) if p and p.get("Raid") else None
        if raid:
            raid["Now"] = time.time()
        return {"Bonus": self.bonus.pop(aid, None), "Raid": raid,
                "LastNo": (p or {}).get("LastNo"), "Party": p["Id"] if p else None, "Leader": bool(p and p["Leader"] == aid) or not p,
                "Members": members, "Invites": invites, "Friends": friends, "Max": MAX_SIZE}
