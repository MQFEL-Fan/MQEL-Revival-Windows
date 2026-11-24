# Revival Build Plan

> This file is mostly the **historical log** of how the server was built
> (October 2026). For the current state see `CHECKLIST.md`; for running it on
> Windows see `05-windows-setup.md`.

## A. Already clarified statically ✅

- Archive inventory; no runnable server in `main.*.7z`, but **complete server
  assemblies + API docs**.
- Process model (launcher → master (packed) ↔ worker (pipe) → HTTP).
- **Protocol**: `GET/POST {GameServerUrl}/{Service}.hqs/{Method}[?params]`,
  JSON body `{"param":…}`, headers `t/i/h/rnd/n/g`, errors as JSON with
  HTTP status, `BodyStyle=bare` (no wrapper — later disproved for the final
  client, see section E).
- **Auth**: ConnectionToken via header `t`; client HMAC = Murmur3 + secret
  (algorithm known exactly; run with it disabled first).
- **API map**: 25+5 services, ~220 endpoints with parameter names
  (`docs/analysis/*.txt`, tool `tools/apimap.py`).

## B. Next analysis steps (at the time)

1. **JSON details** (own docs / verify dynamically):
   property names (C# names 1:1?), enum/DateTime/ObjectId/decimal format,
   `ServiceException` JSON fields, GET conversions, `$type` fields
   (`TypeNameHandling`).
2. **`[Authenticated]` mapping** on `HyperQuest.GameServer.dll`
   (which methods need a token?) + `EnableClientHmac` default.
3. **Login implementations** (`SleepyGiantService.Login/ValidateToken`,
   `ConnectionManager`): exact session setup, `LoginResult` content.
4. **Capture the start flow** (dynamically, see C): real request order
   after game start, real JSON examples.
5. **GameplaySettings inventory**: which `*.json` the server loads
   (`RootSettingsPath`, `[JsonPath]` classes), news/shop paths.
6. **GameCommand model** (`SendCommands`, `EndAttackParams`,
   replay format) for attack resolution.

## C. Dynamic analysis (running since 2026-10-13, log)

- Logging server: `server/logging_server.py`, today `server/game_server.py`
  (renamed when it became the actual game server; all requests → console +
  `server/requests.log.jsonl`), responses via `server/responses.json`
  (reloaded per request, `$file:` includes for large stubs).
- First capture: `SendCommands` (GameStart tracking) →
  `GetAccountInformation` → client crash in the loading screen (empty `{}`).
- `GetAccountInformation` stub: `server/build_account_stub.py` builds the
  response from `GameplaySettings/AccountTemplates/000003 - FullAccount.json`
  (4 heroes level 30, wallet, castle blueprint, objectives…); shape via
  reflection over the original contracts (`server/gen_stub.ps1`,
  catalog: `docs/analysis/dto-catalog.txt` — 1495 classes, 223 enums).
- AccountTemplates (`GameplaySettings/AccountTemplates/*.json`) are the
  **server-side seed data** for `AdminService.ResetAccount` /
  `CreateFullyFunctionalAccount(…, templateId, …)` (TemplateId = file name
  prefix, e.g. `000001` = DefaultAccount with `ShouldResetDisplayName=true` →
  `ChooseDisplayName` flow).
- Run 2: the client stops after `GetAccountInformation` (no further server
  requests), shows `NETWORK ERROR …`, and on exit
  `OPAL ASSERT - XmppInfo cannot be null … ChatController::LeaveRoom:438`.
  Client strings prove its own XMPP implementation (`XmppClient_Z.cpp`,
  `AccountServerController::GetXmppInfo`, `Invalid XmppInfo in
  AccountInformation`, `m_currentAccountInfo->ClientSettings->XmppInfo`).
  Hypothesis: `XmppInfo` is validated directly after the account and the error
  dialog comes from there (not from the HTTP traffic).
- Countermeasure: the stub now delivers a plausible `XmppInfo` (`Enabled=true`,
  `Server=127.0.0.1`, `Port=5222`, …); `logging_server.py --tcp-ports 5222`
  proves via honeypot whether the client dials XMPP. If yes: fake XMPP
  (SASL PLAIN + bind + presence) as the next building block.
- Run 3: `OPAL ASSERT Functional server error 0x80030003` in
  `AccountServerController::OnAccountInformationTaskError:449` (task
  `GetAccountInformationTask`), then ignored: `Invalid
  AccountInformation … GetAccountForgedItem:502` (follow-up error without a
  loaded account), then game UI `NETWORK ERROR`, on exit again
  `LeaveRoom:438`. The only stub change was `XmppInfo` → evidence that the
  account task includes the XMPP connect and fails without a chat server.
- Built: `server/xmpp_server.py` (fake XMPP: stream/PLAIN/bind/session,
  empty roster, MUC self-join, keepalive; everything → `server/xmpp.log`;
  smoke test with a complete handshake passed). Client expectations confirmed
  from binary strings (`Did not receive stream features after SASL
  authentication.`, `Bind successful.`, `STARTTLS not supported.` →
  plain text without a TLS offer is intended).
  Note: `xmpp_server.py` exits cleanly with Ctrl+C (timeout loop + signal
  handler, socket is closed); if a terminal hangs, end the `python.exe` with
  `xmpp_server` in its command line via Task Manager/`Stop-Process`
  (on Windows: `stop_servers.bat`).
- Side note: `Inventory.ForgedItem` is non-null (`ForgeMode=None`), otherwise
  `GetAccountForgedItem:502` asserts.
- Run 4 (stub with `Enabled=true`, everything 127.0.0.1): again `0x80030003`,
  **no** XMPP contact, no further HTTP requests. Client logs
  (`Bin/MQLog.txt`, `Bin/NetworkLog.Txt`) prove: the HTTP response arrives
  completely (`ARGO: Request 1 completed`), the assert fires ~50 ms later —
  so a **local** failure in account processing, not a network timeout.
  Shutdown sequence logged cleanly (`ClientIdleCommand` + `GameStateTracking`
  + `LogoutCommand`, i=2).
- Next hypothesis: the client connects to `Domain`/`ConferenceServer`
  instead of `Server` (DNS failure without TCP) → the stub now uses
  `127.0.0.1` everywhere (JIDs `test@127.0.0.1/…`, fake XMPP mirrors any
  domain).
- Independently confirmed: the lobby UI loads from `http://localhost/gamedata/…`
  (`WebviewManager::Initialize() - lobbyPageUrl`, see MQLog) → own
  `server/static_server.py` (`/gamedata/` → `GameData/Data/`,
  `/AG_BA073_01.gamewebsite/` → `GameData/`, 404 logging; port 80 = admin
  terminal needed). Explains the game UI `NETWORK ERROR` from run 2.
  *Later disproved (Oct 2026):* the client serves `/gamedata/` itself
  (CEF handler → `../Data`), the game runs without the static server; it
  was removed.
- Experiment: `XmppInfo.Enabled` back to `false` (only variable), rest (lobby
  with :80 server) unchanged — goal: reach the lobby, chat later (see comment
  in `build_account_stub.py`).
- Run 5 (screenshot): `0x80030003` despite `Enabled=false` → `Enabled` was
  never the variable. Remaining diff to run 2 (task OK): filled XmppInfo fields
  + `ForgedItem` null→object. Diagnostic variants `server/stubs/ai-A.json`
  (only Xmpp empty) / `ai-B.json` (exact run-2 state), switchable via
  `responses.json` with the server running + assert dialog button "Retry"
  (`server/make_variants.py`).
  Result: error in BOTH cases → neither the Xmpp fields nor ForgedItem.
- New hypothesis: castle integrity (`AccountPrivilege.ByPassCastleIntegrity-
  Check` exists; our draft had 3 EMPTY rooms). `010030 -
  FullAccount_30_FullUpdate.json` contains the only COMPLETE castle (rooms
  with buildings/creatures) → `build_account_stub.py` now uses it for the
  draft (4 rooms, 9 buildings, 1 creature; DTO shapes
  `CastleBuilding/CastleCreature/Orientation` from dto-catalog). Base for the
  rest = 010030 (priv 232), objectives still from 000003.
- Result: SAME error, "Retry" crashes the client (retry route dead).
  Strategy change: **structure vs. content** — `server/stubs/ai-S.json`
  (reflection skeleton: all 37 keys, empty defaults, 2.7 KB) as a new
  experiment; additive build-up on success. At the same time transport
  spec-compliant: `logging_server.py` speaks HTTP/1.1 + keep-alive and sends
  the `sl` header (verified). **Caution: server restart required**
  (code change, not just a responses.json reload).
- Result skeleton: SAME error → content is ruled out. RE finding
  (static, `MightyQuest_release.exe` is 32-bit!): task invokers
  (`0x115eca0` ff.) map sub-call failure → `0x80030003`
  (`0x80030002` = null arg); `OnAccountInformationTaskError` only swallows
  `0x80000001` (cancel). The client JSON parser is strict, hand-written
  (`Expected [true] or [false]`, `Not a number`, `Not a time span`,
  `Expected character/string`, `Max json string exceeded`,
  `Cannot get object serializer [%s]`); datetime = `"YYYY-MM-DDTHH:MM:SSZ"`
  (Z mandatory), but `""` → MinValue is OK. The error logger is NULL in this
  path (silent). Role of the `sl` header: unclear.
- New hypothesis: after the account parse a SECOND request follows to a
  DIFFERENT target (not GameServer/XMPP/:80 — nothing arrives there), which
  fails immediately. Test: `Get-NetTCPConnection` per MightyQuest process
  during the hang (SYN targets!).
- Netstat result: NO outbound except 2× keep-alive to :8081; instead the game
  listens on 1337/9920/12987/50000 (CEF bridge/debug, irrelevant).
  The error is 100 % local. Open uncertainty: whether the ai-S run already
  used the new server code (HTTP/1.1+`sl`, restart required) — a clean
  restart + ai-S was pending.
- Restart confirmed, ai-S still fails. New finding: the skeleton contains
  `Inventory.ForgedItem.Item = null` (`InventoryItem` is abstract!),
  2× ObjectId `"000…"`, 4× `""` dates. Variant
  `server/stubs/ai-C.json` (`server/make_aiC.py`) removes all three forms;
  on success build up additively, on failure bisect the scalars.
- ai-C also fails → bisect by key removal (`server/make_aiD.py`):
  `ai-D1.json` (28 keys: without all 9 object members), fallback
  `ai-D2.json` (13 scalars).
- D1 + D2 BOTH fail → even 13 scalars don't parse. New suspicion:
  response `Content-Type`: our server sent `application/json`, but the only
  JSON CT literal in the client is `application/json; charset=utf-8`
  (exact ASP.NET format, also in its requests). `logging_server.py` now sends
  exactly this CT (server restart required). Test directly with the full stub:
  if CT was the cause, we are through in one run.
- CT theory still open. NEW LEADING THEORY ($type): the client parser resolves
  object deserializers via `$type` (`Cannot get object serializer [%s]`; no
  key literals in the binary!); the client itself sends `$type` per DTO
  (capture). Our responses never had `$type` — `{}` gets through (nothing to
  resolve), every non-empty object fails. `server/add_dollar_type.py` sets
  `$type` (Newtonsoft format, first position) on all 521 DTO objects of the
  full stub (type names verified from dto-catalog; polymorphic `Item`s
  included). `logging_server.py` now also logs a response summary + start
  marker (verified) — from `requests.log.jsonl` you can now read WHAT the
  client received (restart check!).
- BREAKTHROUGH: with the `$type` full stub (+ new server code) the account task
  goes through — instead of `0x80030003` now
  `Invalid AccountInformation … GetBuildInfo:279` (`m_currentAccountInfo`
  NULL). I.e. response parse OK; check storage/follow-up call. Next step:
  ignore chain (all follow-up dialogs in order) + new requests in the game
  log. The contributions of CT vs. $type cannot be cleanly separated in
  retrospect — both stay in (both are spec-compliant).
- Analysis of the storage path (static): the success handler stores via
  `AcquireResult` (`[Task+0x9B8]` → slot, move!) — slot NULL means TASK
  RESULT NULL (parse "successful", but NULL object). Hypothesis: top-level
  `$type` confuses the lookup (silently NULL); static dispatch without top
  `$type` + nested `$type` for polymorphic `.Item` could be the combination.
  Variant `ai-E.json` (`server/make_aiE.py`): full stub minus top `$type`.
  Three outcomes: 0x80030003 back / assert remains / breakthrough.
- Result ai-E: 0x80030003 back. BUT: transport fix vs. $type never cleanly
  decoupled (ai-E may have run with old code)! Next run: ai-E + VERIFIED new
  code (curl check `Content-Type: application/json; charset=utf-8`) →
  separates transport vs. $type cleanly.
- Side finding: log lines could tear with parallel requests (threading
  without lock) → `LOG_LOCK` in `logging_server.py`.
- Ops: `server/stop.ps1` stops all three servers by command line (if Ctrl+C
  does not reach the terminal; for the port-80 process run as admin if
  needed). Today: `stop_servers.bat`.

- Start `MightyQuest.exe` directly (bypass the launcher):
  `MightyQuest.exe -server_url http://127.0.0.1:PORT -token test -email
  test@test -environmentName local -httpCompression 0`
  (omit Steam args if needed; watch `-compipe` child processes). Today the
  server only accepts tokens it issued itself, see `40-auth.md` and
  `launch_game.bat`.
- Own logging HTTP server on PORT (dump all paths + headers + body),
  return minimal JSON responses, extend **iteratively**:
  `HealthCheck` → `ValidateToken/Login` → `GetAccountInformation` → …
- WinHTTP traffic to localhost can be captured without TLS; the UBX packing
  is unpacked at runtime (memory dump for strings/URLs if needed).
- Expectation: after every missing call the game shows an error with the
  service name — that is the best specification.

## D. Server rebuild (proposal at the time: C# / ASP.NET Core or Python — Python was chosen)

1. **Skeleton**: routing `{service}.hqs/{method}`, GET/POST dispatch,
   JSON, read headers `t/i/h/rnd/n/g`, error envelope, logging of all calls
   (crucial for iteration).
2. **Session/auth**: token table, `ValidateToken`→token,
   `[Authenticated]` equivalent, HMAC verify (Murmur3) optional.
3. **Domain stubs**: minimal sensible responses per service
   (account info with starting castle/hero from `GameplaySettings`, empty
   lists, fixed shop SKUs); attack lifecycle (`StartAttack`→`EndAttack`) with
   simple loot calculation; `SendCommands` as no-op with echo.
4. **Persistence**: JSON files per account (originally planned:
   SQLite/Postgres); model from `Entities.xml` + needs.
5. **Load GameplaySettings**: `Data/GameplaySettings/**/*.json` from
   `GameData.7z` as the rule base (SpecContainerIds, costs, loot tables).
6. Later: friendship/challenges/leaderboards, admin import
   (`ImportCastle`), E2E tests with a script client against all 220 endpoints.

## E. Open risks (at the time) and resolutions

- **Packed master**: if it contains integrity/anti-debug checks (UBX) or
  hard-coded URLs/certificates, patches or hosts/proxy tricks are needed.
  *Resolved:* the ship exe insists on `https` and only trusts embedded CAs;
  the revival uses the unpacked `MightyQuest_profile.exe` with our own
  certificate (`tools/patch_ca.py`, see `60-client.md`).
- **CEF UI** (`mightyquest-ui.exe`): lobby/shop pages could make their own
  web calls — capture and rebuild.
- **Chat (ejabberd/XMPP)**: `ChatSettings`/`XmppInfo` DTOs exist;
  *resolved* with `server/xmpp_server.py`.
- **Version**: client `0.36.1.34.0` vs. toolbox `main.348.1` — small API
  drift possible; the dynamic capture decides.
- CAUSE FOUND (`GetBuildInfo:279`): the client expects JSON responses as a
  `WrappedResponse` (`{"$type":"Util.Common.Service.WrappedResponse,
  Util.Common.Service","Result":…}`), see `30-protokoll.md`. The MQLog of the
  run with the `$type` full stub showed `Account information loaded` directly
  before the assert. Schema drift client (Update3) ↔ toolbox: the client does
  not know e.g. `ShopSkus`, `Challenges`, `AttackRegions`, `Hero.Attributes`,
  `InventoryItem.Type/SellPrice`, `ItemEffect.Variation/AbsoluteValue`
  (only JSON WARNINGs, not critical).
- Follow-up error "silent exit after 20–30 s": wrapper `$type` →
  out-of-bounds read in the client type table (procdump minidump, see
  `30-protokoll.md`). Fix: wrapper without `$type` (`{"Result":…}`), empty
  responses `{}`.
- Items in client form (Update3): values 1:1 from the AccountTemplates of the
  client data (ArchetypeId, PrimaryStatsModifiers, Effects{Id,Level,Type},
  PowerUp{Id,Level}); field lists from the client readers. Result: shop,
  purchase (`BuyHeroItemCommand`) and equipping (`HeroEquipmentEquipCommand`)
  work on the client side.
- Persistence: `server/account_state.py` holds the account (seed = stub,
  state in `server/state/<profile>/`, delete = reset). Handles all commands
  listed in `CHECKLIST.md`. Client HeroItemSlot (Update3, verified): Head1
  Shoulders2 Body3 Back4 Neck5 Finger1=6 Hands7 MainHand8 OffHand9 Costume10
  Pet11. Unknown commands → `[state] nicht behandelt` ("not handled") in the
  server log.
