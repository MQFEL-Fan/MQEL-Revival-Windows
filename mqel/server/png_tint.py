"""Minimal PNG tinting without Pillow (8-bit RGBA, non-interlaced, as the
game's UI images are). Used for the gold island of region 10 on the region
map (ui_patches.py patch 13): the game's old browser doesn't zoom elements
with -webkit-filter correctly, so the tint is baked into the image."""

import base64
import struct
import zlib


def _chunks(data):
    pos = 8
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        yield kind, data[pos + 8:pos + 8 + n]
        pos += 12 + n


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(data):
    """(width, height, rows of RGBA bytearrays); 8-bit RGB is read as RGBA."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("no PNG")
    idat = b""
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace:
                raise ValueError("only 8-bit RGB(A), non-interlaced")
        elif kind == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    bpp = 4 if ctype == 6 else 3
    stride, rows, prev = w * bpp, [], bytearray(w * bpp)
    pos = 0
    for _ in range(h):
        f = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                line[i] = (line[i] + _paeth(a, b, c)) & 255
        rows.append(line)
        prev = line
    if bpp == 3:
        rows = [bytearray(b for i in range(0, len(r), 3) for b in (r[i], r[i + 1], r[i + 2], 255))
                for r in rows]
    return w, h, rows


def encode(w, h, rows):
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# Gold gradient: shadow -> gold -> highlight (by brightness)
GOLD = ((52, 30, 6), (214, 158, 34), (255, 236, 150))


def _gold(lum):
    lo, mid, hi = GOLD
    if lum < 0.5:
        t, a, b = lum * 2, lo, mid
    else:
        t, a, b = (lum - 0.5) * 2, mid, hi
    return [round(a[k] + (b[k] - a[k]) * t) for k in range(3)]


def tint_gold(data, strength=1.0, contrast=1.15, box=None):
    """PNG bytes, gold-tinted (alpha kept); strength 0..1 blends with the
    original colors; box (x0, y0, x1, y1): only that area."""
    w, h, rows = decode(data)
    x0, y0, x1, y1 = box or (0, 0, w, h)
    cache = {}
    for y, line in enumerate(rows):
        if not y0 <= y < y1:
            continue
        for i in range(4 * x0, 4 * min(x1, w), 4):
            if not line[i + 3]:
                continue
            r, g, b = line[i], line[i + 1], line[i + 2]
            key = (r, g, b)
            if key not in cache:
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                lum = min(1.0, max(0.0, (lum - 0.5) * contrast + 0.5))
                gr, gg, gb = _gold(lum)
                cache[key] = (round(r + (gr - r) * strength),
                              round(g + (gg - g) * strength),
                              round(b + (gb - b) * strength))
            line[i], line[i + 1], line[i + 2] = cache[key]
    return encode(w, h, rows)


def paste_ellipse(base_png, top_png, center_base, center_top, rx, ry, feather=8):
    """base with an ellipse (radii rx, ry, soft edge `feather` px) of top
    pasted on it, the two centers aligned; alpha-blended. Used to put the
    dragon medallion of Upper Bestmount's island on region 10's island."""
    w, h, base = decode(base_png)
    tw, th, top = decode(top_png)
    cbx, cby = center_base
    ctx, cty = center_top
    for y in range(max(0, int(cby - ry)), min(h, int(cby + ry) + 1)):
        for x in range(max(0, int(cbx - rx)), min(w, int(cbx + rx) + 1)):
            d = ((x - cbx) / rx) ** 2 + ((y - cby) / ry) ** 2
            if d > 1:
                continue
            tx, ty = int(round(x - cbx + ctx)), int(round(y - cby + cty))
            if not (0 <= tx < tw and 0 <= ty < th):
                continue
            edge = (1 - d ** 0.5) * min(rx, ry) / feather
            k = min(1.0, edge) * top[ty][4 * tx + 3] / 255.0
            if k <= 0:
                continue
            i, j = 4 * x, 4 * tx
            ba = base[y][i + 3] / 255.0
            oa = k + ba * (1 - k)
            for c in range(3):
                v = (top[ty][j + c] * k + base[y][i + c] * ba * (1 - k)) / oa if oa else 0
                base[y][i + c] = int(round(v))
            base[y][i + 3] = int(round(oa * 255))
    return encode(w, h, base)


def data_uri(png):
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def fit(data, w, h, margin=0.1):
    """PNG `data` centered on a transparent w x h canvas, its visible part
    (alpha > 96) scaled to fit inside the margin (box filter down, nearest
    up)."""
    sw, sh, rows = decode(data)
    xs = [x for r in rows for x in range(sw) if r[4 * x + 3] > 96]
    ys = [y for y, r in enumerate(rows) if max(r[3::4]) > 96]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    scale = min(w * (1 - 2 * margin) / (x1 - x0), h * (1 - 2 * margin) / (y1 - y0))
    tw, th = max(1, int((x1 - x0) * scale)), max(1, int((y1 - y0) * scale))
    ox, oy = (w - tw) // 2, (h - th) // 2
    out = [bytearray(4 * w) for _ in range(h)]
    for ty in range(th):
        sy0 = y0 + ty / scale
        sy1 = max(sy0 + 1, y0 + (ty + 1) / scale)
        for tx in range(tw):
            sx0 = x0 + tx / scale
            sx1 = max(sx0 + 1, x0 + (tx + 1) / scale)
            acc, n = [0, 0, 0, 0], 0
            for yy in range(int(sy0), min(sh, int(sy1 + 0.999))):
                r = rows[yy]
                for xx in range(int(sx0), min(sw, int(sx1 + 0.999))):
                    a = r[4 * xx + 3]
                    acc[0] += r[4 * xx] * a
                    acc[1] += r[4 * xx + 1] * a
                    acc[2] += r[4 * xx + 2] * a
                    acc[3] += a
                    n += 1
            o = out[oy + ty]
            i = 4 * (ox + tx)
            if acc[3]:
                o[i:i + 3] = bytes(round(acc[c] / acc[3]) for c in range(3))
            o[i + 3] = round(acc[3] / n) if n else 0
    return encode(w, h, out)


def encode_rgb(w, h, rows):
    """8-bit RGB PNG (like the game's card files) from RGBA or RGB rows."""
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))
    out = []
    for r in rows:
        if len(r) == 4 * w:
            r = bytearray(b for i in range(0, len(r), 4) for b in r[i:i + 3])
        out.append(b"\x00" + bytes(r))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(out), 9)) + chunk(b"IEND", b""))


