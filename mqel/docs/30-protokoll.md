# Protokoll: HTTP + JSON („Argo Services“)

Rekonstruiert aus `Util.Client.dll` (URL-Aufbau, Request-Prozessoren),
`Util.Server.dll` (Routing, Dispatch, HMAC) und
`Util.Common.Service.dll` (Attribute). Verifiziert per IL-Disassemblat
(`tools/ildump.py`).

## URL-Schema

```text
{GameServerUrl}/{ServiceName}/{MethodName}[?param=urlenc(wert)&…]
```

- `GameServerUrl` kommt aus der Launcher-Config bzw. `-server_url`.
- `ServiceName` = `[Service]`-Attribut, z. B. `AccountService.hqs`
  (**inkl. `.hqs`-Suffix**, dem Argo-Service-Definitionsfile).
- `MethodName` = Interface-Methodenname, z. B. `Login`.
- Client-Aufbau (`ServiceClientFactory` → `UrlBuilder.BuildUrlFormat`):
  Basis = `GameServerUrl + "/" + ServiceName`, Methode = `"/" + Name +
  "?p0={0}&p1={1}…"` (Stream-Parameter ausgenommen), Werte via
  `String.Format` + `UrlEncode(ToString(arg))`.
- Server-Routing (`ServiceHttpHandler` + `ServiceRequestProcessor`):
  Komponente `"~/" + ServiceName` (Castle Windsor), darin Map
  `"/" + MethodName` → Methoden-Prozessor. Unbekannte Pfade →
  `NotFoundException` (HTTP 404 als JSON-Fehler, siehe unten).

Beispiel (GET):

```text
GET http://server:port/AccountService.hqs/HealthCheck
GET http://server:port/AttackSelectionService.hqs/GetAttackSelectionList?attackRegionId=3&maxSuggestionCountByLevel=5
```

## Methoden-Typen (Attribute in `Util.Common.Service`)

| Attribut | HTTP | Request | Response |
|---|---|---|---|
| `[JsonGet]` (54× in Game-Contracts) | GET | Query-Params (`Request.Params`: QueryString+Form+Cookies+ServerVars) | `application/json` |
| `[JsonPost]` (160×) | POST | JSON-Body, s. u. | `application/json` |
| `[StreamGet]` (2×: `GetReplay`, `GetAttackAntiCheatJob`) | GET | Query-Params | `application/octet-stream` |
| `[StreamPost]` (1×: `StoreReplay(accountId, replayStream)`) | POST | Query + Binär-Stream (via CallContext) | `application/json` |
| `[HtmlGet]` (1×: `LinkFacebookAccount`) | GET | — | `text/html` (entfällt im Revival) |

- Falsche HTTP-Methode → `NotFoundException`.
- `[Private]` (auf Typ oder Methode; u. a. `AdminService`,
  `SleepyGiantService`, `DashboardService` komplett): nur über
  **Privat-Port + HMAC-Header** (`content-hmac`, `Date`,
  `content-accesskeyid`, Signatur `GenerateHMACSignature(Url, Methode,
  Secret)` in `Util.Common.Service.WebRequestHelper`). Öffentlicher
  Spiel-Traffic braucht das **nicht**.
- `BodyStyle`-Default = **0 = „bare“**: Responses sind das nackte
  Ergebnis-JSON (kein Wrapper). `WrappedResponse<T>` (`{"Result":…}` über
  CallContext-Schlüssel `WRAPPED_RESPONSE`) wird nur bei explizitem
  `BodyStyle=1` genutzt — im GameServer nicht verwendet.

## POST-Body

`{"<paramName>": <wert>, …}` — ein Feld pro Methodenparameter
(`PostHttpBodyContractBuilder`: dynamischer Contract-Typ mit Feldern =
Parameternamen; Deserialisierung via `Util.Common.Json`):

```text
POST http://server:port/AccountService.hqs/Login
Content-Type: application/json

{"email":"…","password":"…","ipAddress":"…","timeZoneOffset":60}
```

Parameter- und Methoden-Namen: `docs/analysis/api-gameserver.txt`
(generiert mit `tools/apimap.py`, inkl. Parameternamen aus der
.NET-`Param`-Tabelle).

## GET-Parameter-Typen

