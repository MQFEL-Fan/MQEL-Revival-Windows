"""Loot filter for the hero (2026-11-24, docs/96-loot-filter.md).

The game's Settings window has "Loot pick-up by Pet": the user setting
AttackUserSettings.MinHeroItemQualityToPickUp (0 = everything, 1 = Magic
and up, 2 = Exceptional, 3 = Legendary, 4 = Epic only). Only the pet's
behaviour (data: CREATURESSETTINGS PetBehavior) reads it; the hero still
collected every item within LootAttractionDistance. The Setting Mod panel
(ui_mods/keybind_panel.html) adds "Loot pick-up by Player": with it on, the
hero (and the pet) leave hero items (equipment and weapons, loot type 3)
below that quality on the ground. Currency, materials, potions, orbs and
XP are never filtered.

Exe patch (MightyQuest.exe 280139, found by byte patterns, unchanged when
anything doesn't match exactly once):

- LootComponent::CollectLoot (0xf0bdd0) walks the entities within
  LootAttractionDistance of a looter; per entity it loads its loot drop
  component, `mov ebp,[esi+0xbc]`, and skips the entity when that is 0. The
  6 bytes become `call hook_collect; nop`: the hook loads ebp and zeroes it
  for a filtered item, so the game skips it.
- The loot drop component's forced pull (0xf0b250, the end-of-castle
  vacuum that flies all loot to the hero): `mov esi,ecx; cmp byte
  [esi+0x71],0` becomes `call hook_pull; nop`; for a filtered item the hook
  sets ZF, the game takes its "not yet" branch and the item stays.
- filter(drop component): loot data [comp+0x84], type [+0x14] == 3, world
  [comp+0x2c], user setting [[[world+0x46b0]+0x114]+4] > 0, quality =
  the game's own HeroItemQuality function (the one the pet's
  HeroItemLootSelection uses: cdecl (item [data+8], [world+0x46cc])) below
  the setting, and the player option on: XInputGetCapabilities(0x4D51454C
  "MQEL", 0, buf) == 0x4D510001, answered by the WASD helper DLL
  (tools/wasd, WASD.ini LootPlayer). Without the helper the real XInput
  returns an error: filter off, the game behaves as before.

The code goes into int3 padding near CollectLoot; the absolute IAT address
gets a base relocation (ASLR, see level60._add_relocation).
"""
import re
import struct

import level60

MAGIC_ASK = 0x4D51454C          # "MQEL"
MAGIC_ON = 0x4D510001

# mov eax,[eax+8]; mov esi,[eax+ebx*4]; | mov ebp,[esi+0xbc] |; test ebp,ebp; je
_COLLECT = bytes.fromhex("8b4008 8b3498") + bytes.fromhex("8baebc000000") + bytes.fromhex("85ed 0f84")
_COLLECT_AT = 6                 # offset of the 6 replaced bytes
# sub esp,0x58; push esi; | mov esi,ecx; cmp byte [esi+0x71],0 |; je
_PULL = bytes.fromhex("83ec58 56") + bytes.fromhex("8bf1 807e7100") + bytes.fromhex("0f84")
_PULL_AT = 4
# the pet's HeroItemLootSelection: push [eax+0x46cc]; push [ebp+8]; call quality
_QUALITY = bytes.fromhex("8b8200020000 ffb0cc460000 ff7508 e8")


def _pe(exe):
    pe = struct.unpack_from("<I", exe, 0x3c)[0]
    base = struct.unpack_from("<I", exe, pe + 52)[0]
    optsz = struct.unpack_from("<H", exe, pe + 20)[0]
    secs = []
    for i in range(struct.unpack_from("<H", exe, pe + 6)[0]):
        o = pe + 24 + optsz + 40 * i
        name = exe[o:o + 8].rstrip(b"\0")
        vsize, va, rsize, raw = struct.unpack_from("<IIII", exe, o + 8)
        secs.append((name, vsize, va, rsize, raw))
    return pe, base, secs


