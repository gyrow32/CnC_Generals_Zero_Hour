# NEXT SESSION — CommandConquer / prompt-to-map

_Last updated: 2026-07-07 late night (Fable close-out session)_

## TL;DR for Mike ☕
The whole pipeline is REAL now. Three Claude-made maps are installed and show up
in Skirmish → Unofficial Maps, each with its own minimap thumbnail:

| Map | What it is |
| --- | --- |
| **Scorched Crossing** | The father-son 4-player map, **v2 "high roads"** from your red-line sketch: hill-arms flank the center road, stacked bridge X over a border-to-border river, organically sculpted terrain. |
| **Panorama Pass** | First widescreen 1v1 (420×250): central ridge cut by north pass / canyon road / south pass. Built to iterate on together in WorldBuilder. |
| **Claude Alpine** | The polished showcase (patched retail Alpine Assault). |

**Your move: launch vanilla Zero Hour (`Generals.exe`), play Scorched Crossing v2,
and red-line what you want different.** Regeneration takes seconds.

## What the late-night session did (2026-07-07, after the strike was cut off)
1. **Recovered the interrupted work** — the v2 Scorched rework + new Panorama Pass
   builder were sitting uncommitted. Verified: 37 engine tests pass, both builders
   are deterministic and byte-match the installed maps. Committed (`bde4669`).
2. **Built `spike/make_thumbnail.py`** (`8d3b581`) — clean 128×128 minimap TGA from
   any .map (no debug overlay, playable-area crop, retail TGA layout, north-up).
   Generated + installed thumbnails for Panorama Pass (had none) and Scorched v2.
3. **Executed the polish/cleanup doc** (SESSION-POLISH-MAP.md, now deleted as done):
   test litter is out of both Maps folders. Not deleted — **moved to
   `_map-quarantine-2026-07-07`** folders next to each Maps folder (OneDrive +
   native Documents). Empty them whenever you're happy.
4. Checked the name situation: none of our three maps carry a `MAP:` name tag, so
   they list by filename — no `MISSING:` issue, no map.str needed.

## ⏸️ Waiting on YOU
- **Playtest** Scorched Crossing v2 + Panorama Pass in vanilla ZH (2 min each):
  clean names + thumbnails in the list, maps load, bridges/ramps feel right.
- Feedback → next iteration (say it in WorldBuilder terms or plain English;
  the cnc-map-master skill translates).

## Next options (pick by mood)
1. Iterate Scorched v2 / Panorama Pass from your playtest notes.
2. New map from a prompt — the generate path is proven end-to-end now.
3. The "build our own Zero Hour" plan (`ce1ddbc`, docs/) for map testing & editing.

## Repo state
- Branch `prompt-to-map`, clean tree, all local — **nothing pushed to GitHub**.
- Latest: `8d3b581` (thumbnail tool) ← `bde4669` (v2 + Panorama) ← `ce1ddbc` (own-ZH plan).
- Gotchas that cost time before: bridges >~500wu break (keep feet on flats at the
  shortest crossing); always include a map-wide WaterTable trigger; GeneralsOnline's
  EAC client never lists local custom maps — vanilla ZH is the test bed.
