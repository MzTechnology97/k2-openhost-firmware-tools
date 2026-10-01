import pytest

from k2fw.rs485 import (
    build_stock_version_request,
    parse_stock_version_payload,
)


def test_stock_version_request_is_exact_read_only_f0_00_frame():
    # address 0x81, header/status byte 0, command F0, payload 00.
    assert build_stock_version_request(0x81).hex() == "f7810400f0004c"


def test_stock_motor_version_payload_decodes_exact_identity():
    result = parse_stock_version_payload(b"mot0_023_C30-mot2_002_071")
    assert result == {
        "version": "mot0_023_C30-mot2_002_071",
        "hardware": "mot0_023_C30",
        "application": "mot2_002_071",
    }


def test_stock_cfs_version_payload_decodes_exact_identity():
    result = parse_stock_version_payload(b"cfs0_050_G30-cfs0_000_113")
    assert result["hardware"] == "cfs0_050_G30"
    assert result["application"] == "cfs0_000_113"


def test_stock_version_parser_refuses_wrong_length():
    with pytest.raises(ValueError, match="25 bytes"):
        parse_stock_version_payload(b"mot2_002_071")
