from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any

from .manifest import parse_firmware_name
from .cfs_image import inspect_cfs_image_layout
from .rs485 import build_frame


CMD_STOCK_FIRMWARE = 0xF0

SUB_GET_VERSION = 0x00
SUB_UPDATE_REQUEST = 0x01
SUB_START_APP = 0x02
SUB_GET_SECTOR_SIZE = 0x03
SUB_ERASE_FLASH = 0x06

RESP_NACK = 0x1F
RESP_DONE = 0x20
RESP_FAIL = 0x21
RESP_ACK = 0x75
RESP_NONE = 0xFF

RESPONSE_NAMES = {
    RESP_NACK: "NACK",
    RESP_DONE: "DONE",
    RESP_FAIL: "FAIL",
    RESP_ACK: "ACK",
    RESP_NONE: "NONE",
}

STATE_NAMES = {
    0: "unknown",
    1: "get_salve_info",
    2: "set_salve_addr",
    3: "get_version",
    4: "get_sector_size",
    5: "erase_flash",
    6: "update_request",
    7: "app_len",
    8: "app_data",
    9: "update_end",
    10: "start_app",
    11: "app_run",
    12: "end",
    13: "error",
    14: "timeout",
}

STOCK_DATA_BUFFER_SIZE = 0xFF
STOCK_FRAME_MAX_PAYLOAD = 0xFC
STOCK_HEADER = 0x00


def _signed_byte(raw: int) -> int:
    if not 0 <= raw <= 0xFF:
        raise ValueError("sector token must be one byte")
    return raw if raw < 0x80 else raw - 0x100


def stock_data_chunk_size(sector_token: int) -> int:
    """Recover the stock updater's read size from the sector-size response byte."""
    signed = _signed_byte(sector_token)
    if signed == 0:
        raise ValueError("stock updater treats sector token 0x00 as invalid")
    if signed > 0:
        raise ValueError(
            "positive sector token reaches a zero-length stock read; "
            "no usable chunk size can be claimed"
        )
    chunk = (signed * STOCK_FRAME_MAX_PAYLOAD) & 0xFF
    if chunk == 0 or chunk > STOCK_FRAME_MAX_PAYLOAD:
        raise ValueError(
            f"sector token 0x{sector_token:02x} does not produce a usable stock chunk size"
        )
    return chunk


def stock_data_chunk_sizes(size: int, sector_token: int) -> list[int]:
    if size < 0:
        raise ValueError("firmware size cannot be negative")
    if size == 0:
        return []
    chunk = stock_data_chunk_size(sector_token)
    full, tail = divmod(size, chunk)
    sizes = [chunk] * full
    if tail:
        sizes.append(tail)
    return sizes


def stock_update_response_transition(state: int, response_code: int) -> dict[str, Any]:
    """Model the state changes in the recovered F0 receive handler."""
    if state not in STATE_NAMES:
        raise ValueError(f"unknown stock updater state {state}")
    if not 0 <= response_code <= 0xFF:
        raise ValueError("response code must be one byte")

    next_state = state
    accepted = False
    terminal = False

    if state == 6:
        accepted = response_code == RESP_ACK
        if accepted:
            next_state = 7
    elif state == 7:
        accepted = response_code == RESP_ACK
        if accepted:
            next_state = 8
    elif state == 8:
        if response_code == RESP_ACK:
            accepted = True
        elif response_code == RESP_DONE:
            accepted = True
            terminal = True
            next_state = 9
    elif state == 10:
        accepted = response_code == RESP_ACK
        if accepted:
            terminal = True
            next_state = 11

    return {
        "state": state,
        "state_name": STATE_NAMES[state],
        "response_code": response_code,
        "response_name": RESPONSE_NAMES.get(response_code, "UNKNOWN"),
        "accepted": accepted,
        "terminal": terminal,
        "next_state": next_state,
        "next_state_name": STATE_NAMES[next_state],
    }


def _control_frame_hex(address: int, payload: bytes) -> str:
    return build_frame(
        address, CMD_STOCK_FIRMWARE, payload, header=STOCK_HEADER
    ).hex()