def _once(exe, pattern):
    at = exe.find(pattern)
    if at < 0 or exe.find(pattern, at + 1) >= 0:
        return None
    return at


def _iat(exe, pe, base, secs, dll, func):
    """VA of the import address slot of dll!func, or None."""
    def f(rva):
        for _n, vs, va, rs, raw in secs:
            if va <= rva < va + max(vs, rs):
                return rva - va + raw
        return None
    imp = f(struct.unpack_from("<I", exe, pe + 24 + 96 + 8)[0])
    if imp is None:
        return None
    while True:
        oft, _ts, _fc, name, ft = struct.unpack_from("<IIIII", exe, imp)
        if name == 0:
            return None
        n = exe[f(name):f(name) + 64].split(b"\0")[0]
        if n.lower() == dll.lower():
            k = 0
            while True:
                thunk = struct.unpack_from("<I", exe, f(oft or ft) + 4 * k)[0]
                if thunk == 0:
                    return None
                if not thunk & 0x80000000:
                    if exe[f(thunk) + 2:f(thunk) + 2 + len(func) + 1] == func + b"\0":
                        return base + ft + 4 * k
                k += 1
        imp += 20


def patch_exe(exe):
    """exe with the hero loot filter, or unchanged (other exe version,
    already patched, no room, not a PE file)."""
    if exe.find(_COLLECT) < 0 or exe.find(_PULL) < 0:
        return exe
    try:
        return _patch(exe)
    except (struct.error, IndexError, TypeError, ValueError):
        return exe


def _patch(exe):
    pe, base, secs = _pe(exe)
    text = next((s for s in secs if s[0] == b".text"), None)
    if text is None:
        return exe
    _n, _vs, tva, trs, traw = text

    def va(fo):
        return base + tva + fo - traw

    collect = _once(exe, _COLLECT)
    pull = _once(exe, _PULL)
    quality_site = _once(exe, _QUALITY)
    if collect is None or pull is None or quality_site is None:
        return exe
    rel = struct.unpack_from("<i", exe, quality_site + len(_QUALITY))[0]
    quality = va(quality_site + len(_QUALITY) + 4) + rel
    iat = _iat(exe, pe, base, secs, b"XINPUT9_1_0.dll", b"XInputGetCapabilities")
    if iat is None:
        return exe

    # cave: int3 padding near CollectLoot (code is ~180 bytes)
    need = 192
    best = None
    for m in re.finditer(rb"\xcc{%d,}" % (need + 32), exe[traw:traw + trs]):
        fo = traw + m.start()
        if best is None or abs(fo - collect) < abs(best[0] - collect):
            best = (fo, len(m.group()))
    if best is None:
        return exe
    cave = (best[0] + 16) & ~15              # keep int3s before the code
    if cave + need > best[0] + best[1] - 8:
        return exe

    def rel32(frm_fo, to_va):              # frm_fo: file offset after the insn
        return struct.pack("<i", to_va - va(frm_fo))

    hook_collect = cave
    hook_pull = cave + 32
    filt = cave + 64
    code = bytearray(b"\xcc" * need)

    # hook_collect: mov ebp,[esi+0xbc]; test ebp,ebp; jz done; push ebp;
    #   call filter; add esp,4; test al,al; jz done; xor ebp,ebp; done: ret
    hc = (bytes.fromhex("8baebc000000 85ed 740f 55 e8") + b"\0\0\0\0"
          + bytes.fromhex("83c404 84c0 7402 33ed c3"))
    code[0:len(hc)] = hc
    code[12:16] = rel32(hook_collect + 16, va(filt))

    # hook_pull: mov esi,ecx; push esi; call filter; add esp,4; test al,al;
    #   jnz filtered; cmp byte [esi+0x71],0; ret; filtered: xor eax,eax; ret
    hp = (bytes.fromhex("8bf1 56 e8") + b"\0\0\0\0"
          + bytes.fromhex("83c404 84c0 7505 807e7100 c3 33c0 c3"))
    code[32:32 + len(hp)] = hp
    code[36:40] = rel32(hook_pull + 8, va(filt))

    # filter(comp) -> al: 1 = leave this item on the ground (_filter_code)
    return _assemble(exe, code, filt, hook_collect, hook_pull, collect, pull, quality, iat, va)


