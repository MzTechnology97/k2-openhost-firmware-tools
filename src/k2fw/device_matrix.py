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


TUNNELED_P2P_FAMILIES = {
    "extruder": FirmwareDeviceFamily(
        name="extruder",
        transport="P2P loader tunneled through Nozzle transparent mode",
        updater="Jacob K2 Plus motor_updater.py reference",
        stock_device_type=None,
        discovery_address=None,
        explicit_erase=None,
        loader_identity_query="00 FF after Nozzle 04 FB transparent mode",
        sector_query="03 FC",
        update_request="01 FE",
        start_application="not explicitly sent by the Jacob reference updater",
        runtime_identity="application flash_param_version through motor-control protocol",
        live_loader_entry=(
            "Jacob K2 Plus reference relies on shared MCU-rail power-on before "
            "Nozzle transparent mode; K2 Pro equivalence is not yet proven"
        ),
        recovery_status=(
            "reference updater uses the direct P2P checksum/data protocol with a "
            "256-byte extruder chunk override; K2 Pro stock path remains gated"
        ),
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
        "tunneled_p2p": {
            name: asdict(item) for name, item in TUNNELED_P2P_FAMILIES.items()
        },
        "jacob_k2_plus_reference": {
            "provenance": {
                "artifact": "motor_updater.py from Jacob K2 Plus custom rootfs",
                "sha256": "0ba8d5fad79029ebbe16b907b0fb06d547d77a693a0265076025c723a52b3d62",
                "scope": "reference implementation; model-specific counts/targets are not K2 Pro facts",
            },
            "boot_orchestration": {
                "systemd_stage": "sysinit.target",
                "klipper_ordering": "klipper.service starts After=motor-updater.service",
                "gpio": 140,
                "gpio_name": "MCU_PWR_EN",
                "active_low": True,
                "script_claims_kernel_boots_rail_off": True,
                "default_action": "set rail ON then wait 1.0 s before updater threads",
                "optional_power_cycle": "1.0 s OFF, then ON, then 1.0 s settle",
                "implication": (
                    "reference design expects loaders to remain reachable after "
                    "hardware power-on; no application-side loader-entry command is used"
                ),
            },
            "parallel_transports": {
                "rs485": {"port": "ttyS5", "baud": 230400},
                "main_p2p": {"port": "ttyS2", "baud": 115200},
                "nozzle_p2p": {"port": "ttyS3", "baud": 115200},
            },
            "p2p_protocol": {
                "handshake": "75 -> 75",
                "ack": "75 8a",
                "final_done": "20 df",
                "get_version": "00 ff",
                "get_sector": "03 fc",
                "update_request": "01 fe",
                "start_app": "02 fd",
                "enter_transparent": "04 fb",
                "exit_transparent": "05 fa",
                "chunk_checksum": "ones-complement uint8 sum",
                "positive_sector_chunk_formula": "sector_byte * 1024",
            },
            "extruder": {
                "path": "Nozzle P2P -> 04 fb transparent -> extruder P2P",
                "separate_0x75_handshake_in_reference": False,
                "version_query": "00 ff",
                "chunk_override": 256,
                "explicit_start_app_after_extruder_update": False,
                "k2_pro_equivalence": "not-yet-proven",
            },
            "rs485": {
                "reference_expected_counts": {
                    "motor": 4,
                    "belt": 2,
                    "rfid": 1,
                    "cfs": 4,
                },
                "note": (
                    "these counts belong to the K2 Plus reference and must not replace "
                    "the independently recovered K2 Pro stock count"
                ),
                "motor_explicit_f0_06_erase": False,
                "cfs_explicit_f0_06_erase": True,
                "chunk_retries": 5,
            },
            "firmware_targets": [
                "cfs0_050_G32-cfs0_000_142.bin",
                "mcu0_140_G32-mcu0_022_000.bin",
                "mot2_023_C30-mot2_002_081.bin",
                "noz0_130_G30-noz0_021_000.bin",
            ],
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
                "jacob_k2_plus_reference": (
                    "E is updated with the P2P protocol through Nozzle transparent mode, "
                    "not through the RS-485 F0 stream; K2 Pro stock equivalence pending"
                ),
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