"""Minimal Command & Conquer CSF string-table patching support."""

from __future__ import annotations

import struct
from collections.abc import Mapping


CSF_ID = b" FSC"
CSF_LABEL = b" LBL"
CSF_STRING = b" RTS"
CSF_STRING_WITH_WAVE = b"WRTS"
HEADER = struct.Struct("<6I")
UINT32 = struct.Struct("<I")


def _read_u32(data: bytes, offset: int) -> tuple[int, int]:
    if offset + UINT32.size > len(data):
        raise ValueError("Truncated CSF integer")
    return UINT32.unpack_from(data, offset)[0], offset + UINT32.size


def labels(data: bytes) -> set[str]:
    """Return all labels while validating the portions of the CSF we traverse."""
    if len(data) < HEADER.size:
        raise ValueError("Truncated CSF header")
    signature, version, label_count, _string_count, _skip, _language = HEADER.unpack_from(data)
    if signature.to_bytes(4, "little") != CSF_ID:
        raise ValueError("Not a CSF file")
    if version != 3:
        raise ValueError(f"Unsupported CSF version: {version}")

    offset = HEADER.size
    found: set[str] = set()
    for _ in range(label_count):
        if data[offset : offset + 4] != CSF_LABEL:
            raise ValueError(f"Invalid CSF label marker at offset {offset}")
        offset += 4
        string_count, offset = _read_u32(data, offset)
        name_length, offset = _read_u32(data, offset)
        name_end = offset + name_length
        if name_end > len(data):
            raise ValueError("Truncated CSF label")
        found.add(data[offset:name_end].decode("ascii"))
        offset = name_end

        for _ in range(string_count):
            marker = data[offset : offset + 4]
            if marker not in (CSF_STRING, CSF_STRING_WITH_WAVE):
                raise ValueError(f"Invalid CSF string marker at offset {offset}")
            offset += 4
            text_length, offset = _read_u32(data, offset)
            offset += text_length * 2
            if offset > len(data):
                raise ValueError("Truncated CSF text")
            if marker == CSF_STRING_WITH_WAVE:
                wave_length, offset = _read_u32(data, offset)
                offset += wave_length
                if offset > len(data):
                    raise ValueError("Truncated CSF wave name")

    if offset != len(data):
        raise ValueError(f"Unexpected trailing CSF data at offset {offset}")
    return found


def _encode_string(text: str) -> bytes:
    plain = text.encode("utf-16-le")
    encrypted = bytearray(len(plain))
    for offset in range(0, len(plain), 2):
        unit = int.from_bytes(plain[offset : offset + 2], "little") ^ 0xFFFF
        encrypted[offset : offset + 2] = unit.to_bytes(2, "little")
    return CSF_STRING + UINT32.pack(len(plain) // 2) + encrypted


def add_strings(data: bytes, additions: Mapping[str, str]) -> bytes:
    """Append uniquely named strings and adjust the CSF header counts."""
    existing = labels(data)
    duplicates = sorted(existing.intersection(additions))
    if duplicates:
        raise ValueError(f"CSF label(s) already exist: {', '.join(duplicates)}")

    output = bytearray(data)
    for label, text in additions.items():
        encoded_label = label.encode("ascii")
        output.extend(CSF_LABEL)
        output.extend(UINT32.pack(1))
        output.extend(UINT32.pack(len(encoded_label)))
        output.extend(encoded_label)
        output.extend(_encode_string(text))

    header = list(HEADER.unpack_from(output))
    header[2] += len(additions)
    header[3] += len(additions)
    HEADER.pack_into(output, 0, *header)
    return bytes(output)
