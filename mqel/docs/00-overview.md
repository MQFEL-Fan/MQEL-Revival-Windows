# MQEL Revival — Übersicht

**Ziel:** Einen kompatiblen Gameserver für *The Mighty Quest for Epic Loot*
(Ubisoft, 2014–2015, Opal-Engine, PC) bauen, sodass das Spiel mit den
vorliegenden Client-Dateien wieder spielbar wird. Eine 1:1-Wiederherstellung
ist unmöglich (keine serverseitigen Daten/DBs bekannt); angestrebt wird ein
sauberer Nachbau des **Client↔Server-Protokolls** mit neu implementierter
Spiellogik.

**Kurzbefund (Stand 13.10.2026):**

- `main.348.1_232184_GameplayToolbox.7z` enthält **keinen lauffähigen Server**,
  aber etwas fast genauso Wertvolles: die kompletten **.NET-Serverassemblies**
  (`HyperQuest.GameServer.dll`, `*.Contracts.dll`, `Util.*.dll`) inkl.
  XML-Dokumentation und PDBs. Daraus ist das **gesamte Server-API**
  (Services, Methoden, Parameter, DTOs) rekonstruierbar.
- Das Client↔Server-Protokoll ist **HTTP + JSON**, selbst gebaut
  („Argo“-Service-Framework, kein WCF/REST-Standard). URL-Schema,
  Header, Auth- und Anti-Cheat-HMAC sind statisch rekonstruiert
  (Details: `30-protokoll.md`, `40-auth.md`).
- Der Spiel-Client besteht aus zwei Prozessen: `MightyQuest.exe` (gepackt,
  enthält Netzwerk-/HTTP-Code) und `MightyQuestWorker.exe` (ungepackt,
  Simulation/Replay, spricht via Named Pipe mit dem Master).
- Die Server-Settings (`GameplaySettings/*.json`, ~8700 Dateien) liegen in
  `0.36.1.34.0_104956_GameData.7z` und können vom Nachbau **direkt von Platte**
  gelesen werden — genau wie vom Original (`GameplaySettingsPath`).

**Doku-Struktur:**

| Datei | Inhalt |
|---|---|
| `10-quellen.md` | Inventar der 5 Archive, was wo drin ist |
| `20-architektur.md` | Prozesse, Launcher-Flow, Server-Komponenten, Abhängigkeiten |
| `30-protokoll.md` | HTTP+JSON-Protokoll (URL-Schema, Verben, Header, Envelopes, Versionierung) |
| `31-services.md` | Service-Katalog (welche Services das Spiel wirklich braucht) |
| `40-auth.md` | Login-Flow, ConnectionToken, `[Authenticated]`, Client-HMAC (Murmur3) |
| `50-revival-plan.md` | Bauplan: was zu implementieren ist, in welcher Reihenfolge |
| `analysis/api-gameserver.txt` | Vollständige API-Map (Service → Methoden, Parameter, Verben) |
| `analysis/api-common.txt` | API-Map der Shared-Contracts (Tracking, CrashReport, …) |

**Werkzeuge** liegen in `../tools/` (siehe `../tools/README.md`):
`ildump.py` (IL-Disassembler), `dnbrowse.py` (Typ-/String-Browser),
`cadecode.py` (Custom-Attribute-Dekoder), `apimap.py` (API-Map-Generator),
`callfinder.py` (Caller-Suche).
