"""Tracking: Ereignisprotokoll je Profil für die GameplayToolbox (Reiter Tracking).

Das Original schrieb TrackingBaseEntity-Dokumente nach MongoDB/S3
(HyperQuest.GameServer TrackingManager); die Toolbox liest sie mit
AdminService.GetLatestTrackedData als JSON-Strings und wertet daraus nur
TrackingTagId, AccountId und TagId aus, der Rest erscheint im Detailbaum.

Quellen: was der Client selbst an TrackingService.hqs schickt (Launcher,
Logout, PC-Konfiguration), Spielbefehle (COMMAND_TAGS), Server-Meldungen an
den Spieler (NOTIFICATION_TAGS), Login und Angriffsende (game_server.py).

Ablage: tracking-JJJJ-MM.jsonl je Monat im Profilverzeichnis, eine Zeile je
Ereignis, nichts wird gelöscht (Archiv). Im Speicher (für die Toolbox) nur
die letzten KEEP Ereignisse; beim Start aus den neuesten Monatsdateien.
"""

import collections
import glob
import datetime
import json
import os
import secrets
import threading

# Contracts.Common.Tracking.TrackingTagId (Contracts.Common.Enum.dll)
LOGIN = 102
RESURRECTION = 506
CASTLE_RATING_PRIZE = 509
SHOP = 501
PREMIUM_CASH_PURCHASED = 519
ACCOUNT_CREATION = 522
SPECIAL_PACK_PURCHASED = 526
FRIENDSHIP_INVITATION_SENT = 601
FRIENDSHIP_ANSWERED = {"AcceptFriendshipInvitation": 603,
                       "DeclineFriendshipInvitation": 604,
                       "CancelFriendshipInvitation": 602}
FRIENDSHIP_REMOVED = 605
HERO_LEVEL_UP = 701
ATTACK = 2101
TEST_ATTACK = 2102
CASTLE_RATING = 2904
LEAGUE_PROMOTED = 3201
LEAGUE_DEMOTED = 3202
WORLD_LEADERS = 3204
CHEAT_FAILURE = 1401
CLIENT_HACK = 1402
CHAT_MUTED = 2790  # eigene Id (nicht im Original): Stummschaltung im Admin-Tool

# Namen aller TrackingTagIds (Anzeige im Admin-Werkzeug)
LAUNCHER_STATE_MACHINE = 212

TAG_NAMES = {
    101: "Session",
    102: "Login",
    103: "Logout",
    104: "PcConfigurationTracking",
    105: "ServerStatus",
    107: "GameState",
    108: "GameStart",
    109: "GameInitialize",
    150: "AssignmentStarted",
    151: "AssignmentCompleted",
    201: "LauncherDownloadFullClientStarted",
    202: "LauncherDownloadFullClientCompleted",
    203: "LauncherDownloadPackageStarted",
    204: "LauncherDownloadPackageCompleted",
    205: "LauncherInstallFullClientStarted",
    206: "LauncherInstallFullClientCompleted",
    207: "LauncherInstallPackageStarted",
    208: "LauncherInstallPackageCompleted",
    209: "LauncherDownloadPatcherStarted",
    210: "LauncherDownloadPatcherCompleted",
    211: "LauncherPlayGameClicked",
    LAUNCHER_STATE_MACHINE: "LauncherStateMachine",
    501: "EconomicShop",
    502: "EconomicGoldAttackerReward",
    504: "EconomicHeroItemSell",
    505: "EconomicLootTransference",
    506: "EconomicResurrection",
    509: "EconomicCastleRatingFreePrize",
    510: "EconomicChallengeReward",
    511: "EconomicLifeForceAttackerReward",
    516: "EconomicIncrementAllAccounts",
    518: "EconomicObjectiveCompleted",
    519: "EconomicPremiumCashPurchased",
    520: "EconomicPayToForceExpiration",
    521: "EconomicDefenderLoss",
    522: "EconomicAccountCreation",
    523: "EconomicMineHarvested",
    524: "EconomicHeroCorpseHarvested",
    525: "EconomicItemBuyBack",
    526: "EconomicSpecialPackPurchased",
    527: "EconomicPremiumCashRefunded",
    528: "EconomicCustomerSupportWalletUpdated",
    529: "EconomicKillsAttackerReward",
    530: "EconomicTreasureRoomAttackerReward",
    531: "EconomicGift",
    533: "EconomicAccountReset",
    534: "EconomicDefenseIngredientItemSold",
    535: "EconomicFriendRewardRecieved",
    536: "EconomicMinePillagingAttackerReward",
    537: "EconomicCurrencyGeneratedFromDesync",
    538: "EconomicPremiumCashRestored",
    601: "FriendshipInvitationSent",
    602: "FriendshipInvitationCancelled",
    603: "FriendshipInvitationAccepted",
    604: "FriendshipInvitationDeclined",
    605: "FriendshipRemoved",
    701: "HeroLevelUp",
    702: "HeroLevelUpReady",
    801: "PublishedCastle",
    901: "ItemShareStarted",
    902: "ItemShareExpired",
    903: "ItemShareDeclined",
    904: "ItemAdded",
    1001: "ClientCallProfiling",
    1002: "ServerMethodProfiling",
    1101: "ObjectiveUnlocked",
    1102: "ObjectiveCompleted",
    1201: "AchievementCompleted",
    1301: "CastleLevelUp",
    1401: "CheatFailure",
    1402: "ClientHack",
    1501: "ChallengeCreated",
    1502: "ChallengeCancelled",
    1503: "ChallengeAccepted",
    1504: "ChallengeDeclined",
    1505: "ChallengeEnded",
    1601: "OpenPanel",
    1602: "ClosePanel",
    1701: "GameUrl",
    1801: "ShopGlanceView",
    1901: "BuildingUpgradeStarted",
    1902: "BuildingUpgradeCompleted",
    2001: "ConsumableActivated",
    2002: "ConsumableExpired",
    2101: "Attack",
    2102: "TestAttack",
    2201: "Account",
    2301: "HeroSelected",
    2401: "CreatureUpgrade",
    2402: "TrapUpgrade",
    2501: "ShieldGameActivated",
    2502: "ShieldGameDeactivated",
    2601: "CreatureSpecialized",
    2701: "TrackingChatJoinRoom",
    2702: "TrackingChatLeaveRoom",
    2703: "TrackingChatMessageSent",
    2790: "ChatMuted",
    2801: "TrackingThemeApplied",
    2901: "FriendReferralSent",
    2902: "FriendReferralAccepted",
    2903: "FriendReferralRewarded",
    2904: "TrackingCastleRating",
    3001: "AvatarChanged",
    3101: "ForgeItemStarted",
    3102: "ForgeItemCompleted",
    3103: "ForgeItemCollected",
    3201: "LeaguePromoted",
    3202: "LeagueDemoted",
    3203: "LeagueLeaders",
    3204: "WorldLeaders",
}

