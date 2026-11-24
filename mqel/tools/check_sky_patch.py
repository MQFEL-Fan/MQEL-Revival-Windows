"""Checks the exe sky patch (server/level60.py patch_exe) before a restart.

Prints the patched default case of the castle-selection sky switch, the sky
name each region id gets, and the base relocations inside the patched code.
Exit code 1 if the patch was not applied or the relocations are wrong.

    python tools/check_sky_patch.py [path to the client exe]

Default exe: server/state/tls/MightyQuest_local.exe (the --client-exe of the
live server). Needs `pip install capstone` for the disassembly (optional).
See docs/93-region-sky.md.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import level60  # noqa: E402


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "server", "state", "tls", "MightyQuest_local.exe")
    exe = open(path, "rb").read()
    patched = level60.patch_exe(exe)
    if patched == exe:
        print("NOT PATCHED: patch_exe left the exe unchanged (pattern, padding or relocation check failed)")
        return 1
    pe = struct.unpack_from("<I", exe, 0x3c)[0]
    base = struct.unpack_from("<I", exe, pe + 52)[0]
    opt = struct.unpack_from("<H", exe, pe + 20)[0]
    secs = []
    for i in range(struct.unpack_from("<H", exe, pe + 6)[0]):
        o = pe + 24 + opt + 40 * i
        secs.append(struct.unpack_from("<IIII", exe, o + 8))

    def v2f(v):
        for vs, va, rs, raw in secs:
            if base + va <= v < base + va + rs:
                return v - base - va + raw

    def f2v(f):
        for vs, va, rs, raw in secs:
            if raw <= f < raw + rs:
                return base + va + f - raw

    def cstr(data, v):
        f = v2f(v)
        return data[f:f + 32].split(b"\0")[0].decode("latin-1") if f is not None else "?"

    at = exe.find(level60._SKY_SWITCH)
    jmp = at + len(level60._SKY_SWITCH) + 4
    table = v2f(struct.unpack_from("<I", exe, jmp + 3)[0])
    dflt = jmp + struct.unpack_from("<i", exe, at + len(level60._SKY_SWITCH))[0]
    print("sky switch at %x, default case at %x" % (f2v(at), f2v(dflt)))
    for i in range(9):
        case = v2f(struct.unpack_from("<I", exe, table + 4 * i)[0])
        print("  region %2d -> %s" % (i + 1, cstr(exe, struct.unpack_from("<I", exe, case + 5)[0])))
    print("  region 10 -> %s   (patched default case)" % cstr(patched, struct.unpack_from("<I", patched, dflt + 8)[0]))
    print("  region 11+ -> %s   (patched default case)" % cstr(patched, struct.unpack_from("<I", patched, dflt + 15)[0]))
    try:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for ins in md.disasm(patched[dflt:dflt + 22], f2v(dflt)):
            print("    %x  %s %s" % (ins.address, ins.mnemonic, ins.op_str))
    except ImportError:
        print("    (pip install capstone for the disassembly)")
    rva = f2v(dflt) - base
    have = level60._relocations_in(patched, rva, 23)
    want = {rva + 8, rva + 15}
    print("relocations in the patched code:", sorted(hex(r + base) for r in have))
    if have != want:
        print("WRONG RELOCATIONS: expected", sorted(hex(r + base) for r in want))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
