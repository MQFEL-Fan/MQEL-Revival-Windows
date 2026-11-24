"""Level-60 update: hero level cap 30 -> 60 (docs/90-level60.md).

One set of rules, applied to the gameplay-settings JSONs:
- for the client: patcher.py rebuilds settings.bin from the Steam original
  with these edits (DataBin version part L<CRC>, see version());
- for the server: tools/apply_level60.py writes the same edited JSONs into
  client/GameData/Data/GameplaySettings (the loose copies the server reads),
  always from the untouched files inside settings.bin.

What changes (each function below says why):
- HeroSettings: XP table and level requirements up to 60.
- Hero skills: every skill gets 5 ranks (the skill tree draws 5 slots, the
  data had 2-3); new ranks continue the step between the last two ranks,
  unlocked every 12 levels up to 60 (also through spawned creatures'
  abilities and helper abilities; flat skills get boosted damage). Trap
  skills: cooldown 10 s -> 7.5 s over the 5 ranks.
- Castle heart: ranks 31-60 (defense rating up to 750, gold/bling SKUs);
  gold/life force storage rank 6 (1,000,000) with castle heart 60;
  Architect's Office ranks 7/8 (9/10 rooms) with four new room types;
  gold/life force mines ranks 12/13, one more mine of each kind at heart
  35 and 55; craftable Goldmaw (gold Dragonificus) with heart 60.
- Boss pictures of region 10 / Goldmaw (UIGLOBALSETTINGS).
- Creature/trap tiers continued up to level 60, so monsters in level 35-60
  castles reach the castle level.
- Item templates whose range ended at 30 go up to 60 (not default gear,
  not cosmetics); shop filters, forge/drop/resurrection ranges to 60.
- New attack region 10 (levels 35-60) with its own name and boss; its NPC
  castles and fake players come from region_castles() (server only, the
  client gets castles from the server).
"""

import copy
import functools
import glob
import json
import os
import re
import zlib

CAP = 60
OLD_CAP = 30
ENABLED = os.environ.get("MQEL_LEVEL60", "1") != "0"

REGION_ID = 10
REGION_LEVELS = (35, CAP)
# New Oasis texts (ids above the highest used one, 16781)
OASIS = {
    16782: "Splendorado",                 # region name
    16783: "Goldmaw the Insatiable",      # region boss
    16784: "Goldmaw's Hoard",             # boss castle
    16785: "All That Glitters",           # quest title (objective 105)
    16786: "Splendorado's gold has a keeper. When you feel ready, defeat "
           "Goldmaw the Insatiable in Goldmaw's Hoard.",
    16787: "Defeat Goldmaw the Insatiable.",
}
GILDED_FIRST_ID = 16790                   # names of the region's castles
REGION_POS = (1165, 470)                  # OverPosX/Y (map hover position)
BOSS_SOURCE = 20                          # Black Dragon castle as template
CASTLE_ID_BASE = 60000                    # region castles: 60000 + level*10 + k
BOSS_CASTLE_ID = 60999
CASTLES_PER_LEVEL = 2
# castle levels of region 10 (the 3D selection has 5 rings: two levels per
# ring, castles.MAX_LEVEL_RINGS); level 60: 2 castles plus the boss
REGION_CASTLE_LEVELS = (35, 37, 40, 43, 45, 47, 50, 53, 55, 57, 60)
# the client gets LevelMax 39 for region 10: the 3D selection puts the hero's
# tower on ring min(hero level, LevelMax) - LevelMin; with 60 a level-60
# hero stood 25 rings above the castles, outside the sky. The UI shows
# "35-60" anyway (ui_patches 14.), the server uses REGION_LEVELS.
CLIENT_LEVEL_MAX = REGION_LEVELS[0] + 4
# Region boss: a copy of the Black Dragon (creature 432, one tier at level
# 34) named Goldmaw, level 60, more health; its quest like 104 (Dragonificus)
GOLDMAW_ID = 1200                         # creature ids end at 1156
GOLDMAW_SOURCE = 432
GOLDMAW_HEALTH = 1.5
GOLDMAW_DAMAGE = 1.25
# gold look: the yellow weapon-glow material as a persistent overlay (like
# the elite creatures' overlay); there is no gold dragon model
GOLDMAW_GLOW = "DB:>RAW>MATERIALS>MATERIAL_7449040D_AG673.MATERIAL"
GOLDMAW_OBJECTIVE = 105

SKILL_RANKS = 5
SKILL_STEP = 12                           # levels between skill ranks
HAWK_HACK = 1373
# trap skills of all four heroes (Runaway, Mage, Knight, Archer = Hawk: Hack):
# cooldown 10 s at rank I down to 7.5 s at rank V (originally 0.5 s); the
# trap disable itself stays 5 s (Hawk: Hack: Effect 499)
TRAP_SKILLS = (1370, 1371, 1372, HAWK_HACK)
TRAP_COOLDOWN = (10.0, 7.5)
HAWK_HACK_COOLDOWN = TRAP_COOLDOWN[0]
# skills whose original ranks are equal in every number (only the hero's
# damage grows): new ranks get BOOST_STEP x the tooltip's damage values more
# per rank (Thunderclap 0.2 -> 0.23 -> 0.26 -> 0.29 x hero DPS)
BOOST_STEP = 0.15
# Teen Spirit (1306): all 3 ranks used buff 731 (+10 % damage), while the
# tooltip of rank II already showed buff 732 (+12 %, bonus 6 s); rank II
# uses 732, ranks III-V continue 731 -> 732
TEEN_SPIRIT = 1306
TEEN_SPIRIT_BUFFS = (731, 732)

# Gold/life force storage rank 6 (1,000,000) with castle heart rank 60
STORAGES = (3, 4)
STORAGE6_CAPACITY = 1000000
STORAGE6_HEART = CAP
STORAGE6_GOLD = 250000                    # gold, under the 500,000 of rank 5
STORAGE6_BLINGS = 1200
# castle heart: defense rating (MaxConstructionPoints) 375 at 30 -> 750 at 60
HEART_CP_TOP = 750
# Architect's Office ranks 7/8: (MaxRooms, castle heart rank, gold, blings);
# rank 6 = 8 rooms. The rank-7 SKUs exist (unused), rank 8 gets new ones.
ARCHITECT = 13
ARCHITECT_RANKS = ((9, 40, 350000, 1250), (10, 50, 450000, 1500))
# new room types per office rank: rooms of Ubisoft's PVE castles with shop
# icons and inactive SKUs (14399, 14602, 14397, 14606), price in gold
ARCHITECT_ROOMS = {7: ((7093, 10000), (7098, 10000)),   # Cross Chamber 04, Linear Chamber 07
                   8: ((7094, 20000), (7102, 20000))}   # Cross Chamber 05, Junction Chamber 04
# the room cards come only from the game's packed texture atlas (LayerName;
# loose files are not read: tested 2026-11-21 with transparent and RGB card
# files). Cross Chamber 04/05 have no atlas picture, so they showed the
# wardrobe (UIGLOBALSETTINGS DefaultIconLayerName "UI_Invalid:InvalidIcon").
# They get the atlas picture of the most similar cross room instead.
ROOM_ATLAS_PICTURE = {7093: "icoShop_rooms:Cross_Hall_01",    # plus shape
                      7094: "icoShop_rooms:Cross_Hall_06"}    # hook-shaped inner wall
ROOMS_ICON_FILE = tuple(ROOM_ATLAS_PICTURE)
CARD_ART = (46, 40, 192, 152)             # picture box of the 330x192 creature cards
# gold/life force mines ranks 12/13: (castle heart rank, production per
# 5 min, capacity, gold, blings); rank 11 = 49 / 24,000 at heart 30
MINES = (5, 6)
# (rank 9-11: 40,000 / 56,000 / 75,000 gold, 850 blings)
MINE_RANKS = ((38, 58, 36000, 150000, 1200), (52, 68, 50000, 250000, 1600))
# one more gold, life force and bling mine at castle heart 35 and 55
BLING_MINE = 16
MINE_INSTANCE_HEARTS = (35, 55)
# craftable region-10 boss "Goldmaw the Insatiable": a gold copy of
# Dragonificus Terribilis (creature 1067, crafting lab SKU 14698: 129,000
# life force + materials), stronger, twice the price, needs crafting lab
# (Summoning Portal, building 10) rank 15, which needs castle heart 60
DRAGON_ID = 1201
DRAGON_SOURCE = 1067
DRAGON_SKU = 14698
DRAGON_HEALTH = 1.5
DRAGON_DAMAGE = 1.3
DRAGON_CP = 30                            # Dragonificus: 26
DRAGON_PRICE = 2                          # x life force and materials
DRAGON_NAME, DRAGON_DESC = 16783, 16851     # name = the region boss's
OASIS[DRAGON_DESC] = ("Splendorado's golden dragon, now guarding your castle: tougher "
                      "scales, harder bites, and an even worse temper.")
# picture: the crafting lab card is a file set Generated/shopicons/<layer
# path>_<size>.png plus <...>lock_<size>.png (silhouette while locked; without
# it the client draws a wardrobe). New files can't be shipped safely (the
# launcher's .new fails if the file exists, .replace if it's missing), so the
# one unused set of the game, "missflameo", gets Dragonificus' card in gold
# (dragon_icon_files)
DRAGON_ICON = ("UI/Common/CreaturesIcons/Rares/missflameo.png",
               "UI/Common/CreaturesIconsInv/Rares/missflameo.png",
               "UI_Common_CreaturesIcons_Rares:missflameo")
PORTAL = 10                               # crafting lab
PORTAL_RANK15 = (CAP, 300000, 1000)       # castle heart, gold, blings (14: 220,000)
NEW_SKU_FIRST_CODE = 72000                # 72000.. (forge SKUs end at 71599)
# region 10 fake players: an older region boss in the throne room instead of
# Goldmaw / the Black Dragon (Goldmaw stays in Goldmaw's Hoard only)
OLD_REGION_BOSSES = (1060, 1077, 429, 1061, 431, 430, 432)

HEART_SKU_GOLD_STEP = 13700               # like the unused ranks 31/32
HEART_SKU_FIRST_CODE = 60000              # 60031..60060 gold, 61031..61060 blings
XP_GROWTH = 1.06                          # XP per level grows 6 % per level


# --------------------------------------------------------------------------
# helpers

def _ext(values, n, step=None):
    """Continue a list of numbers to n entries with the last difference."""
    out = list(values)
    d = step if step is not None else (out[-1] - out[-2] if len(out) > 1 else 0)
    while len(out) < n:
        out.append(out[-1] + d)
    return out


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# keys never extrapolated when adding skill ranks
_KEEP_KEYS = {"HeroMinimumLevel", "Cooldown", "PrepareTime", "RecoverTime",
              "RecoverInterruptWindow", "OasisName", "OasisShortDescription",
              "OasisLongDescription", "OasisDescription", "Tier", "Tag",
              "AbilitySlotIndex", "FamilyId", "MaxDistance", "EffectRadius"}


def _keep(key):
    # intervals (ticks, arrows per volley) stay: a longer interval means
    # fewer hits, which would make the new ranks weaker
    return (key in _KEEP_KEYS or key.endswith("Id") or key.endswith("Ids")
            or "SpecContainer" in key or key.endswith("RefId") or "Interval" in key)


_REF_SUFFIX = "SpecContainerRef, "  # e.g. "...EffectSpecContainerRef, HyperQuest..."
_DEFAULTS = {"Multiplier": 1.0}     # StatValueSpec without Multiplier = 1.0


def _top(kind):
    """Settings folder of a spec kind: Effect -> Effects, Ability -> Abilities."""
    return kind[:-1] + "ies" if kind.endswith("y") else kind + "s"


def _ref_kind(d):
    """Folder kind of a spec reference ({"$type": "...EffectSpecContainerRef",
    "SpecContainerReferenceId": 34} -> "Effect"), else None."""
    t = d.get("$type", "")
    if "SpecContainerReferenceId" not in d or _REF_SUFFIX not in t:
        return None
    return t.split(_REF_SUFFIX)[0].split(".")[-1]


