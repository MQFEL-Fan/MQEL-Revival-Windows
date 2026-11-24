"""Client-UI-Patches: Fehler der finalen UI beheben.

Die UI-Dateien liegen lose unter Data/UI und werden von dort geladen. Alle
Patches einer Datei stehen hier zusammen, weil jede Datei immer vom
Original aus gepatcht wird (<Name>.orig, falls vorhanden: das legt
tools/patch_ui.py beim lokalen Patchen an). Verteilt werden sie vom
Patcher (patcher.py, Paket GameUI).

1. Wettbewerbs-Popup "Castle's level": CastleCompetitionPopUpModule liest
   UbisoftCompetitionInfo.HeroLevel, das der Contract des finalen Clients
   nicht mehr hat (der C++-Leser kennt nur CastleLevel) -- die Zeile blieb
   leer. Der Patch nimmt CastleLevel.
2. Wettbewerbs-Rangliste, Spalte "Reward": das Template prüft
   enumValueCompare(RewardItems[0].Type, "CurrencyAmount"), der Client
   übergibt Type aber als Namen ("CurrencyAmount", 0x526330 -> 0x561a20),
   hyperquest.enums.getName vergleicht mit === gegen Zahlen -- die Spalte
   blieb immer leer. Der Patch prüft auf CurrencyAmount selbst.
3. Schmiede: Hinweis beim Einlegen der angelegten Waffe. Beim Abholen einer
   umgeschmiedeten angelegten Waffe (MainHand) wendet der Client die
   Equip-Meldungen nicht an; der Server erzwingt ein Neuladen des Accounts
   (docs/CHECKLIST.md, Schmiede), das erst beim nächsten Moduswechsel kommt.
   Angelegte Teile kommen als ForgeMysteryBoxItemModel.ItemSlotModel.
   EquippedItemModel (ItemSlot 8 = MainHand). Die MessageBox meldet beim OK
   ihre Id an den Client -> vorhandene reine Info-Id.
4. Freundes-News (HeroLevelUpFriend/Own): der Server schickt HeroName als
   englischen Klassennamen (Knight/Archer/Mage/Runaway), die Vorlagen setzen
   ihn unübersetzt in den Satz. Der Patch übersetzt ihn je Sprache mit den
   Namen aus GameplaySettings/Oasis/oasis_<Sprache>.json (Ids 4, 440, 441,
   12183). Englisch zusätzlich: "Name's{Held}" ohne Leerzeichen und
   "Your Knight's is now stronger".
5. Blings im Hauptmenü: beim Zuwachs zählte eine Animation hoch, startete bei
   parseInt("1.234") = 1 und schrieb jeden Schritt und den Endwert ohne
   Tausendertrenner. Der Patch lässt das Hochzählen (280 ms) weg; den
   formatierten Endwert setzt der Client gleich danach selbst. Die erste
   Fassung (Hochzählen mit formatCurrency je Schritt) legte im Spiel danach
   alle Achievement-Popups lahm (im Browser nicht nachvollziehbar).
6. "Attack Castle" im Kontextmenü eines Spielers: der Link nimmt
   PlayerInteractionModel.AttackType, das der C++-Leser nicht kennt
   (nur AttackSource/CastleType) -> attackType=undefined, Assert "Cannot
   parse enum" (UrlParameterMap::GetEnum) und kein Burg-Popup. Der Patch
   setzt wie der Rache-Knopf im Kampfprotokoll attackType=None.

7. Template-Helfer enumValueCompare: vergleicht getEnumName(Wert) mit dem
   Namen; der Client übergibt Enums aber oft schon als Namen (wie in 2.),
   dann liefert getEnumName "" und der Vergleich ist immer falsch. Z. B.
   zeigte das Burgfenster einer delegierten Validierung (AttackType
   "Validation") Kronen statt der Validierungs-Belohnung. Der Patch nimmt
   den Wert auch direkt als Namen.
8. Kaufabfrage eines Probe-Helden: das Helden-Fenster zeigt den Preis mit
   Trial-Rabatt (CurrencyAmount, z. B. 900), die Kaufabfrage danach den
   Listenpreis der SKU (ShopProduct.Skus[..].ActualPrice, 950); berechnet
   wird der Rabatt (Server). Der Patch merkt sich je SkuCode den Preis aus
   dem Helden-/Themen-Fenster und zeigt ihn in den Kaufabfragen.
9. Achievement-Blings (balance.py, nur bei eingeschalteter Bling-Wirtschaft):
   der Client kennt keine Achievement-Belohnung. Der Helfer
   achievementBlings (Beträge eingebettet) liefert sie je Id; Popup und
   Achievement-Liste zeigen "+N" mit Bling-Symbol.
10. Kauf eines Probe-Helden mit weniger Blings als dem Listenpreis: der Kauf-
   knopf im Helden-Fenster (game://shop/buySku) prüft im Client zuerst mit
   dem SKU-Listenpreis ohne Trial-Rabatt (ShopController 0xe4be20, nur
   Sale-Prozente) und öffnet bei zu wenig Blings den Bling-Shop
   (HandleInsufficientPremiumAmount); erst der Bestätigungsknopf
   (isPremiumCashConfirmationPurchase=1) rechnet mit Rabatt
   (CalculateSkuActualPrice 0xe4bc00 zieht die Ziele aus
   Hero.PriceReductionIds ab). Z. B. Level 16, 500 Blings, Preis 300: Shop
   statt Kauf. Der Patch gibt dem Knopf beim Probe-Helden den Parameter
   gleich mit; das Helden-Fenster mit dem Preis auf dem Knopf ist dann die
   Kaufabfrage, die zweite entfällt.
11. Bling counter in the lobby (2026-11-20): the 0.36 TopView has
   .premiumAmount in #lobby-index-premium-wallet, outside
   #modules-lobby-wallet-container where lobbyWalletModule.js looks, so the
   number stayed empty (only the gem icon). The patch looks in both places
   and formats the amount on updates too. Patch notes: PATCH_NOTES.md.
12. Keybind panel / WASD movement (MQEL-Improvement): a "KEYS" button (since
   2026-11-24 "SETTING MOD", see 18.) left of
   the pause-menu gear in the lobby top bar opens a panel
   (ui_mods/keybind_panel.html) that edits the WASD movement keys and the
   game's ShortcutsDictionary. The game's own Settings window is a native
   Opal panel (log: "OpenOpalPanel : OptionPanel"), so it can't get a
   button. The panel talks to the WASD helper DLL (tools/wasd,
   GameData/Bin/mqelwasd9_1.dll, see patcher.wasd_import) on
   http://127.0.0.1:27631; without the DLL
   it only shows how to install it. Guide: docs/80-wasd-keybinds.md.
13. Region 10 (Level-60-Update, level60.py) on the region map: the
   template draws every region from the data, but each needs CSS
   (regionSelectionModule.css: castle-position-N, castle-N ...). Region 10
   reuses the Glimmering Valley island (ZONE7), tinted gold by png_tint.py
   (data URIs), between Upper Bestmount and Stabbinshire. Move it with
   REGION10_LEFT/TOP. Built from the Steam UI files in server/data/steam
   (the copy in client/ is the 2014 UI with a smaller map). Also the gold
   boss medallion of Goldmaw (castleSelectorModule.css, bossId-60999).
14. Online status in the friend list (2026-11-22): a green (online) or red
   (offline) dot at the top left of each friend's picture. The friend data
   of the client (AccountSummaryForFriend) has no online field and the
   client drops unknown fields, so the list asks the server itself:
   GET /friends/online?a=<AccountId> (presence.friends_online; online =
   a game request in the last 3 minutes), first on 127.0.0.1 (the server
   PC), then on MQEL_PUBLIC_HOST, port MQEL_GAME_PORT (8081). Only friends,
   only for the player's own IP. Refreshes every 30 s while the list is
   open. The dot sits below the player menu (#module-player-interaction-
   container, absolute without z-index: the dot of the next friend covered
   "View Profile", 2026-11-22), so the patch gives the menu z-index 30.
15. Patch base (2026-11-22): the scripts in client/GameData/Data/UI/Js are
   the May 2014 UI, but the game (and the players' Steam install) is the
   July 2015 UI (GameUI 280139, identical to the Steam files). Patching the
   2014 copies shipped 2014 scripts to the players; e.g. the competition
   popup asked ChallengeController.getChallenge, which the 2015 game never
   answers (spinner forever). The originals of every patched file are now
   the 2015 files in server/data/steam (from 0.36.1.34.0_280139_GameUI.7z).
16. Ingame Market, in-game Bling shop, update countdown (2026-11-22,
   ui_mods/ingame_market.html, server ingame_market.py, guide
   docs/87-ingame-market.md): an MARKET button left of KEYS (shown after
   the castle crafting tutorial) opens the player market; the game's
   "Purchase blings" links (game://shop/showprimaryshop) open the Bling shop
   in a frame inside the game instead of the Steam overlay; a countdown
   bottom right shows a planned server update in the player's local time
   and closes the game at 0 (game://pause/quitGame). Server addresses as in
   14. (MQEL_GE_URLS).
17. Party and co-op raids (2026-11-22, ui_mods/party.html, server parties.py
   and raids.py, guide docs/89-coop-raids.md): a party button after Clans
   (purple Friends sprite) opens the party window (invite friends, up to 4,
   join/leave/remove); during a raid a panel at the left shows the other
   members' health, gold, XP and items (reported by each game every 3 s).
   Region 11 "Co-op Raids" on the map: the Friendzone island in purple
   (region11_css), label 5-60.
18. Setting Mod and party icon (2026-11-24, docs/96-loot-filter.md): the
   KEYS button (12.) is now "SETTING MOD"; it and MARKET (16.) are
   stacked in one 88 px column (#mqel-mod-buttons) so the top bar is
   narrower than before and nothing overlaps. The panel has a new section
   "Loot pick-up by Player" (the pet's loot filter for the hero too; exe
   patch loot_filter.py, WASD helper WASD.ini LootPlayer). The party button
   (17.) sits on the dark-blue tile of the 2015 lobby buttons
   (png_tint.party_icon_tiled, sprites in server/data/steam/.../LOBBYBAR/BTN).
19. Orbs and inventory sort (2026-11-23, v1.5, ui_mods/lobby_mods.html,
   docs/97-inventory-sort-orbs.md): the health and mana orbs show
   "current / max" in white bold (taken from the game's own orb tooltip);
   a Sort menu under the inventory grid sorts the open tab on the server
   (market token, POST /market/sort_inventory, account_state.sort_inventory_tab,
   then FORCE_RELOAD). The Ingame Market got quality-filled icons, a
   reversible sort, two columns in Weapons/Equipment, pages in My offers
   and an item info box on hover (ingame_market.html).
"""
import functools
import json
import os
import pathlib

