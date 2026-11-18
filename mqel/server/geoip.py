"""Land eines Spielers aus seiner IP (CountryCode neuer Accounts).

Quelle: db-ip.com "IP to Country Lite" (CC BY 4.0, https://db-ip.com),
geholt per tools/update_geoip.py nach server/data/geoip-country.csv.gz
(Zeilen "erste IP,letzte IP,Land", IPv4 und IPv6). Ohne Datei, für
private/lokale Adressen und unbekannte IPs liefert country() None; der
Aufrufer behält dann den Standard der Vorlage (DE). Abgefragt wird nur
lokal, keine IP verlässt den Server.
"""
import bisect
import csv
import gzip
import ipaddress
import os
import threading

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                    "geoip-country.csv.gz")

_lock = threading.Lock()
_table = None  # {4/6: (Anfänge, Enden, Länder)}, nach Adressen sortiert


def load():
    """Datenbank einlesen (einmal; dauert einige Sekunden)."""
    global _table
    with _lock:
        if _table is None:
            table = {4: ([], [], []), 6: ([], [], [])}
            if os.path.exists(PATH):  # die Datei ist nach Adressen sortiert
                with gzip.open(PATH, "rt", encoding="ascii", newline="") as f:
                    for first, last, cc in csv.reader(f):
                        a = ipaddress.ip_address(first)
                        starts, ends, codes = table[a.version]
                        starts.append(int(a))
                        ends.append(int(ipaddress.ip_address(last)))
                        codes.append(cc)
            _table = table
    return _table


def country(ip):
    """Ländercode (z. B. "DE") zur IP oder None."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if not addr.is_global:
        return None
    starts, ends, codes = load()[addr.version]
    i = bisect.bisect_right(starts, int(addr)) - 1
    if i >= 0 and int(addr) <= ends[i] and codes[i] != "ZZ":
        return codes[i]
    return None