def extrapolate(prev, last, k, key="", forge=None):
    """Value k steps after `last`, continuing prev -> last. Anything that
    isn't a matching number (ids, texts, different structures) stays as in
    `last`; numbers never change sign, chances stay <= 1. With `forge`, a
    spec reference that differs between prev and last (rank 1 -> effect 34,
    rank 2 -> effect 35) points to a new spec continued the same way."""
    if isinstance(last, dict) and isinstance(prev, dict) and forge is not None:
        kind = _ref_kind(last)
        if (kind and _ref_kind(prev) == kind
                and prev["SpecContainerReferenceId"] != last["SpecContainerReferenceId"]):
            new_id = forge.derive(kind, prev["SpecContainerReferenceId"],
                                  last["SpecContainerReferenceId"], k)
            if new_id is not None:
                out = copy.deepcopy(last)
                out["SpecContainerReferenceId"] = new_id
                return out
    if _keep(key):
        return copy.deepcopy(last)
    if isinstance(last, dict) and isinstance(prev, dict):
        # a key the previous rank doesn't have has its default there (Stunning
        # Blow rank I: no Multiplier = 1.0, rank II: 1.2 -> 1.4, 1.6, 1.8)
        return {kk: (extrapolate(prev[kk] if kk in prev else _DEFAULTS[kk], v, k, kk, forge)
                     if kk in prev or (kk in _DEFAULTS and _num(v)) else copy.deepcopy(v))
                for kk, v in last.items()}
    if isinstance(last, list) and isinstance(prev, list):
        # by position; entries the previous rank didn't have stay as they are
        return [extrapolate(prev[i], v, k, key, forge) if i < len(prev) else copy.deepcopy(v)
                for i, v in enumerate(last)]
    if _num(last) and _num(prev):
        d = last - prev
        if prev * last < 0 or abs(last) <= abs(prev):
            # only continue values that grow in size (more damage, stronger
            # slow/defense debuff -0.075 -> -0.1 -> -0.125): a shrinking one
            # (smaller radius, shorter stun ...) would make new ranks weaker
            return last
        v = last + k * d
        if (last > 0 and v <= 0) or (last < 0 and v >= 0):
            return last
        if "Chance" in key and last <= 1:
            v = min(v, 1.0)
        if -1 < last < 0:
            v = max(v, -0.95)  # slows/debuffs as fractions stay below 100 %
        if isinstance(last, int) and isinstance(prev, int):
            return int(round(v))
        return round(v, 4)
    return copy.deepcopy(last)


def _extend_levels(levels, n, forge=None):
    """Per-rank list to n entries: extrapolated from the last two ranks
    (one rank: copies)."""
    out = list(levels)
    if not out:
        return out
    prev = out[-2] if len(out) > 1 else out[-1]
    last = out[-1]
    k = 1
    while len(out) < n:
        out.append(extrapolate(prev, last, k, forge=forge))
        k += 1
    return out


_TAG_NUMBER = re.compile(r"^(.*?)(\d+)$")


def _next_tag(tag, k, rank=None):
    """Tag of a value k ranks later: "Caltrops damage 3" -> "Caltrops
    damage 4"; with `rank` (boosted copies of specs that all ranks share,
    whose tags may have no number or collide) "<tag> R<rank>"."""
    if rank is not None:
        return "%s R%d" % (tag, rank)
    m = _TAG_NUMBER.match(tag)
    return "%s%d" % (m.group(1), int(m.group(2)) + k) if m else None


def _retag(obj, k, created=None, rank=None):
    """Spec tags ("Tag": "Caltrops damage 3") of a new spec k ranks later
    ("Caltrops damage 4"): the skill tooltips find their numbers by these
    tags (UI.JSON TaggedSpec), so ranks IV/V show their own values."""
    if isinstance(obj, dict):
        for key, v in obj.items():
            new = _next_tag(v, k, rank) if key == "Tag" and isinstance(v, str) else None
            if new:
                obj[key] = new
                if created is not None:
                    created.add(new)
            else:
                _retag(v, k, created, rank)
    elif isinstance(obj, list):
        for v in obj:
            _retag(v, k, created, rank)
    return obj


def _retag_ui(obj, k, tags, rank=None):
    """TaggedSpec of a copied tooltip rank -> the new spec's tag, if one
    was made (otherwise the rank-III spec stays the source)."""
    if isinstance(obj, dict):
        for key, v in obj.items():
            if key == "TaggedSpec" and isinstance(v, str):
                for new in (_next_tag(v, k), rank and _next_tag(v, k, rank)):
                    if new and new in tags:
                        obj[key] = new
                        break
            else:
                _retag_ui(v, k, tags, rank)
    elif isinstance(obj, list):
        for v in obj:
            _retag_ui(v, k, tags, rank)
    return obj


_NOT_POWER = re.compile(r"(Oasis\w*|Tag|Name|HeroMinimumLevel|\w*Id)$")


def _numbers(obj, path=""):
    """{path: number} of the values that make a rank stronger (no ids,
    texts or unlock levels)."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not _NOT_POWER.match(k):
                out.update(_numbers(v, path + "/" + k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_numbers(v, "%s[%d]" % (path, i)))
    elif _num(obj):
        out[path] = obj
    return out


def _contains_ref(obj, kind, spec_id):
    if isinstance(obj, dict):
        if _ref_kind(obj) == kind and obj["SpecContainerReferenceId"] == spec_id:
            return True
        return any(_contains_ref(v, kind, spec_id) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_ref(v, kind, spec_id) for v in obj)
    return False


def _slot_index(slot):
    """Ability slot -> position in AbilityManagerSpec.Abilities (the exe's
    enum: Attack, Spell1 ... Spell10)."""
    return int(slot[5:]) if slot and slot.startswith("Spell") else 0


def _ops(obj):
    """All operation dicts of a rank, in a fixed order."""
    out = []
    if isinstance(obj, dict):
        if "Operation" in obj.get("$type", ""):
            out.append(obj)
        for v in obj.values():
            out += _ops(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _ops(v)
    return out


class SpecForge:
    """New effect/missile/buff/... specs for the new skill ranks: a copy of
    the last rank's spec with its numbers continued from the previous
    rank's spec (and, the same way, the specs those reference). Ids from
    700000 up in each folder; folder name "<id> - <name>_R<k>"."""

    FIRST_ID = 700000
    FILE_KINDS = ("GAMEPLAY.JSON", "UI.JSON", "VISUAL.JSON", "AUDIO.JSON")

    def __init__(self, src):
        self.src = src
        self.memo = {}
        self.added = {}       # {archive path: bytes}
        self.next_id = {}
        self.tags = set()     # Tag names of the new specs (tooltips, _retag)
        self._folders = {}    # {top: {id: folder}}

    def _folder(self, top, spec_id):
        folders = self._folders.get(top)
        if folders is None:
            folders = self._folders[top] = {}
            for p in self.src.list(top, None):
                folder = p.split("/")[2]
                if folder[:6].isdigit():
                    folders.setdefault(int(folder[:6]), folder)
        return folders.get(spec_id)

    def _gameplay(self, kind, spec_id):
        folder = self._folder(_top(kind), spec_id)
        if folder is None:
            return None, None
        return folder, self.src.json(self.src.find(_top(kind), folder, "GAMEPLAY.JSON"))

    def _write(self, top, folder, name, gameplay):
        """New spec folder `name`: GAMEPLAY.JSON from `gameplay`, the other
        files copied from `folder`."""
        stored = "%s\\%s" % (top.upper(), name.upper())
        for fname in self.FILE_KINDS:
            p = self.src.find(top, folder, fname, required=False)
            if p is None:
                continue
            data = _dump(gameplay, self.src.raw(p)) if fname == "GAMEPLAY.JSON" else self.src.raw(p)
            self.added["GameplaySettings/%s/%s/%s\\%s" % (top, name, stored, fname)] = data

    # --- numbers of a rank (specs it references resolved), for flat skills

    def resolve(self, obj, depth=0):
        """obj with every spec reference (not abilities) replaced by the
        referenced spec's GAMEPLAY, a few levels deep."""
        if isinstance(obj, list):
            return [self.resolve(v, depth) for v in obj]
        if not isinstance(obj, dict):
            return obj
        out = {k: self.resolve(v, depth) for k, v in obj.items()}
        kind = _ref_kind(obj)
        if kind and kind != "Ability" and depth < 6:
            gp = self._gameplay(kind, obj["SpecContainerReferenceId"])[1]
            if gp is not None:
                out["SpecContainerReferenceId"] = "spec"
                out["spec"] = self.resolve(gp, depth + 1)
        return out

    def flat(self, levels):
        """True if the last two ranks (with the specs they reference) have
        the same numbers: nothing to continue (Thunderclap ranks I and II)."""
        if len(levels) < 2:
            return True
        return _numbers(self.resolve(levels[-2])) == _numbers(self.resolve(levels[-1]))

    # --- boosted copies (flat skills)

    def boost_level(self, last, k, rank):
        """Rank `rank` of a flat skill: the last rank with its damage values
        (StatValueSpec Multiplier, tagged "... damage" values) BOOST_STEP x k
        higher, in boosted copies of the specs that hold them; their tags
        get " R<rank>" (the tooltip copies look for those)."""
        lv = copy.deepcopy(last)
        self._boost_tree(lv, k, rank)
        return _retag(lv, k, self.tags, rank)

    def _boost_tree(self, obj, k, rank):
        changed = False
        if isinstance(obj, list):
            for v in obj:
                changed = self._boost_tree(v, k, rank) or changed
            return changed
        if not isinstance(obj, dict):
            return False
        kind = _ref_kind(obj)
        if kind:
            new = self.boosted(kind, obj["SpecContainerReferenceId"], k, rank)
            if new is None:
                return False
            obj["SpecContainerReferenceId"] = new
            return True
        factor = 1 + BOOST_STEP * k
        if "StatType" in obj and _num(obj.get("Multiplier")) and obj["Multiplier"] > 0:
            obj["Multiplier"] = round(obj["Multiplier"] * factor, 4)
            changed = True
        tag = obj.get("Tag")
        if (_num(obj.get("Value")) and obj["Value"] > 0 and isinstance(tag, str)
                and "damage" in tag.lower()):
            obj["Value"] = round(obj["Value"] * factor, 4)
            changed = True
        for v in obj.values():
            if isinstance(v, (dict, list)):
                changed = self._boost_tree(v, k, rank) or changed
        return changed

    def boosted(self, kind, spec_id, k, rank):
        """Id of a boosted copy of a spec (None if it holds no damage value;
        abilities are never copied)."""
        key = ("boost", kind, spec_id, k)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = None                  # also stops reference loops
        if kind == "Ability":
            return None
        folder, gp = self._gameplay(kind, spec_id)
        if gp is None or not self._boost_tree(gp, k, rank):
            return None
        top = _top(kind)
        new_id = self._alloc(top)
        self._write(top, folder, "%06d - %s_R%d" % (new_id, folder.split(" - ", 1)[1], rank),
                    _retag(gp, k, self.tags, rank))
        self.memo[key] = new_id
        return new_id

    # --- one spec referenced instead of another (Teen Spirit rank II)

    def substitute(self, obj, kind, old, new):
        """obj with references to spec `old` pointing to `new`, also inside
        the specs it references (those become copies)."""
        if isinstance(obj, list):
            return [self.substitute(v, kind, old, new) for v in obj]
        if not isinstance(obj, dict):
            return obj
        ref = _ref_kind(obj)
        if ref == kind and obj["SpecContainerReferenceId"] == old:
            return dict(obj, SpecContainerReferenceId=new)
        if ref and ref != "Ability":
            sid = obj["SpecContainerReferenceId"]
            key = ("subst", ref, sid, kind, old, new)
            if key not in self.memo:
                self.memo[key] = sid
                folder, gp = self._gameplay(ref, sid)
                if gp is not None and _contains_ref(gp, kind, old):
                    top = _top(ref)
                    new_id = self._alloc(top)
                    self._write(top, folder, "%06d - %s_S%d" % (new_id, folder.split(" - ", 1)[1], new),
                                self.substitute(gp, kind, old, new))
                    self.memo[key] = new_id
            return dict(obj, SpecContainerReferenceId=self.memo[key])
        return {k: self.substitute(v, kind, old, new) for k, v in obj.items()}

    # --- creatures a skill spawns (Hawk: Harass/Dive use the GhostHawk's
    # abilities by slot: rank I Attack, II Spell6, III Spell7)

    def entity_ability(self, creature_id, slot):
        """Ability id in a creature's slot ("Attack", "Spell1" ... "Spell10")."""
        gp = self._gameplay("Creature", creature_id)[1]
        for comp in gp or []:
            abilities = comp.get("Abilities") if isinstance(comp, dict) else None
            if "AbilityManagerSpec" in comp.get("$type", "") and abilities:
                i = _slot_index(slot)
                if i < len(abilities):
                    return abilities[i]["SpecContainerReferenceId"]
        return None

    def entity_variant(self, creature_id, slot, ability_id, rank):
        """Copy of a creature with `ability_id` in `slot` (the exe knows
        only the slots Attack, Spell1-Spell10 and the GhostHawk uses all but
        one, so new ranks spawn their own hawk instead of a new slot). Its
        tiers go to 60 like the original's."""
        key = ("entity", creature_id, slot, ability_id)
        if key in self.memo:
            return self.memo[key]
        folder, gp = self._gameplay("Creature", creature_id)
        gp = tiers(gp)
        for comp in gp:
            if isinstance(comp, dict) and "AbilityManagerSpec" in comp.get("$type", ""):
                comp["Abilities"][_slot_index(slot)]["SpecContainerReferenceId"] = ability_id
        new_id = self._alloc("Creatures")
        self._write("Creatures", folder, "%06d - %s_R%d" % (new_id, folder.split(" - ", 1)[1], rank), gp)
        self.memo[key] = new_id
        return new_id

    def _alloc(self, top):
        if top not in self.next_id:
            used = [int(p.split("/")[2][:6]) for p in self.src.list(top, None)
                    if p.split("/")[2][:6].isdigit()]
            self.next_id[top] = max(used + [self.FIRST_ID - 1]) + 1
        n = self.next_id[top]
        self.next_id[top] += 1
        return n

    def derive(self, kind, prev_id, last_id, k):
        key = (kind, prev_id, last_id, k)
        if key in self.memo:
            return self.memo[key]
        top = _top(kind)
        prev_folder, prev_gp = self._gameplay(kind, prev_id)
        last_folder, last_gp = self._gameplay(kind, last_id)
        if prev_gp is None or last_gp is None:
            self.memo[key] = None
            return None
        new_id = self._alloc(top)
        self.memo[key] = new_id
        name = "%06d - %s_R%d" % (new_id, last_folder.split(" - ", 1)[1], k)
        gp = _retag(extrapolate(prev_gp, last_gp, k, forge=self), k, self.tags)
        self._write(top, last_folder, name, gp)
        return new_id


