"""DataChunk container codec: TOC, chunk headers, primitives, Dict.

Byte-level mirror of EA's DataChunkInput/DataChunkOutput
(GeneralsMD/Code/GameEngine/Source/Common/System/DataChunk.cpp).
Everything is little-endian. Parsing is STRICT: any bound overrun or
malformed structure raises MapFormatError — a desync is a bug, not
something to paper over.

Key semantics reproduced exactly:
  * TOC: "CkMp" + i32 count + entries {u8 nameLen, name, u32 id}.
    Ids are allocated from 1 in first-use order, but entries are PREPENDED
    to a linked list, so on disk the newest id comes first
    (DataChunk.cpp:482-526). Toc.get_or_allocate mirrors allocateID.
  * Chunk header (10 bytes): u32 labelId, u16 version, i32 dataSize.
    dataSize covers the payload including nested sub-chunk headers.
  * AsciiString: u16 len + bytes (no NUL). Encoded latin-1 (byte-preserving).
  * UnicodeString: u16 CHAR count + UTF-16LE bytes (surrogatepass for exactness).
  * Dict: u16 pairCount, each pair i32 keyAndType = (tocId << 8) | dataType,
    then the value. Key names share the TOC id space with chunk labels.
"""
import struct
from typing import NamedTuple

CHUNK_HEADER = struct.Struct("<IHi")   # labelId, version, dataSize

# Dict::DataType (Common/Dict.h:74-81)
DICT_BOOL = 0
DICT_INT = 1
DICT_REAL = 2
DICT_ASCIISTRING = 3
DICT_UNICODESTRING = 4


class MapFormatError(Exception):
    """Raised on any structural violation of the .map format."""


class DictEntry(NamedTuple):
    key: str      # key name (interned in the TOC on write)
    dtype: int    # DICT_* type code
    value: object


class Toc:
    """The name table. Holds (name, id) entries in exact on-disk order.

    Parsed maps keep their original entries verbatim so re-serialization is
    byte-exact. Fresh maps allocate like EA: ids from 1 in first-use order,
    each new entry prepended (so disk order is reverse allocation order).
    """

    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self._by_name = {}
        self._by_id = {}
        for name, cid in self.entries:
            if name in self._by_name:
                raise MapFormatError(f"duplicate TOC name {name!r}")
            if cid in self._by_id:
                raise MapFormatError(f"duplicate TOC id {cid}")
            self._by_name[name] = cid
            self._by_id[cid] = name
        self._next_id = max(self._by_id, default=0) + 1

    @classmethod
    def parse(cls, r: "Reader") -> "Toc":
        if r.bytes(4) != b"CkMp":
            raise MapFormatError("bad magic: not a chunky map (missing CkMp)")
        count = r.i32()
        if count <= 0:
            raise MapFormatError(f"TOC count {count} invalid")
        entries = []
        for _ in range(count):
            nlen = r.u8()
            name = r.bytes(nlen).decode("latin-1")
            entries.append((name, r.u32()))
        return cls(entries)

    def serialize(self) -> bytes:
        out = bytearray(b"CkMp")
        out += struct.pack("<i", len(self.entries))
        for name, cid in self.entries:
            raw = name.encode("latin-1")
            if len(raw) > 255:
                raise MapFormatError(f"TOC name too long: {name!r}")
            out += struct.pack("<B", len(raw)) + raw + struct.pack("<I", cid)
        return bytes(out)

    def name_of(self, cid: int) -> str:
        try:
            return self._by_id[cid]
        except KeyError:
            raise MapFormatError(f"TOC id {cid} not in table") from None

    def get_or_allocate(self, name: str) -> int:
        cid = self._by_name.get(name)
        if cid is None:
            cid = self._next_id
            self._next_id += 1
            self.entries.insert(0, (name, cid))   # EA prepends (DataChunk.cpp:497)
            self._by_name[name] = cid
            self._by_id[cid] = name
        return cid


class Reader:
    """Strict bounds-checked reader over a bytes window."""
    __slots__ = ("data", "pos", "end")

    def __init__(self, data: bytes, pos: int = 0, end: int = None):
        self.data = data
        self.pos = pos
        self.end = len(data) if end is None else end

    @property
    def remaining(self) -> int:
        return self.end - self.pos

    def _need(self, n: int):
        if self.pos + n > self.end:
            raise MapFormatError(
                f"read past end: need {n} bytes at offset {self.pos}, "
                f"only {self.remaining} left")

    def bytes(self, n: int) -> bytes:
        self._need(n)
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v

    def sub(self, n: int) -> "Reader":
        """Consume n bytes and return a child Reader scoped to exactly them."""
        self._need(n)
        child = Reader(self.data, self.pos, self.pos + n)
        self.pos += n
        return child

    def u8(self) -> int:
        self._need(1)
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        self._need(2)
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def i32(self) -> int:
        self._need(4)
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def u32(self) -> int:
        self._need(4)
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32(self) -> float:
        self._need(4)
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def ascii(self) -> str:
        n = self.u16()
        return self.bytes(n).decode("latin-1")

    def unicode(self) -> str:
        n = self.u16()   # CHAR count, not bytes
        return self.bytes(n * 2).decode("utf-16-le", "surrogatepass")

    def dict(self, toc: Toc) -> list:
        count = self.u16()
        out = []
        for _ in range(count):
            kt = self.u32()
            dtype = kt & 0xFF
            key = toc.name_of(kt >> 8)
            if dtype == DICT_BOOL:
                value = self.u8()
            elif dtype == DICT_INT:
                value = self.i32()
            elif dtype == DICT_REAL:
                value = self.f32()
            elif dtype == DICT_ASCIISTRING:
                value = self.ascii()
            elif dtype == DICT_UNICODESTRING:
                value = self.unicode()
            else:
                raise MapFormatError(f"bad Dict type {dtype} for key {key!r}")
            out.append(DictEntry(key, dtype, value))
        return out

    def expect_end(self, context: str):
        if self.remaining:
            raise MapFormatError(
                f"{context}: {self.remaining} unparsed bytes left in chunk")


class Writer:
    """Append-only byte builder mirroring DataChunkOutput's primitives."""
    __slots__ = ("buf",)

    def __init__(self):
        self.buf = bytearray()

    def raw(self, data: bytes):
        self.buf += data

    def u8(self, v: int):
        self.buf.append(v & 0xFF)

    def u16(self, v: int):
        self.buf += struct.pack("<H", v)

    def i32(self, v: int):
        self.buf += struct.pack("<i", v)

    def u32(self, v: int):
        self.buf += struct.pack("<I", v)

    def f32(self, v: float):
        self.buf += struct.pack("<f", v)

    def ascii(self, s: str):
        raw = s.encode("latin-1")
        self.u16(len(raw))
        self.buf += raw

    def unicode(self, s: str):
        raw = s.encode("utf-16-le", "surrogatepass")
        self.u16(len(raw) // 2)   # CHAR count
        self.buf += raw

    def dict(self, entries: list, toc: Toc):
        self.u16(len(entries))
        for key, dtype, value in entries:
            self.u32((toc.get_or_allocate(key) << 8) | (dtype & 0xFF))
            if dtype == DICT_BOOL:
                self.u8(value)
            elif dtype == DICT_INT:
                self.i32(value)
            elif dtype == DICT_REAL:
                self.f32(value)
            elif dtype == DICT_ASCIISTRING:
                self.ascii(value)
            elif dtype == DICT_UNICODESTRING:
                self.unicode(value)
            else:
                raise MapFormatError(f"bad Dict type {dtype} for key {key!r}")

    def getvalue(self) -> bytes:
        return bytes(self.buf)
