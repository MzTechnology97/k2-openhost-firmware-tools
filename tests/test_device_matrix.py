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
    assert findings["loader_lifecycle_proven_in_stock_host"] is True