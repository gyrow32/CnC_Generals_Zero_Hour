#!/usr/bin/env python3
"""SPIKE (throwaway feasibility proof, not the real toolkit).

EA RefPack decompression, needed to read real retail .map files (which are
compressed) so we can round-trip them against our own writer in Phase 0.

Retail .map wrapper (verified against MapsZH.big fixtures):
  0x00 char[4]  "EAR\\0"                     EA refpack container tag
  0x04 uint32   uncompressed size (LITTLE-endian)
  0x08 ...       raw RefPack stream, which itself begins with 0x10 0xFB
                 and a 3-byte big-endian uncompressed size.

RefPack stream command encoding (Frank Barchard's format):
  0xxxxxxx : 2-byte op  -> literal run 0..3, back-ref len 3..10,  dist 1..1024
  10xxxxxx : 3-byte op  -> literal run 0..3, back-ref len 4..67,  dist 1..16384
  110xxxxx : 4-byte op  -> literal run 0..3, back-ref len 5..1028,dist 1..131072
  111xxxxx : 1-byte op  -> literal run only (4,8,..,112); 0xFC..0xFF = EOF (+0..3 lit)
"""
import struct


def _refpack_stream(data: bytes) -> bytes:
    pos = 0
    b0 = data[pos]
    # optional flags byte; standard signature is 0x10 0xFB
    if data[pos + 1] == 0xFB:
        flags = data[pos]
        pos += 2
    else:  # some variants put 0xFB first
        flags = data[pos + 1]
        pos += 2
    # 3-byte big-endian decompressed size (4 bytes if flags & 0x80)
    if flags & 0x80:
        size = (data[pos] << 24) | (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
        pos += 4
    else:
        size = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
        pos += 3

    out = bytearray()

    def copy_ref(dist, length):
        start = len(out) - dist
        for i in range(length):
            out.append(out[start + i])

    while pos < len(data):
        b0 = data[pos]; pos += 1
        if not (b0 & 0x80):                         # 0xxxxxxx  2-byte
            b1 = data[pos]; pos += 1
            run = b0 & 0x03
            out += data[pos:pos + run]; pos += run
            length = ((b0 & 0x1C) >> 2) + 3
            dist = ((b0 & 0x60) << 3) + b1 + 1
            copy_ref(dist, length)
        elif not (b0 & 0x40):                       # 10xxxxxx  3-byte
            b1 = data[pos]; b2 = data[pos + 1]; pos += 2
            run = (b1 & 0xC0) >> 6
            out += data[pos:pos + run]; pos += run
            length = (b0 & 0x3F) + 4
            dist = ((b1 & 0x3F) << 8) + b2 + 1
            copy_ref(dist, length)
        elif not (b0 & 0x20):                       # 110xxxxx  4-byte
            b1 = data[pos]; b2 = data[pos + 1]; b3 = data[pos + 2]; pos += 3
            run = b0 & 0x03
            out += data[pos:pos + run]; pos += run
            length = ((b0 & 0x0C) << 6) + b3 + 5
            dist = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            copy_ref(dist, length)
        else:                                       # 111xxxxx  1-byte literal
            run = ((b0 & 0x1F) << 2) + 4
            if run <= 112:
                out += data[pos:pos + run]; pos += run
            else:                                   # 0xFC..0xFF EOF
                run = b0 & 0x03
                out += data[pos:pos + run]; pos += run
                break
    return bytes(out)


def is_compressed(data: bytes) -> bool:
    return data[:4] in (b"EAR\x00", b"EAB\x00", b"EAZ\x00", b"NOX\x00")


def decompress_map(data: bytes) -> bytes:
    """Return raw DataChunk bytes (starting with 'CkMp'), decompressing if needed."""
    if not is_compressed(data):
        return data
    tag = data[:4]
    (expected,) = struct.unpack_from("<I", data, 4)
    raw = _refpack_stream(data[8:])
    if len(raw) != expected:
        raise ValueError(f"{tag!r}: decompressed {len(raw)} bytes, header said {expected}")
    return raw


if __name__ == "__main__":
    import sys
    blob = open(sys.argv[1], "rb").read()
    raw = decompress_map(blob)
    print(f"compressed:   {len(blob):>10,} bytes  ({blob[:4]!r})")
    print(f"decompressed: {len(raw):>10,} bytes  (magic {raw[:4]!r})")