import balance
import png_tint

# 4. Klassennamen: Wert, den der Server schickt -> Oasis-Id
HERO_NAME_IDS = {"Knight": "4", "Archer": "440", "Mage": "441", "Runaway": "12183"}
HERO_NAME = "{{:News.Data.HeroName}}"


def hero_name(game_data, lang):
    """jsrender-Ausdruck, der HeroName in die Sprache lang übersetzt
    (unbekannte Werte unverändert). Manche Installationen haben UI-Ordner
    ohne Oasis-Datei (z. B. zh): dann englische Namen."""
    path = game_data / f"Data/GameplaySettings/Oasis/oasis_{lang}.json"
    if not path.exists():
        path = path.with_name("oasis_en.json")
    names = json.loads(path.read_text(encoding="utf-8-sig"))["Translations"]
    out = ""
    for i, (key, oasis_id) in enumerate(HERO_NAME_IDS.items()):
        out += "{{%s News.Data.HeroName=='%s'}}%s" % (
            "if" if i == 0 else "else", key, names[oasis_id])
    return out + "{{else}}" + HERO_NAME + "{{/if}}"


def topview_patches(game_data, lang, path, achievement_blings=True):
    patches = [
        # 2.
        ('{{if ~enumValueCompare(Reward.RewardItems[0].Type, "CurrencyAmount", '
         '"hyperquest.enums.RewardItemType")}}',
         "{{if Reward.RewardItems[0].CurrencyAmount}}", "alle"),
    ]
    if lang == "en":
        patches += [
            ("</div>'s" + HERO_NAME + " just reached",
             "</div>'s " + HERO_NAME + " just reached"),
            ("doesn't want it to stay that way\n", "doesn't want it to stay that way!\n"),
            ("Your " + HERO_NAME + "'s is now stronger", "Your " + HERO_NAME + " is now stronger"),
        ]
    # 8.
    patches += [
        (SKU_PRICE, '<span class="currency-value">{{:~rememberPrice(SkuCode, '
                    'CurrencyAmount.Amount)}}</span>', "alle"),
        (CONFIRM_PRICE, '<span class="amount">{{:~rememberedPrice('
                        'ShopProduct.Skus[ShopProduct.Skus.length-1].SkuCode, '
                        'ShopProduct.Skus[ShopProduct.Skus.length-1].ActualPrice.Amount)}}</span>',
         "alle"),
    ]
    # 10.
    patches.append((HERO_BUY_LINK, HERO_BUY_LINK.replace(
        '{{:SkuCode}}"', '{{:SkuCode}}{{if !HeroModel.IsHeroOwned && HeroModel.IsInFreeTrial}}'
        '&isPremiumCashConfirmationPurchase=1{{/if}}"', 1)))
    # 9.
    if achievement_blings:
        patches.append(achievement_blings_patch(path))
        patches.append((ACHIEVEMENT_LIST_ANCHOR, ACHIEVEMENT_LIST_ANCHOR + ACHIEVEMENT_LIST_LINE, "alle"))
    # 12. Keybind button + panel (WASD helper)
    patches += [
        (KEYBIND_ANCHOR, KEYBIND_BUTTON + KEYBIND_ANCHOR),
        ("</body>", keybind_panel() + "</body>"),
        # 16. Ingame Market button (2026-11-23 v1.5.0.2: "INGAME MARKET" in two
        # lines, in the free space right of the trophy score), panel/shop/countdown
        (MARKET_ANCHOR, MARKET_BUTTON + MARKET_ANCHOR),
        ("</body>", market_panel() + "</body>"),
        # 17. party button after Clans, party window and raid live panel
        (PARTY_ANCHOR, PARTY_BUTTON + PARTY_ANCHOR),
        ("</body>", party_panel() + "</body>"),
        # 19. orb numbers + inventory sort (lobby_mods.html)
        ("</body>", lobby_panel() + "</body>"),
    ]
    # 14. Region 10: the client gets LevelMax 39 (level60.CLIENT_LEVEL_MAX,
    # tower position in the 3D selection); its labels show 35-60
    patches += [
        ("<span>{{:LevelMin}}-{{:LevelMax}}</span>",
         "<span>{{:LevelMin}}-{{if AttackRegionId==%d}}%d{{else AttackRegionId==11}}60{{else}}{{:LevelMax}}{{/if}}</span>"
         % (REGION10_ID, REGION10_LEVEL_MAX), "alle"),
        ("<span class='level-range'>{{:LevelRange}}</span>",
         "<span class='level-range'>{{if BossCastleId==%d}}%d-%d{{else BossCastleId==61999}}5-60"
         "{{else}}{{:LevelRange}}{{/if}}</span>"
         % (REGION10_BOSS, REGION10_LEVEL_MIN, REGION10_LEVEL_MAX), "alle"),
    ]
    # 4. nach den Textkorrekturen, die HERO_NAME als Anker brauchen
    patches.append((HERO_NAME, hero_name(game_data, lang), "alle"))
    return patches