# Spielbefehl (ServerCommandService.SendCommands) -> TrackingTagId
COMMAND_TAGS = {
    "StartAssignmentCommand": 150,          # AssignmentStarted
    "CompleteAssignmentCommand": 151,       # AssignmentCompleted
    "BuyCommand": 501,                      # EconomicShop
    "BuyHeroItemCommand": 501,
    "BuyConsumableCommand": 501,
    "SellHeroItemCommand": 504,             # EconomicHeroItemSell
    "HarvestMineBuildingCommand": 523,      # EconomicMineHarvested
    "HarvestHeroCorpseCommand": 524,        # EconomicHeroCorpseHarvested
    "BuyBackCommand": 525,                  # EconomicItemBuyBack
    "SellDefenseIngredientCommand": 534,    # EconomicDefenseIngredientItemSold
    "ActivateConsumableCommand": 2001,      # ConsumableActivated
    "ActivateConsumableOnItemCommand": 2001,
    "SetAvatarCommand": 3001,               # AvatarChanged
}

# TrackingCommand-Tags des Clients, die ins Protokoll kommen (Chat: Raum
# betreten/verlassen, Anzahl gesendeter Nachrichten; der Text selbst wird
# nie getrackt). Der Rest (GameState u. ä.) wäre nur Rauschen.
CLIENT_COMMAND_TAGS = {2701, 2702, 2703}

# Server-Meldung an den Spieler -> TrackingTagId
NOTIFICATION_TAGS = {
    "CastleAttacked": 521,                  # EconomicDefenderLoss (Verteidiger)
    "FriendshipAdded": 603,                 # FriendshipInvitationAccepted (beide Seiten)
    "FriendshipRemoved": 605,               # beim Entfernten
    "DraftValidated": 801,                  # PublishedCastle
    "HeroInventoryAdded": 904,              # ItemAdded
    "ObjectiveUnlocked": 1101,
    "ObjectiveCompleted": 1102,
    "AchievementCompleted": 1201,
    "CastleLevelUp": 1301,
    "BuildingUpgradeStarted": 1901,
    "BuildingUpgradeCompleted": 1902,
    "ConsumableActivated": 2001,
    "ShieldAdded": 2501,                    # ShieldGameActivated
    "ShieldExpired": 2502,                  # ShieldGameDeactivated
    "HeroSelected": 2301,
    "ThemeSelected": 2801,                  # TrackingThemeApplied
    "ForgeStarted": 3101,                   # ForgeItemStarted
    "ForgeItemReady": 3102,                 # ForgeItemCompleted
    "ForgeItemCollected": 3103,
}

