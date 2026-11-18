"""Cheat-Erkennung wie im Original (AntiCheatManager): nur protokollieren,
nicht sperren. Sperren macht der Admin im Webtool.

- Hack-Flags: der Client meldet bei jeder Anfrage im Header "rnd"
  ClientHackFlags, gemischt mit Zufallsbits (DoNotUseRandom*). Ändern sich
  die echten Bits, schreibt der Server einen ClientHack-Eintrag (1402).
- Kampfende: die Prüfungen aus AttackManager.GetValidatedEndAttackParams.
  Die Beute deckelt attack.end_attack ohnehin auf das beim Start
  Angebotene; hier wird nur gemeldet, was ein ehrlicher Client nie
  schickt (CheatFailure, 1401, CheatContext 1 = EndAttack).
"""

import time

# ClientHackFlags (Contracts.Enum) -> Feld des ClientHackTrackingEntity
HACK_FLAGS = {
    2: "OllyDebugRunning",
    8: "CheatEngineRunning",
    32: "HardwareBreakpointTampered",
    128: "SpeedHackInjected",
    512: "DebuggerAttached",
    2048: "ImportTableHacked",
    8192: "CheatEngineDllInjected",
}
HACK_MASK = sum(HACK_FLAGS)

CHEAT_CONTEXT_END_ATTACK = 1

# Echtzeit zwischen StartAttack und EndAttack darf die gemeldete Spielzeit
# nicht unterschreiten (Speedhack, nachgebaute Anfrage); ehrliche Kämpfe
# liegen im Log mindestens 0,8 s darüber. Spielraum für Rundung.
TIME_GRACE_S = 1.0

# DeactivatedTrapIds fehlt bewusst: Fallen werden wieder scharf und können
# im selben Kampf erneut entschärft werden, der Client meldet die ID dann
# mehrfach. Die Liste bringt keine Beute, Duplikate sind harmlos.
ID_LISTS = ("KilledCreatureIds",
            "LootedGoldCreatureIds", "LootedGoldTrapIds",
            "LootedLifeForceCreatureIds", "LootedLifeForceTrapIds")


def hack_flags(header):
    """Echte ClientHackFlags aus dem Header rnd (0 bei fehlendem/kaputtem)."""
    try:
        return int(header or 0) & HACK_MASK
    except ValueError:
        return 0


def hack_fields(flags):
    """Felder des ClientHack-Tracking-Eintrags."""
    return {name: bool(flags & bit) for bit, name in HACK_FLAGS.items()}


def end_attack_violations(params, cur):
    """Liste der Verstöße (Texte wie im Original) für EndAttack-Parameter
    gegen den laufenden Angriff (attack.AttackSession.current)."""
    out = []
    frames = params.get("AttackFrameCount", 0) or 0
    if (params.get("TreasureRoomOpenFrameCount", 0) or 0) > frames:
        out.append("TreasureRoomOpenFrameCount is greater than AttackFrameCount")
    for key in ID_LISTS:
        ids = params.get(key) or []
        if len(set(ids)) != len(ids):
            out.append(f"Duplicate ids in {key}")
    rating = params.get("CastleRating", 0) or 0
    if not 0 <= rating <= 5:
        out.append(f"Castle rating ({rating}) must be between 0 and 5")
    if not cur:
        # Angriff vor einem Server-Neustart begonnen: kein Angebot zum Abgleich
        return out
    gold_max, lf_max = cur.get("treasure", (0, 0))
    if (params.get("TreasureRoomLootedGold", 0) or 0) > gold_max:
        out.append(f"Stole more gold than allowed ({params['TreasureRoomLootedGold']} "
                   f"instead of max {gold_max})")
    if (params.get("TreasureRoomLootedLifeForce", 0) or 0) > lf_max:
        out.append(f"Stole more life force than allowed "
                   f"({params['TreasureRoomLootedLifeForce']} instead of max {lf_max})")
    buildings = cur.get("buildings") or {}
    materials = cur.get("material_mines") or {}
    seen = set()
    for p in params.get("PillagedMines") or []:
        bid = p.get("CastleBuildingId")
        b = buildings.get(bid)
        if bid in materials:
            pass  # Material-O-Matic: Zutaten statt Betrag, siehe attack._pillaged_materials
        elif b is None:
            if p.get("StolenAmount", 0):  # leere/geschützte Minen meldet der Client mit 0
                out.append(f"Stole from an inexisting mine (buildingid {bid})")
        elif (p.get("StolenAmount", 0) or 0) > b[1]:
            out.append(f"Stole more than allowed on mine {bid} "
                       f"({p['StolenAmount']} instead of max {b[1]})")
        if bid in seen:
            out.append("Duplicate pillaged mines")
        seen.add(bid)
    started = cur.get("started")
    if started is not None:
        game_s = frames * (params.get("AttackFrameDuration", 0) or 0)
        wall_s = time.monotonic() - started
        if wall_s + TIME_GRACE_S < game_s:
            out.append(f"Time between StartAttack and EndAttack ({wall_s:.1f}s) "
                       f"shorter than attack duration ({game_s:.1f}s)")
    return out
