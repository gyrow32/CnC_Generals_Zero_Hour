#!/usr/bin/env python3
"""Build "Panorama Pass" — a widescreen 1v1 map made together with Mike.

Canvas: 420 x 250 playable (~1.7:1, widescreen). West vs East bases separated
by a central N-S ridge cut by three routes: north pass, center canyon (road),
south pass. Initial version — iterate in WorldBuilder with Mike.

Skeleton: Golden Oasis (retail) supplies TOC, SidesList, lighting, WorldInfo.

Usage (from repo root):
    python tools/prompt-to-map/maps/build_panorama_pass.py [--install]
"""
import math
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cncmap import (DICT_ASCIISTRING, DICT_INT, DictEntry, HeightMapData,
                    BlendTileData, MapFile, MapObject, ObjectsList,
                    PolygonTriggers, TextureClass, Trigger, WaypointsList)

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tools/prompt-to-map/tests/fixtures"
OUT_DIR = Path(__file__).resolve().parent / "out"
GAME_MAPS = Path(r"C:\Users\gyrow\OneDrive\Documents"
                 r"\Command and Conquer Generals Zero Hour Data\Maps")
MAP_NAME = "Panorama Pass"

# --- geometry (playable-cell coordinates; PX x PY playable, BORDER around) ---
PX, PY = 420, 250            # widescreen: ~1.7:1
BORDER = 40
TX, TY = PX + 2 * BORDER, PY + 2 * BORDER
CX, CY = PX // 2, PY // 2

H_GROUND = 20
H_RIDGE = 48                 # the central dividing ridge
H_RIM = 60                   # thin rim so the map edge reads as terrain

RIDGE_X = (CX - 26, CX + 26)         # x range of the ridge mass
CANYON_Y = (CY - 12, CY + 12)        # center canyon (road route)
PASS_N = (int(PY * 0.78) - 13, int(PY * 0.78) + 13)   # north pass
PASS_S = (int(PY * 0.22) - 13, int(PY * 0.22) + 13)   # south pass
RIM_TOP = 8                  # rim plateau thickness inside playable
RIM_SLOPE = 14               # rim face ends here


def lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def in_route(py):
    return (CANYON_Y[0] <= py < CANYON_Y[1]
            or PASS_N[0] <= py < PASS_N[1]
            or PASS_S[0] <= py < PASS_S[1])


def height_at(px, py):
    """Target height (u8 units) for a playable-coord cell; border uses rim."""
    if px < 0 or py < 0 or px >= PX or py >= PY:
        return H_RIM
    edge = min(px, py, PX - 1 - px, PY - 1 - py)
    if edge < RIM_TOP:
        return H_RIM
    if edge < RIM_SLOPE:                       # steep rim face
        return round(lerp(H_RIM, H_GROUND,
                          (edge - RIM_TOP) / (RIM_SLOPE - RIM_TOP)))
    if RIDGE_X[0] <= px < RIDGE_X[1] and not in_route(py):
        # ridge shoulders taper over 6 cells so tops aren't knife-edged
        d = min(px - RIDGE_X[0], RIDGE_X[1] - 1 - px)
        if d < 6:
            return round(lerp(H_GROUND, H_RIDGE, (d + 1) / 6))
        return H_RIDGE
    return H_GROUND


# ------------------------------------------------------------------ textures
# (name, num_tiles) drawn from Golden Oasis's desert palette
PALETTE = [
    ("SandMediumType5c", 16),      # 0 base sand
    ("GrassMediumType22", 16),     # 1 green base pockets
    ("DirtMediumType12", 16),      # 2 road / canyon floor
    ("CliffMediumType20", 16),     # 3 cliff faces
    ("SandMediumType11", 16),      # 4 ridge tops
    ("RocksType6", 4),             # 5 rim plateau
]

BASE_GREENS = [(58, None), (PX - 58, None)]   # filled in main() with CY


def texture_class_at(px, py, cell_heights, greens):
    h = cell_heights
    if max(h) - min(h) > 12:
        return 3                                   # cliff face
    edge = (min(px, py, PX - 1 - px, PY - 1 - py)
            if 0 <= px < PX and 0 <= py < PY else -1)
    if edge < 0 or edge < RIM_TOP:
        return 5                                   # rim / border
    if CANYON_Y[0] + 2 <= py < CANYON_Y[1] - 2 and RIM_SLOPE <= px < PX - RIM_SLOPE:
        return 2                                   # the road bed
    if min(h) >= H_RIDGE:
        return 4                                   # ridge tops
    if any((px - gx) ** 2 + (py - gy) ** 2 < r * r for gx, gy, r in greens):
        return 1                                   # green base pockets
    return 0


