# Ingame Market, in-game Bling shop and update countdown

Status: built and tested on a copy of the live data (2026-11-22). Goes live
with the next server restart; players get the UI from the launcher.
Code: `server/ingame_market.py`, `server/ui_mods/ingame_market.html`
(UI patch 16 in `server/ui_patches.py`), routes in `server/game_server.py`
(`_market`), inventory/wallet helpers `AccountState.market_*`.

**Renamed (2026-11-24):** this feature was first called "Grand Exchange".
Everything now uses the name **Ingame Market**:

| Before | Now |
|---|---|
| `server/grand_exchange.py`, class `Exchange` | `server/ingame_market.py`, class `Market` |
| `server/ui_mods/grand_exchange.html` | `server/ui_mods/ingame_market.html` |
| `docs/87-grand-exchange.md` | `docs/87-ingame-market.md` |
| routes `/ge/...` (session, items, icon, sort_inventory ...) | `/market/...` |
| element ids `mqel-ge-*`, `GE_BUTTON`/`GE_ANCHOR` | `mqel-market-*`, `MARKET_BUTTON`/`MARKET_ANCHOR` |
| `AccountState.ge_*`, `srv.ge`, admin API `GetExchange` | `AccountState.market_*`, `srv.market`, `GetMarket` |
| state file `<state>/grand_exchange.json` | `<state>/ingame_market.json` (an old file is renamed on the first start) |
| ledger tag `grand-exchange` | `ingame-market` (older ledger entries keep the old tag) |
| button "GRAND EXCHANGE" | "INGAME MARKET" |

## For players

