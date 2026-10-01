from k2fw.live import normalize_klipper_mcu


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
    assert result["write_enabled"] is False


def test_normalize_nozzle_mcu_runtime_identity_is_read_only():
    result = normalize_klipper_mcu(
        "mcu nozzle_mcu",
        {"mcu_version": "1.1.0.48-293-gabcd", "mcu_constants": {"MCU": "gd32f303xb"}},
    )
    assert result["device"] == "nozzle"
    assert result["microcontroller"] == "gd32f303xb"
    assert result["write_enabled"] is False
