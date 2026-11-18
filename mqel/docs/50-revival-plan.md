# Revival-Bauplan

## A. Statisch bereits geklärt ✅

- Archiv-Inventar; kein lauffähiger Server in `main.*.7z`, aber **komplette
  Serverassemblies + API-Doku**.
- Prozess-Modell (Launcher → Master (gepackt) ↔ Worker (Pipe) → HTTP).
- **Protokoll**: `GET/POST {GameServerUrl}/{Service}.hqs/{Methode}[?params]`,
  JSON-Body `{"param":…}`, Header `t/i/h/rnd/n/g`, Fehler als JSON mit
  HTTP-Status, `BodyStyle=bare` (kein Wrapper).
- **Auth**: ConnectionToken via Header `t`; Client-HMAC = Murmur3 + Secret
  (Algorithmus exakt bekannt; zuerst deaktiviert betreiben).
- **API-Map**: 25+5 Services, ~220 Endpunkte mit Parameternamen
  (`docs/analysis/*.txt`, Tool `tools/apimap.py`).

## B. Nächste Analyse-Schritte

1. **JSON-Details** (eigene Doku / dynamisch verifizieren):
   Property-Namen (C#-Namen 1:1?), Enum-/DateTime-/ObjectId-/Decimal-Format,
   `ServiceException`-JSON-Felder, GET-Konvertierungen, `$type`-Felder
   (`TypeNameHandling`).
2. **`[Authenticated]`-Kartierung** auf `HyperQuest.GameServer.dll`
   (welche Methoden brauchen Token?) + `EnableClientHmac`-Default.
3. **Login-Implements** (`SleepyGiantService.Login/ValidateToken`,
   `ConnectionManager`): exakter Session-Aufbau, `LoginResult`-Inhalt.
4. **Start-Flow mitschneiden** (dynamisch, s. C): reale Request-Reihenfolge
   nach Spielstart, echte JSON-Beispiele.
5. **GameplaySettings-Inventar**: welche `*.json` der Server lädt
   (`RootSettingsPath`, `[JsonPath]`-Klassen), News-/Shop-Pfade.
6. **GameCommand-Modell** (`SendCommands`, `EndAttackParams`,
   Replay-Format) für Angriffsauflösung.

## C. Dynamische Analyse (läuft seit 13.10.2026, Stand)

- Logging-Server: `server/logging_server.py`, heute `server/game_server.py`
  (umbenannt, als er zum eigentlichen Spielserver wurde; alle Requests → Konsole +
  `server/requests.log.jsonl`), Antworten via `server/responses.json`
  (pro Request neu geladen, `$file:`-Includes für große Stubs).
- Erster Capture: `SendCommands` (GameStart-Tracking) →
  `GetAccountInformation` → Client-Crash im Ladebildschirm (leeres `{}`).
- `GetAccountInformation`-Stub: `server/build_account_stub.py` baut die
  Antwort aus `GameplaySettings/AccountTemplates/000003 - FullAccount.json`
  (4 Helden Lvl 30, Wallet, Burg-Blueprint, Objectives…); Form per
  Reflection über Original-Contracts (`server/gen_stub.ps1`,
  Katalog: `docs/analysis/dto-catalog.txt` — 1495 Klassen, 223 Enums).
- AccountTemplates (`GameplaySettings/AccountTemplates/*.json`) sind die
  **serverseitigen Seed-Daten** für `AdminService.ResetAccount` /
  `CreateFullyFunctionalAccount(…, templateId, …)` (TemplateId =
  Dateiname-Präfix, z. B. `000001` = DefaultAccount mit
  `ShouldResetDisplayName=true` → `ChooseDisplayName`-Flow).
- Nächster Client-Lauf mit gefülltem Account-Stub ausstehend.
- Stand 2. Lauf: Client bleibt nach `GetAccountInformation` stehen (keine
  weiteren Server-Requests), zeigt `NETWORK ERROR …`, beim Beenden
  `OPAL ASSERT - XmppInfo cannot be null … ChatController::LeaveRoom:438`.
  Client-Strings belegen eigene XMPP-Implementierung (`XmppClient_Z.cpp`,
  `AccountServerController::GetXmppInfo`, `Invalid XmppInfo in
  AccountInformation`, `m_currentAccountInfo->ClientSettings->XmppInfo`).
  Hypothese: `XmppInfo` wird direkt nach dem Account validiert und der
  Fehlerdialog kommt von dort (nicht vom HTTP-Traffic).
- Gegenmaßnahme: Stub liefert jetzt plausibles `XmppInfo` (`Enabled=true`,
  `Server=127.0.0.1`, `Port=5222`, …); `logging_server.py --tcp-ports 5222`
  weist per Honeypot nach, ob der Client XMPP anwählt. Falls ja: Fake-XMPP
  (SASL PLAIN + Bind + Presence) als nächster Baustein.
- Lauf 3: `OPAL ASSERT Functional server error 0x80030003` in
  `AccountServerController::OnAccountInformationTaskError:449` (Task
  `GetAccountInformationTask`), danach ignoriert: `Invalid
  AccountInformation … GetAccountForgedItem:502` (Folgefehler ohne
  geladenen Account), dann Game-UI-`NETWORK ERROR`, beim Beenden wieder
  `LeaveRoom:438`. Einzige Stub-Änderung war `XmppInfo` → Beleg, dass der
  Account-Task den XMPP-Connect enthält und ohne Chat-Server scheitert.
- Gebaut: `server/xmpp_server.py` (Fake-XMPP: Stream/PLAIN/Bind/Session,
  leeres Roster, MUC-Selbst-Join, Keepalive; alles → `server/xmpp.log`;
  Smoke-Test mit komplettem Handshake bestanden). Client-Erwartungen aus
  Binary-Strings bestätigt (`Did not receive stream features after SASL
  authentication.`, `Bind successful.`, `STARTTLS not supported.` →
  Plaintext ohne TLS-Angebot ist vorgesehen).
  Hinweis: `xmpp_server.py` beendet sich sauber mit Strg+C (Timeout-Loop +
  Signal-Handler, Socket wird geschlossen); falls ein Terminal hängt,
  notfalls per Task-Manager/`Stop-Process` den `python.exe` mit
  `xmpp_server` in der Kommandozeile beenden.
- Nebenbei: `Inventory.ForgedItem` ist non-null (`ForgeMode=None`), sonst
  assertet `GetAccountForgedItem:502`.
- Lauf 4 (Stub mit `Enabled=true`, alles 127.0.0.1): wieder `0x80030003`,
  **kein** XMPP-Kontakt, keine weiteren HTTP-Requests. Client-Logs
  (`Bin/MQLog.txt`, `Bin/NetworkLog.Txt`) belegen: HTTP-Response kommt
  vollständig an (`ARGO: Request 1 completed`), der Assert fällt ~50 ms
  danach — also **lokales** Scheitern in der Account-Verarbeitung, kein
  Netzwerk-Timeout. Shutdown-Sequenz sauber geloggt
  (`ClientIdleCommand` + `GameStateTracking` + `LogoutCommand`, i=2).
- Nächste Hypothese: Client verbindet auf `Domain`/`ConferenceServer`
  statt `Server` (DNS-Fail ohne TCP) → Stub nutzt jetzt überall
  `127.0.0.1` (JIDs `test@127.0.0.1/…`, Fake-XMPP spiegelt jede Domain).
- Unabhängig bestätigt: Lobby-UI lädt von `http://localhost/gamedata/…`
  (`WebviewManager::Initialize() - lobbyPageUrl`, s. MQLog) → eigener
  `server/static_server.py` (`/gamedata/` → `GameData/Data/`,
  `/AG_BA073_01.gamewebsite/` → `GameData/`, 404-Logging; Port 80 =
  Admin-Terminal nötig). Erklärt den Game-UI-`NETWORK ERROR` aus Lauf 2.
  *Später widerlegt (Okt. 2026):* der Client bedient `/gamedata/` selbst
  (CEF-Handler → `../Data`), das Spiel läuft ohne den Static-Server; er
  wurde entfernt.
- Experiment: `XmppInfo.Enabled` zurück auf `false` (einzige Variable),
  Rest (Lobby mit :80-Server) unverändert — Ziel: Lobby erreichen, Chat
  später (s. Kommentar in `build_account_stub.py`).
- Lauf 5 (Screenshot): `0x80030003` trotz `Enabled=false` → `Enabled` war
  nie die Variable. Verbleibendes Diff zu Lauf 2 (Task ok): gefüllte
  XmppInfo-Felder + `ForgedItem` null→Objekt. Diagnose-Varianten
  `server/stubs/ai-A.json` (nur Xmpp leer) / `ai-B.json` (exakter
  Lauf-2-Zustand), umschaltbar per `responses.json` bei laufendem Server
  + Assert-Dialog-Button „Wiederholen" (`server/make_variants.py`).
  Ergebnis: Fehler in BEIDEN Fällen → weder Xmpp-Felder noch ForgedItem.
- Neue Hypothese: Burg-Integrität (`AccountPrivilege.ByPassCastleIntegrity-
  Check` existiert; unser Draft hatte 3 LEERE Räume). `010030 -
  FullAccount_30_FullUpdate.json` enthält die einzige VOLLSTÄNDIGE Burg
  (Räume mit Buildings/Creatures) → `build_account_stub.py` nutzt sie
  jetzt für den Draft (4 Räume, 9 Buildings, 1 Kreatur; DTO-Formen
  `CastleBuilding/CastleCreature/Orientation` aus dto-catalog). Basis
  übriges = 010030 (Priv 232), Objectives weiter aus 000003.
- Ergebnis: GLEICHER Fehler, „Wiederholen" crasht den Client (Retry-Route
  tot). Strategie-Wechsel: **Struktur vs. Inhalt** — `server/stubs/ai-S.json`
  (Reflection-Skelett: alle 37 Keys, leere Defaults, 2,7 KB) als neues
  Experiment; additiver Aufbau bei Erfolg. Gleichzeitig Transport
  spec-treu: `logging_server.py` spricht HTTP/1.1 + Keep-Alive und sendet
  `sl`-Header (verifiziert). **Achtung: Server-Neustart nötig**
  (Code-Änderung, kein reines responses.json-Reload).
