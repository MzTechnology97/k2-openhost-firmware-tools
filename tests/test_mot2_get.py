import math
import struct

import pytest

from k2fw.mot2_get import (
    GET_INDEXES,
    GetDecodeError,
    decode_get_payload,
    describe,
    index_matrix,
)


def f32(value):
    return struct.pack("<f", value)


def test_float_fields_are_little_endian_float32():
    r = decode_get_payload(17, f32(48.25))
    assert r["value"] == pytest.approx(48.25) and r["unit"] == "degC"
    assert r["status"] == "verified" and r["valid"] is True
    # big-endian bytes would decode to a different number
    assert decode_get_payload(17, struct.pack(">f", 48.25))["value"] != pytest.approx(48.25)
    assert decode_get_payload(18, f32(24.1))["value"] == pytest.approx(24.1)
    assert decode_get_payload(9, f32(-0.75))["value"] == pytest.approx(-0.75)


def test_integer_fields_are_not_floats():
    # encoder multi-turn count 123456: as float32 it would be a denormal ~1.7e-40
    payload = struct.pack("<i", 123456)
    r = decode_get_payload(16, payload)
    assert r["value"] == 123456 and isinstance(r["value"], int)
    assert struct.unpack("<f", payload)[0] < 1e-30  # what a float decode would give
    assert decode_get_payload(15, struct.pack("<i", -5))["value"] == -5
    assert decode_get_payload(14, struct.pack("<I", 1))["value"] == 1


def test_uint16_field_rejects_upper_bytes():
    with pytest.raises(GetDecodeError):
        decode_get_payload(14, struct.pack("<I", 0x10001))


@pytest.mark.parametrize("length", [0, 2, 3, 5, 8])
def test_length_must_be_four(length):
    with pytest.raises(GetDecodeError):
        decode_get_payload(17, b"\x00" * length)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nan_and_infinity_are_invalid(value):
    r = decode_get_payload(4, f32(value))
    assert r["valid"] is False and r["value"] is None


def test_out_of_scope_and_unsupported_are_refused():
    for index in (11, 12, 13):
        assert describe(index).status == "out-of-scope"
        with pytest.raises(GetDecodeError):
            decode_get_payload(index, b"\x00\x00\x00\x00")
    for index in (19, 25, 255):
        assert describe(index).status == "unsupported"
        with pytest.raises(GetDecodeError):
            decode_get_payload(index, f32(1.0))


def test_zero_index():
    assert decode_get_payload(0, b"\x00\x00\x00\x00")["valid"] is True
    assert decode_get_payload(0, b"\x01\x00\x00\x00")["valid"] is False


def test_matrix_is_closed_and_consistent():
    rows = index_matrix()
    assert [r["index"] for r in rows] == list(range(20))
    assert rows[-1]["status"] == "unsupported"
    assert set(GET_INDEXES) == set(range(19))
    statuses = {r["status"] for r in rows}
    assert statuses <= {"verified", "verified-static", "out-of-scope", "unsupported"}
    # only the temperature has been observed live
    assert [r["index"] for r in rows if r["status"] == "verified"] == [17]
    for r in rows:
        if r["type"] == "float32":
            assert r["unit"] is not None
