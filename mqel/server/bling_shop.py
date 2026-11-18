"""Test-Shop für Blings (PremiumCash), ohne Bezahlung.

Der Knopf "Purchase blings" im Client öffnet
Account.ClientSettings.PrimaryShopPremiumPurchaseUrl im Browser; im
Original die Bezahlseite (Uplay/Steam), danach schrieb der Shop-Server die
Blings gut. Hier zeigt der Server unter /blings?t=<Token> eine Seite mit
Paketen; ein Klick schreibt sie dem Spieler gut (WalletUpdated-Meldung mit
der nächsten Client-Anfrage).

Die Original-Pakete stehen nicht in den Client-Daten (Kauf lief über eine
externe Bezahlseite). Belegt ist nur ein "500 Bling Bundle" (Steam-DLC
"Supply Pack") und grob 100 Blings je Euro (Fan-Wiki); die übrigen Stufen
sind angenommen.
"""

import html
import re

import balance
import special_packs

PACKS = [500, 1000, 2500, 5000, 10000]

# Saison-Packs (SpecialPackSettings), nur während ihres Events
# (patcher.seasonal_event) im Angebot
EVENT_PACKS = {"Halloween": (67, "Halloween Pack")}


def shop_url(base, token):
    """base: Schema und Host, unter denen der Client den Spielserver erreicht."""
    return "%s/blings?t=%s" % (base, token)


# Tabs des Bling-Shops und je Pack (Tab, Name, Kurzbeschreibung); Packs
# ohne Eintrag landen unter "Specials" mit ihrem DebugName
TABS = ["Heroes", "Pets", "Castle", "Specials"]
CATALOG = {
    2: ("Heroes", "Legit Fan: Knight",
        "DoubleO knight skin, Giganticness hammers and gear, a creature, DoubleO castle skin"),
    3: ("Heroes", "Legit Fan: Archer",
        "DoubleO archer skin, weapons and gear, a creature, DoubleO castle skin"),
    4: ("Heroes", "Legit Fan: Mage",
        "DoubleO mage skin, weapons and gear, a creature, DoubleO castle skin"),
    5: ("Heroes", "High Roller",
        "DoubleO skins for three heroes, nine legendary weapons, castle skin and theme"),
    7: ("Heroes", "DoubleO Starter: Knight", "DoubleO knight skin, starter gear, castle skin"),
    8: ("Heroes", "DoubleO Starter: Archer", "DoubleO archer skin, starter gear, castle skin"),
    14: ("Heroes", "Diamond Collection",
         "Diamond costumes for all four heroes, Princess Pufflefang, a creature and a theme"),
    15: ("Heroes", "Diamond Underwear", "Painhammer's underwear costume, a creature, two inventory tabs"),
    45: ("Heroes", "Wannabe Collection",
         "Four Nigel pets with matching costumes: Darkness, Funktastic, Adorable, Retro"),
    47: ("Heroes", "Watch_Dogs", "Watch_Dogs weapons, capes and bandanas for all four heroes, a theme"),
    49: ("Heroes", "Pajama Party", "Sleepwear costumes for all four heroes"),
    50: ("Heroes", "Gabe's Pendant", "The amulet from the Steam release"),
    74: ("Heroes", "Beta Rewards", "GoldenGuy, Irene's Pretty Pet Peacock and the beta testers' rings"),
    26: ("Pets", "Lil Arachbro", "A small spider that follows your hero"),
    27: ("Pets", "Lil Flameo", "A little fire spirit that follows your hero"),
    28: ("Pets", "Snugglemuffin", "A cuddly companion for your hero"),
    51: ("Pets", "Nigel", "Nigel, the pet from the Steam release"),
    1: ("Castle", "DoubleO Castle", "DoubleO castle skin and an inventory tab"),
    66: ("Castle", "The Big Pack",
         "Masks, hats and pets (Jumbo, Lil Smokey, ...), 95 creatures, 77 traps, "
         "63 decorations, 3 themes"),
    67: ("Castle", "Halloween", "Spooky theme, creatures and decorations"),
    71: ("Castle", "Xmas Package", "Icy Stare, 15 creatures, 5 traps and 55 decorations"),
    75: ("Castle", "Look Ma, I'm the Best!", "52 decorations to show off in your castle"),
    72: ("Specials", "Infinite Pack",
         "Seven inventory tabs and Cornelius' shop unlocks that grow with your castle level"),
    69: ("Specials", "Material-O-Matic", "One Material-O-Matic for your castle plus a set of crafting materials"),
}