`GetHttpMethodCompiler`: `string` roh, sonst `BuildConvertMethodCallExpression`
(`Parse`-basiert: numerische Typen, `bool`, `Enum`, `DateTime`, `ObjectId`,
`Nullable<>`; fehlend → `default(T)`). Komplexe DTOs per GET gibt es nicht —
alle komplexen Calls sind POST.

## Ambient Header (jedes Request, siehe `40-auth.md`)

| Header | Typ | Bedeutung |
|---|---|---|
| `t` | string | ConnectionToken (Session, s. Auth) |
| `i` | uint32 | Request-Zähler (Anti-Replay, nur mit `h`) |
| `h` | uint32 | Client-HMAC (Murmur3, nur wenn Server `EnableClientHmac`) |
| `rnd` | uint32 | Client-Flags (`& 0xAAAAAAAA` → `ClientHackFlags`, Telemetrie) |
| `n` | int | (Kontext, Verwendung serverseitig prüfen) |
| `g` | string | (Kontext, Verwendung serverseitig prüfen) |

Server liest sie in `UserStorageLoader.LoadUserInformation` aus
`Request.Headers` in den CallContext. Sie sind für den Basisbetrieb
optional (ohne `t` = anonym; ohne `h` = kein HMAC-Check).

## Dynamisch verifiziert (13.10.2026, Client `0.36.1.34.0` gegen Logging-Server)

- Der Client sendet zusätzlich den Header **`sl: 0`** (sonst nur als
  Server-Header bekannt) sowie `Accept: */*`.
- `Content-Type` ist `application/json; charset=utf-8`.
- Der Request-Zähler `i` beginnt bei **0** und steigt strikt (`0, 1, …`);
  `h` wird immer mitgesendet (Server ignoriert beides vorerst).
- POST-Bodys nutzen **Newtonsoft-`$type`-Polymorphie**:
  `{"commands":[{"$type":"HyperQuest.GameServer.Contracts.TrackingCommand,
  HyperQuest.GameServer.Contracts","TrackingTag":{"$type":"…GameStartTracking,
  …","GameClientVersion":"280139","MachineId":"…","CreationDate":"",
  "TrackingTagId":108}}]}` — beachte: Default-`DateTime` wird als **`""`**
  serialisiert, `GameClientVersion` = Game-Paket-ID (`version.Game.txt`).
- Stream-Parameter (`replayStream`) erscheinen wie erwartet **nicht** im
  JSON-Body (`SendCommands` sendet nur `{"commands":[…]}`).
- Erster Boot-Flow: `POST ServerCommandService.hqs/SendCommands`
  (GameStart-Tracking) → `GET AccountInformationService.hqs/GetAccountInformation`.

## Versionierung

- `[Service]` kann `ServiceVersion` tragen; `CheckServiceVersionInterceptor`
  prüft Client-Version (`"v"`). Details/Toleranz noch zu verifizieren —
  der Nachbau sollte jede Version akzeptieren.
- `Content-Length: 0`-POSTs ohne Body sind zulässig (parameterlose Calls).

## Fehler

- HTTP-Status = `ServiceException.HttpStatusCode`,
  `Content-Type: application/json`, Body = `ServiceExceptionSerializer`-JSON
  (Code, Meldung, …). Client wirft daraus typisierte Exceptions
  (`InvalidConnectionTokenException` → Re-Login nötig).
- Unbekannte Route/Methode → 404-JSON (`NotFoundException`).

## Timeouts / Sonstiges

- Client-Timeout: 1.200.000 ms; `HttpCompression`-Flag (Launcher-Config)
  deutet auf optionale Kompression.
- Header `sl: <ms>` (Server): zufälliger Zusatz-Sleep (Timing-Verschleierung) —
  im Nachbau ignorierbar.

## Response-Wrapper (statisch verifiziert, 13.10.2026)

