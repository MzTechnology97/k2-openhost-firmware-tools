from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from .rs485 import port_owners


DEFAULT_OBJECTS = (
    "print_stats",
    "extruder",
    "heater_bed",
    "heater_generic chamber_heater",
)


def query_moonraker_status(
    base_url: str = "http://127.0.0.1:7125",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    query = "&".join(quote(name, safe="") for name in DEFAULT_OBJECTS)
    url = base_url.rstrip("/") + "/printer/objects/query?" + query
    with urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    try:
        return payload["result"]["status"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("unexpected Moonraker object-query response") from exc


def evaluate_preflight(
    status: dict[str, Any],
    owner_map: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    print_state = str(status.get("print_stats", {}).get("state", "unknown"))
    machine_idle = print_state not in {"printing", "paused"}

    heater_targets: dict[str, float | None] = {}
    heaters_off = True
    for name in ("extruder", "heater_bed", "heater_generic chamber_heater"):
        raw = status.get(name, {}).get("target")
        try:
            target = None if raw is None else float(raw)
        except (TypeError, ValueError):
            target = None
        heater_targets[name] = target
        if target is None or target > 0.0:
            heaters_off = False

    busy_ports = {
        port: owners for port, owners in owner_map.items() if owners
    }
    serial_exclusive = not busy_ports
    safe = machine_idle and heaters_off and serial_exclusive

    return {
        "schema": 1,
        "safe_for_flash": safe,
        "machine_idle": machine_idle,
        "print_state": print_state,
        "heaters_off": heaters_off,
        "heater_targets": heater_targets,
        "serial_exclusive": serial_exclusive,
        "busy_ports": busy_ports,
        "checks": {
            "machine_idle": "pass" if machine_idle else "fail",
            "heaters_off": "pass" if heaters_off else "fail",
            "serial_exclusive": "pass" if serial_exclusive else "fail",
        },
    }


def run_preflight(
    ports: list[str],
    *,
    base_url: str = "http://127.0.0.1:7125",
    timeout: float = 3.0,
) -> dict[str, Any]:
    status = query_moonraker_status(base_url, timeout=timeout)
    owners = {port: port_owners(port) for port in ports}
    result = evaluate_preflight(status, owners)
    result["moonraker"] = base_url
    result["ports"] = list(ports)
    return result
