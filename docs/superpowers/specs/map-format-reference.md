# Command & Conquer: Generals Zero Hour — `.map` File Format Reference

**Scope:** Binary layout of Zero Hour `.map` files, derived by reading EA's open-source
release (GPLv3, 2025) under `C:\Dev\CommandConquer\GeneralsMD\Code`. This is ground truth
for a Phase-0 Python reader/writer. Every non-obvious claim cites `file:line`.

All primary citations are to files under
`C:\Dev\CommandConquer\GeneralsMD\Code\` (paths below are relative to that root).

---

## 1. Overall file layout

A `.map` file is a **"chunky" container**: a name table (Table Of Contents) followed by a
flat stream of nested chunks. Optionally the *entire* file is wrapped in a compression
envelope; the game transparently decompresses before parsing.

```
+--------------------------------------------------------------+
| [optional 8-byte compression header + compressed payload]    |  (see §5)
+--------------------------------------------------------------+
                       | after decompression (or if never compressed) |
                       v
+--------------------------------------------------------------+
|  Table Of Contents (TOC)   — magic "CkMp" + name/id table    |  (§2)
+--------------------------------------------------------------+
|  Chunk stream — one or more top-level chunks, each possibly   |
|  containing nested sub-chunks                                 |  (§3, §6)
+--------------------------------------------------------------+
```

**Write order note.** The writer (`DataChunkOutput`) buffers all chunk *data* to a temp
file while writing, then on destruction emits the **TOC first**, then appends the buffered
chunk data (`DataChunk.cpp:251-276`). So in the final file the TOC always precedes the
chunk stream. The reader constructor reads the TOC, then records the position of the first
chunk (`DataChunk.cpp:584-595`).

**Byte order: little-endian.** Every scalar is written with a raw `fwrite` of the native
x86 type (`DataChunk.cpp:337-369`), so all multi-byte integers/floats are little-endian.

---

## 2. Table Of Contents (name table)

The TOC interns every chunk label **and every Dict key string** as a small integer id.
Written by `DataChunkTableOfContents::write` (`DataChunk.cpp:507-526`), read by
`::read` (`DataChunk.cpp:531-579`).

### 2.1 Binary layout

| Offset | Size | Type | Field | Notes |
|-------:|-----:|------|-------|-------|
| 0 | 4 | bytes | Magic `"CkMp"` | Literally `{'C','k','M','p'}` (`DataChunk.cpp:512`). "Chunky Map". No null. |
| 4 | 4 | Int32 (LE) | `count` | Number of name→id entries (`DataChunk.cpp:516`). |
| 8 | … | entries | symbol table | `count` entries, format below. |

Each entry (`DataChunk.cpp:519-525`):

| Size | Type | Field | Notes |
|-----:|------|-------|-------|
| 1 | UInt8 | `nameLen` | Length of the label string in bytes. |
| `nameLen` | bytes | `name` | ASCII label, **no null terminator** stored. |
| 4 | UInt32 (LE) | `id` | The integer id this name maps to. |

### 2.2 Semantics / gotchas for a writer

- **ids start at 1.** The allocator (`m_nextID`) initializes to 1 and increments; id 0 is
  never allocated (`DataChunk.cpp:424-428`, `482-504`). id 0 is used as a sentinel.
- **ids are assigned in first-use order** as chunks/keys are written, but the table is
  written **in reverse** (entries are *prepended* to a linked list — `DataChunk.cpp:497-498`).
  So on disk you typically see the highest id first. A reader must not assume any ordering;
  build a dict from `name→id` / `id→name` as you read.
- **The same table holds both chunk labels and Dict key names.** `writeDict` and
  `writeNameKey` call `m_contents.allocateID(keyname)` (`DataChunk.cpp:371-379`, `390`),
  so Dict keys share the id space with chunk labels. A Python writer must add every Dict key
  string to the TOC and reference it by id.
- **Validity check.** If the first 4 bytes are not `"CkMp"`, `read` bails without throwing
  and the file is treated as an old/legacy non-chunky format (`DataChunk.cpp:538-542`).
  `isValidFileType()` / `parse()` return false when the header wasn't a valid TOC
  (`DataChunk.cpp:575`, `638-640`, `716-719`). A valid TOC requires `count > 0` and not at EOF.

---

## 3. Chunk header & nesting

Written by `DataChunkOutput::openDataChunk` / `closeDataChunk`
(`DataChunk.cpp:278-335`); read by `DataChunkInput::openDataChunk`
(`DataChunk.cpp:721-753`).

### 3.1 Chunk header layout (10 bytes)

| Offset | Size | Type | Field | Notes |
|-------:|-----:|------|-------|-------|
| 0 | 4 | UInt32 (LE) | `id` | TOC id of the chunk label (`DataChunk.cpp:290`, `730`). |
| 4 | 2 | UInt16 (LE) | `version` | `DataChunkVersionType` = `unsigned short` (`DataChunk.h:38`, write `293`, read `734`). |
| 6 | 4 | Int32 (LE) | `dataSize` | Number of payload bytes that follow (`DataChunk.cpp:300-302`, `320-323`, `738`). |
| 10 | `dataSize` | bytes | payload | Primitives and/or nested sub-chunks. |

`dataSize` is computed as `here - filepos - sizeof(Int)` where `filepos` is the position
just after the version field (`DataChunk.cpp:296`, `320`). **It counts everything after the
header, including any nested sub-chunk headers and their data**, but not the 4-byte
`dataSize` field itself.

### 3.2 Nesting

- Sub-chunks are simply more chunk headers written inside a parent's payload. Example:
  `ObjectsList` contains a sequence of `Object` sub-chunks (`WHeightMapEdit.cpp:689-726`);
  `SidesList` contains a `PlayerScriptsList` sub-chunk (`SidesList.cpp:381`, `297`).
- The reader tracks `dataLeft` per open chunk. Reads from a child also decrement all parent
  chunks on the stack (`DataChunkInput::decrementDataLeft`, `DataChunk.cpp:847-857`).
- A parser dispatches sub-chunks by re-registering a parser scoped to the parent label, then
  calling `file.parse()` recursively (e.g. `WorldHeightMap.cpp:863-868`). Parser dispatch
  matches on **(label, parentLabel)**; `parentLabel` is `""` (empty) for top-level chunks
  (`DataChunk.cpp:660-685`; registration examples `WorldHeightMap.cpp:513-527`).
- `parse()` stops reading a chunk's children when fewer than `CHUNK_HEADER_BYTES` (=4)
  bytes remain (`DataChunk.h:176`, `DataChunk.cpp:648-652`). On close, the reader seeks past
  any unread remainder (`DataChunk.cpp:756-776`).

---

## 4. Primitive encodings

All from `DataChunkOutput` (`DataChunk.cpp:337-418`) and `DataChunkInput`
(`DataChunk.cpp:859-988`). Underlying C types: `Int`=int32, `Real`=float32, `Byte`=int8,
`UnsignedShort`=uint16, `UnsignedInt`=uint32, `WideChar`=uint16.

| Method | On-disk encoding | Cite |
|--------|------------------|------|
| `writeInt` / `readInt` | 4 bytes, signed int32 LE | `342-345`, `868-875` |
| `writeReal` / `readReal` | 4 bytes, IEEE-754 float32 LE | `337-340`, `859-866` |
| `writeByte` / `readByte` | 1 byte | `347-350`, `877-884` |
| `writeArrayOfBytes` / `readArrayOfBytes` | `len` raw bytes, no prefix | `352-355`, `886-891` |
| `writeAsciiString` / `readAsciiString` | UInt16 LE `len` + `len` bytes (**no null on disk**) | `357-362`, `952-969` |
| `writeUnicodeString` / `readUnicodeString` | UInt16 LE `len` (char count) + `len × 2` bytes (UTF-16LE, no null) | `364-369`, `971-988` |
| `writeDict` / `readDict` | see §4.2 | `381-418`, `907-950` |
| `writeNameKey` / `readNameKey` | Int32 `keyAndType` (see §4.1) | `371-379`, `893-905` |

**Strings:** the length prefix is a *character* count (bytes for ASCII, UTF-16 code units
for Unicode), not a byte count for Unicode. Max length 65535. No terminator is stored; the
reader appends its own null.

### 4.1 NameKey / "keyAndType" packing

A dict entry key is packed into one Int32 (`DataChunk.cpp:371-379`, `390-394`; unpack
`893-905`, `919-923`):

```
keyAndType = (TOC_id_of_key_name << 8) | (dataType & 0xFF)
```

- Low byte = the value's `Dict::DataType` (§4.2).
- Upper 24 bits = the TOC id of the key's *name string* (interned via `allocateID`).
- On read: `type = keyAndType & 0xFF`, `nameId = keyAndType >> 8`, then look up the string
  via the TOC and convert to a runtime NameKey.

### 4.2 Dict encoding

`Dict::DataType` values (`Common/Dict.h:74-81`):

| Value | Name | Value encoding |
|------:|------|----------------|
| -1 | `DICT_NONE` | (never serialized) |
| 0 | `DICT_BOOL` | 1 byte (0/1) |
| 1 | `DICT_INT` | Int32 |
| 2 | `DICT_REAL` | float32 |
| 3 | `DICT_ASCIISTRING` | AsciiString (uint16 len + bytes) |
| 4 | `DICT_UNICODESTRING` | UnicodeString (uint16 len + UTF-16LE) |

Dict on-disk layout (`DataChunk.cpp:381-418` / `907-950`):

| Size | Field |
|-----:|-------|
| 2 | UInt16 LE `pairCount` |
| … | `pairCount` pairs, each: Int32 `keyAndType` (§4.1) followed by the value encoded per the low-byte type |

A Python writer must, for every key it emits, ensure the key name string is in the TOC and
use its id in `keyAndType`.

---

## 5. Compression detection & envelope

Real implementation: `Libraries/Source/Compression/CompressionManager.cpp`. (The
`GameEngine/.../Compression.cpp` file is only perf-test scaffolding.)

### 5.1 Detection (`CompressionManager.cpp:103-137`)

`getCompressionType` inspects the **first 4 bytes**. A file is compressed iff one of these
magics matches; otherwise `COMPRESSION_NONE`:

| First 4 bytes | Compression |
|---------------|-------------|
| `"NOX\0"` | NoxLZH |
| `"ZL1\0"` … `"ZL9\0"` | zlib level 1–9 |
| `"EAB\0"` | EA BTree |
| `"EAH\0"` | EA Huffman |
| `"EAR\0"` | EA RefPack |

If `len < 8`, always `COMPRESSION_NONE` (`:105-106`). `isDataCompressed` = `type != NONE`
(`:91-95`).

### 5.2 Envelope (when compressed)

Compressed files have an **8-byte header** (`compressData`, `:193-280`):

| Offset | Size | Field |
|-------:|-----:|-------|
| 0 | 4 | magic (e.g. `"EAR\0"`) |
| 4 | 4 | Int32 LE **uncompressed size** |
| 8 | … | compressed payload |

`getUncompressedSize` returns `*(Int*)(mem+4)` for any recognized magic (`:166-191`).
`decompressData` strips the 8 bytes and dispatches by magic (`:282-349`).

### 5.3 Reading path

`CachedFileInputStream::open` (`DataChunk.cpp:53-103`) reads the whole file, then: if
`isDataCompressed`, allocate `getUncompressedSize` bytes and `decompressData`; else use the
buffer as-is. All later chunk parsing sees only decompressed bytes.

### 5.4 Confirmation: **uncompressed files have no wrapper**

An uncompressed `.map` is exactly `[CkMp TOC][chunk stream]` with **no prefix**. Because none
of the compression magics equals `"CkMp"`, `getCompressionType` returns `COMPRESSION_NONE`
and the bytes are parsed directly. WorldBuilder normally compresses on save (RefPack by
default via `getPreferredCompression`, `CompressionManager.cpp:97-100`), but its writer
falls back to writing the **raw uncompressed buffer** if compression returns 0
(`WorldBuilderDoc.cpp:253-276`). The engine reads both. **A Phase-0 writer may safely emit
uncompressed files** (start the file with `"CkMp"`).

---

## 6. Top-level chunks

Version constants are in `Common/MapReaderWriterInfo.h:34-60`. The canonical top-level set
registered by the game loader is in `WorldHeightMap.cpp:513-527` and `MapUtil.cpp:268-270`;
the writer that emits them is `WHeightMapEdit.cpp:581-793` plus the helper writers in
`SidesList.cpp`, `PolygonTrigger.cpp`, and `WorldBuilderDoc.cpp`.

**On-disk order emitted by WorldBuilder** (`WHeightMapEdit.cpp` + `WorldBuilderDoc.cpp`):
`HeightMapData`, `BlendTileData`, (`FUNKY_TILING` debug only), `WorldInfo`, `SidesList`,
`ObjectsList`, `PolygonTriggers`, `GlobalLighting`, `WaypointsList`. Parsers are
order-independent (dispatch is by label), **except** the two documented ordering
constraints: `WorldInfo` must precede the player/side chunk, and the side chunk must
precede `ObjectsList` (`WHeightMapEdit.cpp:678`, `685`).

### Top-level chunk summary

| Label | Current ver | Parent | Payload summary | Writer / Reader |
|-------|------------:|--------|-----------------|-----------------|
| `HeightMapData` | 4 | "" | terrain elevation grid | §6.1 |
| `BlendTileData` | 8 | "" | texture/tile/blend/cliff data | §6.2 |
| `WorldInfo` | 1 | "" | single Dict of global map settings | §6.3 |
| `SidesList` | 3 | "" | players/sides + build lists + teams + scripts | §6.4 |
| `ObjectsList` | 3 | "" | container of `Object` sub-chunks | §6.5 |
| `Object` | 3 | `ObjectsList` | one placed object | §6.5 |
| `PolygonTriggers` | 4 | "" | polygon areas / water / rivers | §6.6 |
| `GlobalLighting` | 3 | "" | time-of-day lighting + shadow color | §6.7 |
| `WaypointsList` | 1 | "" | waypoint link pairs | §6.8 |
| `MapPreview` | 1 | "" | (see §6.9 — normally NOT in the .map) | §6.9 |
| `PlayerScriptsList` | — | `SidesList`/"" | script data (nested) | §6.10 |
| `ScriptsPlayers` / `ScriptTeams` | 2 / 1 | "" | only in `.scb`/`.sav`, not standard `.map` | §6.10 |
| `FUNKY_TILING` | 1 | "" | debug-build only (`#ifdef EVAL_TILING_MODES`) | — |

