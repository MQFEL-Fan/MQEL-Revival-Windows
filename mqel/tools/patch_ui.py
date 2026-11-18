"""Client-UI-Patches lokal anwenden (Regeln: server/ui_patches.py).

Spieler bekommen die Patches über den Launcher (server/patcher.py, Paket
GameUI); dieses Werkzeug patcht einen Client-Baum direkt. Vor dem ersten
Schreiben wird je Datei <Name>.orig angelegt, gepatcht wird immer davon.

Aufruf: python tools/patch_ui.py [GameData-Verzeichnis]
"""
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))
import ui_patches  # noqa: E402


def main():
    game_data = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "client/GameData")
    try:
        files = ui_patches.patched(str(game_data))
    except ValueError as e:
        sys.exit(str(e))
    for rel, data in files.items():
        path = game_data / rel
        orig = path.with_name(path.name + ".orig")
        if not orig.exists():
            shutil.copy2(path, orig)
        path.write_bytes(data)
        print(f"gepatcht: {path}")


if __name__ == "__main__":
    main()