# 12. Keybind panel: button left of the pause-menu gear, panel before </body>
KEYBIND_ANCHOR = '<a id="lobby-option-settings"'
# 2026-11-24: "Setting Mod" (key binds, WASD, loot filter for the hero).
# v1.5.0.2: one two-line button filling #mqel-mod-buttons; MARKET moved left
# of the hero portraits (MARKET_ANCHOR)
KEYBIND_BUTTON = ('<div id="mqel-mod-buttons"><a id="mqel-kb-button" data-tooltip="Setting Mod: key binds, '
                  'WASD movement, loot filter"><span>SETTING<br/>MOD</span></a></div>\n        ')


@functools.lru_cache(maxsize=1)
def keybind_panel():
    return (pathlib.Path(__file__).with_name("ui_mods") / "keybind_panel.html").read_text(encoding="utf-8")


# 16. Ingame Market (hidden until the session says it is unlocked)
MARKET_ANCHOR = '<div class="buy-level-up"'
MARKET_BUTTON = ('<a id="mqel-market-button" class="mqel-hidden" data-tooltip="Ingame Market">'
             '<span>INGAME<br/>MARKET</span><i id="mqel-market-badge"></i></a>\n        ')


# 17. Party (parties.py, raids.py): button after Clans, a group of four from the Friends sprite
# after the Notifications button: in front of it, the notifications list's
# arrow pointed at the party button (2026-11-22)
PARTY_ANCHOR = '        </nav>\n\n        \n        <nav id="lobby-index-shopContainer">'
PARTY_BUTTON = ('    <a id="mqel-party-button" data-tooltip="Party (co-op raids)"><i id="mqel-party-badge"></i></a>'
                '\n')


