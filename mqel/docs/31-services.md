# Service Catalog (game-relevant)

25 game services + 5 common services (complete map with all methods,
parameters and verbs: `analysis/api-gameserver.txt`,
`analysis/api-common.txt`).

## Core flow of a game client (to implement, prioritized)

| # | Service | Methods (selection) | Purpose |
|---|---|---|---|
| 1 | `SleepyGiantService.hqs` | `ValidateToken`, `Login`, `GetAccountIdByEmail` | Session setup (replaces Ubi login) |
| 2 | `AccountService.hqs` | `HealthCheck`, `ChooseDisplayName`, `Logout` | Boot, name selection |
| 3 | `AccountInformationService.hqs` | `GetAccountInformation`, `GetPublicProfileById`, `Search` | Everything after login |
| 4 | `AttackSelectionService.hqs` | `GetAttackSelectionList`, `GetCastleInfo` | Attack targets |
| 5 | `AttackService.hqs` | `StartAttack`, `Resurrect`, `EndAttack`, `RateCastle` | Attack lifecycle + replay upload |
| 6 | `ServerCommandService.hqs` | `SendCommands` | Build/buy/inventory commands |
| 7 | `CastleService.hqs` | `GetHighestRatedCastles`, `GetRecentlyPlayedCastles`, `GetFriendCastles` | Castle browser (dead code in the final client) |
| 8 | `BuildingService.hqs` | (still to be mapped) | Building logic |
| 9 | `HeroService.hqs` | (still to be mapped) | Heroes |
| 10 | `ShopService.hqs` | (still to be mapped) | Shop/SKUs (purchases without real money) |
| 11 | `FriendshipService.hqs` | accept/decline/… invitations | Friends |
| 12 | `ChallengeService.hqs` | CRUD + `SendAttackMessage` | Challenges |
| 13 | `MessagingService.hqs` | threads/inbox/outbox | Messages (dead code in the final client) |
| 14 | `NewsService.hqs` | `GetNews` | Lobby news |
| 15 | `NotificationService.hqs` | `CheckNotifications` | Polling |
| 16 | `ObjectiveService.hqs` | `CompleteClientObjective` | Tutorials/objectives |
| 17 | `LossService.hqs` | `RemoveShield` | Shield |
| 18 | `MysteryChestService.hqs` | `UnlockChest` | Chests |
| 19 | `ThemeService.hqs` | `SetCurrentTheme` | Castle skins |
| 20 | `SeasonalCompetitionService.hqs` | `CheckSeasonalCompetitionRewards`, `GetSeasonalCompetition` | Leagues/leaderboards |
| 21 | `ReplayService.hqs` | `StartReplayAttack`, `GetReplay` (+ `StoreReplay` StreamPost) | Replays |
| 22 | `TrackingService.hqs` (common) | `Track`, `TrackBatch` | Telemetry (accept + discard) |
| 23 | `UtilityService.hqs` (common) | `KeepAlive` | (trivial) |
| 24 | `TimeService.hqs` / `NewsService` | … | (trivial) |
| 25 | `NotificationService.hqs` | … | see above |

Also called by the final client (seen in the logs): `CastleForSaleService.hqs`
(`GetCastlesForSale`, startup castle), `UbisoftCompetitionService.hqs`
(`GetUbisoftCompetitionInfo`, `CheckEndedUbisoftCompetitions`), guild
services, `PatcherService.hqs` (launcher). The current implementation status
of each feature is in `CHECKLIST.md`.

## Tool/back office only (not needed for playing for now)

- `AdminService.hqs` (`[Private]`, among others `ImportCastle`/`ExportCastle`,
  `CreateFullyFunctionalAccount`, `ResetAccount` …) — useful later for
  **test accounts and starting castles** (instead: seed the database
  directly). Replaced by the admin web tool `/admin`.
- The rest of `SleepyGiantService.hqs` (ban/suspend/wallet/special packs/…) —
  adopt selectively (`UpdateWallet`, `ApplySpecialPack`, `GiveGifts` …).
- `DashboardService.hqs` (`[Private]`), `HeroService`/`ShopService` details,
  `IBuildingService` (check the method list in the map), `IFacebookService`
  (not a server service, only a doc pointer to the Facebook Graph API —
  dropped), `CrashReportService.hqs` (accept + ignore).
