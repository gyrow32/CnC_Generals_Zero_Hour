# prompt-to-map

Turn a natural-language prompt into a playable **Command & Conquer: Generals — Zero Hour** map.

Claude (in a Claude Code session) is the generation engine: it designs the map and writes a
real `.map` file the game loads. See the design spec:
[`docs/superpowers/specs/2026-07-06-prompt-to-map-design.md`](../../docs/superpowers/specs/2026-07-06-prompt-to-map-design.md)
and the byte-level format reference:
[`docs/superpowers/specs/map-format-reference.md`](../../docs/superpowers/specs/map-format-reference.md).

## Status

**Phase 0 (foundation) — in progress.** The `spike/` folder holds throwaway feasibility
proofs (already validated against real retail maps: BIG extraction, RefPack decompression,
DataChunk parsing). The real toolkit (`cncmap/`, `generator/`) is not built yet — it awaits
the implementation plan.

## Layout (planned)

```
cncmap/       file engine + map model (datachunk, refpack, mapfile, validate)
generator/    the "designer": terrain, textures, content, balance
tests/        round-trip tests against real fixtures
spike/        throwaway feasibility proofs (reference only, not the real toolkit)
```

## Reproduce the fixtures (needs the game installed locally)

```bash
# from repo root
MAPS="/c/Program Files/EA Games/Command and Conquer Generals Zero Hour/Command and Conquer Generals Zero Hour/MapsZH.big"
python tools/prompt-to-map/spike/big_extract.py "$MAPS" tools/prompt-to-map/tests/fixtures ".map" 6
python tools/prompt-to-map/spike/datachunk_dump.py tools/prompt-to-map/tests/fixtures/Hovercraft.map
```