- Ergebnis Skelett: GLEICHER Fehler → Inhalt scheidet aus. RE-Befund
  (statisch, `MightyQuest_release.exe` ist 32-Bit!): Task-Invoker
  (`0x115eca0` ff.) mappen Sub-Call-Fehlschlag → `0x80030003`
  (`0x80030002` = Null-Arg); `OnAccountInformationTaskError` schluckt nur
  `0x80000001` (Cancel). Client-JSON-Parser ist strikt, handgeschrieben
  (`Expected [true] or [false]`, `Not a number`, `Not a time span`,
  `Expected character/string`, `Max json string exceeded`,
  `Cannot get object serializer [%s]`); Datetime = `"YYYY-MM-DDTHH:MM:SSZ"`
  (Z Pflicht), aber `""` → MinValue ist OK. Fehler-Logger ist in diesem
  Pfad NULL (still). `sl`-Header rankt: unklar.
- Neue Hypothese: Nach dem Account-Parse folgt ein ZWEITER Request an ein
  ANDERES Ziel (nicht GameServer/XMPP/:80 — dort kommt nichts an), der
  sofort fehlschlägt. Test: `Get-NetTCPConnection` pro
  MightyQuest-Prozess während des Hangs (SYN-Ziele!).
- Ergebnis Netstat: KEIN Outbound außer 2× Keep-Alive nach :8081; dafür
  lauscht das Spiel auf 1337/9920/12987/50000 (CEF-Bridge/Debug, irrelevant).
  Fehler ist 100 % lokal. Offene Unschärfe: Ob der ai-S-Lauf schon mit
  neuem Server-Code (HTTP/1.1+`sl`, Neustart-pflichtig) lief — sauberer
  Neustart + ai-S steht aus.
