from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .manifest import parse_firmware_name


CMD_STOCK_FIRMWARE = 0xF0
SUB_GET_VERSION = 0x00
SUB_APP_STREAM = 0x01
SUB_UPDATE_END = 0x02
SUB_ERASE_FLASH = 0x03
SUB_UPDATE_REQUEST = 0x06
MAX_DATA_CHUNK = 0xFF
FIRST_ALIGNMENT = 0xFC


def stock_data_chunk_sizes(size: int) -> list[int]:
    """Recover the stock mcu_util_485 firmware read/chunk schedule.

    Static analysis shows a 255-byte transfer buffer.  When firmware_size % 4
    is non-zero, the first read is shortened to (remainder * 0xfc) & 0xff,
    i.e. 252/248/244 bytes for remainders 1/2/3.  Remaining reads are 255
    bytes, with the final read naturally shorter at EOF.
    """
    if size < 0:
        raise ValueError("firmware size cannot be negative")
    if size == 0:
        return []

    remainder = size % 4
    first = (remainder * FIRST_ALIGNMENT) & 0xFF if remainder else MAX_DATA_CHUNK
    chunks: list[int] = []
    remaining = size
    while remaining:
        amount = min(first if not chunks else MAX_DATA_CHUNK, remaining)
        chunks.append(amount)
        remaining -= amount
    return chunks


def inspect_rs485_update(firmware: str | Path) -> dict[str, Any]:
    """Build an offline description of the recovered stock update sequence.

    This function never opens a serial port and never emits an RS-485 frame.
    """
    path = Path(firmware)
    data = path.read_bytes()
    parsed = parse_firmware_name(path.name)
    if parsed is None:
        raise ValueError("firmware filename is not hardware-application.bin form")

    sizes = stock_data_chunk_sizes(len(data))
    return {
        "schema": 1,
        "mode": "offline-static-inspection",
        "firmware": {
            "name": path.name,
            "hardware": parsed["hardware"],
            "application": parsed["application"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "stock_protocol": {
            "command": CMD_STOCK_FIRMWARE,
            "sequence": [
                {"stage": "get_version", "payload_prefix": [SUB_GET_VERSION]},
                {"stage": "erase_flash", "payload_prefix": [SUB_ERASE_FLASH]},
                {"stage": "update_request", "payload_prefix": [SUB_UPDATE_REQUEST]},
                {"stage": "app_stream_begin", "payload_prefix": [SUB_APP_STREAM]},
                {
                    "stage": "app_len",
                    "encoding": "little-endian uint32",
                    "value": len(data),
                },
                {
                    "stage": "app_data",
                    "chunk_count": len(sizes),
                    "chunk_sizes": sizes,
                    "max_chunk": MAX_DATA_CHUNK,
                },
                {"stage": "update_end", "payload_prefix": [SUB_UPDATE_END]},
                {
                    "stage": "start_app",
                    "payload_prefix": None,
                    "note": (
                        "stock receive-state strings distinguish update_end/start_app; "
                        "no independent transmitted start-app subcommand is claimed yet"
                    ),
                },
            ],
            "retry_limit_observed": 3,
            "request_timeout_ms_observed": 500,
        },
        "recovery_status": {
            "frame_envelope": "known",
            "state_order": "known",
            "subcommands": "known",
            "data_chunking": "known-from-static-analysis",
            "ack_semantics": "partial",
            "interrupted_update_recovery": "not-yet-proven",
        },
        "serial_io_performed": False,
        "write_enabled": False,
        "flash_allowed": False,
    }