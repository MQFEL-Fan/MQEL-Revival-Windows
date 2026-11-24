"""Display version of the server's updates (docs/92-versions.md).

Shown in the game's ESC menu (Game menu) on the "Credits" button
(Oasis text 11382, shipped with the DataBin texts, level60.oasis_text_files).
Only a label: the client's own version and the patcher versions keep their
format.

Rules (owner's, 2026-11-22):
- v1.1 = the level-60 update (everything up to level 60 unlocked);
- a big feature: +0.1 (the lower parts start again at 0),
- a small feature: +0.0.1,
- a background fix: +0.0.0.1.
Add one line per update to HISTORY, newest last.
"""

BASE = (1, 1, 0, 0)

# (date, kind "big" | "small" | "fix", title as in PATCH_NOTES.md)
HISTORY = [
    ("2026-11-21", "base", "Level 60 update"),
    ("2026-11-21", "small", "Level 60 fixes"),
    ("2026-11-21", "small", "Castle upgrades for level 60"),
    ("2026-11-21", "small", "Discord status and a new launcher look"),
    ("2026-11-22", "big", "Heroes pack, friends online and events all year"),
    ("2026-11-22", "small", "Cornelius Richling joins our Discord"),
    ("2026-11-22", "big", "The Ingame Market opens, and decorations drop loot"),
    ("2026-11-22", "small", "Ingame Market fixes, more decoration loot, chat and clans"),
    ("2026-11-22", "big", "Parties and Co-op Raids"),
    ("2026-11-22", "small", "Co-op Raids update, one account per player and our privacy policy"),
    ("2026-11-22", "small", "Raid bosses, Ingame Market collect and the version number"),
    ("2026-11-23", "small", "Party raids: pick, ready, start together"),
    ("2026-11-23", "fix", "Attack button crash fixed"),
    ("2026-11-23", "fix", "Co-op Raids sky and banner emblem"),
    ("2026-11-23", "small", "Back home at start, roomier region map, WASD optional"),
    ("2026-11-23", "fix", "Steam login on the first start, party and market on Linux"),
    ("2026-11-23", "small", "Setting Mod and a loot filter for your hero"),
    ("2026-11-23", "big", "Orb numbers, inventory sort and a better Ingame Market"),
    ("2026-11-23", "fix", "Orb numbers in attacks and inside the orb, Sort button"),
    ("2026-11-23", "fix", "Ingame Market and Setting Mod buttons, windows above the building bar"),
    ("2026-11-24", "fix", "Ingame Market: Buy now button no longer covers the next item"),
]

_STEP = {"big": 1, "small": 2, "fix": 3}


def _bump(v, kind):
    i = _STEP[kind]
    v = list(v)
    v[i] += 1
    for j in range(i + 1, 4):
        v[j] = 0
    return tuple(v)


def history():
    """[(version string, date, kind, title)] oldest first."""
    v, out = BASE, []
    for date, kind, title in HISTORY:
        if kind != "base":
            v = _bump(v, kind)
        out.append((text(v), date, kind, title))
    return out


def text(v):
    parts = list(v)
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return "v" + ".".join(str(p) for p in parts)


def current():
    return history()[-1][0]


# Oasis texts that get the version appended (ESC menu, "Credits")
OASIS_CREDITS = 11382


def oasis_suffix():
    # plain ASCII: a JSON escape (backslash-u00b7, a middle dot) made the game drop the whole
    # text file (every text empty, 2026-11-22)
    return " - " + current()
