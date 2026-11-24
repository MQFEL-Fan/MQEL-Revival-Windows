# tools/ — wiederverwendbare Analyse-Werkzeuge

Alle Skripte brauchen Python 3 + `pip install dotnetfile pefile py7zr`
(lesen nur, schreiben nichts in die Archive).

| Skript | Zweck | Beispiel |
|---|---|---|
| `ildump.py` | IL-Disassembler für .NET-Assemblies mit Token-Auflösung (Methoden-, Feld-, String-Tokens) | `python tools/ildump.py <assembly.dll> <Typfilter> [Methodenfilter]` |
| `dnbrowse.py` | Typ-/Methoden-Liste + `ldstr`-Strings pro Methode | `python tools/dnbrowse.py <assembly.dll> [Filter] [types\|ldstr]` |
| `cadecode.py` | Custom-Attribute-Dump (Parent, Attributtyp, Blob-Strings) | `python tools/cadecode.py <assembly.dll> [Filter]` |
| `apimap.py` | **HTTP-API-Map**: `[Service]`-Interfaces → Methoden mit Parameternamen, HTTP-Verb (`JsonGet/JsonPost/…`), `Private`-Flag | `python tools/apimap.py HyperQuest.GameServer.Contracts.dll > docs/analysis/api-gameserver.txt` |
| `callfinder.py` | Caller-Suche: welche Methoden rufen `Typ.Methode` auf (MemberRef + same-assembly MethodDef) | `python tools/callfinder.py HyperQuest.GameServer.dll CallContextManager SetItem` |

Hinweise:

- `dotnetfile` nummeriert `CustomAttribute.Parent` anders als ECMA-335:
  **Tag 3 = TypeDef, Tag 0 = MethodDef** (empirisch verifiziert);
  `CustomAttribute.Type` ist ein `CustomAttributeType`-Coded-Index
  (Tag = `& 0x7`, Tag 3 = MemberRef, Row = `>> 3`).
- Extrahierte Fakten gehören als Doku nach `docs/` (nicht nur als
  Tool-Output): `docs/analysis/*.txt` sind Momentaufnahmen, die
  `docs/*.md` die kuratierte Spezifikation.
- `patch_ui.py [GameData]` – alle Client-UI-Patches lokal anwenden (Regeln in `server/ui_patches.py`; Spieler bekommen sie über den Launcher, Paket GameUI; Backups `*.orig`, gepatcht wird immer vom Original): Wettbewerbs-Popup "Castle's level" aus CastleLevel, Spalte "Reward" der Wettbewerbs-Rangliste, Schmiede-Hinweis beim Einlegen der angelegten Waffe, Freundes-News (Klassenname je Sprache übersetzt, englische Grammatik), Tausendertrenner bei der Bling-Zähl-Animation im Hauptmenü.
- `client_members.py <exe> Klasse…` – listet die JSON-Member, die der Client-Leser einer Klasse erwartet (Update3-Binary); mit `-t` zusätzlich den JSON-Typ je Feld (int/float/bool/string/date/object/array/int-array, sonst typ-eigener Leser = meist Enum).

## Level-60 update / settings archive

- `apply_level60.py`: writes the level-60 gameplay settings (`server/level60.py`) into the loose JSONs the server reads (`--check`, `--restore`); see `docs/90-level60.md`.
- `settings_dump.py`: lists, prints or extracts the files inside `settings.bin` / `settings2.bin`.
- `jsonshape.py`: prints the structure (keys, list lengths) of a JSON file.
