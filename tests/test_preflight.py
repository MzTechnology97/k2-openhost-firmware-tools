import io
import json
import os
import socket
import sys
from urllib.error import HTTPError, URLError

import pytest

from k2fw import preflight
from k2fw.preflight import (
    IDLE_PRINT_STATES,
    MoonrakerQueryError,
    evaluate_preflight,
    port_ownership,
    query_moonraker_status,
)


def _status(state="standby", extruder=0, bed=0, chamber=0):
    return {
        "print_stats": {"state": state},
        "extruder": {"target": extruder},
        "heater_bed": {"target": bed},
        "heater_generic chamber_heater": {"target": chamber},
    }


def _free(port="/dev/serial/by-id/usb-gadget-if00-port0", device="/dev/ttyUSB0"):
    return {"port": port, "device": device, "exists": True, "owners": [],
            "complete": True, "error": None}


FREE = {
    "/dev/serial/by-id/a-if00": _free("/dev/serial/by-id/a-if00", "/dev/ttyUSB0"),
    "/dev/serial/by-id/a-if01": _free("/dev/serial/by-id/a-if01", "/dev/ttyUSB1"),
    "/dev/serial/by-id/a-if02": _free("/dev/serial/by-id/a-if02", "/dev/ttyUSB2"),
}


def _codes(result):
    return {b["code"] for b in result["blockers"]}


def test_preflight_passes_only_when_idle_cold_and_exclusive():
    result = evaluate_preflight(_status(), FREE)
    assert result["safe_for_flash"] is True
    assert result["blockers"] == []
    assert result["checks"] == {
        "machine_idle": "pass",
        "heaters_off": "pass",
        "serial_exclusive": "pass",
    }


@pytest.mark.parametrize("state", sorted(IDLE_PRINT_STATES))
def test_agreed_idle_states_pass(state):
    assert evaluate_preflight(_status(state), FREE)["safe_for_flash"] is True


@pytest.mark.parametrize("state", ["printing", "paused"])
def test_active_print_blocks(state):
    result = evaluate_preflight(_status(state), FREE)
    assert result["safe_for_flash"] is False
    assert result["checks"]["machine_idle"] == "fail"
    assert "print_active" in _codes(result)


@pytest.mark.parametrize("stats, code", [
    (None, "print_stats_missing"),
    ({}, "print_state_missing"),
    ({"state": None}, "print_state_missing"),
    ({"state": 3}, "print_state_missing"),
    ({"state": "unknown"}, "print_state_unexpected"),
    ({"state": "Standby"}, "print_state_unexpected"),
])
def test_missing_or_unexpected_print_state_blocks(stats, code):
    status = _status()
    if stats is None:
        del status["print_stats"]
    else:
        status["print_stats"] = stats
    result = evaluate_preflight(status, FREE)
    assert result["safe_for_flash"] is False
    assert result["checks"]["machine_idle"] == "unknown"
    assert code in _codes(result)


def test_print_stats_absent_with_cold_heaters_and_free_ports_is_not_safe():
    # The case from the audit: three zero targets, no owner, no print_stats.
    status = _status()
    del status["print_stats"]
    assert evaluate_preflight(status, FREE)["safe_for_flash"] is False


def test_heating_blocks():
    result = evaluate_preflight(_status(extruder=220), FREE)
    assert result["checks"]["heaters_off"] == "fail"
    assert "heater_on" in _codes(result)


@pytest.mark.parametrize("target", [None, "0", float("nan"), float("inf"), float("-inf"), -1, True, [0]])
def test_invalid_heater_target_blocks(target):
    status = _status()
    status["heater_bed"] = {"target": target}
    result = evaluate_preflight(status, FREE)
    assert result["safe_for_flash"] is False
    assert result["checks"]["heaters_off"] == "unknown"
    assert result["heater_targets"]["heater_bed"] is None
    assert "heater_target_invalid" in _codes(result)
    json.dumps(result, allow_nan=False)


def test_missing_heater_blocks():
    status = _status()
    del status["heater_generic chamber_heater"]
    result = evaluate_preflight(status, FREE)
    assert result["safe_for_flash"] is False
    assert "heater_missing" in _codes(result)


def test_heater_object_without_target_blocks():
    status = _status()
    status["heater_bed"] = {}
    result = evaluate_preflight(status, FREE)
    assert result["safe_for_flash"] is False
    assert result["heaters_off"] is False


def test_heating_wins_over_unknown_in_the_check_but_both_are_reported():
    status = _status(extruder=200)
    status["heater_bed"] = {"target": float("nan")}
    result = evaluate_preflight(status, FREE)
    assert result["checks"]["heaters_off"] == "fail"
    assert {"heater_on", "heater_target_invalid"} <= _codes(result)


@pytest.mark.parametrize("code", ["moonraker_timeout", "moonraker_unreachable",
                                  "moonraker_http_error", "moonraker_malformed"])
def test_moonraker_failure_blocks_with_its_reason(code):
    result = evaluate_preflight(None, FREE, status_error=MoonrakerQueryError(code, "x"))
    assert result["safe_for_flash"] is False
    assert code in _codes(result)
    assert result["checks"]["machine_idle"] == "unknown"
    assert result["checks"]["heaters_off"] == "unknown"


def test_malformed_status_object_blocks():
    result = evaluate_preflight(["not", "a", "dict"], FREE)
    assert result["safe_for_flash"] is False
    assert "moonraker_malformed" in _codes(result)


