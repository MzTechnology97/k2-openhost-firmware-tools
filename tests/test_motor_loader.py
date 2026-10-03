import pytest

from k2fw.motor_loader import (
    MODE_APPLICATION,
    MODE_LOADER,
    MOTOR_DEVICE_TYPE,
    inspect_motor_loader_probe,
    parse_motor_auto_mode_payload,
)


def test_motor_auto_mode_payload_decodes_loader_and_application():
    uid = bytes(range(1, 13))

    loader = parse_motor_auto_mode_payload(
        bytes((MOTOR_DEVICE_TYPE, MODE_LOADER)) + uid
    )
    assert loader["device_type"] == 2
    assert loader["mode"] == 1
    assert loader["mode_name"] == "loader"
    assert loader["uniid_hex"] == uid.hex()

    app = parse_motor_auto_mode_payload(
        bytes((MOTOR_DEVICE_TYPE, MODE_APPLICATION)) + uid
    )
    assert app["mode_name"] == "application"


def test_motor_auto_mode_payload_rejects_wrong_type_mode_and_zero_uid():
    uid = bytes(range(1, 13))
    with pytest.raises(ValueError, match="not a motor"):
        parse_motor_auto_mode_payload(bytes((1, 1)) + uid)
    with pytest.raises(ValueError, match="unknown mode"):
        parse_motor_auto_mode_payload(bytes((2, 3)) + uid)
    with pytest.raises(ValueError, match="zero UniID"):
        parse_motor_auto_mode_payload(bytes((2, 1)) + bytes(12))


def test_motor_loader_probe_is_offline_and_omits_unproven_entry():
    result = inspect_motor_loader_probe()
    assert result["device_type"] == 2
    assert result["stock_expected_motor_count"] == 2
    assert result["assigned_address"] == 0x85

    assert result["entry"]["loader_entry_known"] is False
    assert result["entry"]["loader_entry_command"] is None
    assert result["entry"]["stock_requirement"] == "A1/A2 identity mode must already equal 1"

    discovery = result["stock_discovery"]
    assert discovery["group_address"] == "0xfd"
    assert discovery["payload_hex"] == "fdfd"
    assert discovery["required_mode"] == 1
    assert discovery["frame_hex"] == "f7fd0500a1fdfdce"

    seq = {item["stage"]: item for item in result["sequence"]}
    assert seq["assign_temporary_address"]["frame_template_hex"] == (
        "f7fd1000a08522222222222222222222222242"
    )
    assert seq["read_loader_identity"]["frame_hex"] == "f7850400f0004c"
    assert seq["read_sector_token"]["frame_hex"] == "f7850400f00345"
    assert seq["start_application"]["frame_hex"] == "f7850400f00242"
    assert seq["erase_policy"]["explicit_f0_06"] is False
    assert seq["update_request_if_needed"]["rendered_here"] is False

    safety = result["safety"]
    assert safety["serial_io_performed"] is False
    assert safety["loader_entry_performed"] is False
    assert safety["erase_command_present"] is False
    assert safety["update_request_sent"] is False
    assert safety["write_enabled"] is False
    assert safety["send_enabled"] is False
    assert safety["flash_allowed"] is False


def test_motor_loader_probe_rejects_non_stock_temp_address_range():
    with pytest.raises(ValueError, match="0x85"):
        inspect_motor_loader_probe(0x81)