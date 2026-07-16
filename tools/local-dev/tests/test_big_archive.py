from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from big_archive import extract_all, pack_directory, pack_files, read_entries, read_file


def test_pack_and_extract_round_trip(tmp_path):
    source = tmp_path / "source"
    (source / "Data" / "INI").mkdir(parents=True)
    (source / "Data" / "INI" / "GameData.ini").write_text("hello", encoding="ascii")
    (source / "read me.txt").write_bytes(b"world\x00")

    archive = tmp_path / "sample.big"
    entries = pack_directory(source, archive)

    assert [entry.name for entry in entries] == ["Data\\INI\\GameData.ini", "read me.txt"]
    assert read_file(archive, "data/ini/gamedata.ini") == b"hello"
    assert len(read_entries(archive)[1]) == 2

    extracted = tmp_path / "extracted"
    extract_all(archive, extracted)
    assert (extracted / "Data" / "INI" / "GameData.ini").read_text() == "hello"
    assert (extracted / "read me.txt").read_bytes() == b"world\x00"


@pytest.mark.parametrize("name", ["../escape.ini", "/absolute.ini", "C:\\bad.ini"])
def test_pack_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        pack_files([(name, b"bad")], tmp_path / "bad.big")


def test_pack_rejects_case_insensitive_duplicates(tmp_path):
    with pytest.raises(ValueError):
        pack_files([("A.ini", b"a"), ("a.ini", b"b")], tmp_path / "bad.big")

