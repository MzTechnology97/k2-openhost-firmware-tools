import pytest

from k2fw.live import (
    KNOWN_MOTOR_FLASH_PARAM_VERSIONS,
    parse_motor_flash_readback,
)


def test_motor_fingerprint_maps_known_071_and_081():
    assert KNOWN_MOTOR_FLASH_PARAM_VERSIONS[583] == "mot2_002_071"
    assert KNOWN_MOTOR_FLASH_PARAM_VERSIONS[587] == "mot2_002_081"


def test_parse_motor_flash_readback_uses_last_matching_command():
    command = "MOTOR_READ_PARAM PARAM=x_param_flash_param_version"
    messages = [
        command,
        "// Flash readback=518",
        command,
        "// Warning: read only",
        "// Live readback=583",
        "// Flash readback=583",
    ]
    assert parse_motor_flash_readback(messages, command) == 583


def test_parse_motor_flash_readback_does_not_cross_next_motor_command():
    x = "MOTOR_READ_PARAM PARAM=x_param_flash_param_version"
    y = "MOTOR_READ_PARAM PARAM=y_param_flash_param_version"
    with pytest.raises(RuntimeError, match="no flash readback"):
        parse_motor_flash_readback([x, "// Live readback=583", y, "// Flash readback=583"], x)
