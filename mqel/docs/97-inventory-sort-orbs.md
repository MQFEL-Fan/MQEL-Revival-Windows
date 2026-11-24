# v1.5: orb numbers, inventory sort, Ingame Market upgrades, game icon

Date: 2026-11-23. Released without the update countdown (no players
online, owner's call). Code: `server/ui_mods/lobby_mods.html` (UI patch 19),
`server/ui_mods/ingame_market.html`, `server/ingame_market.py`,
`server/account_state.py` (`sort_inventory_tab`), `server/game_server.py`
(`/market/sort_inventory`, `desc` on `/market/items`), `tools/wasd/xinput_wasd.c`
(icon, Unicode subclass). Tests: `InventorySortTest`, market logic check
(`node` + fake DOM, see "Testing").

## Health and mana numbers in the orbs

The HUD orbs (`#modules-hudBar-attackHUD .health-gauge` / `.mana-gauge`,
canvases of `attackHUD.js`, in TopView, lobby and attacks) show
`current / max` in white bold with a dark outline, centred on the orb. The
numbers come from the orb's own tooltip (`data-tooltip`, rendered by the
game from `template-attackHUD-health-tooltip-content` on every gauge
update), read every 250 ms; no game script is changed. Labels are
`position:fixed` over the canvas and let mouse events through, so the
game's tooltip still works. Hidden when the HUD isn't shown.

## Inventory sort

- A **SORT** button at the left of the "Drag here to sell items" row of
  every inventory grid (`.inventory-grid-module .sell-container`; the
  inventory panel and the forge). The menu opens upward: Type, Quality
  (best first), Level (high to low), Name (A to Z). Picking the option that
  is already active reverses it (Type reversed, Quality lowest first, Level
  low to high, Name Z to A).
- It sorts the **open tab** only (tab = lowest `slot-index` shown / 21) and
  packs the items from the tab's first slot. Every unlocked tab (up to 8,
  `Inventory.InventoryTabCount`) can be sorted; a tab that isn't unlocked is
  refused.
- Server: `POST /market/sort_inventory {w, tab, by, desc}` (Ingame Market web
  token, works before the market is unlocked) → `Market.sort_inventory` →
  `AccountState.sort_inventory_tab(tab, key)`; only `SlotIndex` values change.
  If anything moved, `FORCE_RELOAD` makes the game reload the account and
  redraw the bag ("your bag reloads in a moment").
- Sort keys (`Market._sort_key`): Type = weapons, equipment, potions and
  other consumables, crafting materials, dyes, then class, quality, level,
  name. Equipment quality = number of effects (like the game).
- Caveat: an item dragged in the same second (swap not yet sent to the
  server) can be undone by the reload.

## Ingame Market

- **Quality fill**: every icon (all tabs, also Sell) has the game's
  inventory quality box behind it (`inv/box/50x50/inv_box_50x50_<quality>.png`,
  the same images as `.inventory-slot .icon-background.quality-*`); the
  coloured frame stays.
- **Sort that reverses**: the Sort menu of Weapons and Equipment is our own
  drop-down; picking the active option again reverses it (Ending soon ↔
  Ending last, Newest ↔ Oldest, Price low ↔ high, Level high ↔ low).
  `GET /market/items?...&desc=1` reverses the server's order.
- **Two columns**: Weapons and Equipment list items in two compact columns
  (flex wrap, 50% each, prices and bid box on the right of each card).
- **My offers in pages**: 6 per page, Prev / Page x / y / Next instead of
  scrolling; back to page 1 when the tab is opened.
- **Item info box on hover**: any item in any tab (icon or row) shows a box
  like the game's inventory tooltip: name in its quality colour, quality and
  type, level badge, every effect with its description, class and required
  level; materials show name, kind and quantity. The box always sits to the
  **left** of the mouse (to the right only when there's no room).
  Effect text: `describe_item` → `EffectInfo [{Name, Text}]`, Text = the
  Oasis description with `{0}` = `BaseValue + ValuePerLevel × level`
  (percent when `FormatValueAsPercentage`), e.g. Magic Find III = +10%.

## Game icon in the taskbar

Players saw a blank page instead of the game logo on the game window. The
WASD helper (always loaded, `mqelwasd9_1.dll`) now:

- gives the game window the exe's own icon (first `RT_GROUP_ICON`, big and
  small, `WM_SETICON`) once per window, from the movement thread's 5-second
  check; `WASD.log` field `iconSet`;
- subclasses the window with the W functions when it is a Unicode window
  (`SetWindowLongPtrA` on a Unicode window turned it into an ANSI window,
  suspected cause).

The exe files themselves were checked: their icons are intact.

## Testing

- `python -m unittest discover -s tests` (InventorySortTest).
- market logic without the game: the script of `ingame_market.html` runs in
  node with a fake DOM and fake XHR (two columns, quality box, sort reverse
  request, pages 1-3, tooltip text and position).
- To confirm in game: orb numbers in lobby and attack, Sort on several tabs
  (and twice for reverse), market tooltips and columns, taskbar icon.

## Fix v1.5.0.1 (2026-11-23)

Reported after v1.5: no numbers in the orbs during attacks, the numbers
ran over the orb's edge, and no SORT button in the inventory.

- **Orb numbers**: the labels now sit above everything except our own
  windows (`z-index` 99980; 60 was under the HUD during attacks) and are
  hidden only when the gauge itself is hidden or has no size. Two lines,
  current on top and "/ max" smaller below, centred on the gauge; the font
  starts at 17% of the orb (max 18 px) and shrinks until the wider line
  fits 82% of the orb's inner circle (68% of the 146 px gauge).
- **SORT button**: injected into `.sell-container` it never showed (the
  game's own CSS for that row). It is now a floating button (fixed, z-index
  99985) per inventory grid, kept at the left of the "Drag here to sell
  items" row every 250 ms, and shown only while the grid is really on
  screen: `document.elementFromPoint` at the grid's top left has to belong
  to that inventory, so it hides when another window covers it. Same menu
  as before (opens upward, same pick again = reversed), works on tabs 1-8.

## Fix v1.5.0.2 (2026-11-23): windows above the building bar

The five building shortcuts under the top bar (`#modules-building-nav-bar`:
Cornelius, brewery, forge, ...) covered our item info box and windows. The
bar sits in `#top-navigation-bar-container`, whose stacking level the game
sets at run time (`top-navigation-bar-layerIndex`), so it can't be lowered
with CSS. All mod layers moved above the game's UI instead, same order as
before: orb numbers 2147480900 < Sort button 2147480950 < raid live panel
2147480980 < windows (`.mqel-win`: Ingame Market, party, Bling shop)
2147480990 < update countdown 2147480995 < party toast 2147480996 <
Setting Mod panel 2147481000 < item info box 2147483000.

## Fix v1.5.0.3 (2026-11-24): Buy now over the next card

In the two-column Weapons/Equipment list the bid box, Bid and Buy now sat
in the absolutely positioned price block (`.mqel-right`, 134 px): Buy now
wrapped to a third line and, as the block doesn't size the card, covered
the card below. The controls are now a normal-flow row at the bottom of
the card (`.mqel-acts`, right-aligned, `margin-right:-136px` to use the
price column's width, no wrapping), so the card grows to hold them. The
price lines (Start / Bid, Buy now) keep their size (12 px / 11 px).
