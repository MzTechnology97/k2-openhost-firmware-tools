from k2fw.device_matrix import inspect_device_matrix


def test_motor_and_cfs_share_rs485_loader_but_erase_policy_differs():
    result = inspect_device_matrix()
    motor = result["rs485"]["motor"]
    cfs = result["rs485"]["cfs"]

    assert motor["updater"] == cfs["updater"] == "mcu_util_485"
    assert motor["stock_device_type"] == 2
    assert motor["discovery_address"] == 0xFD
    assert cfs["stock_device_type"] == 1
    assert cfs["discovery_address"] == 0xFE

    for key in (
        "loader_identity_query",
        "sector_query",
        "update_request",
        "start_application",
    ):
        assert motor[key] == cfs[key]

    assert motor["explicit_erase"] is False
    assert cfs["explicit_erase"] is True


def test_motor_live_observations_are_read_only_and_writes_remain_disabled():
    result = inspect_device_matrix()
    motor = result["motor_findings"]

    assert motor["current_application_fingerprint"]["mapped_application"] == "mot2_002_071"
    assert motor["live_boot_key"]["x"] == 17030
    assert motor["live_boot_key"]["y"] == 17030
    assert motor["live_boot_key"]["e"] == 17030
    assert motor["live_boot_key"]["read_only_observation"] is True
    assert motor["live_system_startup_delay_ms"] == {"x": 100, "y": 100, "e": 100}
    assert motor["live_flash_key_write_retries_num"] == {"x": 5, "y": 5, "e": 5}
    assert "loader-side use" in motor["boot_parameter_consumption"]
    enumeration = motor["stock_loader_enumeration"]
    assert enumeration["device_type"] == 2
    assert enumeration["discovery_group"] == "0xfd"
    assert enumeration["discovery_payload"] == "fdfd"
    assert enumeration["required_mode"] == 1
    assert enumeration["stock_expected_count"] == 2
    assert enumeration["first_temp_address"] == "0x85"
    assert enumeration["extruder_e_equivalence"] == "not-yet-proven"
    assert "no host-side motor loader-entry command" in motor["loader_entry"]

    safety = result["safety"]
    assert safety["motor_loader_entry_enabled"] is False
    assert safety["motor_write_enabled"] is False
    assert safety["flash_allowed"] is False


def test_toolhead_is_a_direct_mcu_backend_not_the_rs485_updater():
    result = inspect_device_matrix()
    toolhead = result["direct_mcu"]["toolhead"]

    assert toolhead["updater"] == "mcu_util"
    assert toolhead["stock_device_type"] is None
    assert toolhead["loader_identity_query"] == "00 FF after 0x75 handshake"
    assert toolhead["sector_query"] == "03 FC"
    assert toolhead["update_request"] == "01 FE"
    assert toolhead["start_application"] == "02 FD"

    findings = result["toolhead_findings"]
    assert findings["hardware_token_embedded_in_package"] is False
    boot = findings["canboot_katapult_abi"]
    assert boot["signature"] == "0x21746f6f426e6143"
    assert boot["signature_offset"] == "0x3e0"
    assert boot["request_start_app"] == "0x7b06ec45a9a8243d"
    assert boot["request_start_app_offset"] == "0x3e8"
    assert boot["request_canboot_present"] is False
    assert "wire protocol/bootloader identity is not proven" in boot["interpretation"]
    assert findings["loader_lifecycle_proven_in_stock_host"] is True

def test_jacob_k2_plus_reference_is_model_scoped_and_keeps_e_separate():
    result = inspect_device_matrix()
    ref = result["jacob_k2_plus_reference"]
    assert ref["provenance"]["scope"].startswith("reference implementation")
    assert ref["boot_orchestration"]["gpio"] == 140
    assert ref["boot_orchestration"]["active_low"] is True
    assert ref["parallel_transports"]["rs485"]["baud"] == 230400
    assert ref["parallel_transports"]["main_p2p"]["baud"] == 115200
    assert ref["parallel_transports"]["nozzle_p2p"]["baud"] == 115200

    e = result["tunneled_p2p"]["extruder"]
    assert "transparent mode" in e["transport"]
    assert e["loader_identity_query"] == "00 FF after Nozzle 04 FB transparent mode"
    assert e["sector_query"] == "03 FC"
    assert e["update_request"] == "01 FE"
    assert "not explicitly sent" in e["start_application"]

    extruder_ref = ref["extruder"]
    assert extruder_ref["separate_0x75_handshake_in_reference"] is False
    assert extruder_ref["chunk_override"] == 256
    assert extruder_ref["explicit_start_app_after_extruder_update"] is False
    assert extruder_ref["k2_pro_equivalence"] == "not-yet-proven"

    counts = ref["rs485"]["reference_expected_counts"]
    assert counts == {"motor": 4, "belt": 2, "rfid": 1, "cfs": 4}
    assert "must not replace" in ref["rs485"]["note"]