from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

FLASH_BASE = 0x08000000
LINK_ALIGNMENT = 0x10000


def inspect_cfs_image_layout(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    if len(data) < 8:
        raise ValueError("CFS image is too small to contain a Cortex-M vector table")

    initial_sp, reset_vector = struct.unpack_from("<II", data, 0)
    reset_address = reset_vector & ~1
    thumb = bool(reset_vector & 1)

    # The CFS artifacts are raw Cortex-M application images.  Infer the linked
    # region from the reset-vector window, then verify that the reset handler
    # actually lands inside the supplied image.
    link_base = reset_address & ~(LINK_ALIGNMENT - 1)
    reset_offset = reset_address - link_base
    reset_inside_image = 0 <= reset_offset < len(data)
    image_end = link_base + len(data)
    lower_reserved = max(0, link_base - FLASH_BASE)

    return {
        "vector_table": {
            "initial_sp": f"0x{initial_sp:08x}",
            "reset_vector": f"0x{reset_vector:08x}",
            "reset_address": f"0x{reset_address:08x}",
            "thumb": thumb,
        },
        "linked_flash": {
            "base": f"0x{link_base:08x}",
            "end_exclusive": f"0x{image_end:08x}",
            "size": len(data),
            "reset_offset": reset_offset,
            "reset_inside_image": reset_inside_image,
        },
        "lower_flash_region": {
            "flash_origin": f"0x{FLASH_BASE:08x}",
            "bytes_before_application": lower_reserved,
            "separate_from_application": lower_reserved > 0,
            "interpretation": (
                "consistent-with-resident-bootloader-or-other-lower-flash-code"
                if lower_reserved > 0
                else "no-lower-reserved-region-inferred"
            ),
        },
        "claims": {
            "bootloader_image_present_in_application": False,
            "bootloader_fallback_after_bad_app_proven": False,
        },
    }