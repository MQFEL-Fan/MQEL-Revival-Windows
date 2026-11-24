"""Import an exported player account (zip with manifest.json, account.json,
blings.jsonl) into a server state directory.

The zip format (Format 1):
  manifest.json   {"Format": 1, "Name": "<login name>", "AccountId": <id>,
                   "Login": {"SteamId": "<steamid64>"}   (and/or Salt/Hash)}
  account.json    AccountInformation (the saved game, server/state/<p>/<id>.json)
  blings.jsonl    Bling ledger (<id>.blings.jsonl), optional

The account keeps its original AccountId, so friends, guild members and
news entries between imported accounts still point at each other.

Stop the game server first (stop_servers.bat): it keeps players.json and
logins.json in memory and would overwrite the import.

Usage:
  python tools/import_account.py player1.zip player2.zip [--state server/state/new]
         [--replace]   an existing account with the same login name is renamed
                       to <name>_old; the imported one takes over its password
                       (if any) and gets the SteamId from the manifest
         [--dry-run]
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def server_running(port=8081):
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def read_zip(path):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for need in ("manifest.json", "account.json"):
            if need not in names:
                raise SystemExit(f"{path}: {need} missing")
        manifest = json.loads(z.read("manifest.json"))
        account = json.loads(z.read("account.json"))
        ledger = z.read("blings.jsonl") if "blings.jsonl" in names else b""
    if manifest.get("Format") != 1:
        raise SystemExit(f"{path}: unknown export format {manifest.get('Format')!r}")
    if account.get("AccountId") != manifest.get("AccountId"):
        raise SystemExit(f"{path}: AccountId in account.json ({account.get('AccountId')}) "
                         f"!= manifest ({manifest.get('AccountId')})")
    return manifest, account, ledger


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zips", nargs="+")
    ap.add_argument("--state", default=os.path.join(ROOT, "server", "state", "new"))
    ap.add_argument("--replace", action="store_true",
                    help="rename an existing account with the same name to <name>_old")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="import even if port 8081 is in use")
    args = ap.parse_args()

    state = os.path.abspath(args.state)
    if server_running() and not args.force and not args.dry_run:
        sys.exit("Port 8081 is in use: stop the game server first (stop_servers.bat), "
                 "or pass --force if that server uses a different state folder.")
    os.makedirs(state, exist_ok=True)
    players_path = os.path.join(state, "players.json")
    logins_path = os.path.join(state, "logins.json")
    players = load(players_path, {})
    logins = load(logins_path, {"users": {}, "sessions": {}})
    users = logins.setdefault("users", {})

    if not args.dry_run:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = state.rstrip("\\/") + "_backup_" + stamp
        shutil.copytree(state, backup)
        print("backup:", backup)

    for zpath in args.zips:
        manifest, account, ledger = read_zip(zpath)
        name, aid = manifest["Name"], int(manifest["AccountId"])
        login = manifest.get("Login") or {}
        steam_id = login.get("SteamId")
        print(f"\n{os.path.basename(zpath)}: {name} (AccountId {aid}"
              + (f", SteamId {steam_id})" if steam_id else ")"))

        owner = next((n for n, i in players.items() if i == aid), None)
        if owner not in (None, name):
            sys.exit(f"  AccountId {aid} already belongs to {owner!r}: not imported")
        password = {}
        if name in players and players[name] != aid:
            if not args.replace:
                sys.exit(f"  login name {name!r} already exists (AccountId {players[name]}); "
                         "use --replace to rename the existing one to <name>_old")
            old = name + "_old"
            n = 2
            while old in players or old in users:
                old, n = f"{name}_old{n}", n + 1
            players[old] = players.pop(name)
            entry = users.pop(name, {})
            password = {k: entry[k] for k in ("Salt", "Hash") if k in entry}
            # the old account keeps no login (no password, no SteamId)
            for tok in [t for t, u in logins.get("sessions", {}).items() if u == name]:
                del logins["sessions"][tok]
            print(f"  existing {name!r} (AccountId {players[old]}) renamed to {old!r}"
                  + ("; its password moves to the imported account" if password else ""))
        if steam_id:
            other = next((n for n, u in users.items()
                          if u.get("SteamId") == steam_id and n != name), None)
            if other:
                sys.exit(f"  SteamId {steam_id} is already linked to {other!r}: not imported")

        entry = users.setdefault(name, {})
        entry.update(password)
        entry.update({k: v for k, v in login.items() if k in ("Salt", "Hash", "SteamId")})
        players[name] = aid
        print(f"  login: {', '.join(sorted(entry)) or '(none)'}")

        acc_path = os.path.join(state, f"{aid}.json")
        if args.dry_run:
            print(f"  would write {acc_path}")
            continue
        save(acc_path, account)
        if ledger:
            with open(os.path.join(state, f"{aid}.blings.jsonl"), "wb") as f:
                f.write(ledger)
        print(f"  written {acc_path}" + (" + blings ledger" if ledger else ""))

    if not args.dry_run:
        save(players_path, players)
        save(logins_path, logins)
        print("\nplayers.json and logins.json updated:", state)


if __name__ == "__main__":
    main()
