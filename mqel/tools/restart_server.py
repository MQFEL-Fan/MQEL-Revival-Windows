"""Restart the game server for an update, with the update countdown first.

1. Schedules the countdown in every game (AdminService ScheduleUpdate, the
   admin tool's "Schedule update"): default 5 minutes, so players can finish
   and sign off safely. At 0 their game closes itself.
2. Waits for 0 (plus a few seconds for the games to close).
3. Restarts only the game server with the same command line it runs with
   now (the XMPP chat server keeps running). Not running: start_servers.bat.

Usage (from the project folder):
    python tools\\restart_server.py                    # 5 min countdown
    python tools\\restart_server.py --minutes 10 --message "Patch v1.4.4.1"
    python tools\\restart_server.py --now               # no countdown
Ctrl+C while waiting cancels the countdown and leaves the server running.
The HMAC key comes from server/state/new/admin_hmac.json (never printed).
"""
import argparse
import email.utils
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import admin  # noqa: E402

BASE = "http://127.0.0.1:8081"
GRACE_S = 10  # after 0: the games close themselves (WASD helper /quit)


def call(method, body):
    keys = admin.load_keys(os.path.join(ROOT, "server", "state", "new", "admin_hmac.json"))
    key_id, secret = next(iter(keys.items()))
    path = "/AdminService.hqs/" + method
    date = email.utils.formatdate(usegmt=True)
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "Date": date, "content-accesskeyid": key_id,
        "content-hmac": admin.signature(path, "POST", date, key_id, secret)})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


def server_processes():
    """[(pid, parent pid, name, command line)] of game_server.py and its cmd wrapper."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'game_server\\.py' "
          "-and $_.Name -notmatch 'powershell' } | Select-Object ProcessId,ParentProcessId,Name,CommandLine "
          "| ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        return []
    rows = json.loads(out)
    rows = rows if isinstance(rows, list) else [rows]
    return [(r["ProcessId"], r["ParentProcessId"], r["Name"], r["CommandLine"] or "") for r in rows]


def wrapper_command(procs):
    """Command line to start the server again, always with server_config.bat
    loaded first (Steam API key, public host, Discord webhooks).

    2026-11-23 fix: a server started by start_servers.bat runs as
    `cmd /c "python ... > game_server.log"`; its settings come from the
    batch file's environment, not from that command line. Relaunching the
    bare command started the server without them (Steam login disabled, no
    public host for the UI mods, no Discord). Now the python part (with its
    log redirection) is wrapped in `call server_config.bat && ...`."""
    inner = None
    for _pid, _ppid, name, cmd in procs:
        if name.lower() == "cmd.exe":
            m = re.search(r'/c\s+"(.*)"\s*$', cmd, re.S)
            inner = m.group(1) if m else None
            break
    if inner is None:
        for _pid, _ppid, name, cmd in procs:
            if name.lower().startswith("python"):
                inner = cmd.strip() + " > game_server.log 2>&1"
                break
    if inner is None:
        return None
    inner = re.sub(r"^\s*call\s+server_config\.bat\s*&&\s*", "", inner, flags=re.I)
    # absolute paths: a relative "call server_config.bat" wasn't found by the
    # detached cmd.exe (2026-11-24, the server didn't come back up)
    config = os.path.join(ROOT, "server_config.bat")
    if os.path.exists(config):
        return 'cmd.exe /s /c "cd /d "%s" && call "%s" && %s"' % (ROOT, config, inner)
    return 'cmd.exe /s /c "cd /d "%s" && %s"' % (ROOT, inner)


def start_detached(cmdline):
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
             | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000))
    try:
        subprocess.Popen(cmdline, cwd=ROOT, creationflags=flags, close_fds=True)
    except OSError:  # breakaway not allowed in this job: without it
        subprocess.Popen(cmdline, cwd=ROOT, close_fds=True, creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS))


def wait_listening(seconds=30):
    for _ in range(seconds * 2):
        try:
            urllib.request.urlopen(BASE + "/notice", timeout=2).read()
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--minutes", type=float, default=5)
    ap.add_argument("--message", default="Server update")
    ap.add_argument("--now", action="store_true", help="restart without a countdown")
    args = ap.parse_args()

    procs = server_processes()
    if procs and not args.now:
        notice = call("ScheduleUpdate", {"minutes": args.minutes, "message": args.message})["Notice"]
        at = notice["At"]
        print("Countdown in every game: %s, restart at %s" % (
            args.message, time.strftime("%H:%M:%S", time.localtime(at))), flush=True)
        try:
            while time.time() < at + GRACE_S:
                left = int(at - time.time())
                if left > 0 and left % 60 == 0:
                    print("  %d min left" % (left // 60), flush=True)
                time.sleep(1)
        except KeyboardInterrupt:
            call("CancelUpdate", {})
            print("Cancelled: countdown removed, server keeps running.")
            return 1

    procs = server_processes()
    cmdline = wrapper_command(procs)
    for pid, _ppid, _name, _cmd in procs:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    if procs:
        print("Game server stopped.", flush=True)
        time.sleep(2)
    # the countdown is over: don't send it again after the restart
    path = os.path.join(ROOT, "server", "state", "new", "server_notice.json")
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}")

    if cmdline:
        start_detached(cmdline)
    else:
        start_detached('cmd.exe /c "%s" /nopause' % os.path.join(ROOT, "start_servers.bat"))
    if wait_listening():
        print("Game server is running again on %s." % BASE)
        return 0
    print("The game server did not come up: see server\\game_server.out / game_server.log.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