- Neustart bestätigt, ai-S scheitert trotzdem. Neuer Befund: Skelett
  enthält `Inventory.ForgedItem.Item = null` (`InventoryItem` ist
  abstrakt!), 2× ObjectId-`"000…"`, 4× `""`-Dates. Variante
  `server/stubs/ai-C.json` (`server/make_aiC.py`) löscht alle drei Formen;
  bei Erfolg additiv aufbauen, bei Fehlschlag Bisect der Skalare.
- ai-C scheitert auch → Bisect per Key-Removal (`server/make_aiD.py`):
  `ai-D1.json` (28 Keys: ohne alle 9 Objekt-Member), Fallback
  `ai-D2.json` (13 Skalare).
- D1 + D2 scheitern BEIDE → auch 13 Skalare parsen nicht. Neuer Verdacht:
  Response-`Content-Type`: Unser Server sendete `application/json`, das
  einzige JSON-CT-Literal im Client ist aber
  `application/json; charset=utf-8` (exakt ASP.NET-Format, auch in seinen
  Requests). `logging_server.py` sendet jetzt exakt dieses CT (Server-
  Neustart nötig). Test direkt mit Voll-Stub: falls CT die Ursache war,
  sind wir in einem Lauf durch.
- CT-Theorie weiter offen. NEUE LEITTHEORIE ($type): Client-Parser löst
  Objekt-Deserialisierer per `$type` auf
  (`Cannot get object serializer [%s]`; keine Key-Literale im Binary!);
  Client sendet selbst `$type` pro DTO (Capture). Unsere Antworten hatten
  nie `$type` — `{}` kommt durch (nichts aufzulösen), jedes nicht-leere
  Objekt scheitert. `server/add_dollar_type.py` setzt `$type` (Newtonsoft-
  Format, an erster Stelle) auf alle 521 DTO-Objekte des Voll-Stubs
  (Typnamen aus dto-catalog verifiziert; polymorphe `Item`s inkl.).
  `logging_server.py` loggt jetzt zusätzlich Response-Summary +
  Start-Marker (verifiziert) — aus `requests.log.jsonl` ist künftig
  ablesbar, WAS der Client bekam (Neustart-Kontrolle!).
