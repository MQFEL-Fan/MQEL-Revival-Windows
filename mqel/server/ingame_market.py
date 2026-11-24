"""Ingame Market: player market inside the game (UI: ui_mods/ingame_market.html,
ui_patches 16.; guide: docs/87-ingame-market.md).

- Equipment and Weapons: one listing per item with a starting bid, an
  optional buy-now price and a duration. Bids hold the bidder's money; an
  outbid player gets it back. When the time is up the highest bidder gets
  the item; without bids it goes back to the seller.
- Items (materials, dyes): no auctions. Sell orders (lowest price first)
  and buy orders (highest price first) like the Steam market; a new order
  that meets the other side trades at once at the waiting order's price.
- Prices in gold or blings, chosen by the seller (buy orders: by the buyer).
- 1% fee on every sale, paid by the seller (rounded, nothing below 50).
- Everything a player gets (bought items, money from sales, refunds,
  returned items) goes to their collect box; "Collect" moves it into the
  inventory/wallet (gold up to the storage capacity). Taking items out of
  the inventory and paying happen at once and are sent to the running
  client as inventory/wallet notifications.
- Unlocked after the castle crafting tutorial (assignment 5007), at any hero
  level.

Access: the game UI calls /market/session?a=<AccountId> from the IP of the
account's last game request (like the friend online dots) and gets a web
token for the other calls; the in-game Bling shop uses the same token.
State: <state>/ingame_market.json (written atomically).
"""
import copy
import datetime
import json
import os
import secrets
import threading
import time

import account_state
import castles
import loot

T = castles.T
CURRENCIES = {"gold": "InGameCoin", "bling": "PremiumCash"}
FEE_PERCENT = 1
DURATIONS_H = (12, 24, 48)
MIN_INCREMENT = 0.05            # next bid at least +5% (and +1)
MAX_PRICE = 100_000_000
MAX_LISTINGS = 20               # open listings + orders per player
UNLOCK_ASSIGNMENT = 5007        # Castle_Crafting_1st_Floor_Complete
HISTORY_MAX = 2000
LOG_MAX = 5000
SESSION_TTL = 12 * 3600
SESSION_IDLE = 300              # last game request at most 5 min ago

CLASS_TYPES = {
    "knight": {1, 2, 3, 4, 5, 6, 27}, "mage": {9, 10, 11, 12, 13, 14, 29},
    "archer": {15, 16, 17, 18, 19, 20, 28}, "runaway": {21, 22, 23, 24, 25, 26, 30},
}
CLASS_NAMES = {"knight": "Knight", "archer": "Archer", "mage": "Mage", "runaway": "Runaway",
               "all": "All classes"}
QUALITIES = ("Basic", "Magic", "Exceptional", "Legendary", "Epic")
MATERIAL_TYPES = ("CraftingMaterialConsumableTemplate", "DyeConsumableTemplate")


class GEError(ValueError):
    pass


def _now():
    return time.time()


def fee(total):
    return (total * FEE_PERCENT + 50) // 100


# -- game data ----------------------------------------------------------------