@functools.lru_cache(maxsize=1)
def _party_icon():
    # 2015 sprites (the players' game): the dark-blue tile of Friends/Clans/
    # Notifications under the party glyph (2026-11-24); the 2014 copy in
    # client/ has no tile, so the party button stood out
    steam = STEAM_BASE / "Data/Generated/Web/LOBBYBAR/BTN"
    if (steam / "BTNFRIENDS.PNG").exists() and (steam / "BTNNOTIFICATIONS.PNG").exists():
        return png_tint.data_uri(png_tint.party_icon_tiled(
            (steam / "BTNFRIENDS.PNG").read_bytes(), (steam / "BTNNOTIFICATIONS.PNG").read_bytes()))
    path = pathlib.Path(__file__).resolve().parent.parent / "client/GameData/Data/Generated/Web/LOBBYBAR/BTN/BTNFRIENDS.PNG"
    # same style as Friends/Clans: two smaller Friends glyphs (four people)
    return png_tint.data_uri(png_tint.party_icon(path.read_bytes()))


def party_panel():
    text = (pathlib.Path(__file__).with_name("ui_mods") / "party.html").read_text(encoding="utf-8")
    return text.replace("MQEL_PARTY_URLS", json.dumps(online_urls())).replace("MQEL_PARTY_ICON", _party_icon())


def lobby_panel():
    """19. Health/mana numbers in the orbs, inventory sort (ui_mods/lobby_mods.html)."""
    text = (pathlib.Path(__file__).with_name("ui_mods") / "lobby_mods.html").read_text(encoding="utf-8")
    return text.replace("MQEL_LOBBY_URLS", json.dumps(online_urls()))


def market_panel():
    text = (pathlib.Path(__file__).with_name("ui_mods") / "ingame_market.html").read_text(encoding="utf-8")
    return text.replace("MQEL_GE_URLS", json.dumps(online_urls()))


# 9. Achievement-Blings (balance.py): eigene Zeile unter den Punkten
ACHIEVEMENT_POPUP = 'id="template-achievement-completed-popup"'
ACHIEVEMENT_BLINGS_LINE = (
    "\n        {{if ~achievementBlings && ~achievementBlings(Achievement.Id)}}<div class=\"score\"><span>"
    "<span class='value'>+{{:~achievementBlings(Achievement.Id)}}</span> "
    "<span class=\"icon currency-small currency-small-1\" "
    "style=\"display:inline-block;vertical-align:middle\"></span></span></div>{{/if}}")


# ... und in der Achievement-Liste unter der Beschreibung (Punktespalte zu schmal)
ACHIEVEMENT_LIST_ANCHOR = ('<div class="achievementTitleDescription-description">'
                           '{{:profile.Achievement.Description}}</div>')
ACHIEVEMENT_LIST_LINE = (
    "\n        {{if ~achievementBlings && ~achievementBlings(profile.Achievement.Id)}}"
    "<div class=\"achievementTitleDescription-description\">"
    "+{{:~achievementBlings(profile.Achievement.Id)}} "
    "<span class=\"icon currency-small currency-small-1\" "
    "style=\"display:inline-block;vertical-align:middle\"></span></div>{{/if}}")


def achievement_blings_patch(path):
    """Anker = Punktezeile des Popups (je Sprache anders: pts, Pkte, ...)."""
    text = original(path).read_text(encoding="utf-8")
    start = text.index(ACHIEVEMENT_POPUP)
    begin = text.index('<div class="score">', start)
    end = text.index("</div>", begin) + len("</div>")
    line = text[begin:end]
    return (line, line + ACHIEVEMENT_BLINGS_LINE, "alle")


FORGE_ANCHOR = ("_updateMysteryBoxInformation:function(h){var a=h.ForgeMysteryBoxModel,"
                "b=a.ForgeMysteryBoxItemModel;")
WALLET_COUNT_UP = ('var j=parseInt(c.text()),f=parseInt(k);$({numericValue:j}).stop(true)'
                   '.animate({numericValue:f},{delay:100,duration:b,easing:"swing",'
                   'step:function(){c.text(parseInt(this.numericValue))},'
                   'complete:function(){c.text(f)}})')

# 11. Bling counter in the lobby: in the 0.36 TopView the .premiumAmount sits in
# #lobby-index-premium-wallet, outside #modules-lobby-wallet-container, but
# lobbyWalletModule.js still looks for it inside the container -> the number
# stays empty (only the gem icon shows). Look in both places (older clients
# keep it inside the container) and format the amount on updates too.
# 14. (MQEL_ONLINE_URLS: online_urls() as a JS array)
FRIENDS_ONLINE_JS = 'window.mqelFriendsOnline=function(l){var u=MQEL_ONLINE_URLS,id=hyperquest.cache.AccountId;if(!id||!l||!l.length)return;if(!document.getElementById("mqel-online-css")){$("head").append(\'<style id="mqel-online-css">.mqel-online{position:absolute;width:11px;height:11px;border-radius:50%;border:1px solid #1b1b1b;box-shadow:0 0 3px rgba(0,0,0,.8);z-index:2;pointer-events:none}#module-player-interaction-container{z-index:30}.mqel-online.on{background:#37d43a}.mqel-online.off{background:#d8322c}</style>\')}function paint(m){l.find(".friend-entry").each(function(){var e=$(this),k=e.attr("account-id");if(!m.hasOwnProperty(k))return;var d=e.children(".mqel-online");if(!d.length){if(e.css("position")==="static")e.css("position","relative");d=$(\'<div class="mqel-online"></div>\').appendTo(e)}var a=e.find(".avatar-container").first(),p=a.length?a.position():{left:0,top:0};d.css({left:(p.left+1)+"px",top:(p.top+1)+"px"}).attr("class","mqel-online "+(m[k]?"on":"off"))})}function ask(i){if(i>=u.length)return;var x=new XMLHttpRequest(),f=false,t=setTimeout(function(){x.abort()},4000);x.onreadystatechange=function(){if(x.readyState!==4||f)return;f=true;clearTimeout(t);if(x.status===200){try{paint(JSON.parse(x.responseText))}catch(e){}}else ask(i+1)};try{x.open("GET",u[i]+"/friends/online?a="+id,true);x.send()}catch(e){f=true;clearTimeout(t);ask(i+1)}}ask(0);if(!window.mqelOnlineTimer)window.mqelOnlineTimer=setInterval(function(){var g=$("#module-friend-notifications-friendContainer .entry-list");if(g.is(":visible")&&g.find(".friend-entry").length)window.mqelFriendsOnline(g)},30000)};'