- DURCHBRUCH: Mit `$type`-Voll-Stub (+ neuem Server-Code) läuft der
  Account-Task durch — statt `0x80030003` jetzt
  `Invalid AccountInformation … GetBuildInfo:279` (`m_currentAccountInfo`
  NULL). D. h. Response-Parse OK; Ablage/Folgeaufruf prüfen. Nächster
  Schritt: Ignore-Kette (alle Folge-Dialoge der Reihe nach) + neue
  Requests im Game-Log. Beiträge CT vs. $type retrospektiv nicht sauber
  trennbar — beides bleibt drin (beides spec-treu).
- Analyse Ablegepfad (statisch): Success-Handler lagert via
  `AcquireResult` (`[Task+0x9B8]` → Slot, Move!) — Slot NULL heißt
  TASK-RESULT NULL (Parse „erfolgreich", aber NULL-Objekt). Hypothese:
  Top-Level-`$type` verwirrt den Lookup (still NULL); statischer Dispatch
  ohne Top-`$type` + Nested-`$type` für polymorphe `.Item` könnte die
  Kombi sein. Variante `ai-E.json` (`server/make_aiE.py`): Voll-Stub
  minus Top-`$type`. Drei Ausgänge: 0x80030003 zurück / Assert bleibt /
  Durchbruch.
- Ergebnis ai-E: 0x80030003 zurück. ABER: Transport-Fix vs. $type nie
  sauber entkoppelt (ai-E lief evtl. mit altem Code)! Nächster Lauf:
  ai-E + VERIFIZIERT neuer Code (curl-Check `Content-Type:
  application/json; charset=utf-8`) → trennt Transport vs. $type sauber.
- Nebenbefund: Log-Zeilen konnten sich bei parallelen Requests
  zerreißen (Threading ohne Lock) → `LOG_LOCK` in `logging_server.py`.
- Ops: `server/stop.ps1` beendet alle drei Server anhand der Kommandozeile
  (falls Strg+C im Terminal nicht ankommt; für Port-80-Prozess ggf. als
  Admin ausführen).

- `MightyQuest.exe` direkt starten (Launcher umgehen):
  `MightyQuest.exe -server_url http://127.0.0.1:PORT -token test -email
  test@test -environmentName local -httpCompression 0`
  (ggf. Steam-Args weglassen; `-compipe`-Kindprozesse beobachten).
- Eigenen Logging-HTTP-Server auf PORT (alle Pfade + Header + Body dump),
  minimale JSON-Antworten zurückgeben, **iterativ** erweitern:
  `HealthCheck` → `ValidateToken/Login` → `GetAccountInformation` → …
- WinHTTP-Verkehr nach localhost ist ohne TLS abgreifbar; UBX-Packung ist
  zur Laufzeit entpackt (ggf. Memory-Dump für Strings/URLs).
- Erwartung: Das Spiel zeigt nach jedem fehlenden Call einen Fehler mit
  Service-Namen — das ist die beste Spezifikation.

## D. Server-Neubau (Vorschlag: C# / ASP.NET Core oder Python)

1. **Skelett**: Routing `{service}.hqs/{methode}`, GET/POST-Dispatch,
   JSON (System.Text.Json / Newtonsoft), Header `t/i/h/rnd/n/g` lesen,
   Fehler-Envelope, Logging aller Calls (entscheidend für Iteration).
2. **Session/Auth**: Token-Tabelle, `ValidateToken`→Token,
   `[Authenticated]`-äquivalent, HMAC-Verify (Murmur3) optional.
3. **Domain-Stubs**: pro Service minimale sinnvolle Antworten
   (Account-Info mit Start-Burg/Held aus `GameplaySettings`, leere Listen,
   feste Shop-SKUs); Angriffs-Lifecycle (`StartAttack`→`EndAttack`) mit
   einfacher Loot-Berechnung; `SendCommands` als No-Op mit Echo.
4. **Persistenz**: SQLite/Postgres; Modell aus `Entities.xml` + Bedarf.
5. **GameplaySettings laden**: `Data/GameplaySettings/**/*.json` aus
   `GameData.7z` als Regelbasis (SpecContainerIds, Kosten, Loot-Tabellen).
6. Später: Freundschaft/Challenges/Leaderboards, Admin-Import
   (`ImportCastle`), E2E-Tests mit Skript-Client gegen alle 220 Endpunkte.

## E. Offene Risiken

- **Gepackter Master**: Falls er Integritäts-/Anti-Debug-Checks (UBX) oder
  hartcodierte URLs/Zertifikate enthält, braucht es Patches oder
  Hosts-/Proxy-Tricks. Bisher keine Hinweise auf Zertifikats-Pinning
  (plain HTTP via `-server_url` ist vorgesehen).
- **CEF-UI** (`mightyquest-ui.exe`): Lobby-/Shop-Seiten könnten eigene
  Web-Calls machen — mitschneiden und nachbauen.
- **Chat (ejabberd/XMPP)**: `ChatSettings`/`XmppInfo`-DTOs existieren;
  vorerst `ChatEnabled=false` liefern.
- **Version**: Client `0.36.1.34.0` vs. Toolbox `main.348.1` — kleine
  API-Drift möglich; dynamischer Mitschnitt entscheidet.
- URSACHE GEFUNDEN (`GetBuildInfo:279`): Client erwartet JSON-Antworten als
  `WrappedResponse` (`{"$type":"Util.Common.Service.WrappedResponse,
  Util.Common.Service","Result":…}`), s. `30-protokoll.md`. MQLog des
  Laufs mit `$type`-Voll-Stub zeigte `Account information loaded` direkt
  vor dem Assert. Schema-Drift Client (Update3) ↔ Toolbox: Client kennt
  u. a. `ShopSkus`, `Challenges`, `AttackRegions`, `Hero.Attributes`,
  `InventoryItem.Type/SellPrice`, `ItemEffect.Variation/AbsoluteValue`
  nicht (nur JSON-WARNINGs, unkritisch).
- Folgefehler „stilles Beenden nach 20–30 s": Wrapper-`$type` →
  OOB-Read in der Client-Typ-Tabelle (procdump-Minidump, s. `30-protokoll.md`).
  Fix: Wrapper ohne `$type` (`{"Result":…}`), leere Antworten `{}`.
- Items in Client-Form (Update3): Werte 1:1 aus den AccountTemplates der
  Client-Daten (ArchetypeId, PrimaryStatsModifiers, Effects{Id,Level,Type},
  PowerUp{Id,Level}); Feldlisten aus den Client-Lesern. Ergebnis: Shop,
  Kauf (`BuyHeroItemCommand`) und Anlegen (`HeroEquipmentEquipCommand`)
  laufen clientseitig; Server quittiert `SendCommands` mit `{}`, speichert
  aber noch nichts (nach Neustart ist der Kauf weg).
- Persistenz: `server/account_state.py` hält den Account (Seed = Stub,
  Zustand `server/state/account.json`, löschen = Reset). Behandelt:
  `BuyHeroItemCommand` (SKU aus `ShopSkuBaseSettings.json`),
  `HeroEquipmentEquipCommand`/`UnequipCommand`. Client-HeroItemSlot
  (Update3, verifiziert): Head1 Shoulders2 Body3 Back4 Neck5 Finger1=6
  Hands7 MainHand8 OffHand9 Costume10 Pet11. Unbekannte Commands →
  `[state] nicht behandelt` im Server-Log.
