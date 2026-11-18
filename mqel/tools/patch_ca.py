"""Eigenes Wurzelzertifikat in MightyQuest_profile.exe eintragen (HTTPS).

Die Exe (libcurl + OpenSSL 1.0.1e) vertraut nur vier eingebetteten
PEM-Zertifikaten, die heute niemand mehr nutzt (docs/60-client.md). Der
Patch ersetzt eines davon durch das angegebene PEM; der Rest des Platzes
wird mit Zeilenumbrüchen gefüllt (PEM-Leser überspringen sie), Länge und
Lage aller Bytes bleiben gleich.

Vorgabe ist der Platz des abgelaufenen AddTrust External CA Root.
Taugliche PEMs: das selbstsignierte server/state/tls/cert.pem des
Spielservers (--tls-port; Zertifikat gilt nur für dessen IPs) oder eine
echte Wurzel wie ISRG Root X1 (Let's Encrypt, dann mit Domainnamen).

Gebrauch: python tools/patch_ca.py <exe> <zertifikat.pem> [--out <neue exe>] [--no-fps]

Die so gebaute Exe verteilt der Patcher an alle Spieler:
game_server.py --client-exe <neue exe> (server/patcher.py, GameBin).
"""

import argparse
import re
import sys

# FPS-Anzeige der MightyQuest_profile.exe: `or [0x1c916d8],8` (VA 0xe26e74)
# setzt sie ohne Bedingung, -nofps wirkt nicht; (Datei-Offset, alt, neu)
FPS_PATCH = (0xA2627A, 0x08, 0x00)

PEM_RE = re.compile(rb"-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\r\n]+?-----END CERTIFICATE-----")


def replace_ca(data, pem, slot=3):
    """PEM `pem` (bytes) in den Zertifikatsplatz `slot` von `data`
    (bytearray der Exe) schreiben; liefert (Datei-Offset, Platzgröße)."""
    m = PEM_RE.search(pem.replace(b"\r\n", b"\n"))
    if not m:
        raise ValueError("kein Zertifikat im PEM")
    new = m.group(0)
    slots = list(PEM_RE.finditer(data))
    if len(slots) != 4:
        raise ValueError(f"{len(slots)} eingebettete Zertifikate statt 4: falsche Exe?")
    old = slots[slot]
    size = old.end() - old.start()
    if len(new) > size:
        raise ValueError(f"Zertifikat zu groß ({len(new)} > {size} Bytes), anderen --slot wählen: "
                         + ", ".join(str(s.end() - s.start()) for s in slots))
    data[old.start():old.end()] = new + b"\n" * (size - len(new))
    return old.start(), size


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("exe")
    ap.add_argument("pem")
    ap.add_argument("--out", help="Ziel (Vorgabe: die Exe selbst)")
    ap.add_argument("--slot", type=int, default=3,
                    help="Nummer des ersetzten Zertifikats (0-3, Vorgabe 3 = AddTrust)")
    ap.add_argument("--no-fps", action="store_true",
                    help="zusätzlich die FPS-Anzeige abschalten (1 Byte, s. FPS_PATCH)")
    args = ap.parse_args()

    data = bytearray(open(args.exe, "rb").read())
    try:
        offset, size = replace_ca(data, open(args.pem, "rb").read(), args.slot)
    except ValueError as e:
        sys.exit(f"{args.pem}: {e}")
    if args.no_fps:
        at, old, new = FPS_PATCH
        if data[at] not in (old, new):
            sys.exit(f"Byte 0x{at:x} ist 0x{data[at]:02x}: falsche Exe?")
        data[at] = new
    out = args.out or args.exe
    with open(out, "wb") as f:
        f.write(data)
    print(f"{out}: Zertifikat {args.slot} (0x{offset:x}, {size} Bytes) ersetzt"
          + (", FPS-Anzeige aus" if args.no_fps else ""))


if __name__ == "__main__":
    main()