WALLET_PREMIUM_SPAN = 'this._$premiumCash=$(this._mainPanelSelector+" .premiumAmount span")'
WALLET_PREMIUM_SPAN_FIXED = ('this._$premiumCash=$("#lobby-index-premium-wallet .premiumAmount span,"'
                             '+this._mainPanelSelector+" .premiumAmount span")')
WALLET_FEEDBACK = 'this._startFeedbackAnimation("#modules-lobby-wallet-container .premiumAmount",'
WALLET_FEEDBACK_FIXED = ('this._startFeedbackAnimation($("#lobby-index-premium-wallet .premiumAmount")'
                         '.length?"#lobby-index-premium-wallet .premiumAmount"'
                         ':"#modules-lobby-wallet-container .premiumAmount",')
WALLET_EVENT_AMOUNT = 'this._$premiumCash.html(this._newAmount)'
WALLET_EVENT_AMOUNT_FIXED = 'this._$premiumCash.html($.views.helpers.formatCurrency(this._newAmount))'

# 8. Preis je SkuCode aus dem Fenster, das ihn mit Rabatt kennt
REMEMBER_PRICE = ('(function(){var p={};'
                  '$.views.helpers("rememberPrice",function(s,a){p[s]=a;return a});'
                  '$.views.helpers("rememberedPrice",function(s,a){return p.hasOwnProperty(s)?p[s]:a})})();')
ACHIEVEMENT_HELPER = "@ACHIEVEMENT_BLINGS@"  # ersetzt files() je Stand
SKU_PRICE = '<span class="currency-value">{{:CurrencyAmount.Amount}}</span>'
CONFIRM_PRICE = ('<span class="amount">{{:ShopProduct.Skus[ShopProduct.Skus.length-1]'
                 '.ActualPrice.Amount}}</span>')

# 10. Kaufknopf im Helden-Fenster
HERO_BUY_LINK = '<a href="game://shop/buySku?skuCode={{:SkuCode}}" class="buy" sku-code="{{:SkuCode}}">'

# 13. Region 10 on the region map. The Steam UI is newer than the 2014 copy
# in client/ (map 1920x1008, other positions and island images), so this
# patch starts from the Steam files in server/data/steam (see original()).
# The gold island fills the gap between Upper Bestmount (9) and Stabbinshire
# (8); the tint is baked into the images (png_tint.py, data URIs).
STEAM_BASE = pathlib.Path(__file__).resolve().parent / "data" / "steam"
REGION10_ID, REGION10_BOSS = 10, 60999
REGION10_LEVEL_MIN, REGION10_LEVEL_MAX = 35, 60
REGION10_LEFT, REGION10_TOP = 1265, 25      # base coordinates (1920x1008 map)
REGION10_W, REGION10_H = 210, 420           # ZONE7 (218x436) slightly smaller
REGION10_ANCHOR = "#region-selection-container .map-level-9{"
REGION10_CSS = "/*REGION10_CSS*/"           # replaced in files()
_ZONE = "Data/Generated/Web/ATTACKSELECTION/ZONE7/ZONE7%s.PNG"
# Upper Bestmount's dragon medallion (ZONE9) on the island instead of
# Glimmering Valley's skull: ring centers found by their green pixels
_DRAGON = "Data/Generated/Web/ATTACKSELECTION/ZONE9/ZONE9%s.PNG"
_MEDALLION = dict(center_base=(113, 283), center_top=(191.5, 282), rx=72, ry=49, feather=5)
# boss medallion of region 10 in the castle selection (bossId-<castle id>):
# Dragonificus' (castle 20) tinted gold
BOSS10_ANCHOR = ("#attack-castleSelector #attack-castleSelector-boss-panel .boss "
                 ".button.bossId-20{")
BOSS10_CSS = "/*BOSS10_CSS*/"
POPUP10_ANCHOR = "#castle-popup .main-panel .header .builder-info .name .boss-icon.boss-id-20{"
POPUP10_CSS = "/*POPUP10_CSS*/"
_BOSS_ICON = "Data/Generated/Web/hud/btnRegions/HUD_AURFEROUSCIRCLE.PNG"


def _gold(rel, strength=1.0, png=None):
    png = png if png is not None else (STEAM_BASE / rel).read_bytes()
    return png_tint.data_uri(png_tint.tint_gold(png, strength))


def _island(suffix, strength=1.0):
    """Region 10 island: ZONE7 with the dragon medallion of ZONE9, gold."""
    disabled = {"_DISABLED": "_DISABLED"}.get(suffix, suffix)
    png = png_tint.paste_ellipse((STEAM_BASE / (_ZONE % suffix)).read_bytes(),
                                 (STEAM_BASE / (_DRAGON % disabled)).read_bytes(), **_MEDALLION)
    return _gold(None, strength, png)