---

### 6.1 `HeightMapData` (version 4)

Writer `WHeightMapEdit.cpp:587-608`; reader `WorldHeightMap.cpp:890-942` (and size-only
variant `964-1007`).

Payload (v4):

| Order | Type | Field | Notes |
|------:|------|-------|-------|
| 1 | Int32 | `width` | grid columns (`m_width`) |
| 2 | Int32 | `height` | grid rows (`m_height`) |
| 3 | Int32 | `borderSize` | v≥3 only; playable-area inset (`:894-898`) |
| 4 | Int32 | `numBoundaries` | v≥4 only (`:900-906`) |
| 5 | `numBoundaries ×` (Int32 `x`, Int32 `y`) | boundary corners | top-right of each playable region; lower-left implied (0,0) |
| 6 | Int32 | `dataSize` | must equal `width*height` else `ERROR_CORRUPT_FILE_FORMAT` (`:913-917`) |
| 7 | `dataSize` bytes | `heightData` | one **UInt8** height per cell, row-major | 

Height values are raw bytes; world elevation = `byte * MAP_HEIGHT_SCALE`. Versions 1/2
predate `borderSize`; version 1 also halves the grid on load (`:930-939`).

### 6.2 `BlendTileData` (version 8)

Writer `WHeightMapEdit.cpp:611-669`; reader `WorldHeightMap.cpp:1071-1228`. All array
counts are `dataSize = width*height` cells.