class Catalog:
    """Names, icons, classes of items (from the gameplay settings)."""

    def __init__(self):
        self.data = account_state.GameData()
        self._types = {t["Id"]: t for t in account_state._load_json(os.path.join(
            loot.SETTINGS, "HeroItems", "HeroItemTypes.json"))["ItemTypeList"]}
        try:
            with open(os.path.join(loot.SETTINGS, "Oasis", "OASIS_EN.JSON"), encoding="utf-8-sig") as f:
                self._text = json.load(f)["Translations"]
        except (OSError, ValueError, KeyError):
            self._text = {}
        import item_drops  # noqa: PLC0415
        self._props = item_drops._magical_properties()
        counts = item_drops._effect_counts()
        self._quality_by_count = sorted(((n, q) for q, n in counts.items()), reverse=True)

    def text(self, oasis_id, default=""):
        return self._text.get(str(oasis_id), default) if oasis_id else default

    def item_class(self, template):
        tid = template.get("HeroItemTypeId")
        return next((c for c, ids in CLASS_TYPES.items() if tid in ids), "all")

    def category(self, template):
        t = self._types.get(template.get("HeroItemTypeId"), {})
        return "weapon" if t.get("HeroItemCategoryType") == "Weapon" else "equipment"

    def quality(self, item):
        n = len(item.get("Effects") or [])  # like the game: every effect counts
        return next((q for c, q in self._quality_by_count if n >= c), "Basic")

    def describe_item(self, item):
        t = self.data.templates.get(item.get("TemplateId"), {})
        typ = self._types.get(t.get("HeroItemTypeId"), {})
        effects, info = [], []
        for e in item.get("Effects") or []:
            p = self._props.get(e.get("Id"), {})
            name = self.text(p.get("OasisName"), p.get("DebugName") or "Bonus")
            level = e.get("Level", 1)
            label = "%s %s" % (name, "I II III IV V VI VII VIII".split()[min(7, max(0, level - 1))])
            effects.append(label)
            info.append({"Name": label, "Text": self.effect_text(p, level)})
        return {"EffectInfo": info, "RequiredLevel": t.get("RequiredLevel") or item.get("ItemLevel", 1),
                "Name": self.text(t.get("OasisID"), t.get("InternalDescription", "Item")),
                "Type": self.text(typ.get("OasisID"), typ.get("InternalDescription", "")),
                "Icon": _icon(t.get("InvIconUrl")), "Level": item.get("ItemLevel", 1),
                "Quality": self.quality(item), "Class": self.item_class(t),
                "Category": self.category(t), "Effects": effects, "TemplateId": item.get("TemplateId")}

    def effect_text(self, prop, level):
        """Effect description like the game's tooltip: {0} = BaseValue +
        ValuePerLevel x level ("Magic Find III": 0.04 + 0.02 x 3 = +10%)."""
        text = self.text(prop.get("OasisDescription"), "")
        if not text:
            return ""
        v = (prop.get("BaseValue") or 0) + (prop.get("ValuePerLevel") or 0) * level
        if prop.get("FormatValueAsPercentage"):
            n = round(v * 100, 1)
            value = "+%s%%" % (int(n) if n == int(n) else n)
        else:
            n = round(v, 2)
            value = str(int(n) if n == int(n) else n)
        return text.replace("{0}", value)

    def consumable_name(self, template_id):
        c = self.data.consumables.get(template_id) or {}
        name = c.get("Name") or {}
        return self.text(name.get("OasisName"), name.get("DebugName", ""))

    def material(self, template_id):
        c = self.data.consumables.get(template_id)
        if not c or c["$type"].split(",")[0].split(".")[-1] not in MATERIAL_TYPES:
            return None
        debug = ((c.get("Name") or {}).get("DebugName") or "").lower()
        if "tutorial" in debug or "test" in debug or not c.get("IsLootable", True):
            return None
        return c

    def describe_material(self, template_id):
        c = self.material(template_id) or {}
        name = c.get("Name") or {}
        return {"TemplateId": template_id, "Name": self.text(name.get("OasisName"), name.get("DebugName", "Item")),
                "Icon": _icon((c.get("Ui") or {}).get("InvIconUrl")),
                "Kind": "Dye" if "Dye" in c.get("$type", "") else "Material",
                "StackMax": c.get("MaxInventoryStackCount") or 999}

    def stack_max(self, template_id):
        return (self.data.consumables.get(template_id) or {}).get("MaxInventoryStackCount") or 999

    def materials(self):
        return sorted((t for t in self.data.consumables if self.material(t)))


class _Rev:
    """Inverted string order for sort keys (name Z-A)."""
    __slots__ = ("s",)

    def __init__(self, s):
        self.s = s

    def __lt__(self, other):
        return self.s > other.s

    def __eq__(self, other):
        return self.s == other.s


def _icon(url):
    """Inventory icon, relative to Generated/Web (served by /market/icon/<path>:
    the players' game has no web copy of most item icons)."""
    if not url:
        return ""
    url = url.replace("\\", "/")
    if not url.lower().endswith(".png"):
        url += ".png"
    return url.upper()


ICON_ROOT = os.path.join(account_state.ROOT, "client", "GameData", "Data", "Generated", "Web")


def icon_file(rel):
    """Local file for /market/icon/<rel> or None (only PNGs below ICON_ROOT)."""
    rel = (rel or "").replace("\\", "/").strip("/")
    if not rel.upper().endswith(".PNG") or ".." in rel.split("/"):
        return None
    path = os.path.realpath(os.path.join(ICON_ROOT, *rel.split("/")))
    root = os.path.realpath(ICON_ROOT)
    if not path.startswith(root + os.sep) or not os.path.isfile(path):
        return None
    return path


# -- market -------------------------------------------------------------------