# 17. co-op raids: Warlord's Keep (raids.BOSS_ID) with Little Spitaly's boss
# medallion in purple (without it the region banner showed a blank silhouette)
_RAID_BOSS_ICON = pathlib.Path(__file__).resolve().parent.parent / "client/GameData/Data/Generated/Web/HUD/BTNREGIONS/PANEL_SNOTTERCIRCLE.PNG"


@functools.lru_cache(maxsize=1)
def _raid_boss_icon():
    """Co-op emblem: the friends icon of the region's island (ZONE1, 234 x
    300, icon at about x 70-138, y 182-224), square crop, purple."""
    w, h, rows = png_tint.decode((_ZONE1 / "ZONE1.PNG").read_bytes())
    x0, y0, size = 58, 157, 92
    crop = [bytes(rows[y][4 * x0:4 * (x0 + size)]) for y in range(y0, y0 + size)]
    png = png_tint.encode(size, size, [bytearray(r) for r in crop])
    emblem = png_tint.tint_color(png, png_tint.PURPLE, 0.85)
    # 2026-11-23: the bare 92 px square, stretched to the button width, was
    # far too big. The boss buttons are 214 x 480 strips of four 120 px
    # states (normal, hover, pressed, disabled) with a ~104 px medallion
    # centered at x 113 (like PANEL_SNOTTERCIRCLE): same layout here, the
    # emblem on a round purple medallion with a gold rim.
    return png_tint.data_uri(_medallion_strip(png_tint.fit(emblem, 78, 78, 0.04)))


