#!/usr/bin/env python3
"""SPIKE (throwaway feasibility proof, not the real toolkit).

Read-only extractor for EA .BIG archives, used to pull real retail .map files
out of the game so we have ground-truth fixtures for Phase-0 round-trip tests.

BIG format (verified against MapsZH.big):
  0x00  char[4]  magic "BIGF"
  0x04  uint32   archive size            (LITTLE-endian)
  0x08  uint32   number of entries       (BIG-endian)
  0x0C  uint32   index/header size       (BIG-endian; offset to first data)
  then per entry:
        uint32   offset                  (BIG-endian)
        uint32   size                    (BIG-endian)
        char[]   name, NUL-terminated ASCII (uses '\\' path separators)
"""
import struct
import sys
from pathlib import Path


def list_entries(data: bytes):
    magic = data[0:4]
    if magic not in (b"BIGF", b"BIG4"):
        raise ValueError(f"not a BIG archive (magic={magic!r})")
    # archive size is little-endian; count + index size are big-endian
    (num_entries,) = struct.unpack_from(">I", data, 8)
    entries = []
    pos = 16
    for _ in range(num_entries):
        offset, size = struct.unpack_from(">II", data, pos)
        pos += 8
        end = data.index(b"\x00", pos)
        name = data[pos:end].decode("latin-1")
        pos = end + 1
        entries.append((name, offset, size))
    return entries


def main():
    big_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    name_filter = sys.argv[3].lower() if len(sys.argv) > 3 else ".map"
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    data = big_path.read_bytes()
    entries = list_entries(data)
    maps = [e for e in entries if e[0].lower().endswith(name_filter)]
    print(f"{big_path.name}: {len(entries)} entries, {len(maps)} matching '{name_filter}'")

    # prefer smaller maps first (simpler fixtures), extract up to `limit` (0 = all)
    maps.sort(key=lambda e: e[2])
    if limit:
        maps = maps[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, offset, size in maps:
        blob = data[offset:offset + size]
        # flatten "Maps\Foo\Foo.map" -> "Foo.map"
        flat = name.replace("\\", "/").split("/")[-1]
        (out_dir / flat).write_bytes(blob)
        print(f"  extracted {flat:40s} {size:>10,} bytes   (src: {name})")


if __name__ == "__main__":
    main()
