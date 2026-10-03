from pathlib import Path

from k2fw.rs485_update import inspect_rs485_update, stock_data_chunk_sizes


def test_chunk_schedule_aligned_size():
    assert stock_data_chunk_sizes(510) == [248, 255, 7]
    assert sum(stock_data_chunk_sizes(175104)) == 175104
    assert max(stock_data_chunk_sizes(175104)) <= 255


def test_chunk_schedule_remainder_one_uses_252_first():
    sizes = stock_data_chunk_sizes(256)
    assert sizes == [255, 1]

    sizes = stock_data_chunk_sizes(257)
    assert sizes[0] == 252
    assert sum(sizes) == 257


def test_inspection_is_offline_and_never_enables_flash(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G30-cfs0_000_150.bin"
    fw.write_bytes(bytes(range(256)) * 3 + b"x")
    result = inspect_rs485_update(fw)

    assert result["firmware"]["hardware"] == "cfs0_050_G30"
    assert result["firmware"]["application"] == "cfs0_000_150"
    assert result["serial_io_performed"] is False
    assert result["write_enabled"] is False
    assert result["flash_allowed"] is False
    assert [x["stage"] for x in result["stock_protocol"]["sequence"]] == [
        "get_version",
        "erase_flash",
        "update_request",
        "app_stream_begin",
        "app_len",
        "app_data",
        "update_end",
        "start_app",
    ]


def test_start_app_is_not_invented_as_a_transmitted_subcommand(tmp_path: Path):
    fw = tmp_path / "cfs0_050_G32-cfs0_000_150.bin"
    fw.write_bytes(b"x" * 64)
    result = inspect_rs485_update(fw)
    start = result["stock_protocol"]["sequence"][-1]

    assert start["stage"] == "start_app"
    assert start["payload_prefix"] is None
    assert result["recovery_status"]["interrupted_update_recovery"] == "not-yet-proven"