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
    assert "hardware-validated" in enumeration["extruder_e_equivalence"]
    assert "GPIO140 MCU-rail power-cycle" in motor["loader_entry"]

    safety = result["safety"]
    assert safety["motor_loader_entry_hardware_validated"] is True
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
    assert "hardware-validated" in extruder_ref["k2_pro_equivalence"]

    counts = ref["rs485"]["reference_expected_counts"]
    assert counts == {"motor": 4, "belt": 2, "rfid": 1, "cfs": 4}
    assert "must not replace" in ref["rs485"]["note"]

def test_k2_pro_live_loader_probe_records_real_identities_and_safe_restore():
    result = inspect_device_matrix()
    live = result["k2_pro_live_loader_probe"]

    assert live["entry"]["hardware_validated"] is True
    assert live["entry"]["mechanism"] == "GPIO140 MCU_PWR_EN hardware power-cycle"
    assert live["transports"]["main"]["baud"] == 115200
    assert live["transports"]["toolhead"]["baud"] == 115200
    assert live["transports"]["rs485"]["baud"] == 230400

    ids = live["identities"]
    assert ids["main"]["full"] == "mcu0_120_G32-mcu0_001_000"
    assert ids["nozzle"]["full"] == "noz0_130_G30-noz0_021_000"
    assert ids["extruder"]["full"] == "mot2_022_C30-mot2_002_071"
    assert ids["xy_motors"]["count"] == 2
    assert ids["xy_motors"]["full"] == "mot2_023_C30-mot2_002_071"
    assert ids["cfs"]["full"] == "cfs0_050_G32-cfs0_000_113"
    assert live["rs485_counts"] == {"motor": 2, "cfs": 1, "belt": 0, "rfid": 0}
    assert live["loader_modes"] == {"motor": 1, "cfs": 1}

    restore = live["restore"]
    assert restore["main_02_fd_ack"] is True
    assert restore["toolhead_02_fd_ack"] is True
    assert restore["motor_0x85_f0_02_ack"] is True
    assert restore["motor_0x86_f0_02_ack"] is True
    assert restore["cfs_0x01_f0_02_ack"] is True
    assert restore["cfs_0b_01_fallback_sent"] is True
    assert restore["final_printer_ready"] is True

    safety = live["safety"]
    assert safety["erase_sent"] is False
    assert safety["update_request_sent"] is False
    assert safety["firmware_length_sent"] is False
    assert safety["firmware_data_sent"] is False
    assert safety["flash_allowed"] is False
    assert safety["device_uniids_published"] is False

def test_k2_pro_live_loader_probe_records_all_validated_identities_without_flash():
    result = inspect_device_matrix()
    probe = result["k2_pro_live_loader_probe"]
    assert probe["entry"]["gpio"] == 140
    assert probe["entry"]["active_low"] is True
    assert probe["entry"]["hardware_validated"] is True
    identities = probe["identities"]
    assert identities["main"]["hardware"] == "mcu0_120_G32"
    assert identities["nozzle"]["hardware"] == "noz0_130_G30"
    assert identities["extruder"]["hardware"] == "mot2_022_C30"
    assert identities["xy_motors"]["count"] == 2
    assert identities["xy_motors"]["hardware"] == "mot2_023_C30"
    assert identities["cfs"]["hardware"] == "cfs0_050_G32"
    assert identities["belt_count"] == 0
    assert identities["rfid_count"] == 0
    restore = probe["restore"]
    assert restore["main_start_app_ack"] is True
    assert restore["nozzle_start_app_ack"] is True
    assert restore["xy_start_app_ack_count"] == 2
    assert restore["cfs_start_app_ack"] is True
    assert restore["post_runtime_printer_ready"] is True
    assert restore["post_runtime_motor_ready"] is True
    assert restore["post_runtime_cfs"] == "IDLE/OK"
    safety = probe["safety"]
    assert safety["erase_sent"] is False
    assert safety["update_request_sent"] is False
    assert safety["firmware_length_sent"] is False
    assert safety["firmware_data_sent"] is False
    assert safety["flash_allowed"] is False

