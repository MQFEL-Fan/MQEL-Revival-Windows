# Protocol: HTTP + JSON ("Argo Services")

Reconstructed from `Util.Client.dll` (URL building, request processors),
`Util.Server.dll` (routing, dispatch, HMAC) and
`Util.Common.Service.dll` (attributes). Verified by IL disassembly
(`tools/ildump.py`).

## URL scheme

```text
{GameServerUrl}/{ServiceName}/{MethodName}[?param=urlenc(value)&…]
```

- `GameServerUrl` comes from the launcher config or `-server_url`.
- `ServiceName` = `[Service]` attribute, e.g. `AccountService.hqs`
  (**including the `.hqs` suffix**, the Argo service definition file).
- `MethodName` = interface method name, e.g. `Login`.
- Client side (`ServiceClientFactory` → `UrlBuilder.BuildUrlFormat`):
  base = `GameServerUrl + "/" + ServiceName`, method = `"/" + Name +
  "?p0={0}&p1={1}…"` (stream parameters excluded), values via
  `String.Format` + `UrlEncode(ToString(arg))`.
- Server routing (`ServiceHttpHandler` + `ServiceRequestProcessor`):
  component `"~/" + ServiceName` (Castle Windsor), inside it the map
  `"/" + MethodName` → method processor. Unknown paths →
  `NotFoundException` (HTTP 404 as JSON error, see below).

Example (GET):

```text
GET http://server:port/AccountService.hqs/HealthCheck
GET http://server:port/AttackSelectionService.hqs/GetAttackSelectionList?attackRegionId=3&maxSuggestionCountByLevel=5
```

## Method types (attributes in `Util.Common.Service`)

| Attribute | HTTP | Request | Response |
|---|---|---|---|
| `[JsonGet]` (54× in game contracts) | GET | query params (`Request.Params`: QueryString+Form+Cookies+ServerVars) | `application/json` |
| `[JsonPost]` (160×) | POST | JSON body, see below | `application/json` |
| `[StreamGet]` (2×: `GetReplay`, `GetAttackAntiCheatJob`) | GET | query params | `application/octet-stream` |
| `[StreamPost]` (1×: `StoreReplay(accountId, replayStream)`) | POST | query + binary stream (via CallContext) | `application/json` |
| `[HtmlGet]` (1×: `LinkFacebookAccount`) | GET | — | `text/html` (dropped in the revival) |

- Wrong HTTP method → `NotFoundException`.
- `[Private]` (on type or method; among others `AdminService`,
  `SleepyGiantService`, `DashboardService` entirely): only via the
  **private port + HMAC headers** (`content-hmac`, `Date`,
  `content-accesskeyid`, signature `GenerateHMACSignature(Url, Method,
  Secret)` in `Util.Common.Service.WebRequestHelper`). Public game traffic
  does **not** need this.
- `BodyStyle` default = **0 = "bare"**: responses are the bare result JSON
  (no wrapper). `WrappedResponse<T>` (`{"Result":…}` via the CallContext key
  `WRAPPED_RESPONSE`) is only used with an explicit `BodyStyle=1` — not used
  in the GameServer. (But see "Response wrapper" below: the final client
  expects the wrapper anyway.)

## POST body

`{"<paramName>": <value>, …}` — one field per method parameter
(`PostHttpBodyContractBuilder`: dynamic contract type with fields =
parameter names; deserialized via `Util.Common.Json`):

```text
POST http://server:port/AccountService.hqs/Login
Content-Type: application/json

{"email":"…","password":"…","ipAddress":"…","timeZoneOffset":60}
```

Parameter and method names: `docs/analysis/api-gameserver.txt`
(generated with `tools/apimap.py`, including parameter names from the
.NET `Param` table).

## GET parameter types

`GetHttpMethodCompiler`: `string` raw, otherwise `BuildConvertMethodCallExpression`
(`Parse`-based: numeric types, `bool`, `Enum`, `DateTime`, `ObjectId`,
`Nullable<>`; missing → `default(T)`). There are no complex DTOs via GET —
all complex calls are POST.

## Ambient headers (every request, see `40-auth.md`)

| Header | Type | Meaning |
|---|---|---|
| `t` | string | ConnectionToken (session, see auth) |
| `i` | uint32 | Request counter (anti-replay, only with `h`) |
| `h` | uint32 | Client HMAC (Murmur3, only if server has `EnableClientHmac`) |
| `rnd` | uint32 | Client flags (`& 0xAAAAAAAA` → `ClientHackFlags`, telemetry) |
| `n` | int | Last received notification index (see "Server notifications") |
| `g` | string | (context, usage to be checked on the server side) |

The server reads them in `UserStorageLoader.LoadUserInformation` from
`Request.Headers` into the CallContext. They are optional for basic operation
(without `t` = anonymous; without `h` = no HMAC check).

## Dynamically verified (2026-10-13, client `0.36.1.34.0` against a logging server)

- The client additionally sends the header **`sl: 0`** (otherwise only known
  as a server header) and `Accept: */*`.
- `Content-Type` is `application/json; charset=utf-8`.
- The request counter `i` starts at **0** and increases strictly (`0, 1, …`);
  `h` is always sent (the server ignores both for now).
- POST bodies use **Newtonsoft `$type` polymorphism**:
  `{"commands":[{"$type":"HyperQuest.GameServer.Contracts.TrackingCommand,
  HyperQuest.GameServer.Contracts","TrackingTag":{"$type":"…GameStartTracking,
  …","GameClientVersion":"280139","MachineId":"…","CreationDate":"",
  "TrackingTagId":108}}]}` — note: a default `DateTime` is serialized as
  **`""`**, `GameClientVersion` = game package ID (`version.Game.txt`).
