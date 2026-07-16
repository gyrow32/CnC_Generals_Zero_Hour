#!/usr/bin/env python3
"""Minimal reader/writer for the BIGF archives used by Generals and Zero Hour."""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


MAGIC = b"BIGF"
HEADER_SIZE = 16


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    size: int


def read_entries(archive: Path) -> tuple[bytes, list[Entry]]:
    data = archive.read_bytes()
    if len(data) < HEADER_SIZE or data[:4] not in (b"BIGF", b"BIG4"):
        raise ValueError(f"{archive} is not a BIG archive")

    declared_size = struct.unpack_from("<I", data, 4)[0]
    count, index_size = struct.unpack_from(">II", data, 8)
    if declared_size != len(data):
        raise ValueError(
            f"archive size mismatch: header says {declared_size}, file is {len(data)}"
        )
    if index_size < HEADER_SIZE or index_size > len(data):
        raise ValueError(f"invalid BIG index size: {index_size}")

    entries: list[Entry] = []
    position = HEADER_SIZE
    for _ in range(count):
        if position + 8 > index_size:
            raise ValueError("truncated BIG entry table")
        offset, size = struct.unpack_from(">II", data, position)
        position += 8
        try:
            name_end = data.index(b"\0", position, index_size)
        except ValueError as exc:
            raise ValueError("unterminated BIG entry name") from exc
        name = data[position:name_end].decode("latin-1")
        position = name_end + 1
        if offset < index_size or offset + size > len(data):
            raise ValueError(f"invalid bounds for {name!r}")
        entries.append(Entry(name, offset, size))

    return data, entries


def read_file(archive: Path, entry_name: str) -> bytes:
    data, entries = read_entries(archive)
    wanted = _archive_name(entry_name).lower()
    for entry in entries:
        if entry.name.lower() == wanted:
            return data[entry.offset : entry.offset + entry.size]
    raise KeyError(f"{entry_name!r} was not found in {archive}")


def _archive_name(name: str) -> str:
    if name.startswith(("/", "\\")):
        raise ValueError(f"unsafe archive path: {name!r}")
    normalized = name.replace("/", "\\").strip("\\")
    parts = PurePosixPath(normalized.replace("\\", "/")).parts
    if not normalized or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"unsafe archive path: {name!r}")
    if ":" in normalized:
        raise ValueError(f"unsafe archive path: {name!r}")
    return normalized


def pack_files(files: Iterable[tuple[str, bytes]], output: Path) -> list[Entry]:
    prepared = [(_archive_name(name), payload) for name, payload in files]
    prepared.sort(key=lambda item: item[0].lower())
    if not prepared:
        raise ValueError("a mod archive must contain at least one file")

    lowered = [name.lower() for name, _ in prepared]
    if len(lowered) != len(set(lowered)):
        raise ValueError("archive paths must be unique (case-insensitive)")

    encoded_names = [name.encode("latin-1") for name, _ in prepared]
    index_size = HEADER_SIZE + sum(8 + len(name) + 1 for name in encoded_names)
    data_offset = index_size
    entries: list[Entry] = []
    for (name, payload), _ in zip(prepared, encoded_names):
        entries.append(Entry(name, data_offset, len(payload)))
        data_offset += len(payload)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(MAGIC)
        handle.write(struct.pack("<I", data_offset))
        handle.write(struct.pack(">II", len(entries), index_size))
        for entry, encoded in zip(entries, encoded_names):
            handle.write(struct.pack(">II", entry.offset, entry.size))
            handle.write(encoded)
            handle.write(b"\0")
        for (_, payload) in prepared:
            handle.write(payload)

    # Re-read what we wrote so malformed archives fail during the build, not at launch.
    read_entries(output)
    return entries


def pack_directory(source: Path, output: Path) -> list[Entry]:
    if not source.is_dir():
        raise FileNotFoundError(f"mod source directory does not exist: {source}")
    files = [
        (path.relative_to(source).as_posix(), path.read_bytes())
        for path in source.rglob("*")
        if path.is_file()
    ]
    return pack_files(files, output)


def extract_all(archive: Path, output: Path) -> None:
    data, entries = read_entries(archive)
    output = output.resolve()
    for entry in entries:
        relative = Path(*_archive_name(entry.name).split("\\"))
        destination = (output / relative).resolve()
        if output not in destination.parents:
            raise ValueError(f"unsafe archive path: {entry.name!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data[entry.offset : entry.offset + entry.size])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack_parser = subparsers.add_parser("pack", help="pack a directory into a BIG file")
    pack_parser.add_argument("source", type=Path)
    pack_parser.add_argument("output", type=Path)

    list_parser = subparsers.add_parser("list", help="list a BIG file")
    list_parser.add_argument("archive", type=Path)

    extract_parser = subparsers.add_parser("extract", help="extract a BIG file")
    extract_parser.add_argument("archive", type=Path)
    extract_parser.add_argument("output", type=Path)

    args = parser.parse_args()
    if args.command == "pack":
        entries = pack_directory(args.source, args.output)
        print(f"Built {args.output} ({len(entries)} files)")
    elif args.command == "list":
        _, entries = read_entries(args.archive)
        for entry in entries:
            print(f"{entry.size:>10}  {entry.name}")
    else:
        extract_all(args.archive, args.output)
        print(f"Extracted {args.archive} to {args.output}")


if __name__ == "__main__":
    main()
