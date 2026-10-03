from __future__ import annotations

from typing import Any

from .rs485 import FRAME_HEAD, crc8
from .rs485_update import CMD_STOCK_FIRMWARE, SUB_GET_SECTOR_SIZE, SUB_GET_VERSION, SUB_START_APP

AUTO_ASSIGN = 0xA0
AUTO_DISCOVER = 0xA1
AUTO_QUERY = 0xA2
LOADER_TO_APP = 0x0B

MODE_APP = 0
MODE_LOADER = 1

ADDRESS_BROADCAST = 0xFE
ADDRESS_GENERAL_BROADCAST = 0xFF
ADDRESS_IAP_BROADCAST = 0xEB

CMD_ENTER_BOOTLOADER = 0x56


def build_any_address_frame(
    address: int,
    command: int,
    payload: bytes = b"",
    *,
    header: int = 0x00,
) -> bytes:
    """Build the Creality RS-485 envelope, including reserved broadcast addresses."""
    if not 0 <= address <= 0xFF:
        raise ValueError("address must be a byte")
    if not 0 <= command <= 0xFF or not 0 <= header <= 0xFF:
        raise ValueError("command/header must be bytes")
    payload = bytes(payload)
    declared_len = len(payload) + 3
    if declared_len > 0xFF:
        raise ValueError("payload is too large")
    body = bytes((address, declared_len, header, command)) + payload
    return bytes((FRAME_HEAD,)) + body + bytes((crc8(body[1:]),))


def parse_auto_mode_payload(payload: bytes) -> dict[str, Any]:
    """Decode the A0/A1/A2 identity payload used by the Jacob CFS driver."""
    payload = bytes(payload)
    if len(payload) != 14:
        raise ValueError("auto-address payload must be 14 bytes")
    device_type, mode = payload[:2]
    if device_type != 1:
        raise ValueError("auto-address payload is not a CFS device")
    if mode not in (MODE_APP, MODE_LOADER):
        raise ValueError("auto-address payload has an unknown mode")
    uniid = payload[2:]
    if not any(uniid):
        raise ValueError("auto-address payload has a zero UniID")
    return {
        "device_type": device_type,
        "mode": mode,
        "mode_name": "loader" if mode == MODE_LOADER else "application",
        "uniid_hex": uniid.hex(),
    }


def inspect_cfs_loader_probe(address: int = 1) -> dict[str, Any]:
    """Describe two non-flash CFS loader workflows without touching serial hardware."""
    if not 1 <= address <= 4:
        raise ValueError("CFS assigned address must be 1..4")

    dummy_uid = bytes([0x11]) * 12
    enter = build_any_address_frame(
        ADDRESS_IAP_BROADCAST, CMD_ENTER_BOOTLOADER, header=0xFF
    )
    discover = build_any_address_frame(
        ADDRESS_BROADCAST, AUTO_DISCOVER,
        bytes((ADDRESS_BROADCAST, ADDRESS_BROADCAST)),
    )
    assign = build_any_address_frame(
        ADDRESS_BROADCAST, AUTO_ASSIGN,
        bytes((address,)) + dummy_uid,
    )
    query = build_any_address_frame(address, AUTO_QUERY)
    get_version = build_any_address_frame(
        address, CMD_STOCK_FIRMWARE, bytes((SUB_GET_VERSION,))
    )
    get_sector = build_any_address_frame(
        address, CMD_STOCK_FIRMWARE, bytes((SUB_GET_SECTOR_SIZE,))
    )
    updater_start_app = build_any_address_frame(
        address, CMD_STOCK_FIRMWARE, bytes((SUB_START_APP,))
    )
    jacob_loader_to_app = build_any_address_frame(
        ADDRESS_GENERAL_BROADCAST, LOADER_TO_APP, b"\x01"
    )

    return {
        "schema": 1,
        "mode": "offline-loader-probe-plan",
        "assigned_address": address,
        "protocol_evidence": {
            "auto_mode_field": {
                "device_type": 1,
                "application": MODE_APP,
                "loader": MODE_LOADER,
            },
            "application_link_base": "0x08010000",
            "lower_region_bytes": 0x10000,
            "stock_ota_power_cycles_before_cfs_update": True,
            "jacob_loader_recovery_present": True,
            "community_active_loader_entry_frame": enter.hex(),
        },
        "paths": {
            "loader_detected_during_normal_enumeration": [
                {
                    "stage": "query_or_discover",
                    "commands": ["A2", "A1"],
                    "purpose": "observe mode=0 application or mode=1 loader",
                },
                {
                    "stage": "assign_if_unaddressed",
                    "command": "A0",
                    "state_changing": True,
                },
                {
                    "stage": "loader_to_app",
                    "command": "0B/01",
                    "frame_hex": jacob_loader_to_app.hex(),
                    "state_changing": True,
                },
                {
                    "stage": "verify_application",
                    "command": "A2",
                    "expected_mode": MODE_APP,
                },
            ],
            "bootloader_identity_probe": [
                {
                    "stage": "enter_loader",
                    "command": "special 0x56 broadcast",
                    "frame_hex": enter.hex(),
                    "provenance": "independent community reconstruction",
                    "state_changing": True,
                },
                {
                    "stage": "discover_loader",
                    "command": "A1",
                    "frame_hex": discover.hex(),
                },
                {
                    "stage": "assign_address",
                    "command": "A0",
                    "frame_template_hex": assign.hex(),
                    "note": "template uses dummy UniID 11*12; a live plan must insert the discovered UniID",
                    "state_changing": True,
                },
                {
                    "stage": "read_boot_identity",
                    "command": "F0/00",
                    "frame_hex": get_version.hex(),
                },
                {
                    "stage": "read_sector_token",
                    "command": "F0/03",
                    "frame_hex": get_sector.hex(),
                },
                {
                    "stage": "start_application",
                    "command": "F0/02",
                    "frame_hex": updater_start_app.hex(),
                    "state_changing": True,
                },
                {
                    "stage": "verify_application",
                    "command": "A2",
                    "frame_hex": query.hex(),
                    "expected_mode": MODE_APP,
                },
            ],
        },
        "safety": {
            "serial_io_performed": False,
            "flash_write_present": False,
            "erase_command_present": False,
            "update_request_present": False,
            "application_data_present": False,
            "state_changing": True,
            "why_state_changing": [
                "loader entry changes execution mode",
                "A0 changes the temporary RS-485 address",
                "start-app changes execution mode",
            ],
            "live_execution_enabled": False,
            "flash_allowed": False,
        },
    }