# --------------------------------------------------------------------------
# hero levels

def hero_settings(d):
    """XpPerLevel (cumulative XP per level) and LevelRequirements to 60:
    the XP needed per level keeps growing 6 % per level from the step
    29 -> 30 (381,060 XP), so 60 needs about 32 million XP in total."""
    xp = d["XpPerLevel"]
    step = xp[-1] - xp[-2]
    while len(xp) < CAP:
        step = int(round(step * XP_GROWTH / 100.0)) * 100
        xp.append(xp[-1] + step)
    req = d["LevelRequirements"]
    while len(req) < CAP:
        req.append(copy.deepcopy(req[-1]))
    return d


# --------------------------------------------------------------------------
# skills

def base_ranks(sid, levels):
    """Original ranks the new ones continue from (Teen Spirit: I and II,
    see TEEN_SPIRIT)."""
    return min(2, len(levels)) if sid == TEEN_SPIRIT else len(levels)


def trap_cooldown(rank):
    """Cooldown of a trap skill at rank 1-5: 10 s -> 7.5 s."""
    hi, lo = TRAP_COOLDOWN
    return round(hi - (hi - lo) * (rank - 1) / (SKILL_RANKS - 1), 3)


def _slot_ranks(levels, new, forge):
    """Skills that use an ability of the creature they spawn, by slot, one
    slot per rank (Hawk: Harass Attack/Spell6/Spell7 = HawkScratch 1-3,
    Hawk: Dive Spell1/3/5 = HawkDive 1-3): new ranks spawn a copy of the
    creature whose ability in the last rank's slot is continued from the
    previous rank's ability (HawkScratch 4, 5). True if done."""
    if len(levels) < 2:
        return False
    prev_ops, last_ops = _ops(levels[-2]), _ops(levels[-1])
    if len(prev_ops) != len(last_ops):
        return False
    done = False
    for n, (up, ul) in enumerate(zip(prev_ops, last_ops)):
        if "UseAbilityOperationSpec" not in ul.get("$type", ""):
            continue
        sp, sl = up.get("AbilitySlotIndex", "Attack"), ul.get("AbilitySlotIndex", "Attack")
        saved = (ul.get("Target") or {}).get("Slot")
        if sp == sl or not saved:
            continue
        spawns = [(i, e) for i, o in enumerate(last_ops) for e in o.get("SpawnableEntities") or []
                  if e.get("SaveSpawnedEntitySlot") == saved]
        if not spawns:
            continue
        op_i, entity = spawns[0]
        creature = entity["SpawnableEntitySpecContainerRefId"]
        prev_ab, last_ab = forge.entity_ability(creature, sp), forge.entity_ability(creature, sl)
        if prev_ab is None or last_ab is None:
            continue
        for i in range(len(levels), len(new)):
            k = i - len(levels) + 1
            ability = forge.derive("Ability", prev_ab, last_ab, k)
            if ability is None:
                continue
            ent = next(e for e in _ops(new[i])[op_i]["SpawnableEntities"]
                       if e.get("SaveSpawnedEntitySlot") == saved)
            ent["SpawnableEntitySpecContainerRefId"] = forge.entity_variant(creature, sl, ability, i + 1)
            done = True
    return done


def ability_gameplay(d, sid, forge=None):
    """Hero skill to 5 ranks. New ranks: HeroMinimumLevel = last + 12 per
    rank (max 60), values continued from the last two ranks, including the
    effect/missile/buff specs each rank points to (SpecForge), the abilities
    of spawned creatures (_slot_ranks) and the ranks' own tags (tooltips).
    Skills whose last two ranks have the same numbers get boosted damage
    values instead (BOOST_STEP); trap skills a falling cooldown."""
    spec = d[0]
    levels = spec.get("Levels") or []
    if not levels:
        return d
    mins = [(lv.get("UpgradeRequirement") or {}).get("HeroMinimumLevel", 1) for lv in levels]
    if sid == TEEN_SPIRIT and forge is not None and len(levels) >= 2:
        levels = [levels[0], forge.substitute(levels[1], "Buff", *TEEN_SPIRIT_BUFFS)]
    levels = levels[:base_ranks(sid, levels)]
    new = _extend_levels(levels, SKILL_RANKS, forge)
    n = len(levels)
    if forge is not None and n < len(new):
        slots = _slot_ranks(levels, new, forge)
        flat = not slots and sid not in TRAP_SKILLS and forge.flat(levels)
        for i in range(n, len(new)):
            if flat:
                new[i] = forge.boost_level(levels[-1], i - n + 1, i + 1)
            else:
                _retag(new[i], i - n + 1, forge.tags)
    last_min = mins[n - 1]
    for i in range(n, len(new)):
        last_min = mins[i] if i < len(mins) else min(CAP, last_min + SKILL_STEP)
        new[i].setdefault("UpgradeRequirement", {})["HeroMinimumLevel"] = last_min
    if sid in TRAP_SKILLS:
        for r, lv in enumerate(new, 1):
            lv["Cooldown"] = trap_cooldown(r)
    spec["Levels"] = new
    return d


def ability_side(d, ranks, forge=None):
    """UI/VISUAL/AUDIO of a skill: per-rank lists (tooltips) to 5 entries
    by copying the last one; shared single entries stay. The copies'
    TaggedSpec point to the new ranks' specs (_retag_ui)."""
    tags = forge.tags if forge is not None else set()
    for comp in d:
        lv = comp.get("Levels") if isinstance(comp, dict) else None
        if isinstance(lv, list) and lv and len(lv) >= ranks:
            last, k = lv[-1], 1
            while len(lv) < SKILL_RANKS:
                lv.append(_retag_ui(copy.deepcopy(last), k, tags, len(lv) + 1))
                k += 1
    return d


# --------------------------------------------------------------------------
# castle heart, shop

def rank_lists_ui(ranks):
    """Per-rank lists of a building's UI.JSON (UiBuildingInfoSpec.Ranks,
    icons) and VISUAL.JSON (VisualProgression, one more) to `ranks` with the
    last entry: the client read the icon of castle heart rank 31 from an
    empty slot and crashed opening the heart (MightyQuest.exe+0x85f2ef)."""
    def edit(d):
        for comp in d:
            for key, n in (("Ranks", ranks), ("VisualProgression", ranks + 1)):
                lst = comp.get(key) if isinstance(comp, dict) else None
                if isinstance(lst, list) and lst and len(lst) < n:
                    lst.extend(copy.deepcopy(lst[-1]) for _ in range(n - len(lst)))
        return d
    return edit


heart_ranks_ui = rank_lists_ui(CAP)


def storage(d):
    """Gold/life force storage rank 6: 1,000,000 with castle heart rank 60
    (rank 5: 500,000 at heart 25)."""
    ranks = d[0]["Ranks"]
    if len(ranks) == 5:
        r = copy.deepcopy(ranks[-1])
        r.update(Capacity=STORAGE6_CAPACITY, BuildingRequirementRank=STORAGE6_HEART)
        ranks.append(r)
    return d


def ui_global(d):
    """Boss pictures of region 10 / Goldmaw (UIGLOBALSETTINGS): the square
    badge over the boss castle in the 3D selection (RegionBossPictureLayer
    Names, without "10" the client showed the spider), the castle popup's
    medallion and the boss health bar portrait (BossPictureLayerNames by
    creature, without Goldmaw a skeleton) as Upper Bestmount's gold
    dragon."""
    for key, src, dst in (("RegionBossPictureLayerNames", REGION_ID - 1, REGION_ID),
                          ("CastlePopupRegionBossPictureLayerNames", REGION_ID - 1, REGION_ID),
                          ("RegionBossPictureLayerNames", 3, 11),            # co-op raids
                          ("CastlePopupRegionBossPictureLayerNames", 3, 11),
                          ("BossPictureLayerNames", GOLDMAW_SOURCE, GOLDMAW_ID),
                          ("BossPictureLayerNames", DRAGON_SOURCE, DRAGON_ID)):
        names = d.get(key)
        if isinstance(names, dict) and str(src) in names:
            names.setdefault(str(dst), names[str(src)])
    return d


def castle_heart(d):
    """Ranks 31-60: MaxConstructionPoints (defense rating) evenly from 375
    at 30 to HEART_CP_TOP (750) at 60, +12.5 per rank (a castle has up to
    10 rooms at 60, see architect_office)."""
    ranks = d[0]["Ranks"]
    while len(ranks) < CAP:
        ranks.append(copy.deepcopy(ranks[-1]))
    base = ranks[OLD_CAP - 1]["MaxConstructionPoints"]
    for rank in range(OLD_CAP + 1, CAP + 1):
        ranks[rank - 1]["MaxConstructionPoints"] = int(
            base + (HEART_CP_TOP - base) * (rank - OLD_CAP) / (CAP - OLD_CAP) + 0.5)
    return d


def architect_office(d):
    """Architect's Office ranks 7/8: 9 rooms with castle heart 40, 10 rooms
    with 50 (rank 6: 8 rooms at 29). The client limits the rooms
    (CastleCellGrid, CannotPlaceMoreRooms)."""
    ranks = next(c for c in d if "Ranks" in c)["Ranks"]
    for i, (rooms, heart, _, _) in enumerate(ARCHITECT_RANKS):
        if len(ranks) == 6 + i:
            r = copy.deepcopy(ranks[-1])
            r.update(MaxRooms=rooms, BuildingRequirementRank=heart)
            ranks.append(r)
    return d


def room_requirement(rank):
    """New room types: buildable with Architect's Office `rank`."""
    def edit(d):
        for c in d:
            if c.get("$type", "").startswith("HyperQuest.GameServer.Contracts.BuildingRequirementSpec"):
                c.update(BuildingRequirementSpecContainerId=ARCHITECT, BuildingRequirementRank=rank)
        return d
    return edit


def room_picture(room):
    """UiSpec LayerName of `room` -> the atlas picture ROOM_ATLAS_PICTURE."""
    def edit(d):
        for c in d:
            if c.get("$type", "").startswith("HyperQuest.GameServer.Contracts.UiSpec"):
                c["LayerName"] = ROOM_ATLAS_PICTURE[room]
        return d
    return edit


def mines(d):
    """Gold/life force mines ranks 12 (castle heart 38) and 13 (52), and a
    5th/6th mine with castle heart 35/55 (BuildingInstanceRequirements)."""
    spec = next(c for c in d if "Ranks" in c)
    ranks = spec["Ranks"]
    for i, (heart, value, capacity, _, _) in enumerate(MINE_RANKS):
        if len(ranks) == 11 + i:
            r = copy.deepcopy(ranks[-1])
            r.update(ProductionValue=value, Capacity=capacity, BuildingRequirementRank=heart)
            ranks.append(r)
    return more_mines(d)


def more_mines(d):
    """One more instance with castle heart 35 and one with 55 (gold, life
    force and bling mine; the heart's upgrade window lists them)."""
    spec = next(c for c in d if "BuildingInstanceRequirements" in c)
    inst = spec["BuildingInstanceRequirements"]
    have = {r.get("BuildingRequirementRank") for r in inst}
    for heart in MINE_INSTANCE_HEARTS:
        if heart not in have and inst and "BuildingRequirementRank" in inst[-1]:
            r = copy.deepcopy(inst[-1])
            r["BuildingRequirementRank"] = heart
            inst.append(r)
    return d


