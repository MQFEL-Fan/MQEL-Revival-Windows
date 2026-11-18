"""Schimpfwortfilter (Ersatz für CleanSpeak, das der Original-Server über
ProfanityManager/ProfanityCleanspeakDAL befragte).

Wortlisten: LDNOOBW („List of Dirty, Naughty, Obscene and Otherwise Bad
Words“, CC-BY-4.0, server/data/profanity/<sprache>.txt). Alle Sprachen
gelten zusammen, weil Chaträume gemischt sind. Gefunden werden nur ganze
Wörter (Groß-/Kleinschreibung egal, einfache Ziffern-Umschreibungen wie
4→a, 3→e), ersetzt wird jedes Zeichen durch „*“. Ob der Client den
gefilterten Text zeigt, entscheidet er selbst nach der Option
„Profanity filter“ (Account.ProfanityFiltering).
"""

import os
import re

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "profanity")

# Einträge, die in einer anderen Spielsprache harmlose Wörter sind
# (fr „con“ = es/it „mit“, fr „bite“ = en „beißen“, ...)
HARMLESS = {"con", "bite", "mama", "gol", "trio", "pele", "fing", "saco",
            "mona", "cu", "pau", "xx", "sexo", "nazi", "cul", "pis", "byk",
            "segg", "fava", "biga", "topa"}

LEET = str.maketrans({"4": "a", "@": "a", "3": "e", "1": "i",
                      "0": "o", "5": "s", "$": "s", "7": "t"})


def _load():
    words = set()
    try:
        names = sorted(os.listdir(DIR))
    except OSError:
        return None
    for name in names:
        if not name.endswith(".txt"):
            continue
        with open(os.path.join(DIR, name), encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w and w not in HARMLESS:
                    words.add(w)
    if not words:
        return None
    # längere Einträge zuerst, damit Wortgruppen vor ihren Teilen greifen;
    # Leerzeichen in Wortgruppen passen auf beliebigen Leerraum
    alts = (r"\s+".join(map(re.escape, w.split()))
            for w in sorted(words, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)")


PATTERN = _load()


def filter_text(text):
    """Text mit Schimpfwörtern durch „*“ ersetzt (gleiche Länge)."""
    if not text or PATTERN is None:
        return text
    norm = text.lower().translate(LEET)
    if len(norm) != len(text):  # Sonderfälle wie „İ“: ohne Umschreibung
        norm = text.lower()
        if len(norm) != len(text):
            return text
    out, last = [], 0
    for m in PATTERN.finditer(norm):
        out.append(text[last:m.start()])
        out.append(re.sub(r"\S", "*", text[m.start():m.end()]))
        last = m.end()
    if not out:
        return text
    out.append(text[last:])
    return "".join(out)
