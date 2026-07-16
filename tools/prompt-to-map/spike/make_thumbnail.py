#!/usr/bin/env python3
"""Render a .map to its in-game 128x128 minimap thumbnail (.tga).

Clean render for the map-select screen: terrain + hillshade + object dots and
plain faction-colored start dots -- no tactical grid, no boundary box, no
numbered rings (those stay in render_png.py, the debug view).

The .map grid stores +y = north but render rows run top-down (south at top);
writing rows in render order into a bottom-left-origin TGA flips it back, so
the thumbnail comes out north-up in game. Format matches retail: type 2
uncompressed 32-bit BGRA + TRUEVISION-XFILE footer.

Usage: python make_thumbnail.py <map path> <out.tga> [size]
"""
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, sys.path[0])
from render_png import parse, KIND_COLOR, FACTION, RAMP_T, RAMP_C
from map_parse import CELL


def render_clean(path, scale=3):
    W, H, border, heights, objs = parse(path)
    t = (heights.astype(float) - heights.min()) / (max(1, int(np.ptp(heights))))
    rgb = np.stack([np.interp(t, RAMP_T, RAMP_C[:, c]) for c in range(3)], -1)
    sh = np.zeros_like(t)
    sh[:, 1:] = (heights[:, 1:].astype(float) - heights[:, :-1]) * 3
    rgb += np.clip(sh, -18, 22)[..., None]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    img = img.resize((W * scale, H * scale), Image.BILINEAR)
    d = ImageDraw.Draw(img, "RGBA")
    sx = W * scale / (W * CELL)

    for x, y, tmpl, kind, wpn in objs:
        if kind == "waypoint":
            continue
        cx, cy = x * sx, y * sx
        if kind == "start":
            idx = (int("".join(ch for ch in (wpn or "1") if ch.isdigit()) or 1)) - 1
            col = FACTION[idx % len(FACTION)]
            R = 6 * scale / 3
            d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=col)
            continue
        r = 3.2 if kind == "resource" else 2.2
        c = KIND_COLOR[kind]
        a = 190 if kind == "scenery" else 235
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(c[0], c[1], c[2], a))

    # crop to the playable area (what the game's minimap shows)
    b = border * scale
    return img.crop((b, b, W * scale - b, H * scale - b))


def write_tga(img, out_path, size=128):
    img = img.resize((size, size), Image.LANCZOS).convert("RGB")
    px = np.asarray(img, np.uint8)
    bgra = np.dstack([px[..., 2], px[..., 1], px[..., 0],
                      np.full(px.shape[:2], 255, np.uint8)])
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0,
                         size, size, 32, 0)          # descriptor 0 = bottom-left
    footer = bytes(8) + b"TRUEVISION-XFILE." + b"\x00"
    with open(out_path, "wb") as f:
        f.write(header + bgra.tobytes() + footer)
    print(f"{out_path}: {size}x{size} TGA ({img.size[0]}px source crop)")


if __name__ == "__main__":
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 128
    write_tga(render_clean(sys.argv[1]), sys.argv[2], size)