WALLET_FIELDS = ("InGameCoin", "LifeForce", "PremiumCash")

KEEP = 50_000


def notification_tag(type_name, fields):
    """TrackingTagId einer Server-Meldung oder None."""
    if type_name == "HeroXpChanged":
        return HERO_LEVEL_UP if fields.get("LevelChanged") else None
    return NOTIFICATION_TAGS.get(type_name)


def _object_id(now):
    """MongoDB-ObjectId als Hex (TagId): Sekunden + Zufall, nach Zeit sortierbar."""
    return "%08x%s" % (int(now.timestamp()), secrets.token_hex(8))


class Tracker:
    def __init__(self, directory):
        self.dir = directory
        self.lock = threading.Lock()
        self.entries = collections.deque(maxlen=KEEP)
        # neueste Monate rückwärts, bis KEEP Ereignisse beisammen sind
        loaded = []
        for path in sorted(glob.glob(os.path.join(directory, "tracking-*.jsonl")),
                           reverse=True):
            with open(path, encoding="utf-8") as f:
                month = []
                for line in f:
                    try:
                        month.append(json.loads(line))
                    except ValueError:
                        pass
            loaded[:0] = month
            if len(loaded) >= KEEP:
                break
        self.entries.extend(loaded[-KEEP:])

    def _path(self, now):
        return os.path.join(self.dir, now.strftime("tracking-%Y-%m.jsonl"))

    def track(self, account_id, tag, fields=None):
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = {"TagId": _object_id(now), "TrackingTagId": int(tag),
                 "AccountId": int(account_id or 0),
                 "CreationDate": now.isoformat(timespec="seconds").replace("+00:00", "Z")}
        for k, v in (fields or {}).items():
            if k not in ("$type", "TrackingTagId", "AccountId", "TagId"):
                entry[k] = v
        with self.lock:
            self.entries.append(entry)
            with open(self._path(now), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def track_client(self, account_id, body):
        """TrackingService.Track/TrackBatch: jedes Tracking-Objekt im Body
        (Track: "tracking", TrackBatch: Liste) mit seiner TrackingTagId."""
        items = []
        for v in (body or {}).values() if isinstance(body, dict) else ():
            items.extend(v if isinstance(v, list) else [v])
        for t in items:
            if not isinstance(t, dict) or not t.get("TrackingTagId"):
                continue
            # Launcher-Ablauf bei jedem Start: nur behalten, wenn ein Schritt scheiterte
            if t["TrackingTagId"] == LAUNCHER_STATE_MACHINE and all(
                    s.get("Successful", True) for s in t.get("States") or []):
                continue
            fields = dict(t)
            fields["ClientType"] = (t.get("$type") or "").split(",")[0].split(".")[-1]
            self.track(account_id, t["TrackingTagId"], fields)

    def remove(self, account_id, tags=None):
        """Ereignisse eines Accounts mit diesen Tags (None: alle) löschen, im
        Speicher und in den Monatsdateien (Admin: Cheat-Verdacht zurücksetzen,
        Account löschen); Anzahl."""
        drop = lambda e: e.get("AccountId") == account_id and (
            tags is None or e.get("TrackingTagId") in tags)
        removed = 0
        with self.lock:
            kept = [e for e in self.entries if not drop(e)]
            self.entries.clear()
            self.entries.extend(kept)
            for path in glob.glob(os.path.join(self.dir, "tracking-*.jsonl")):
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
                out = []
                for line in lines:
                    try:
                        if drop(json.loads(line)):
                            removed += 1
                            continue
                    except ValueError:
                        pass
                    out.append(line)
                if len(out) != len(lines):
                    with open(path + ".tmp", "w", encoding="utf-8") as f:
                        f.writelines(out)
                    os.replace(path + ".tmp", path)
        return removed

    def latest_by_account(self, tags):
        """Ereignisse der Tags je AccountId, neueste zuerst, in einem
        Durchlauf (Übersicht über alle Accounts; latest je Account liefe
        jedes Mal über alle Einträge)."""
        tags, out = set(tags), {}
        with self.lock:
            for e in reversed(self.entries):
                if e["TrackingTagId"] in tags:
                    out.setdefault(e["AccountId"], []).append(dict(e))
        return out

    def latest(self, account_ids, tags, max_size):
        """GetLatestTrackedData: neueste zuerst, gefiltert nach Accounts
        (leer = alle) und Tags, höchstens max_size; als JSON-Strings."""
        accounts, tags = set(account_ids or ()), set(tags or ())
        out = []
        with self.lock:
            for e in reversed(self.entries):
                if len(out) >= max_size:
                    break
                if e["TrackingTagId"] in tags and (not accounts or e["AccountId"] in accounts):
                    out.append(json.dumps(e, ensure_ascii=False))
        return out
