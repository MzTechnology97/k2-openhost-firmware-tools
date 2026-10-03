from __future__ import annotations

from typing import Any

from .cfs_loader import build_any_address_frame
from .rs485_update import (
    CMD_STOCK_FIRMWARE,
    SUB_GET_SECTOR_SIZE,
    SUB_GET_VERSION,
    SUB_START_APP,
)

AUTO_ASSIGN = 0xA0
AUTO_DISCOVER = 0xA1

MOTOR_DEVICE_TYPE = 2
MODE_APPLICATION = 0
MODE_LOADER = 1

MOTOR_DISCOVERY_ADDRESS = 0xFD
MOTOR_DISCOVERY_PAYLOAD = bytes((0xFD, 0xFD))
MOTOR_FIRST_TEMP_ADDRESS = 0x85
STOCK_EXPECTED_MOTOR_COUNT = 2


def parse_motor_auto_mode_payload(payload: bytes) -> dict[str, Any]:
    """Decode the common stock A0/A1/A2 identity payload for a motor."""
    payload = bytes(payload)
    if len(payload) != 14:
        raise ValueError("motor auto-address payload must be 14 bytes")
    device_type, mode = payload[:2]
    if device_type != MOTOR_DEVICE_TYPE:
        raise ValueError("auto-address payload is not a motor device")
    if mode not in (MODE_APPLICATION, MODE_LOADER):
        raise ValueError("motor auto-address payload has an unknown mode")
    uniid = payload[2:]
    if not any(uniid):
        raise ValueError("motor auto-address payload has a zero UniID")
    return {
        "device_type": device_type,
        "mode": mode,
        "mode_name": "loader" if mode == MODE_LOADER else "application",
        "uniid_hex": uniid.hex(),
    }


def inspect_motor_loader_probe(address: int = MOTOR_FIRST_TEMP_ADDRESS) -> dict[str, Any]:
    """Render the proven stock motor-loader probe path without serial I/O.

    Loader entry is deliberately omitted because static analysis has not
    identified a stock host command that moves an already-running motor
    application into loader mode. Stock mcu_util_485 only updates motors
    discovered with mode=1.
    """
    if not 0x85 <= address <= 0xEF:
        raise ValueError("motor temporary loader address must be 0x85..0xef")

    dummy_uid = bytes([0x22]) * 12
    discover = build_any_address_frame(
        MOTOR_DISCOVERY_ADDRESS,
        AUTO_DISCOVER,
        MOTOR_DISCOVERY_PAYLOAD,
    )
    assign = build_any_address_frame(
        MOTOR_DISCOVERY_ADDRESS,
        AUTO_ASSIGN,
        bytes((address,)) + dummy_uid,
    )
    get_version = build_any_address_frame(
        address,
        CMD_STOCK_FIRMWARE,
        bytes((SUB_GET_VERSION,)),
    )
    get_sector = build_any_address_frame(
        address,
        CMD_STOCK_FIRMWARE,
        bytes((SUB_GET_SECTOR_SIZE,)),
    )
    start_app = build_any_address_frame(
        address,
        CMD_STOCK_FIRMWARE,
        bytes((SUB_START_APP,)),
    )

    return {
        "schema": 1,
        "mode": "offline-motor-loader-probe-plan",
        "device_type": MOTOR_DEVICE_TYPE,
        "stock_expected_motor_count": STOCK_EXPECTED_MOTOR_COUNT,
        "assigned_address": address,
        "entry": {
            "loader_entry_command": None,
            "loader_entry_known": False,
            "stock_requirement": "A1/A2 identity mode must already equal 1",
            "stock_behavior": (
                "devices with mode=0 application are not selected for the "
                "firmware-update path"
            ),
            "boot_parameter_evidence": {
                "boot_key": "0x4286 on live X/Y/E",
                "system_startup_delay_ms": 100,
                "flash_key_write_retries_num": 5,
                "host_contains_boot_key_literal": False,
                "interpretation": (
                    "consistent with controller-side boot coordination; the "
                    "loader-entry trigger is not yet proven"
                ),
            },
        },
        "stock_discovery": {
            "group_address": f"0x{MOTOR_DISCOVERY_ADDRESS:02x}",
            "payload_hex": MOTOR_DISCOVERY_PAYLOAD.hex(),
            "frame_hex": discover.hex(),
            "response_payload": "device_type | mode | 12-byte UniID",
            "required_device_type": MOTOR_DEVICE_TYPE,
            "required_mode": MODE_LOADER,
            "first_temp_address": f"0x{MOTOR_FIRST_TEMP_ADDRESS:02x}",
        },
        "sequence": [
            {
                "stage": "discover_existing_loader",
                "command": "A1",
                "frame_hex": discover.hex(),
                "required_mode": MODE_LOADER,
            },
            {
                "stage": "assign_temporary_address",
                "command": "A0",
                "frame_template_hex": assign.hex(),
                "note": "template uses dummy UniID 22*12",
                "state_changing": True,
            },
            {
                "stage": "read_loader_identity",
                "command": "F0/00",
                "frame_hex": get_version.hex(),
            },
            {
                "stage": "read_sector_token",
                "command": "F0/03",
                "frame_hex": get_sector.hex(),
            },
            {
                "stage": "erase_policy",
                "command": None,
                "explicit_f0_06": False,
                "note": (
                    "stock updater skips F0/06 for device type 2; motor-side "
                    "erase/preparation semantics remain unresolved"
                ),
            },
            {
                "stage": "update_request_if_needed",
                "command": "F0/01",
                "rendered_here": False,
                "write_operation": True,
            },
            {
                "stage": "start_application",
                "command": "F0/02",
                "frame_hex": start_app.hex(),
                "state_changing": True,
            },
        ],
        "topology": {
            "stock_bus_motor_count": 2,
            "proven_scope": "two motors enumerated by stock mcu_util_485 (X/Y bus path)",
            "extruder_e": (
                "runtime motor protocol is known through nozzle transparent "
                "transport, but stock loader enumeration equivalence is not "
                "yet proven"
            ),
        },
        "safety": {
            "serial_io_performed": False,
            "loader_entry_performed": False,
            "address_assignment_performed": False,
            "erase_command_present": False,
            "update_request_sent": False,
            "application_data_sent": False,
            "write_enabled": False,
            "send_enabled": False,
            "flash_allowed": False,
        },
    }