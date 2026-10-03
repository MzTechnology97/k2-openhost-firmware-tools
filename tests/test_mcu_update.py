from pathlib import Path

import pytest

from k2fw.mcu_update import (
    CANBOOT_SIGNATURE,
    REQUEST_CANBOOT,
    REQUEST_START_APP,
    direct_mcu_boot_fingerprint,
    build_control,
    build_payload,
    checksum8,
    inspect_mcu_update,
    stock_direct_chunk_size,
    stock_direct_chunk_sizes,
)


def test_direct_control_frames_use_complement_checksum():
    assert checksum8(b"\x00") == 0xFF
    assert checksum8(b"\x01") == 0xFE
    assert build_control(0x00).hex() == "00ff"
    assert build_control(0x01).hex() == "01fe"
    assert build_control(0x02).hex() == "02fd"
    assert build_control(0x03).hex() == "03fc"
    assert build_control(0x04).hex() == "04fb"
    assert build_control(0x05).hex() == "05fa"


def test_direct_sector_token_formula_matches_recovered_sender():
    assert stock_direct_chunk_size(0x01) == 1024
    assert stock_direct_chunk_size(0x04) == 4096
    assert stock_direct_chunk_size(0x11) == 0x4400
    assert stock_direct_chunk_size(0xFF) == 4
    assert stock_direct_chunk_size(0xC0) == 256
    assert stock_direct_chunk_size(0x80) == 512
def test_direct_sector_token_rejects_zero_and_buffer_overflow():
    with pytest.raises(ValueError, match="invalid"):
        stock_direct_chunk_size(0x00)
    with pytest.raises(ValueError, match="0x4400"):
        stock_direct_chunk_size(0x12)


def test_direct_chunk_sizes_cover_entire_image():
    sizes = stock_direct_chunk_sizes(30948, 0x04)
    assert sizes == [4096] * 7 + [2276]
    assert sum(sizes) == 30948


def test_offline_main_inspector_renders_exact_sequence(tmp_path: Path):
    fw = tmp_path / "mcu0_120_G32-mcu0_001_000.bin"
    fw.write_bytes(b"x" * 30948)

    result = inspect_mcu_update(fw)
    controls = result["stock_protocol"]["control_frames"]
    assert controls == {
        "handshake": "75",
        "enter_transparent": "04fb",
        "exit_transparent": "05fa",
        "get_version": "00ff",
        "get_sector_size": "03fc",
        "update_request": "01fe",
        "start_app": "02fd",
    }

    seq = {
        item["stage"]: item
        for item in result["stock_protocol"]["sequence"]
    }
    assert seq["app_len"]["payload_hex"] == "e4780000"
    assert seq["app_len"]["tx_hex"] == build_payload(
        bytes.fromhex("e4780000")
    ).hex()
    assert seq["app_data"]["data_frames_generated"] is False
    chunking = seq["app_data"]["chunking"]
    assert chunking["requires_runtime_sector_token"] is True
    assert chunking["chunk_size"] is None

    assert result["serial_io_performed"] is False
    assert result["write_enabled"] is False
    assert result["send_enabled"] is False
    assert result["flash_allowed"] is False


def test_explicit_sector_token_is_offline_arithmetic_only(tmp_path: Path):
    fw = tmp_path / "noz0_130_G30-noz0_021_000.bin"
    fw.write_bytes(b"x" * 30872)
    result = inspect_mcu_update(fw, sector_token=0x04)

    data = next(
        item for item in result["stock_protocol"]["sequence"]
        if item["stage"] == "app_data"
    )
    chunking = data["chunking"]
    assert chunking["sector_token"] == "0x04"
    assert chunking["sector_token_signed"] == 4
    assert chunking["chunk_size"] == 4096
    assert chunking["chunk_count"] == 8
    assert sum(chunking["chunk_sizes"]) == 30872
    assert result["send_enabled"] is False


def test_direct_inspector_rejects_non_mcu_images(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 64)
    with pytest.raises(ValueError, match="Main/Nozzle"):
        inspect_mcu_update(fw)

def test_direct_mcu_boot_fingerprint_recovers_canboot_abi_magic():
    data = bytearray(b"\x00" * 0x500)
    data[0x3E0:0x3E8] = CANBOOT_SIGNATURE.to_bytes(8, "little")
    data[0x3E8:0x3F0] = REQUEST_START_APP.to_bytes(8, "little")

    result = direct_mcu_boot_fingerprint(bytes(data))
    assert result["canboot_signature"]["offsets"] == ["0x3e0"]
    assert result["request_start_app"]["offsets"] == ["0x3e8"]
    assert result["request_canboot"]["present"] is False
    assert "reuse of CanBoot/Katapult" in result["interpretation"]


def test_direct_mcu_boot_fingerprint_reports_request_canboot_when_present():
    data = REQUEST_CANBOOT.to_bytes(8, "little")
    result = direct_mcu_boot_fingerprint(data)
    assert result["request_canboot"]["offsets"] == ["0x0"]