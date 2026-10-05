"""MOT2 motor controller GET (function 0x08) index map and payload parser.

Recovered statically from the GET handler of the four analysed K2 Pro motor
images (071 and 081, F012 ``mot*_022`` and ``motor/mot*_021/023`` profiles),
see ``docs/MOT2_GET_READINGS.md``. The handler answers one byte of index with
four little-endian bytes copied from a firmware field. The field type decides
the decoding: some indices carry float32 bits, others integers. Decoding every
index as float (as the Kalico client does today for its only user, index 17)
is wrong for the integer ones.

Statuses:
- ``verified``: field, type and unit proven, and the value observed live;
- ``verified-static``: field and type proven in every analysed image; the
  unit follows from the code; the live value is not yet observed;
- ``out-of-scope``: step-pulse input / subdivision domain, excluded by the
  project owner, not analysed and refused by the parser;
- ``unsupported``: no handler case (index >= 19): the firmware returns the
  previous answer unchanged, so the bytes mean nothing.

Nothing here performs I/O. Reading these values on the printer needs the
supervised procedure in the documentation.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class GetIndex:
    index: int
    name: str
    kind: str  # "float32", "int32", "uint16", "zero"
    unit: str | None
    unit_status: str  # "proven", "candidate", "n/a"
    status: str
    source: str
    note: str = ""


_CTRL = "controller object (system +4)"
_SYS = "system object"
_ENC = "encoder object (system +0xc)"
_DRV = "driver board object (system +8)"

GET_INDEXES: dict[int, GetIndex] = {i.index: i for i in (
    GetIndex(0, "zero", "zero", None, "n/a", "verified-static",
             "constant 0 in the handler"),
    GetIndex(1, "pos_ref", "float32", "rad", "candidate", "verified-static",
             _CTRL + " +0x118: position PID reference",
             "position PID error is compared with stall_pos_err_rad"),
    GetIndex(2, "spd_ref", "float32", "rad/s", "candidate", "verified-static",
             _CTRL + " +0x1e4: speed PID reference"),
    GetIndex(3, "id_ref", "float32", "A", "candidate", "verified-static",
             _CTRL + " +0x2b0: first current PID reference",
             "d axis by elimination: the other current loop is the one checked "
             "against stall_cur_A"),
    GetIndex(4, "iq_ref", "float32", "A", "proven", "verified-static",
             _CTRL + " +0x37c: second current PID reference",
             "compared directly with stall_cur_A by the stall detector"),
    GetIndex(5, "pos_fdb", "float32", "rad", "candidate", "verified-static",
             _CTRL + " +0x11c: position PID feedback"),
    GetIndex(6, "spd_fdb", "float32", "rad/s", "candidate", "verified-static",
             _CTRL + " +0x1e8: speed PID feedback"),
    GetIndex(7, "id_fdb", "float32", "A", "candidate", "verified-static",
             _CTRL + " +0x2b4: first current PID feedback"),
    GetIndex(8, "iq_fdb", "float32", "A", "proven", "verified-static",
             _CTRL + " +0x380: second current PID feedback"),
    GetIndex(9, "phase_current_a", "float32", "A", "proven", "verified-static",
             _CTRL + " +0x7c: ADC channel 0 minus offset, x Vref/4096 / "
             "(amp_gain x R_shunt)"),
    GetIndex(10, "phase_current_b", "float32", "A", "proven", "verified-static",
             _CTRL + " +0x80: ADC channel 1, same scaling, sign +/-1 from a "
             "system flag"),
    GetIndex(11, "step_input_11", "int32", None, "n/a", "out-of-scope",
             _SYS + " step-pulse input object field",
             "subdivision domain: excluded"),
    GetIndex(12, "step_input_12", "uint16", None, "n/a", "out-of-scope",
             _SYS + " step-pulse input object field",
             "subdivision domain: excluded"),
    GetIndex(13, "step_input_13", "uint16", None, "n/a", "out-of-scope",
             _SYS + " step-pulse input object field",
             "subdivision domain: excluded"),
    GetIndex(14, "stall_detected", "uint16", None, "n/a", "verified-static",
             _SYS + " +0x38 (071) / +0x40 (081): set to 1 by the stall "
             "detector, 0 when cleared"),
    GetIndex(15, "encoder_single_turn", "int32", "counts", "proven",
             "verified-static", _ENC + " +0x24: position within one turn",
             "counts per turn are the encoder resolution field, not decoded here"),
    GetIndex(16, "encoder_multi_turn", "int32", "counts", "proven",
             "verified-static", _ENC + " +0x2c: turns x resolution + "
             "single-turn count"),
    GetIndex(17, "mcu_temperature", "float32", "degC", "proven", "verified",
             _DRV + " +0x4c: internal sensor with the factory calibration "
             "word at 0x1ffff720",
             "polled by Kalico (motor_control GET_MCU_TEMP_INDEX)"),
    GetIndex(18, "supply_voltage", "float32", "V", "proven", "verified-static",
             _DRV + " +0x48: ADC x Vref x divider / 4096"),
)}

MAX_HANDLED_INDEX = 18


class GetDecodeError(ValueError):
    pass


def describe(index: int) -> GetIndex:
    if index in GET_INDEXES:
        return GET_INDEXES[index]
    return GetIndex(index, f"unsupported_{index}", "none", None, "n/a",
                    "unsupported", "no handler case: the previous answer is "
                    "returned unchanged")


def decode_get_payload(index: int, payload: bytes) -> dict:
    """Decode one GET answer payload for a proven format.

    Returns ``{"index", "name", "value", "unit", "status", "valid"}``.
    ``valid`` is False for NaN or infinity (the value is kept as None).
    Raises GetDecodeError for a wrong length, an out-of-scope or unsupported
    index, or integer bytes that cannot belong to the field.
    """
    info = describe(int(index))
    if info.status in ("unsupported", "out-of-scope"):
        raise GetDecodeError(f"GET index {index} is {info.status}: not decoded")
    raw = bytes(payload)
    if len(raw) != 4:
        raise GetDecodeError(f"GET payload must be 4 bytes, got {len(raw)}")
    valid = True
    if info.kind == "float32":
        value = struct.unpack("<f", raw)[0]
        if math.isnan(value) or math.isinf(value):
            value, valid = None, False
    elif info.kind == "int32":
        value = struct.unpack("<i", raw)[0]
    elif info.kind == "uint16":
        word = struct.unpack("<I", raw)[0]
        if word > 0xFFFF:
            raise GetDecodeError(
                f"GET index {index} is a 16-bit field; upper bytes must be 0")
        value = word
    elif info.kind == "zero":
        value = struct.unpack("<I", raw)[0]
        valid = value == 0
    else:  # pragma: no cover - table is closed
        raise GetDecodeError(f"unknown kind {info.kind}")
    return {"index": info.index, "name": info.name, "value": value,
            "unit": info.unit, "status": info.status, "valid": valid}


def index_matrix() -> list[dict]:
    """The full matrix (0..19) as plain dicts, for documentation and JSON."""
    rows = []
    for index in range(MAX_HANDLED_INDEX + 2):
        info = describe(index)
        rows.append({
            "index": info.index, "name": info.name, "type": info.kind,
            "unit": info.unit, "unit_status": info.unit_status,
            "status": info.status, "source": info.source, "note": info.note,
        })
    return rows