def shop_skus(d, shop_plan=()):
    """Castle heart ranks 31-60: gold 72,600 (+13,700 per rank, the prices
    of the unused SKUs 31/32) up to 469,900 (gold storage holds 500,000),
    blings 600 (+25 per rank). Existing SKUs for 31/32 get activated."""
    skus = d["Skus"]
    heart = {(s.get("Price", {}).get("CurrencyType"), s.get("ItemCount")): s
             for s in skus if s.get("ItemType") == 10 and s.get("ItemId") == 1}
    gold30 = heart[(4, 30)]["Price"]["Amount"]
    for rank in range(31, CAP + 1):
        gold = 72600 + (rank - 31) * HEART_SKU_GOLD_STEP
        bling = 600 + (rank - 31) * 25
        for ctype, amount, code in ((4, gold, HEART_SKU_FIRST_CODE + rank),
                                    (1, bling, HEART_SKU_FIRST_CODE + 1000 + rank)):
            s = heart.get((ctype, rank))
            if s is None:
                s = {"Code": str(code), "ItemType": 10, "ItemId": 1, "ItemCount": rank,
                     "ShopContext": 5,
                     "InternalDescription": ("PM " if ctype == 1 else "")
                     + "Castle Heart Rank %d" % rank}
                skus.append(s)
            s["Price"] = {"CurrencyType": ctype, "Amount": amount}
            s["IsActive"] = True
    assert gold30 < 72600
    # storage rank 6: the unused SKUs (gold 10017/10031, blings 12368/12382)
    for s in skus:
        if s.get("ItemType") == 10 and s.get("ItemId") in STORAGES and s.get("ItemCount") == 6:
            ctype = (s.get("Price") or {}).get("CurrencyType")
            if ctype in (1, 2):
                s["Price"] = {"CurrencyType": ctype,
                              "Amount": STORAGE6_BLINGS if ctype == 1 else STORAGE6_GOLD}
                s["IsActive"] = True
    building_skus(skus)
    have = {s["Code"] for s in skus}
    skus += [copy.deepcopy(n) for _, new in shop_plan for n in new if n["Code"] not in have]
    have = {s["Code"] for s in skus}
    skus += [n for n in forge_skus(skus) if n["Code"] not in have]
    # "More castles" (ItemType 14, ItemId = region) for regions 10 and 11
    # (co-op raids): copies of region 9's two SKUs (blings / gold); without
    # them the castle selection shows no reroll button
    have = {s["Code"] for s in skus}
    base = [x for x in skus if x.get("ItemType") == 14 and x.get("ItemId") == REGION_ID - 1]
    for region, first in ((REGION_ID, 72101), (REGION_ID + 1, 72111)):
        for i, src in enumerate(base):
            code = str(first + i)
            if code not in have and not any(x.get("ItemType") == 14 and x.get("ItemId") == region
                                            and x["Price"]["CurrencyType"] == src["Price"]["CurrencyType"]
                                            for x in skus):
                skus.append(dict(copy.deepcopy(src), Code=code, ItemId=region,
                                 InternalDescription="Show More Castle Region %d" % region))
    return d


def _set_price(skus, item_type, item_id, count, gold, blings, gold_type=2, code=None):
    """Activate the SKUs (gold `gold_type` and blings) of an item rank;
    missing ones are created from `code` on."""
    for ctype, amount in ((gold_type, gold), (1, blings)):
        if amount is None:
            continue
        s = next((x for x in skus if x.get("ItemType") == item_type and x.get("ItemId") == item_id
                  and x.get("ItemCount") == count
                  and (x.get("Price") or {}).get("CurrencyType") in ((1,) if ctype == 1 else (2, 4))),
                 None)
        if s is None:
            same = next(x for x in skus if x.get("ItemType") == item_type and x.get("ItemId") == item_id
                        and (x.get("Price") or {}).get("CurrencyType") == ctype)
            s = copy.deepcopy(same)
            s.update(Code=str(code + (ctype == 1)), ItemCount=count,
                     InternalDescription=re.sub(r"\d+$", str(count), same.get("InternalDescription", "")))
            s.pop("Discounts", None)
            skus.append(s)
        s["Price"] = {"CurrencyType": ctype, "Amount": amount}
        s["IsActive"] = True


def building_skus(skus):
    """Prices of the new building ranks, rooms and the gold dragon:
    - Architect's Office 7/8 (ARCHITECT_RANKS; 6 costs 250,000 gold),
    - gold/life force mines 12/13 (MINE_RANKS; 11 costs 75,000 gold; the
      unused SKUs 10051/10052, 10065/10066 ...),
    - the new room types (ARCHITECT_ROOMS),
    - craftable Goldmaw in the crafting lab: Dragonificus' SKU x DRAGON_PRICE."""
    code = NEW_SKU_FIRST_CODE
    for i, (_, _, gold, blings) in enumerate(ARCHITECT_RANKS):
        _set_price(skus, 10, ARCHITECT, 7 + i, gold, blings, code=code)
        code += 2
    for mine in MINES:
        for i, (_, _, _, gold, blings) in enumerate(MINE_RANKS):
            _set_price(skus, 10, mine, 12 + i, gold, blings, code=code)
            code += 2
    _set_price(skus, 10, PORTAL, 15, PORTAL_RANK15[1], PORTAL_RANK15[2], code=code)
    for s in skus:
        if s.get("ItemType") == 10 and s.get("ItemId") == PORTAL and s.get("ItemCount") == 15:
            s["InternalDescription"] = s.get("InternalDescription", "").replace("NOT USED - ", "")
    code += 2
    for rooms in ARCHITECT_ROOMS.values():
        for room, gold in rooms:
            _set_price(skus, 12, room, 1, gold, None, code=code)
            code += 2
    if not any(s.get("ItemType") == 5 and s.get("ItemId") == DRAGON_ID for s in skus):
        src = next(s for s in skus if s["Code"] == str(DRAGON_SKU))
        n = copy.deepcopy(src)
        n.update(Code=str(code), ItemId=DRAGON_ID, IsActive=True,
                 InternalDescription="N_Goldmaw_Craftable_Boss",
                 Price=dict(src["Price"], Amount=src["Price"]["Amount"] * DRAGON_PRICE),
                 CraftingMaterials=[dict(m, Quantity=m["Quantity"] * DRAGON_PRICE)
                                    for m in src.get("CraftingMaterials") or []])
        skus.append(n)
    return skus


FORGE_SKU_TYPES = (16, 17, 24)            # blacksmith craft, reforge, upgrade
FORGE_SKU_FIRST_CODE = 71000


def forge_skus(skus):
    """Blacksmith prices per item level (craft 16, reforge 17, upgrade 24;
    ItemId = rarity, ItemCount = item level, one SKU per currency) up to 60:
    without them the client shows no price for items above 30 and does not
    upgrade/reforge them. Prices continue with the last step (bling prices
    stay), gold/life force at most 450,000."""
    series = {}
    for x in skus:
        if x.get("ItemType") in FORGE_SKU_TYPES and x.get("IsActive") and x.get("Price"):
            key = (x["ItemType"], x["ItemId"], x["Price"]["CurrencyType"])
            series.setdefault(key, {})[x["ItemCount"]] = x
    out, code = [], FORGE_SKU_FIRST_CODE
    for key in sorted(series):
        by_level = series[key]
        if OLD_CAP not in by_level or OLD_CAP - 1 not in by_level:
            continue
        last, prev = by_level[OLD_CAP], by_level[OLD_CAP - 1]
        step = max(0, last["Price"]["Amount"] - prev["Price"]["Amount"])
        for lv in range(OLD_CAP + 1, CAP + 1):
            n = copy.deepcopy(last)
            amount = last["Price"]["Amount"] + step * (lv - OLD_CAP)
            if key[2] != 1:
                amount = min(amount, 450000)
            n.update(Code=str(code), ItemCount=lv,
                     Price=dict(last["Price"], Amount=amount),
                     InternalDescription=re.sub(r"\d+\s*$", str(lv),
                                                last.get("InternalDescription", "")))
            out.append(n)
            code += 1
    return out


def shop_settings(d):
    """Shop filters: hero levels 36-41, 42-47, 48-53, 54-60 and castle
    levels 36-40 ... 56-60 after the last original range."""
    for f in d["Filters"]:
        if f.get("Type") not in ("HeroLevel", "CastleLevel"):
            continue
        vals = f["Values"]
        width = vals[-1]["LevelMax"] - vals[-1]["LevelMin"] + 1
        while vals[-1]["LevelMax"] < CAP:
            lo = vals[-1]["LevelMax"] + 1
            hi = min(CAP, lo + width - 1)
            if CAP - hi < width // 2:
                hi = CAP
            v = copy.deepcopy(vals[-1])
            v.update(LevelMin=lo, LevelMax=hi, Id=vals[-1]["Id"] + 1)
            vals.append(v)
    return d


# --------------------------------------------------------------------------
# ranges that ended at the old cap

def _raise_top(rows, key, old=(29, 30, 34, 35)):
    """Last range of a table (highest `key`) up to 60 if it ended at the
    old cap."""
    tops = [r[key] for r in rows if isinstance(r, dict) and _num(r.get(key))]
    if not tops:
        return
    top = max(tops)
    if top in old:
        for r in rows:
            if isinstance(r, dict) and r.get(key) == top:
                r[key] = CAP


def _walk_lists(o, fn):
    if isinstance(o, dict):
        for v in o.values():
            _walk_lists(v, fn)
    elif isinstance(o, list):
        fn(o)
        for v in o:
            _walk_lists(v, fn)


def raise_ranges(*keys):
    def edit(d):
        for key in keys:
            _walk_lists(d, lambda rows, key=key: _raise_top(rows, key))
        return d
    return edit


XP_ATTACKS_PER_LEVEL = 50                 # 25 gave ~100k for a level-60 castle: too much
TYPICAL_CASTLE_CP = 250                   # creature CP of a PVE castle level 25-60


def attacker_rewards(d, xp_table=None):
    """LootTransfereCostsPerLevel continued (+ last step) to 60. Creature XP
    (construction points x XpLootBaseCpMultiplier of the castle level, the
    multiplier = level, 36 from 36 on): from 31 on the multiplier is the
    XP the level needs / (XP_ATTACKS_PER_LEVEL x TYPICAL_CASTLE_CP), so a
    level takes about 25 attacks on castles of the hero's level (at 30 it
    was ~50; castles below the hero give less: XpModifierTable)."""
    d["LootTransfereCostsPerLevel"] = _ext(d["LootTransfereCostsPerLevel"], CAP)
    if xp_table:
        need = lambda lv: xp_table[lv - 1] - xp_table[lv - 2]  # noqa: E731
        rows = [r for r in d["XpLootBaseCpMultiplierTable"] if r["MaxLevel"] <= OLD_CAP]
        for lv in range(OLD_CAP + 1, CAP + 1):
            rows.append({"MinLevel": lv, "MaxLevel": lv if lv < CAP else 1000,
                         "XpLootBaseCpMultiplier": max(lv, int(round(
                             need(lv) / (XP_ATTACKS_PER_LEVEL * TYPICAL_CASTLE_CP))))})
        d["XpLootBaseCpMultiplierTable"] = rows
    # decoration drops (loot.decoration_loot, 2026-11-22): the client only
    # spawns AttackInfo.DecorationLoot with this on
    d["AllowDecorationLoot"] = True
    return d


DECORATION_LOOTABLE = {
    "$type": "HyperQuest.GameServer.Contracts.LootableSpec, HyperQuest.GameServer.Contracts",
    "OverrideAttackSettingsLootConfig": True, "LootDropMinDistance": 1, "LootDropMaxDistance": 2,
    "LootRadius": 0.25, "LootDropSectorCircleArc": 360,
    # every loot type (traps use 126 for PVP), in PVE castles too
    "PVEDroppableLootTypeMask": 127, "PVPDroppableLootTypeMask": 127}


def decoration_lootable(specs):
    """Decoration GAMEPLAY.JSON (list of specs) + LootableSpec."""
    if not any("LootableSpec" in x.get("$type", "") for x in specs):
        specs = specs + [dict(DECORATION_LOOTABLE)]
    return specs


# --------------------------------------------------------------------------
# forge, build, environments

def forge_settings(d):
    """Blacksmith: items up to level 60 (MaxForgeItemLevel 30 -> 60) and the
    level ranges that ended at 30."""
    d["MaxForgeItemLevel"] = CAP
    return raise_ranges("LevelTo")(d)


