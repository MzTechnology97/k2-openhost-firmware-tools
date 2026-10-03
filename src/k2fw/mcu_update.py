from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any

from .manifest import parse_firmware_name


CMD_GET_VERSION = 0x00
CMD_UPDATE_REQUEST = 0x01
CMD_START_APP = 0x02
CMD_GET_SECTOR_SIZE = 0x03
CMD_ENTER_TRANSPARENT = 0x04
CMD_EXIT_TRANSPARENT = 0x05

RESP_NACK = 0x1F
RESP_DONE = 0x20
RESP_FAIL = 0x21
RESP_ACK = 0x75

DIRECT_MCU_KINDS = {"main_mcu", "nozzle_mcu"}
STOCK_DATA_BUFFER_SIZE = 0x4400


def checksum8(data: bytes) -> int:
    """Stock mcu_util checksum: one's complement of the uint8 byte sum."""
    return (~sum(data)) & 0xFF


def build_control(command: int) -> bytes:
    if not 0 <= command <= 0xFF:
        raise ValueError("command must be one byte")
    raw = bytes((command,))
    return raw + bytes((checksum8(raw),))


def build_payload(payload: bytes) -> bytes:
    return payload + bytes((checksum8(payload),))
def _signed_byte(raw: int) -> int:
    if not 0 <= raw <= 0xFF:
        raise ValueError("sector token must be one byte")
    return raw if raw < 0x80 else raw - 0x100


def stock_direct_chunk_size(sector_token: int) -> int:
    """Recover mcu_util's file-read size from its signed sector token."""
    signed = _signed_byte(sector_token)
    if signed == 0:
        raise ValueError("stock mcu_util treats sector token 0x00 as invalid")
    chunk = signed * 1024 if signed > 0 else (-signed) * 4
    if chunk > STOCK_DATA_BUFFER_SIZE:
        raise ValueError(
            "sector token exceeds the stock 0x4400-byte checked read buffer"
        )
    return chunk


def stock_direct_chunk_sizes(size: int, sector_token: int) -> list[int]:
    if size < 0:
        raise ValueError("firmware size cannot be negative")
    if size == 0:
        return []
    chunk = stock_direct_chunk_size(sector_token)
    full, tail = divmod(size, chunk)
    result = [chunk] * full
    if tail:
        result.append(tail)
    return result


