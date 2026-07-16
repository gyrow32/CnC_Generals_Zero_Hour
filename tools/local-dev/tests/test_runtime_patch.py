from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime_patch import (
    SIGNED_WHEEL_COORDS,
    SIGNED_WHEEL_COORDS_EARLY,
    UNSIGNED_WHEEL_COORDS,
    UNSIGNED_WHEEL_COORDS_EARLY,
    patch_negative_monitor_wheel,
)


def test_patch_sign_extends_negative_monitor_wheel_coordinates():
    original = b"prefix" + UNSIGNED_WHEEL_COORDS + b"suffix"

    patched, changed = patch_negative_monitor_wheel(original)

    assert changed is True
    assert UNSIGNED_WHEEL_COORDS not in patched
    assert patched == b"prefix" + SIGNED_WHEEL_COORDS + b"suffix"


def test_patch_is_idempotent():
    patched, changed = patch_negative_monitor_wheel(SIGNED_WHEEL_COORDS)

    assert changed is False
    assert patched == SIGNED_WHEEL_COORDS


def test_patch_supports_early_weekly_runtime_register_layout():
    patched, changed = patch_negative_monitor_wheel(UNSIGNED_WHEEL_COORDS_EARLY)

    assert changed is True
    assert patched == SIGNED_WHEEL_COORDS_EARLY


@pytest.mark.parametrize("data", [b"no match", UNSIGNED_WHEEL_COORDS * 2])
def test_patch_refuses_unknown_or_ambiguous_binary(data):
    with pytest.raises(ValueError, match="Cannot safely identify"):
        patch_negative_monitor_wheel(data)