| Order | Type | Field | Ver gate | Notes |
|------:|------|-------|----------|-------|
| 1 | Int32 | `len` | — | must equal `dataSize` (`:1074-1077`) |
| 2 | `len × Int16` | `tileNdxes` | — | base texture tile index per cell |
| 3 | `len × Int16` | `blendTileNdxes` | — | first blend layer index per cell |
| 4 | `len × Int16` | `extraBlendTileNdxes` | v≥6 (`:1097`) | second blend layer (3-way blends) |
| 5 | `len × Int16` | `cliffInfoNdxes` | v≥5 (`:1104`) | cliff-uv index per cell |
| 6 | `height × ceil(width/8)` bytes | `cellCliffState` | v≥7 (`:1107-1119`) | 1 bit/cell passability. **v7 quirk:** width computed as `(width+1)/8` (buggy); v8 uses `(width+7)/8`. |
| 7 | Int32 | `numBitmapTiles` | — | |
| 8 | Int32 | `numBlendedTiles` | — | index 0 reserved; entries written for 1..n-1 |
| 9 | Int32 | `numCliffInfo` | v≥5 (`:1127`) | index 0 reserved |
| 10 | Int32 | `numTextureClasses` | — | |
| 11 | `numTextureClasses ×` TextureClass | — | see below |
| 12 | Int32 | `numEdgeTiles` | v≥4 (`:1150-1152`) | |
| 13 | Int32 | `numEdgeTextureClasses` | v≥4 | |
| 14 | `numEdgeTextureClasses ×` EdgeTextureClass | v≥4 | see below |
| 15 | `(numBlendedTiles-1) ×` BlendEntry | — | see below (`:1162-1191`) |
| 16 | `(numCliffInfo-1) ×` CliffInfo | v≥5 (`:1192-1206`) | see below |

