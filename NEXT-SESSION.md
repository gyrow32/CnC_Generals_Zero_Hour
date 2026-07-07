# NEXT SESSION — CommandConquer / prompt-to-map

_Last updated: 2026-07-06 (overnight autonomous session)_

## TL;DR for Mike ☕
You asked: decompile WorldBuilder so Claude can make maps from prompts.
Reality is **better than that** — no decompiling needed. EA open-sourced the real code,
and overnight I **proved the whole approach works** by reading real retail maps end-to-end.
Everything's written up and committed locally. **Your move: read the spec, then say "go"
and I'll build it.**

## What happened this session
1. Cloned your fork `gyrow32/CnC_Generals_Zero_Hour` into this repo; added `upstream` = EA's original.
2. Found your game + a runnable `WorldBuilder.exe` already installed (free map viewer — no build needed).
3. Brainstormed the idea into an **approved design**: Claude = the map-generation engine,
   writing real `.map` files. Target = competitive/balanced maps, delivered in 4 phases.
4. Wrote two docs (committed on branch `prompt-to-map`):
   - `docs/superpowers/specs/2026-07-06-prompt-to-map-design.md` — the design.
   - `docs/superpowers/specs/map-format-reference.md` — byte-level `.map` format, cited to source.
5. **Ran a Phase-0 feasibility spike and it worked** (`tools/prompt-to-map/spike/`):
   - Extracted 6 real Zero Hour maps from `MapsZH.big` (116 available).
   - Decompressed them (EA RefPack) — output sizes match headers **exactly**.
   - Parsed the chunk tree of 3 real maps (incl. a 752-object map) with **zero desync**;
     chunk versions match the reference exactly.
   - **Conclusion: reading the real map format is proven. Nothing surprising/blocking found.**

## ⏸️ Waiting on YOU (the one gate)
Per our process, before I write toolkit code you should **read the spec** and approve it.
Skim `2026-07-06-prompt-to-map-design.md` (esp. §5 architecture, §9 phases, §13 spike results).
Then just say **"looks good, go"** (or tell me what to change).

## ▶️ Next steps once you approve
1. I invoke the **writing-plans** skill → detailed Phase-0 implementation plan.
2. Build the real toolkit (`cncmap/`: `datachunk.py`, `refpack.py`, `mapfile.py`) — TDD,
   promoting the validated spike logic into tested modules.
3. **Phase-0 exit gate:** byte-perfect round-trip on a real map.
4. Phase 1: generate a first playable 1v1 map → load it in Skirmish. 🎉

## Notes / decisions
- Language: **Python** (best for binary formats; runs in-session; no build step).
- We **write uncompressed** maps (game auto-decompresses); RefPack is read-only for tests.
- **Gotcha:** player-start positions are stored as `Object` entries with `Player_N_Start`
  dict keys — NOT in `WaypointsList` (which only holds link pairs).
- Nothing was pushed to GitHub; branch `prompt-to-map` is local. Main is untouched.
- Fixtures (real maps) are gitignored — reproducible via `spike/big_extract.py`.