class Market:
    def __init__(self, state_dir, players, log=print):
        self.path = os.path.join(state_dir, "ingame_market.json")
        # servers from before the rename kept the market in grand_exchange.json
        old = os.path.join(state_dir, "grand_exchange.json")
        if not os.path.exists(self.path) and os.path.exists(old):
            os.replace(old, self.path)
        self.players = players
        self.log = log
        self.lock = threading.RLock()
        self.catalog = Catalog()
        self.sessions = {}  # web token -> (account id, expires)
        try:
            with open(self.path, encoding="utf-8") as f:
                self.db = json.load(f)
        except (OSError, ValueError):
            self.db = {}
        for key, default in (("NextId", 1), ("Listings", {}), ("BuyOrders", {}),
                             ("Collect", {}), ("History", []), ("Log", []), ("Fees", {})):
            self.db.setdefault(key, default)
        self._stop = threading.Event()
        threading.Thread(target=self._sweeper, name="ingame-market", daemon=True).start()

    # -- persistence / helpers --

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def _id(self):
        i = self.db["NextId"]
        self.db["NextId"] = i + 1
        return str(i)

    def _box(self, account_id):
        return self.db["Collect"].setdefault(str(account_id), {"Items": [], "InGameCoin": 0, "PremiumCash": 0})

    def _credit_box(self, account_id, field=None, amount=0, item=None, count=1, note=""):
        box = self._box(account_id)
        if field and amount:
            box[field] = box.get(field, 0) + amount
        if item is not None:
            if item.get("$type") == T("HeroConsumableItem"):
                same = next((e for e in box["Items"] if e["Item"].get("$type") == T("HeroConsumableItem")
                             and e["Item"]["TemplateId"] == item["TemplateId"]), None)
                if same:
                    same["Count"] += count
                    return
            box["Items"].append({"Item": item, "Count": count, "Note": note})

    def _history(self, kind, template_id, qty, price, currency):
        h = self.db["History"]
        h.append({"Time": int(_now()), "Kind": kind, "TemplateId": template_id,
                  "Qty": qty, "Price": price, "Currency": currency})
        del h[:-HISTORY_MAX]

    def _log(self, event, player, other=None, name="", qty=1, price=0, currency="", fee_=0, ref=""):
        """Ingame Market log for the admin tool (newest last, LOG_MAX)."""
        self.db["Log"].append({"Time": int(_now()), "Event": event, "Player": int(player) if player else None,
                               "Other": int(other) if other else None, "Item": name, "Qty": qty,
                               "Price": price, "Currency": currency, "Fee": fee_, "Ref": ref})
        del self.db["Log"][:-LOG_MAX]
        if fee_:
            self.db["Fees"][currency] = self.db["Fees"].get(currency, 0) + fee_

    def _item_name(self, x):
        return (self.catalog.describe_item(x["Item"])["Name"] if x["Kind"] == "item"
                else self.catalog.describe_material(x["TemplateId"])["Name"])

    def _player(self, account_id):
        p = self.players.by_account_id(int(account_id))
        if p is None:
            raise GEError("Unknown player.")
        return p

    @staticmethod
    def _push(p, events=(), wallet=None):
        import notifications  # noqa: PLC0415
        for name, fields in events:
            p.notifications.push(name, fields)
        if wallet:
            notifications.wallet_updated(p.notifications, wallet)

    def _name(self, account_id):
        p = self.players.by_account_id(int(account_id))
        return (p.state.snapshot().get("DisplayName") if p else "") or "?"

    def _open_count(self, account_id):
        a = int(account_id)
        return (sum(1 for x in self.db["Listings"].values() if x["Seller"] == a)
                + sum(1 for x in self.db["BuyOrders"].values() if x["Buyer"] == a))

    @staticmethod
    def _price(value):
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise GEError("Enter a price.")
        if not 1 <= v <= MAX_PRICE:
            raise GEError("Price must be between 1 and %s." % format(MAX_PRICE, ","))
        return v

    @staticmethod
    def _currency(value):
        if value not in CURRENCIES:
            raise GEError("Choose gold or blings.")
        return value

    # -- access --

    def unlocked(self, account):
        return UNLOCK_ASSIGNMENT in (account.get("CompletedAssignments") or [])

    def session(self, account_id, ip):
        """Web token for the UI of this account (None: not allowed)."""
        import ipaddress  # noqa: PLC0415
        p = next((x for x in list(self.players.players.values()) if x.account_id == account_id), None)
        if p is None:
            print(f"    [market] session refused: account {account_id} not loaded (from {ip})", flush=True)
            return None
        try:
            local = ipaddress.ip_address(ip).is_loopback
        except ValueError:
            local = False
        seen = getattr(p, "presence_seen", 0) or 0
        game_ip = getattr(p, "presence_ip", None)
        if not local and (game_ip != ip or _now() - seen > SESSION_IDLE):
            print(f"    [market] session refused: {p.name}: UI from {ip}, game from {game_ip}, "
                  f"last game request {int(_now() - seen)} s ago", flush=True)
            return None
        now = _now()
        with self.lock:
            # several windows of the same game (Ingame Market, party) each
            # hold a token; keep at most 4 per account
            mine = sorted((exp, t) for t, (aid, exp) in self.sessions.items() if aid == account_id)
            for exp, t in mine[:-3]:
                del self.sessions[t]
            for t, (aid, exp) in list(self.sessions.items()):
                if exp < now:
                    del self.sessions[t]
            token = secrets.token_urlsafe(18)
            self.sessions[token] = (account_id, now + SESSION_TTL)
        return token

    def account_for(self, token):
        entry = self.sessions.get(token or "")
        if not entry or entry[1] < _now():
            return None
        return entry[0]

    def player_for(self, token):
        aid = self.account_for(token)
        return self.players.by_account_id(aid) if aid else None

    # -- views --

    def overview(self, account_id):
        self.sweep()
        p = self._player(account_id)
        a = p.state.snapshot()
        aid = int(account_id)
        with self.lock:
            box = copy.deepcopy(self.db["Collect"].get(str(aid)) or {"Items": [], "InGameCoin": 0, "PremiumCash": 0})
            mine = [self._listing_view(x, aid) for x in self.db["Listings"].values() if x["Seller"] == aid]
            bids = [self._listing_view(x, aid) for x in self.db["Listings"].values()
                    if (x.get("Bid") or {}).get("Bidder") == aid]
            orders = [self._order_view(x) for x in self.db["BuyOrders"].values() if x["Buyer"] == aid]
        inventory = []
        for s in sorted(a["Inventory"]["HeroItems"], key=lambda s: s["SlotIndex"]):
            item = s["Item"]
            if item.get("$type") == T("HeroEquipmentItem"):
                if item.get("IsSellable") is False:
                    continue
                d = self.catalog.describe_item(item)
                d.update(Slot=s["SlotIndex"], Count=1, Kind="item")
                inventory.append(d)
            elif self.catalog.material(item.get("TemplateId")):
                d = self.catalog.describe_material(item["TemplateId"])
                d.update(Slot=s["SlotIndex"], Count=s["StackCount"], Kind="material")
                inventory.append(d)
        items = []
        for e in box["Items"]:
            it = e["Item"]
            d = (self.catalog.describe_material(it["TemplateId"]) if it.get("$type") == T("HeroConsumableItem")
                 else self.catalog.describe_item(it))
            d.update(Count=e.get("Count", 1), Note=e.get("Note", ""))
            items.append(d)
        return {"Unlocked": self.unlocked(a), "Gold": a["Wallet"]["InGameCoin"],
                "Blings": a["Wallet"]["PremiumCash"], "Fee": FEE_PERCENT,
                "Durations": DURATIONS_H, "MaxListings": MAX_LISTINGS,
                "Collect": {"Items": items, "Gold": box.get("InGameCoin", 0), "Blings": box.get("PremiumCash", 0)},
                "MyListings": sorted(mine, key=lambda x: -x["Created"]),
                "MyBids": bids, "MyOrders": orders, "Inventory": inventory,
                "Classes": CLASS_NAMES}

    def _listing_view(self, x, viewer):
        d = dict(self.catalog.describe_item(x["Item"])) if x["Kind"] == "item" \
            else dict(self.catalog.describe_material(x["TemplateId"]))
        bid = x.get("Bid") or {}
        d.update(Id=x["Id"], Kind=x["Kind"], Currency=x["Currency"], Created=x["Created"],
                 Seller=self._name(x["Seller"]), Mine=x["Seller"] == viewer)
        if x["Kind"] == "item":
            d.update(StartPrice=x["StartPrice"], BuyNow=x.get("BuyNow"), Ends=x["Ends"],
                     Bid=bid.get("Amount"), Bids=x.get("Bids", 0),
                     MinBid=self._min_bid(x), Leading=bid.get("Bidder") == viewer)
        else:
            d.update(Price=x["Price"], Qty=x["Qty"])
        return d

    def _order_view(self, x):
        d = dict(self.catalog.describe_material(x["TemplateId"]))
        d.update(Id=x["Id"], Kind="buyorder", Currency=x["Currency"], Price=x["Price"],
                 Qty=x["Qty"], Created=x["Created"])
        return d

    @staticmethod
    def _min_bid(x):
        bid = (x.get("Bid") or {}).get("Amount")
        if not bid:
            return x["StartPrice"]
        return bid + max(1, int(bid * MIN_INCREMENT + 0.999))

    def items_market(self, viewer, category, klass="", search="", currency="", sort="ending", desc=False):
        self.sweep()
        search = (search or "").strip().lower()
        with self.lock:
            out = []
            for x in self.db["Listings"].values():
                if x["Kind"] != "item":
                    continue
                d = self._listing_view(x, int(viewer))
                if category and d["Category"] != category:
                    continue
                if klass and klass != "any" and d["Class"] not in (klass, "all"):
                    continue
                if currency and x["Currency"] != currency:
                    continue
                if search and search not in d["Name"].lower() and search not in d["Type"].lower():
                    continue
                out.append(d)
        keys = {"ending": lambda d: d["Ends"], "newest": lambda d: -d["Created"],
                "price": lambda d: (d["Currency"], d["Bid"] or d["StartPrice"]),
                "level": lambda d: -d["Level"]}
        out.sort(key=keys.get(sort, keys["ending"]), reverse=bool(desc))
        return out[:200]

    # -- inventory sort (lobby inventory, ui_mods/lobby_mods.html) --
    QUALITY_RANK = {"Basic": 0, "Magic": 1, "Exceptional": 2, "Legendary": 3, "Epic": 4}
    SORTS = ("type", "quality", "level", "name")

    def _sort_key(self, by, desc):
        """key(slot) for AccountState.sort_inventory_tab. Defaults: type
        (weapons, equipment, potions and other consumables, materials, dyes),
        quality best first, level highest first, name A-Z; desc inverts."""
        cat = self.catalog
        sign = -1 if desc else 1

        def info(s):
            item = s["Item"]
            if item.get("$type") == T("HeroEquipmentItem"):
                d = cat.describe_item(item)
                group = 0 if d["Category"] == "weapon" else 1
                return group, self.QUALITY_RANK.get(d["Quality"], 0), d["Level"], d["Name"], d["Class"]
            tid = item.get("TemplateId")
            if cat.material(tid):
                d = cat.describe_material(tid)
                group = 4 if d["Kind"] == "Dye" else 3
                return group, -1, 0, d["Name"], ""
            return 2, -1, 0, cat.consumable_name(tid) or str(tid), ""

        def key(s):
            group, q, level, name, klass = info(s)
            name = name.lower()
            if by == "quality":
                return (-q * sign, group, -level, name)
            if by == "level":
                return (-level * sign, group, -q, name)
            if by == "name":
                return (_Rev(name) if desc else name, group)
            return (group * sign, klass, -q, -level, name)
        return key

    def sort_inventory(self, account_id, tab, by="type", desc=False):
        by = by if by in self.SORTS else "type"
        p = self._player(account_id)
        events = p.state.sort_inventory_tab(int(tab), self._sort_key(by, bool(desc)))
        self._push(p, events)
        return {"Sorted": True, "Tab": int(tab), "By": by, "Desc": bool(desc), "Reload": bool(events)}

    def materials_market(self, search=""):
        """One row per material and currency: lowest ask, highest bid, depth."""
        self.sweep()
        search = (search or "").strip().lower()
        rows = {}
        with self.lock:
            for x in self.db["Listings"].values():
                if x["Kind"] != "material":
                    continue
                r = rows.setdefault((x["TemplateId"], x["Currency"]), {"Asks": [], "Bids": []})
                r["Asks"].append((x["Price"], x["Qty"]))
            for x in self.db["BuyOrders"].values():
                r = rows.setdefault((x["TemplateId"], x["Currency"]), {"Asks": [], "Bids": []})
                r["Bids"].append((x["Price"], x["Qty"]))
            last = {}
            for h in self.db["History"]:
                if h["Kind"] == "material":
                    last[(h["TemplateId"], h["Currency"])] = h["Price"]
        out = []
        for tid in self.catalog.materials():
            d = self.catalog.describe_material(tid)
            if search and search not in d["Name"].lower():
                continue
            for cur in CURRENCIES:
                r = rows.get((tid, cur))
                if not r and (tid, cur) not in last:
                    continue
                asks = sorted(_depth(r["Asks"])) if r else []
                bids = sorted(_depth(r["Bids"]), reverse=True) if r else []
                out.append(dict(d, Currency=cur, LowestAsk=asks[0][0] if asks else None,
                                ForSale=sum(q for _, q in asks), HighestBid=bids[0][0] if bids else None,
                                Wanted=sum(q for _, q in bids), Asks=asks[:6], BidsDepth=bids[:6],
                                Last=last.get((tid, cur))))
        out.sort(key=lambda d: (d["LowestAsk"] is None, d["Name"]))
        return {"Rows": out, "All": [self.catalog.describe_material(t) for t in self.catalog.materials()]}

    # -- actions: equipment / weapons --

    def sell_item(self, account_id, slot, start, buy_now, currency, hours):
        currency = self._currency(currency)
        start = self._price(start)
        buy_now = self._price(buy_now) if buy_now not in (None, "", 0, "0") else None
        if buy_now is not None and buy_now < start:
            raise GEError("The buy-now price must be at least the starting bid.")
        if int(hours) not in DURATIONS_H:
            raise GEError("Choose a duration.")
        p = self._player(account_id)
        with self.lock:
            if not self.unlocked(p.state.snapshot()):
                raise GEError("Finish the castle crafting tutorial first.")
            if self._open_count(account_id) >= MAX_LISTINGS:
                raise GEError("You have %d open listings and orders already." % MAX_LISTINGS)
            item, events = p.state.market_take_item(int(slot))
            lid = self._id()
            self.db["Listings"][lid] = {
                "Id": lid, "Kind": "item", "Seller": int(account_id), "Item": item,
                "TemplateId": item["TemplateId"], "Currency": currency, "StartPrice": start,
                "BuyNow": buy_now, "Created": int(_now()), "Ends": int(_now() + int(hours) * 3600),
                "Bid": None, "Bids": 0}
            self._log("listed", account_id, name=self._item_name(self.db["Listings"][lid]),
                      price=start, currency=currency, ref=lid)
            self._save()
        self._push(p, events)
        self.log(f"    [market] {p.name!r} lists item {item['TemplateId']} (#{lid}) from {start} {currency}")
        return {"Id": lid}

    def bid(self, account_id, listing_id, amount):
        amount = self._price(amount)
        p = self._player(account_id)
        aid = int(account_id)
        with self.lock:
            x = self.db["Listings"].get(str(listing_id))
            if not x or x["Kind"] != "item" or x["Ends"] <= _now():
                raise GEError("This listing has ended.")
            if x["Seller"] == aid:
                raise GEError("You can't bid on your own item.")
            if (x.get("Bid") or {}).get("Bidder") == aid:
                raise GEError("You already have the highest bid.")
            if x.get("BuyNow") and amount >= x["BuyNow"]:
                return self.buy_now(account_id, listing_id)
            if amount < self._min_bid(x):
                raise GEError("Bid at least %s." % format(self._min_bid(x), ","))
            field = CURRENCIES[x["Currency"]]
            wallet = p.state.market_pay(field, amount)
            old = x.get("Bid")
            if old:
                self._credit_box(old["Bidder"], field, old["Amount"])
            x["Bid"] = {"Bidder": aid, "Amount": amount, "Time": int(_now())}
            x["Bids"] = x.get("Bids", 0) + 1
            # a bid in the last 2 minutes extends the auction (no sniping)
            x["Ends"] = max(x["Ends"], int(_now()) + 120)
            self._log("bid", aid, x["Seller"], self._item_name(x), price=amount, currency=x["Currency"], ref=x["Id"])
            self._save()
        self._push(p, wallet=wallet)
        return {"Bid": amount}

    def buy_now(self, account_id, listing_id):
        p = self._player(account_id)
        aid = int(account_id)
        with self.lock:
            x = self.db["Listings"].get(str(listing_id))
            if not x or x["Kind"] != "item" or x["Ends"] <= _now():
                raise GEError("This listing has ended.")
            if not x.get("BuyNow"):
                raise GEError("This item has no buy-now price.")
            if x["Seller"] == aid:
                raise GEError("You can't buy your own item.")
            field = CURRENCIES[x["Currency"]]
            price = x["BuyNow"]
            wallet = p.state.market_pay(field, price)
            old = x.get("Bid")
            if old:
                self._credit_box(old["Bidder"], field, old["Amount"])
            self._settle(x, aid, price)
            self._save()
        self._push(p, wallet=wallet)
        return {"Bought": True}

    def _settle(self, x, buyer, price):
        """Item listing sold (lock held, money already taken from the buyer)."""
        field = CURRENCIES[x["Currency"]]
        self._credit_box(buyer, item=x["Item"], note="Bought")
        self._credit_box(x["Seller"], field, price - fee(price))
        self._history("item", x["TemplateId"], 1, price, x["Currency"])
        self._log("sold", x["Seller"], buyer, self._item_name(x), price=price, currency=x["Currency"],
                  fee_=fee(price), ref=x["Id"])
        del self.db["Listings"][x["Id"]]
        self.log(f"    [market] #{x['Id']} sold to {buyer} for {price} {x['Currency']}")

    def cancel(self, account_id, listing_id):
        aid = int(account_id)
        with self.lock:
            lid = str(listing_id)
            x = self.db["Listings"].get(lid)
            if x and x["Seller"] == aid:
                if x["Kind"] == "item":
                    if x.get("Bid"):
                        raise GEError("Someone has bid on it: it can't be cancelled.")
                    self._credit_box(aid, item=x["Item"], note="Cancelled")
                    self._log("cancelled", aid, name=self._item_name(x), ref=lid)
                else:
                    self._log("cancelled", aid, name=self._item_name(x), qty=x["Qty"], price=x["Price"],
                              currency=x["Currency"], ref=lid)
                    self._credit_box(aid, item=_material(x["TemplateId"]), count=x["Qty"], note="Cancelled")
                del self.db["Listings"][lid]
            else:
                o = self.db["BuyOrders"].get(lid)
                if not o or o["Buyer"] != aid:
                    raise GEError("Not found.")
                self._credit_box(aid, CURRENCIES[o["Currency"]], o["Price"] * o["Qty"])
                self._log("order cancelled", aid, name=self.catalog.describe_material(o["TemplateId"])["Name"],
                          qty=o["Qty"], price=o["Price"], currency=o["Currency"], ref=lid)
                del self.db["BuyOrders"][lid]
            self._save()
        return {"Cancelled": True}

    # -- actions: materials (order book) --

    def sell_material(self, account_id, template_id, qty, price, currency):
        currency = self._currency(currency)
        price = self._price(price)
        template_id, qty = int(template_id), int(qty)
        if not self.catalog.material(template_id):
            raise GEError("This item can't be traded.")
        if qty < 1:
            raise GEError("Enter a quantity.")
        p = self._player(account_id)
        aid = int(account_id)
        with self.lock:
            if not self.unlocked(p.state.snapshot()):
                raise GEError("Finish the castle crafting tutorial first.")
            events = p.state.market_take_material(template_id, qty)
            field, sold, left = CURRENCIES[currency], 0, qty
            for o in sorted((o for o in self.db["BuyOrders"].values()
                             if o["TemplateId"] == template_id and o["Currency"] == currency
                             and o["Price"] >= price and o["Buyer"] != aid),
                            key=lambda o: (-o["Price"], o["Created"])):
                n = min(left, o["Qty"])
                total = n * o["Price"]
                self._credit_box(o["Buyer"], item=_material(template_id), count=n, note="Bought")
                self._credit_box(aid, field, total - fee(total))
                self._history("material", template_id, n, o["Price"], currency)
                self._log("sold", aid, o["Buyer"], self.catalog.describe_material(template_id)["Name"], qty=n,
                          price=o["Price"], currency=currency, fee_=fee(total), ref=o["Id"])
                o["Qty"] -= n
                left -= n
                sold += n
                if o["Qty"] <= 0:
                    del self.db["BuyOrders"][o["Id"]]
                if not left:
                    break
            lid = None
            if left:
                if self._open_count(aid) >= MAX_LISTINGS:
                    self._credit_box(aid, item=_material(template_id), count=left, note="Not listed")
                else:
                    lid = self._id()
                    self.db["Listings"][lid] = {"Id": lid, "Kind": "material", "Seller": aid,
                                                "TemplateId": template_id, "Qty": left, "Price": price,
                                                "Currency": currency, "Created": int(_now())}
                    self._log("listed", aid, name=self.catalog.describe_material(template_id)["Name"],
                              qty=left, price=price, currency=currency, ref=lid)
            self._save()
        self._push(p, events)
        return {"Sold": sold, "Listed": left if lid else 0}

    def buy_material(self, account_id, template_id, qty, price, currency):
        """Buy up to qty at most `price` each; the rest stays as a buy order."""
        currency = self._currency(currency)
        price = self._price(price)
        template_id, qty = int(template_id), int(qty)
        if not self.catalog.material(template_id):
            raise GEError("This item can't be traded.")
        if not 1 <= qty <= 9999:
            raise GEError("Enter a quantity (1-9999).")
        p = self._player(account_id)
        aid = int(account_id)
        field = CURRENCIES[currency]
        with self.lock:
            if not self.unlocked(p.state.snapshot()):
                raise GEError("Finish the castle crafting tutorial first.")
            wallet = p.state.market_pay(field, price * qty)
            bought, left, refund = 0, qty, 0
            for x in sorted((x for x in self.db["Listings"].values()
                             if x["Kind"] == "material" and x["TemplateId"] == template_id
                             and x["Currency"] == currency and x["Price"] <= price and x["Seller"] != aid),
                            key=lambda x: (x["Price"], x["Created"])):
                n = min(left, x["Qty"])
                total = n * x["Price"]
                self._credit_box(x["Seller"], field, total - fee(total))
                refund += n * (price - x["Price"])
                self._history("material", template_id, n, x["Price"], currency)
                self._log("sold", x["Seller"], aid, self.catalog.describe_material(template_id)["Name"], qty=n,
                          price=x["Price"], currency=currency, fee_=fee(total), ref=x["Id"])
                x["Qty"] -= n
                left -= n
                bought += n
                if x["Qty"] <= 0:
                    del self.db["Listings"][x["Id"]]
                if not left:
                    break
            if bought:
                self._credit_box(aid, item=_material(template_id), count=bought, note="Bought")
            if left and self._open_count(aid) >= MAX_LISTINGS:
                refund += left * price
                left = 0
            if refund:
                self._credit_box(aid, field, refund)
            if left:
                oid = self._id()
                self.db["BuyOrders"][oid] = {"Id": oid, "Buyer": aid, "TemplateId": template_id,
                                             "Qty": left, "Price": price, "Currency": currency,
                                             "Created": int(_now())}
                self._log("buy order", aid, name=self.catalog.describe_material(template_id)["Name"],
                          qty=left, price=price, currency=currency, ref=oid)
            self._save()
        self._push(p, wallet=wallet)
        return {"Bought": bought, "Ordered": left}

    # -- collect box --

    def collect(self, account_id, which=None):
        """Collect box -> account: everything, or one entry (which = item
        index, "gold" or "blings"). The game reloads the account afterwards
        (FORCE_RELOAD), so the bag shows the new items at once."""
        p = self._player(account_id)
        with self.lock:
            full = self._box(account_id)
            box = full
            if which is not None:
                if which == "gold":
                    box = {"Items": [], "InGameCoin": full.get("InGameCoin", 0), "PremiumCash": 0}
                elif which == "blings":
                    box = {"Items": [], "InGameCoin": 0, "PremiumCash": full.get("PremiumCash", 0)}
                else:
                    i = int(which)
                    if not 0 <= i < len(full["Items"]):
                        raise GEError("Already collected.")
                    box = {"Items": [full["Items"][i]], "InGameCoin": 0, "PremiumCash": 0}
            # slots whose removal the game hasn't received yet still look used there
            avoid = {n.get("SlotIndex") for n in p.notifications.outgoing()
                     if n.get("NotificationType") in (38, "HeroInventoryRemoved")}
            left, gold_left, wallet, events = p.state.market_receive(
                box["Items"], box.get("InGameCoin", 0), box.get("PremiumCash", 0), self.catalog.stack_max, avoid)
            moved = len(box["Items"]) - len(left)
            if which is not None:  # write the single entry back into the full box
                if which == "gold":
                    full["InGameCoin"] = gold_left
                elif which == "blings":
                    full["PremiumCash"] = 0
                else:
                    i = int(which)
                    full["Items"][i:i + 1] = left
                box = full
            if moved or wallet:
                self._log("collected", account_id, name="%d item(s)" % moved, qty=moved,
                          price=wallet.get("InGameCoin", 0), currency="gold",
                          ref=("+%d blings" % wallet["PremiumCash"]) if wallet.get("PremiumCash") else "")
            if which is None:
                box.update(Items=left, InGameCoin=gold_left, PremiumCash=0)
            self._save()
        if moved or wallet:
            events = list(events) + [(p.state.FORCE_RELOAD, {})]
        self._push(p, events, wallet)
        return {"Items": moved, "ItemsLeft": len(left), "GoldLeft": gold_left,
                "Wallet": wallet}

    # -- time --

    def match_books(self):
        """Fill crossing material orders (highest buy >= lowest sell) at the
        older order's price. Lock held by the caller."""
        changed = False
        keys = {(x["TemplateId"], x["Currency"]) for x in self.db["Listings"].values() if x["Kind"] == "material"}
        for tid, cur in keys:
            field = CURRENCIES[cur]
            while True:
                asks = sorted((x for x in self.db["Listings"].values() if x["Kind"] == "material"
                               and x["TemplateId"] == tid and x["Currency"] == cur),
                              key=lambda x: (x["Price"], x["Created"]))
                bids = sorted((o for o in self.db["BuyOrders"].values()
                               if o["TemplateId"] == tid and o["Currency"] == cur),
                              key=lambda o: (-o["Price"], o["Created"]))
                pair = next(((a, b) for b in bids for a in asks
                             if b["Price"] >= a["Price"] and a["Seller"] != b["Buyer"]), None)
                if pair is None:
                    break
                a, b = pair
                price = a["Price"] if a["Created"] <= b["Created"] else b["Price"]
                n = min(a["Qty"], b["Qty"])
                total = n * price
                self._credit_box(b["Buyer"], item=_material(tid), count=n, note="Bought")
                self._credit_box(b["Buyer"], field, n * (b["Price"] - price))  # held at the order price
                self._credit_box(a["Seller"], field, total - fee(total))
                self._history("material", tid, n, price, cur)
                self._log("sold", a["Seller"], b["Buyer"], self.catalog.describe_material(tid)["Name"], qty=n,
                          price=price, currency=cur, fee_=fee(total), ref=a["Id"])
                for o, table in ((a, "Listings"), (b, "BuyOrders")):
                    o["Qty"] -= n
                    if o["Qty"] <= 0:
                        del self.db[table][o["Id"]]
                changed = True
        return changed

    def sweep(self):
        """End item auctions whose time is up, fill crossing orders."""
        now = _now()
        with self.lock:
            if self.match_books():
                self._save()
            done = [x for x in self.db["Listings"].values() if x["Kind"] == "item" and x["Ends"] <= now]
            for x in done:
                bid = x.get("Bid")
                if bid:
                    self._settle(x, bid["Bidder"], bid["Amount"])
                else:
                    self._credit_box(x["Seller"], item=x["Item"], note="Not sold")
                    self._log("expired", x["Seller"], name=self._item_name(x), ref=x["Id"])
                    del self.db["Listings"][x["Id"]]
            if done:
                self._save()

    def _sweeper(self):
        while not self._stop.wait(30):
            try:
                self.sweep()
            except Exception as e:  # noqa: BLE001 - keep the thread alive
                self.log(f"[market] sweep failed: {e}")

    def admin_view(self, limit=300):
        """Open offers, collect boxes and the log for the admin tool."""
        self.sweep()
        with self.lock:
            listings = [dict(self._listing_view(x, 0), SellerId=x["Seller"]) for x in self.db["Listings"].values()]
            orders = [dict(self._order_view(x), Buyer=self._name(x["Buyer"]), BuyerId=x["Buyer"])
                      for x in self.db["BuyOrders"].values()]
            boxes = [{"AccountId": int(a), "Name": self._name(a), "Items": len(b.get("Items") or []),
                      "Gold": b.get("InGameCoin", 0), "Blings": b.get("PremiumCash", 0)}
                     for a, b in self.db["Collect"].items()
                     if b.get("Items") or b.get("InGameCoin") or b.get("PremiumCash")]
            log = [dict(e, PlayerName=self._name(e["Player"]) if e.get("Player") else "",
                        OtherName=self._name(e["Other"]) if e.get("Other") else "")
                   for e in self.db["Log"][-int(limit):]][::-1]
            volume, trades = {}, 0
            for e in self.db["Log"]:
                if e["Event"] == "sold":
                    trades += 1
                    volume[e["Currency"]] = volume.get(e["Currency"], 0) + e["Price"] * e["Qty"]
            return {"Listings": listings, "Orders": orders, "Boxes": boxes, "Log": log,
                    "Fees": dict(self.db["Fees"]), "Volume": volume, "Trades": trades}

    def pending_collect(self, account_id):
        box = self.db["Collect"].get(str(account_id)) or {}
        return len(box.get("Items") or []) + (1 if box.get("InGameCoin") else 0) + (1 if box.get("PremiumCash") else 0)