def _entry(pack):
    return CATALOG.get(pack["Id"], ("Specials", pack["DebugName"], ""))


def _name(pack):
    return _entry(pack)[1]


def _contents(pack):
    """Inhalt in Worten (ohne Blings, Heldenzugang und Emotes)."""
    def n(count, one, many=None):
        return "%d %s" % (count, one if count == 1 else (many or one + "s"))
    out = []
    if pack.get("HeroItems"):
        out.append(n(len(pack["HeroItems"]), "equipment item"))
    heroes = pack.get("BoostedHeroes") or {}
    if heroes:
        out.append(n(len(heroes), "hero skin"))
    if pack.get("CastleVisualGroupNames"):
        out.append("castle skin")
    for key, one in (("UnlockedThemes", "castle theme"), ("Creatures", "creature"),
                     ("Traps", "trap"), ("Decorations", "decoration")):
        count = (len(pack.get(key) or []) if key == "UnlockedThemes" else
                 sum(x.get("AvailableCount", 1) for x in pack.get(key) or []))
        if count:
            out.append(n(count, one))
    if pack.get("AdditionalInventoryTabCount"):
        out.append(n(pack["AdditionalInventoryTabCount"], "inventory tab"))
    if pack.get("CraftingMaterials"):
        out.append("crafting materials")
    if pack.get("ShopSkus"):
        out.append(n(len(pack["ShopSkus"]), "shop item") + " unlocked")
    if pack.get("PerLevelShopSkus"):
        out.append("more shop items with each castle level")
    return out


def offers(event):
    """[(Pack-Id, Preis)] im Angebot, teuerste zuerst; 67 nur im Event."""
    seasonal = {pid for pid, _ in EVENT_PACKS.values()}
    current = EVENT_PACKS.get(event, (None,))[0]
    return sorted(((pid, price) for pid, price in balance.shop_prices().items()
                   if pid not in seasonal or pid == current),
                  key=lambda x: (-x[1], x[0]))


def fmt(n):
    return "{:,}".format(n)


