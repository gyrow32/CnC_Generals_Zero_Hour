#!/usr/bin/env python3
"""Build a Zero Hour mod BIG from local files and reproducible retail-file patches."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from big_archive import pack_directory, read_file
from csf import add_strings


def build_mod(manifest_path: Path, game_dir: Path, output: Path) -> int:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_root = manifest_path.parent

    with tempfile.TemporaryDirectory(prefix="zh-mod-") as temp_name:
        staging = Path(temp_name)
        files_dir = source_root / "files"
        if files_dir.is_dir():
            shutil.copytree(files_dir, staging, dirs_exist_ok=True)

        for patch in manifest.get("basePatches", []):
            archive = game_dir / patch["archive"]
            entry = patch["entry"]
            text = read_file(archive, entry).decode(patch.get("encoding", "latin-1"))
            for replacement in patch.get("replacements", []):
                old = replacement["old"]
                new = replacement["new"]
                expected = replacement.get("expectedCount", 1)
                actual = text.count(old)
                if actual != expected:
                    raise ValueError(
                        f"{entry}: expected {expected} occurrence(s) of {old!r}, found {actual}"
                    )
                text = text.replace(old, new)

            destination = staging.joinpath(*entry.replace("/", "\\").split("\\"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(text.encode(patch.get("encoding", "latin-1")))

        for patch in manifest.get("csfAdditions", []):
            archive = game_dir / patch["archive"]
            entry = patch["entry"]
            contents = add_strings(read_file(archive, entry), patch["strings"])
            destination = staging.joinpath(*entry.replace("/", "\\").split("\\"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)

        entries = pack_directory(staging, output)
        return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("game_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    count = build_mod(args.manifest, args.game_dir, args.output)
    print(f"Built {args.output} ({count} files)")


if __name__ == "__main__":
    main()
