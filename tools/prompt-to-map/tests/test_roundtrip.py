"""THE GATE: byte-exact round-trip on every real fixture, plus a
from-scratch new-map smoke test.

serialize(parse(decompress(f))) must equal decompress(f) -- the full
decompressed stream including the TOC, byte for byte.
"""
import struct
from pathlib import Path

import pytest

from cncmap import (DICT_ASCIISTRING, DICT_BOOL, DICT_INT, DICT_UNICODESTRING,
                    DictEntry, HeightMapData, MapFile, MapObject, ObjectsList,
                    RawChunk, Side, SidesList, WorldInfo, decompress_map)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = sorted(FIXTURE_DIR.glob("*.map"), key=lambda p: p.name.lower())

MODELED_LABELS = {
    "HeightMapData", "BlendTileData", "WorldInfo", "SidesList",
    "ObjectsList", "PolygonTriggers", "GlobalLighting", "WaypointsList",
}


def chunk_spans(data):
    """[(label, start, end)] for every top-level chunk, plus the TOC span."""
    from cncmap.datachunk import Reader, Toc
    r = Reader(data)
    toc = Toc.parse(r)
    spans = [("<TOC>", 0, r.pos)]
    while r.remaining >= 10:
        start = r.pos
        label = toc.name_of(r.u32())
        r.u16()
        size = r.i32()
        r.pos += size
        spans.append((label, start, r.pos))
    return spans


def describe_mismatch(expected, produced):
    """Locate the first differing byte and name the chunk that owns it."""
    n = min(len(expected), len(produced))
    off = next((i for i in range(n) if expected[i] != produced[i]), n)
    owner = next((f"{lbl} [{s:#x}..{e:#x}]"
                  for lbl, s, e in chunk_spans(expected) if s <= off < e),
                 "<past end>")
    lo, hi = max(0, off - 16), off + 16
    return (
        f"first mismatch at offset {off:#x} inside {owner}\n"
        f"  sizes: expected {len(expected)}, produced {len(produced)}\n"
        f"  expected[{lo:#x}:{hi:#x}] = {expected[lo:hi].hex(' ')}\n"
        f"  produced[{lo:#x}:{hi:#x}] = {produced[lo:hi].hex(' ')}"
    )


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_byte_exact_roundtrip(path):
    plain = decompress_map(path.read_bytes())
    produced = MapFile.parse(plain).to_bytes()
    if produced != plain:
        pytest.fail(describe_mismatch(plain, produced))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_known_chunks_are_fully_modeled(path):
    """Every chunk in our 8-label set must decode to a typed model, and raw
    preservation is only allowed for labels outside that set."""
    m = MapFile.from_bytes(path.read_bytes())
    for chunk in m.chunks:
        if chunk.label in MODELED_LABELS:
            assert not isinstance(chunk, RawChunk), (
                f"{chunk.label} fell back to raw preservation")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_reparse_yields_equal_model(path):
    m = MapFile.from_bytes(path.read_bytes())
    again = MapFile.parse(m.to_bytes())
    assert again.chunks == m.chunks


def f32(value):
    """Snap a Python float to exact float32, as it will live on disk."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def build_minimal_map(width=64, height=64, border=8):
    """A from-scratch skirmish skeleton: flat terrain, world dict, two sides,
    two player-start waypoints."""
    playable = [(width - 2 * border, height - 2 * border)]
    heightmap = HeightMapData(
        version=4, width=width, height=height, border_size=border,
        boundaries=playable, elevations=bytes([20]) * (width * height))
    world = WorldInfo(version=1, props=[DictEntry("weather", DICT_INT, 0)])
    sides = SidesList(
        version=3,
        sides=[
            Side(props=[
                DictEntry("playerName", DICT_ASCIISTRING, ""),
                DictEntry("playerFaction", DICT_ASCIISTRING, "FactionCivilian"),
                DictEntry("playerDisplayName", DICT_UNICODESTRING, "Neutral"),
                DictEntry("playerIsHuman", DICT_BOOL, 0),
            ], build_list=[]),
            Side(props=[
                DictEntry("playerName", DICT_ASCIISTRING, "SkirmishPlayer"),
                DictEntry("playerFaction", DICT_ASCIISTRING, "FactionAmerica"),
                DictEntry("playerDisplayName", DICT_UNICODESTRING, "Player 1"),
                DictEntry("playerIsHuman", DICT_BOOL, 1),
            ], build_list=[]),
        ],
        teams=[],
        subchunks=[])

    def start(n, x, y):
        return MapObject(
            version=3, x=f32(x), y=f32(y), z=f32(0.0), angle=f32(0.0), flags=0,
            template_name="*Waypoints/Waypoint",
            props=[
                DictEntry("waypointID", DICT_INT, n),
                DictEntry("waypointName", DICT_ASCIISTRING, f"Player_{n}_Start"),
            ])

    objects = ObjectsList(version=3, items=[
        start(1, 160.0, 160.0),
        start(2, (width - border * 2) * 10.0 - 160.0,
              (height - border * 2) * 10.0 - 160.0),
    ])
    return MapFile(chunks=[heightmap, world, sides, objects])


def test_new_map_from_scratch_roundtrips():
    m = build_minimal_map()
    data = m.to_bytes()
    assert data.startswith(b"CkMp")
    again = MapFile.parse(data)
    assert again.chunks == m.chunks
    # and serializing the reparsed model (now with a preserved TOC) is
    # byte-identical -- writer and reader agree on every id
    assert again.to_bytes() == data


def test_new_map_toc_matches_ea_allocator():
    data = build_minimal_map().to_bytes()
    m = MapFile.parse(data)
    ids = dict(m.toc.entries)
    # ids start at 1 in first-use order: first chunk label, then its dict keys
    assert ids["HeightMapData"] == 1
    assert ids["WorldInfo"] == 2
    assert ids["weather"] == 3
    # disk order is newest-first (EA prepends to the mapping list)
    disk_ids = [cid for _, cid in m.toc.entries]
    assert disk_ids == sorted(disk_ids, reverse=True)
