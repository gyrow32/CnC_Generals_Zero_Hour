
# Command & Conquer Generals (inc. Zero Hour) Source Code

## Local play and modding quick start

This fork includes an isolated Windows development launcher. It uses the game data from
an owned EA/Steam Zero Hour installation, but keeps the maintained executable and every
generated mod under this repository's ignored `.local` directory. It does not replace
the retail executable or disturb a GeneralsOnline installation.

From PowerShell in the repository root:

```powershell
# Download the latest maintained Zero Hour runtime and verify the setup.
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\local-dev\dev.ps1 -Action setup

# Build the sample mod and play it locally.
# The visible proof is $50,000 starting cash in a skirmish match.
# Play defaults to borderless 16:9 HD on the landscape monitor.
powershell -NoProfile -ExecutionPolicy Bypass -File .\play-local.ps1

# Play without any mod, or open the installed WorldBuilder.
powershell -NoProfile -ExecutionPolicy Bypass -File .\play-local.ps1 -Vanilla
powershell -NoProfile -ExecutionPolicy Bypass -File .\worldbuilder-local.ps1

# Validate/install an AI-generated map and open it directly in WorldBuilder.
powershell -NoProfile -ExecutionPolicy Bypass -File .\worldbuilder-local.ps1 -Map "Panorama Pass"
```

The launcher chooses the largest connected landscape display and defaults to borderless
fullscreen there, ignoring portrait screens. Use `-Windowed -XRes 1600 -YRes 900` for a
movable fixed-size development window, or `-Fullscreen` for legacy exclusive fullscreen.
Do not externally maximize or resize a fixed-size game window: this legacy DirectX build
does not recalculate mouse coordinates after an external resize.

Edit [`mods/local-dev`](mods/local-dev) to develop the starter mod. Files below its
`files` directory are packed using their relative game paths. For example,
`files/Data/INI/Object/MyUnit.ini` becomes `Data\\INI\\Object\\MyUnit.ini` in the mod.
`mod.json` can also copy a file from an owned retail BIG archive and apply exact text
replacements at build time; this avoids checking copyrighted retail data into Git.

The starter mod raises the default camera and camera ceiling to `400`, so a
skirmish starts with a higher tactical view even when wheel input is unavailable.
To choose another fixed height, change both camera-height replacements in
`mods/local-dev/mod.json`, then launch again.

Useful development commands:

```powershell
# Build without launching, then inspect the produced archive.
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\local-dev\dev.ps1 -Action build
python .\tools\local-dev\big_archive.py list .\.local\mods\local-dev.big

# Re-run dependency/runtime checks.
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\local-dev\dev.ps1 -Action check

# Run the mod/archive and map-tool tests.
python -m pytest .\tools\local-dev\tests .\tools\prompt-to-map\tests -q
```

Custom maps remain separate from gameplay mods. Put each map in its own folder under
`Documents\Command and Conquer Generals Zero Hour Data\Maps`, or use the existing
`tools/prompt-to-map` builders with `--install`.

For AI map design, unpack the owned retail maps and INI definitions into the ignored
local reference catalog. This gives the AI canonical object names, retail map layouts,
terrain texture names, dimensions, player starts, and object counts without committing
EA's assets:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\local-dev\dev.ps1 -Action unpack
```

The original EA source below still needs its historical proprietary SDK dependencies.
The local launcher therefore uses a current game binary from the community-maintained
[GeneralsGameCode project](https://github.com/TheSuperHackers/GeneralsGameCode/releases)
and the retail WorldBuilder while preserving this source tree for engine work.

This repository includes source code for Command & Conquer Generals, and its expansion pack Zero Hour. This release provides support to the Steam Workshop for both games ([C&C Generals](https://steamcommunity.com/workshop/browse/?appid=2229870) and [C&C Generals - Zero Hour](https://steamcommunity.com/workshop/browse/?appid=2732960)).


## Dependencies

If you wish to rebuild the source code and tools successfully you will need to find or write new replacements (or remove the code using them entirely) for the following libraries;

- DirectX SDK (Version 9.0 or higher) (expected path `\Code\Libraries\DirectX\`)
- STLport (4.5.3) - (expected path `\Code\Libraries\STLport-4.5.3`)
- 3DSMax 4 SDK - (expected path `\Code\Libraries\Max4SDK\`)
- NVASM - (expected path `\Code\Tools\NVASM\`)
- BYTEmark - (expected path `\Code\Libraries\Source\Benchmark`)
- RAD Miles Sound System SDK - (expected path `\Code\Libraries\Source\WWVegas\Miles6\`)
- RAD Bink SDK - (expected path `\Code\GameEngineDevice\Include\VideoDevice\Bink`)
- SafeDisk API - (expected path `\Code\GameEngine\Include\Common\SafeDisk` and `\Code\Tools\Launcher\SafeDisk\`)
- Miles Sound System "Asimp3" - (expected path `\Code\Libraries\WPAudio\Asimp3`)
- GameSpy SDK - (expected path `\Code\Libraries\Source\GameSpy\`)
- ZLib (1.1.4) - (expected path `\Code\Libraries\Source\Compression\ZLib\`)
- LZH-Light (1.0) - (expected path `\Code\Libraries\Source\Compression\LZHCompress\CompLibSource` and `CompLibHeader`)


## Compiling (Win32 Only)

To use the compiled binaries, you must own the game. The C&C Ultimate Collection is available for purchase on [EA App](https://www.ea.com/en-gb/games/command-and-conquer/command-and-conquer-the-ultimate-collection/buy/pc) or [Steam](https://store.steampowered.com/bundle/39394/Command__Conquer_The_Ultimate_Collection/).

The quickest way to build all configurations in the project is to open `rts.dsw` in Microsoft Visual Studio C++ 6.0 (SP6 recommended for binary matching to Generals patch 1.08 and Zero Hour patch 1.04) and select Build -> Batch Build, then hit the “Rebuild All” button.

If you wish to compile the code under a modern version of Microsoft Visual Studio, you can convert the legacy project file to a modern MSVC solution by opening `rts.dsw` in Microsoft Visual Studio .NET 2003, and then opening the newly created project and solution file in MSVC 2015 or newer.

NOTE: As modern versions of MSVC enforce newer revisions of the C++ standard, you will need to make extensive changes to the codebase before it successfully compiles, even more so if you plan on compiling for the Win64 platform.

When the workspace has finished building, the compiled binaries will be copied to the folder called `/Run/` found in the root of each games directory. 


## Known Issues

Windows has a policy where executables that contain words “version”, “update” or “install” in their filename will require UAC Elevation to run. This will affect “versionUpdate” and “buildVersionUpdate” projects from running as post-build events. Renaming the output binary name for these projects to not include these words should resolve the issue for you.


## STLport
STLport will require changes to successfully compile this source code. The file [stlport.diff](stlport.diff) has been provided for you so you can review and apply these changes. Please make sure you are using STLport 4.5.3 before attempting to apply the patch.


## Contributing

This repository will not be accepting contributions (pull requests, issues, etc). If you wish to create changes to the source code and encourage collaboration, please create a fork of the repository under your GitHub user/organization space.


## Support

This repository is for preservation purposes only and is archived without support. 


## License

This repository and its contents are licensed under the GPL v3 license, with additional terms applied. Please see [LICENSE.md](LICENSE.md) for details.