def build_blend_tile(heights, greens):
    first = {}
    acc = 0
    classes = []
    for name, num in PALETTE:
        first[name] = acc
        width = int(math.isqrt(num))
        classes.append(TextureClass(acc, num, width, 0, name))
        acc += num

    tile = bytearray(TX * TY * 2)
    row_bytes = (TX + 7) // 8
    cliff_bits = bytearray(TY * row_bytes)
    for y in range(TY):
        for x in range(TX):
            px, py = x - BORDER, y - BORDER
            h = (heights[y * TX + x],
                 heights[y * TX + min(x + 1, TX - 1)],
                 heights[min(y + 1, TY - 1) * TX + x],
                 heights[min(y + 1, TY - 1) * TX + min(x + 1, TX - 1)])
            cls = texture_class_at(px, py, h, greens)
            name, num = PALETTE[cls]
            width = int(math.isqrt(num))
            ndx = first[name] + (x // 2) % width + width * ((y // 2) % width)
            ndx = (ndx << 2) + 2 * (y & 1) + (x & 1)
            struct.pack_into("<h", tile, (y * TX + x) * 2, ndx)
            # engine cliff rule: corner spread > 9.8wu (15.68 height units)
            if (max(h) - min(h)) * 0.625 > 9.8:
                cliff_bits[y * row_bytes + (x >> 3)] |= 1 << (x & 7)

    zeros = bytes(TX * TY * 2)
    return BlendTileData(
        version=8, tile_ndxes=bytes(tile), blend_tile_ndxes=zeros,
        extra_blend_tile_ndxes=zeros, cliff_info_ndxes=zeros,
        cell_cliff_state=bytes(cliff_bits), num_bitmap_tiles=acc,
        num_blended_tiles=1, num_cliff_info=1, texture_classes=classes,
        num_edge_tiles=0, edge_texture_classes=[], blend_entries=[],
        cliff_infos=[])


# ------------------------------------------------------------------- objects
def wu(p):
    """Playable cell coord -> world units."""
    return (p + BORDER) * 10.0


class ObjectFactory:
    """Stamps new objects using property blocks copied from real retail maps."""

    def __init__(self, donor_objects):
        self.templates = {}
        for o in donor_objects:
            self.templates.setdefault((o.template_name, o.flags & 0xF0), o)
            self.templates.setdefault((o.template_name, None), o)
        self.serial = 100

    def find_props(self, template, flag_group=None):
        donor = (self.templates.get((template, flag_group))
                 or self.templates.get((template, None)))
        return list(donor.props) if donor else None

    def make(self, template, x, y, angle=0.0, flags=0, props=None,
             extra=(), drop=()):
        base = props if props is not None else self.find_props(template)
        if base is None:                      # generic scenery boilerplate
            base = self.find_props("TreePalm03") or []
        self.serial += 1
        out = []
        for e in base:
            if e.key in drop or e.key in {k for k, _, _ in extra}:
                continue
            if e.key == "uniqueID":
                e = DictEntry("uniqueID", DICT_ASCIISTRING,
                              f"{template} {self.serial}")
            out.append(e)
        out += [DictEntry(k, t, v) for k, t, v in extra]
        return MapObject(version=3, x=float(x), y=float(y), z=0.0,
                         angle=float(angle), flags=flags,
                         template_name=template, props=out)

    def road_segment(self, template, x1, y1, x2, y2):
        return [self.make(template, x1, y1, flags=0x02),
                self.make(template, x2, y2, flags=0x04)]


def build_objects(factory, greens):
    rng = random.Random(2470)
    objs = []

    # player starts: west vs east, on the center line
    starts = {"1": (58, CY), "2": (PX - 58, CY)}
    wp_props = factory.find_props("*Waypoints/Waypoint")
    for n, (px, py) in starts.items():
        objs.append(factory.make(
            "*Waypoints/Waypoint", wu(px), wu(py), props=wp_props,
            drop=("waypointPathLabel1", "waypointPathLabel2",
                  "waypointPathLabel3"),
            extra=(("waypointID", DICT_INT, int(n)),
                   ("waypointName", DICT_ASCIISTRING, f"Player_{n}_Start"))))

    # economy: two supply docks per base + expansions near each pass mouth
    for px, py in starts.values():
        for dx, dy in ((0, 42), (0, -42)):
            objs.append(factory.make("SupplyDock", wu(px + dx), wu(py + dy),
                                     angle=rng.uniform(-3.14, 3.14)))
    for px in (RIDGE_X[0] - 34, RIDGE_X[1] + 34):     # pass-mouth expansions
        for py in (sum(PASS_N) // 2, sum(PASS_S) // 2):
            objs.append(factory.make("SupplyPileSmall", wu(px), wu(py)))

    # oil derricks: one in each pass + two in the center canyon (contested)
    if factory.find_props("TechOilDerrick"):
        for px, py in ((CX, sum(PASS_N) // 2), (CX, sum(PASS_S) // 2),
                       (CX - 40, CY), (CX + 40, CY)):
            objs.append(factory.make("TechOilDerrick", wu(px), wu(py)))

    # road: east-west through the center canyon, base to base
    def chain(template, points):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            objs.extend(factory.road_segment(template, wu(x1), wu(y1),
                                             wu(x2), wu(y2)))

    chain("DirtRoad", [(x, CY) for x in range(26, PX - 25, 24)] + [(PX - 26, CY)])

    # scenery: palms around the green base pockets, rocks on the ridge tops
    palms = ["TreePalm1short", "TreePalm03", "TreePalm04", "TreePalm2",
             "TreePalm1", "TreePalm2short"]
    for gx, gy, r in greens:
        for _ in range(7):
            a, d = rng.uniform(0, 6.283), rng.uniform(r * 0.5, r + 6)
            objs.append(factory.make(rng.choice(palms),
                                     wu(gx + d * math.cos(a)),
                                     wu(gy + d * math.sin(a)),
                                     angle=rng.uniform(-3.14, 3.14)))
    for _ in range(10):
        py = rng.choice(list(range(RIM_SLOPE + 4, PASS_S[0] - 4))
                        + list(range(PASS_S[1] + 4, CANYON_Y[0] - 4))
                        + list(range(CANYON_Y[1] + 4, PASS_N[0] - 4))
                        + list(range(PASS_N[1] + 4, PY - RIM_SLOPE - 4)))
        objs.append(factory.make("Rocks1Brown",
                                 wu(rng.uniform(RIDGE_X[0] + 8, RIDGE_X[1] - 8)),
                                 wu(py), angle=rng.uniform(-3.14, 3.14)))

    # ambience
    for px, py in starts.values():
        objs.append(factory.make("Amb_DesertNatureWindThinLoop", wu(px), wu(py)))
    return objs


def build_triggers():
    def rect_points(x0, x1, y0, y1, z=0):
        return [(int(wu(x0)), int(wu(y0)), z), (int(wu(x1)), int(wu(y0)), z),
                (int(wu(x1)), int(wu(y1)), z), (int(wu(x0)), int(wu(y1)), z)]

    triggers = [Trigger("CombatZone", "", 1, 0, 0, 0,
                        rect_points(RIDGE_X[0] - 40, RIDGE_X[1] + 40,
                                    20, PY - 20))]
    tid = 2
    starts = {"1": (58, CY), "2": (PX - 58, CY)}
    for n, (px, py) in starts.items():
        triggers.append(Trigger(f"InnerPerimeter{n}", "", tid, 0, 0, 0,
                                rect_points(px - 45, px + 45, py - 60, py + 60)))
        triggers.append(Trigger(f"OuterPerimeter{n}", "", tid + 1, 0, 0, 0,
                                rect_points(px - 60, px + 60, py - 85, py + 85)))
        tid += 2
    return PolygonTriggers(version=4, triggers=triggers)


def main():
    donor = MapFile.from_bytes((FIXTURES / "Golden Oasis.map").read_bytes())
    donor_objs = [o for o in donor.get("ObjectsList").items
                  if isinstance(o, MapObject)]
    factory = ObjectFactory(donor_objs)

    heights = bytearray(TX * TY)
    for y in range(TY):
        for x in range(TX):
            heights[y * TX + x] = height_at(x - BORDER, y - BORDER)

    greens = [(58, CY, 26), (PX - 58, CY, 26)]

    heightmap = HeightMapData(version=4, width=TX, height=TY,
                              border_size=BORDER, boundaries=[(PX, PY)],
                              elevations=bytes(heights))
    blend = build_blend_tile(heights, greens)
    objects = ObjectsList(version=3, items=build_objects(factory, greens))
    triggers = build_triggers()
    waypoints = WaypointsList(version=1, links=[])

    # graft onto the Golden Oasis skeleton (keeps TOC, sides, scripts, lighting)
    world = donor.get("WorldInfo")
    world.props = [DictEntry(e.key, e.dtype, "" if e.key == "mapName" else e.value)
                   for e in world.props]
    replacements = {"HeightMapData": heightmap, "BlendTileData": blend,
                    "ObjectsList": objects, "PolygonTriggers": triggers,
                    "WaypointsList": waypoints}
    donor.chunks = [replacements.get(c.label, c) for c in donor.chunks]

    data = donor.to_bytes()
    OUT_DIR.mkdir(exist_ok=True)
    out_map = OUT_DIR / f"{MAP_NAME}.map"
    out_map.write_bytes(data)
    reparsed = MapFile.parse(data)          # sanity: our own reader accepts it
    n_objs = len(reparsed.get("ObjectsList").items)
    print(f"built {out_map.name}: {len(data):,} bytes, {n_objs} objects, "
          f"{len(reparsed.get('PolygonTriggers').triggers)} triggers")

    if "--install" in sys.argv:
        dest = GAME_MAPS / MAP_NAME
        dest.mkdir(exist_ok=True)
        (dest / f"{MAP_NAME}.map").write_bytes(data)
        print(f"installed -> {dest}")


if __name__ == "__main__":
    main()
