"""Co-op raids (region 11 "Co-op Raids", guide docs/89-coop-raids.md).

- Raid castles at levels 5, 7, 9, 10, 12, 14 ... 59 (three per 5-level
  bracket), castle ids RAID_BASE + level * 10; boss castles at 15, 30, 45
  (story bosses' layouts) and Warlord's Keep (BOSS_ID, 60, region boss). The id is the same for everyone; the castle behind it is built for
  the player who asks (VIEWER, set per game request): from the party's
  seed and size (parties.py), so every member of a party gets the same
  castle and other parties get their own.
- Procedural: a big story castle as layout (8+ rooms), every creature
  type swapped for another of similar strength, traps swapped, a random
  theme, then scaled to the tier's level like the region-10 castles.
- Party size: 50-60% more creatures per extra member (copies next to the
  originals), so 4 players face about 2.5 times the monsters; their loot
  grows with them. Each player attacks in their own game with their own
  loot.
- New castles: the castle selection's own reroll button ("More castles",
  paid by the game) counts per player; the seed uses the sum of the party
  members' rerolls of region 11, so any member's reroll gives the whole
  party new castles.
- Party bonus: when every member has cleared the same raid castle, each
  gets gold, life force and crafting materials (game_server, EndAttack).
"""
import copy
import functools
import random
import threading
import zlib

REGION_ID = 11
# castle levels: three per 5-level bracket (5, 7, 9, 10, 12, 14 ... 59),
# boss castles at 15, 30, 45 and 60 (60 = the region boss, BOSS_ID)
LEVELS = tuple(sorted({b + d for b in range(5, 60, 5) for d in (0, 2, 4)} | {60}))
TIERS = LEVELS                    # (old name)
RAID_BASE = 61000                 # castle id = RAID_BASE + level * 10
BOSS_ID = 61999                   # Warlord's Keep (60): region boss (sidebar, sky)
BOSS_LEVELS = {15: (15, 16903), 30: (17, 16904), 45: (19, 16905), 60: (20, 16902)}
#                level: (layout = a story region's boss castle, Oasis name)
BOSS_LEVEL = 60
OASIS_BOSS = 16901
OASIS_BOSS_CASTLE = 16902
CLIENT_LEVELS = (5, 9)            # the 3D selection has 5 rings (castles._rings)
RINGS = 5
OASIS_REGION = 16900
OASIS_TIER_FIRST = 16910          # "Co-op Raid N" per tier
REGION_POS = (1790, 680)          # OverPosX/Y on the region map
MIN_ROOMS = 8
# more creatures per extra party member: off while the co-op isn't live
# (every member plays alone in their own game, 2026-11-22)
EXTRA_PER_MEMBER = 0.55
PARTY_SCALING = False
BOSS_CASTLES = {14, 15, 16, 17, 18, 19, 20}

VIEWER = threading.local()        # .value = account id of the current request
PARTIES = None                    # parties.Parties (game_server)
PLAYERS = None                    # players.Players (game_server)


def oasis_texts():
    return {OASIS_REGION: "Co-op Raids", OASIS_BOSS: "The Raid Warlord",
            16902: "Warlord's Keep", 16903: "Warlord's Outpost",
            16904: "Warlord's Fortress", 16905: "Warlord's Citadel"}


BOSS_NAMES = {16902: "Warlord's Keep", 16903: "Warlord's Outpost",
              16904: "Warlord's Fortress", 16905: "Warlord's Citadel"}


