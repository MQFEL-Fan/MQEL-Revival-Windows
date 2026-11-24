"""List or extract the files inside a client settings archive
(GameData/Data/GameplaySettings/settings.bin or settings2.bin).

    python tools/settings_dump.py list  [archive] [filter]
    python tools/settings_dump.py dump  <path inside archive> [archive]
    python tools/settings_dump.py extract <out dir> [archive]

Archive format: server/settings_archive.py.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import settings_archive  # noqa: E402

DEFAULT = os.path.join(ROOT, "client", "GameData", "Data", "GameplaySettings", "settings.bin")


def entries(content):
    """[(path, json bytes)] of the archive content (folder tree)."""
    out = []
    pos = 0

    def cstr():
        nonlocal pos
        end = content.index(b"\0", pos)
        s = content[pos:end]
        pos = end + 1
        return s

    def folder(prefix):
        nonlocal pos
        name = cstr().decode("latin1")
        path = prefix + name + "/" if name else prefix
        n = struct.unpack_from("<I", content, pos)[0]
        pos += 4
        for _ in range(n):
            fname = cstr().decode("latin1")
            data = cstr()
            out.append((path + fname, data))
        n = struct.unpack_from("<I", content, pos)[0]
        pos += 4
        for _ in range(n):
            folder(path)

    folder("")
    return out


def load(archive=DEFAULT):
    with open(archive, "rb") as f:
        content = settings_archive.read(f.read())[0]
    return entries(content[:-4])


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        archive = sys.argv[2] if len(sys.argv) > 2 else DEFAULT
        flt = sys.argv[3].lower() if len(sys.argv) > 3 else ""
        for path, data in load(archive):
            if flt in path.lower():
                print(len(data), path)
    elif cmd == "dump":
        archive = sys.argv[3] if len(sys.argv) > 3 else DEFAULT
        for path, data in load(archive):
            if path.lower() == sys.argv[2].lower():
                sys.stdout.write(data.decode("utf-8", "replace"))
                return
        sys.exit("not found")
    elif cmd == "extract":
        out = sys.argv[2]
        archive = sys.argv[3] if len(sys.argv) > 3 else DEFAULT
        for path, data in load(archive):
            p = os.path.join(out, *path.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)


if __name__ == "__main__":
    main()
