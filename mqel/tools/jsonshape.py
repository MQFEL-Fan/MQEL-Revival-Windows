"""Print the shape of a JSON file: keys, list lengths, sample scalars."""
import json, sys
def shape(v, ind=0, key="", maxd=6):
    p = "  " * ind
    if isinstance(v, dict):
        print(f"{p}{key}{{{len(v)}}}")
        if ind < maxd:
            for k, x in list(v.items())[:40]:
                shape(x, ind + 1, k + ": ", maxd)
    elif isinstance(v, list):
        print(f"{p}{key}[{len(v)}]")
        if v and ind < maxd:
            shape(v[0], ind + 1, "[0]: ", maxd)
    else:
        print(f"{p}{key}{json.dumps(v)[:80]}")
d = json.load(open(sys.argv[1], encoding="utf-8-sig"))
shape(d, maxd=int(sys.argv[2]) if len(sys.argv) > 2 else 6)
