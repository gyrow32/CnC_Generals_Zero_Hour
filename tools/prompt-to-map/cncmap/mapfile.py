"""Map model: parse/serialize every top-level chunk of a Zero Hour .map.

Each chunk class mirrors the EA reader/writer pair cited in
docs/superpowers/specs/map-format-reference.md. Parsing keeps fields exactly
as they are on disk (no read-side transforms like the v1 grid halving or the
"drop triggers with <2 points" cleanup), and serialization is gated on the
chunk's own version so any fixture version round-trips byte-exactly.

Unknown chunks — including everything nested under SidesList (scripts) —
are preserved as RawChunk so no data is ever silently dropped. Raw payloads
bake in TOC ids from the file they were read from, so a MapFile that
contains RawChunks can only be serialized with its original (preserved) TOC.
"""
from dataclasses import dataclass, field
from typing import ClassVar, Optional

from .datachunk import (CHUNK_HEADER, DictEntry, MapFormatError, Reader, Toc,
                        Writer)
from .refpack import decompress_map

# BlendEntry trailing sentinel (WorldHeightMap.h:54)
FLAG_VAL = 0x7ADA0000

# Current chunk versions (Common/MapReaderWriterInfo.h)
K_HEIGHT_MAP_VERSION = 4
K_BLEND_TILE_VERSION = 8
K_WORLDDICT_VERSION = 1
K_SIDES_DATA_VERSION = 3
K_OBJECTS_VERSION = 3
K_TRIGGERS_VERSION = 4
K_LIGHTING_VERSION = 3
K_WAYPOINTS_VERSION = 1


@dataclass
class RawChunk:
    """Any chunk we don't model: header fields + verbatim payload bytes."""
    label: str
    version: int
    data: bytes

    def body_bytes(self, toc: Toc) -> bytes:
        return self.data


def _write_subchunk(w: Writer, toc: Toc, chunk) -> None:
    cid = toc.get_or_allocate(chunk.label)
    body = chunk.body_bytes(toc)
    w.raw(CHUNK_HEADER.pack(cid, chunk.version, len(body)))
    w.raw(body)


def _parse_raw_subchunks(r: Reader, toc: Toc) -> list:
    """Consume the rest of a payload as a sequence of raw sub-chunks."""
    out = []
    while r.remaining:
        if r.remaining < CHUNK_HEADER.size:
            raise MapFormatError(
                f"{r.remaining} trailing bytes: too small for a sub-chunk header")
        label = toc.name_of(r.u32())
        version = r.u16()
        size = r.i32()
        if size < 0 or size > r.remaining:
            raise MapFormatError(
                f"sub-chunk {label!r} dataSize {size} exceeds parent payload")
        out.append(RawChunk(label, version, r.bytes(size)))
    return out


# ---------------------------------------------------------------------------
# HeightMapData (v4) — WHeightMapEdit.cpp:587-608 / WorldHeightMap.cpp:890-942
# ---------------------------------------------------------------------------

@dataclass
class HeightMapData:
    label: ClassVar[str] = "HeightMapData"
    version: int
    width: int
    height: int
    border_size: Optional[int]                 # v>=3
    boundaries: Optional[list]                 # v>=4: [(x, y), ...]
    elevations: bytes                          # width*height u8, row-major

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "HeightMapData":
        width = r.i32()
        height = r.i32()
        border = r.i32() if version >= 3 else None
        boundaries = None
        if version >= 4:
            boundaries = [(r.i32(), r.i32()) for _ in range(r.i32())]
        data_size = r.i32()
        if data_size <= 0 or data_size != width * height:
            raise MapFormatError(
                f"HeightMapData dataSize {data_size} != {width}x{height}")
        return cls(version, width, height, border, boundaries,
                   r.bytes(data_size))

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.i32(self.width)
        w.i32(self.height)
        if self.version >= 3:
            w.i32(self.border_size)
        if self.version >= 4:
            w.i32(len(self.boundaries))
            for x, y in self.boundaries:
                w.i32(x)
                w.i32(y)
        w.i32(len(self.elevations))
        w.raw(self.elevations)
        return w.getvalue()


# ---------------------------------------------------------------------------
# BlendTileData (v8) — WHeightMapEdit.cpp:611-669 / WorldHeightMap.cpp:1071-1228
# ---------------------------------------------------------------------------

@dataclass
class TextureClass:
    first_tile: int
    num_tiles: int
    width: int
    legacy: int          # written as 0 by EA, read and discarded; preserved here
    name: str


