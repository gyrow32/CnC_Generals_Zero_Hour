# Plan — Build our own Zero Hour (for map testing & dev)

**Goal:** a playable Zero Hour + WorldBuilder we control, so we can test `cncmap`-generated
maps fast and (eventually) add debug output telling us *why* a map fails to load.
**Model note:** all of this is free Opus work. No Fable needed.
**Status:** researched 2026-07-07 (grounded, URLs below). Not started.

## The big realization: two paths, try the easy one first

The community project **TheSuperHackers/GeneralsGameCode**
(https://github.com/TheSuperHackers/GeneralsGameCode) modernizes EA's GPLv3 source and
publishes **prebuilt weekly release binaries**. So there are two ways in:

| Path | Effort | When to use |
|------|--------|-------------|
| **A. Download prebuilt binaries** | ~20 min | Try this FIRST |
| **B. Compile from source** (VS2022 + CMake + vcpkg) | 1–3 hrs first time | Only if we need to modify engine code |

We only fall to Path B when we actually want to change the game (e.g. add map-load debug
logging). For "test our maps in a modern exe," Path A is enough.

## Prerequisite (both paths): own retail Zero Hour

The projects modernize *code only* — no game art/audio/data. The exe needs the retail
`.big` archives. Mike already has a Zero Hour install (this is what GeneralsOnline runs
on), so this is likely already satisfied. If a clean install is ever needed, the wiki
recommends **C&C: The Ultimate Collection on Steam**.

- [ ] Confirm the retail install path (where `Generals.exe` + the `Data\*.big` live).

## Path A — Prebuilt binaries (do this first)

1. [ ] Open https://github.com/TheSuperHackers/GeneralsGameCode/releases — grab the latest
   `weekly-YYYY-MM-DD`. Check the release assets for Windows binaries incl. WorldBuilder.
2. [ ] Back up the retail game folder (copy the whole dir, or at least `Generals.exe` +
   any existing `Options.ini`).
3. [ ] Drop the modern game exe + `worldbuilder.exe` into the retail install folder
   (alongside the `.big` files — that's how the exe finds game data).
4. [ ] Launch the modern exe. Verify it reaches the main menu and reads game data.
5. [ ] Launch WorldBuilder. Open a `cncmap`-generated map (Scorched Crossing) to confirm
   the editor round-trips our files.
6. [ ] Skirmish-test Scorched Crossing in the modern exe.

**If a release has no Windows binaries / no WorldBuilder attached → go to Path B.**

## Path B — Compile from source (only if we need engine changes)

Toolchain: **Visual Studio 2022** (Desktop C++ workload) + **CMake** + **vcpkg** (repo ships
a manifest, deps auto-resolve). Code is C++20. Windows 11 is the primary dev platform.

```bash
git clone --recursive https://github.com/TheSuperHackers/GeneralsGameCode
cd GeneralsGameCode
cmake --preset win32 -DGENZH_BUILD_ZEROHOUR=ON -DGENZH_BUILD_ZEROHOUR_TOOLS=ON
cmake --build build/win32
cmake --install build/win32 --config Release
```

- Game target: `z_generals`. WorldBuilder target: `z_worldbuilder` (needs
  `GENZH_BUILD_ZEROHOUR_TOOLS=ON`). Build just the editor:
  `cmake --build build/win32 --target z_worldbuilder`.
- Install prefix (`GENZH_ZEROHOUR_INSTALL_PREFIX`) is **configure-time only** — point it at
  the retail folder; to change it, delete `build/` and reconfigure.
- **#1 gotcha:** stale CMake cache. If the build acts strange, delete `build/` and start
  fresh.
- First build is slow (first-time vcpkg dependency compile). Budget 1–3 hrs incl. tooling
  setup.

## Why this is worth it (the payoff for the map engine)

- **Instant map iteration** — test a generated `.map` without the online launcher/EAC.
- **A debuggable engine** — Path B lets us add logging to the map loader
  (`WorldHeightMap.cpp`, `DataChunk.cpp`) so a bad map tells us *exactly* which chunk/offset
  it choked on, instead of a silent crash. This is the real superpower for `cncmap`.
- **WorldBuilder as an oracle** — open our generated maps in the real editor to visually
  verify terrain/objects/passability before ever launching a match.

## Open questions / risks

- **GeneralsOnline compatibility unconfirmed.** GeneralsOnline (playgenerals.online) is a
  *separate* multiplayer reimplementation. Whether a GeneralsGameCode exe works with the GO
  service is unverified — **irrelevant for local map testing**, but don't assume our modern
  exe joins GO matches.
- Keep the modern build in a **copy** of the game folder, not the live GeneralsOnline
  install, so we never disturb Mike's working online setup.

## Sources
- https://github.com/TheSuperHackers/GeneralsGameCode (README, targets, presets)
- https://github.com/TheSuperHackers/GeneralsGameCode/wiki/cmake_guide
- https://github.com/TheSuperHackers/GeneralsGameCode/wiki/build_guides
- https://github.com/TheSuperHackers/GeneralsGameCode/releases (weekly binaries)
- https://github.com/TheSuperHackers/GeneralsGameCode/wiki/new_configuration_options
- https://github.com/electronicarts/CnC_Generals_Zero_Hour (EA GPLv3 source)
