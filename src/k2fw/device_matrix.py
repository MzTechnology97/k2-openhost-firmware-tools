from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FirmwareDeviceFamily:
    name: str
    transport: str
    updater: str
    stock_device_type: int | None
    discovery_address: int | None
    explicit_erase: bool | None
    loader_identity_query: str
    sector_query: str | None
    update_request: str
    start_application: str
    runtime_identity: str
    live_loader_entry: str
    recovery_status: str


RS485_FAMILIES = {
    "motor": FirmwareDeviceFamily(
        name="motor",
        transport="RS-485 peripheral bus",
        updater="mcu_util_485",
        stock_device_type=2,
        discovery_address=0xFD,
        explicit_erase=False,
        loader_identity_query="F0/00",
        sector_query="F0/03",
        update_request="F0/01",
        start_application="F0/02",
        runtime_identity="application flash_param_version (parameter id 0)",
        live_loader_entry="not yet proven; stock updater starts with A1 discovery",
        recovery_status=(
            "shared loader/update state machine recovered; loader-entry trigger and "
            "interrupted-write recovery are not yet proven"
        ),
    ),
    "belt": FirmwareDeviceFamily(
        name="belt",
        transport="RS-485 peripheral bus",
        updater="mcu_util_485",
        stock_device_type=3,
        discovery_address=0xFC,
        explicit_erase=False,
        loader_identity_query="F0/00",
        sector_query="F0/03",
        update_request="F0/01",
        start_application="F0/02",
        runtime_identity="not modeled",
        live_loader_entry="not modeled",
        recovery_status="not modeled",
    ),
    "rfid": FirmwareDeviceFamily(
        name="rfid",
        transport="RS-485 peripheral bus",
        updater="mcu_util_485",
        stock_device_type=4,
        discovery_address=0xFB,
        explicit_erase=False,
        loader_identity_query="F0/00",
        sector_query="F0/03",
        update_request="F0/01",
        start_application="F0/02",
        runtime_identity="not modeled",
        live_loader_entry="not modeled",
        recovery_status="not modeled",
    ),
    "cfs": FirmwareDeviceFamily(
        name="cfs",
        transport="RS-485 peripheral bus",
        updater="mcu_util_485",
        stock_device_type=1,
        discovery_address=0xFE,
        explicit_erase=True,
        loader_identity_query="F0/00",
        sector_query="F0/03",
        update_request="F0/01",
        start_application="F0/02",
        runtime_identity="application 0x14 VERSION_SN plus A2 mode",
        live_loader_entry="guarded 0x56 broadcast, hardware-validated",
        recovery_status=(
            "loader identity/sector probe hardware-validated; F0/02 ACK requires "
            "A2 verification and 0B/01 fallback is proven"
        ),
    ),
    "cfs_pro": FirmwareDeviceFamily(
        name="cfs_pro",
        transport="RS-485 peripheral bus",
        updater="mcu_util_485",
        stock_device_type=10,
        discovery_address=0xFE,
        explicit_erase=True,
        loader_identity_query="F0/00",
        sector_query="F0/03",
        update_request="F0/01",
        start_application="F0/02",
        runtime_identity="not hardware-validated",
        live_loader_entry="not hardware-validated",
        recovery_status="new updater generation recognizes device type 10",
    ),
}


DIRECT_MCU_FAMILIES = {
    "main": FirmwareDeviceFamily(
        name="main",
        transport="direct MCU serial",
        updater="mcu_util",
        stock_device_type=None,
        discovery_address=None,
        explicit_erase=None,
        loader_identity_query="00 FF after 0x75 handshake",
        sector_query="03 FC",
        update_request="01 FE",
        start_application="02 FD",
        runtime_identity="running Klipper/Kalico MCU identity",
        live_loader_entry="not yet hardware-validated",
        recovery_status=(
            "direct loader framing recovered offline; exact live loader entry, sector "
            "token and interrupted-write recovery remain gated"
        ),
    ),
    "toolhead": FirmwareDeviceFamily(
        name="toolhead",
        transport="direct MCU serial; also provides transparent RS-485 tunnel",
        updater="mcu_util",
        stock_device_type=None,
        discovery_address=None,
        explicit_erase=None,
        loader_identity_query="00 FF after 0x75 handshake",
        sector_query="03 FC",
        update_request="01 FE",
        start_application="02 FD",
        runtime_identity="running nozzle_mcu Klipper/Kalico identity",
        live_loader_entry="not yet hardware-validated",
        recovery_status=(
            "stock updater explicitly enters/exits transparent mode around RS-485 "
            "peripheral updates; direct loader framing is recovered offline"
        ),
    ),
}


def inspect_device_matrix() -> dict[str, Any]:
    return {
        "schema": 1,
        "scope": "K2 peripheral firmware architecture",
        "rs485": {name: asdict(item) for name, item in RS485_FAMILIES.items()},
        "direct_mcu": {
            name: asdict(item) for name, item in DIRECT_MCU_FAMILIES.items()
        },
        "motor_findings": {
            "current_application_fingerprint": {
                "x": 0x0247,
                "y": 0x0247,
                "e": 0x0247,
                "mapped_application": "mot2_002_071",
            },
            "live_boot_key": {
                "x": 17030,
                "y": 17030,
                "e": 17030,
                "hex": "0x4286",
                "read_only_observation": True,
            },
            "live_system_startup_delay_ms": {"x": 100, "y": 100, "e": 100},
            "live_flash_key_write_retries_num": {"x": 5, "y": 5, "e": 5},
            "boot_parameter_consumption": (
                "boot_key/startup-delay/retry parameters are registered by both 071 "
                "and 081 applications; no direct application-side consumption was "
                "identified, consistent with but not proof of loader-side use"
            ),
            "stock_loader_enumeration": {
                "device_type": 2,
                "discovery_group": "0xfd",
                "discovery_payload": "fdfd",
                "required_mode": 1,
                "stock_expected_count": 2,
                "first_temp_address": "0x85",
                "proven_scope": "two motors on the stock RS-485 enumeration path",
                "extruder_e_equivalence": "not-yet-proven",
            },
            "stock_update_difference": (
                "motors share A1/A0/F0 loader flow with CFS but do not receive the "
                "explicit F0/06 erase command"
            ),
            "loader_entry": (
                "unresolved: stock mcu_util_485 only updates motors already reporting "
                "mode=1; no host-side motor loader-entry command has been recovered"
            ),
            "bootloader_placement": (
                "unresolved; motor application package contains its application token "
                "but not the mot0 hardware/loader token"
            ),
        },
        "toolhead_findings": {
            "package_target": "noz0_130_G30-noz0_021_000.bin",
            "application_token_offset": "0x200",
            "hardware_token_embedded_in_package": False,
            "canboot_katapult_abi": {
                "signature": "0x21746f6f426e6143",
                "signature_offset": "0x3e0",
                "request_start_app": "0x7b06ec45a9a8243d",
                "request_start_app_offset": "0x3e8",
                "request_canboot_present": False,
                "interpretation": (
                    "exact upstream ABI constants are reused; full upstream "
                    "Katapult wire protocol/bootloader identity is not proven"
                ),
            },
            "loader_lifecycle_proven_in_stock_host": True,
        },
        "safety": {
            "motor_loader_entry_enabled": False,
            "motor_write_enabled": False,
            "direct_mcu_loader_entry_enabled": False,
            "direct_mcu_write_enabled": False,
            "flash_allowed": False,
        },
    }