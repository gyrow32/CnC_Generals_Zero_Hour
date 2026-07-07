#!/usr/bin/env python3
"""SPIKE (throwaway feasibility proof, not the real toolkit).

Parse a decompressed Generals .map (DataChunk format) and print its chunk tree.
Proves our understanding of the format reference against a REAL retail map.

Format (little-endian, confirmed vs MapsZH.big fixtures + EA source):
  TOC:   "CkMp", count i32, then count x { nameLen u8, name bytes, id u32 }
  chunk: id u32, version u16, dataSize i32, payload[dataSize]
         payload may itself contain nested sub-chunks.
"""
import struct
import sys

# chunk labels known to CONTAIN nested sub-chunks (so we recurse into them)
CONTAINERS = {"ObjectsList", "PolygonTriggers", "SidesList", "PlayerScriptsList",
              "ScriptList", "ScriptGroup", "Script"}


def parse_toc(data):
    assert data[:4] == b"CkMp", f"bad magic {data[:4]!r}"
    (count,) = struct.unpack_from("<i", data, 4)
    pos = 8
    id_to_name = {}
    for _ in range(count):
        nlen = data[pos]; pos += 1
        name = data[pos:pos + nlen].decode("latin-1"); pos += nlen
        (cid,) = struct.unpack_from("<I", data, pos); pos += 4
        id_to_name[cid] = name
    return id_to_name, pos, count


def walk(data, start, end, id_to_name, depth, counts):
    pos = start
    while pos + 10 <= end:
        cid, ver, size = struct.unpack_from("<IHi", data, pos)
        name = id_to_name.get(cid)
        if name is None or size < 0 or pos + 10 + size > end:
            break  # not a chunk boundary (we're inside raw payload data)
        counts[name] = counts.get(name, 0) + 1
        body = pos + 10
        indent = "  " * depth
        print(f"{indent}{name:<20} v{ver:<3} {size:>9,} bytes")
        if name in CONTAINERS:
            walk(data, body, body + size, id_to_name, depth + 1, counts)
        pos = body + size
    return pos


def main():
    sys.path.insert(0, sys.path[0])
    from refpack import decompress_map
    raw = decompress_map(open(sys.argv[1], "rb").read())
    id_to_name, chunk_start, toc_count = parse_toc(raw)
    print(f"TOC: {toc_count} interned names, chunk stream starts at 0x{chunk_start:x}")
    print(f"decompressed size: {len(raw):,} bytes\n")
    print("CHUNK TREE (top level + known containers):")
    counts = {}
    walk(raw, chunk_start, len(raw), id_to_name, 0, counts)
    print("\nOBJECT/CHUNK CENSUS:")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>5}  {name}")


if __name__ == "__main__":
    main()
