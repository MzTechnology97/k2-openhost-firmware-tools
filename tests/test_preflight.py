from k2fw.preflight import evaluate_preflight


def _status(state="standby", extruder=0, bed=0, chamber=0):
    return {
        "print_stats": {"state": state},
        "extruder": {"target": extruder},
        "heater_bed": {"target": bed},
        "heater_generic chamber_heater": {"target": chamber},
    }


def test_preflight_passes_only_when_idle_cold_and_exclusive():
    result = evaluate_preflight(
        _status(),
        {"/dev/ttyUSB0": [], "/dev/ttyUSB1": [], "/dev/ttyUSB2": []},
    )
    assert result["safe_for_flash"] is True
    assert result["checks"] == {
        "machine_idle": "pass",
        "heaters_off": "pass",
        "serial_exclusive": "pass",
    }


def test_preflight_blocks_printing_heating_and_busy_port():
    owners = {
        "/dev/ttyUSB2": [{"pid": 123, "command": "python klippy.py"}],
    }
    result = evaluate_preflight(_status("printing", extruder=220), owners)
    assert result["safe_for_flash"] is False
    assert result["machine_idle"] is False
    assert result["heaters_off"] is False
    assert result["serial_exclusive"] is False
    assert "/dev/ttyUSB2" in result["busy_ports"]


def test_unknown_heater_target_is_not_treated_as_safe():
    status = _status()
    status["heater_bed"] = {}
    result = evaluate_preflight(status, {})
    assert result["safe_for_flash"] is False
    assert result["heaters_off"] is False