**TextureClass** (`:625-631` / `:1135-1147`): Int32 `firstTile`, Int32 `numTiles`,
Int32 `width`, Int32 `0` (legacy/reserved — written as 0, read and discarded),
AsciiString `name`.

**EdgeTextureClass** (`:637-642` / `:1153-1160`): Int32 `firstTile`, Int32 `numTiles`,
Int32 `width`, AsciiString `name`. (No reserved int.)

**BlendEntry** (`:644-655` / `:1162-1191`): Int32 `blendNdx`, Byte `horiz`, Byte `vert`,
Byte `rightDiagonal`, Byte `leftDiagonal`, Byte `inverted`, Byte `longDiagonal` (v≥3),
Int32 `customBlendEdgeClass` (v≥4), Int32 `flag` (**must equal `FLAG_VAL`** = sentinel, else
corrupt — `:1186-1190`).

**CliffInfo** (`:656-668` / `:1193-1205`): Int32 `tileIndex`, then 8× float32
`u0,v0,u1,v1,u2,v2,u3,v3`, Byte `flip`, Byte `mutant`.

### 6.3 `WorldInfo` (version 1)

Writer `WHeightMapEdit.cpp:680-682`; reader `WorldHeightMap.cpp:763-773`.
Payload: a **single Dict** (§4.2). Holds global settings (weather, compression preference,
etc.). Keys are runtime `NameKey`s such as `weather`, `compression`. Must be written before
the sides chunk (weather is stashed into it first, `:679`).

