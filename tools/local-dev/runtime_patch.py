#!/usr/bin/env python3
"""Apply narrowly validated fixes to the maintained prebuilt game runtime."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


# weekly-2026-07-10 WndProc extracts WM_MOUSEWHEEL screen coordinates with
# unsigned operations. The replacement sign-extends X and arithmetically shifts Y.
UNSIGNED_WHEEL_COORDS = bytes.fromhex(
    "8b f3 8b fb 52 50 81 e6 ff ff 00 00 c1 ef 10 ff 15"
)
SIGNED_WHEEL_COORDS = bytes.fromhex(
    "8b f3 8b fb 52 50 0f bf f6 90 90 90 c1 ff 10 ff 15"
)

# The same bug in earlier weekly builds uses EDI as both the packed lParam and Y.
UNSIGNED_WHEEL_COORDS_EARLY = bytes.fromhex(
    "8b f7 52 50 81 e6 ff ff 00 00 c1 ef 10 ff 15"
)
SIGNED_WHEEL_COORDS_EARLY = bytes.fromhex(
    "8b f7 52 50 0f bf f6 90 90 90 c1 ff 10 ff 15"
)


def patch_negative_monitor_wheel(data: bytes) -> tuple[bytes, bool]:
    variants = (
        (UNSIGNED_WHEEL_COORDS, SIGNED_WHEEL_COORDS),
        (UNSIGNED_WHEEL_COORDS_EARLY, SIGNED_WHEEL_COORDS_EARLY),
    )
    unsigned_count = sum(data.count(old) for old, _new in variants)
    signed_count = sum(data.count(new) for _old, new in variants)

    if unsigned_count == 1 and signed_count == 0:
        for old, new in variants:
            if old in data:
                return data.replace(old, new), True
    if unsigned_count == 0 and signed_count == 1:
        return data, False
    raise ValueError(
        "Cannot safely identify the wheel-coordinate code "
        f"(unsigned={unsigned_count}, patched={signed_count})"
    )


def patch_runtime(path: Path) -> bool:
    path = path.resolve()
    patched, changed = patch_negative_monitor_wheel(path.read_bytes())
    if changed:
        backup = path.with_suffix(path.suffix + ".before-wheel-fix")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_bytes(patched)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    changed = patch_runtime(args.executable)
    state = "applied" if changed else "already applied"
    print(f"Negative-monitor mouse-wheel fix: {state}")


if __name__ == "__main__":
    main()
