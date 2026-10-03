from pathlib import Path
import struct

import pytest

from k2fw.rs485_update import (
    RESP_ACK,
    RESP_DONE,
    RESP_FAIL,
    RESP_NACK,
    inspect_rs485_update,
    stock_data_chunk_size,
    stock_data_chunk_sizes,
    stock_update_response_transition,
)


def test_sector_token_drives_chunk_size_not_firmware_length():
    assert stock_data_chunk_size(0xC1) == 252
    assert stock_data_chunk_size(0xFE) == 8
    assert stock_data_chunk_size(0xFF) == 4

    sizes = stock_data_chunk_sizes(175104, 0xC1)
    assert len(sizes) == 695
    assert sizes[0] == 252
    assert sizes[-1] == 216
    assert sum(sizes) == 175104


def test_unusable_sector_tokens_are_rejected():
    for value in (0x00, 0x01, 0x80, 0xC0):
        with pytest.raises(ValueError):
            stock_data_chunk_size(value)


def test_recovered_response_state_machine():
    assert stock_update_response_transition(6, RESP_ACK)["next_state"] == 7
    assert stock_update_response_transition(7, RESP_ACK)["next_state"] == 8

    keep = stock_update_response_transition(8, RESP_ACK)
    assert keep["accepted"] is True
    assert keep["next_state"] == 8

    done = stock_update_response_transition(8, RESP_DONE)
    assert done["accepted"] is True
    assert done["next_state"] == 9
    assert done["next_state_name"] == "update_end"

    failed = stock_update_response_transition(8, RESP_FAIL)
    assert failed["accepted"] is False
    assert failed["next_state"] == 8

    nack = stock_update_response_transition(10, RESP_NACK)
    assert nack["accepted"] is False
    assert nack["next_state"] == 10

    running = stock_update_response_transition(10, RESP_ACK)
    assert running["accepted"] is True
    assert running["next_state"] == 11
    assert running["next_state_name"] == "app_run"


def test_offline_inspector_renders_fixed_cfs_frames_without_sending(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    image = bytearray(175104)
    struct.pack_into("<II", image, 0, 0x20006EE8, 0x0801A759)
    image[0xA758:0xA75C] = b"\x12\x34\x56\x78"
    fw.write_bytes(image)
    result = inspect_rs485_update(fw)

    seq = {item["stage"]: item for item in result["stock_protocol"]["sequence"]}
    assert seq["get_version"]["frame_hex"] == "f7010400f0004c"
    assert seq["get_sector_size"]["frame_hex"] == "f7010400f00345"
    assert seq["erase_flash"]["frame_hex"] == "f7010400f0065e"
    assert seq["update_request"]["frame_hex"] == "f7010400f0014b"
    assert seq["app_len"]["payload_hex"] == "00ac0200"
    assert seq["app_len"]["frame_hex"] == "f7010700f000ac020082"
    assert seq["update_end"]["frame_hex"] is None
    assert seq["start_app"]["frame_hex"] == "f7010400f00242"
    assert seq["app_data"]["frame_hex"] is None
    assert seq["app_data"]["data_frames_generated"] is False

    layout = result["firmware"]["image_layout"]
    assert layout["linked_flash"]["base"] == "0x08010000"
    assert layout["lower_flash_region"]["bytes_before_application"] == 0x10000
    assert result["recovery_status"]["host_flash_address_control"] is False

    assert result["serial_io_performed"] is False
    assert result["write_enabled"] is False
    assert result["send_enabled"] is False
    assert result["flash_allowed"] is False


def test_sector_token_is_unresolved_unless_supplied(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G32-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 175104)

    unresolved = inspect_rs485_update(fw)
    data = next(
        x for x in unresolved["stock_protocol"]["sequence"]
        if x["stage"] == "app_data"
    )
    assert data["chunking"]["requires_runtime_sector_token"] is True
    assert data["chunking"]["chunk_size"] is None
    assert data["chunking"]["chunk_count"] is None

    example = inspect_rs485_update(fw, sector_token=0xC1)
    data = next(
        x for x in example["stock_protocol"]["sequence"]
        if x["stage"] == "app_data"
    )
    assert data["chunking"]["sector_token"] == "0xc1"
    assert data["chunking"]["sector_token_signed"] == -63
    assert data["chunking"]["chunk_size"] == 252
    assert data["chunking"]["chunk_count"] == 695
    assert data["chunking"]["chunk_sizes"][-1] == 216
    assert example["send_enabled"] is False
    assert example["flash_allowed"] is False


def test_f0_02_is_start_app_not_update_end(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 64)
    result = inspect_rs485_update(fw)
    seq = {item["stage"]: item for item in result["stock_protocol"]["sequence"]}

    assert seq["update_end"]["state"] == 9
    assert seq["update_end"]["tx_payload"] is None
    assert seq["start_app"]["state"] == 10
    assert seq["start_app"]["tx_payload"] == [0x02]
    assert seq["start_app"]["frame_hex"] == "f7010400f00242"


def test_sector_token_storage_and_recovery_gates_are_explicit(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 64)
    result = inspect_rs485_update(fw)

    recovery = result["recovery_status"]
    assert recovery["sector_token_storage"] == "known-in-both-forced-receive-handlers"
    assert recovery["fixed_control_frames"] == "known-offline-only"
    assert "skips the later start_app" in recovery["interrupted_transfer_behavior"]
    assert recovery["host_resume_supported"] is False
    assert recovery["host_file_restart_offset"] == 0
    assert "current request/data chunk" in recovery["host_retry_scope"]
    assert "offset 0" in recovery["host_reentry_strategy"]
    assert recovery["device_reentry_after_interruption"].startswith("not-yet-proven")


def test_inspector_is_cfs_only(tmp_path: Path):
    fw = tmp_path / "mot0_023_C30-mot2_002_081.bin"
    fw.write_bytes(b"x" * 64)
    with pytest.raises(ValueError, match="CFS"):
        inspect_rs485_update(fw)