def inspect_rs485_update(
    firmware: str | Path,
    *,
    address: int = 1,
    sector_token: int | None = None,
) -> dict[str, Any]:
    """Build an offline description of the recovered stock update sequence."""
    path = Path(firmware)
    data = path.read_bytes()
    parsed = parse_firmware_name(path.name)
    if parsed["kind"] != "cfs" or not parsed.get("application"):
        raise ValueError(
            "inspect-update currently supports exact CFS firmware images only"
        )

    chunking: dict[str, Any] = {
        "buffer_bytes": STOCK_DATA_BUFFER_SIZE,
        "frame_payload_limit": STOCK_FRAME_MAX_PAYLOAD,
        "sector_token": (
            f"0x{sector_token:02x}" if sector_token is not None else None
        ),
        "sector_token_signed": (
            _signed_byte(sector_token) if sector_token is not None else None
        ),
        "requires_runtime_sector_token": sector_token is None,
        "chunk_size": None,
        "chunk_count": None,
        "chunk_sizes": None,
    }
    if sector_token is not None:
        sizes = stock_data_chunk_sizes(len(data), sector_token)
        chunking.update(
            {
                "requires_runtime_sector_token": False,
                "chunk_size": stock_data_chunk_size(sector_token),
                "chunk_count": len(sizes),
                "chunk_sizes": sizes,
            }
        )

    return {
        "schema": 2,
        "mode": "offline-static-inspection",
        "address": address,
        "firmware": {
            "name": path.name,
            "hardware": parsed["hardware"],
            "application": parsed["application"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "image_layout": inspect_cfs_image_layout(path),
        },
        "stock_protocol": {
            "command": CMD_STOCK_FIRMWARE,
            "header": STOCK_HEADER,
            "response_codes": {
                f"0x{code:02x}": name for code, name in RESPONSE_NAMES.items()
            },
            "states": STATE_NAMES,
            "sequence": [
                {
                    "state": 3,
                    "stage": "get_version",
                    "tx_payload": [SUB_GET_VERSION],
                    "frame_hex": _control_frame_hex(address, bytes((SUB_GET_VERSION,))),
                    "rx": "25-byte hardware-application identity",
                },
                {
                    "state": 4,
                    "stage": "get_sector_size",
                    "tx_payload": [SUB_GET_SECTOR_SIZE],
                    "frame_hex": _control_frame_hex(address, bytes((SUB_GET_SECTOR_SIZE,))),
                    "rx": (
                        "response[9] one-byte sector token; both forced receive "
                        "handlers store it in the field later loaded with LDRSB"
                    ),
                },
                {
                    "state": 5,
                    "stage": "erase_flash",
                    "tx_payload": [SUB_ERASE_FLASH],
                    "frame_hex": _control_frame_hex(address, bytes((SUB_ERASE_FLASH,))),
                    "rx": "status byte; handler logs it without a state transition",
                },
                {
                    "state": 6,
                    "stage": "update_request",
                    "tx_payload": [SUB_UPDATE_REQUEST],
                    "frame_hex": _control_frame_hex(address, bytes((SUB_UPDATE_REQUEST,))),
                    "rx": "ACK advances to app_len",
                },
                {
                    "state": 7,
                    "stage": "app_len",
                    "tx_payload": "little-endian uint32 firmware size",
                    "value": len(data),
                    "payload_hex": struct.pack("<I", len(data)).hex(),
                    "frame_hex": _control_frame_hex(
                        address, struct.pack("<I", len(data))
                    ),
                    "rx": "ACK advances to app_data",
                },
                {
                    "state": 8,
                    "stage": "app_data",
                    "tx_payload": "raw firmware chunk",
                    "frame_hex": None,
                    "data_frames_generated": False,
                    "chunking": chunking,
                    "rx": "ACK keeps app_data; DONE advances to update_end",
                },
                {
                    "state": 9,
                    "stage": "update_end",
                    "tx_payload": None,
                    "frame_hex": None,
                    "note": "receive-side state reached when final app_data reply is DONE",
                },
                {
                    "state": 10,
                    "stage": "start_app",
                    "tx_payload": [SUB_START_APP],
                    "frame_hex": _control_frame_hex(address, bytes((SUB_START_APP,))),
                    "rx": "ACK advances to app_run",
                },
                {
                    "state": 11,
                    "stage": "app_run",
                    "tx_payload": None,
                    "frame_hex": None,
                },
            ],
            "transport_retry_limit_observed": 3,
            "request_timeout_ms_observed": 500,
            "retry_trigger": (
                "transport timeout/no response; a protocol NACK/FAIL still wakes "
                "the sender and is handled by state validation"
            ),
        },
        "recovery_status": {
            "frame_envelope": "known",
            "state_order": "known",
            "subcommands": "known",
            "response_code_names": "known",
            "ack_state_transitions": "known",
            "sector_token_storage": "known-in-both-forced-receive-handlers",
            "fixed_control_frames": "known-offline-only",
            "data_chunking": (
                "formula-known-sector-token-required"
                if sector_token is None
                else "resolved-from-explicit-sector-token"
            ),
            "interrupted_transfer_behavior": (
                "if app_data does not reach state 9/update_end, stock marks the "
                "device failed and skips the later start_app command for that device"
            ),
            "host_resume_supported": False,
            "host_file_restart_offset": 0,
            "host_retry_scope": (
                "the current request/data chunk is retried up to three times; "
                "there is no recovered host-side resume offset or checkpoint"
            ),
            "host_reentry_strategy": (
                "a fresh updater invocation reopens the image and seeks to offset 0, "
                "then repeats discovery/version/sector/erase/update from the beginning"
            ),
            "host_flash_address_control": False,
            "host_flash_address_note": (
                "recovered erase/update/data transactions carry no destination flash "
                "address; placement is controlled by the peripheral loader"
            ),
            "device_reentry_after_interruption": (
                "not-yet-proven: application layout is consistent with a separate "
                "lower-flash loader region, but static host/application analysis does "
                "not prove loader fallback after every interrupted erase/write"
            ),
        },
        "serial_io_performed": False,
        "write_enabled": False,
        "send_enabled": False,
        "flash_allowed": False,
    }