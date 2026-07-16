import struct

import pytest

from csf import CSF_ID, CSF_LABEL, CSF_STRING, HEADER, add_strings, labels


def make_csf(label: str = "GUI:Existing", text: str = "Existing") -> bytes:
    encoded_label = label.encode("ascii")
    plain = text.encode("utf-16-le")
    encrypted = b"".join(
        (int.from_bytes(plain[i : i + 2], "little") ^ 0xFFFF).to_bytes(2, "little")
        for i in range(0, len(plain), 2)
    )
    signature = int.from_bytes(CSF_ID, "little")
    return (
        HEADER.pack(signature, 3, 1, 1, 0, 0)
        + CSF_LABEL
        + struct.pack("<II", 1, len(encoded_label))
        + encoded_label
        + CSF_STRING
        + struct.pack("<I", len(plain) // 2)
        + encrypted
    )


def test_add_strings_updates_counts_and_labels():
    patched = add_strings(make_csf(), {"GUI:CustomMission": "Custom Mission"})

    assert HEADER.unpack_from(patched)[2:4] == (2, 2)
    assert labels(patched) == {"GUI:Existing", "GUI:CustomMission"}


def test_add_strings_rejects_duplicate_label():
    with pytest.raises(ValueError, match="already exist"):
        add_strings(make_csf(), {"GUI:Existing": "Replacement"})


def test_labels_rejects_invalid_file():
    with pytest.raises(ValueError, match="Not a CSF"):
        labels(b"not a csf" + bytes(32))