def _chunking(size: int, sector_token: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "buffer_bytes": STOCK_DATA_BUFFER_SIZE,
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
        sizes = stock_direct_chunk_sizes(size, sector_token)
        result.update({
            "requires_runtime_sector_token": False,
            "chunk_size": stock_direct_chunk_size(sector_token),
            "chunk_count": len(sizes),
            "chunk_sizes": sizes,
        })
    return result
def inspect_mcu_update(
    firmware: str | Path,
    *,
    sector_token: int | None = None,
) -> dict[str, Any]:
    """Describe the recovered direct-serial updater without serial I/O."""
    path = Path(firmware)
    data = path.read_bytes()
    parsed = parse_firmware_name(path.name)
    if parsed["kind"] not in DIRECT_MCU_KINDS or not parsed.get("application"):
        raise ValueError(
            "inspect-mcu-update supports Main/Nozzle direct-MCU images only"
        )

    length_payload = struct.pack("<I", len(data))
    chunking = _chunking(len(data), sector_token)

    return {
        "schema": 1,
        "mode": "offline-static-inspection",
        "firmware": {
            "name": path.name,
            "hardware": parsed["hardware"],
            "application": parsed["application"],
            "kind": parsed["kind"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "stock_protocol": {
            "transport": "direct serial MCU loader",
            "checksum": "ones-complement uint8(sum(payload bytes))",
            "control_frames": {
                "handshake": "75",
                "enter_transparent": build_control(
                    CMD_ENTER_TRANSPARENT
                ).hex(),
                "exit_transparent": build_control(
                    CMD_EXIT_TRANSPARENT
                ).hex(),
                "get_version": build_control(CMD_GET_VERSION).hex(),
                "get_sector_size": build_control(
                    CMD_GET_SECTOR_SIZE
                ).hex(),
                "update_request": build_control(
                    CMD_UPDATE_REQUEST
                ).hex(),
                "start_app": build_control(CMD_START_APP).hex(),
            },
            "sequence": [
                {
                    "stage": "handshake",
                    "tx_hex": "75",
                    "rx": "0x75",
                    "note": (
                        "stock mcu_update runs this as a separate mcu_util -c "
                        "invocation before version/update operations"
                    ),
                },
                {
                    "stage": "get_version",
                    "tx_hex": build_control(CMD_GET_VERSION).hex(),
                    "rx": "25-byte hardware/application identity + checksum",
                },
                {
                    "stage": "get_sector_size",
                    "tx_hex": build_control(CMD_GET_SECTOR_SIZE).hex(),
                    "rx": "one signed sector-token byte + checksum",
                },
                {
                    "stage": "update_request",
                    "tx_hex": build_control(CMD_UPDATE_REQUEST).hex(),
                    "rx": "ACK (0x75) + checksum",
                },
                {
                    "stage": "app_len",
                    "tx_payload": "little-endian uint32 firmware size",
                    "payload_hex": length_payload.hex(),
                    "tx_hex": build_payload(length_payload).hex(),
                    "rx": "ACK (0x75) + checksum",
                },
                {
                    "stage": "app_data",
                    "tx_payload": "raw firmware chunk + checksum",
                    "data_frames_generated": False,
                    "chunking": chunking,
                    "rx": (
                        "ACK/other valid nonterminal reply continues; "
                        "DONE (0x20) finishes; NACK (0x1f) retries; "
                        "FAIL (0x21) aborts"
                    ),
                },
                {
                    "stage": "start_app",
                    "tx_hex": build_control(CMD_START_APP).hex(),
                    "rx": "ACK (0x75) + checksum",
                },
            ],
            "transparent_controls": {
                "enter": build_control(CMD_ENTER_TRANSPARENT).hex(),
                "exit": build_control(CMD_EXIT_TRANSPARENT).hex(),
            },
            "response_codes": {
                "0x1f": "NACK",
                "0x20": "DONE",
                "0x21": "FAIL",
                "0x75": "ACK",
            },
        },
        "old_new_comparison": {
            "core_state_machine": "equivalent",
            "old_release": "1.1.0.94",
            "new_release": "1.1.6.7.2",
            "new_only_transport_option": (
                "-d/--delay: optional microseconds between transmitted bytes"
            ),
            "old_write_behavior": "one write() per frame/chunk",
            "new_write_behavior": (
                "one write() when delay=0; otherwise one write() per byte "
                "with usleep(delay)"
            ),
        },
        "recovery_status": {
            "control_commands": "known",
            "checksum": "known",
            "version_response_length": 26,
            "sector_token_formula": (
                "int8(token)>0 => token*1024 bytes; "
                "int8(token)<0 => abs(token)*4 bytes; zero invalid"
            ),
            "data_chunking": (
                "formula-known-sector-token-required"
                if sector_token is None
                else "resolved-from-explicit-sector-token"
            ),
            "data_retry_behavior": (
                "on data checksum failure or NACK, retry counter increments; "
                "while below three, stock seeks firmware back to offset 0, "
                "re-enters update_request and retransfers from the beginning"
            ),
            "data_fail_behavior": (
                "0x21 FAIL aborts; after three data retry failures the "
                "utility enters its error path"
            ),
            "no_startup_option": (
                "-n/--no-startup suppresses the final 02 fd start-app command"
            ),
            "live_loader_entry_required": True,
        },
        "serial_io_performed": False,
        "write_enabled": False,
        "send_enabled": False,
        "flash_allowed": False,
    }