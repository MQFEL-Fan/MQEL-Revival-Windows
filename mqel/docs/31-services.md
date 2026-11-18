# Service-Katalog (Spiel-relevant)

25 Game-Services + 5 Common-Services (vollständige Map mit allen Methoden,
Parametern und Verben: `analysis/api-gameserver.txt`,
`analysis/api-common.txt`).

## Kern-Flow eines Spiel-Clients (zu implementieren, priorisiert)

| # | Service | Methoden (Auswahl) | Wofür |
|---|---|---|---|
| 1 | `SleepyGiantService.hqs` | `ValidateToken`, `Login`, `GetAccountIdByEmail` | Session-Aufbau (ersetzt Ubi-Login) |
| 2 | `AccountService.hqs` | `HealthCheck`, `ChooseDisplayName`, `Logout` | Boot, Namenswahl |
| 3 | `AccountInformationService.hqs` | `GetAccountInformation`, `GetPublicProfileById`, `Search` | Alles nach Login |
| 4 | `AttackSelectionService.hqs` | `GetAttackSelectionList`, `GetCastleInfo` | Angriffsziele |
| 5 | `AttackService.hqs` | `StartAttack`, `Resurrect`, `EndAttack`, `RateCastle` | Angriffs-Lifecycle + Replay-Upload |
| 6 | `ServerCommandService.hqs` | `SendCommands` | Bau-/Kauf-/Inventar-Commands |
| 7 | `CastleService.hqs` | `GetHighestRatedCastles`, `GetRecentlyPlayedCastles`, `GetFriendCastles` | Burgen-Browser |
| 8 | `BuildingService.hqs` | (noch zu kartieren) | Bau-Logik |
| 9 | `HeroService.hqs` | (noch zu kartieren) | Helden |
| 10 | `ShopService.hqs` | (noch zu kartieren) | Shop/SKUs (Kauf ohne Echtgeld) |
| 11 | `FriendshipService.hqs` | Einladungen annehmen/ablehnen/… | Freunde |
| 12 | `ChallengeService.hqs` | CRUD + `SendAttackMessage` | Challenges |
| 13 | `MessagingService.hqs` | Threads/Inbox/Outbox | Nachrichten |
| 14 | `NewsService.hqs` | `GetNews` | Lobby-News |
| 15 | `NotificationService.hqs` | `CheckNotifications` | Polling |
| 16 | `ObjectiveService.hqs` | `CompleteClientObjective` | Tutorials/Ziele |
| 17 | `LossService.hqs` | `RemoveShield` | Schild |
| 18 | `MysteryChestService.hqs` | `UnlockChest` | Truhen |
| 19 | `ThemeService.hqs` | `SetCurrentTheme` | Burg-Skins |
| 20 | `SeasonalCompetitionService.hqs` | `CheckSeasonalCompetitionRewards`, `GetSeasonalCompetition` | Ligen/Leaderboards |
| 21 | `ReplayService.hqs` | `StartReplayAttack`, `GetReplay` (+ `StoreReplay` StreamPost) | Replays |
| 22 | `TrackingService.hqs` (Common) | `Track`, `TrackBatch` | Telemetrie (annehmen + verwerfen) |
| 23 | `UtilityService.hqs` (Common) | `KeepAlive` | ( trivial) |
| 24 | `TimeService.hqs` / `NewsService` | … | (trivial) |
| 25 | `NotificationService.hqs` | … | s. o. |

## Nur-Tool/Backoffice (fürs reine Spielen vorerst entbehrlich)

- `AdminService.hqs` (`[Private]`, u. a. `ImportCastle`/`ExportCastle`,
  `CreateFullyFunctionalAccount`, `ResetAccount` …) — später nützlich für
  **Test-Accounts und Start-Burgen** (stattdessen: DB-Seed direkt).
- `SleepyGiantService.hqs`-Rest (Ban/Suspend/Wallet/SpecialPacks/…) —
  punktuell übernehmen (`UpdateWallet`, `ApplySpecialPack`, `GiveGifts` …).
- `DashboardService.hqs` (`[Private]`), `HeroService`-/`ShopService`-Details,
  `IBuildingService` (Methodenliste in Map prüfen), `IFacebookService`
  (kein Server-Service, nur Doku-Zeiger auf Facebook Graph API — entfällt),
  `CrashReportService.hqs` (annehmen + ignorieren).
