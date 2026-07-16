import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from big_archive import pack_files, read_file
from build_mod import build_mod


def test_build_mod_patches_retail_file_and_adds_overlay(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    pack_files(
        [("Data/INI/GameData.ini", b"DefaultStartingCash = 10000\n")],
        game / "INIZH.big",
    )

    mod = tmp_path / "mod"
    (mod / "files" / "Data" / "INI" / "Object").mkdir(parents=True)
    (mod / "files" / "Data" / "INI" / "Object" / "New.ini").write_text("Object New\nEnd\n")
    manifest = {
        "basePatches": [
            {
                "archive": "INIZH.big",
                "entry": "Data\\INI\\GameData.ini",
                "replacements": [
                    {"old": "DefaultStartingCash = 10000", "new": "DefaultStartingCash = 50000"}
                ],
            }
        ]
    }
    (mod / "mod.json").write_text(json.dumps(manifest), encoding="utf-8")

    output = tmp_path / "local-dev.big"
    assert build_mod(mod / "mod.json", game, output) == 2
    assert b"50000" in read_file(output, "Data/INI/GameData.ini")
    assert read_file(output, "Data/INI/Object/New.ini").decode().splitlines() == [
        "Object New",
        "End",
    ]
