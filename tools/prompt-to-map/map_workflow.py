#!/usr/bin/env python3
"""Inspect and install AI-generated Zero Hour maps for WorldBuilder and Skirmish."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cncmap import MapFile, MapFormatError, MapObject  # noqa: E402


REQUIRED_CHUNKS = (
    "HeightMapData",
    "BlendTileData",
    "WorldInfo",
    "SidesList",
    "ObjectsList",
    "PolygonTriggers",
    "GlobalLighting",
    "WaypointsList",
)


def _prop(obj: MapObject, key: str):
    for entry in obj.props or []:
        if entry.key == key:
            return entry.value
    return None


def inspect_map(map_path: Path) -> dict:
    map_path = map_path.resolve()
    parsed = MapFile.from_bytes(map_path.read_bytes())
    missing = [label for label in REQUIRED_CHUNKS if parsed.get(label) is None]
    if missing:
        raise MapFormatError(f"missing required chunks: {', '.join(missing)}")

    height = parsed.get("HeightMapData")
    if height.width <= 0 or height.height <= 0:
        raise MapFormatError(f"invalid heightmap size {height.width}x{height.height}")
    if len(height.elevations) != height.width * height.height:
        raise MapFormatError("heightmap elevation byte count does not match its dimensions")

    objects = [
        item for item in parsed.get("ObjectsList").items if isinstance(item, MapObject)
    ]
    starts = []
    for obj in objects:
        waypoint = _prop(obj, "waypointName")
        if isinstance(waypoint, str) and waypoint.startswith("Player_") and waypoint.endswith("_Start"):
            starts.append({"name": waypoint, "x": round(obj.x, 2), "y": round(obj.y, 2)})
    if len(starts) < 2:
        raise MapFormatError(f"a skirmish map needs at least 2 player starts; found {len(starts)}")
    if len({start["name"] for start in starts}) != len(starts):
        raise MapFormatError("player start waypoint names must be unique")

    return {
        "path": str(map_path),
        "name": map_path.stem,
        "width": height.width,
        "height": height.height,
        "border": height.border_size,
        "players": len(starts),
        "starts": sorted(starts, key=lambda item: item["name"]),
        "objects": len(objects),
        "triggers": len(parsed.get("PolygonTriggers").triggers),
        "bytes": map_path.stat().st_size,
    }


def _backup_if_changed(source: Path, destination: Path, backup_dir: Path | None) -> None:
    if not destination.exists() or destination.read_bytes() == source.read_bytes():
        return
    if backup_dir is None:
        raise FileExistsError(f"refusing to replace {destination} without a backup directory")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / timestamp / destination.parent.name / destination.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, target)


def install_map(
    map_path: Path, maps_dir: Path, backup_dir: Path | None = None
) -> tuple[Path, dict]:
    summary = inspect_map(map_path)
    name = map_path.stem
    destination_dir = maps_dir.resolve() / name
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_map = destination_dir / f"{name}.map"
    _backup_if_changed(map_path, destination_map, backup_dir)
    shutil.copy2(map_path, destination_map)

    source_tga = map_path.with_suffix(".tga")
    destination_tga = destination_dir / f"{name}.tga"
    if source_tga.exists():
        _backup_if_changed(source_tga, destination_tga, backup_dir)
        shutil.copy2(source_tga, destination_tga)
    elif not destination_tga.exists():
        spike = HERE / "spike"
        sys.path.insert(0, str(spike))
        from make_thumbnail import render_clean, write_tga

        write_tga(render_clean(str(map_path)), str(destination_tga), 128)

    source_strings = map_path.with_name("map.str")
    if source_strings.exists():
        destination_strings = destination_dir / "map.str"
        _backup_if_changed(source_strings, destination_strings, backup_dir)
        shutil.copy2(source_strings, destination_strings)
    return destination_map, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("map", type=Path)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("map", type=Path)
    install_parser.add_argument("maps_dir", type=Path)
    install_parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()

    if args.command == "inspect":
        print(json.dumps(inspect_map(args.map), indent=2))
    else:
        destination, summary = install_map(args.map, args.maps_dir, args.backup_dir)
        print(
            f"Validated {summary['name']}: {summary['players']} players, "
            f"{summary['objects']} objects, {summary['width']}x{summary['height']} cells"
        )
        print(destination)


if __name__ == "__main__":
    main()

