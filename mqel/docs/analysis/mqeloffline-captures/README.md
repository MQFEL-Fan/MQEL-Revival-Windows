# Captures from MQELOffline_cpp

Source: <https://github.com/Hedgehogscience/MQELOffline_cpp> (MIT, Convery /
Hedgehogscience, 2018), an earlier C++ re-implementation of the server against
the same client. `captures.json` contains all JSON responses embedded in its
source code, with their location. Several are obviously captures from the
original server (MongoDB ObjectIds and dates from October 2016), e.g.
`AttackService.cpp:173/177` (EndAttack), `AttackSelectionService.cpp:19`
(attack selection incl. `BossCastle` and real player castles).

Proven from this (2026-10-14):
- Response wrapper with `Result`, `Notifications`, `GlobalNotifications`.
- `WalletUpdatedNotification.Amounts` = **differences** per currency.
- `NotificationType` as a number: ObjectiveCompleted 14, ObjectiveUnlocked 17,
  WalletUpdated 24, HeroXpChanged 43, WalletCurrencyCapacityUpdated 47,
  ServerAssignmentActionCompleted 74, CastleBought 86, InboxItemsAdded 111.
- Loot items went into an inbox as `InboxItemsAddedNotification`
  (`InboxHeroEquipmentItem`/`InboxConsumableItem` with `ObjectId`), not
  directly into the inventory.
- Nested DTOs without `$type` were accepted by the client.