### 6.4 `SidesList` (version 3)

Writer `SidesList.cpp:329-388`; reader `:243-319`. This chunk is EA's "players + teams".

Payload:

| Order | Type | Field |
|------:|------|-------|
| 1 | Int32 | `numSides` |
| 2 | `numSides ×` Side | see below |
| 3 | Int32 | `numTeams` (v≥2) |
| 4 | `numTeams ×` Dict | one team Dict each (v≥2) |
| 5 | nested sub-chunk | `PlayerScriptsList` (per-player scripts) |

**Side** (`:339-368` / `:257-284`):
- Dict `sideDict` (player properties — name, faction, color, etc.)
- Int32 `buildCount`
- `buildCount ×` BuildListInfo:
  - AsciiString `buildingName`
  - AsciiString `templateName`
  - float32 `x`, float32 `y`, float32 `z`
  - float32 `angle`
  - Byte `initiallyBuilt`
  - Int32 `numRebuilds`
  - *(v≥3 only)* AsciiString `script`, Int32 `health`, Byte `whiner`, Byte `unsellable`, Byte `repairable`

The reader forces build-list `z` to 0 (`:270`). Player start positions are **not** in this
chunk — they are waypoints named `Player_N_Start` (see §6.8).

### 6.5 `ObjectsList` (v3) and `Object` (v3)

