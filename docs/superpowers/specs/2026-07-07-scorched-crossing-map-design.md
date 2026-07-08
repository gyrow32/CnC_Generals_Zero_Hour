# Scorched Crossing — 4-player map design (the father-son map, rebuilt)

**Status:** approved by Mike 2026-07-07 (layout confirmed verbally; "make it happen now").
**Origin:** recreation of a map Mike and his son built in WorldBuilder ~15 years ago.
**Builder:** generated entirely by `cncmap` (no WorldBuilder) — first real map from the
prompt-to-map engine.

## Layout (top-down)

Four corner bases, each a flat valley walled in by mountains. A river bisects the map
vertically; a road bisects it horizontally. The only ground routes between bases:

1. **Edge corridors** — flat strips hugging the far-left and far-right map edges,
   connecting the two bases on each side (TL↔BL on the left, TR↔BR on the right).
2. **The center road** — runs west↔east between the mountain belts at map middle,
   linking the two edge corridors and crossing the river on a normal bridge at center.
3. **Two high diagonal crossings** — from each valley a ramp climbs to an elevated
   shelf beside the river; a long bridge crosses the river diagonally to the shelf of
   the *diagonally opposite* base (BL↔TR and BR↔TL), then a ramp descends into that
   valley. The diagonals pass high above the center road bridge (bridge-over-bridge).

The outer rim is high flat-topped mountains (helicopter-landable). Symmetric under
180° rotation.

## Numbers

- Grid 480×480 cells, border 40 → playable 400×400 (4000×4000 world units).
- Heights (u8, ×0.625 = world z): river bed 8, valley floor 20, shelves 52,
  inner ranges 72, outer rim 84.
- Cliff rule (engine): a cell is impassable when its corner-height spread exceeds
  9.8 wu ≈ 15.7 height units. Ramps rise ≤ 8 units/cell (drivable); mountain walls
  rise much faster (sealed).
- River: vertical strip ~28 cells wide at center; water = a `PolygonTriggers` water
  area at z ≈ 6.5 wu spanning the river.

## Skeleton reuse

Start from parsed **Golden Oasis** (desert retail map) and keep, verbatim: the TOC,
`SidesList` (Neutral + Civilian + 12 skirmish factions, teams, AI script chunk),
`GlobalLighting` (desert daylight), `WorldInfo` (with `mapName` blanked so the game
displays the folder name). Replace: `HeightMapData`, `BlendTileData`, `ObjectsList`,
`PolygonTriggers`, `WaypointsList`. This keeps every fiddly multiplayer boilerplate
byte proven-correct while the terrain and content are 100% generated.

## Textures (scorched desert + green accents)

Per-cell texture classes from Golden Oasis's palette, no blend edges in v1
(hard transitions acceptable): `SandMediumType5c` base; `DirtMediumType12` road
shoulders and scorched patches; `CliffMediumType20` on steep cells;
`GrassMediumType22`/`SandLargeType4Grassy` river banks and small oasis pockets;
`RocksType6` near the rim. Cell tile index = EA formula
`(firstTile + (x/2)%w + w*((y/2)%w)) << 2 | (y&1)<<1 | (x&1)`.

## Objects

- 4 player starts (`*Waypoints/Waypoint`, `waypointID` 1–4, `waypointName
  Player_N_Start`), one per valley.
- Economy: 2 `SupplyDock` per valley; contested `TechOilDerrick`s where the road
  meets the edge corridors (verify template name against fixtures; drop if absent).
- Bridges: center road bridge + two diagonal shelf bridges (`KandaharBridge`-family;
  two objects per bridge, flags 0x10/0x20 = endpoints).
- Roads: `DirtRoad` segment pairs (flags 0x02/0x04) along the center road and short
  spurs into the valleys from the corridors.
- Scenery: palm clusters (`TreePalm*`) at oases and banks, `Rocks1Brown` near
  cliffs, sparse `Barrel`/`Tire` at road junctions; a few `Amb_DesertNatureWind*` /
  `Amb_WaterRiverLoop` ambient-sound objects.
- Object Dict boilerplate copied from retail objects (health/enabled/owner/uniqueID…).

## Skirmish support

`PolygonTriggers`: the river water area, `CombatZone` (center of map), and
`InnerPerimeterN`/`OuterPerimeterN` rectangles around each base (N = 1–4) so the
skirmish AI defends and attacks sensibly. `WaypointsList` links empty in v1.

## Deliverables

- `tools/prompt-to-map/maps/build_scorched_crossing.py` — deterministic builder;
  writes the `.map` plus a PNG preview.
- Installed to the game as `Maps\Scorched Crossing\Scorched Crossing.map`.
- v1 gate: loads and plays in vanilla Zero Hour; layout matches this spec.
  Polish (thumbnail TGA, texture blends, waypoint attack paths) iterates after
  Mike's playtest.