def _medallion_strip(emblem_png, w=214, frame=120, cx=113, radius=52):
    ew, eh, em = png_tint.decode(emblem_png)
    out = [bytearray(4 * w) for _ in range(4 * frame)]
    looks = [(1.0, False), (1.18, False), (0.85, False), (1.0, True)]
    for k, (light, grey) in enumerate(looks):
        cy = k * frame + frame // 2
        for y in range(cy - radius - 1, cy + radius + 2):
            row = out[y]
            for x in range(cx - radius - 1, cx + radius + 2):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if d > radius + 0.5:
                    continue
                a = 255 if d <= radius - 0.5 else round(255 * (radius + 0.5 - d))
                if d > radius - 6:                         # gold rim
                    col = (236, 182, 52) if d > radius - 3 else (160, 104, 22)
                else:                                      # purple glow
                    t = (d / (radius - 6)) ** 2
                    col = tuple(round(c0 + (c1 - c0) * t) for c0, c1 in zip((150, 96, 220), (58, 22, 104)))
                row[4 * x:4 * x + 4] = bytes(list(col) + [a])
        ox, oy = cx - ew // 2, cy - eh // 2 + 2
        for y in range(eh):
            src, dst = em[y], out[oy + y]
            for x in range(ew):
                a = src[4 * x + 3] / 255
                if a:
                    i = 4 * (ox + x)
                    for c in range(3):
                        dst[i + c] = round(dst[i + c] * (1 - a) + src[4 * x + c] * a)
        for y in range(cy - frame // 2, cy + frame // 2):            # state look
            row = out[y]
            for i in range(0, 4 * w, 4):
                if row[i + 3]:
                    r, g, b = row[i:i + 3]
                    if grey:
                        r = g = b = round(0.3 * r + 0.59 * g + 0.11 * b)
                    row[i:i + 3] = bytes(min(255, round(v * light)) for v in (r, g, b))
    return png_tint.encode(w, 4 * frame, out)


@functools.lru_cache(maxsize=1)
def boss10_css():
    import level60
    import raids
    return ("#attack-castleSelector #attack-castleSelector-boss-panel .boss .button.bossId-%d{"
            "background:url('%s') top left no-repeat;background-size:100%% auto}"
            % (level60.BOSS_CASTLE_ID, _gold(_BOSS_ICON))
            + "#attack-castleSelector #attack-castleSelector-boss-panel .boss .button.bossId-%d{"
            "background:url('%s') top left no-repeat;background-size:100%% auto}"
            % (raids.BOSS_ID, _raid_boss_icon()))


@functools.lru_cache(maxsize=1)
def popup10_css():
    import level60
    import raids
    return ("#castle-popup .main-panel .header .builder-info .name .boss-icon.boss-id-%d{"
            "background:url('%s') top left no-repeat;background-size:100%% auto}"
            % (level60.BOSS_CASTLE_ID, _gold(_BOSS_ICON))
            + "#castle-popup .main-panel .header .builder-info .name .boss-icon.boss-id-%d{"
            "background:url('%s') top left no-repeat;background-size:100%% auto}"
            % (raids.BOSS_ID, _raid_boss_icon()))


@functools.lru_cache(maxsize=1)
def region10_css():
    sel = "#region-selection-container "
    w, h = REGION10_W, REGION10_H
    cx, cy = _medallion_center()
    size = "background-size:%dpx %dpx" % (w, h)
    return (
        sel + ".castle-position-10{position:absolute;-webkit-box-align:center;-webkit-box-pack:start;"
        "display:-webkit-box;-webkit-box-orient:vertical;width:%dpx;height:%dpx;left:%dpx;top:%dpx}"
        % (w, h, REGION10_LEFT, REGION10_TOP)
        + sel + ".castle-10{position:relative;background:url('%s') no-repeat;%s;width:%dpx;height:%dpx}"
        % (_island(""), size, w, h)
        + sel + ".castle-10:hover{transition:background 0.35s linear;background:url('%s') no-repeat;%s}"
        % (_island("OVER"), size)
        + sel + ".castle-10[disabled=disabled]:not(.unlock-anim-castle){background:url('%s') no-repeat;%s}"
        % (_island("_DISABLED", 0.45), size)
        + sel + ".castle-10.unlock-anim-castle{-webkit-animation:castle-unlock-animation 0.6s}"
        + sel + ".castle-flash-10{width:600px;height:300px;position:absolute;"
        "background:url('http://localhost/gamedata/Generated/Web/HUD/LEVELUPFX/LEVELUPFX.PNG') no-repeat;"
        "pointer-events:none;display:none;margin-left:%dpx;margin-top:60px}" % ((w - 600) // 2)
        + sel + ".castle-flash-10.unlock-anim-flash{display:inline;"
        "-webkit-animation:castle-unlock-animation-flash 0.33s}"
        + sel + ".banner-position-10{height:0px;margin-top:-130px;margin-left:0px}"
        + sel + ".checkmark-10{width:60px;height:60px;left:%dpx;top:%dpx;position:absolute}"
        % (cx + 11, cy - 65)
        + sel + ".map-level-10{width:72px;height:53px;left:%dpx;top:%dpx;position:absolute}"
        % (cx - 88, cy - 42))


# 17. Co-op raids (raids.py): region 11 on the map, the Friendzone island
# (ZONE1, friends medallion) tinted purple, right of Competitions
REGION11_LEFT, REGION11_TOP = 1570, 492
# bottom row moved left to make room (owner's request 2026-11-22):
# {region: (left, top)} of castle-position-N, map arrows with them
BOTTOM_ROW = {3: (45, 471), 5: (360, 326), 4: (540, 500), 1: (930, 550), 2: (1265, 450)}
ARROWS_LEFT = {4: 340, 5: 580}
# top row: Upper Bestmount (9), Splendorado (10) and Stabbinshire (8) sat
# too close together (owner's request 2026-11-23): 9 moves left (950 ->
# 890), 8 moves right (1450 -> 1520); Splendorado stays in the middle
TOP_ROW = {9: 890, 8: 1520}
REGION11_W, REGION11_H = 230, 295               # ZONE1 is 281x360
_ZONE1 = pathlib.Path(__file__).resolve().parent.parent / "client/GameData/Data/Generated/Web/ATTACKSELECTION/ZONE1"


def _purple(name, strength=0.85):
    return png_tint.data_uri(png_tint.tint_color((_ZONE1 / name).read_bytes(), png_tint.PURPLE, strength))


@functools.lru_cache(maxsize=1)
def region11_css():
    sel = "#region-selection-container "
    w, h = REGION11_W, REGION11_H
    size = "background-size:%dpx %dpx" % (w, h)
    return (
        sel + ".castle-position-11{position:absolute;-webkit-box-align:center;-webkit-box-pack:start;"
        "display:-webkit-box;-webkit-box-orient:vertical;width:%dpx;height:%dpx;left:%dpx;top:%dpx}"
        % (w, h, REGION11_LEFT, REGION11_TOP)
        + sel + ".castle-11{position:relative;background:url('%s') no-repeat;%s;width:%dpx;height:%dpx}"
        % (_purple("ZONE1.PNG"), size, w, h)
        + sel + ".castle-11:hover{transition:background 0.35s linear;background:url('%s') no-repeat;%s}"
        % (_purple("ZONE1OVER.PNG"), size)
        + sel + ".castle-11[disabled=disabled]:not(.unlock-anim-castle){background:url('%s') no-repeat;%s}"
        % (_purple("ZONE1_DISABLED.PNG", 0.5), size)
        + sel + ".castle-flash-11{display:none}"
        + sel + ".banner-position-11{height:0px;margin-top:-60px;margin-left:-20px}"
        + sel + ".checkmark-11{display:none}"
        + sel + ".map-level-11{width:72px;height:53px;left:18px;top:150px;position:absolute}"
        + sel + ".castle-11::after{content:'Procedural';position:absolute;left:0;right:0;top:%dpx;"
        "text-align:center;font-family:Verdana;font-size:11px;font-style:italic;color:#f3e6ff;"
        "text-shadow:0 0 3px #2a0b4a,0 0 3px #2a0b4a,0 0 3px #2a0b4a;pointer-events:none}" % (h - 70)
        + "".join(sel + ".castle-position-%d{left:%dpx;top:%dpx}" % (r, x, y) for r, (x, y) in BOTTOM_ROW.items())
        + "".join(sel + ".arrow-position-%d{left:%dpx}" % (r, x) for r, x in ARROWS_LEFT.items())
        + "".join(sel + ".castle-position-%d{left:%dpx}" % (r, x) for r, x in TOP_ROW.items()))


def _medallion_center():
    """Center of the dragon medallion on the (scaled) region 10 island. The
    level badge sits left of it and the checkmark top right, like on Upper
    Bestmount (map-level-9: 88 px left / 42 px above the medallion center,
    checkmark-9: 11 px right / 65 px above); centered, the "35-60" badge
    covered the dragon."""
    x, y = _MEDALLION["center_base"]
    return int(x * REGION10_W / 218 + 0.5), int(y * REGION10_H / 436 + 0.5)


STATIC_FILES = [
    # 1.
    ("Js/modules/attackSelection/CastleCompetitionPopUpModule.js",
     [("Level:a.HeroLevel", "Level:a.CastleLevel")]),
    # 3.
    ("Js/modules/forge/forgeModule.js", [(FORGE_ANCHOR, FORGE_ANCHOR + (
        "if(exists(b)&&exists(b.ItemSlotModel)&&exists(b.ItemSlotModel"
        ".EquippedItemModel)&&b.ItemSlotModel.EquippedItemModel.ItemSlot==8){try{"
        "hyperquest.ui.messageBox.show({Id:hyperquest.enums.MessageBoxIds."
        "NotEnoughCraftingMaterials,Type:hyperquest.enums.MessageBoxButtonConfig.Ok,"
        "Title:\"Blacksmith\",Text:\"You are reforging your equipped weapon. It stays "
        "equipped until you collect the new one. The new weapon will only be equipped "
        "after your next mode switch; until then, both weapons may be shown. To swap, "
        "drag the new weapon onto the weapon slot.\"})}catch(x){}}"))]),
    # 7.
    ("Js/hyperquest.extensions.js", [
        ('$.views.helpers("enumValueCompare",function(c,a,b){var d=$.views.helpers.getEnumName(c,b);return d===a});',
         '$.views.helpers("enumValueCompare",function(c,a,b){var d=$.views.helpers.getEnumName(c,b);return d===a||c===a});'),
        # 8., 9.
        ('$.views.helpers("enumValueCompare",',
         REMEMBER_PRICE + ACHIEVEMENT_HELPER + '$.views.helpers("enumValueCompare",')]),
    # 6.
    ("Js/modules/profile/playerInteractionModule.js", [
        ('"&attackType="+getEnumName(this._playerInteractionModel.AttackType,'
         '"hyperquest.enums.AttackType")',
         '"&attackType=None"')]),
    # 13.
    ("Css/modules/attackSelection/regionSelectionModule.css", [
        (REGION10_ANCHOR, REGION10_CSS + REGION10_ANCHOR)]),
    ("Css/modules/attackSelection/castleSelectorModule.css", [
        (BOSS10_ANCHOR, BOSS10_CSS + BOSS10_ANCHOR)]),
    ("Css/modules/attackSelection/CastlePopUp.css", [
        (POPUP10_ANCHOR, POPUP10_CSS + POPUP10_ANCHOR)]),
    # 14.
    ("Js/modules/lobby/friendNotificationsModule.js", [
        ("var FriendNotificationsModule=", FRIENDS_ONLINE_JS + "var FriendNotificationsModule="),
        ("a.html(e.render(this._friends));",
         "a.html(e.render(this._friends));window.mqelFriendsOnline&&mqelFriendsOnline(a);")]),
    # 5., 11.
    # (11.: the 2015 lobbyWalletModule.js already looks in
    # #lobby-index-premium-wallet and formats the amount; the WALLET_*_FIXED
    # patches were for the 2014 copy in client/ and are no longer needed)
    ("Js/modules/lobby/lobbyWalletModule.js", [
        (WALLET_COUNT_UP, "")]),
]


def online_urls():
    """Addresses the friend list asks for online status (14.)."""
    port = os.environ.get("MQEL_GAME_PORT", "").strip() or "8081"
    urls = ["http://127.0.0.1:%s" % port]
    host = os.environ.get("MQEL_PUBLIC_HOST", "").strip()
    if host and host not in ("127.0.0.1", "localhost"):
        urls.append("http://%s:%s" % (host, port))
    return urls


def files(game_data, blings=None):
    """[(Pfad unter Data/UI, [(alt, neu[, "alle"]), ...]), ...]; blings:
    JSON {Achievement-Id: Blings} für den Helfer achievementBlings (9.),
    None = Bling-Wirtschaft aus (9. entfällt)."""
    ui = game_data / "Data/UI"
    helper = "" if blings is None else (
        '$.views.helpers("achievementBlings",function(i){var m=%s;'
        'return m[i]||0});' % blings)
    region10 = region10_css() + region11_css()
    static = [(path, [(old, new.replace(ACHIEVEMENT_HELPER, helper)
                       .replace(REGION10_CSS, region10)
                       .replace(BOSS10_CSS, boss10_css())
                       .replace(POPUP10_CSS, popup10_css())
                       .replace("MQEL_ONLINE_URLS", json.dumps(online_urls()))) + tuple(rest)
                      for old, new, *rest in patches])
              for path, patches in STATIC_FILES]
    return static + [
        (str(p.relative_to(ui)), topview_patches(game_data, p.parent.name, p, blings is not None))
        for p in sorted((ui / "Html").glob("*/TopView*.html"))]


def original(path):
    """Unpatched content of `path` (under GameData/Data/UI): the Steam file
    from server/data/steam if there is one (13.), else <path>.orig or the
    file itself."""
    parts = pathlib.Path(path).parts
    if "Data" in parts:
        steam = STEAM_BASE.joinpath(*parts[len(parts) - parts[::-1].index("Data") - 1:])
        if steam.exists():
            return steam
    orig = path.with_name(path.name + ".orig")
    return orig if orig.exists() else path


def patched(game_data):
    """{Pfad unter GameData ("Data/UI/..."): gepatchter Inhalt}; ValueError,
    wenn ein Anker fehlt (andere UI-Version). Hängt von den
    Achievement-Blings ab (balance.py)."""
    blings = balance.ui_achievement_blings() if balance.enabled() else None
    return _patched(str(game_data), None if blings is None else json.dumps(blings, sort_keys=True))


@functools.lru_cache(maxsize=4)
def _patched(game_data, blings):
    game_data = pathlib.Path(game_data)
    out = {}
    for rel, patches in files(game_data, blings):
        path = game_data / "Data/UI" / rel
        text = original(path).read_text(encoding="utf-8")  # Zeilenenden \n
        patched_anything = False
        for old, new, *every in patches:
            count = text.count(old)
            if count == 0:
                print(f"Warning: Anchor not found in {path}, skipping patch")
                continue  # Skip this patch instead of raising an error
            elif count > 1 and not every:
                print(f"Warning: Anchor found {count} times in {path}, expected 1")
                continue  # Skip this patch if anchor appears multiple times unexpectedly
            text = text.replace(old, new)
            patched_anything = True
        out["Data/UI/" + rel.replace("\\", "/")] = text.encode("utf-8")
    return out
