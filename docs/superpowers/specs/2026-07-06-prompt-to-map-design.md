# Prompt-to-Map for Command & Conquer: Generals — Zero Hour

**Status:** Design (approved to draft)
**Date:** 2026-07-06
**Owner:** Mike (gyrow32)
**Companion doc:** [`map-format-reference.md`](./map-format-reference.md) — the byte-level `.map` format ground truth extracted from EA's source.

---

## 1. Summary

Build a small **Python toolkit that reads and writes Generals: Zero Hour `.map` files**, so that Claude (in a Claude Code session) can turn a natural-language prompt into a **playable, and eventually competitively balanced, game map**.

The user describes a map in plain English. Claude designs it — terrain, resources, structures, player start positions, balance — assembles it with the toolkit, saves a real `.map` file into the game's maps folder, and the user opens it in the already-installed **WorldBuilder.exe** or loads it directly in **Skirmish**.

**No decompilation is involved.** EA open-sourced the actual game and WorldBuilder source in 2025 (`electronicarts/CnC_Generals_Zero_Hour`, forked to `gyrow32/CnC_Generals_Zero_Hour`, cloned into this repo). That source is used as the **rulebook** for the file format — we mirror EA's own read/write code rather than reverse-engineering a binary.

## 2. Goals & Non-Goals

### Goals
- Turn a text prompt into a valid `.map` file the retail game loads without errors.
- Reach **competitive/balanced** maps as the north star: symmetric spawns, fair resource distances, sensible chokepoints.
- Keep a tight, trustworthy feedback loop: generate → inspect in WorldBuilder → play in Skirmish → improve.
- Be usable **in-session** — Claude is the generation engine; there is no separate AI service to build or call.

### Non-Goals (YAGNI)
- **No GUI / web app.** Interaction happens in the Claude Code session.
- **No external AI API.** Claude does the design reasoning directly.
- **No modification of WorldBuilder or the game.** We only produce files they already know how to read.
- **No writing compressed maps.** We always write uncompressed (the game auto-detects and reads them). Compression support is read-only, and only to validate against real retail maps.
- **No campaign/scripting-heavy scenarios** in the initial scope — skirmish/multiplayer-style maps first. Rich trigger scripting is a possible later extension, not part of this design.

## 3. Users & Success Criteria

**Primary user:** Mike, working with Claude in a Claude Code session, for fun and experimentation.

**Success looks like:**
1. **Phase 0 done:** we can read a real retail map and write it back byte-identically (at the decompressed-chunk level). This proves the writer is correct.
2. **Phase 1 done:** "make me a small 1v1 map" produces a file that loads in Skirmish and is playable.
3. **Phase 2 done:** maps have real terrain variety (hills, water, cliffs), textures, resources, and neutral structures.
4. **Phase 3 done:** "make me a balanced 2v2 map with a central resource contest" produces a symmetric, fair, competitive-feeling map.

## 4. Background: how a Generals map is stored

