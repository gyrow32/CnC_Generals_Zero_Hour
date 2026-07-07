"""Codec round-trips for the low-level primitives: ints, floats, strings,
Dict, TOC, chunk headers."""
import struct

import pytest

from cncmap import (DICT_ASCIISTRING, DICT_BOOL, DICT_INT, DICT_REAL,
                    DICT_UNICODESTRING, DictEntry, MapFormatError, Toc)
from cncmap.datachunk import Reader, Writer


def rt(write, read):
    """Write with one Writer, read back with a fresh Reader."""
    w = Writer()
    write(w)
    r = Reader(w.getvalue())
    out = read(r)
    assert r.remaining == 0, "reader did not consume everything written"
    return out


def test_scalar_roundtrips():
    assert rt(lambda w: w.i32(-123456789), lambda r: r.i32()) == -123456789
    assert rt(lambda w: w.u32(0x7ADA0000), lambda r: r.u32()) == 0x7ADA0000
    assert rt(lambda w: w.u16(65535), lambda r: r.u16()) == 65535
    assert rt(lambda w: w.u8(200), lambda r: r.u8()) == 200


def test_f32_is_bit_exact():
    for value in (0.0, -1.0, 3.14159, 1e-30, -2.5e20):
        f32 = struct.unpack("<f", struct.pack("<f", value))[0]
        assert rt(lambda w: w.f32(f32), lambda r: r.f32()) == f32
        # and the bytes themselves survive a second pass
        w = Writer()
        w.f32(f32)
        w2 = Writer()
        w2.f32(Reader(w.getvalue()).f32())
        assert w.getvalue() == w2.getvalue()


def test_string_roundtrips():
    assert rt(lambda w: w.ascii("GLABarracks"), lambda r: r.ascii()) == "GLABarracks"
    assert rt(lambda w: w.ascii(""), lambda r: r.ascii()) == ""
    # latin-1 keeps every byte value 0-255 intact
    gnarly = bytes(range(256)).decode("latin-1")
    assert rt(lambda w: w.ascii(gnarly), lambda r: r.ascii()) == gnarly
    assert rt(lambda w: w.unicode("Alpine Assault – 中文"),
              lambda r: r.unicode()) == "Alpine Assault – 中文"


def test_ascii_length_prefix_is_u16_char_count():
    w = Writer()
    w.ascii("abc")
    assert w.getvalue() == b"\x03\x00abc"
    w = Writer()
    w.unicode("ab")
    assert w.getvalue() == b"\x02\x00a\x00b\x00"   # CHAR count, not bytes


def test_dict_roundtrip_all_types():
    toc = Toc()
    entries = [
        DictEntry("boolKey", DICT_BOOL, 1),
        DictEntry("intKey", DICT_INT, -42),
        DictEntry("realKey", DICT_REAL,
                  struct.unpack("<f", struct.pack("<f", 2.5))[0]),
        DictEntry("asciiKey", DICT_ASCIISTRING, "hello"),
        DictEntry("uniKey", DICT_UNICODESTRING, "wörld"),
    ]
    w = Writer()
    w.dict(entries, toc)
    r = Reader(w.getvalue())
    assert r.dict(toc) == entries
    assert r.remaining == 0


def test_dict_key_and_type_packing():
    toc = Toc()
    kid = toc.get_or_allocate("weather")
    w = Writer()
    w.dict([DictEntry("weather", DICT_INT, 7)], toc)
    data = w.getvalue()
    assert struct.unpack_from("<H", data, 0)[0] == 1           # pairCount
    key_and_type = struct.unpack_from("<I", data, 2)[0]
    assert key_and_type == (kid << 8) | DICT_INT
    assert struct.unpack_from("<i", data, 6)[0] == 7


def test_toc_allocation_matches_ea_semantics():
    toc = Toc()
    a = toc.get_or_allocate("First")
    b = toc.get_or_allocate("Second")
    assert (a, b) == (1, 2)                       # ids from 1, first-use order
    assert toc.get_or_allocate("First") == 1      # idempotent
    # entries are prepended, so disk order is newest-first
    assert toc.entries == [("Second", 2), ("First", 1)]


def test_toc_serialize_parse_identity():
    toc = Toc()
    for name in ("HeightMapData", "weather", "Object"):
        toc.get_or_allocate(name)
    data = toc.serialize()
    assert data.startswith(b"CkMp")
    parsed = Toc.parse(Reader(data))
    assert parsed.entries == toc.entries
    # a re-serialize of the parsed table is byte-identical
    assert parsed.serialize() == data


def test_toc_parsed_table_allocates_above_max_id():
    toc = Toc([("B", 5), ("A", 1)])
    assert toc.get_or_allocate("C") == 6
    assert toc.entries[0] == ("C", 6)             # prepended


def test_reader_bounds_are_strict():
    r = Reader(b"\x01\x02")
    with pytest.raises(MapFormatError):
        r.i32()
    with pytest.raises(MapFormatError):
        Reader(b"").u8()


def test_bad_magic_rejected():
    with pytest.raises(MapFormatError):
        Toc.parse(Reader(b"NOPE\x01\x00\x00\x00"))