def glow_rows(w, h, edge, center):
    """RGBA rows: radial gradient from `center` color (middle) to `edge`."""
    rows = []
    for y in range(h):
        r = bytearray(4 * w)
        for x in range(w):
            d = min(1.0, (((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) ** 0.5)
            t = d * d
            r[4 * x:4 * x + 4] = bytes([round(center[c] + (edge[c] - center[c]) * t) for c in range(3)] + [255])
        rows.append(r)
    return rows


def paste(rows, top_png, x0, y0):
    """Alpha-blend PNG `top_png` onto RGBA `rows` at x0, y0 (in place)."""
    tw, th, top = decode(top_png)
    for y in range(th):
        if not 0 <= y0 + y < len(rows):
            continue
        dst, src = rows[y0 + y], top[y]
        for x in range(tw):
            i, j = 4 * (x0 + x), 4 * x
            if not 0 <= i < len(dst):
                continue
            a = src[j + 3] / 255
            if a:
                for c in range(3):
                    dst[i + c] = round(dst[i + c] * (1 - a) + src[j + c] * a)
    return rows


PURPLE = ((36, 12, 64), (132, 72, 206), (238, 214, 255))   # co-op region / party button


def tint_color(data, palette, strength=1.0, contrast=1.15):
    """Like tint_gold with another palette (dark, middle, light RGB)."""
    lo, mid, hi = palette
    w, h, rows = decode(data)
    cache = {}
    for line in rows:
        for i in range(0, 4 * w, 4):
            if not line[i + 3]:
                continue
            key = (line[i], line[i + 1], line[i + 2])
            if key not in cache:
                r, g, b = key
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                lum = min(1.0, max(0.0, (lum - 0.5) * contrast + 0.5))
                if lum < 0.5:
                    t, a, c = lum * 2, lo, mid
                else:
                    t, a, c = (lum - 0.5) * 2, mid, hi
                tc = [a[k] + (c[k] - a[k]) * t for k in range(3)]
                cache[key] = tuple(round(key[k] + (tc[k] - key[k]) * strength) for k in range(3))
            line[i], line[i + 1], line[i + 2] = cache[key]
    return encode(w, h, rows)


def group_icon(data, frame_h=40, scale=0.7, lift=6, behind=0.85):
    """Lobby-bar sprite (frames stacked vertically) with a smaller copy of
    the glyph behind it, top center: the Friends icon (two people) becomes
    a group of three for the party button (same colours, same style)."""
    w, h, rows = decode(data)
    out = [bytearray(r) for r in rows]
    for top in range(0, h, frame_h):
        fh = min(frame_h, h - top)
        sw, sh = int(w * scale), int(fh * scale)
        ox, oy = (w - sw) // 2, max(0, (fh - sh) // 2 - lift)
        small = []
        for y in range(sh):
            sy = top + int(y / scale)
            line = rows[sy]
            small.append([tuple(line[4 * int(x / scale): 4 * int(x / scale) + 4]) for x in range(sw)])
        # draw the small copy first, then the original glyph over it
        frame = [bytearray(4 * w) for _ in range(fh)]
        for y in range(sh):
            for x in range(sw):
                r, g, b, a = small[y][x]
                if a:
                    i = 4 * (ox + x)
                    frame[oy + y][i:i + 4] = bytes((int(r * behind), int(g * behind), int(b * behind), a))
        for y in range(fh):
            src = rows[top + y]
            for x in range(w):
                i = 4 * x
                a = src[i + 3]
                if a:
                    fa = frame[y][i + 3]
                    if a >= 250 or not fa:
                        frame[y][i:i + 4] = src[i:i + 4]
                    else:  # blend over the copy behind
                        t = a / 255
                        frame[y][i:i + 4] = bytes((round(src[i] * t + frame[y][i] * (1 - t)),
                                                   round(src[i + 1] * t + frame[y][i + 1] * (1 - t)),
                                                   round(src[i + 2] * t + frame[y][i + 2] * (1 - t)),
                                                   max(a, fa)))
        for y in range(fh):
            out[top + y] = frame[y]
    return encode(w, h, out)


def party_icon(data, frame_h=40, scale=0.62):
    """Lobby-bar sprite: two smaller copies of the Friends glyph side by
    side (four people, a party of up to 4), back pair slightly higher."""
    w, h, rows = decode(data)
    out = [bytearray(r) for r in rows]
    for top in range(0, h, frame_h):
        fh = min(frame_h, h - top)
        sw, sh = int(w * scale), int(fh * scale)
        frame = [bytearray(4 * w) for _ in range(fh)]
        # back pair (right, higher, a little darker), then front pair (left, lower)
        for ox, oy, dim in ((w - sw - 1, (fh - sh) // 2 - 4, 0.8), (1, (fh - sh) // 2 + 5, 1.0)):
            for y in range(sh):
                src = rows[top + int(y / scale)]
                for x in range(sw):
                    j = 4 * int(x / scale)
                    a = src[j + 3]
                    if not a or not (0 <= oy + y < fh):
                        continue
                    i = 4 * (ox + x)
                    t = a / 255
                    dst = frame[oy + y]
                    dst[i:i + 4] = bytes((round(src[j] * dim * t + dst[i] * (1 - t)),
                                          round(src[j + 1] * dim * t + dst[i + 1] * (1 - t)),
                                          round(src[j + 2] * dim * t + dst[i + 2] * (1 - t)),
                                          max(a, dst[i + 3])))
        for y in range(fh):
            out[top + y] = frame[y]
    return encode(w, h, out)


def _tile_colour(rows, top, frame_h, w):
    """Most common opaque colour of a frame: the button's tile."""
    count = {}
    for y in range(top, top + frame_h):
        r = rows[y]
        for x in range(w):
            if r[4 * x + 3] == 255:
                k = bytes(r[4 * x:4 * x + 3])
                count[k] = count.get(k, 0) + 1
    return max(count, key=count.get)


def party_icon_tiled(friends, tile, frame_h=40, scale=0.62):
    """Party sprite on the dark-blue tile of the 2015 lobby buttons
    (2026-11-24): `friends` and `tile` are the 2015 BtnFriends and
    BtnNotifications sprites (tile normal / hover / pressed, one frame each).
    The Friends glyph is cut from its tile, made a party (party_icon) and
    drawn on the Notifications tile, so the button matches its neighbours."""
    w, h, frows = decode(friends)
    tw, th, trows = decode(tile)
    if (tw, th) != (w, h):
        raise ValueError("sprites of different size")
    glyph = []
    for top in range(0, h, frame_h):
        key = _tile_colour(frows, top, min(frame_h, h - top), w)
        for y in range(top, min(top + frame_h, h)):
            r = bytearray(frows[y])
            for x in range(w):
                if bytes(r[4 * x:4 * x + 3]) == key or r[4 * x + 3] < 255:
                    r[4 * x + 3] = 0  # tile and its rounded edge
            glyph.append(r)
    _, _, grows = decode(party_icon(encode(w, h, glyph), frame_h, scale))
    out = []
    for top in range(0, h, frame_h):
        bg = _tile_colour(trows, top, min(frame_h, h - top), w)
        for y in range(top, min(top + frame_h, h)):
            t, g, row = trows[y], grows[y], bytearray(4 * w)
            for x in range(w):
                i = 4 * x
                ga = g[i + 3] / 255
                row[i:i + 4] = bytes((round(g[i] * ga + bg[0] * (1 - ga)),
                                      round(g[i + 1] * ga + bg[1] * (1 - ga)),
                                      round(g[i + 2] * ga + bg[2] * (1 - ga)),
                                      t[i + 3]))
            out.append(row)
    return encode(w, h, out)
