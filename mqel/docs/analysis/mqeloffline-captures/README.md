# Mitschnitte aus MQELOffline_cpp

Quelle: <https://github.com/Hedgehogscience/MQELOffline_cpp> (MIT, Convery /
Hedgehogscience, 2018), ein früherer C++-Nachbau des Servers gegen denselben
Client. `captures.json` enthält alle dort im Quelltext eingebetteten
JSON-Antworten mit Fundstelle. Mehrere sind offensichtlich Mitschnitte des
Originalservers (MongoDB-ObjectIds und Daten aus Oktober 2016), z. B.
`AttackService.cpp:173/177` (EndAttack), `AttackSelectionService.cpp:19`
(Angriffsauswahl inkl. `BossCastle` und echter Spielerburgen).

Daraus belegt (14.10.2026):
- Antwort-Wrapper mit `Result`, `Notifications`, `GlobalNotifications`.
- `WalletUpdatedNotification.Amounts` = **Differenzen** je Währung.
- `NotificationType` als Zahl: ObjectiveCompleted 14, ObjectiveUnlocked 17,
  WalletUpdated 24, HeroXpChanged 43, WalletCurrencyCapacityUpdated 47,
  ServerAssignmentActionCompleted 74, CastleBought 86, InboxItemsAdded 111.
- Beute-Items gingen als `InboxItemsAddedNotification` in einen Posteingang
  (`InboxHeroEquipmentItem`/`InboxConsumableItem` mit `ObjectId`), nicht
  direkt ins Inventar.
- Verschachtelte DTOs ohne `$type` wurden vom Client akzeptiert.