Container: `ObjectsList` payload is a sequence of `Object` sub-chunks
(`WHeightMapEdit.cpp:689-726`; dispatch `WorldHeightMap.cpp:863-868`).

**`Object` payload** (writer `WHeightMapEdit.cpp:694-724`; reader `WorldHeightMap.cpp:1251-1274`):

| Order | Type | Field | Notes |
|------:|------|-------|-------|
| 1 | float32 | `x` | |
| 2 | float32 | `y` | |
| 3 | float32 | `z` | forced to 0 for v≤2 (`:1263-1265`) |
| 4 | float32 | `angle` | radians |
| 5 | Int32 | `flags` | object flag bitfield |
| 6 | AsciiString | `name` | thing-template name |
| 7 | Dict | `properties` | v≥2 only (`readDict` gated on `version>=K_OBJECTS_VERSION_2`, `:1271-1274`) |

Special object kinds are detected from Dict keys after load: waypoints
(`waypointID` is DICT_INT), lights (`lightHeightAboveTerrain` is DICT_REAL), scorch marks
(`scorchType` is DICT_INT) — `WorldHeightMap.cpp:1289-1296`. Waypoint objects also carry
`waypointName`, `waypointPathLabel1..3`, `waypointPathBiDirectional` in their Dict
(`TerrainLogic.cpp:1361-1365`).

### 6.6 `PolygonTriggers` (version 4)

Writer `PolygonTrigger.cpp:240-268`; reader `:150-231` (registration is
`ParsePolygonTriggersDataChunk`).

| Order | Type | Field |
|------:|------|-------|
| 1 | Int32 | `count` (number of triggers) |
| … | `count ×` Trigger | |

**Trigger** (`:251-264` / `:153-188`):
- AsciiString `triggerName`
- AsciiString `layerName` *(v≥4 only)*
- Int32 `triggerID`
- Byte `isWaterArea` *(v≥2 only)*
- Byte `isRiver` *(v≥3 only)*
- Int32 `riverStart` *(v≥3 only)*
- Int32 `numPoints`
- `numPoints ×` (Int32 `x`, Int32 `y`, Int32 `z`) — **integer** world coords (`ICoord3D`)

Triggers with <2 points are dropped on read (`:189-194`).

### 6.7 `GlobalLighting` (version 3)

Writer `WHeightMapEdit.cpp:732-782`; reader `WorldHeightMap.cpp:782-853`.

| Order | Type | Field |
|------:|------|-------|
| 1 | Int32 | `timeOfDay` (enum; 4 slots span "first".."last") |
| 2 | 4 × TimeOfDayBlock | one per time-of-day (morning/afternoon/evening/night) |
| 3 | Int32 | `shadowColor` (packed RGBA; only if bytes remain — `:846-851`) |

**Each TimeOfDayBlock** (`:735-778` / `:796-844`), all values float32:
- Terrain light[0]: ambient `r,g,b`, diffuse `r,g,b`, lightPos `x,y,z` (9 floats)
- Object light[0]: ambient `r,g,b`, diffuse `r,g,b`, lightPos `x,y,z` (9 floats)
- *(v≥2)* Object lights[1..2]: 2 × 9 floats
- *(v≥3)* Terrain lights[1..2]: 2 × 9 floats

`MAX_GLOBAL_LIGHTS` = 3. Note the writer's per-block loop order differs from the reader's
gating logic, but both agree on the version-gated field presence above. A writer targeting
v3 must emit terrain[0], object[0], object[1], object[2], terrain[1], terrain[2] for each of
the 4 blocks (matching reader order `:796-844`), then the trailing Int32 shadowColor.

### 6.8 `WaypointsList` (version 1)

Writer `WorldBuilderDoc.cpp:302-308`; reader `TerrainLogic.cpp:1338-1349`.

| Order | Type | Field |
|------:|------|-------|
| 1 | Int32 | `numWaypointLinks` |
| … | `numWaypointLinks ×` (Int32 `waypoint1`, Int32 `waypoint2`) | id→id links |

