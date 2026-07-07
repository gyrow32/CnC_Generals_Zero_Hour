#!/usr/bin/env python3
"""SPIKE: render a real .map to a PNG image (terrain + objects + player starts),
so we can view a decoded map directly. Full-resolution heightmap."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, sys.path[0])
from refpack import decompress_map
from map_parse import Reader, parse_toc, read_dict, classify, CELL

KIND_COLOR = {
    "resource": (255, 207, 77), "unit": (159, 182, 198), "scenery": (78, 138, 88),
    "civilian": (168, 146, 224), "tech": (217, 138, 77), "waypoint": (86, 104, 118),
}
FACTION = [(229, 72, 77), (76, 141, 255), (95, 208, 106), (244, 193, 75),
           (201, 107, 216), (255, 143, 77), (67, 199, 199), (208, 213, 218)]
RAMP_T = [0, .12, .34, .56, .74, .88, 1]
RAMP_C = np.array([[18, 34, 44], [20, 52, 58], [29, 58, 46], [63, 90, 58],
                   [122, 125, 69], [184, 154, 85], [232, 207, 143]], float)


def parse(path):
    raw = decompress_map(open(path, "rb").read())
    id_to_name, pos = parse_toc(raw)
    r = Reader(raw, pos); end = len(raw)
    W = H = border = 0; heights = None; objs = []
    while r.p + 10 <= end:
        cid = r.u32(); ver = r.u16(); size = r.i32()
        name = id_to_name.get(cid); body = r.p
        if name is None or size < 0 or body + size > end:
            break
        if name == "HeightMapData":
            hr = Reader(raw, body); W = hr.i32(); H = hr.i32()
            border = hr.i32() if ver >= 3 else 0
            if ver >= 4:
                nb = hr.i32(); hr.p += nb * 8
            ds = hr.i32(); heights = np.frombuffer(raw[hr.p:hr.p + ds], np.uint8).reshape(H, W)
        elif name == "ObjectsList":
            oe = body + size; o = Reader(raw, body)
            while o.p + 10 <= oe:
                ocid = o.u32(); over = o.u16(); osz = o.i32(); on = id_to_name.get(ocid); ob = o.p
                if on != "Object" or ob + osz > oe:
                    break
                x = o.f32(); y = o.f32(); o.f32(); o.f32(); o.i32(); tmpl = o.astr()
                d = read_dict(o, id_to_name) if over >= 2 else {}
                wpn = d.get("waypointName")
                objs.append((x, y, tmpl, classify(tmpl, wpn), wpn))
                o.p = ob + osz
        r.p = body + size
    return W, H, border, heights, objs


def render(path, out, scale=3):
    W, H, border, heights, objs = parse(path)
    t = (heights.astype(float) - heights.min()) / (max(1, int(np.ptp(heights))))
    rgb = np.stack([np.interp(t, RAMP_T, RAMP_C[:, c]) for c in range(3)], -1)
    # hillshade from west-neighbour slope
    sh = np.zeros_like(t); sh[:, 1:] = (heights[:, 1:].astype(float) - heights[:, :-1]) * 3
    rgb += np.clip(sh, -18, 22)[..., None]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    img = img.resize((W * scale, H * scale), Image.BILINEAR)
    d = ImageDraw.Draw(img, "RGBA")
    sx = W * scale / (W * CELL)  # world -> pixel

    def px(x, y):
        return (x * sx, y * sx)
    # tactical grid
    for i in range(1, 16):
        gx = W * scale * i / 16; d.line([(gx, 0), (gx, H * scale)], (120, 150, 165, 22))
        gy = H * scale * i / 16; d.line([(0, gy), (W * scale, gy)], (120, 150, 165, 22))
    # playable border
    b0 = px(border * CELL, border * CELL); b1 = px((W - border) * CELL, (H - border) * CELL)
    for k in range(2):
        d.rectangle([b0[0] - k, b0[1] - k, b1[0] + k, b1[1] + k], outline=(255, 180, 58, 150))
    # objects
    starts = []
    for x, y, tmpl, kind, wpn in objs:
        if kind == "start":
            starts.append((x, y, wpn)); continue
        if kind == "waypoint":
            continue
        cx, cy = px(x, y); r = 3.2 if kind == "resource" else 2.2
        c = KIND_COLOR[kind]; a = 190 if kind == "scenery" else 235
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(c[0], c[1], c[2], a))
    # player starts
    try:
        font = ImageFont.truetype("arialbd.ttf", 13 * scale // 3)
    except Exception:
        font = ImageFont.load_default()
    for x, y, wpn in starts:
        idx = (int("".join(ch for ch in (wpn or "1") if ch.isdigit()) or 1)) - 1
        col = FACTION[idx % len(FACTION)]; cx, cy = px(x, y); R = 9 * scale / 3
        d.ellipse([cx - R * 1.4, cy - R * 1.4, cx + R * 1.4, cy + R * 1.4], fill=(col[0], col[1], col[2], 55))
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=col, width=max(2, scale))
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=col)
        d.text((cx, cy - R - 10), str(idx + 1), fill=(255, 255, 255, 255), font=font, anchor="mm")
    img.save(out)
    print(f"{out}: {img.size[0]}x{img.size[1]}  ({W}x{H} grid, {len(objs)} objs, {len(starts)} starts)")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
