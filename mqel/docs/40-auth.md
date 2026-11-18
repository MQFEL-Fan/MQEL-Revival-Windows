# Auth & Sessions

Rekonstruiert aus `HyperQuest.GameServer.dll`
(`Business.ConnectionManager`, `Util.Security.AuthenticationInterceptor`,
`Util.Security.HmacGenerator`, `Util.UserStorageLoader`) und
`HyperQuest.GameServer.Contracts` (`IAccountService`,
`ISleepyGiantService`).

## Login-Flow (Spiel-Client)

```text
Launcher (Website-Login) ── Cookie "t" (= LoginToken), "hyperquest_launcher_session" (= SGToken)
  │  _buildUserInfoPayload() → { LoginToken, SGToken, UserEmail }
  ▼  als CLI-Args -token/-email an MightyQuest.exe
Spiel → POST SleepyGiantService.hqs/ValidateToken {"token": LoginToken}
     oder POST SleepyGiantService.hqs/Login {profileId, accountId, ipAddress,
        languageCode, countryCode, dateOfBirth, timeZoneOffset}
  ▼
Server erzeugt Session (Entities.Sessions.*) + ConnectionToken
  ▼
Spiel sendet ab sofort Header "t: <ConnectionToken>" mit jedem Request
```

- `IAccountService.Login(email, password, ipAddress, timeZoneOffset)` ist der
  Passwort-Login (Launcher-Website, nicht Spiel-Client).
- `ConnectionTokenManager.GetOrCreateUserContext`: liest `t` aus dem
  CallContext (von `UserStorageLoader` aus den Request-Headern kopiert),
  lädt `AuthenticatedInfoEntity` (AccountId, Privileges, …), cached als
  `UserContext`. Unbekannt/leer → anonymer Kontext (`a`/`e`-Header) oder null.
- `Logout()` zerstört den Token.

**Revival-Folgerung:** Wir vergeben ConnectionTokens selbst (z. B. nach
freiem `ValidateToken`/`Login`: Token = Zufallsstring → Session anlegen).
Der Original-Login gegen Ubiservices entfällt.

## `[Authenticated]` (Methoden-Schutz)

- Serverseitig prüfen `AuthenticationInterceptor`s, ob die Zielmethode
  `[Authenticated]` trägt (`AllowAnonymous`, `RequiredPrivileges`,
  `DisableHmac`).
- Ohne UserContext → `InvalidConnectionTokenException`; anonym trotz
  Verbot bzw. fehlende Privileges → `AccessDeniedException`.
- **Kartierung** (56× bare + 3× mit Props, aus
  `HyperQuest.GameServer.dll`, s. `analysis/authenticated-map.txt`):
  praktisch alle Spiel-Methoden (`GetAccountInformation`, `StartAttack`,
  `EndAttack`, `SendCommands`, `Buy`, …). **Ohne** Attribut (= anonym OK):
  `Login`/`ValidateToken`/`HealthCheck`-Methoden, `KeepAlive`
  (`DisableHmac`), `Track`/`TrackBatch` (`AllowAnonymous, DisableHmac`).

## Client-HMAC (Anti-Cheat, Build-Flavor `HW_ANTICHEAT_MASTER`)

Wenn `EnableClientHmac` aktiv **und** Header `h` vorhanden **und** Methode
`[Authenticated]` ohne `DisableHmac`:

```text
erwartet = Murmur32_seed0( UTF8(PathAndQuery) + UTF8(HttpMethod)
                           + rohe Request-Body-Bytes
                           + UTF8(ConnectionToken) + UTF8(RequestId-dezimal)
                           + UTF8("`19^sW5;*|k#1$_lKo+dR,J5)El4*l}-") )[0..4] als UInt32
```

- `HmacGenerator.GenerateHMACSignature(request, connectionToken, requestId)`,
  Hash = `Util.Common.Cryptography.Murmur32` = **Standard-MurmurHash3/x86_32**,
  Seed 0 (Body-Konstanten `0xCC9E2D51/0x1B873593`, Tail- und
  fMix-Konstanten verifiziert).
- Client sendet `i` = strikt steigende Request-Id (uint) und `h` = Wert.
  Server lehnt ab bei: falschem Wert, `i` älter als `LastRequestId-10`,
  Wiederholung innerhalb der letzten 10 HMACs (`MAX_CLIENT_HMACS_IN_SESSION`).
- **Revival:** zuerst `EnableClientHmac=false` (Spiel sendet `h`/`i` trotzdem,
  sie werden ignoriert), später Verifikation nachbauen — Algorithmus liegt vor.

## Weitere Header-Kontexte

`UserStorageLoader.LoadUserInformation` kopiert pro Request aus den Headern:
`rnd` (uint, `& 0xAAAAAAAA` → `ClientHackFlags`), `n` (int), `g` (string).
Harmlos ignorierbar, aber der Server sollte unbekannte Header tolerieren
(und der Nachbau sie der Form halber akzeptieren).