A `.map` file is a **chunked binary container** (EA's `DataChunk` format). Conceptually it is a box of labeled compartments; each compartment ("chunk") has a name, a version number, a size, and a payload, and chunks can nest. The important top-level compartments are roughly:

- **HeightMapData** — the terrain elevation grid (width × height of height bytes) plus border size.
- **BlendTileData** — which ground textures are painted where, and how they blend.
- **ObjectsList / Object** — every placed thing (trees, buildings, units, resources, technicals) with a position, facing angle, and a properties dictionary.
- **WaypointsList** — holds only the *links* between waypoints (id → id pairs). **Important:** the actual waypoints — including **player start positions** (`Player_1_Start`, etc.) — are stored as **`Object` entries** in `ObjectsList`, identified by a `waypointID` / `Player_N_Start` key in their properties dictionary. (Confirmed against source + real maps during the Phase-0 spike.)
- **PolygonTriggers** — named polygonal areas used for regions, water bodies, and triggers.
- **SidesList / PlayerList** — the players/sides defined for the map and their properties.
- **WorldInfo** — a dictionary of global map settings (name, description, weather, etc.).
- **GlobalLighting** — sun/terrain lighting.
- **MapPreview** (optional) — the little preview image shown in menus.

> The exact chunk names, versions, and byte layouts are documented in the companion [`map-format-reference.md`](./map-format-reference.md). This design intentionally defers those specifics to that reference so the two stay in sync.

**Compression:** map files may be RefPack/EA-compressed, but the loader (`DataChunkInput`) auto-detects compression and transparently decompresses. Therefore **we always write plain uncompressed files** and the game reads them fine. We implement decompression only to read real retail maps for round-trip testing.

## 5. Architecture

Three layers, stacked, each independently understandable and testable.

```
        ┌─────────────────────────────────────────────┐
Prompt ─▶│  Layer 3: The Designer  (generator/)         │  ← "competitive/balanced" lives here
        │  terrain shaping · symmetry · resources ·     │
        │  start spacing · passability · validation     │
        └───────────────────────┬─────────────────────┘
                                │ builds a Map object
        ┌───────────────────────▼─────────────────────┐
        │  Layer 2: The Map model  (mapfile.py)         │  ← in-memory Map ↔ chunks
        │  Map, HeightMap, MapObject, Waypoint,         │
        │  PolygonTrigger, Player/Side, WorldInfo       │
        └───────────────────────┬─────────────────────┘
                                │ serialize / parse
        ┌───────────────────────▼─────────────────────┐
        │  Layer 1: The File engine                     │  ← exact byte fidelity
        │  datachunk.py (container)  ·  refpack.py       │
        │  (read-only decompression)                    │
        └───────────────────────────────────────────────┘
                                │ .map bytes
                                ▼
             Documents\...\Zero Hour Data\Maps\<Name>\<Name>.map
```

### Layer 1 — The file engine
- **`datachunk.py`** — a faithful port of EA's `DataChunkInput`/`DataChunkOutput`. Handles the file header, the chunk **name table** (label interning), chunk headers (name index + version + size), nesting, and every primitive encoder/decoder (int, real/float, byte/bool, ASCII string, Unicode string, dict, RGB(A) color, Coord3D, ICoord2D, Region3D, …). This is the layer that must be **byte-exact**; everything else rests on it.
- **`refpack.py`** — read-only EA RefPack decompression, plus the compression-detection check, used solely to open real compressed retail maps during testing.

### Layer 2 — The Map model
- **`mapfile.py`** — a high-level object model of a map and the code that (de)serializes it to/from chunks via Layer 1:
  - `Map` (top-level: holds everything below)
  - `HeightMap` (grid of elevations + border)
  - `BlendTileData` / texture layer
  - `MapObject` (position, angle, type name, properties dict)
  - `Waypoint` (incl. player starts)
  - `PolygonTrigger` (areas/water)
  - `Player` / `Side`
  - `WorldInfo`, `GlobalLighting`, optional `MapPreview`
  - Each class knows which chunk(s) it reads from and writes to, mirroring WorldBuilder's save order.

### Layer 3 — The Designer (generator)
Where map *design intelligence* lives. Pure Python that produces a `Map` object; grows across phases:
- **Terrain shaping** — procedural heightfields (flat, rolling hills, mesas/cliffs, valleys), plus water bodies via polygon triggers.
- **Texture painting** — choose and blend ground textures to match terrain (grass, dirt, rock, sand, water edges).
- **Content placement** — supply docks/resources, neutral structures, civilian buildings, foliage, roads.
- **Player starts** — place `Player_N_Start` waypoints with spacing rules.
- **Balance rules (Phase 3)** — symmetry/mirroring so spawns are fair, equalized resource distances, chokepoint shaping, passability checks.
- **`validate(map)`** — pre-save invariant checks (see §7).

### Workflow / entry point
- **`cli.py`** (thin) — Claude invokes it to serialize a `Map` and write it into the correct game folder. In practice Claude constructs the `Map` in Python (via the generator helpers) and calls save; the CLI exists so a generation run is a single reproducible command with the map spec as input (e.g. a small JSON/py describing the intent), and so runs are logged.

## 6. Data flow (one generation)

1. **Prompt** — user: "small 1v1 desert map, two bases across a dry riverbed, oil derricks in the middle."
2. **Design** — Claude reasons about layout, size, symmetry, resource placement.
3. **Assemble** — Claude calls generator helpers to build a `Map`: heightmap, textures, objects, two `Player_Start` waypoints, water/riverbed polygon.
4. **Validate** — `validate(map)` checks invariants; fails loudly with a clear message if something's off.
5. **Serialize** — `mapfile.py` → `datachunk.py` → uncompressed `.map` bytes.
6. **Save** — written to `Documents\Command and Conquer Generals Zero Hour Data\Maps\<Name>\<Name>.map` (each map lives in its own folder, matching how the game expects user maps).
7. **Verify** — user opens it in WorldBuilder.exe (visual) and/or loads Skirmish (playable). Feedback → Claude iterates.

## 7. Correctness, validation & error handling

Correctness is the heart of this project, so it gets three overlapping guarantees:

1. **Always write uncompressed.** Removes an entire class of compression bugs; the game handles it.
2. **Round-trip guarantee (the core test):**
   - `parse(serialize(map)) == map` for maps we build (in-memory equality).
   - `serialize(parse(real_map))` reproduces the same **decompressed chunk stream** as the original real map. If a real map is compressed, we decompress both sides and compare chunk-for-chunk. Any chunk we don't yet model shows up immediately as a diff.
3. **Pre-save validator** — before writing, check invariants and refuse to save an invalid map with a human-readable error:
   - Heightmap dimensions and border are valid for the engine.
   - Every declared player has a corresponding `Player_N_Start` waypoint.
   - Every object position is within map bounds.
   - Required chunks are present and in the expected order/version.
   - No two start positions absurdly close; starts are on passable ground.

**Error philosophy:** fail early and loudly in Python (bad map never reaches the game). Distinguish *malformed* (validator/round-trip failure → our bug, block the save) from *unbalanced* (design quality → warn, allow, iterate).

## 8. Testing strategy

- **Fixtures:** extract several real maps from the game's `.big` archives (e.g. official skirmish maps) into `tests/fixtures/` for use as ground truth.
- **Round-trip tests (Phase 0 gate):** for each fixture, decompress → parse → serialize → compare chunk streams byte-for-byte. Must be green before any generation work.
- **Unit tests:** each primitive encoder/decoder (string length prefixes, float encoding, dict format, coords) tested against known byte sequences taken from the source's documented layout.
- **Generation smoke tests:** generated maps pass `validate()` and re-parse cleanly.
- **Manual acceptance:** open generated maps in WorldBuilder.exe; load in Skirmish. Recorded per phase.

## 9. Phased delivery

Each phase ends in something verifiable/playable before the next begins.

### Phase 0 — Foundation & recon *(make-or-break; no generation yet)*
- Extract sample maps from `.big` archives → `tests/fixtures/`.
- Finalize [`map-format-reference.md`](./map-format-reference.md) from the source.
- Implement `datachunk.py` (+ `refpack.py` decompression).
- Implement `mapfile.py` enough to parse the fixtures.
- **Exit gate:** byte-perfect round-trip on ≥1 real map (ideally several), tests green.

### Phase 1 — First playable map
- Minimal generator: simple/flat terrain, a handful of objects, two `Player_Start` waypoints, minimal `WorldInfo`/`SidesList`.
- Save into the game maps folder.
- **Exit gate:** the map loads in WorldBuilder and plays a 1v1 Skirmish.

### Phase 2 — Real terrain & content
- Heightmap shaping (hills, cliffs, valleys), water via polygon triggers.
- Texture selection + blending.
- Resource placement (supply docks/derricks), neutral/civilian structures, roads, foliage.
- Support for N player starts (up to 8).
- **Exit gate:** varied, resource-rich, good-looking maps that play well.

### Phase 3 — Competitive balance
- Symmetry/mirroring engine (rotational + reflective) so spawns are provably fair.
- Equalized resource distances, chokepoint shaping, start-spacing rules.
- Passability validation (each start can reach resources and enemies).
- **Exit gate:** "balanced 2v2 with central contest" yields a symmetric, fair, competitive map.

## 10. Tech choices

- **Language: Python.** Best fit for binary formats (`struct`), no build step, runs directly on Windows in-session. (The C++ game/source stays untouched; we only *read* it as reference.)
- **Layout (proposed):**
  ```
  tools/prompt-to-map/
    cncmap/
      datachunk.py
      refpack.py
      mapfile.py
      validate.py
    generator/
      terrain.py
      textures.py
      content.py
      balance.py
    cli.py
    tests/
      fixtures/
      test_roundtrip.py
      test_primitives.py
      test_generation.py
  ```
- **Dependencies:** standard library only if feasible (`struct`, `zlib` not applicable — RefPack is custom). Avoid heavy deps.

## 11. Risks & open questions (resolved in Phase 0)

| Risk | Mitigation |
|---|---|
| A chunk we didn't model / wrong version | Round-trip diff surfaces it immediately against real maps. |
| RefPack decompression fidelity | Only needed for reading; verify by decompressing a known map and checking uncompressed size matches the header. |
| WorldBuilder accepts maps the game rejects (or vice versa) | Test in **both** for each phase. |
| `.big` extraction | Use the documented BIG archive format (or an existing extractor) to pull fixtures; read-only. |
| Map folder / naming conventions the game expects | Confirm the `Maps\<Name>\<Name>.map` layout with a known-good manual save from WorldBuilder. |

## 12. Out of scope / possible future work
- Rich AI-scripted scenarios and campaign triggers.
- A GUI or preview renderer outside WorldBuilder.
- Writing compressed maps.
- Auto-generating minimap/preview art beyond what the format needs.

## 13. Phase-0 spike results — 2026-07-06 (feasibility PROVEN)

An overnight read-only spike (throwaway code in `tools/prompt-to-map/spike/`, kept for reference) validated the riskiest assumptions **against real retail maps**, not just the source:

**What was proven:**
1. **Fixtures obtained.** `big_extract.py` reads the EA `.BIG` archive format and pulled real maps out of the game's `MapsZH.big` (116 maps available) into `tools/prompt-to-map/tests/fixtures/`. BIG layout confirmed: `"BIGF"` magic, archive size little-endian, entry count + index size big-endian, per-entry `{offset BE, size BE, NUL-terminated name}`.
2. **Compression decoded.** Real maps are `EAR\0`-wrapped **EA RefPack**. `refpack.py` decompresses them and the output length matches the header's stated size **exactly** (e.g. Hovercraft: 17,341 → 1,197,979 bytes), with decompressed magic `CkMp`. Confirms the spec's plan: write uncompressed, decompress only for round-trip reads.
3. **Container format parsed.** `datachunk_dump.py` parses the `CkMp` TOC (name table) and walks the chunk tree of real maps with **zero desync** — it consumes the entire stream, boundaries all line up. Verified on 3 maps including a 752-object gameplay map.
4. **Chunk versions match the reference exactly:** `HeightMapData` v4, `BlendTileData` v8, `WorldInfo` v1, `SidesList` v3, `ObjectsList`/`Object` v3, `PolygonTriggers` v4, `GlobalLighting` v3, `WaypointsList` v1.

**What this de-risks:** the entire *reading* half of the round-trip (TOC, chunk headers, compression, little-endianness, nesting) is confirmed correct. Remaining Phase-0 work is the *writing* half + byte-exact round-trip, plus decoding the per-chunk payloads (heightmap array, Dict, object fields) — all now low-uncertainty because we can read real examples to compare against.

**Refined open questions (down from the original list):**
- Exact `HeightMapData` payload layout (border/boundary fields before the height byte array) — read from a fixture and cross-check vs `WorldHeightMap.cpp`.
- `Dict` and `Object` field order for a full parse (research doc §ObjectsList has the layout; verify against fixture bytes).
- `FLAG_VAL` constant, `shadowColor` channel order, whether any real map embeds `MapPreview` (per research doc §7 — minor).
- Confirm the game accepts an uncompressed file we author (Phase 1 acceptance test in WorldBuilder + Skirmish).

> **Bottom line:** nothing surprising or blocking turned up. The approach in this spec is sound and the hardest unknown (can we even read the real format?) is now answered: **yes.**
