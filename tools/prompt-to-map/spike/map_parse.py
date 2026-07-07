#!/usr/bin/env python3
"""SPIKE (throwaway feasibility proof, not the real toolkit).

Parse a real .map into a JSON summary (terrain heightmap + object coords +
player starts) so we can RENDER it and visually prove the read pipeline works.

Follows the layouts in docs/superpowers/specs/map-format-reference.md:
  HeightMapData v4 : width,height,border,numBoundaries,(x,y)*,dataSize,heights[u8]
  Object v3        : x,y,z,angle(f32) flags(i32) name(AsciiStr) Dict
  Dict             : u16 pairCount, then (keyAndType i32 = TOCid<<8|type) + value
"""
import json
import struct
import sys

sys.path.insert(0, sys.path[0])
from refpack import decompress_map

CELL = 10.0  # world units per heightmap cell (MAP_XY_FACTOR)


class Reader:
    def __init__(self, data, pos=0):
        self.d = data; self.p = pos
    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]; self.p += 4; return v
    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]; self.p += 4; return v
    def u16(self):
        v = struct.unpack_from("<H", self.d, self.p)[0]; self.p += 2; return v
    def f32(self):
        v = struct.unpack_from("<f", self.d, self.p)[0]; self.p += 4; return v
    def u8(self):
        v = self.d[self.p]; self.p += 1; return v
    def astr(self):
        n = self.u16(); s = self.d[self.p:self.p + n].decode("latin-1"); self.p += n; return s
    def ustr(self):
        n = self.u16(); s = self.d[self.p:self.p + n * 2].decode("utf-16-le"); self.p += n * 2; return s


def parse_toc(data):
    assert data[:4] == b"CkMp"
    r = Reader(data, 4)
    count = r.i32()
    id_to_name = {}
    for _ in range(count):
        nlen = r.u8()
        name = data[r.p:r.p + nlen].decode("latin-1"); r.p += nlen
        cid = r.u32()
        id_to_name[cid] = name
    return id_to_name, r.p


def read_dict(r, id_to_name):
    out = {}
    n = r.u16()
    for _ in range(n):
        kt = r.u32()
        key = id_to_name.get(kt >> 8, f"#{kt>>8}")
        typ = kt & 0xFF
        if typ == 0:   v = bool(r.u8())
        elif typ == 1: v = r.i32()
        elif typ == 2: v = r.f32()
        elif typ == 3: v = r.astr()
        elif typ == 4: v = r.ustr()
        else: raise ValueError(f"bad dict type {typ}")
        out[key] = v
    return out


def classify(name, waypoint_name):
    n = name.lower()
    if waypoint_name and waypoint_name.lower().startswith("player_") and waypoint_name.lower().endswith("_start"):
        return "start"
    if any(k in n for k in ("supplydock", "supplywarehouse", "oilderrick", "supplycenter")):
        return "resource"
    if "tech" in n:
        return "tech"
    if waypoint_name is not None or "waypoint" in n:
        return "waypoint"
    if any(k in n for k in ("tree", "bush", "foliage", "rock", "shrub", "palm", "grass")):
        return "scenery"
    if "civilian" in n or "prop" in n:
        return "civilian"
    return "unit"


def main():
    raw = decompress_map(open(sys.argv[1], "rb").read())
    id_to_name, pos = parse_toc(raw)
    name_to_id = {v: k for k, v in id_to_name.items()}
    r = Reader(raw, pos)
    result = {"width": 0, "height": 0, "border": 0, "cell": CELL,
              "heights": [], "hw": 0, "hh": 0, "objects": [], "counts": {}}

    end = len(raw)
    while r.p + 10 <= end:
        cid = r.u32(); ver = r.u16(); size = r.i32()
        name = id_to_name.get(cid)
        body = r.p
        if name is None or size < 0 or body + size > end:
            break
        if name == "HeightMapData":
            hr = Reader(raw, body)
            w = hr.i32(); h = hr.i32()
            border = hr.i32() if ver >= 3 else 0
            if ver >= 4:
                nb = hr.i32()
                hr.p += nb * 8  # skip boundary (x,y) pairs
            dsize = hr.i32()
            heights = raw[hr.p:hr.p + dsize]
            result.update(width=w, height=h, border=border)
            # downsample so the render array stays small (ceil to ~150 max dim)
            step = max(1, -(-max(w, h) // 150))
            hw = (w + step - 1) // step; hh = (h + step - 1) // step
            grid = []
            for yy in range(0, h, step):
                for xx in range(0, w, step):
                    grid.append(heights[yy * w + xx])
            result["heights"] = grid; result["hw"] = hw; result["hh"] = hh
            result["step"] = step
        elif name == "ObjectsList":
            oe = body + size
            orr = Reader(raw, body)
            while orr.p + 10 <= oe:
                ocid = orr.u32(); over = orr.u16(); osize = orr.i32()
                oname = id_to_name.get(ocid)
                obody = orr.p
                if oname != "Object" or obody + osize > oe:
                    break
                x = orr.f32(); y = orr.f32(); z = orr.f32(); angle = orr.f32()
                flags = orr.i32(); tmpl = orr.astr()
                d = read_dict(orr, id_to_name) if over >= 2 else {}
                wpn = d.get("waypointName")
                kind = classify(tmpl, wpn)
                result["objects"].append({
                    "x": round(x, 1), "y": round(y, 1), "a": round(angle, 3),
                    "n": tmpl, "k": kind, "w": wpn})
                result["counts"][kind] = result["counts"].get(kind, 0) + 1
                orr.p = obody + osize
        r.p = body + size

    result["name"] = sys.argv[1].replace("\\", "/").split("/")[-1][:-4]
    json.dump(result, open(sys.argv[2], "w"))
    o = result["objects"]
    starts = [b for b in o if b["k"] == "start"]
    print(f"{result['name']}: {result['width']}x{result['height']} grid "
          f"(border {result['border']}), {len(o)} objects, {len(starts)} player starts")
    print("  kinds:", result["counts"])
    print("  starts:", sorted(b["w"] for b in starts))


if __name__ == "__main__":
    main()