def _filter_code(filt_va, quality_va, iat):
    """Bytes of filter() at filt_va."""
    parts = []                     # (bytes, jump-to-no?) pieces

    def op(h):
        parts.append((bytes.fromhex(h), False))

    def jno(opcode):
        parts.append((bytes([opcode, 0]), True))

    op("56 8b742408")                                # push esi; mov esi,[esp+8]
    op("8b8684000000 85c0"); jno(0x74)               # loot data
    op("83781403"); jno(0x75)                        # hero item (type 3)
    op("8b4e2c 85c9"); jno(0x74)                     # world
    op("8b91b0460000 85d2"); jno(0x74)
    op("8b9214010000 85d2"); jno(0x74)               # AttackUserSettings
    op("8b5204 85d2"); jno(0x7e)                     # min quality <= 0: keep
    op("52 ffb1cc460000 ff7008")                     # push min; push settings; push item
    parts.append((b"CALLQ", False))                  # call quality (5 bytes)
    op("83c408 5a 3bc2"); jno(0x7d)                  # quality >= min: keep
    op("83ec20 8bc4 50 6a00")
    parts.append((b"\x68" + struct.pack("<I", MAGIC_ASK), False))
    parts.append((b"\xff\x15" + struct.pack("<I", iat), False))
    parts.append((b"\x83\xc4\x20\x3d" + struct.pack("<I", MAGIC_ON), False))
    jno(0x75)                                        # helper says off: keep
    op("b001 5e c3")                                 # filtered
    no_piece = len(parts)
    op("33c0 5e c3")                                 # keep

    # layout
    offs, at = [], 0
    for b, _j in parts:
        offs.append(at)
        at += len(b)
    no = offs[no_piece]
    out = bytearray()
    iat_at = None
    for (b, j), o in zip(parts, offs):
        if j:
            d = no - (o + 2)
            assert 0 < d < 128
            out += bytes([b[0], d])
        elif b == b"CALLQ":
            out += b"\xe8" + struct.pack("<i", quality_va - (filt_va + o + 5))
        else:
            if b[:2] == b"\xff\x15":
                iat_at = o + 2
            out += b
    return bytes(out), iat_at


def _assemble(exe, code, filt, hook_collect, hook_pull, collect, pull, quality, iat, va):
    fcode, iat_at = _filter_code(va(filt), quality, iat)
    cave = hook_collect
    if 64 + len(fcode) > len(code):
        return exe
    code[64:64 + len(fcode)] = fcode
    out = bytearray(exe)
    out[cave:cave + len(code)] = code
    out[collect + _COLLECT_AT:collect + _COLLECT_AT + 6] = (
        b"\xe8" + struct.pack("<i", va(hook_collect) - va(collect + _COLLECT_AT + 5)) + b"\x90")
    out[pull + _PULL_AT:pull + _PULL_AT + 6] = (
        b"\xe8" + struct.pack("<i", va(hook_pull) - va(pull + _PULL_AT + 5)) + b"\x90")

    _pe_, base, _secs = _pe(exe)

    def rva(fo):
        return va(fo) - base
    # no old relocation may point into the bytes we replaced
    for fo, n in ((cave, len(code)), (collect + _COLLECT_AT, 6), (pull + _PULL_AT, 6)):
        if level60._relocations_in(bytes(out), rva(fo), n):
            return exe
    patched = level60._add_relocation(bytes(out), rva(filt + iat_at))
    if level60._relocations_in(patched, rva(cave), len(code)) != {rva(filt + iat_at)}:
        return exe                      # never ship a half-relocated patch
    return patched