def _material(template_id):
    return {"$type": T("HeroConsumableItem"), "TemplateId": int(template_id)}


def _depth(pairs):
    out = {}
    for price, qty in pairs:
        out[price] = out.get(price, 0) + qty
    return list(out.items())


# -- server notice (update countdown, ui_patches 16.) --------------------------

class Notice:
    """Planned server update: the UI shows a countdown and closes the game
    when it reaches 0 (game://pause/quitGame); the server ends sessions then."""

    def __init__(self, state_dir):
        self.path = os.path.join(state_dir, "server_notice.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        # a countdown whose time passed while the server was down (stopped
        # early with stop_servers.bat, or restarted at 0) is over: sent again
        # after the restart, it closed every game that reconnected within 10 min
        if self.data.get("At") and self.data["At"] <= _now():
            self.cancel()

    def get(self):
        at = self.data.get("At")
        if not at or at < _now() - 600:
            return {}
        return dict(self.data, Now=int(_now()))

    def schedule(self, minutes, message=""):
        at = int(_now() + float(minutes) * 60)
        self.data = {"At": at, "Message": message or "Server update",
                     "Iso": datetime.datetime.fromtimestamp(at, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        self._save()
        return self.get()

    def cancel(self):
        self.data = {}
        self._save()
        return {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
