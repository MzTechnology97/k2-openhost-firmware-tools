from pathlib import Path

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


def test_sector_token_drives_chunk_size_not_firmware_remainder():
    assert stock_data_chunk_size(0xC1) == 252
    assert stock_data_chunk_sizes(510, 0xC1) == [252, 252, 6]
    assert stock_data_chunk_sizes(257, 0xC1) == [252, 5]


def test_unusable_sector_tokens_are_rejected():
    with pytest.raises(ValueError):
        stock_data_chunk_size(0x00)
    with pytest.raises(ValueError):
        stock_data_chunk_size(0x01)
    with pytest.raises(ValueError):
        stock_data_chunk_size(0xC0)


def test_recovered_response_state_machine():
    assert stock_update_response_transition(6, RESP_ACK)["next_state"] == 7
    assert stock_update_response_transition(7, RESP_ACK)["next_state"] == 8

    keep = stock_update_response_transition(8, RESP_ACK)
    assert keep["next_state"] == 8
    assert keep["accepted"] is True

    done = stock_update_response_transition(8, RESP_DONE)
    assert done["next_state"] == 9
    assert done["next_state_name"] == "update_end"
    assert done["terminal"] is True

    failed = stock_update_response_transition(8, RESP_FAIL)
    assert failed["next_state"] == 8
    assert failed["accepted"] is False

    nack = stock_update_response_transition(10, RESP_NACK)
    assert nack["next_state"] == 10
    assert nack["accepted"] is False

    running = stock_update_response_transition(10, RESP_ACK)
    assert running["next_state"] == 11
    assert running["next_state_name"] == "app_run"


def test_inspection_without_sector_token_does_not_invent_chunks(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 1024)
    result = inspect_rs485_update(fw)

    data = next(
        x for x in result["stock_protocol"]["sequence"] if x["stage"] == "app_data"
    )
    assert data["chunking"]["requires_runtime_sector_token"] is True
    assert data["chunking"]["chunk_size"] is None
    assert data["chunking"]["chunk_count"] is None
    assert result["serial_io_performed"] is False
    assert result["write_enabled"] is False
    assert result["flash_allowed"] is False


def test_inspection_with_explicit_sector_token_is_still_offline(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G32-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 510)
    result = inspect_rs485_update(fw, sector_token=0xC1)

    stages = result["stock_protocol"]["sequence"]
    assert [(x["stage"], x["tx_payload"]) for x in stages if "tx_payload" in x][:5] == [
        ("get_version", [0x00]),
        ("get_sector_size", [0x03]),
        ("erase_flash", [0x06]),
        ("update_request", [0x01]),
        ("app_len", "little-endian uint32 firmware size"),
    ]
    data = next(x for x in stages if x["stage"] == "app_data")
    assert data["chunking"]["chunk_size"] == 252
    assert data["chunking"]["chunk_sizes"] == [252, 252, 6]
    start = next(x for x in stages if x["stage"] == "start_app")
    assert start["tx_payload"] == [0x02]
    assert result["serial_io_performed"] is False
    assert result["flash_allowed"] is False


def test_interrupted_transfer_risk_is_explicit(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 64)
    result = inspect_rs485_update(fw)
    recovery = result["recovery_status"]

    assert "skips the later start_app" in recovery["interrupted_transfer_behavior"]
    assert recovery["updater_reentry_after_interruption"] == "not-yet-proven"