def catalog_page(display_name, token, blings, owned, event, message=""):
    """Bling-Shop der Bling-Wirtschaft: Packs gegen erspielte Blings."""
    cards = []
    for pid, price in offers(event):
        pack = special_packs.pack(pid)
        items = "".join("<li>%s</li>" % html.escape(x) for x in _contents(pack))
        if pid in owned:
            action = ""
        elif blings < price:
            action = '<span class="short">%s more blings needed</span>' % fmt(price - blings)
        else:
            # Rückfrage in der Karte: confirm() öffnete im Client ein
            # Windows-Fenster außerhalb des Spiels
            action = ('<a class="buy" href="#" onclick="return ask(this)">Buy</a>'
                      '<span class="ask">Buy for %s? <a class="buy" '
                      'href="/blings/buy_pack?t=%s&amp;id=%d">Yes</a> '
                      '<a class="no" href="#" onclick="return ask(this)">No</a></span>'
                      % (fmt(price), html.escape(token), pid))
        badge = '<span class="badge">Event</span>' if pid == EVENT_PACKS.get(event, (0,))[0] else ""
        tab, name, desc = _entry(pack)
        if pid in owned:
            tab = "Owned"
        cards.append((tab, '<div class="card%s"><h2>%s%s</h2><p class="desc">%s</p>'
                      '<ul>%s</ul><div class="foot"><span class="price">%s</span>%s</div></div>'
                      % ("", html.escape(name), badge,
                         html.escape(desc), items, fmt(price), action)))
    tabs = [t for t in TABS + ["Owned"] if any(c[0] == t for c in cards)]
    buttons = "".join('<a href="#" class="tab%s" onclick="return show(%d)">%s</a>'
                      % (" on" if i == 0 else "", i, t) for i, t in enumerate(tabs))
    panes = "".join('<div class="grid pane%s">%s</div>'
                    % (" on" if i == 0 else "", "".join(c[1] for c in cards if c[0] == t))
                    for i, t in enumerate(tabs))
    note = '<p class="msg">%s</p>' % html.escape(message) if message else ""
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bling Shop</title>
<style>
body{font-family:Georgia,serif;margin:0;padding:1.5rem;background:#1d1a2b;color:#eee}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;
gap:.5rem;max-width:60rem;margin:0 auto 1rem}
h1{margin:0;color:#ffd54a;font-size:1.8rem}
.wallet{font-size:1.2rem}.wallet b{color:#ffd54a}
.msg{max-width:60rem;margin:0 auto 1rem;padding:.6rem 1rem;background:#2f4a2f;border-radius:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem;
max-width:60rem;margin:0 auto}
.card{background:linear-gradient(#352f4d,#28233b);border:1px solid #4d4470;border-radius:10px;
padding:1rem;display:flex;flex-direction:column}
.card.have{opacity:.6}
nav{max-width:60rem;margin:0 auto 1rem;border-bottom:2px solid #4d4470;overflow:hidden}
.tab{float:left;margin-right:1px;padding:.5rem 1.2rem;color:#cfc8e8;text-decoration:none;border-radius:6px 6px 0 0;
background:#28233b}
.tab.on{background:#4d4470;color:#ffd54a;font-weight:bold}
.pane{display:none}.pane.on{display:block;display:grid}
.pane.on .card{margin-bottom:1rem}
.desc{margin:0 0 .6rem;color:#eee;font-size:.95rem}
.card h2{font-size:1.15rem;margin:0 0 .5rem;color:#fff}
.card ul{margin:0 0 1rem;padding-left:1.1rem;color:#a99fc4;font-size:.85rem;flex:1}
.foot{display:flex;justify-content:space-between;align-items:center;gap:.5rem}
.price{font-size:1.3rem;color:#ffd54a;font-weight:bold}
.price::after{content:" blings";font-size:.8rem;color:#bba}
.buy,.owned,.short{margin-left:.8rem}
.buy{background:#ffd54a;color:#1d1a2b;padding:.4rem 1rem;border-radius:5px;
text-decoration:none;font-weight:bold}
.short{font-size:.85rem;color:#a99}.owned{color:#9d9}
.badge{margin-left:.5rem;font-size:.7rem;background:#e07b22;color:#fff;padding:.1rem .4rem;
border-radius:4px;vertical-align:middle}
.ask{display:none;font-size:.9rem}.foot.asking .ask{display:inline}
.foot.asking > .buy,.foot.asking .price{display:none}.no{color:#cfc8e8;margin-left:.3rem}
footer{max-width:60rem;margin:1.5rem auto 0;color:#998;font-size:.85rem}
</style></head><body>
<header><h1>Bling Shop</h1><div class="wallet">%s &ndash; <b>%s</b> blings</div></header>
%s<nav>%s</nav>%s
<footer>Blings are earned in the game: achievements, quests, the bling mine, rare loot,
leagues and competitions. Restart the game after a purchase to see castle items and
shop unlocks.</footer>
<script>
function show(n){
  var t=document.getElementsByClassName("tab"),p=document.getElementsByClassName("pane");
  for(var i=0;i<t.length;i++){t[i].className=i==n?"tab on":"tab";
    p[i].className=i==n?"grid pane on":"grid pane"}
  return false}
function ask(a){
  var f=a.parentNode;if(f.className.indexOf("ask")==0)f=f.parentNode;
  f.className=f.className=="foot"?"foot asking":"foot";return false}
</script>
</body></html>""" % (html.escape(display_name or ""), fmt(blings), note, buttons, panes)


def page(display_name, token, blings, message="", has_infinite=False,
         event_pack=None, has_event_pack=False):
    rows = "".join(
        '<li><a href="/blings/buy?t=%s&amp;amount=%d">%s Blings</a></li>'
        % (html.escape(token), n, "{:,}".format(n).replace(",", "."))
        for n in PACKS)
    note = "<p><b>%s</b></p>" % html.escape(message) if message else ""
    rows += ("<li>Infinite Pack (schon freigeschaltet)</li>" if has_infinite else
             '<li><a href="/blings/infinite?t=%s">Infinite Pack</a></li>'
             % html.escape(token))
    if event_pack:
        pid, name = event_pack
        rows += ("<li>%s (schon freigeschaltet)</li>" % name if has_event_pack else
                 '<li><a href="/blings/pack?t=%s&amp;id=%d">%s</a></li>'
                 % (html.escape(token), pid, name))
    return """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bling-Shop</title>
<style>
body{font-family:sans-serif;max-width:32rem;margin:2rem auto;padding:0 1rem;
background:#1d1a2b;color:#eee}
a{color:#ffd54a}li{margin:.6rem 0;font-size:1.2rem}
</style></head><body>
<h1>Bling-Shop (Test)</h1>
<p>Spieler: %s &ndash; Kontostand: %d Blings</p>%s
<ul>%s</ul>
<p>Kostenlos. Im Spiel erscheint der neue Stand mit der nächsten Aktion.</p>
</body></html>""" % (html.escape(display_name or token), blings, note, rows)
