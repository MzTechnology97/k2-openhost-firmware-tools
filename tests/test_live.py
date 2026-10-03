from k2fw.live import (
    DIRECT_MCU_BOOT_IDENTITY_REASON,
    STOCK_F012_DIRECT_MCU_TARGETS,
    normalize_klipper_mcu,
)


def test_normalize_main_mcu_runtime_identity_is_read_only():
    result = normalize_klipper_mcu(
        "mcu",
        {
            "mcu_version": "1.1.0.48-312-gabcd",
            "mcu_constants": {
                "MCU": "gd32f303xe",
                "CLOCK_FREQ": 120000000,
                "SERIAL_BAUD": 230400,
                "build_machine_uid": "Dec 27 202409:23:29",
            },
        },
    )
    assert result["device"] == "main"
    assert result["microcontroller"] == "gd32f303xe"
    assert result["running_application"] == "1.1.0.48-312-gabcd"
    assert result["bootloader_version"] is None
    assert result["bootloader_identity_reason"] == DIRECT_MCU_BOOT_IDENTITY_REASON
    assert result["stock_package_candidate"]["hardware"] == "mcu0_120_G32"
    assert result["stock_package_candidate"]["application"] == "mcu0_001_000"
    assert result["stock_package_candidate"]["runtime_verified"] is False
    assert result["write_enabled"] is False


def test_normalize_nozzle_mcu_runtime_identity_is_read_only():
    result = normalize_klipper_mcu(
        "mcu nozzle_mcu",
        {"mcu_version": "1.1.0.48-293-gabcd", "mcu_constants": {"MCU": "gd32f303xb"}},
    )
    assert result["device"] == "nozzle"
    assert result["microcontroller"] == "gd32f303xb"
    assert result["stock_package_candidate"]["hardware"] == "noz0_130_G30"
    assert result["stock_package_candidate"]["application"] == "noz0_021_000"
    assert result["stock_package_candidate"]["runtime_verified"] is False
    assert result["write_enabled"] is False


def test_f012_direct_mcu_package_hashes_are_pinned():
    assert (
        STOCK_F012_DIRECT_MCU_TARGETS["main"]["sha256"]
        == "bec548e946f0dd37d15f87569b23d55fb12410068f1a3ad2a95c45bf89c756d6"
    )
    assert (
        STOCK_F012_DIRECT_MCU_TARGETS["nozzle"]["sha256"]
        == "6915e65bcbc543857a915ea93e4f0000879c851865efe776d83a8c9354be3208"
    )