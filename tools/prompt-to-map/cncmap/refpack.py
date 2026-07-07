"""Compression envelope handling for Zero Hour .map files (read-only).

The engine detects compression from the first 4 bytes
(CompressionManager.cpp:103-137); compressed files carry an 8-byte header
(4-byte magic + uint32 LE uncompressed size) followed by the payload.
We only ever *read* compressed maps; the writer always emits uncompressed
"CkMp" streams, which the engine parses directly (COMPRESSION_NONE).

RefPack stream command encoding (Frank Barchard's format):
  0xxxxxxx : 2-byte op  -> literal run 0..3, back-ref len 3..10,  dist 1..1024
  10xxxxxx : 3-byte op  -> literal run 0..3, back-ref len 4..67,  dist 1..16384
  110xxxxx : 4-byte op  -> literal run 0..3, back-ref len 5..1028,dist 1..131072
  111xxxxx : 1-byte op  -> literal run only (4,8,..,112); 0xFC..0xFF = EOF (+0..3 lit)
"""
import struct
import zlib

from .datachunk import MapFormatError

# Exact magic set from CompressionManager::getCompressionType.
_MAGICS = frozenset(
    [b"NOX\x00", b"EAB\x00", b"EAH\x00", b"EAR\x00"]
    + [b"ZL%d\x00" % i for i in range(1, 10)]
)


def is_compressed(data: bytes) -> bool:
    """Mirror of CompressionManager::isDataCompressed (len<8 => never)."""
    return len(data) >= 8 and data[:4] in _MAGICS


def _refpack_stream(data: bytes) -> bytes:
    pos = 0
    # optional flags byte; standard signature is 0x10 0xFB
    if data[pos + 1] == 0xFB:
        flags = data[pos]
    else:  # some variants put 0xFB first
        flags = data[pos + 1]
    pos += 2
    # 3-byte big-endian decompressed size (4 bytes if flags & 0x80)
    if flags & 0x80:
        pos += 4
    else:
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


def decompress_map(data: bytes) -> bytes:
    """Return raw DataChunk bytes (starting with 'CkMp'), decompressing if needed."""
    if not is_compressed(data):
        return data
    magic = data[:4]
    (expected,) = struct.unpack_from("<I", data, 4)
    if magic == b"EAR\x00":
        out = _refpack_stream(data[8:])
    elif magic[:2] == b"ZL":
        out = zlib.decompress(data[8:])
    else:
        raise NotImplementedError(f"unsupported compression magic {magic!r}")
    if len(out) != expected:
        raise MapFormatError(
            f"{magic!r}: decompressed {len(out)} bytes, header said {expected}")
    return out