def test_busy_port_blocks():
    ownership = dict(FREE)
    busy = _free("/dev/serial/by-id/a-if02", "/dev/ttyUSB2")
    busy["owners"] = [{"pid": 123, "command": "python klippy.py"}]
    ownership["/dev/serial/by-id/a-if02"] = busy
    result = evaluate_preflight(_status(), ownership)
    assert result["safe_for_flash"] is False
    assert result["checks"]["serial_exclusive"] == "fail"
    assert "/dev/serial/by-id/a-if02" in result["busy_ports"]
    assert "port_busy" in _codes(result)


def test_failed_ownership_scan_is_unknown_not_empty():
    ownership = dict(FREE)
    partial = _free("/dev/serial/by-id/a-if01", "/dev/ttyUSB1")
    partial["complete"] = False
    partial["error"] = "some processes could not be inspected (run as root)"
    ownership["/dev/serial/by-id/a-if01"] = partial
    result = evaluate_preflight(_status(), ownership)
    assert result["safe_for_flash"] is False
    assert result["checks"]["serial_exclusive"] == "unknown"
    assert "ownership_unknown" in _codes(result)


def test_missing_port_blocks():
    ownership = {"/dev/serial/by-id/gone": {"port": "/dev/serial/by-id/gone", "device": None,
                                           "exists": False, "owners": [], "complete": False,
                                           "error": "port does not exist"}}
    result = evaluate_preflight(_status(), ownership)
    assert result["safe_for_flash"] is False
    assert "port_missing" in _codes(result)


def test_no_ports_is_not_exclusive():
    result = evaluate_preflight(_status(), {})
    assert result["safe_for_flash"] is False
    assert result["checks"]["serial_exclusive"] == "unknown"
    assert "no_ports" in _codes(result)


# --- Moonraker query --------------------------------------------------------

class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("exc, code", [
    (URLError(socket.timeout("timed out")), "moonraker_timeout"),
    (socket.timeout("timed out"), "moonraker_timeout"),
    (URLError(ConnectionRefusedError(111, "refused")), "moonraker_unreachable"),
    (HTTPError("u", 503, "Klippy shutdown", {}, None), "moonraker_http_error"),
])
def test_query_errors_are_classified(monkeypatch, exc, code):
    def fake(url, timeout):
        raise exc
    monkeypatch.setattr(preflight, "urlopen", fake)
    with pytest.raises(MoonrakerQueryError) as caught:
        query_moonraker_status("http://host:7125")
    assert caught.value.code == code


@pytest.mark.parametrize("body", [b"not json", b'{"result": {}}', b'{"result": {"status": []}}', b"[]"])
def test_malformed_answers_are_classified(monkeypatch, body):
    monkeypatch.setattr(preflight, "urlopen", lambda url, timeout: _Response(body))
    with pytest.raises(MoonrakerQueryError) as caught:
        query_moonraker_status("http://host:7125")
    assert caught.value.code == "moonraker_malformed"


def test_run_preflight_reports_unreachable_moonraker(monkeypatch):
    def fake(url, timeout):
        raise URLError(ConnectionRefusedError(111, "refused"))
    monkeypatch.setattr(preflight, "urlopen", fake)
    monkeypatch.setattr(preflight, "port_ownership", lambda port: FREE[port])
    result = preflight.run_preflight(list(FREE))
    assert result["safe_for_flash"] is False
    assert "moonraker_unreachable" in _codes(result)


# --- port ownership on a fake /proc ------------------------------------------

linux_only = pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX symlinks")


def _fake_proc(tmp_path, device, holders=(), unreadable=()):
    proc = tmp_path / "proc"
    for pid in list(holders) + list(unreadable) + [99999]:
        (proc / str(pid) / "fd").mkdir(parents=True, exist_ok=True)
        (proc / str(pid) / "cmdline").write_bytes(b"python\x00klippy.py\x00")
    for pid in holders:
        os.symlink(device, proc / str(pid) / "fd" / "5")
    for pid in unreadable:
        os.chmod(proc / str(pid) / "fd", 0)
    return proc


@linux_only
def test_ownership_follows_the_persistent_name(tmp_path):
    device = tmp_path / "ttyUSB7"
    device.write_text("")
    link = tmp_path / "usb-gadget-if02-port0"
    os.symlink(device, link)
    proc = _fake_proc(tmp_path, device, holders=[4242])
    info = port_ownership(str(link), proc_root=str(proc))
    assert info["device"] == str(device)
    assert info["complete"] is True
    assert [o["pid"] for o in info["owners"]] == [4242]


@linux_only
def test_ownership_free_port(tmp_path):
    device = tmp_path / "ttyUSB0"
    device.write_text("")
    proc = _fake_proc(tmp_path, device)
    info = port_ownership(str(device), proc_root=str(proc))
    assert info["owners"] == [] and info["complete"] is True


@linux_only
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any fd dir")
def test_ownership_unreadable_process_is_incomplete(tmp_path):
    device = tmp_path / "ttyUSB0"
    device.write_text("")
    proc = _fake_proc(tmp_path, device, unreadable=[777])
    try:
        info = port_ownership(str(device), proc_root=str(proc))
    finally:
        os.chmod(proc / "777" / "fd", 0o755)
    assert info["complete"] is False
    assert info["error"]


def test_ownership_missing_port(tmp_path):
    info = port_ownership(str(tmp_path / "nope"))
    assert info["exists"] is False and info["error"] == "port does not exist"
