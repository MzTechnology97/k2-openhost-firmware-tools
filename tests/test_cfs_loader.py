import pytest

from k2fw.cfs_loader import (
    MODE_APP,
    MODE_LOADER,
    build_any_address_frame,
    inspect_cfs_loader_probe,
    parse_auto_mode_payload,
)


def test_reserved_broadcast_frames_are_rendered_exactly():
    result = inspect_cfs_loader_probe()
    path = result["paths"]["bootloader_identity_probe"]
    stages = {item["stage"]: item for item in path}

    assert stages["enter_loader"]["frame_hex"] == "f7eb03ff56cf"
    assert stages["discover_loader"]["frame_hex"] == "f7fe0500a1fefef8"
    assert stages["read_boot_identity"]["frame_hex"] == "f7010400f0004c"
    assert stages["read_sector_token"]["frame_hex"] == "f7010400f00345"
    assert stages["start_application"]["frame_hex"] == "f7010400f00242"


def test_jacob_loader_to_app_broadcast_is_rendered():
    result = inspect_cfs_loader_probe()
    path = result["paths"]["loader_detected_during_normal_enumeration"]
    stage = next(item for item in path if item["stage"] == "loader_to_app")
    assert stage["frame_hex"] == "f7ff04000b01c8"


def test_probe_plan_contains_no_flash_mutation():
    result = inspect_cfs_loader_probe()
    safety = result["safety"]

    assert safety["serial_io_performed"] is False
    assert safety["flash_write_present"] is False
    assert safety["erase_command_present"] is False
    assert safety["update_request_present"] is False
    assert safety["application_data_present"] is False
    assert safety["state_changing"] is True
    assert safety["live_execution_enabled"] is False
    assert safety["flash_allowed"] is False


def test_auto_mode_payload_decodes_app_and_loader():
    uid = bytes(range(1, 13))

    app = parse_auto_mode_payload(bytes((1, MODE_APP)) + uid)
    assert app["mode_name"] == "application"
    assert app["uniid_hex"] == uid.hex()

    loader = parse_auto_mode_payload(bytes((1, MODE_LOADER)) + uid)
    assert loader["mode_name"] == "loader"


def test_auto_mode_payload_rejects_invalid_shapes():
    with pytest.raises(ValueError):
        parse_auto_mode_payload(b"short")
    with pytest.raises(ValueError):
        parse_auto_mode_payload(bytes((2, MODE_APP)) + bytes(range(1, 13)))
    with pytest.raises(ValueError):
        parse_auto_mode_payload(bytes((1, 7)) + bytes(range(1, 13)))
    with pytest.raises(ValueError):
        parse_auto_mode_payload(bytes((1, MODE_APP)) + bytes(12))


def test_any_address_frame_allows_reserved_addresses():
    assert build_any_address_frame(0xFF, 0x0B, b"\x01").hex() == "f7ff04000b01c8"
    assert build_any_address_frame(0xEB, 0x56, header=0xFF).hex() == "f7eb03ff56cf"