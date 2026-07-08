#!/usr/bin/env python3
"""Build "Scorched Crossing" — the father-son 4-player map — entirely in code.

v2 design (Mike's red-line sketch, 2026-07-07):
Four elevated hill-arms flank the central road — the HIGH ROADS. Routes ramp up
from the edge corridors, run the arm tops, and cross the river in a stacked
diagonal X right at the center (NW<->SE high bridge over SW<->NE low bridge).
The river runs border-to-border and drains off both map edges. Terrain is
organically sculpted (noise + smoothing) instead of angular plateaus.

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
H_BELT = 72          # the elevated hill-arms (the high roads)
H_RIM = 84           # outer rim plateau
H_PAD_HIGH = 80      # NW / SE bridge pads (upper deck of the X)
H_PAD_LOW = 64       # SW / NE bridge pads (lower deck, passes underneath)

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
ARM_Y = ((150, 190), (210, 250))     # the two arm bands flanking the road
RAMP_W = (44, 84)                    # west arms ramp up here (20 -> 72)
RAMP_E = (316, 356)                  # east arms ramp down here (72 -> 20)
PADS = {                             # bridge feet: (x, y, height)
    "NW": (180, 212, H_PAD_HIGH), "SE": (220, 188, H_PAD_HIGH),
    "SW": (180, 188, H_PAD_LOW),  "NE": (220, 212, H_PAD_LOW),
}
WATER_Z = 7                  # world units; bed is 5.0, ground is 12.5


def in_rect(px, py, rect):
    x0, x1, y0, y1 = rect
    return x0 <= px < x1 and y0 <= py < y1


def lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def in_arm_band(py):
    return any(y0 <= py < y1 for y0, y1 in ARM_Y)


def height_at(px, py):
    """Structural height (u8) for a cell; the river cuts through the border."""
    if RIVER_BANK[0] <= px < RIVER_BANK[1]:    # river canyon, border-to-border
        if px < RIVER_BED[0]:
            return round(lerp(H_GROUND, H_RIVER_BED,
                              (px - RIVER_BANK[0]) / (RIVER_BED[0] - RIVER_BANK[0])))
        if px >= RIVER_BED[1]:
            return round(lerp(H_RIVER_BED, H_GROUND,
                              (px - RIVER_BED[1] + 1) / (RIVER_BANK[1] - RIVER_BED[1])))
        return H_RIVER_BED
    if px < 0 or py < 0 or px >= P or py >= P:
        return H_RIM
    edge = min(px, py, P - 1 - px, P - 1 - py)
    if edge < RIM_TOP:
        return H_RIM
    if edge < RIM_SLOPE:                       # steep rim face (cliff)
        return round(lerp(H_RIM, H_GROUND, (edge - RIM_TOP) / (RIM_SLOPE - RIM_TOP)))
    for x, y, h in PADS.values():              # bridge pads, blended mounds
        d = math.hypot(px - x, py - y)
        if d < 5:
            return h
        if d < 14 and in_arm_band(py):
            return round(lerp(h, H_BELT, (d - 5) / 9))
    if ROAD_Y[0] <= py < ROAD_Y[1] and CORRIDOR <= px < P - CORRIDOR:
        return H_GROUND                        # the central road corridor
    if RIM_SLOPE <= px < CORRIDOR or P - CORRIDOR <= px < P - RIM_SLOPE:
        return H_GROUND                        # edge corridors
    if in_arm_band(py):                        # ramps up onto the arms
        if RAMP_W[0] <= px < RAMP_W[1]:
            return round(lerp(H_GROUND, H_BELT,
                              (px - RAMP_W[0]) / (RAMP_W[1] - RAMP_W[0])))
        if RAMP_E[0] <= px < RAMP_E[1]:
            return round(lerp(H_BELT, H_GROUND,
                              (px - RAMP_E[0]) / (RAMP_E[1] - RAMP_E[0])))
    for rect in VALLEYS.values():
        if in_rect(px, py, rect):
            return H_GROUND
    if 150 <= px < 250 or 150 <= py < 250:     # the hill mass (arms + core)
        return H_BELT
    return H_GROUND


# --------------------------------------------------------------- organic pass
START_PX = {"1": (92, 308), "2": (308, 308), "3": (308, 92), "4": (92, 92)}
DOCK_OFFSETS = ((-34, 18), (34, -18))
PILE_SPOTS = [(jx, jy) for jx in (28, P - 28)
              for jy in (ROAD_Y[0] - 8, ROAD_Y[1] + 8)]


def freedom_at(px, py):
    """1.0 = free to sculpt organically, 0.0 = must stay exact."""
    if RIVER_BED[0] - 2 <= px < RIVER_BED[1] + 2:
        return 0.0                                   # keep the bed watertight
    for x, y, _h in PADS.values():
        if math.hypot(px - x, py - y) < 10:
            return 0.0                               # bridge feet stay flat
    if ROAD_Y[0] + 2 <= py < ROAD_Y[1] - 2 and CORRIDOR <= px < P - CORRIDOR:
        return 0.0                                   # road stays drivable
    for _q, (sx, sy) in START_PX.items():
        if math.hypot(px - sx, py - sy) < 26:
            return 0.0                               # bases stay buildable
        for dx, dy in DOCK_OFFSETS:
            if math.hypot(px - (sx + dx), py - (sy + dy)) < 8:
                return 0.0
    for jx, jy in PILE_SPOTS:
        if math.hypot(px - jx, py - jy) < 6:
            return 0.0
    if in_arm_band(py) and (RAMP_W[0] <= px < RAMP_W[1]
                            or RAMP_E[0] <= px < RAMP_E[1]):
        return 0.3                                   # ramps: only gentle waves
    edge = min(px, py, P - 1 - px, P - 1 - py) if 0 <= px < P and 0 <= py < P else -1
    if 0 <= edge < RIM_TOP:
        return 0.2                                   # rim stays landable
    return 1.0


def organic_pass(heights):
    """Noise + smoothing: turns angular plateaus into hand-sculpted hills."""
    rng = random.Random(7)
    step = 8
    gw = TOTAL // step + 2
    coarse = [rng.uniform(-5.5, 5.5) for _ in range(gw * gw)]

    def noise(x, y):
        gx, gy = x / step, y / step
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        n00 = coarse[iy * gw + ix]
        n10 = coarse[iy * gw + ix + 1]
        n01 = coarse[(iy + 1) * gw + ix]
        n11 = coarse[(iy + 1) * gw + ix + 1]
        return lerp(lerp(n00, n10, fx), lerp(n01, n11, fx), fy)

    work = [float(h) for h in heights]
    for y in range(TOTAL):
        base = y * TOTAL
        for x in range(TOTAL):
            work[base + x] += noise(x, y)

    for _ in range(2):                       # two 3x3 smoothing passes
        prev = work[:]
        for y in range(1, TOTAL - 1):
            base = y * TOTAL
            for x in range(1, TOTAL - 1):
                acc = 0.0
                for dy in (-TOTAL, 0, TOTAL):
                    i = base + dy + x
                    acc += prev[i - 1] + prev[i] + prev[i + 1]
                work[base + x] = acc / 9.0

    out = bytearray(len(heights))
    for y in range(TOTAL):
        base = y * TOTAL
        for x in range(TOTAL):
            m = freedom_at(x - BORDER, y - BORDER)
            v = heights[base + x] * (1.0 - m) + work[base + x] * m
            out[base + x] = max(0, min(255, round(v)))
    return out


# ------------------------------------------------------------------ textures
# (name, num_tiles) drawn from Golden Oasis's desert palette
PALETTE = [
    ("SandMediumType5c", 16),      # 0 base sand
    ("SandType3wet", 4),           # 1 river bed
    ("GrassMediumType22", 16),     # 2 green banks + meadows
    ("SandLargeType4Grassy", 36),  # 3 oasis pockets
    ("DirtMediumType12", 16),      # 4 roads / high-road trails
    ("DirtMediumType13", 4),       # 5 bridge pads
    ("CliffMediumType20", 16),     # 6 cliff faces
    ("SandMediumType11", 16),      # 7 hill tops
    ("RocksType6", 4),             # 8 rim plateau
]
TRAILS = [(56, 176, 226, 234), (56, 176, 166, 174),      # west arm trails
          (224, 344, 226, 234), (224, 344, 166, 174)]    # east arm trails


def texture_class_at(px, py, cell_heights, oases, meadow):
    """Palette index for a cell (cliff override first)."""
    h = cell_heights
    if max(h) - min(h) > 12:
        return 6                                   # cliff face
    if RIVER_BED[0] - 1 <= px < RIVER_BED[1] + 1:
        return 1
    if RIVER_BANK[0] - 5 <= px < RIVER_BANK[1] + 5 and max(h) <= H_GROUND + 3:
        return 2                                   # lush river banks
    edge = min(px, py, P - 1 - px, P - 1 - py) if 0 <= px < P and 0 <= py < P else -1
    if edge < 0 or edge < RIM_TOP:
        return 8                                   # rim / border
    for x, y, _hh in PADS.values():
        if math.hypot(px - x, py - y) < 7:
            return 5                               # bridge pads
    if ROAD_Y[0] + 2 <= py < ROAD_Y[1] - 2 and CORRIDOR <= px < P - CORRIDOR:
        return 4                                   # the road bed
    if min(h) >= H_BELT - 6:
        for rect in TRAILS:
            if in_rect(px, py, rect):
                return 4                           # trails along the high roads
        return 7                                   # hill tops
    if any((px - ox) ** 2 + (py - oy) ** 2 < r * r for ox, oy, r in oases):
        return 3                                   # oasis pockets
    if meadow(px, py):
        return 2                                   # scattered green meadows
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

    mrng = random.Random(23)
    step = 16
    gw = TOTAL // step + 2
    mgrid = [mrng.random() for _ in range(gw * gw)]

    def meadow(px, py):
        x, y = px + BORDER, py + BORDER
        gx, gy = x / step, y / step
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        v = lerp(lerp(mgrid[iy * gw + ix], mgrid[iy * gw + ix + 1], fx),
                 lerp(mgrid[(iy + 1) * gw + ix], mgrid[(iy + 1) * gw + ix + 1], fx), fy)
        return v > 0.78

    tile = bytearray(TOTAL * TOTAL * 2)
    cliff_bits = bytearray(TOTAL * ((TOTAL + 7) // 8))
    for y in range(TOTAL):
        for x in range(TOTAL):
            px, py = x - BORDER, y - BORDER
            h = (heights[y * TOTAL + x],
                 heights[y * TOTAL + min(x + 1, TOTAL - 1)],
                 heights[min(y + 1, TOTAL - 1) * TOTAL + x],
                 heights[min(y + 1, TOTAL - 1) * TOTAL + min(x + 1, TOTAL - 1)])
            cls = texture_class_at(px, py, h, oases, meadow)
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

    # player starts (waypoints) in the valley hearts
    wp_props = factory.find_props("*Waypoints/Waypoint")
    for n, (px, py) in START_PX.items():
        objs.append(factory.make(
            "*Waypoints/Waypoint", wu(px), wu(py), props=wp_props,
            drop=("waypointPathLabel1", "waypointPathLabel2",
                  "waypointPathLabel3"),
            extra=((f"waypointID", DICT_INT, int(n)),
                   ("waypointName", DICT_ASCIISTRING, f"Player_{n}_Start"))))

    # economy: two supply docks per valley + contested piles at road junctions
    for px, py in START_PX.values():
        for dx, dy in DOCK_OFFSETS:
            objs.append(factory.make("SupplyDock", wu(px + dx), wu(py + dy),
                                     angle=rng.uniform(-3.14, 3.14)))
    for jx, jy in PILE_SPOTS:
        objs.append(factory.make("SupplyPileSmall", wu(jx), wu(jy)))

    # oil derricks up on the high roads (hold the heights, get paid)
    if factory.find_props("TechOilDerrick"):
        for px, py in ((140, 230), (140, 170), (260, 230), (260, 170)):
            objs.append(factory.make("TechOilDerrick", wu(px), wu(py)))

    # THE X: stacked kitty-corner bridges over the river center
    objs += factory.bridge("KandaharBridge",          # high deck: NW <-> SE
                           wu(PADS["NW"][0]), wu(PADS["NW"][1]),
                           wu(PADS["SE"][0]), wu(PADS["SE"][1]))
    objs += factory.bridge("KandaharBridge",          # low deck: SW <-> NE
                           wu(PADS["SW"][0]), wu(PADS["SW"][1]),
                           wu(PADS["NE"][0]), wu(PADS["NE"][1]))

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

    # scenery: palm oases, lush banks, rocks along the high roads
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
                                     wu(RIVER_BANK[0] - 4 - rng.uniform(0, 3)),
                                     wu(py), angle=rng.uniform(-3.14, 3.14)))
            objs.append(factory.make(rng.choice(palms),
                                     wu(RIVER_BANK[1] + 4 + rng.uniform(0, 3)),
                                     wu(py + 13), angle=rng.uniform(-3.14, 3.14)))
    for x0, x1, y0, y1 in TRAILS:                    # rocks lining the trails
        for _ in range(4):
            objs.append(factory.make("Rocks1Brown",
                                     wu(rng.uniform(x0, x1)),
                                     wu(rng.choice((y0 - 3, y1 + 3))),
                                     angle=rng.uniform(-3.14, 3.14)))

    # ambience
    for px, py in START_PX.values():
        objs.append(factory.make("Amb_DesertNatureWindThinLoop", wu(px), wu(py)))
    for py in (70, C, P - 70):
        objs.append(factory.make("Amb_WaterRiverLoop", wu(C), wu(py)))
    return objs


def build_triggers():
    def rect_points(x0, x1, y0, y1, z=0):
        return [(int(wu(x0)), int(wu(y0)), z), (int(wu(x1)), int(wu(y0)), z),
                (int(wu(x1)), int(wu(y1)), z), (int(wu(x0)), int(wu(y1)), z)]

    triggers = [Trigger("River", "", 1, 1, 0, 0,          # border to border
                        rect_points(RIVER_BANK[0], RIVER_BANK[1],
                                    -BORDER, P + BORDER, WATER_Z)),
                Trigger("WaterTable", "", 2, 1, 0, 0,     # map-wide water plane
                        rect_points(0, P, 0, P, 10)),
                Trigger("CombatZone", "", 3, 0, 0, 0,
                        rect_points(120, 280, 120, 280))]
    tid = 4
    for n, (px, py) in START_PX.items():
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
    heights = organic_pass(heights)          # noise + smoothing = sculpted hills

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
