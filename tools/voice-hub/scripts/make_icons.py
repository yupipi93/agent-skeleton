#!/usr/bin/env python3
"""Draw the app icons (PNG) with the standard library: no image tooling needed.

A rounded square in the accent colour with four waveform bars, plus a maskable variant
whose bars sit inside the 40 %-radius safe circle Android crops to.
"""
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "avh", "web", "icons")
BG = (0xD1, 0x60, 0x3A)
FG = (0xFF, 0xFF, 0xFF)
# x centre, half height (fractions of the icon side)
BARS = [(0.27, 0.13), (0.42, 0.25), (0.58, 0.34), (0.73, 0.19)]


def png(path, size, pixels):
    raw = b"".join(b"\x00" + bytes(pixels[y * size * 4:(y + 1) * size * 4]) for y in range(size))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(data)


def inside_round_rect(x, y, size, radius):
    r = radius
    cx = min(max(x, r), size - r)
    cy = min(max(y, r), size - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def draw(size, maskable):
    px = bytearray(size * size * 4)
    scale = 0.62 if maskable else 1.0     # shrink bars into the safe zone
    bar_w = size * 0.085 * scale
    for y in range(size):
        for x in range(size):
            i = (y * size + x) * 4
            bg = maskable or inside_round_rect(x + .5, y + .5, size, size * 0.22)
            if not bg:
                continue
            colour = BG
            for bx, bh in BARS:
                cx = size / 2 + (bx - 0.5) * size * scale
                hh = bh * size * scale
                # Rounded bar: a capsule from (cx, mid-hh) to (cx, mid+hh).
                dy = max(0.0, abs(y + .5 - size / 2) - (hh - bar_w / 2))
                if (x + .5 - cx) ** 2 + dy * dy <= (bar_w / 2) ** 2:
                    colour = FG
                    break
            px[i:i + 4] = bytes(colour + (255,))
    return px


def main():
    os.makedirs(OUT, exist_ok=True)
    for size in (192, 512):
        png(os.path.join(OUT, "icon-%d.png" % size), size, draw(size, False))
    png(os.path.join(OUT, "icon-maskable-512.png"), 512, draw(512, True))
    with open(os.path.join(OUT, "favicon.svg"), "w") as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
                 '<rect width="32" height="32" rx="7" fill="#d1603a"/><g fill="#fff">'
                 '<rect x="7" y="12" width="3" height="8" rx="1.5"/>'
                 '<rect x="12" y="8" width="3" height="16" rx="1.5"/>'
                 '<rect x="17" y="5" width="3" height="22" rx="1.5"/>'
                 '<rect x="22" y="10" width="3" height="12" rx="1.5"/></g></svg>\n')
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
