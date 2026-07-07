"""cncmap — read/write Command & Conquer Generals: Zero Hour .map files.

Proven by byte-exact round-trips against real retail maps:
MapFile.parse(decompress_map(raw)).to_bytes() == decompress_map(raw).
"""
from .datachunk import (DICT_ASCIISTRING, DICT_BOOL, DICT_INT, DICT_REAL,
                        DICT_UNICODESTRING, DictEntry, MapFormatError, Toc)
from .mapfile import (FLAG_VAL, BlendEntry, BlendTileData, BuildListEntry,
                      CliffInfo, EdgeTextureClass, GlobalLighting,
                      HeightMapData, LightingBlock, MapFile, MapObject,
                      ObjectsList, PolygonTriggers, RawChunk, Side, SidesList,
                      TextureClass, Trigger, WaypointsList, WorldInfo)
from .refpack import decompress_map, is_compressed

__all__ = [
    "MapFile", "MapFormatError", "Toc", "DictEntry",
    "DICT_BOOL", "DICT_INT", "DICT_REAL", "DICT_ASCIISTRING",
    "DICT_UNICODESTRING", "FLAG_VAL",
    "HeightMapData", "BlendTileData", "WorldInfo", "SidesList", "ObjectsList",
    "PolygonTriggers", "GlobalLighting", "WaypointsList", "RawChunk",
    "MapObject", "Side", "BuildListEntry", "Trigger", "LightingBlock",
    "TextureClass", "EdgeTextureClass", "BlendEntry", "CliffInfo",
    "decompress_map", "is_compressed",
]