def test_k2_pro_live_sector_metadata_is_exact_and_write_gates_stay_closed():
    result = inspect_device_matrix()
    live = result["k2_pro_live_loader_probe"]
    sectors = live["sector_metadata"]

    assert sectors["main"] == {
        "token": "0x02",
        "signed": 2,
        "chunk_size": 2048,
        "formula": "direct MCU signed-sector formula",
    }
    assert sectors["nozzle"]["token"] == "0x02"
    assert sectors["nozzle"]["chunk_size"] == 2048
    assert sectors["extruder"]["token"] == "0xc0"
    assert sectors["extruder"]["signed"] == -64
    assert sectors["extruder"]["chunk_size"] == 256
    assert sectors["extruder"]["jacob_override"] == 256
    assert sectors["extruder"]["override_matches_live_formula"] is True
    assert sectors["xy_motors"]["count"] == 2
    assert sectors["xy_motors"]["tokens"] == ["0xe0", "0xe0"]
    assert sectors["xy_motors"]["signed"] == -32
    assert sectors["xy_motors"]["chunk_size"] == 128
    assert sectors["cfs"]["token"] == "0xe0"
    assert sectors["cfs"]["chunk_size"] == 128

    prep = live["write_preparation"]
    assert "first mutating command is F0/01" in prep["xy_motors"]
    assert "first mutating command is 01 FE" in prep["main_nozzle"]
    assert "explicit F0/06 erase" in prep["cfs"]
    assert "not hardware-observed" in prep["device_internal_behavior"]

    safety = live["safety"]
    assert safety["sector_queries_sent"] is True
    assert safety["sector_queries_are_non_flash"] is True
    assert safety["erase_sent"] is False
    assert safety["update_request_sent"] is False
    assert safety["firmware_length_sent"] is False
    assert safety["firmware_data_sent"] is False
    assert safety["flash_allowed"] is False

    top = result["safety"]
    assert top["direct_mcu_sector_hardware_validated"] is True
    assert top["motor_sector_hardware_validated"] is True
    assert top["extruder_sector_hardware_validated"] is True
    assert top["motor_write_enabled"] is False
    assert top["direct_mcu_write_enabled"] is False
    assert top["flash_allowed"] is False

def test_k2_pro_transfer_geometry_matches_live_tokens_and_manifest_sizes():
    result = inspect_device_matrix()
    geom = result["k2_pro_live_loader_probe"]["transfer_geometry_1_1_6_7_2"]
    assert geom["main"] == {"size": 30948, "chunk_size": 2048, "chunk_count": 16, "tail_size": 228, "update_required": False}
    assert geom["nozzle"] == {"size": 30872, "chunk_size": 2048, "chunk_count": 16, "tail_size": 152, "update_required": False}
    assert geom["extruder"]["size"] == 116412
    assert geom["extruder"]["chunk_size"] == 256
    assert geom["extruder"]["chunk_count"] == 455
    assert geom["extruder"]["tail_size"] == 188
    assert geom["extruder"]["update_required"] is True
    xy = geom["xy_motors"]
    assert xy["per_motor_size"] == 116396
    assert xy["chunk_size"] == 128
    assert xy["chunk_count_per_motor"] == 910
    assert xy["tail_size"] == 44
    assert xy["device_count"] == 2
    assert xy["update_required"] is True
    cfs = geom["cfs"]
    assert cfs["size"] == 175104
    assert cfs["chunk_size"] == 128
    assert cfs["chunk_count"] == 1368
    assert cfs["tail_size"] == 128
    assert cfs["full_chunks_only"] is True
    assert cfs["update_required"] is True
    assert geom["flash_allowed"] is False
    assert 2048 * 15 + 228 == geom["main"]["size"]
    assert 2048 * 15 + 152 == geom["nozzle"]["size"]
    assert 256 * 454 + 188 == geom["extruder"]["size"]
    assert 128 * 909 + 44 == xy["per_motor_size"]
    assert 128 * 1368 == cfs["size"]