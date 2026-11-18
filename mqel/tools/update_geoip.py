"""Länder-Datenbank für server/geoip.py holen (db-ip.com IP to Country Lite,
CC BY 4.0, monatlich neu). Der laufende Server liest sie beim nächsten Start.

Aufruf: python tools/update_geoip.py
"""
import datetime
import os
import pathlib
import urllib.request

TARGET = pathlib.Path(__file__).resolve().parent.parent / "server/data/geoip-country.csv.gz"


def main():
    today = datetime.date.today()
    last_month = (today.replace(day=1) - datetime.timedelta(days=1))
    for d in (today, last_month):  # die neue Monatsdatei erscheint erst im Lauf des Monats
        url = f"https://download.db-ip.com/free/dbip-country-lite-{d:%Y-%m}.csv.gz"
        try:
            # mit dem Standard-User-Agent von urllib antwortet db-ip mit 403
            req = urllib.request.Request(url, headers={"User-Agent": "mighty-quest"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except OSError as e:
            print(f"{url}: {e}")
            continue
        TARGET.parent.mkdir(exist_ok=True)
        tmp = TARGET.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, TARGET)
        print(f"{url} -> {TARGET} ({len(data)} Bytes)")
        return
    raise SystemExit("keine Datei geladen")


if __name__ == "__main__":
    main()
