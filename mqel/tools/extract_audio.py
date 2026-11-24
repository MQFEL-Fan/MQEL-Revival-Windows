"""Carve the Ogg Vorbis streams out of the game's streaming audio bigfile
(Data/Sounds/HQAudio/PC/Atomic/STREAMING_AUDIO.BFPC) into .ogg files.

  python tools/extract_audio.py <STREAMING_AUDIO.BFPC> <out dir>

Each logical Ogg stream (page with the "beginning of stream" flag to the
page with "end of stream", same serial number) becomes
<out>/<index>_<offset>_<seconds>s.ogg. Prints the Vorbis comments when a
stream has any. Read-only on the game file.
"""
import os
import struct
import sys


def pages(data):
    """(offset, header_type, granule, serial, page bytes) of every Ogg page."""
    pos = data.find(b"OggS")
    while pos != -1:
        if len(data) - pos >= 27 and data[pos + 4] == 0:
            htype = data[pos + 5]
            granule, serial = struct.unpack_from("<qI", data, pos + 6)
            nseg = data[pos + 26]
            if pos + 27 + nseg <= len(data):
                size = 27 + nseg + sum(data[pos + 27:pos + 27 + nseg])
                yield pos, htype, granule, serial, data[pos:pos + size]
                pos = data.find(b"OggS", pos + size)
                continue
        pos = data.find(b"OggS", pos + 4)


def vorbis_info(first_pages):
    """(sample rate, comments) from the identification/comment headers."""
    blob = b"".join(first_pages)
    rate, comments = 0, []
    i = blob.find(b"\x01vorbis")
    if i != -1:
        rate = struct.unpack_from("<I", blob, i + 12)[0]
    j = blob.find(b"\x03vorbis")
    if j != -1:
        try:
            k = j + 7
            vlen = struct.unpack_from("<I", blob, k)[0]
            k += 4 + vlen
            n = struct.unpack_from("<I", blob, k)[0]
            k += 4
            for _ in range(min(n, 50)):
                ln = struct.unpack_from("<I", blob, k)[0]
                comments.append(blob[k + 4:k + 4 + ln].decode("utf-8", "replace"))
                k += 4 + ln
        except struct.error:
            pass
    return rate, comments


def main(src, out):
    with open(src, "rb") as f:
        data = f.read()
    os.makedirs(out, exist_ok=True)
    open_streams, n = {}, 0
    for off, htype, granule, serial, page in pages(data):
        if htype & 2:  # beginning of stream
            open_streams[serial] = {"off": off, "pages": [page], "granule": 0}
            continue
        s = open_streams.get(serial)
        if s is None:
            continue
        s["pages"].append(page)
        if granule > 0:
            s["granule"] = granule
        if htype & 4:  # end of stream
            del open_streams[serial]
            rate, comments = vorbis_info(s["pages"][:3])
            secs = s["granule"] / rate if rate else 0
            name = "%05d_%09d_%.1fs.ogg" % (n, s["off"], secs)
            with open(os.path.join(out, name), "wb") as f:
                f.write(b"".join(s["pages"]))
            if comments:
                print(name, comments)
            n += 1
    print("%d streams written to %s" % (n, out))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
