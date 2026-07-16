from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from map_workflow import inspect_map, install_map


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_inspect_retail_skirmish_map():
    summary = inspect_map(FIXTURES / "Golden Oasis.map")
    assert summary["players"] >= 2
    assert summary["width"] > 0
    assert summary["height"] > 0
    assert summary["objects"] > 0


def test_install_preserves_bundle_and_backs_up_changed_map(tmp_path):
    source = FIXTURES / "Golden Oasis.map"
    maps_dir = tmp_path / "Maps"
    backups = tmp_path / "backups"

    destination, _ = install_map(source, maps_dir, backups)
    assert destination.read_bytes() == source.read_bytes()
    assert destination.with_suffix(".tga").exists()

    destination.write_bytes(b"an older local map")
    install_map(source, maps_dir, backups)
    backup_files = list(backups.rglob("Golden Oasis.map"))
    assert len(backup_files) == 1
    assert backup_files[0].read_bytes() == b"an older local map"