def is_raid(castle_id):
    try:
        cid = int(castle_id)
    except (TypeError, ValueError):
        return False
    if cid == BOSS_ID:
        return True
    return (RAID_BASE < cid < BOSS_ID and (cid - RAID_BASE) % 10 == 0
            and (cid - RAID_BASE) // 10 in LEVELS and (cid - RAID_BASE) // 10 != 60)


def tier_of(castle_id):
    return BOSS_LEVEL if int(castle_id) == BOSS_ID else (int(castle_id) - RAID_BASE) // 10


def castle_id(level, variant=0):
    return BOSS_ID if level == 60 else RAID_BASE + level * 10


# -- party seed / size --------------------------------------------------------

def seed_and_size(account_id):
    """(seed, party size, party key) for account_id."""
    if not account_id:
        return 0, 1, "none"
    members = PARTIES.members(account_id) if PARTIES else [int(account_id)]
    party = PARTIES.party_of(account_id) if PARTIES else None
    rerolls = 0
    for m in members:
        p = PLAYERS.by_account_id(m) if PLAYERS else None
        if p is not None:
            rerolls += int(p.state.read(lambda a: (a.get("CastleRerolls") or {}).get(str(REGION_ID), 0)))
    key = "party-%s" % party["Id"] if party else "solo-%d" % int(account_id)
    locked = PARTIES.raid_seed(account_id) if PARTIES and party else None
    if locked is not None:   # the party's chosen raid: same castle for all until it ends
        return locked, len(members), key
    return zlib.crc32(("%s/%d" % (key, rerolls)).encode()) % 100000, len(members), key


def raid_key(account_id, castle_id):
    seed, _, _ = seed_and_size(account_id)
    return "%d/%d" % (seed, tier_of(castle_id))


# -- generator ----------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _sources():
    import castles  # noqa: PLC0415 (castles imports raids)
    return [c for c in castles.load_pve_castles()
            if len(c.get("Rooms") or []) >= MIN_ROOMS and c["AccountId"] not in BOSS_CASTLES
            and not c.get("IsTutorialCastle")]


@functools.lru_cache(maxsize=1)
def _pools():
    """(creature pool [(spec, cp)], trap specs, themes) from the story castles."""
    import castles  # noqa: PLC0415
    import loot  # noqa: PLC0415
    boss_specs = set()
    for c in castles.load_pve_castles():
        if c["AccountId"] in BOSS_CASTLES:
            for r in c.get("Rooms") or []:
                for e in r.get("Creatures") or []:
                    boss_specs.add(e["SpecContainerId"])
    normal = set()
    for c in castles.load_pve_castles():
        if c["AccountId"] in BOSS_CASTLES:
            continue
        for r in c.get("Rooms") or []:
            for e in r.get("Creatures") or []:
                normal.add(e["SpecContainerId"])
    creatures = []
    for s in sorted(normal - boss_specs):
        try:
            cp = loot.creature(s)[0]
        except Exception:  # noqa: BLE001 - spec without data
            continue
        if cp:
            creatures.append((s, cp))
    traps = sorted({e["SpecContainerId"] for c in castles.load_pve_castles()
                    for r in c.get("Rooms") or [] for e in r.get("Traps") or []})
    themes = sorted({c.get("ThemeId", 1) for c in castles.load_pve_castles()})
    return creatures, traps, themes


def _cp(spec):
    import loot  # noqa: PLC0415
    try:
        return loot.creature(spec)[0] or 1
    except Exception:  # noqa: BLE001
        return 1


@functools.lru_cache(maxsize=256)
def _build(castle_id, seed, size):
    import level60  # noqa: PLC0415
    tier = tier_of(castle_id)
    rng = random.Random("raid/%d/%d" % (seed, castle_id))
    boss = BOSS_LEVELS.get(tier)
    if boss:
        import castles  # noqa: PLC0415
        c = copy.deepcopy(next(x for x in castles.load_pve_castles() if x["AccountId"] == boss[0]))
        pool = {s for s, _ in _pools()[0]}
        keep = {e["SpecContainerId"] for r in c["Rooms"] for e in r.get("Creatures") or []
                if e["SpecContainerId"] not in pool}  # the region boss stays
    else:
        c = copy.deepcopy(rng.choice(_sources()))
        keep = set()
    creatures, traps, themes = _pools()
    swap = {}
    for spec in sorted({e["SpecContainerId"] for r in c["Rooms"] for e in r.get("Creatures") or []} - keep):
        cp = _cp(spec)
        near = [s for s, v in creatures if 0.7 * cp <= v <= 1.3 * cp] or [spec]
        swap[spec] = rng.choice(near)
    # traps stay as the layout has them: rail traps need their rails and
    # trap generators their own trap types (swapped, they stood loose or the
    # generator had no traps, 2026-11-22)
    trap_swap = {}
    for r in c["Rooms"]:
        for e in r.get("Creatures") or []:
            e["SpecContainerId"] = swap.get(e["SpecContainerId"], e["SpecContainerId"])
        for e in r.get("Traps") or []:
            e["SpecContainerId"] = trap_swap.get(e["SpecContainerId"], e["SpecContainerId"])
    c["CreatureTiers"], c["TrapTiers"] = [], []   # rebuilt by _scaled for the new specs
    if themes:
        c["ThemeId"] = rng.choice(themes)
    if boss:
        name, display = boss[1], BOSS_NAMES[boss[1]]
    else:  # a random story castle's name, like the other regions
        name = rng.choice(_names())
        display = _english_name(name)
    c = level60._scaled(c, castle_id, tier, name)
    # party size: more creatures (copies on the same spot; the game pushes
    # them apart), loot grows with them
    extra = (size - 1) * EXTRA_PER_MEMBER if PARTY_SCALING else 0
    if extra > 0:
        next_id = 1 + max([e["Id"] for r in c["Rooms"] for k in ("Creatures", "Traps", "Decorations", "Buildings")
                           for e in r.get(k) or []] + [0])
        for r in c["Rooms"]:
            added = []
            for e in r.get("Creatures") or []:
                n = int(extra) + (1 if rng.random() < extra - int(extra) else 0)
                for _ in range(n):
                    d = dict(e, Id=next_id)
                    next_id += 1
                    added.append(d)
            if added:
                r["Creatures"] = (r.get("Creatures") or []) + added
    c["AccountDisplayName"] = display
    c["_Raid"] = {"Seed": seed, "Size": size, "Tier": tier}
    return c


@functools.lru_cache(maxsize=1)
def _names():
    """Oasis name ids of the story castles (random raid castle names)."""
    import castles  # noqa: PLC0415
    return sorted({c["OasisName"] for c in castles.load_pve_castles()
                   if c.get("OasisName") and c["AccountId"] not in BOSS_CASTLES
                   and c["AccountId"] < 60000})  # not region 10's "Gilded ..." copies


def _english_name(oasis_id):
    import level60  # noqa: PLC0415
    try:
        return level60._english().get(str(oasis_id), "Raid castle")
    except OSError:
        return "Raid castle"


def castle(castle_id, account_id=None):
    """Raid castle for the viewer (or account_id)."""
    aid = account_id if account_id is not None else getattr(VIEWER, "value", None)
    seed, size, _ = seed_and_size(aid)
    return copy.deepcopy(_build(int(castle_id), seed, size))


def selection(account_id, hero_level=None):
    """{ring: [castles]} for the castle selection: every tier with VARIANTS
    castles, the 12 tiers spread over the RINGS rings (up to 12 castles a
    ring, VisualAttackSelectionSettings.NumberOfCastlePerLevel)."""
    out = {}
    levels = [lv for lv in LEVELS if lv != 60]   # 60 is the region boss
    for i, lv in enumerate(levels):
        out.setdefault(i * RINGS // len(levels), []).append(castle(castle_id(lv), account_id))
    return out


def menu(account_id):
    """Raid castles the party leader can pick: [{Id, Level, Name, Boss}]."""
    out = []
    for lv in LEVELS:
        c = castle(castle_id(lv), account_id)
        out.append({"Id": c["AccountId"], "Level": c["Level"], "Name": c["AccountDisplayName"],
                    "Boss": lv in BOSS_LEVELS})
    return out


def bonus(tier, size):
    """Party bonus for clearing a raid together: (gold, life force,
    [(material quality, count)])."""
    # material qualities that exist: Basic, Exceptional, Legendary, Epic
    quality = ("Basic" if tier < 20 else "Exceptional" if tier < 40 else
               "Legendary" if tier < 55 else "Epic")
    amount = 120 * tier * size
    return amount, amount, [(quality, 2 + size // 2)]


def home_region(account):
    """The player's own region (story progress) for the game start and the
    Attack button (party.html): the region in progress (Status 2) with the
    highest id of the selected hero, without Friendzone (1), Competitions
    (2) and the co-op raids; else the highest completed one. The client
    itself opened the co-op raids (11, the highest id) at every start."""
    heroes = account.get("Heroes") or []
    hero = next((h for h in heroes if h.get("HeroSpecContainerId") == account.get("SelectedHeroId")),
                heroes[0] if heroes else account)
    regions = [r for r in hero.get("AttackRegions") or account.get("AttackRegions") or []
               if r.get("AttackRegionId") not in (1, 2, REGION_ID) and r.get("Status", 0) >= 2]
    if not regions:
        return 3
    return max(regions, key=lambda r: (r["Status"] == 2, r["AttackRegionId"]))["AttackRegionId"]