- Stream parameters (`replayStream`) do **not** appear in the JSON body, as
  expected (`SendCommands` sends only `{"commands":[…]}`).
- First boot flow: `POST ServerCommandService.hqs/SendCommands`
  (GameStart tracking) → `GET AccountInformationService.hqs/GetAccountInformation`.

Boot flow observed on Windows (2026-11-20, launcher + patched exe over HTTPS):
`SendCommands` (GameStart tracking) → `GetAccountInformation` →
`UbisoftCompetitionService.hqs/CheckEndedUbisoftCompetitions` →
`CastleForSaleService.hqs/GetCastlesForSale?startupCastle=true` →
`SendCommands` (`StartAssignmentCommand`, castle purchase →
`CastleBoughtNotification`) → periodic `SendCommands`/`Track`/`KeepAlive`.

## Versioning

- `[Service]` can carry `ServiceVersion`; `CheckServiceVersionInterceptor`
  checks the client version (`"v"`). Details/tolerance still to be verified —
  the re-implementation should accept any version.
- `Content-Length: 0` POSTs without a body are allowed (parameterless calls).

## Errors

- HTTP status = `ServiceException.HttpStatusCode`,
  `Content-Type: application/json`, body = `ServiceExceptionSerializer` JSON
  (code, message, …). The client turns it into typed exceptions
  (`InvalidConnectionTokenException` → re-login required).
- Unknown route/method → 404 JSON (`NotFoundException`).

## Timeouts / misc

- Client timeout: 1,200,000 ms; the `HttpCompression` flag (launcher config)
  suggests optional compression.
- Header `sl: <ms>` (server): random extra sleep (timing obfuscation) —
  can be ignored in the re-implementation.

## Response wrapper (statically verified, 2026-10-13)

Contrary to the server default (`BodyStyle=bare`), **this client** expects
every JSON response as a `WrappedResponse`: the generic proxy handler
(`MightyQuest_release.exe` `0x5cc280`) deserializes with the fixed type
`"Util.Common.Service.WrappedResponse, Util.Common.Service"` and stores its
`Result` in the task result slot (`Task+0x9B8`). Property name
`Result` according to `Util.Common.Service.dll` (`WrappedResponse`1`).

```json
{"Result":{"$type":"HyperQuest.GameServer.Contracts.AccountInformation, HyperQuest.GameServer.Contracts", …}}
```

The wrapper itself carries **no `$type`**: `WrappedResponse` is missing from
the client's type table (2293 sorted names, last one `UIContracts…`), and the
binary search (`0x1285020`) reads one entry past the end of the table for
names that sort after the last entry → access violation (`0xE123456E`), the
process exits silently (confirmed by minidump). Empty responses (void methods)
stay `{}`.

Bare DTO response with `$type` → parse OK, but `Result` is NULL
(`GetBuildInfo:279`); without `$type` → `0x80030003`. `game_server.py`
wraps all JSON responses centrally (`wrap_response`).

## TimeSpan format (Update3 client)

The client's JSON reader (0x122c680) does **not** expect TimeSpans as .NET
`"d.hh:mm:ss"`, but as a string of number+unit sequences, optionally prefixed
with `-`: `w` (week), `d`, `h`, `m`, `s`, upper or lower case, result in
seconds. Examples: `"7d"`, `"1h30m"`, `"0s"`.
Caution: many duration fields in the client are not TimeSpans at all but
integers (e.g. `CastleInfo.AverageDuration`, `CastleValidationDuration`), and
lists like `CompletionReward` expect `[`, not `null`. When in doubt check the
field reader: `tools/client_members.py` + disassembly; same reader call as for
a known int field = int.
With `"00:00:00"` the client reports `JSON ERROR: …: Not a time span`, aborts
reading and then loads forever.

## Server notifications (state changes after actions)

The client does **not** apply the results of server-side actions itself
(attack loot: gold, XP, items …), and it calls `GetAccountInformation` only at
startup. In the original such changes came as push notifications
(~100 types, e.g. `WalletUpdatedNotification`, `HeroInventoryAddedNotification`,
`HeroXpChangedNotification`, `MinePillagedNotification`; base
`Notification {Index, NotificationType}`).
  `Index` is the running number per session (header `n` acknowledges it).
  Subclasses must not reuse that name for their own data:
  `ShowMoreCastleNotification` has only this `Index`. A reroll count sent
  there made the client drop the notification as already seen, and the
  castle selection loaded forever (fixed 2026-11-20; `notifications.push`
  protects `Index`/`NotificationType`).

- `ServerNotificationController` (`0xe22710`) processes received
  notifications in order and compares `Index` with its own counter
  (`+0xcb50`) — exactly this counter is sent as request header **`n`** to the
  server. If there is a gap, the client calls
  `NotificationService.CheckNotifications` (void) so that the server resends
  what is missing.
- **The transport is the response wrapper of every HTTP response**, not XMPP:
  the client reads it with `HyperquestWrappedResponseSerializer`, fields
  `Result`, `Notifications`, `GlobalNotifications`, `AccountForValidation`
  (the toolbox `WrappedResponse`1` only knows `Result`).
  `ServerNotificationController` subscribes to the corresponding event of the
  ArgoManager (HTTP layer).
- Format: `{"Result": …, "Notifications": [{"$type": "…WalletUpdatedNotification, …",
  "Index": 1, "NotificationType": "WalletUpdated", …}]}`; `NotificationType` as
  enum name (list in the client directly after the `…Notification` class names).
- Implementation: `server/notifications.py` (queue, `n` = acknowledgement,
  reset on `GetAccountInformation`).
- Consequence, verified 2026-10-14 with a fresh account: before notifications
  were implemented, gold/XP/items of an attack only appeared after a client
  restart (server state was correct).
