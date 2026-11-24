"""Link (or unlink, or list) SteamIDs of accounts in logins.json, offline.

The running server keeps logins.json in memory and overwrites it, so stop it
first (stop_servers.bat). With the server running, use the web tool instead:
http://127.0.0.1:8081/admin -> Players -> account -> "Link Steam".

  python tools/link_steam.py --list
  python tools/link_steam.py PlayerName 76561198000000001 [OtherPlayer 76561198000000002 ...]
  python tools/link_steam.py --unlink PlayerName
  [--state server/state/new]

Find a SteamID64: the player's Steam profile URL (steamcommunity.com/profiles/7656...),
or the server log (/launcher/?steamID=... when they open the launcher).
"""

import argparse
import json
import os
import re
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEAM_RE = re.compile(r"7656119\d{10}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pairs", nargs="*", help="NAME STEAMID [NAME STEAMID ...]")
    ap.add_argument("--state", default=os.path.join(ROOT, "server", "state", "new"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--unlink", metavar="NAME", action="append", default=[])
    args = ap.parse_args()

    path = os.path.join(args.state, "logins.json")
    players = json.load(open(os.path.join(args.state, "players.json"), encoding="utf-8"))
    logins = json.load(open(path, encoding="utf-8"))
    users = logins.setdefault("users", {})

    if args.list or not (args.pairs or args.unlink):
        for name, aid in players.items():
            u = users.get(name, {})
            print(f"{name:20} {aid:>8}  SteamId={u.get('SteamId', '-'):18} "
                  f"{'password' if 'Hash' in u else ''}")
        return

    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", 8081)) == 0:
            sys.exit("The game server is running: stop it first (stop_servers.bat), "
                     "or use the web tool /admin -> Link Steam.")
    if len(args.pairs) % 2:
        sys.exit("give NAME STEAMID pairs")
    for name in args.unlink:
        print(name, "unlinked" if users.get(name, {}).pop("SteamId", None) else "had no SteamId")
    for name, steam_id in zip(args.pairs[::2], args.pairs[1::2]):
        if name not in players:
            sys.exit(f"{name}: no such account (see --list)")
        if not STEAM_RE.fullmatch(steam_id):
            sys.exit(f"{steam_id}: not a SteamID64 (17 digits, starts with 7656119)")
        other = next((n for n, u in users.items() if u.get("SteamId") == steam_id and n != name), None)
        if other:
            sys.exit(f"{steam_id} is already linked to {other}: --unlink {other} first")
        users.setdefault(name, {})["SteamId"] = steam_id
        # end running sessions of this account (fresh login with Steam)
        logins["sessions"] = {t: n for t, n in logins.get("sessions", {}).items() if n != name}
        print(f"{name} -> {steam_id}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(logins, f, indent=1)
    os.replace(tmp, path)
    print("saved", path)


if __name__ == "__main__":
    main()
