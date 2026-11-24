# Auth & Sessions

Reconstructed from `HyperQuest.GameServer.dll`
(`Business.ConnectionManager`, `Util.Security.AuthenticationInterceptor`,
`Util.Security.HmacGenerator`, `Util.UserStorageLoader`) and
`HyperQuest.GameServer.Contracts` (`IAccountService`,
`ISleepyGiantService`).

## Login flow (game client)

```text
Launcher (website login) ── cookie "t" (= LoginToken), "hyperquest_launcher_session" (= SGToken)
  │  _buildUserInfoPayload() → { LoginToken, SGToken, UserEmail }
  ▼  as CLI args -token/-email to MightyQuest.exe
Game → POST SleepyGiantService.hqs/ValidateToken {"token": LoginToken}
    or POST SleepyGiantService.hqs/Login {profileId, accountId, ipAddress,
        languageCode, countryCode, dateOfBirth, timeZoneOffset}
  ▼
Server creates a session (Entities.Sessions.*) + ConnectionToken
  ▼
From then on the game sends the header "t: <ConnectionToken>" with every request
```

- `IAccountService.Login(email, password, ipAddress, timeZoneOffset)` is the
  password login (launcher website, not the game client).
- `ConnectionTokenManager.GetOrCreateUserContext`: reads `t` from the
  CallContext (copied from the request headers by `UserStorageLoader`),
  loads `AuthenticatedInfoEntity` (AccountId, privileges, …), caches it as
  `UserContext`. Unknown/empty → anonymous context (`a`/`e` headers) or null.
- `Logout()` destroys the token.

**Revival consequence:** we issue ConnectionTokens ourselves. Implemented in
`server/auth.py`: the launcher page (`/launcher/`, `POST /launcher/login` or
`/launcher/register` with `{name, password}`) returns a random 24-character
token; the launcher passes it to the game as `-token`. Only tokens issued by
the server are accepted — any other token gets `401
InvalidConnectionTokenException` and the client closes. A new login ends the
previous session of the same account. The dev option `--names-as-tokens`
additionally accepts the account name as token from 127.0.0.1. Steam login:
`server/steam_auth.py` (see `60-client.md`). The original login against
Ubiservices is dropped.

## `[Authenticated]` (method protection)

- On the server, `AuthenticationInterceptor`s check whether the target method
  carries `[Authenticated]` (`AllowAnonymous`, `RequiredPrivileges`,
  `DisableHmac`).
- Without a UserContext → `InvalidConnectionTokenException`; anonymous despite
  prohibition or missing privileges → `AccessDeniedException`.
- **Mapping** (56× bare + 3× with properties, from
  `HyperQuest.GameServer.dll`, see `analysis/authenticated-map.txt`):
  practically all game methods (`GetAccountInformation`, `StartAttack`,
  `EndAttack`, `SendCommands`, `Buy`, …). **Without** the attribute
  (= anonymous OK): `Login`/`ValidateToken`/`HealthCheck` methods, `KeepAlive`
  (`DisableHmac`), `Track`/`TrackBatch` (`AllowAnonymous, DisableHmac`).

## Client HMAC (anti-cheat, build flavor `HW_ANTICHEAT_MASTER`)

If `EnableClientHmac` is active **and** header `h` is present **and** the
method is `[Authenticated]` without `DisableHmac`:

```text
expected = Murmur32_seed0( UTF8(PathAndQuery) + UTF8(HttpMethod)
                           + raw request body bytes
                           + UTF8(ConnectionToken) + UTF8(RequestId-decimal)
                           + UTF8("`19^sW5;*|k#1$_lKo+dR,J5)El4*l}-") )[0..4] as UInt32
```

- `HmacGenerator.GenerateHMACSignature(request, connectionToken, requestId)`,
  hash = `Util.Common.Cryptography.Murmur32` = **standard MurmurHash3/x86_32**,
  seed 0 (body constants `0xCC9E2D51/0x1B873593`, tail and fmix constants
  verified).
- The client sends `i` = strictly increasing request id (uint) and `h` = value.
  The server rejects: wrong value, `i` older than `LastRequestId-10`,
  repetition within the last 10 HMACs (`MAX_CLIENT_HMACS_IN_SESSION`).
- **Revival:** currently `EnableClientHmac=false` (the game still sends `h`/`i`,
  they are ignored); verification can be added later — the algorithm is known.

## Other header contexts

`UserStorageLoader.LoadUserInformation` copies per request from the headers:
`rnd` (uint, `& 0xAAAAAAAA` → `ClientHackFlags`), `n` (int), `g` (string).
Safe to ignore, but the server should tolerate unknown headers (and the
re-implementation accepts them for form's sake). `rnd` is evaluated by the
revival's anti-cheat tracking (`server/anticheat.py`, logging only).