- **MARKET** button in the lobby top bar, left of KEYS. It appears once the
  castle crafting tutorial is done (assignment 5007, "first floor
  complete"), with no guide. Any hero level can use it.
- **Weapons / Equipment:** auctions. The seller sets a starting bid, an
  optional buy-now price, gold or blings, and 12/24/48 hours. Bids take
  the money at once; an outbid player gets it back in Collect. A bid in the
  last 2 minutes extends the auction to 2 minutes (no sniping). With bids,
  the listing can't be cancelled. When time is up the highest bid wins;
  without bids the item comes back.
  Filters: class (defaults to the selected hero's class; rings, amulets,
  pets and universal costumes show for every class), gold/blings, sort
  (ending soon, newest, price, level), search.
- **Items** (crafting materials and dyes): no auctions, a market like
  Steam's. Sell orders are filled cheapest first, buy orders highest first.
  An order that meets the other side trades at once at the waiting order's
  price. A buyer's unspent money (bought cheaper than their max) is
  refunded. Buy orders hold the money until they fill or are cancelled.
- **Fee:** 1% of every sale, paid by the seller (rounded; sales under 50
  pay nothing).
- **Collect:** bought items, sale money, refunds, unsold and cancelled items
  wait here. "Collect all" moves them into the inventory and wallet. Gold
  above the storage capacity, and items without inventory space, stay.
- **Limits:** 20 open listings and orders per player, prices 1 to
  100,000,000, only inventory items (not equipped ones), no items marked
  not sellable.
- **Bling shop in the game:** the green "+" next to the blings (and every
  other "Purchase blings" link) opens the Bling shop in a window inside the
  game with an X top right, instead of the Steam overlay (Shift+Tab). Esc
  closes it too.
- **Update countdown:** before a server update a box bottom right shows the
  time left and the closing time in the player's own time zone. At 0 the
  game closes itself (WASD helper `POST /quit`, since 2026-11-22 evening; `game://pause/quitGame` alone left the exe running, kept as a fallback) and the server ends all
  sessions.

## Changes after the first test (2026-11-22)

- No trading with yourself: own buy orders and sell offers don't fill each
  other (crossing books are matched only between different players,
  `Market.match_books`, every 30 s and on each request), no buy-now or
  bid on your own auction.
- Everything a player gets waits in Collect (an automatic delivery was
  tried for an hour and dropped at the owner's request).
- Sell tab sorted: weapons, equipment (class, then level high to low), then
  materials and dyes by name.
- No browser `confirm()` (it opened a Windows dialog outside the game).
- A listed item stays visible in the game's bag until the game's next
  request (about a minute). A vendor sale of it in that window is refused
  by the server, which also undoes the gold the client booked itself
  (`AccountState.market_taken`, `_cmd_SellHeroItemCommand`). After every
  trade the panel clicks `game://battlelog/RefreshFriends` (best effort) so
  the game talks to the server sooner.

## Changes (2026-11-23, v1.4.3)

- **Rarity like the game:** every effect of an item counts, ability effects
  too (0 Basic grey, 1 Magic green, 2 Exceptional yellow, 3 Legendary
  orange, 4 Epic purple); only magic properties were counted before.
- The "refresh" click on `game://battlelog/RefreshFriends` after a trade is
  gone: it opened the battle log.

## Changes (2026-11-22, v1.4.2)

- **Collect one entry** (button per row) or everything. After a collect the
  server sends a notification the client doesn't know
  (`AccountState.FORCE_RELOAD` = ForgeItemCollected): the game reloads the
  whole account, so the bag shows the new items (it used to stay stale).
- **Gold above the storage capacity:** collected sale money is credited in
  full. Castle upgrades still can't cost more than the storage capacity
  (`_cmd_UpgradeBuildingCommand` refuses and makes the game reload).
- **Drag and drop:** dragging an item from the game's inventory onto the
  Ingame Market window opens the Sell tab with that item selected
  (mousedown on an `inventory-grid-slot-index-N` slot, mouseup inside the
  window).
- **Rarity colours as in the game:** Basic grey, Magic green #6ec007,
  Exceptional gold #d8b500, Legendary orange #ec6a04, Epic pink #f735ff.
- **Esc** closes the Ingame Market / Bling shop / party windows without
  opening the game menu; with none of them open the game handles Esc as
  usual.
- **Admin:** the log and open offers are paged (25 / 15 rows a page).

## Admin

- **Economy stats tab → Ingame Market log:** every listing, bid, sale (with
  buyer, seller, price and fee), cancel, expiry, buy order and collect,
  newest first (last 5000 kept), plus total sales, volume and fees per
  currency, all open offers and what waits in collect boxes. Player names
  link to the player page. AdminService `GetMarket {limit}`. Actions from
  before the log existed (2026-11-22, first hour) aren't in it.

- **Server tab → Server update countdown:** minutes (1-1440) and a message,
  "Schedule update", "Cancel". AdminService `GetNotice`, `ScheduleUpdate
  {minutes, message}`, `CancelUpdate`. Stored in
  `state/new/server_notice.json`. Every game polls `/notice` every 20 s.
  At the time, `_notice_watch` logs out every session (once).
  Workflow for a patch: `python tools
estart_server.py` (2026-11-23)
  schedules the 5-minute countdown, waits for 0 and restarts only the game
  server with its current command line (chat server keeps running);
  `--minutes`, `--message`, `--now`; Ctrl+C while waiting cancels.
  A countdown whose time passed while the server was down is dropped at
  startup (`Notice.__init__`), and `stop_servers.bat` cancels a pending one:
  stopping early no longer carries the countdown into the next start, where
  it closed every game that reconnected. Both .bat files take `/nopause`.
  Fix 2026-11-23: a server started by `start_servers.bat` gets its settings
  (Steam API key, public host, Discord webhooks) from the batch file's
  environment, not from its own command line. `restart_server.py` copied
  that bare command, so the restarted server ran without them (Steam login
  `steam_disabled`, no Discord post). It now always relaunches with
  `call server_config.bat && <python command>`. Check after a restart:
  `POST /launcher/steam` with an empty ticket must answer `steam_no_ticket`,
  not `steam_disabled`.
- **Players → Login → Castle name → Rename** (`SetDisplayName`): fix a name
  without a restart (logs the player out).

## How it works

- **Refused sessions** are logged (2026-11-23): `[market] session refused:
  <player>: UI from <ip>, game from <ip>, last game request N s ago` (or
  "account ... not loaded"). Replies of `/market/*`, `/party/*` and `/notice`
  carry the header `X-MQEL: 1` (exposed for CORS); the UI keeps an address
  only when its reply has it, so another program on 127.0.0.1:8081 of a
  player's PC is skipped. The party window shows the error instead of
  "Loading..." forever.
- **Access:** the UI asks `GET /market/session?a=<AccountId>` on the game port
  (8081; first 127.0.0.1, then `MQEL_PUBLIC_HOST`, like the friend online
  dots). The server answers only if the request comes from the IP of that
  account's last game request (at most 5 minutes ago), or from the server
  PC. It returns a random web token (12 h) that the other calls carry
  (`w`). The Bling shop accepts the same token in place of the session
  token (`/blings?t=<web token>`), so the game's real session token never
  reaches the UI. Limit: two players behind the same internet connection
  could, with crafted requests, act for each other. Same as the friend
  online dots.
- **Endpoints** (JSON, CORS `*`): GET `overview`, `items`
  (`category`, `class`, `currency`, `q`, `sort`), `materials` (`q`); POST
  `sell_item {slot, start, buyNow, currency, hours}`, `bid {id, amount}`,
  `buy_now {id}`, `cancel {id}`, `sell_material {templateId, qty, price,
  currency}`, `buy_material {...}`, `collect`. `GET /notice` without a token.
- **Inventory and wallet:** taking items and paying change the account
  under its lock and are sent to the running game as
  `HeroInventoryRemoved/Updated` and `WalletUpdated` notifications (they
  arrive with the game's next request). Collect sends
  `HeroInventoryAdded/Updated` + `WalletUpdated`. Counterparties are never
  touched directly: everything they get goes to their collect box, so
  offline players are no problem.
- **Data:** `state/new/ingame_market.json` (listings, buy orders, collect
  boxes, last 2000 trades for "last sale"), written atomically. Auctions
  end on every request and every 30 s (`Market.sweep`).
- **Icons:** served by the game server at `/market/icon/<path>` from
  `client/GameData/Data/Generated/Web` (`<InvIconUrl upper case>`, PNG only,
  no `..`). The players' game has no web copy of most item icons (its
  inventory is a native panel), so `http://localhost/gamedata/...` showed
  empty boxes (fixed 2026-11-22). The event eggs have no icon file.
- **Inventory delay:** an idle lobby talks to the server about once a
  minute, and the inventory/wallet notifications ride on those answers. A
  listed item stays visible in the game's bag, and collected items appear,
  up to a minute later. Collect therefore never fills a slot whose removal
  the game hasn't received yet (pending `HeroInventoryRemoved`), so the
  game can't mix up two items in one slot.
- **Rarity colour:** by the number of magic properties (`EffectCount` in
  EquipmentCategorySettings: Basic 0, Magic 1, Exceptional 2, Legendary 3,
  Epic 4).

## Testing

On a copy of the state (`_temp60/market_test/new`), a second server on port
18081 without the Discord webhooks:

```
python server/game_server.py --host 127.0.0.1 --port 18081 --profile new --state _temp60/market_test/new
```

Load the two accounts with an admin call (e.g. `GetWallet`), then
`/market/session` from 127.0.0.1 works for them. Tested: listing, own bid
refused, bid, auction end with fee, buy-now in blings, collect (gold
capped by storage), material sell/buy with matching and refunds, buy-order
cancel, Bling shop with the web token, notice schedule/cancel. UI: mock
pages with real data rendered in headless Brave (`_temp60/market_mock`).

## v1.5 (2026-11-23)

Quality-filled icons, a Sort menu that reverses when the active option is
picked again (`/market/items?...&desc=1`), two columns in Weapons and
Equipment, pages in My offers (6 per page), an item info box on hover
(always left of the mouse; `describe_item` → `EffectInfo`), and the lobby
inventory sort (`POST /market/sort_inventory`). Details:
docs/97-inventory-sort-orbs.md.
