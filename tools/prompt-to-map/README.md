# prompt-to-map

Turn a natural-language prompt into a playable **Command & Conquer: Generals — Zero Hour**
map. The AI designs terrain, resources, structures, player starts, and balance, then writes
a real `.map` file that the game and WorldBuilder can load.

See the [design spec](../../docs/superpowers/specs/2026-07-06-prompt-to-map-design.md) and
the [byte-level format reference](../../docs/superpowers/specs/map-format-reference.md).

## Status

The binary map engine is working and covered by round-trip tests. Two generated maps,
Scorched Crossing and Panorama Pass, are playable and editable in WorldBuilder. The next
phase is turning their reusable terrain/content patterns into a general prompt-driven
designer rather than one builder script per map.

## AI-to-WorldBuilder workflow

From the repository root:

```powershell
# Build one of the deterministic AI-designed maps.
python .\tools\prompt-to-map\maps\build_panorama_pass.py

# Validate it, install its bundle, and open it directly in WorldBuilder.
powershell -NoProfile -ExecutionPolicy Bypass -File .\worldbuilder-local.ps1 -Map "Panorama Pass"

# Unpack owned retail INI/maps and build an AI-friendly reference catalog.
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\local-dev\dev.ps1 -Action unpack
```

`map_workflow.py` refuses maps missing required chunks or at least two unique player
starts. It preserves a changed installed map under `.local/map-backups` before replacing
it, carries along `map.str` and an existing thumbnail, and generates a thumbnail when
one is missing.

The ignored `.local/reference/reference-catalog.json` file inventories official map
dimensions, player counts, object usage, object templates, and terrain textures. Extracted
retail files remain under `.local/reference/archives` and are never committed.

## Layout

```text
cncmap/               binary file engine and map object model
maps/                 deterministic AI-authored map builders and generated output
map_workflow.py       validation, safe installation, thumbnails, and backups
reference_catalog.py  owned retail archive extraction and AI reference index
tests/                round-trip, primitive, and workflow tests
spike/                feasibility tools and renderers retained for reference
```

## Tests

```powershell
python -m pytest .\tools\prompt-to-map\tests -q
```