@dataclass
class EdgeTextureClass:
    first_tile: int
    num_tiles: int
    width: int
    name: str


@dataclass
class BlendEntry:
    blend_ndx: int
    horiz: int
    vert: int
    right_diagonal: int
    left_diagonal: int
    inverted: int
    long_diagonal: Optional[int]               # v>=3
    custom_blend_edge_class: Optional[int]     # v>=4


@dataclass
class CliffInfo:
    tile_index: int
    uvs: tuple            # (u0, v0, u1, v1, u2, v2, u3, v3)
    flip: int
    mutant: int


@dataclass
class BlendTileData:
    label: ClassVar[str] = "BlendTileData"
    version: int
    tile_ndxes: bytes                          # width*height i16
    blend_tile_ndxes: bytes                    # width*height i16
    extra_blend_tile_ndxes: Optional[bytes]    # v>=6
    cliff_info_ndxes: Optional[bytes]          # v>=5
    cell_cliff_state: Optional[bytes]          # v>=7 (v7: (w+1)//8, v8: (w+7)//8 bytes/row)
    num_bitmap_tiles: int
    num_blended_tiles: int                     # index 0 reserved; entries = n-1
    num_cliff_info: Optional[int]              # v>=5; index 0 reserved
    texture_classes: list
    num_edge_tiles: Optional[int]              # v>=4
    edge_texture_classes: Optional[list]       # v>=4
    blend_entries: list
    cliff_infos: Optional[list]                # v>=5

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc,
                   width: int, height: int) -> "BlendTileData":
        n = r.i32()
        if n != width * height:
            raise MapFormatError(
                f"BlendTileData len {n} != heightmap {width}x{height}")
        tile = r.bytes(n * 2)
        blend = r.bytes(n * 2)
        extra = r.bytes(n * 2) if version >= 6 else None
        cliff_ndx = r.bytes(n * 2) if version >= 5 else None
        cliff_state = None
        if version >= 7:
            # v7 saved rows at the buggy (width+1)/8 bytes (WorldHeightMap.cpp:1109)
            row = (width + 1) // 8 if version == 7 else (width + 7) // 8
            cliff_state = r.bytes(height * row)
        num_bitmap = r.i32()
        num_blended = r.i32()
        num_cliff = r.i32() if version >= 5 else None
        texture_classes = [
            TextureClass(r.i32(), r.i32(), r.i32(), r.i32(), r.ascii())
            for _ in range(r.i32())]
        num_edge_tiles = None
        edge_classes = None
        if version >= 4:
            num_edge_tiles = r.i32()
            edge_classes = [
                EdgeTextureClass(r.i32(), r.i32(), r.i32(), r.ascii())
                for _ in range(r.i32())]
        blend_entries = []
        for _ in range(1, num_blended):
            e = BlendEntry(r.i32(), r.u8(), r.u8(), r.u8(), r.u8(), r.u8(),
                           r.u8() if version >= 3 else None,
                           r.i32() if version >= 4 else None)
            flag = r.u32()
            if flag != FLAG_VAL:
                raise MapFormatError(
                    f"BlendEntry sentinel 0x{flag:08X} != 0x{FLAG_VAL:08X}")
            blend_entries.append(e)
        cliff_infos = None
        if version >= 5:
            cliff_infos = [
                CliffInfo(r.i32(), tuple(r.f32() for _ in range(8)),
                          r.u8(), r.u8())
                for _ in range(1, num_cliff)]
        return cls(version, tile, blend, extra, cliff_ndx, cliff_state,
                   num_bitmap, num_blended, num_cliff, texture_classes,
                   num_edge_tiles, edge_classes, blend_entries, cliff_infos)

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.i32(len(self.tile_ndxes) // 2)
        w.raw(self.tile_ndxes)
        w.raw(self.blend_tile_ndxes)
        if self.version >= 6:
            w.raw(self.extra_blend_tile_ndxes)
        if self.version >= 5:
            w.raw(self.cliff_info_ndxes)
        if self.version >= 7:
            w.raw(self.cell_cliff_state)
        w.i32(self.num_bitmap_tiles)
        w.i32(self.num_blended_tiles)
        if self.version >= 5:
            w.i32(self.num_cliff_info)
        w.i32(len(self.texture_classes))
        for t in self.texture_classes:
            w.i32(t.first_tile)
            w.i32(t.num_tiles)
            w.i32(t.width)
            w.i32(t.legacy)
            w.ascii(t.name)
        if self.version >= 4:
            w.i32(self.num_edge_tiles)
            w.i32(len(self.edge_texture_classes))
            for t in self.edge_texture_classes:
                w.i32(t.first_tile)
                w.i32(t.num_tiles)
                w.i32(t.width)
                w.ascii(t.name)
        for e in self.blend_entries:
            w.i32(e.blend_ndx)
            w.u8(e.horiz)
            w.u8(e.vert)
            w.u8(e.right_diagonal)
            w.u8(e.left_diagonal)
            w.u8(e.inverted)
            if self.version >= 3:
                w.u8(e.long_diagonal)
            if self.version >= 4:
                w.i32(e.custom_blend_edge_class)
            w.u32(FLAG_VAL)
        if self.version >= 5:
            for c in self.cliff_infos:
                w.i32(c.tile_index)
                for v in c.uvs:
                    w.f32(v)
                w.u8(c.flip)
                w.u8(c.mutant)
        return w.getvalue()


# ---------------------------------------------------------------------------
# WorldInfo (v1) — a single Dict of global settings
# ---------------------------------------------------------------------------

@dataclass
class WorldInfo:
    label: ClassVar[str] = "WorldInfo"
    version: int
    props: list          # [DictEntry, ...]

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "WorldInfo":
        return cls(version, r.dict(toc))

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.dict(self.props, toc)
        return w.getvalue()


# ---------------------------------------------------------------------------
# SidesList (v3) — SidesList.cpp:329-388 / :243-319
# ---------------------------------------------------------------------------

@dataclass
class BuildListEntry:
    building_name: str
    template_name: str
    x: float
    y: float
    z: float
    angle: float
    initially_built: int
    num_rebuilds: int
    script: Optional[str]        # v>=3
    health: Optional[int]        # v>=3
    whiner: Optional[int]        # v>=3
    unsellable: Optional[int]    # v>=3
    repairable: Optional[int]    # v>=3


@dataclass
class Side:
    props: list                  # [DictEntry, ...]
    build_list: list             # [BuildListEntry, ...]


@dataclass
class SidesList:
    label: ClassVar[str] = "SidesList"
    version: int
    sides: list
    teams: Optional[list]        # v>=2: [[DictEntry, ...], ...]
    subchunks: list = field(default_factory=list)   # PlayerScriptsList etc., raw

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "SidesList":
        sides = []
        for _ in range(r.i32()):
            props = r.dict(toc)
            builds = []
            for _ in range(r.i32()):
                builds.append(BuildListEntry(
                    r.ascii(), r.ascii(), r.f32(), r.f32(), r.f32(), r.f32(),
                    r.u8(), r.i32(),
                    r.ascii() if version >= 3 else None,
                    r.i32() if version >= 3 else None,
                    r.u8() if version >= 3 else None,
                    r.u8() if version >= 3 else None,
                    r.u8() if version >= 3 else None))
            sides.append(Side(props, builds))
        teams = None
        if version >= 2:
            teams = [r.dict(toc) for _ in range(r.i32())]
        return cls(version, sides, teams, _parse_raw_subchunks(r, toc))

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.i32(len(self.sides))
        for side in self.sides:
            w.dict(side.props, toc)
            w.i32(len(side.build_list))
            for b in side.build_list:
                w.ascii(b.building_name)
                w.ascii(b.template_name)
                w.f32(b.x)
                w.f32(b.y)
                w.f32(b.z)
                w.f32(b.angle)
                w.u8(b.initially_built)
                w.i32(b.num_rebuilds)
                if self.version >= 3:
                    w.ascii(b.script)
                    w.i32(b.health)
                    w.u8(b.whiner)
                    w.u8(b.unsellable)
                    w.u8(b.repairable)
        if self.version >= 2:
            w.i32(len(self.teams))
            for team in self.teams:
                w.dict(team, toc)
        for chunk in self.subchunks:
            _write_subchunk(w, toc, chunk)
        return w.getvalue()


# ---------------------------------------------------------------------------
# ObjectsList (v3) / Object (v3) — WHeightMapEdit.cpp:689-726
# ---------------------------------------------------------------------------

@dataclass
class MapObject:
    label: ClassVar[str] = "Object"
    version: int
    x: float
    y: float
    z: float
    angle: float
    flags: int
    template_name: str
    props: Optional[list]        # v>=2: [DictEntry, ...]

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.f32(self.x)
        w.f32(self.y)
        w.f32(self.z)
        w.f32(self.angle)
        w.i32(self.flags)
        w.ascii(self.template_name)
        if self.version >= 2:
            w.dict(self.props, toc)
        return w.getvalue()


@dataclass
class ObjectsList:
    label: ClassVar[str] = "ObjectsList"
    version: int
    items: list                  # MapObject | RawChunk, in file order

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "ObjectsList":
        items = []
        while r.remaining:
            if r.remaining < CHUNK_HEADER.size:
                raise MapFormatError(
                    f"ObjectsList: {r.remaining} trailing bytes")
            label = toc.name_of(r.u32())
            sub_version = r.u16()
            size = r.i32()
            if size < 0 or size > r.remaining:
                raise MapFormatError(
                    f"ObjectsList sub-chunk {label!r} dataSize {size} too big")
            sub = r.sub(size)
            if label == "Object":
                obj = MapObject(sub_version, sub.f32(), sub.f32(), sub.f32(),
                                sub.f32(), sub.i32(), sub.ascii(),
                                sub.dict(toc) if sub_version >= 2 else None)
                sub.expect_end("Object")
                items.append(obj)
            else:
                items.append(RawChunk(label, sub_version,
                                      sub.bytes(sub.remaining)))
        return cls(version, items)

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        for item in self.items:
            _write_subchunk(w, toc, item)
        return w.getvalue()


# ---------------------------------------------------------------------------
# PolygonTriggers (v4) — PolygonTrigger.cpp:240-268 / :150-231
# ---------------------------------------------------------------------------

@dataclass
class Trigger:
    name: str
    layer_name: Optional[str]    # v>=4
    trigger_id: int
    is_water: Optional[int]      # v>=2
    is_river: Optional[int]      # v>=3
    river_start: Optional[int]   # v>=3
    points: list                 # [(x, y, z) int world coords, ...]


@dataclass
class PolygonTriggers:
    label: ClassVar[str] = "PolygonTriggers"
    version: int
    triggers: list

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "PolygonTriggers":
        triggers = []
        for _ in range(r.i32()):
            name = r.ascii()
            layer = r.ascii() if version >= 4 else None
            trigger_id = r.i32()
            is_water = r.u8() if version >= 2 else None
            is_river = r.u8() if version >= 3 else None
            river_start = r.i32() if version >= 3 else None
            points = [(r.i32(), r.i32(), r.i32()) for _ in range(r.i32())]
            triggers.append(Trigger(name, layer, trigger_id, is_water,
                                    is_river, river_start, points))
        return cls(version, triggers)

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.i32(len(self.triggers))
        for t in self.triggers:
            w.ascii(t.name)
            if self.version >= 4:
                w.ascii(t.layer_name)
            w.i32(t.trigger_id)
            if self.version >= 2:
                w.u8(t.is_water)
            if self.version >= 3:
                w.u8(t.is_river)
                w.i32(t.river_start)
            w.i32(len(t.points))
            for x, y, z in t.points:
                w.i32(x)
                w.i32(y)
                w.i32(z)
        return w.getvalue()


# ---------------------------------------------------------------------------
# GlobalLighting (v3) — WHeightMapEdit.cpp:732-782 / WorldHeightMap.cpp:782-853
# ---------------------------------------------------------------------------

@dataclass
class LightingBlock:
    """One time-of-day. Each light is a 9-float tuple:
    ambient r,g,b, diffuse r,g,b, lightPos x,y,z."""
    terrain: list                # 1 light (v1/v2) or 3 (v>=3)
    objects: list                # 1 light (v1) or 3 (v>=2)


@dataclass
class GlobalLighting:
    label: ClassVar[str] = "GlobalLighting"
    version: int
    time_of_day: int
    blocks: list                 # 4 LightingBlocks
    shadow_color: Optional[int]  # trailing u32, present iff bytes remained

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "GlobalLighting":
        def light():
            return tuple(r.f32() for _ in range(9))

        time_of_day = r.i32()
        blocks = []
        for _ in range(4):
            terrain = [light()]
            objects = [light()]
            if version >= 2:
                objects += [light(), light()]
            if version >= 3:
                terrain += [light(), light()]
            blocks.append(LightingBlock(terrain, objects))
        shadow_color = r.u32() if r.remaining else None
        return cls(version, time_of_day, blocks, shadow_color)

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()

        def light(values):
            for v in values:
                w.f32(v)

        w.i32(self.time_of_day)
        for b in self.blocks:
            light(b.terrain[0])
            light(b.objects[0])
            if self.version >= 2:
                light(b.objects[1])
                light(b.objects[2])
            if self.version >= 3:
                light(b.terrain[1])
                light(b.terrain[2])
        if self.shadow_color is not None:
            w.u32(self.shadow_color)
        return w.getvalue()


# ---------------------------------------------------------------------------
# WaypointsList (v1) — WorldBuilderDoc.cpp:302-308 / TerrainLogic.cpp:1338-1349
# ---------------------------------------------------------------------------

@dataclass
class WaypointsList:
    label: ClassVar[str] = "WaypointsList"
    version: int
    links: list                  # [(waypoint1_id, waypoint2_id), ...]

    @classmethod
    def parse_body(cls, r: Reader, version: int, toc: Toc) -> "WaypointsList":
        return cls(version, [(r.i32(), r.i32()) for _ in range(r.i32())])

    def body_bytes(self, toc: Toc) -> bytes:
        w = Writer()
        w.i32(len(self.links))
        for a, b in self.links:
            w.i32(a)
            w.i32(b)
        return w.getvalue()


# ---------------------------------------------------------------------------
# MapFile — the whole container
# ---------------------------------------------------------------------------

_SIMPLE_CHUNKS = {
    cls.label: cls for cls in
    (HeightMapData, WorldInfo, SidesList, ObjectsList, PolygonTriggers,
     GlobalLighting, WaypointsList)
}


@dataclass
class MapFile:
    chunks: list
    toc: Optional[Toc] = None    # preserved verbatim when parsed; None = fresh

    @classmethod
    def from_bytes(cls, data: bytes) -> "MapFile":
        """Parse a .map as it sits on disk (decompressing if needed)."""
        return cls.parse(decompress_map(data))

    @classmethod
    def parse(cls, data: bytes) -> "MapFile":
        """Parse a decompressed CkMp chunk stream."""
        r = Reader(data)
        toc = Toc.parse(r)
        chunks = []
        heightmap_dims = None
        while r.remaining:
            if r.remaining < CHUNK_HEADER.size:
                raise MapFormatError(f"{r.remaining} trailing bytes after last chunk")
            label = toc.name_of(r.u32())
            version = r.u16()
            size = r.i32()
            if size < 0 or size > r.remaining:
                raise MapFormatError(f"chunk {label!r} dataSize {size} too big")
            sub = r.sub(size)
            if label == "BlendTileData":
                if heightmap_dims is None:
                    raise MapFormatError("BlendTileData before HeightMapData")
                chunk = BlendTileData.parse_body(sub, version, toc,
                                                 *heightmap_dims)
            elif label in _SIMPLE_CHUNKS:
                chunk = _SIMPLE_CHUNKS[label].parse_body(sub, version, toc)
                if label == "HeightMapData":
                    heightmap_dims = (chunk.width, chunk.height)
            else:
                chunk = RawChunk(label, version, sub.bytes(sub.remaining))
            sub.expect_end(label)
            chunks.append(chunk)
        return cls(chunks, toc)

    def to_bytes(self) -> bytes:
        """Serialize to an uncompressed CkMp stream (the engine reads these)."""
        toc = self.toc
        if toc is None:
            self._reject_raw_chunks()
            toc = Toc()
        stream = bytearray()
        for chunk in self.chunks:
            cid = toc.get_or_allocate(chunk.label)
            body = chunk.body_bytes(toc)
            stream += CHUNK_HEADER.pack(cid, chunk.version, len(body))
            stream += body
        return toc.serialize() + bytes(stream)

    def _reject_raw_chunks(self):
        """Raw payloads reference ids from their original TOC; with a fresh
        TOC those ids would dangle, so refuse rather than corrupt."""
        raws = [c.label for c in self.chunks if isinstance(c, RawChunk)]
        for c in self.chunks:
            if isinstance(c, SidesList):
                raws += [s.label for s in c.subchunks]
            elif isinstance(c, ObjectsList):
                raws += [i.label for i in c.items if isinstance(i, RawChunk)]
        if raws:
            raise MapFormatError(
                f"cannot serialize RawChunks {raws} without the original TOC")

    def get(self, label: str):
        """First chunk with the given label, or None."""
        for chunk in self.chunks:
            if chunk.label == label:
                return chunk
        return None
