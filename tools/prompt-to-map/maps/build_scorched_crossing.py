#!/usr/bin/env python3
"""Build "Scorched Crossing" — the father-son 4-player map — entirely in code.

Design: docs/superpowers/specs/2026-07-07-scorched-crossing-map-design.md
Skeleton: Golden Oasis (retail) supplies the TOC, SidesList (skirmish factions +
AI scripts), GlobalLighting and WorldInfo; terrain/objects/triggers are generated.

Usage (from repo root):
    python tools/prompt-to-map/maps/build_scorched_crossing.py [--install]
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
MAP_NAME = "Scorched Crossing"

# --- geometry (playable-cell coordinates; P x P playable, BORDER all around) ---
P = 400
BORDER = 40
TOTAL = P + 2 * BORDER
C = P // 2

H_RIVER_BED = 8
H_GROUND = 20
H_SHELF_LOW = 36     # SW / NE shelves (the low diagonal: BL <-> TR)
H_SHELF_HIGH = 52    # NW / SE shelves (the high diagonal: TL <-> BR)
H_BELT = 72          # inner mountain mass
H_RIM = 84           # outer rim plateau (helicopter-landable)

RIVER_BED = (188, 212)       # x range of the river bed
RIVER_BANK = (184, 216)      # x range including sloping banks
ROAD_Y = (190, 210)          # the central west-east road corridor
CORRIDOR = 40                # edge corridors span x 16..40 and P-40..P-16
RIM_TOP = 12                 # rim plateau thickness inside playable
RIM_SLOPE = 16               # rim cliff face ends here
VALLEYS = {                  # (x0, x1, y0, y1) flat corner bases
    "BL": (40, 150, 40, 150),
    "BR": (250, 360, 40, 150),
    "TL": (40, 150, 250, 360),
    "TR": (250, 360, 250, 360),
}
SHELF_X_W = (158, 186)
SHELF_X_E = (214, 242)
SHELF_Y_N = (212, 258)
SHELF_Y_S = (142, 188)
SHELVES = {                  # quadrant -> (rect, height)
    "TL": ((*SHELF_X_W, *SHELF_Y_N), H_SHELF_HIGH),
    "SE": ((*SHELF_X_E, *SHELF_Y_S), H_SHELF_HIGH),
    "BL": ((*SHELF_X_W, *SHELF_Y_S), H_SHELF_LOW),
    "NE": ((*SHELF_X_E, *SHELF_Y_N), H_SHELF_LOW),
}
RAMPS = {                    # (x0, x1, y0, y1, h_from_x0, h_at_x1)
    "TL": (150, 158, 228, 244, H_GROUND, H_SHELF_HIGH),
    "BL": (150, 158, 156, 172, H_GROUND, H_SHELF_LOW),
    "TR": (242, 250, 228, 244, H_SHELF_LOW, H_GROUND),
    "BR": (242, 250, 156, 172, H_SHELF_HIGH, H_GROUND),
}
WATER_Z = 7                  # world units; bed is 5.0, ground is 12.5


def in_rect(px, py, rect):
    x0, x1, y0, y1 = rect
    return x0 <= px < x1 and y0 <= py < y1


def lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def height_at(px, py):
    """Target height (u8 units) for a playable-coord cell; border uses rim."""
    if px < 0 or py < 0 or px >= P or py >= P:
        return H_RIM
    edge = min(px, py, P - 1 - px, P - 1 - py)
    if edge < RIM_TOP:
        return H_RIM
    if edge < RIM_SLOPE:                       # steep rim face (cliff)
        return round(lerp(H_RIM, H_GROUND, (edge - RIM_TOP) / (RIM_SLOPE - RIM_TOP)))
    if RIVER_BANK[0] <= px < RIVER_BANK[1]:    # river canyon (before road/belt)
        if px < RIVER_BED[0]:
            return round(lerp(H_GROUND, H_RIVER_BED,
                              (px - RIVER_BANK[0]) / (RIVER_BED[0] - RIVER_BANK[0])))
        if px >= RIVER_BED[1]:
            return round(lerp(H_RIVER_BED, H_GROUND,
                              (px - RIVER_BED[1] + 1) / (RIVER_BANK[1] - RIVER_BED[1])))
        return H_RIVER_BED
    for rect, h in SHELVES.values():
        if in_rect(px, py, rect):
            return h
    for x0, x1, y0, y1, h0, h1 in RAMPS.values():
        if x0 <= px < x1 and y0 <= py < y1:
            return round(lerp(h0, h1, (px - x0) / (x1 - x0)))
    if ROAD_Y[0] <= py < ROAD_Y[1] and CORRIDOR <= px < P - CORRIDOR:
        return H_GROUND
    if RIM_SLOPE <= px < CORRIDOR or P - CORRIDOR <= px < P - RIM_SLOPE:
        return H_GROUND                        # edge corridors
    for rect in VALLEYS.values():
        if in_rect(px, py, rect):
            return H_GROUND
    if 150 <= px < 250 or 150 <= py < 250:     # inner mountain belts
        return H_BELT
    return H_GROUND


# ------------------------------------------------------------------ textures
# (name, num_tiles) drawn from Golden Oasis's desert palette
PALETTE = [
    ("SandMediumType5c", 16),      # 0 base sand
    ("SandType3wet", 4),           # 1 river bed
    ("GrassMediumType22", 16),     # 2 green banks
    ("SandLargeType4Grassy", 36),  # 3 oasis pockets
    ("DirtMediumType12", 16),      # 4 road / scorched track
    ("DirtMediumType13", 4),       # 5 shelves
    ("CliffMediumType20", 16),     # 6 cliff faces
    ("SandMediumType11", 16),      # 7 mountain tops
    ("RocksType6", 4),             # 8 rim plateau
]


def texture_class_at(px, py, cell_heights):
    """Palette index for a cell (before cliff override)."""
    h = cell_heights
    if max(h) - min(h) > 12:
        return 6                                   # cliff face
    if RIVER_BED[0] - 1 <= px < RIVER_BED[1] + 1:
        return 1
    if RIVER_BANK[0] - 4 <= px < RIVER_BANK[1] + 4 and max(h) <= H_GROUND:
        return 2                                   # green river banks
    edge = min(px, py, P - 1 - px, P - 1 - py) if 0 <= px < P and 0 <= py < P else -1
    if edge < 0 or edge < RIM_TOP:
        return 8                                   # rim / border
    if ROAD_Y[0] + 2 <= py < ROAD_Y[1] - 2 and CORRIDOR <= px < P - CORRIDOR:
        return 4                                   # the road bed
    for rect, _h in SHELVES.values():
        if in_rect(px, py, rect):
            return 5
    if min(h) >= H_BELT:
        return 7                                   # mountain tops
    return 0


def build_blend_tile(heights, oases):
    first = {}
    acc = 0
    classes = []
    for name, num in PALETTE:
        first[name] = acc
        width = int(math.isqrt(num))
        classes.append(TextureClass(acc, num, width, 0, name))
        acc += num

    tile = bytearray(TOTAL * TOTAL * 2)
    cliff_bits = bytearray(TOTAL * ((TOTAL + 7) // 8))
    for y in range(TOTAL):
        for x in range(TOTAL):
            px, py = x - BORDER, y - BORDER
            h = (heights[y * TOTAL + x],
                 heights[y * TOTAL + min(x + 1, TOTAL - 1)],
                 heights[min(y + 1, TOTAL - 1) * TOTAL + x],
                 heights[min(y + 1, TOTAL - 1) * TOTAL + min(x + 1, TOTAL - 1)])
            cls = texture_class_at(px, py, h)
            if cls == 0 and any((px - ox) ** 2 + (py - oy) ** 2 < r * r
                                for ox, oy, r in oases):
                cls = 3
            name, num = PALETTE[cls]
            width = int(math.isqrt(num))
            ndx = first[name] + (x // 2) % width + width * ((y // 2) % width)
            ndx = (ndx << 2) + 2 * (y & 1) + (x & 1)
            struct.pack_into("<h", tile, (y * TOTAL + x) * 2, ndx)
            # engine cliff rule: corner spread > 9.8wu (15.68 height units)
            if (max(h) - min(h)) * 0.625 > 9.8:
                cliff_bits[y * ((TOTAL + 7) // 8) + (x >> 3)] |= 1 << (x & 7)

    zeros = bytes(TOTAL * TOTAL * 2)
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

    def bridge(self, template, x1, y1, x2, y2):
        return [self.make(template, x1, y1, flags=0x10),
                self.make(template, x2, y2, flags=0x20)]


def build_objects(factory, oases):
    rng = random.Random(1959)
    objs = []

    # player starts (waypoints) in the valley hearts, toward their corridor
    start_px = {"1": ("TL", 92, 308), "2": ("TR", 308, 308),
                "3": ("BR", 308, 92), "4": ("BL", 92, 92)}
    wp_props = factory.find_props("*Waypoints/Waypoint")
    for n, (_q, px, py) in start_px.items():
        objs.append(factory.make(
            "*Waypoints/Waypoint", wu(px), wu(py), props=wp_props,
            drop=("waypointPathLabel1", "waypointPathLabel2",
                  "waypointPathLabel3"),
            extra=((f"waypointID", DICT_INT, int(n)),
                   ("waypointName", DICT_ASCIISTRING, f"Player_{n}_Start"))))

    # economy: two supply docks per valley + a contested pile at road junctions
    dock_offsets = ((-34, 18), (34, -18))
    for _q, px, py in start_px.values():
        for dx, dy in dock_offsets:
            objs.append(factory.make("SupplyDock", wu(px + dx), wu(py + dy),
                                     angle=rng.uniform(-3.14, 3.14)))
    for jx in (28, P - 28):
        for jy in (ROAD_Y[0] - 8, ROAD_Y[1] + 8):
            objs.append(factory.make("SupplyPileSmall", wu(jx), wu(jy)))

    # oil derricks guarding the road's river approaches (contested center)
    if factory.find_props("TechOilDerrick"):
        for px, py in ((170, 178), (230, 222), (170, 222), (230, 178)):
            objs.append(factory.make("TechOilDerrick", wu(px), wu(py)))

    # the three bridges: low road bridge + the two stacked diagonals
    objs += factory.bridge("KandaharBridge",
                           wu(RIVER_BANK[0] - 1), wu(C), wu(RIVER_BANK[1]), wu(C))
    objs += factory.bridge("KandaharBridge",          # high: TL <-> BR (SE shelf)
                           wu(184), wu(232), wu(216), wu(168))
    objs += factory.bridge("KandaharBridge",          # low: BL <-> TR (NE shelf)
                           wu(184), wu(168), wu(216), wu(232))

    # roads: center road + both edge corridors, in straight chained segments
    def chain(template, points):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            objs.extend(factory.road_segment(template, wu(x1), wu(y1),
                                             wu(x2), wu(y2)))

    road_pts_w = [(x, C) for x in range(28, RIVER_BANK[0] + 1, 24)] + [(RIVER_BANK[0] - 1, C)]
    road_pts_e = [(RIVER_BANK[1], C)] + [(x, C) for x in range(RIVER_BANK[1] + 12, P - 27, 24)] + [(P - 28, C)]
    chain("DirtRoad", road_pts_w)
    chain("DirtRoad", road_pts_e)
    chain("DirtRoad", [(28, y) for y in range(32, P - 31, 32)])
    chain("DirtRoad", [(P - 28, y) for y in range(32, P - 31, 32)])

    # scenery: palm oases, green banks, rocks on shelves and rim
    palms = ["TreePalm1short", "TreePalm03", "TreePalm04", "TreePalm2",
             "TreePalm1", "TreePalm2short"]
    for ox, oy, r in oases:
        for _ in range(6):
            a, d = rng.uniform(0, 6.283), rng.uniform(2, r - 2)
            objs.append(factory.make(rng.choice(palms),
                                     wu(ox + d * math.cos(a)),
                                     wu(oy + d * math.sin(a)),
                                     angle=rng.uniform(-3.14, 3.14)))
    for py in range(40, P - 39, 26):                 # palms along the banks
        if abs(py - C) > 24:
            objs.append(factory.make(rng.choice(palms),
                                     wu(RIVER_BANK[0] - 3 - rng.uniform(0, 3)),
                                     wu(py), angle=rng.uniform(-3.14, 3.14)))
            objs.append(factory.make(rng.choice(palms),
                                     wu(RIVER_BANK[1] + 3 + rng.uniform(0, 3)),
                                     wu(py + 13), angle=rng.uniform(-3.14, 3.14)))
    for rect, _h in SHELVES.values():                # rocks on the shelves
        x0, x1, y0, y1 = rect
        for _ in range(3):
            objs.append(factory.make("Rocks1Brown",
                                     wu(rng.uniform(x0 + 3, x1 - 3)),
                                     wu(rng.uniform(y0 + 3, y1 - 3)),
                                     angle=rng.uniform(-3.14, 3.14)))

    # ambience
    for _q, px, py in start_px.values():
        objs.append(factory.make("Amb_DesertNatureWindThinLoop", wu(px), wu(py)))
    for py in (70, C, P - 70):
        objs.append(factory.make("Amb_WaterRiverLoop", wu(C), wu(py)))
    return objs


def build_triggers():
    def rect_points(x0, x1, y0, y1, z=0):
        return [(int(wu(x0)), int(wu(y0)), z), (int(wu(x1)), int(wu(y0)), z),
                (int(wu(x1)), int(wu(y1)), z), (int(wu(x0)), int(wu(y1)), z)]

    triggers = [Trigger("River", "", 1, 1, 0, 0,
                        rect_points(RIVER_BANK[0], RIVER_BANK[1], 2, P - 2,
                                    WATER_Z)),
                Trigger("CombatZone", "", 2, 0, 0, 0,
                        rect_points(120, 280, 120, 280))]
    tid = 3
    centers = {"1": (92, 308), "2": (308, 308), "3": (308, 92), "4": (92, 92)}
    for n, (px, py) in centers.items():
        triggers.append(Trigger(f"InnerPerimeter{n}", "", tid, 0, 0, 0,
                                rect_points(px - 45, px + 45, py - 45, py + 45)))
        triggers.append(Trigger(f"OuterPerimeter{n}", "", tid + 1, 0, 0, 0,
                                rect_points(px - 68, px + 68, py - 68, py + 68)))
        tid += 2
    return PolygonTriggers(version=4, triggers=triggers)


def main():
    donor = MapFile.from_bytes((FIXTURES / "Golden Oasis.map").read_bytes())
    donor_objs = [o for o in donor.get("ObjectsList").items
                  if isinstance(o, MapObject)]
    factory = ObjectFactory(donor_objs)

    heights = bytearray(TOTAL * TOTAL)
    for y in range(TOTAL):
        for x in range(TOTAL):
            heights[y * TOTAL + x] = height_at(x - BORDER, y - BORDER)

    oases = [(60, 276, 12), (340, 340, 12), (340, 124, 12), (60, 60, 12),
             (124, 340, 10), (276, 60, 10)]

    heightmap = HeightMapData(version=4, width=TOTAL, height=TOTAL,
                              border_size=BORDER, boundaries=[(P, P)],
                              elevations=bytes(heights))
    blend = build_blend_tile(heights, oases)
    objects = ObjectsList(version=3, items=build_objects(factory, oases))
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