def forge_materials(d):
    """Crafting materials per item level (keys "6" ... "30") to 60: +5 per
    5 levels, like 25 -> 30 (18 -> 23)."""
    for cat in d.get("HeroItemCategoryTypeConversionTable", {}).values():
        per = cat.get("PerLevelCraftingMaterialRequirement")
        if not per or str(OLD_CAP) not in per:
            continue
        last = per[str(OLD_CAP)]
        for lv in range(OLD_CAP + 1, CAP + 1):
            n = copy.deepcopy(last)
            n["Amount"] = last["Amount"] + 5 * ((lv - OLD_CAP + 4) // 5)
            per.setdefault(str(lv), n)
    return d


def castle_item_values(d):
    """Castle value of castle heart ranks 31-60 (the table ended at 30; the
    game crashed opening the heart's upgrade at rank 31): + the last step
    per rank."""
    items = d["Items"]
    heart = {x["ItemCount"]: x for x in items
             if x.get("ItemType") == 10 and x.get("ItemId") == 1 and "ItemCount" in x}
    if OLD_CAP in heart and OLD_CAP - 1 in heart:
        step = heart[OLD_CAP].get("Value", 0) - heart[OLD_CAP - 1].get("Value", 0)
        for rank in range(OLD_CAP + 1, CAP + 1):
            if rank not in heart:
                n = copy.deepcopy(heart[OLD_CAP])
                n.update(ItemCount=rank, Value=heart[OLD_CAP]["Value"] + step * (rank - OLD_CAP))
                if "DebugName" in n:
                    n["DebugName"] = re.sub(r"\d+$", str(rank), n["DebugName"])
                items.insert(items.index(heart[OLD_CAP]) + rank - OLD_CAP, n)
    # new building ranks: value of the rank before + its bling price (like
    # the original ranks): storage 6, Architect's Office 7/8, mines 12/13
    new_ranks = [(sid, 6, STORAGE6_BLINGS) for sid in STORAGES]
    new_ranks += [(ARCHITECT, 7 + i, r[3]) for i, r in enumerate(ARCHITECT_RANKS)]
    new_ranks += [(sid, 12 + i, r[4]) for sid in MINES for i, r in enumerate(MINE_RANKS)]
    new_ranks.append((PORTAL, 15, PORTAL_RANK15[2]))
    for sid, rank, blings in new_ranks:
        ranks = {x["ItemCount"]: x for x in items
                 if x.get("ItemType") == 10 and x.get("ItemId") == sid and "ItemCount" in x}
        if rank - 1 in ranks and rank not in ranks:
            prev = ranks[rank - 1]
            n = copy.deepcopy(prev)
            n.update(ItemCount=rank, Value=prev.get("Value", 0) + blings)
            if "DebugName" in n:
                n["DebugName"] = re.sub(r"\d+$", str(rank), n["DebugName"])
            items.insert(items.index(prev) + 1, n)
    # craftable Goldmaw: Dragonificus' value x DRAGON_PRICE
    src = next((x for x in items if x.get("ItemType") == 5 and x.get("ItemId") == DRAGON_SOURCE), None)
    if src and not any(x.get("ItemType") == 5 and x.get("ItemId") == DRAGON_ID for x in items):
        n = copy.deepcopy(src)
        n.update(ItemId=DRAGON_ID, Value=src.get("Value", 0) * DRAGON_PRICE)
        if "DebugName" in n:
            n["DebugName"] = "Goldmaw craftable"
        items.insert(items.index(src) + 1, n)
    return d


def build_settings(d):
    """MaxBoostedCreaturePerCastleLevel for castle levels 31-60 (as 30)."""
    m = d.get("MaxBoostedCreaturePerCastleLevel")
    if m and str(OLD_CAP) in m:
        for lv in range(OLD_CAP + 1, CAP + 1):
            m.setdefault(str(lv), m[str(OLD_CAP)])
    return d


# castle selection / home sky of region 10: Region_<n> = region n + 2;
# Region_8 = Region_7 (Upper Bestmount) in warmer gold
REGION_ENV = "Region_%d" % (REGION_ID - 2)
GOLD_ENV = {"FogColor": "255,214,168,62", "SkyColor": "255,168,128,40",
            "SouthColor": "255,250,206,92", "WestColor": "255,206,150,52",
            "EastColor": "255,160,112,38"}


def environments(d):
    """Without an environment the castle selection of region 10 had no sky
    (black)."""
    for mode in ("AttackSelection", "Home"):
        lst = d["Environments"].get(mode, {}).get("EnvironmentSettingsList") or []
        names = [e["EnvironmentName"] for e in lst]
        # Little Spitaly's sky (Region_1) in gold: Upper Bestmount's sky dome
        # (Region_7) sat under the camera ("bubble underneath", 2026-11-22)
        prev = "Region_1"
        if REGION_ENV in names or prev not in names:
            continue
        e = copy.deepcopy(lst[names.index(prev)])
        e["EnvironmentName"] = REGION_ENV
        e.update(GOLD_ENV)
        lst.append(e)
    # co-op raids (region 11 -> Region_9): the sky of Little Spitaly (Region_1)
    for mode in ("AttackSelection", "Home"):
        lst = d["Environments"].get(mode, {}).get("EnvironmentSettingsList") or []
        names = [e["EnvironmentName"] for e in lst]
        # Region_9 (= region 11 - 2, like Region_8 for region 10) did not
        # show in the game (black, 2026-11-22): also under the other names
        # the client might look up for region 11
        for name in ("Region_9", "Region_10", "Region_11"):
            names = [e["EnvironmentName"] for e in lst]
            if name not in names and "Region_1" in names:
                e = copy.deepcopy(lst[names.index("Region_1")])
                e["EnvironmentName"] = name
                lst.append(e)
    return d


# --------------------------------------------------------------------------
# items

@functools.lru_cache(maxsize=None)
def _default_templates(settings):
    out = set()
    for f in glob.glob(os.path.join(settings, "Heroes", "*", "GAMEPLAY.JSON")):
        with open(f, encoding="utf-8-sig") as fh:
            for c in json.load(fh):
                out.update(c.get("DefaultEquipmentTemplateIds") or [])
    return out


# Infinite Pack rings (owner's request 2026-11-22: a quarter of the
# original pay-to-win effect): {template: (effect id, new effect level)}.
# Extra XP 0.04 + 0.02 x (level - 1): 48 -> 98 %, 12 -> 26 %;
# Bonus Random Material 0.025 + 0.025 x (level - 1): 19 -> 47.5 %, 5 -> 12.5 %
INFINITE_RINGS = {84243: (24, 12), 84244: (48, 5)}


def infinite_rings(d):
    for t in d.get("TemplateList") or []:
        if t.get("Id") in INFINITE_RINGS:
            eid, level = INFINITE_RINGS[t["Id"]]
            for e in t.get("Effects") or []:
                if e.get("Id") == eid:
                    e["Level"] = level
    return d


def item_templates(d, settings, cosmetic_types, shop_plan=()):
    """Gear whose level range ended at 30 goes to 60 (stats grow per item
    level). Default gear, cosmetics and fixed-level items (shop items,
    LevelMin == LevelMax) keep their range: the server creates them at
    LevelMax/LevelMin. New fixed-level shop items from shop_plan."""
    defaults = _default_templates(settings)
    for t in d["TemplateList"]:
        if (t.get("LevelMax") == OLD_CAP and t.get("LevelMin") != OLD_CAP
                and t["Id"] not in defaults
                and t.get("HeroItemTypeId") not in cosmetic_types):
            t["LevelMax"] = CAP
    have = {t["Id"] for t in d["TemplateList"]}
    d["TemplateList"] += [copy.deepcopy(t) for t, _ in shop_plan if t["Id"] not in have]
    return d


# Shop equipment above 30: the "Exceptional ..." series (fixed-level named
# items every 3 levels, one gold and one bling SKU each) continue up to 60
SHOP_ITEM_FIRST_ID = 90001                # templates end at 84349
SHOP_SKU_FIRST_CODE = 70000               # SKU codes end at 16092
SHOP_LEVEL_STEP = 3
SHOP_GOLD_GROWTH = 1.3                    # gold price x(1 + 1.3 per 30 levels)


CRAFT_STEP = 5                            # craftable items every 5 levels
CRAFT_PRICE_STEP = 33000                  # life force per step after 52,000 at 30


def craft_item_plan(templates, skus, first_id, first_code):
    """[(new template, [new SKU])]: the blacksmith's "Item Crafting" recipes
    (ShopContext 6, fixed-level named items every 5 levels up to 30)
    continue at 35 ... 60: same item, life force +33,000 per step (250,000
    at 60), main material +6, second +1 per step, the rare one +1 every
    two steps."""
    by_id = {t["Id"]: t for t in templates}
    plan, next_id, next_code = [], first_id, first_code
    for sku in sorted(skus, key=lambda x: int(x["Code"])):
        t = by_id.get(sku.get("ItemId"))
        if not (sku.get("ItemType") == 3 and sku.get("ShopContext") == 6 and sku.get("IsActive")
                and sku.get("CraftingMaterials") and t is not None
                and t.get("LevelMin") == t.get("LevelMax") == OLD_CAP):
            continue
        for k, level in enumerate(range(OLD_CAP + CRAFT_STEP, CAP + 1, CRAFT_STEP), 1):
            nt = copy.deepcopy(t)
            nt.update(Id=next_id, LevelMin=level, LevelMax=level)
            n = copy.deepcopy(sku)
            for i, m in enumerate(n["CraftingMaterials"]):
                m["Quantity"] += (6 * k, k, k // 2)[min(i, 2)]
            price = dict(n["Price"])
            price["Amount"] += CRAFT_PRICE_STEP * k
            n.update(Code=str(next_code), ItemId=next_id, Price=price,
                     InternalDescription=re.sub(r"\d+\s*$", str(level),
                                                sku.get("InternalDescription", "")))
            plan.append((nt, [n]))
            next_id += 1
            next_code += 1
    return plan


def shop_item_plan(templates, skus):
    """[(new template, [new SKUs])]: for every active shop item at level 30
    (LevelMin == LevelMax == 30) copies at 33, 36, ... 60 with the same
    name, look and effects; gold price grows linearly to 2.3x at 60 (under
    the 500,000 gold storage), the bling price stays."""
    by_id = {t["Id"]: t for t in templates}
    at30 = {}
    for sku in skus:
        t = by_id.get(sku.get("ItemId"))
        if (sku.get("ItemType") == 3 and sku.get("ShopContext") == 2 and sku.get("IsActive")
                and t is not None and t.get("LevelMin") == t.get("LevelMax") == OLD_CAP):
            at30.setdefault(t["Id"], []).append(sku)
    plan, next_id, next_code = [], SHOP_ITEM_FIRST_ID, SHOP_SKU_FIRST_CODE
    for tid in sorted(at30):
        src = by_id[tid]
        for level in range(OLD_CAP + SHOP_LEVEL_STEP, CAP + 1, SHOP_LEVEL_STEP):
            t = copy.deepcopy(src)
            t.update(Id=next_id, LevelMin=level, LevelMax=level)
            new_skus = []
            for sku in sorted(at30[tid], key=lambda x: x["Code"]):
                n = copy.deepcopy(sku)
                price = dict(n["Price"])
                if price["CurrencyType"] == 2:
                    grown = price["Amount"] * (1 + SHOP_GOLD_GROWTH * (level - OLD_CAP) / OLD_CAP)
                    price["Amount"] = int(round(grown, -2))
                n.update(Code=str(next_code), ItemId=next_id, Price=price,
                         InternalDescription=re.sub(r"\d+\s*$", str(level),
                                                    sku.get("InternalDescription", "")))
                new_skus.append(n)
                next_code += 1
            plan.append((t, new_skus))
            next_id += 1
    return plan + craft_item_plan(templates, skus, next_id, next_code)


# --------------------------------------------------------------------------
# creature / trap tiers

SINGLE_TIER_STEP = 4
MONSTER_BOOST = 0.22                     # +22 % health and damage from tier level 35
STAT_KEYS = ("BaseHealth", "BasePhysicalDamage", "HealthPerLevel", "PhysicalDamagePerLevel")


def tiers(d):
    """Tier tables (Tier -> Level) continued with their last level step up
    to 60, so creatures and traps in level 35-60 castles reach the castle
    level. Players can't buy the new tiers (no SKUs)."""
    for comp in d:
        t = comp.get("Tiers") if isinstance(comp, dict) else None
        if not t or not isinstance(t[-1], dict) or "Level" not in t[-1]:
            continue
        if len(t) < 2:
            # single-tier (level-design elites/traps in PVE castles): every
            # SINGLE_TIER_STEP levels, so region 10 castles get them at level
            if t[-1]["Level"] < 10:
                continue
            step = SINGLE_TIER_STEP
        elif t[-1]["Level"] < 20:
            continue  # low-level specs stay
        else:
            step = max(1, t[-1]["Level"] - t[-2]["Level"])
        old_last = t[-1]["Tier"]
        while t[-1]["Level"] < CAP:
            n = copy.deepcopy(t[-1])
            n["Tier"] = t[-1]["Tier"] + 1
            n["Level"] = min(CAP, t[-1]["Level"] + step)
            t.append(n)
        _tier_modifiers(d, comp, old_last)
    return d


def _tier_modifiers(d, comp, old_last):
    """New tiers get the abilities, passive buffs and stat changes of the
    old last tier (TierModifiers list the tiers they apply to; without this
    the new tiers had none of them). Creatures: tiers from level 35 get a
    copy with MONSTER_BOOST more health and damage (StatsModifier adds to
    CreatureStatsSpec: base and per level, both x 1.22)."""
    new = [x for x in comp["Tiers"] if x["Tier"] > old_last]
    strong = [x["Tier"] for x in new if x["Level"] >= REGION_LEVELS[0]]
    weak = [x["Tier"] for x in new if x["Level"] < REGION_LEVELS[0]]
    stats = next((c for c in d if isinstance(c, dict) and c.get("$type", "").startswith(
        "HyperQuest.GameServer.Contracts.CreatureStatsSpec")), None)
    specs = comp.get("Specializations")
    if specs is None and stats is not None and strong:
        specs = comp["Specializations"] = [{"TierModifiers": []}]
    for sp in specs or []:
        mods = sp.setdefault("TierModifiers", [])
        src = next((m for m in mods if old_last in (m.get("Tiers") or [])), None)
        if stats is None:  # traps: the new tiers like the last one
            if src is not None:
                src["Tiers"] = list(src["Tiers"]) + weak + strong
            continue
        if src is not None and weak:
            src["Tiers"] = list(src["Tiers"]) + weak
        if not strong:
            continue
        boosted = copy.deepcopy(src) if src is not None else {}
        boosted["Tiers"] = strong
        sm = dict(boosted.get("StatsModifier") or {})
        for k in STAT_KEYS:
            total = stats.get(k, 0) + sm.get(k, 0)
            if total > 0:
                sm[k] = int(round(sm.get(k, 0) + MONSTER_BOOST * total))
        boosted["StatsModifier"] = sm
        mods.append(boosted)


# --------------------------------------------------------------------------
# region 10

def attack_regions(d):
    """Friends/Competitions up to 60 and the new region 10 (35-60) after
    Upper Bestmount (whose boss unlocks it)."""
    regions = d["AttackRegions"]
    for r in regions:
        if (r.get("IsFriendRegion") or r.get("IsCompetitionRegion")) and r.get("LevelMax") == OLD_CAP:
            r["LevelMax"] = CAP
    if not any(r["AttackRegionId"] == REGION_ID for r in regions):
        last = next(r for r in regions if r["AttackRegionId"] == REGION_ID - 1)
        r = copy.deepcopy(last)
        r.update(AttackRegionId=REGION_ID, DebugName=OASIS[16782], Name=16782,
                 BossCastleId=BOSS_CASTLE_ID, BossName=16783,
                 LevelMin=REGION_LEVELS[0], LevelMax=CLIENT_LEVEL_MAX,
                 OverPosX=REGION_POS[0], OverPosY=REGION_POS[1])
        regions.append(r)
    # co-op raids (raids.py): free for everyone, castles from the server
    import raids  # noqa: PLC0415
    if not any(r["AttackRegionId"] == raids.REGION_ID for r in regions):
        regions.append({"AttackRegionId": raids.REGION_ID, "DebugName": "Co-op Raids",
                        "Name": raids.OASIS_REGION, "LevelMin": raids.CLIENT_LEVELS[0],
                        "LevelMax": raids.CLIENT_LEVELS[1], "OverPosX": raids.REGION_POS[0],
                        "OverPosY": raids.REGION_POS[1], "ShowUbisoftCastle": True,
                        # with a boss the region counts as the 9th boss region and gets the
                        # sky Region_9; without one its castle selection stayed black
                        "BossCastleId": raids.BOSS_ID, "BossName": raids.OASIS_BOSS})
    return d


def visual_attack_selection(d):
    """3D castle selection: region 10 gets the boss castle models of region 9
    (its boss castle is a copy of Upper Bestmount's). Without an entry the
    scene stays black. At most 5 level rings exist (CirclesRadius), so the
    server shows 5 levels of region 10 around the hero's level
    (castles.MAX_LEVEL_RINGS)."""
    for key in ("BossCastleModelsByRegion", "DestroyedBossCastleModelsByRegion"):
        models = d.get(key)
        if models and str(REGION_ID - 1) in models:
            models.setdefault(str(REGION_ID), models[str(REGION_ID - 1)])
        if models and "3" in models:  # co-op raids: Little Spitaly's scene
            models.setdefault("11", models["3"])
    return d


def _creature_copy(read, src_id, new_id, folder, debug, name, health, damage,
                   desc=None, tiers=None, gameplay=None, icon=None):
    """{archive path: bytes} of a new creature copied from `src_id`: name
    and description (Oasis ids), health/damage x factors, gold overlay,
    `tiers` replaces the tier list, `gameplay(comp)` edits components,
    `icon` (shop, inventory icon file) replaces the picture."""
    top = "Creatures"
    prefix = "%06d - " % src_id
    paths = [p for p in read.list(top, None) if p.split("/")[2].startswith(prefix)]
    name_dir = "%06d - %s" % (new_id, folder)
    stored = "%s\\%s" % (top.upper(), name_dir.upper())
    out = {}
    for p in paths:
        fname = read._name(p)
        data = read.json(p)
        if fname == "GAMEPLAY.JSON":
            for comp in data:
                if tiers is not None and "Tiers" in comp:
                    comp["Tiers"] = tiers
                if comp.get("$type", "").startswith("HyperQuest.GameServer.Contracts.CreatureStatsSpec"):
                    for k, f in (("BaseHealth", health), ("HealthPerLevel", health),
                                 ("BasePhysicalDamage", damage),
                                 ("PhysicalDamagePerLevel", damage)):
                        if k in comp:
                            comp[k] = round(comp[k] * f)
                if gameplay:
                    gameplay(comp)
        elif fname == "VISUAL.JSON":
            data.append({"$type": "HyperQuest.GameServer.Contracts.VisualEntityFxSpec, "
                                  "HyperQuest.GameServer.Contracts",
                         "PersistentFxList": [{
                             "$type": "HyperQuest.GameServer.Contracts.VisualMaterialOverlayFxSpec, "
                                      "HyperQuest.GameServer.Contracts",
                             "SynergyEntityFileName": GOLDMAW_GLOW, "NodeAttachment": {}}]})
        elif fname == "UI.JSON":
            for comp in data:
                if "OasisName" in comp and "DebugName" in comp:
                    comp.update(DebugName=debug, OasisName=name)
                    if desc is not None:
                        comp["OasisDescription"] = desc
                if icon and comp.get("$type", "").startswith("HyperQuest.GameServer.Contracts.UiSpec"):
                    comp.update(ShopIconUrl=icon[0], InvIconUrl=icon[1], LayerName=icon[2])
        out["GameplaySettings/%s/%s/%s\\%s" % (top, name_dir, stored, fname)] = _dump(data, read.raw(p))
    return out


def goldmaw_files(read):
    """{archive path: bytes} of the new boss creature (copy of the Black
    Dragon): name Goldmaw, one tier at level 60, GOLDMAW_HEALTH x health."""
    return _creature_copy(read, GOLDMAW_SOURCE, GOLDMAW_ID, "LD_Goldmaw", "Goldmaw LD", 16783,
                          GOLDMAW_HEALTH, GOLDMAW_DAMAGE, tiers=[{"Tier": 1, "Level": CAP}])


def dragon_files(read):
    """Goldmaw the Insatiable for the crafting lab (region 10): Dragonificus
    Terribilis (1067) in gold with a gold picture (dragon_icon_files), DRAGON_HEALTH x health, DRAGON_DAMAGE x
    damage, defense rating DRAGON_CP, craftable with crafting lab rank 15
    (portal_rank15: needs castle heart 60) instead of 14."""
    def gameplay(comp):
        if "CraftingBuildingRequirementSpec" in comp:
            comp["CraftingBuildingRequirementSpec"] = {
                "BuildingRequirementSpecContainerId": PORTAL, "BuildingRequirementRank": 15}
        if "ConstructionPoints" in comp:
            comp["ConstructionPoints"] = DRAGON_CP
    return _creature_copy(read, DRAGON_SOURCE, DRAGON_ID, "Goldmaw_Craftable_Boss",
                          "Goldmaw craftable", DRAGON_NAME, DRAGON_HEALTH, DRAGON_DAMAGE,
                          desc=DRAGON_DESC, gameplay=gameplay, icon=DRAGON_ICON)


def portal_rank15(d):
    """Crafting lab (Summoning Portal) rank 15 with castle heart 60 (rank 14
    at heart 30): unlocks the craftable Goldmaw."""
    ranks = next(c for c in d if "Ranks" in c)["Ranks"]
    if len(ranks) == 14:
        r = copy.deepcopy(ranks[-1])
        r.update(BuildingRequirementSpecContainerId=1, BuildingRequirementRank=PORTAL_RANK15[0])
        ranks.append(r)
    return d


DRAGON_ICON_SOURCE = "Data/Generated/shopicons/ui/common/creaturesicons/bosses/blackdragon_01%s_%s.png"
DRAGON_WEB_SOURCE = "Data/Generated/Web/UI/COMMON/CREATURESICONS/BOSSES/BLACKDRAGON_01.PNG"
DRAGON_CARD_ART = CARD_ART


def _rgb(png):
    """8-bit RGB PNG (the game's card files are all RGB)."""
    import png_tint  # noqa: PLC0415 (server module)
    return png_tint.encode_rgb(*png_tint.decode(png))


@functools.lru_cache(maxsize=1)
def dragon_icon_files(game_data):
    """{DataBin path: PNG} for the "missflameo" icon set (DRAGON_ICON):
    Dragonificus' card and pictures tinted gold, its lock silhouettes.
    `game_data`: a GameData folder with the Steam files (client/GameData)."""
    import png_tint  # noqa: PLC0415 (server module)

    def src(rel):
        with open(os.path.join(game_data, *rel.split("/")), "rb") as f:
            return f.read()
    out = {}
    for size in ("330x192", "200x200", "96x96"):
        box = DRAGON_CARD_ART if size == "330x192" else None
        gold = _rgb(png_tint.tint_gold(src(DRAGON_ICON_SOURCE % ("", size)), box=box))
        for kind in ("creaturesicons", "creaturesiconsinv"):
            out["Data/Generated/shopicons/ui/common/%s/rares/missflameo_%s.png" % (kind, size)] = gold
        out["Data/Generated/shopicons/ui/common/creaturesicons/rares/missflameolock_%s.png" % size] = (
            src(DRAGON_ICON_SOURCE % ("lock", size)))
    gold = png_tint.tint_gold(src(DRAGON_WEB_SOURCE))   # web picture: RGBA like the original
    for kind in ("CREATURESICONS", "CREATURESICONSINV"):
        out["Data/Generated/Web/UI/COMMON/%s/RARES/MISSFLAMEO.PNG" % kind] = gold
    return out


def objective_settings(d):
    """Quest 105 "Defeat Goldmaw the Insatiable" like 104 (Dragonificus):
    unlocked with region 10, done by killing Goldmaw and reaching the
    treasure room of Goldmaw's Hoard."""
    objs = d["Objectives"]
    if any(o["Id"] == GOLDMAW_OBJECTIVE for o in objs):
        return d
    src = next(o for o in objs if (o.get("CastleId") or {}).get("Id") == BOSS_SOURCE)
    o = copy.deepcopy(src)
    o.update(Id=GOLDMAW_OBJECTIVE, DebugName="Defeat Goldmaw the Insatiable",
             CastleId={"CastleType": "Ubisoft", "Id": BOSS_CASTLE_ID},
             Title=16785, Description=16786, Instruction=16787)
    T = "HyperQuest.GameServer.Contracts.%s, HyperQuest.GameServer.Contracts"
    cur = lambda kind, n: {"$type": T % "CurrencyAmountRewardItem",  # noqa: E731
                           "CurrencyAmount": {"CurrencyType": kind, "Amount": n}}
    o["Reward"] = {"RewardItems": [cur("PremiumCash", 50), cur("IGC", 25000),
                                   cur("LifeForce", 25000),
                                   {"$type": T % "XpRewardItem", "Xp": 1000000}]}
    for r in o.get("Requirements") or []:
        if "AttackRegionId" in r:
            r["AttackRegionId"] = REGION_ID
    for c in o.get("Conditions") or []:
        if c.get("SpecContainerId") == GOLDMAW_SOURCE:
            c.update(SpecContainerId=GOLDMAW_ID, OasisId=16787)
    objs.append(o)
    return d


def oasis(d, names):
    """New texts in every language (English text)."""
    tr = d.get("Translations") if isinstance(d, dict) else None
    if tr is None:  # OASIS_CUSTOMTEXT.JSON: other structure
        return d
    for k, v in names.items():
        tr.setdefault(str(k), v)
    return d


# The client reads its texts from loose files of the DataBin package
# (Data/GameplaySettings/Oasis/oasis_<lang>.json, not the copies inside
# settings.bin); originals of a Steam install in server/data/oasis
OASIS_DIR = "Data/GameplaySettings/Oasis"
OASIS_ORIGINALS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "oasis")
_TRANSLATIONS = re.compile(rb'"Translations":\s*\{(\r?\n)')


def _version_label(data):
    """ESC menu: the server's display version (versions.py) after the
    "Credits" button text of this language (Oasis 11382)."""
    import versions  # noqa: PLC0415
    key = b'"%d"' % versions.OASIS_CREDITS
    m = re.search(key + rb'\s*:\s*"((?:[^"\\]|\\.)*)"', data)
    if not m:
        return data
    # raw text like the rest of the file: the game's text reader dropped the
    # whole file when the label had a JSON escape (·)
    label = m.group(1) + versions.oasis_suffix().encode("utf-8")
    return data[:m.start(1)] + label + data[m.end(1):]


def oasis_text_files(enabled=True, folder=OASIS_ORIGINALS):
    """{"Data/GameplaySettings/Oasis/oasis_<lang>.json": bytes}, the
    client's texts. With `enabled` the new
    texts (all_names) are inserted at the top of Translations (English
    everywhere), otherwise the originals (switching the update off)."""
    out = {}
    for name in sorted(os.listdir(folder)):
        if not re.fullmatch(r"oasis_[a-z-]+\.json", name) or name == "oasis_customText.json":
            continue
        with open(os.path.join(folder, name), "rb") as f:
            data = f.read()
        if enabled:
            m = _TRANSLATIONS.search(data)
            if m is None:
                continue
            nl = m.group(1)
            have = set(re.findall(rb'"(\d+)":', data))
            lines = b"".join(b'        "%d":%s,%s' % (k, json.dumps(v, ensure_ascii=False).encode("utf-8"), nl)
                             for k, v in sorted(all_names().items())
                             if str(k).encode() not in have)
            data = data[:m.end()] + lines + data[m.end():]
            data = _version_label(data)
        out["%s/%s" % (OASIS_DIR, name)] = data
    return out


# --------------------------------------------------------------------------
# game exe

# The exe names the sky of the castle selection per region in a switch over
# region ids 1-9 ("Region_FriendsZone", "Region_Competition", "Region_1" ...
# "Region_7"); region 10 fell into the default case: no sky, black. The
# patch lets the switch take id 10 and gives it the case of region 9
# (Upper Bestmount, "Region_7", golden sky). Found by pattern: dec eax;
# push esi; cmp eax, 8; ja ...; jmp [eax*4 + table] (MightyQuest.exe
# 280139: function at file offset 0x9b5390, table at 0x9b5474).
_SKY_SWITCH = bytes.fromhex("8b442408 48 56 83f808 0f87")


def patch_exe(exe):
    """exe bytes with the level-60 changes (sky of region 10); unchanged if
    the code isn't found exactly once (other exe version)."""
    import struct
    at = exe.find(_SKY_SWITCH)
    if at < 0 or exe.find(_SKY_SWITCH, at + 1) >= 0:
        return exe
    jmp = at + len(_SKY_SWITCH) + 4            # after "ja rel32"
    if exe[jmp:jmp + 3] != b"\xff\x24\x85":    # jmp [eax*4 + table]
        return exe
    table_va = struct.unpack_from("<I", exe, jmp + 3)[0]
    pe = struct.unpack_from("<I", exe, 0x3c)[0]
    base = struct.unpack_from("<I", exe, pe + 24 + 28)[0]
    opt = struct.unpack_from("<H", exe, pe + 20)[0]
    table = None
    for i in range(struct.unpack_from("<H", exe, pe + 6)[0]):
        o = pe + 24 + opt + 40 * i
        vsize, va, rsize, raw = struct.unpack_from("<IIII", exe, o + 8)
        if base + va <= table_va < base + va + rsize:
            table = table_va - base - va + raw
    if table is None:
        return exe

    def va_to_file(v):
        for i in range(struct.unpack_from("<H", exe, pe + 6)[0]):
            o = pe + 24 + opt + 40 * i
            vsize, va, rsize, raw = struct.unpack_from("<IIII", exe, o + 8)
            if base + va <= v < base + va + rsize:
                return v - base - va + raw
        return None

    def file_to_rva(f):
        for i in range(struct.unpack_from("<H", exe, pe + 6)[0]):
            o = pe + 24 + opt + 40 * i
            vsize, va, rsize, raw = struct.unpack_from("<IIII", exe, o + 8)
            if raw <= f < raw + rsize:
                return f - raw + va
        return None

    # 2026-11-22: the old patch (id 10 -> case of region 9, "Region_7")
    # showed Upper Bestmount's sky dome below the camera, and region 11
    # (co-op raids) still fell into the default case (black). Now the
    # default case names the sky itself: id 10 -> "Region_8", id 11 and up
    # -> "Region_9" (environments(): Region_8 = Little Spitaly's sky in gold,
    # Region_9 = Little Spitaly's sky). The two names go into the int3
    # padding in front of the function; the new default code (22 bytes, in
    # the 23 of the old one) pushes the name and jumps to the name-building
    # call of region 9's case:
    #   mov ecx,[esp+8]; cmp eax,9; mov eax,"Region_8"; je +5;
    #   mov eax,"Region_9"; push eax; jmp short <case 9: call ctor>
    # 2026-11-23 (v1.4.3.2): the self-made names "Region_8"/"Region_9" left
    # the co-op raids black in the game. Now only the exe's own names are
    # used, whose skies surely exist: id 10 (Splendorado) -> "Region_7"
    # (Upper Bestmount, the golden clouds of the first fix), id 11 and up
    # (co-op raids) -> "Region_1" (Little Spitaly). Both strings are the
    # ones pushed by the cases of id 9 and id 3.
    rel = struct.unpack_from("<i", exe, at + len(_SKY_SWITCH))[0]
    dflt = at + len(_SKY_SWITCH) + 4 + rel
    if exe[dflt:dflt + 2] != b"\x8b\x0d" or exe[dflt + 22] != 0xC3:
        return exe
    case9 = va_to_file(struct.unpack_from("<I", exe, table + 4 * 8)[0])
    if case9 is None or exe[case9:case9 + 5] != b"\x8b\x4c\x24\x08\x68" or exe[case9 + 9] != 0xE8:
        return exe
    case3 = va_to_file(struct.unpack_from("<I", exe, table + 4 * 2)[0])
    if case3 is None or exe[case3:case3 + 5] != b"\x8b\x4c\x24\x08\x68":
        return exe
    sky_10 = struct.unpack_from("<I", exe, case9 + 5)[0]   # "Region_7"
    sky_11 = struct.unpack_from("<I", exe, case3 + 5)[0]   # "Region_1"
    for v, want in ((sky_10, b"Region_7\x00"), (sky_11, b"Region_1\x00")):
        f = va_to_file(v)
        if f is None or exe[f:f + 9] != want:
            return exe
    call = case9 + 9
    rel8 = call - (dflt + 22)
    if not -128 <= rel8 < 0:
        return exe
    code = (b"\x8b\x4c\x24\x08" + b"\x83\xf8\x09" + b"\xb8" + struct.pack("<I", sky_10)
            + b"\x74\x05" + b"\xb8" + struct.pack("<I", sky_11) + b"\x50"
            + b"\xeb" + struct.pack("<b", rel8))
    assert len(code) == 22
    out = bytearray(exe)
    out[dflt:dflt + 22] = code
    out[dflt + 22] = 0xCC                      # the old ret, now unused
    # the exe can be loaded elsewhere (ASLR): both new absolute addresses
    # need a base relocation
    # 2026-11-22 fix: the old default code had relocations at +2 and +15
    # (mov ecx,[global]); the one at +2 now lies inside "mov ecx,[esp+8];
    # cmp eax,9" and the loader (ASLR) corrupted those bytes -> crash on
    # the Attack button. It is turned into a padding entry.
    patched = _drop_relocation(bytes(out), file_to_rva(dflt + 2))
    patched = _add_relocation(patched, file_to_rva(dflt + 8))
    patched = _add_relocation(patched, file_to_rva(dflt + 15))
    if _relocations_in(patched, file_to_rva(dflt), 22) != {file_to_rva(dflt + 8), file_to_rva(dflt + 15)}:
        return exe                             # never ship a half-relocated patch
    return patched


def _reloc_blocks(exe):
    """[(file offset of the entry, rva)] of every HIGHLOW base relocation."""
    import struct
    pe = struct.unpack_from("<I", exe, 0x3c)[0]
    opt = pe + 24
    nsec = struct.unpack_from("<H", exe, pe + 6)[0]
    optsz = struct.unpack_from("<H", exe, pe + 20)[0]
    reloc_rva, reloc_size = struct.unpack_from("<II", exe, opt + 96 + 5 * 8)
    out = []
    for i in range(nsec):
        o = opt + optsz + 40 * i
        vsize, va, rsize, raw = struct.unpack_from("<IIII", exe, o + 8)
        if va <= reloc_rva < va + max(vsize, rsize):
            pos = raw + reloc_rva - va
            end = pos + reloc_size
            while pos < end:
                prva, bsz = struct.unpack_from("<II", exe, pos)
                if bsz < 8:
                    break
                for k in range(8, bsz, 2):
                    e = struct.unpack_from("<H", exe, pos + k)[0]
                    if e >> 12 == 3:
                        out.append((pos + k, prva + (e & 0xfff)))
                pos += bsz
    return out


def _relocations_in(exe, rva, size):
    return {r for _, r in _reloc_blocks(exe) if rva <= r < rva + size}


def _drop_relocation(exe, rva):
    """exe with the HIGHLOW relocation at `rva` turned into a padding entry
    (type 0, skipped by the loader)."""
    out = bytearray(exe)
    for at, r in _reloc_blocks(exe):
        if r == rva:
            out[at:at + 2] = b"\x00\x00"
    return bytes(out)


def _add_relocation(exe, rva):
    """exe with a HIGHLOW base relocation for `rva`: its page's block in
    .reloc grows by 4 bytes (entry + padding entry), the rest of the
    relocation data moves up; directory and section sizes grow. Unchanged
    if .reloc has no room."""
    import struct
    pe = struct.unpack_from("<I", exe, 0x3c)[0]
    opt = pe + 24
    nsec = struct.unpack_from("<H", exe, pe + 6)[0]
    optsz = struct.unpack_from("<H", exe, pe + 20)[0]
    dir_at = opt + 96 + 5 * 8                  # IMAGE_DIRECTORY_ENTRY_BASERELOC
    reloc_rva, reloc_size = struct.unpack_from("<II", exe, dir_at)
    sec = None
    for i in range(nsec):
        o = opt + optsz + 40 * i
        vsize, va, rsize, raw = struct.unpack_from("<IIII", exe, o + 8)
        if va <= reloc_rva < va + max(vsize, rsize):
            sec = (o, vsize, va, rsize, raw)
    if sec is None:
        return exe
    o, vsize, va, rsize, raw = sec
    start = raw + reloc_rva - va
    if reloc_rva - va + reloc_size + 4 > rsize:
        return exe
    page, entry = rva & ~0xfff, 0x3000 | (rva & 0xfff)
    pos, end = start, start + reloc_size
    while pos < end:
        prva, bsz = struct.unpack_from("<II", exe, pos)
        if bsz < 8:
            return exe
        if prva == page:
            ents = list(struct.unpack_from("<%dH" % ((bsz - 8) // 2), exe, pos + 8))
            if entry in ents:
                return exe
            ents = sorted([e for e in ents if e] + [entry])
            if len(ents) % 2:
                ents.append(0)                 # blocks stay 4-byte aligned
            block = struct.pack("<II", page, 8 + 2 * len(ents)) + struct.pack(
                "<%dH" % len(ents), *ents)
            grow = len(block) - bsz
            out = bytearray(exe)
            tail = exe[pos + bsz:end]
            out[pos:pos + len(block) + len(tail)] = block + tail
            struct.pack_into("<I", out, dir_at + 4, reloc_size + grow)
            struct.pack_into("<I", out, o + 8, max(vsize, reloc_rva - va + reloc_size + grow))
            return bytes(out)
        pos += bsz
    return exe


# --------------------------------------------------------------------------
# which file gets which edit

def _hero_spell_ids(read):
    ids = set()
    for path in read.list("Heroes", "GAMEPLAY.JSON"):
        for c in read.json(path):
            ids.update(c.get("AllowedSpells") or [])
    return ids


def _sub_abilities(read, hero_ids):
    """Abilities a hero skill reaches through its specs (not other hero
    skills) that have one level per skill rank, e.g. Siren Stun's cleave
    (1314 -> buff 729 -> ability 1316 -> 1317, 2 levels): they get 5 levels
    too, otherwise ranks III-V used level II's values."""
    look = SpecForge(read)
    out = set()

    def walk(o, seen, depth):
        if isinstance(o, dict):
            kind = _ref_kind(o)
            key = kind and (kind, o["SpecContainerReferenceId"])
            if key and key not in seen and depth < 8:
                seen.add(key)
                gp = look._gameplay(*key)[1]
                if gp is not None:
                    walk(gp, seen, depth + 1)
            for v in o.values():
                walk(v, seen, depth)
        elif isinstance(o, list):
            for v in o:
                walk(v, seen, depth)

    for sid in hero_ids:
        gp = look._gameplay("Ability", sid)[1]
        if not gp:
            continue
        n = len(gp[0].get("Levels") or [])
        seen = set()
        walk(gp, seen, 0)
        for kind, sub in seen:
            sub_gp = look._gameplay(kind, sub)[1] if kind == "Ability" else None
            if (sub_gp and sub not in hero_ids and n > 1
                    and len(sub_gp[0].get("Levels") or []) == n):
                out.add(sub)
    return sorted(out)


def _cosmetic_types(read):
    """HeroItemTypes that are cosmetics (pets, costumes, ...)."""
    d = read.json(read.find("HeroItems", "HEROITEMTYPES.JSON"))
    return {t["Id"] for t in d["ItemTypeList"]
            if t.get("HeroItemCategoryType") in ("Pet", "Costume", "Cosmetic", "Dye")}


def edits(read, forge=None):
    """{path: function(json) -> json} for the archive/loose files.
    `read` gives access to the original files (see Source); `forge`
    collects new specs for the new skill ranks."""
    out = {}
    g = lambda *p: read.find(*p)  # noqa: E731
    out[g("GeneralSettings", "HEROSETTINGS.JSON")] = hero_settings
    out[g("GeneralSettings", "ATTACKADVISORSETTINGS.JSON")] = attack_regions
    out[g("GeneralSettings", "VISUALATTACKSELECTIONSETTINGS.JSON")] = visual_attack_selection
    out[g("GeneralSettings", "OBJECTIVESETTINGS.JSON")] = objective_settings
    xp_table = hero_settings(read.json(g("GeneralSettings", "HEROSETTINGS.JSON")))["XpPerLevel"]
    out[g("GeneralSettings", "ATTACKERREWARDSETTINGS.JSON")] = (
        lambda d: attacker_rewards(d, xp_table))
    # decoration loot: decorations need a LootableSpec, or the client never
    # spawns AttackInfo.DecorationLoot (2026-11-22)
    for path in read.list("Decorations", "GAMEPLAY.JSON"):
        out[path] = decoration_lootable
    out[g("GeneralSettings", "SHOPSETTINGS.JSON")] = shop_settings
    out[g("GeneralSettings", "FORGESETTINGS.JSON")] = forge_settings
    out[g("GeneralSettings", "FORGECRAFTINGMATERIALSSETTINGS.JSON")] = forge_materials
    out[g("GeneralSettings", "BUILDSETTINGS.JSON")] = build_settings
    out[g("GeneralSettings", "CASTLEITEMVALUESETTINGS.JSON")] = castle_item_values
    out[g("GeneralSettings", "ENVIRONMENTSETTINGSCOLLECTION.JSON")] = environments
    out[g("GeneralSettings", "UNIVERSALDROPSETTINGS.JSON")] = raise_ranges("LevelMax")
    out[g("GeneralSettings", "RESURRECTIONSETTINGS.JSON")] = raise_ranges("LevelTo")
    out[g("GeneralSettings", "ATTACKSETTINGS.JSON")] = raise_ranges("HeroLevelMax", "MaxCastleLevel")
    out[g("HeroItems", "HEROITEMBUILDINGREQUIREMENTSETTINGS.JSON")] = raise_ranges("MaxLevel")
    plan = shop_item_plan(read.json(g("HeroItems", "HEROITEMTEMPLATES.JSON"))["TemplateList"],
                          read.json(g("ShopSettings", "SHOPSKUBASESETTINGS.JSON"))["Skus"])
    out[g("ShopSettings", "SHOPSKUBASESETTINGS.JSON")] = lambda d: shop_skus(d, plan)
    out[g("Buildings", "000001 - CastleHeart", "GAMEPLAY.JSON")] = castle_heart
    out[g("Buildings", "000001 - CastleHeart", "UI.JSON")] = heart_ranks_ui
    out[g("Buildings", "000001 - CastleHeart", "VISUAL.JSON")] = heart_ranks_ui
    for folder in ("000003 - GoldStorage", "000004 - LifeForceStorage"):
        out[g("Buildings", folder, "GAMEPLAY.JSON")] = storage
        out[g("Buildings", folder, "UI.JSON")] = rank_lists_ui(6)
        out[g("Buildings", folder, "VISUAL.JSON")] = rank_lists_ui(6)
    for folder, fn, ranks in (("000013 - ArchitectOffice", architect_office, 6 + len(ARCHITECT_RANKS)),
                              ("000005 - GoldMine", mines, 11 + len(MINE_RANKS)),
                              ("000006 - LifeForceMine", mines, 11 + len(MINE_RANKS)),
                              ("000016 - BlingMine", more_mines, None)):
        out[g("Buildings", folder, "GAMEPLAY.JSON")] = fn
        if ranks:
            out[g("Buildings", folder, "UI.JSON")] = rank_lists_ui(ranks)
            out[g("Buildings", folder, "VISUAL.JSON")] = rank_lists_ui(ranks)
    for rank, rooms in ARCHITECT_ROOMS.items():
        for room, _ in rooms:
            out[read.find("Rooms", read.ability_folder(room, "Rooms"), "GAMEPLAY.JSON")] = (
                room_requirement(rank))
    out[g("Buildings", "000010 - SummoningPortal", "GAMEPLAY.JSON")] = portal_rank15
    out[g("Buildings", "000010 - SummoningPortal", "UI.JSON")] = rank_lists_ui(15)
    out[g("Buildings", "000010 - SummoningPortal", "VISUAL.JSON")] = rank_lists_ui(15)
    for room in ROOMS_ICON_FILE:
        out[read.find("Rooms", read.ability_folder(room, "Rooms"), "UI.JSON")] = room_picture(room)
    out[g("UI", "UIGLOBALSETTINGS.JSON")] = ui_global
    cosmetic = _cosmetic_types(read)
    settings = read.settings
    out[g("HeroItems", "HEROITEMTEMPLATES.JSON")] = (
        lambda d: infinite_rings(item_templates(d, settings, frozenset(cosmetic), plan)))
    hero_ids = _hero_spell_ids(read)
    for sid in _sub_abilities(read, hero_ids):
        out[read.find("Abilities", read.ability_folder(sid), "GAMEPLAY.JSON")] = (
            lambda d, sid=sid: ability_gameplay(d, sid, forge))
    for sid in sorted(hero_ids):
        folder = read.ability_folder(sid)
        if folder is None:
            continue
        ranks = base_ranks(sid, read.json(read.find("Abilities", folder, "GAMEPLAY.JSON"))[0].get("Levels") or [])
        out[read.find("Abilities", folder, "GAMEPLAY.JSON")] = (
            lambda d, sid=sid: ability_gameplay(d, sid, forge))
        for kind in ("UI.JSON", "VISUAL.JSON", "AUDIO.JSON"):
            p = read.find("Abilities", folder, kind, required=False)
            if p:
                out[p] = lambda d, ranks=ranks: ability_side(d, ranks, forge)
    for kind in ("Creatures", "Traps"):
        for p in read.list(kind, "GAMEPLAY.JSON"):
            if b'"Tiers"' in read.raw(p):
                out[p] = tiers
    for p in read.list("Oasis", None):
        out[p] = lambda d: oasis(d, all_names())
    return out


@functools.lru_cache(maxsize=None)
def all_names():
    """All new Oasis texts: region, boss and the region castles' names."""
    import raids  # noqa: PLC0415
    names = dict(OASIS)
    names.update({oid: name for oid, name in region_castle_names().items()})
    names.update(raids.oasis_texts())
    return names


# --------------------------------------------------------------------------
# applying the edits

class Source:
    """Original files by archive path (from settings.bin content)."""

    def __init__(self, files, settings):
        self.files = files            # {archive path: bytes}
        self.settings = settings      # loose folder (for lookups only)
        self._by_dir = {}
        for p in files:
            parts = p.split("/")
            self._by_dir.setdefault(parts[1], []).append(p)

    @staticmethod
    def _name(p):
        return p.split("/")[-1].split("\\")[-1].upper()

    def find(self, top, *rest, required=True):
        want_dir = "/".join(rest[:-1]).upper()
        want = rest[-1].upper()
        for p in self._by_dir.get(top, []):
            parts = p.split("/")
            if self._name(p) == want and "/".join(parts[2:-1]).upper() == want_dir:
                return p
        if required:
            raise KeyError("settings: %s/%s" % (top, "/".join(rest)))
        return None

    def list(self, top, name):
        return [p for p in self._by_dir.get(top, [])
                if name is None or self._name(p) == name.upper()]

    def raw(self, p):
        return self.files[p]

    def json(self, p):
        return json.loads(self.files[p].decode("utf-8-sig"))

    def ability_folder(self, sid, top="Abilities"):
        prefix = "%06d - " % sid
        for p in self._by_dir.get(top, []):
            folder = p.split("/")[2]
            if folder.startswith(prefix):
                return folder
        return None


def _dump(obj, original):
    """JSON text like the originals: 4-space indent, "Key":value without a
    space (balance.py finds values with patterns like '"Code":"15522",'),
    CRLF if they had it."""
    text = json.dumps(obj, indent=4, ensure_ascii=False, separators=(",", ":"))
    if b"\r\n" in original:
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    if original.startswith(b"\xef\xbb\xbf"):
        data = b"\xef\xbb\xbf" + data
    return data


def edited_files(files, settings):
    """({archive path: new bytes} of changed files, {archive path: bytes}
    of new files)."""
    src = Source(files, settings)
    forge = SpecForge(src)
    out = {}
    for path, fn in edits(src, forge).items():
        original = src.json(path)
        changed = fn(copy.deepcopy(original))
        if changed != original:  # unchanged files keep their exact bytes
            out[path] = _dump(changed, src.raw(path))
    added = dict(forge.added)
    added.update(goldmaw_files(src))
    added.update(dragon_files(src))
    return out, added


@functools.lru_cache(maxsize=1)
def rules_crc():
    """CRC of this module's rules (part of the DataBin version)."""
    # the rules live in level60.py plus raids.py (co-op raid data and
    # texts) and versions.py (version label): a change in any of them must
    # give players a new DataBin version
    crc = 0
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("level60.py", "raids.py", "versions.py"):
        with open(os.path.join(here, name), "rb") as f:
            crc = zlib.crc32(f.read(), crc)
    return "%08x" % crc


# --------------------------------------------------------------------------
# region 10 castles (server only)

def _settings_dir():
    import loot  # noqa: PLC0415 (server module)
    return loot.SETTINGS


def _pve_sources():
    """PVE castles (level 24+, active, not region bosses) used as layouts
    for the region's castles."""
    folder = os.path.join(_settings_dir(), "Castles")
    bosses = {14, 15, 16, 17, 18, 19, 20}
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.JSON"))):
        with open(path, encoding="utf-8-sig") as f:
            c = json.load(f)
        if (c.get("Level", 0) >= 24 and not c.get("IsDisabled")
                and c.get("AccountId") not in bosses and c.get("OasisName")):
            out.append(c)
    return out


@functools.lru_cache(maxsize=1)
def _english():
    path = os.path.join(_settings_dir(), "Oasis", "OASIS_EN.JSON")
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)["Translations"]


@functools.lru_cache(maxsize=1)
def _plan():
    """[(castle id, level, source castle, name id)] of region 10."""
    sources = _pve_sources()
    plan = []
    n = 0
    for level in REGION_CASTLE_LEVELS:
        for k in range(CASTLES_PER_LEVEL):
            src = sources[n % len(sources)]
            plan.append((CASTLE_ID_BASE + level * 10 + k, level, src,
                         GILDED_FIRST_ID + len(plan)))
            n += 1
    return plan


@functools.lru_cache(maxsize=1)
def region_castle_names():
    """{Oasis id: name}: "Gilded <castle>" for every region castle."""
    try:
        names = _english()
    except OSError:
        return {}
    return {oid: "Gilded " + names.get(str(src["OasisName"]), "Castle")
            for _, _, src, oid in _plan()}


def _top_tier(kind, spec_id, level):
    """Highest tier of a creature/trap whose level is <= `level`."""
    folder = os.path.join(_settings_dir(), kind)
    path = glob.glob(os.path.join(folder, "%06d - *" % spec_id, "GAMEPLAY.JSON"))
    if not path:
        return 1
    with open(path[0], encoding="utf-8-sig") as f:
        for c in json.load(f):
            t = c.get("Tiers") if isinstance(c, dict) else None
            if t and isinstance(t[0], dict) and "Level" in t[0]:
                return max([x["Tier"] for x in t if x["Level"] <= level] or [1])
    return 1


def _scaled(src, castle_id, level, name_id):
    c = copy.deepcopy(src)
    c.update(AccountId=castle_id, Level=level, OasisName=name_id,
             ForceCastleLevelOnBuildables=True,
             AccountDisplayName=region_castle_names().get(name_id) or all_names().get(name_id, ""))
    c.pop("OasisNameId", None)
    c.pop("CastleValidationDuration", None)
    for kind in ("Creature", "Trap"):
        specs = dict.fromkeys(e["SpecContainerId"] for r in c.get("Rooms") or []
                              for e in r.get(kind + "s") or [])
        given = {t["SpecContainerId"]: t for t in c.get(kind + "Tiers") or []}
        c[kind + "Tiers"] = [
            {"SpecContainerId": s, "Tier": _top_tier(kind + "s", s, level),
             "Specialization": given.get(s, {}).get("Specialization", 0)}
            for s in specs]
    for r in c.get("Rooms") or []:
        for b in r.get("Buildings") or []:
            if b["SpecContainerId"] == 1:
                b["Rank"] = level
    return c


@functools.lru_cache(maxsize=1)
def region_castles():
    """NPC castles of region 10: two per level 35-59 ("Gilded ..." copies
    of the level 24-33 PVE castles at the new level) and the boss castle
    (Black Dragon layout, level 60). Fake players come from these like from
    every PVE castle (castles.fake_player_castles)."""
    if not ENABLED:
        return []
    out = [_scaled(src, cid, level, oid) for cid, level, src, oid in _plan()]
    folder = os.path.join(_settings_dir(), "Castles")
    boss_path = glob.glob(os.path.join(folder, "%06d - *" % BOSS_SOURCE))
    with open(boss_path[0], encoding="utf-8-sig") as f:
        boss = json.load(f)
    for r in boss.get("Rooms") or []:
        for e in r.get("Creatures") or []:
            if e["SpecContainerId"] == GOLDMAW_SOURCE:
                e["SpecContainerId"] = GOLDMAW_ID
    for t in boss.get("CreatureTiers") or []:
        if t["SpecContainerId"] == GOLDMAW_SOURCE:
            t["SpecContainerId"] = GOLDMAW_ID
    boss = _scaled(boss, BOSS_CASTLE_ID, CAP, 16784)
    boss["AccountDisplayName"] = OASIS[16783]
    out.append(boss)
    return out


def region_throne_boss(castle_id):
    """Boss for the throne room of the fake player made from region castle
    `castle_id`: the older region bosses in turn (the throne rooms come
    from the boss castles, so every fake player had the Black Dragon or
    Goldmaw; Goldmaw belongs to Goldmaw's Hoard only)."""
    ids = [cid for cid, _, _, _ in _plan()]
    i = ids.index(castle_id) if castle_id in ids else castle_id
    return OLD_REGION_BOSSES[i % len(OLD_REGION_BOSSES)]


def find_region_castle(castle_id):
    if not ENABLED or not (CASTLE_ID_BASE <= castle_id <= BOSS_CASTLE_ID):
        return None
    return next((copy.deepcopy(c) for c in region_castles()
                 if c["AccountId"] == castle_id), None)