**Waypoints themselves are `Object` entries**, not stored here. This chunk only records the
directed links between waypoint ids. Player start positions are waypoints (Objects with a
`waypointID` Dict key) named `Player_1_Start`, etc.

### 6.9 `MapPreview` (version 1)

The in-`.map` `MapPreview` chunk writer is **commented out** (`MapPreview.cpp:81-96`); the
preview is instead saved as a sibling `.tga`. A `MapPreview` chunk parser does exist for the
map-cache path (`MapUtil.cpp:1267`, `parseMapPreviewChunk`). If present, payload would be:
Int32 `width`, Int32 `height`, then `width*height` × Int32 ARGB pixels. **Treat as optional
and typically absent from real `.map` files.** (Open question — see §7.)

### 6.10 Script chunks (nested)

`PlayerScriptsList` (nested under `SidesList` or top-level) contains per-player `ScriptList`
sub-chunks, which contain `Script`, `ScriptGroup`, `OrCondition`, `Condition`,
`ScriptAction`, `ScriptActionFalse` sub-chunks. Writers/readers live in
`GameEngine/Source/GameLogic/ScriptEngine/Scripts.cpp` (e.g. `:585-628`, `:871`, `:1237`,
`:1451`, `:1663`, `:2423`, `:2660`). Versions: `PlayerScriptsList`=1, `ScriptList`=1,
`ScriptGroup`=2, `Script`=2, `OrCondition`=1, `Condition`=4, `ScriptAction`=2.
`ScriptsPlayers` (v2) and `ScriptTeams` (v1) appear in standalone `.scb`/skirmish-script
files, not the standard `.map` (`SidesList.cpp:431-476`, `526-528`). Full script internals
are out of scope for Phase-0 terrain/object work; a reader can skip these sub-chunks by
honoring `dataSize`.

---

## 7. Open questions / not fully determined from source

1. **`MapPreview` chunk in-file presence.** The writer is commented out and previews go to a
   `.tga`. A parser exists (`MapUtil.cpp:1267`) but I did not find a live writer emitting the
   chunk into a `.map`. Whether any shipped `.map` embeds it is unverified — validate against
   real files.
2. **Exact `flags` bitfield for `Object`** and the exact set/meaning of `WorldInfo` and side
   Dict keys are runtime NameKeys; the *encoding* is fully specified (Dict), but the key
   catalog (names + expected types) must be gathered from `TheKey_*` definitions / real maps.
3. **`FLAG_VAL` sentinel numeric value** (BlendEntry field 17) — defined via a macro in
   `WorldHeightMap`/edit headers; confirm the constant before writing v8 blend data. It must
   round-trip exactly (reader throws otherwise, `:1186-1190`).
4. **`shadowColor` packing** in `GlobalLighting` is read as a raw UInt32 (`:847`); its ARGB
   channel order was not chased down.
5. **Legacy versions.** This spec targets current versions (HeightMap 4, BlendTile 8, Objects
   3, Triggers 4, Sides 3, Lighting 3). Older-versioned chunks are still readable per the
   version gates cited, but a writer should emit current versions only.
6. **`writeDict`/nested-chunk `dataSize` and the temp-file writer** mean a Python writer must
   compute each chunk's `dataSize` after serializing its (possibly nested) body — i.e.
   serialize body to a buffer, then backpatch the 4-byte size, exactly as
   `closeDataChunk` backpatches (`DataChunk.cpp:305-335`).

---

## 8. Minimal writer checklist (Python, uncompressed)

1. Maintain a TOC: `name→id` map, ids from 1, in first-use order. Register a chunk label /
   Dict key the first time you emit it.
2. Serialize each chunk body to a bytes buffer (recursively for nested chunks), then prepend
   the 10-byte header `id(u32) + version(u16) + len(body)(i32)`.
3. Emit the file as: `"CkMp"` + `count(i32)` + for each entry `len(u8)+name+id(u32)` + the
   concatenated chunk stream. **TOC first, then chunks.**
4. Everything little-endian. Strings = `u16 length` + raw bytes (ASCII) / UTF-16LE units.
5. Do **not** add any compression wrapper — the loader detects `"CkMp"` as
   `COMPRESSION_NONE` and parses directly (§5.4).
