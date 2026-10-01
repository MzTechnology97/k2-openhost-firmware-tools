from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


KLIPPER_MCU_OBJECTS = ("mcu", "mcu nozzle_mcu")
MOTOR_AXES = ("x", "y", "e")

# Exact constants recovered from the two K2 Pro motor applications analysed
# for this project.  Other firmware families may legitimately use other values.
KNOWN_MOTOR_FLASH_PARAM_VERSIONS = {
    0x0247: "mot2_002_071",
    0x024B: "mot2_002_081",
}


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def _post_gcode(base_url: str, script: str, timeout: float) -> None:
    request = Request(
        base_url.rstrip("/") + "/printer/gcode/script",
        data=json.dumps({"script": script}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("result") != "ok":
        raise RuntimeError(f"Moonraker rejected read-only gcode: {script}")


def _object_status(
    base_url: str,
    objects: tuple[str, ...],
    timeout: float,
) -> dict[str, Any]:
    query = "&".join(quote(name, safe="") for name in objects)
    payload = _get_json(
        base_url.rstrip("/") + "/printer/objects/query?" + query,
        timeout,
    )
    try:
        return payload["result"]["status"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("unexpected Moonraker object-query response") from exc


def normalize_klipper_mcu(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    constants = raw.get("mcu_constants") or {}
    label = "main" if name == "mcu" else "nozzle"
    return {
        "device": label,
        "object": name,
        "running_application": raw.get("mcu_version"),
        "microcontroller": constants.get("MCU"),
        "clock_hz": constants.get("CLOCK_FREQ"),
        "serial_baud": constants.get("SERIAL_BAUD"),
        "build_machine_uid": constants.get("build_machine_uid"),
        "identity_scope": "running Klipper/Kalico application",
        "bootloader_version": None,
        "write_enabled": False,
    }


def query_klipper_mcus(
    base_url: str = "http://127.0.0.1:7125",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    status = _object_status(base_url, KLIPPER_MCU_OBJECTS, timeout)
    devices = []
    for name in KLIPPER_MCU_OBJECTS:
        raw = status.get(name)
        if not isinstance(raw, dict) or not raw.get("mcu_version"):
            raise RuntimeError(f"Moonraker did not return a runtime version for {name}")
        devices.append(normalize_klipper_mcu(name, raw))
    return {
        "schema": 1,
        "source": "moonraker",
        "moonraker": base_url,
        "devices": devices,
        "write_enabled": False,
    }


def parse_motor_flash_readback(messages: list[str], command: str) -> int:
    starts = [index for index, message in enumerate(messages) if message == command]
    if not starts:
        raise RuntimeError(f"gcode store does not contain marker for {command}")
    start = starts[-1] + 1
    for message in messages[start:]:
        if message.startswith("MOTOR_READ_PARAM "):
            break
        prefix = "// Flash readback="
        if message.startswith(prefix):
            try:
                return int(message[len(prefix):].strip(), 0)
            except ValueError as exc:
                raise RuntimeError("invalid motor flash version readback") from exc
    raise RuntimeError(f"no flash readback found for {command}")


def _gcode_messages(base_url: str, timeout: float, count: int = 40) -> list[str]:
    payload = _get_json(
        base_url.rstrip("/") + f"/server/gcode_store?count={count}",
        timeout,
    )
    try:
        entries = payload["result"]["gcode_store"]
        return [str(entry["message"]) for entry in entries]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("unexpected Moonraker gcode-store response") from exc


def query_motor_runtime_versions(
    base_url: str = "http://127.0.0.1:7125",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    state = _object_status(base_url, ("motor_control", "print_stats"), timeout)
    motor = state.get("motor_control") or {}
    print_state = str((state.get("print_stats") or {}).get("state", "unknown"))
    if not motor.get("motor_ready"):
        raise RuntimeError("motor_control is not ready for a read-only version query")
    if motor.get("is_homing"):
        raise RuntimeError("refusing motor version query while homing")
    if print_state in {"printing", "paused"}:
        raise RuntimeError(f"refusing motor version query while print state is {print_state}")

    devices = []
    for axis in MOTOR_AXES:
        command = f"MOTOR_READ_PARAM PARAM={axis}_param_flash_param_version"
        _post_gcode(base_url, command, timeout)
        raw_version = parse_motor_flash_readback(
            _gcode_messages(base_url, timeout), command
        )
        devices.append({
            "device": f"motor_{axis}",
            "axis": axis,
            "flash_param_version": raw_version,
            "flash_param_version_hex": f"0x{raw_version:04x}",
            "matched_application": KNOWN_MOTOR_FLASH_PARAM_VERSIONS.get(raw_version),
            "match_scope": "known K2 Pro motor firmware artifacts",
            "query": "runtime FLASH_PARAM read, parameter id 0",
            "write_enabled": False,
        })
    return {
        "schema": 1,
        "source": "moonraker/motor_control",
        "moonraker": base_url,
        "print_state": print_state,
        "devices": devices,
        "write_enabled": False,
    }


def query_printer_status(
    base_url: str = "http://127.0.0.1:7125",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    mcus = query_klipper_mcus(base_url, timeout=timeout)
    motors = query_motor_runtime_versions(base_url, timeout=timeout)
    return {
        "schema": 1,
        "source": "live-read-only",
        "moonraker": base_url,
        "devices": mcus["devices"] + motors["devices"],
        "write_enabled": False,
    }
