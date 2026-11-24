"""Write the level-60 gameplay settings (server/level60.py) into the loose
JSON copies the server reads (client/GameData/Data/GameplaySettings).

    python tools/apply_level60.py            apply (from the untouched files
                                             inside settings.bin)
    python tools/apply_level60.py --restore  write the original files back
    python tools/apply_level60.py --check    only list what would change

settings.bin itself is never changed: the patcher builds the players'
settings.bin from it (DataBin version part L<CRC>). Restart the server
afterwards (it caches the settings).
"""
import glob
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import level60  # noqa: E402
import settings_archive  # noqa: E402

SETTINGS = os.path.join(ROOT, "client", "GameData", "Data", "GameplaySettings")


def loose_path(archive_path):
    parts = archive_path.split("/")
    return os.path.join(SETTINGS, *parts[1:-1], parts[-1].split("\\")[-1])


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--apply"
    with open(os.path.join(SETTINGS, "settings.bin"), "rb") as f:
        content = settings_archive.read(f.read())[0]
    files = settings_archive.files(content)
    if mode == "--restore":
        changed = 0
        for path, data in files.items():
            lp = loose_path(path)
            if not os.path.exists(lp) or open(lp, "rb").read() != data:
                with open(lp, "wb") as f:
                    f.write(data)
                changed += 1
        # new spec folders of the level-60 skill ranks (ids from 700000)
        removed = 0
        for d in glob.glob(os.path.join(SETTINGS, "*", "7[0-9][0-9][0-9][0-9][0-9] - *")):
            if os.path.isdir(d) and int(os.path.basename(d)[:6]) >= level60.SpecForge.FIRST_ID:
                shutil.rmtree(d)
                removed += 1
        print("restored %d files, removed %d new spec folders" % (changed, removed))
        return
    # the region castle names read the original English texts
    level60.all_names.cache_clear()
    edited, added = level60.edited_files(files, SETTINGS)
    by_kind = {}
    for path in edited:
        by_kind.setdefault(path.split("/")[1], 0)
        by_kind[path.split("/")[1]] += 1
    print("files changed:", dict(sorted(by_kind.items())))
    print("new spec files:", len(added))
    if mode == "--check":
        return
    for path, data in list(edited.items()) + list(added.items()):
        lp = loose_path(path)
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        with open(lp, "wb") as f:
            f.write(data)
    print("written; restart the server")


if __name__ == "__main__":
    main()