Entgegen dem Server-Default (`BodyStyle=bare`) erwartet **dieser Client**
jede JSON-Antwort als `WrappedResponse`: Der generische Proxy-Handler
(`MightyQuest_release.exe` `0x5cc280`) deserialisiert mit festem Typ
`"Util.Common.Service.WrappedResponse, Util.Common.Service"` und legt
dessen `Result` im Task-Ergebnis-Slot (`Task+0x9B8`) ab. Property-Name
`Result` laut `Util.Common.Service.dll` (`WrappedResponse`1`).

```json
{"Result":{"$type":"HyperQuest.GameServer.Contracts.AccountInformation, HyperQuest.GameServer.Contracts", …}}
```

Der Wrapper selbst trägt **kein `$type`**: `WrappedResponse` fehlt in der
Typ-Tabelle des Clients (2293 sortierte Namen, letzter `UIContracts…`), und
die Binärsuche (`0x1285020`) liest bei Namen, die hinter dem letzten Eintrag
sortieren, einen Eintrag über das Tabellenende hinaus → Access Violation
(`0xE123456E`), Prozess endet still (Minidump bestätigt). Leere Antworten
(void-Methoden) bleiben `{}`.

Nackte DTO-Antwort mit `$type` → Parse ok, aber `Result` NULL
(`GetBuildInfo:279`); ohne `$type` → `0x80030003`. `game_server.py`
wickelt alle JSON-Antworten zentral ein (`wrap_response`).

## TimeSpan-Format (Update3-Client)

Der JSON-Leser des Clients (0x122c680) erwartet TimeSpans **nicht** als .NET-`"d.hh:mm:ss"`,
sondern als String aus Zahl+Einheit-Folgen, optional mit `-` davor: `w` (Woche), `d`, `h`, `m`, `s`,
in Groß- und Kleinschreibung, Ergebnis in Sekunden. Beispiele: `"7d"`, `"1h30m"`, `"0s"`.
Achtung: Viele Dauer-Felder sind im Client gar keine TimeSpans, sondern Ganzzahlen (z. B. `CastleInfo.AverageDuration`,
`CastleValidationDuration`), und Listen wie `CompletionReward` erwarten `[`, nicht `null`. Im Zweifel den
Feldleser prüfen: `tools/client_members.py` + Disassembly; gleicher Leser-Call wie bei einem bekannten Int-Feld = Int.
Mit `"00:00:00"` meldet der Client `JSON ERROR: …: Not a time span`, bricht das Lesen ab und lädt dann endlos.

## Server-Notifications (Zustandsänderungen nach Aktionen)

Der Client übernimmt Ergebnisse serverseitiger Aktionen (Angriffsbeute:
Gold, XP, Items …) **nicht selbst**, und `GetAccountInformation` ruft er nur
beim Start. Im Original kamen solche Änderungen als Push-Notifications
(~100 Typen, u. a. `WalletUpdatedNotification`, `HeroInventoryAddedNotification`,
`HeroXpChangedNotification`, `MinePillagedNotification`; Basis
`Notification {Index, NotificationType}`).

- `ServerNotificationController` (`0xe22710`) verarbeitet empfangene
  Notifications der Reihe nach und vergleicht `Index` mit dem eigenen Zähler
  (`+0xcb50`) — genau dieser Zähler geht als Request-Header **`n`** an den
  Server. Bei einer Lücke ruft der Client `NotificationService.CheckNotifications`
  (void), damit der Server Fehlendes erneut schickt.
- **Transport ist der Antwort-Wrapper jeder HTTP-Antwort**, nicht XMPP: Der
  Client liest ihn mit `HyperquestWrappedResponseSerializer`, Felder `Result`,
  `Notifications`, `GlobalNotifications`, `AccountForValidation` (die
  Toolbox-`WrappedResponse`1` kennt nur `Result`). `ServerNotificationController`
  abonniert das entsprechende Ereignis des ArgoManagers (HTTP-Schicht).
- Format: `{"Result": …, "Notifications": [{"$type": "…WalletUpdatedNotification, …",
  "Index": 1, "NotificationType": "WalletUpdated", …}]}`; `NotificationType` als
  Enum-Name (Liste im Client direkt hinter den `…Notification`-Klassennamen).
- Umsetzung: `server/notifications.py` (Warteschlange, `n` = Bestätigung,
  Reset bei `GetAccountInformation`).
- Folge, verifiziert 14.10.2026 mit frischem Account: Gold/XP/Items eines
  Angriffs erscheinen erst nach Client-Neustart (Server-Zustand stimmt).
