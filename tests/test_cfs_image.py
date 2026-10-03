from pathlib import Path
import struct

from k2fw.cfs_image import inspect_cfs_image_layout


def _image(size: int, sp: int, reset: int) -> bytes:
    data = bytearray(size)
    struct.pack_into("<II", data, 0, sp, reset)
    off = (reset & ~1) - ((reset & ~1) & ~0xFFFF)
    data[off:off + 4] = b"\x12\x34\x56\x78"
    return bytes(data)


def test_cfs0_layout_infers_64k_lower_region(tmp_path: Path):
    p = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    p.write_bytes(_image(175104, 0x20006EE8, 0x0801A759))

    result = inspect_cfs_image_layout(p)
    assert result["linked_flash"]["base"] == "0x08010000"
    assert result["linked_flash"]["end_exclusive"] == "0x0803ac00"
    assert result["linked_flash"]["reset_offset"] == 0xA758
    assert result["linked_flash"]["reset_inside_image"] is True
    assert result["lower_flash_region"]["bytes_before_application"] == 0x10000
    assert result["lower_flash_region"]["separate_from_application"] is True
    assert result["claims"]["bootloader_fallback_after_bad_app_proven"] is False


def test_cfs6_layout_does_not_infer_lower_region(tmp_path: Path):
    p = tmp_path / "cfs6_100_G31-cfs6_220_000.bin"
    p.write_bytes(_image(144856, 0x20008030, 0x08004145))

    result = inspect_cfs_image_layout(p)
    assert result["linked_flash"]["base"] == "0x08000000"
    assert result["lower_flash_region"]["bytes_before_application"] == 0
    assert result["lower_flash_region"]["separate_from_application"] is False