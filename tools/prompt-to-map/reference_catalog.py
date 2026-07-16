#!/usr/bin/env python3
"""Unpack owned Zero Hour reference data and build an AI-friendly map catalog."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "local-dev"))
sys.path.insert(0, str(HERE))

from big_archive import extract_all, read_entries  # noqa: E402
from cncmap import MapFile, MapObject  # noqa: E402


TEMPLATE_RE = re.compile(r"^\s*(?:Object|ChildObject)\s+([^\s;]+)", re.MULTILINE)


def _prop(obj: MapObject, key: str):
    for entry in obj.props or []:
        if entry.key == key:
            return entry.value
    return None


def build_catalog(game_dir: Path, output_dir: Path, unpack: bool = True) -> dict:
    game_dir = game_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = output_dir / "archives"

    archive_data: dict[str, tuple[bytes, list]] = {}
    archive_summary = {}
    for archive_name in ("INIZH.big", "MapsZH.big"):
        archive = game_dir / archive_name
        data, entries = read_entries(archive)
        archive_data[archive_name] = (data, entries)
        archive_summary[archive_name] = {
            "path": str(archive),
            "files": len(entries),
            "bytes": len(data),
        }
        if unpack:
            extract_all(archive, archive_dir / archive.stem)

    ini_data, ini_entries = archive_data["INIZH.big"]
    templates: set[str] = set()
    ini_files: list[str] = []
    for entry in ini_entries:
        if not entry.name.lower().endswith(".ini"):
            continue
        ini_files.append(entry.name)
        text = ini_data[entry.offset : entry.offset + entry.size].decode("latin-1")
        templates.update(TEMPLATE_RE.findall(text))

    map_data, map_entries = archive_data["MapsZH.big"]
    maps = []
    terrain_textures: set[str] = set()
    placed_objects: Counter[str] = Counter()
    parse_errors = []
    for entry in map_entries:
        if not entry.name.lower().endswith(".map"):
            continue
        raw = map_data[entry.offset : entry.offset + entry.size]
        try:
            parsed = MapFile.from_bytes(raw)
            height = parsed.get("HeightMapData")
            blend = parsed.get("BlendTileData")
            objects = parsed.get("ObjectsList")
            starts = []
            object_count = 0
            if objects:
                for obj in objects.items:
                    if not isinstance(obj, MapObject):
                        continue
                    object_count += 1
                    placed_objects[obj.template_name] += 1
                    waypoint = _prop(obj, "waypointName")
                    if isinstance(waypoint, str) and waypoint.startswith("Player_"):
                        starts.append(waypoint)
            if blend:
                terrain_textures.update(t.name for t in blend.texture_classes)
                terrain_textures.update(t.name for t in (blend.edge_texture_classes or []))
            maps.append(
                {
                    "name": Path(entry.name.replace("\\", "/")).stem,
                    "archivePath": entry.name,
                    "width": height.width if height else None,
                    "height": height.height if height else None,
                    "border": height.border_size if height else None,
                    "players": len(starts),
                    "starts": sorted(starts),
                    "objects": object_count,
                }
            )
        except Exception as exc:  # catalog the failure without losing all references
            parse_errors.append({"archivePath": entry.name, "error": str(exc)})

    catalog = {
        "gameDirectory": str(game_dir),
        "archives": archive_summary,
        "iniFiles": sorted(ini_files, key=str.lower),
        "objectTemplates": sorted(templates, key=str.lower),
        "terrainTexturesUsedByRetailMaps": sorted(terrain_textures, key=str.lower),
        "placedObjectFrequency": dict(placed_objects.most_common()),
        "maps": sorted(maps, key=lambda item: item["name"].lower()),
        "parseErrors": parse_errors,
    }
    catalog_path = output_dir / "reference-catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--index-only", action="store_true")
    args = parser.parse_args()
    catalog = build_catalog(args.game_dir, args.output_dir, not args.index_only)
    print(
        f"Cataloged {len(catalog['maps'])} retail maps, "
        f"{len(catalog['objectTemplates'])} object templates, and "
        f"{len(catalog['terrainTexturesUsedByRetailMaps'])} terrain textures."
    )
    if catalog["parseErrors"]:
        print(f"Warning: {len(catalog['parseErrors'])} map(s) could not be parsed.")
    print(args.output_dir / "reference-catalog.json")


if __name__ == "__main__":
    main()

