from __future__ import annotations

import json
import math
import os
import socket
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


SCHEMA = 2

HEATERS = (
    "extruder",
    "heater_bed",
    "heater_generic chamber_heater",
)
DEFAULT_OBJECTS = ("print_stats",) + HEATERS

# Klipper's print_stats.state values (klippy/extras/print_stats.py) are
# standby, printing, paused, complete, cancelled and error. Only the four in
# which no job owns the toolhead are idle: "error" is the state a print is
# left in after it failed, with the job already ended. Anything else,
# including a missing or unexpected value, blocks.
IDLE_PRINT_STATES = frozenset({"standby", "complete", "cancelled", "error"})


class MoonrakerQueryError(RuntimeError):
    """The object query failed; ``code`` says how."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def query_moonraker_status(
    base_url: str = "http://127.0.0.1:7125",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    query = "&".join(quote(name, safe="") for name in DEFAULT_OBJECTS)
    url = base_url.rstrip("/") + "/printer/objects/query?" + query
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise MoonrakerQueryError("moonraker_http_error", f"HTTP {exc.code}") from exc
    except URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise MoonrakerQueryError("moonraker_timeout", f"no answer within {timeout} s") from exc
        raise MoonrakerQueryError("moonraker_unreachable", str(exc.reason)) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise MoonrakerQueryError("moonraker_timeout", f"no answer within {timeout} s") from exc
    except ValueError as exc:
        raise MoonrakerQueryError("moonraker_malformed", "the answer is not JSON") from exc
    except OSError as exc:
        raise MoonrakerQueryError("moonraker_unreachable", str(exc)) from exc
    try:
        status = payload["result"]["status"]
    except (KeyError, TypeError) as exc:
        raise MoonrakerQueryError(
            "moonraker_malformed", "unexpected Moonraker object-query response"
        ) from exc
    if not isinstance(status, dict):
        raise MoonrakerQueryError("moonraker_malformed", "result.status is not an object")
    return status


def port_ownership(port: str, proc_root: str = "/proc") -> dict[str, Any]:
    """Who holds ``port`` open, and whether that answer is complete.

    The port is resolved through its link (``/dev/serial/by-id/...`` or
    ``/dev/serial/by-path/...``), so the check follows the device the
    configured name points at today rather than assuming fixed ttyUSB
    numbers. ``complete`` is False when a process could not be inspected
    (another user's /proc/<pid>/fd without root): an empty owner list is
    then not proof of exclusivity.
    """
    result: dict[str, Any] = {
        "port": port,
        "device": None,
        "exists": False,
        "owners": [],
        "complete": False,
        "error": None,
    }
    if not os.path.exists(port):
        result["error"] = "port does not exist"
        return result
    target = os.path.realpath(port)
    result["device"] = target
    result["exists"] = True
    proc = Path(proc_root)
    try:
        entries = [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError as exc:
        result["error"] = f"cannot list {proc_root}: {exc}"
        return result
    complete = True
    me = str(os.getpid())
    for process in entries:
        if process.name == me:
            continue
        try:
            fds = list((process / "fd").iterdir())
        except FileNotFoundError:
            continue  # the process ended while we looked
        except OSError:
            complete = False
            continue
        for fd in fds:
            try:
                if os.path.realpath(fd) != target:
                    continue
                cmdline = (process / "cmdline").read_bytes().replace(b"\x00", b" ")
                command = cmdline.decode("utf-8", "replace").strip()
            except FileNotFoundError:
                continue
            except OSError:
                command = ""
            result["owners"].append({"pid": int(process.name), "command": command})
            break
    result["complete"] = complete
    if not complete:
        result["error"] = "some processes could not be inspected (run as root)"
    return result


def _blocker(check: str, code: str, detail: str) -> dict[str, str]:
    return {"check": check, "code": code, "detail": detail}


def _finite_target(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0.0:
        return None
    return value


def evaluate_preflight(
    status: dict[str, Any] | None,
    ownership: dict[str, dict[str, Any]],
    *,
    status_error: MoonrakerQueryError | None = None,
) -> dict[str, Any]:
    """Decide whether the printer is in a state where flashing may be
    considered. Every needed fact must be known: an unknown value is a
    blocker with a reason, never a pass.

    ``ownership`` maps each configured port to a :func:`port_ownership`
    result. This is a precondition check only: it does not prove that a
    firmware image fits the hardware and it does not enable flashing.
    """
    blockers: list[dict[str, str]] = []
    checks = {"machine_idle": "unknown", "heaters_off": "unknown", "serial_exclusive": "unknown"}

    # -- print state ---------------------------------------------------------
    print_state: str | None = None
    if status_error is not None:
        blockers.append(_blocker("moonraker", status_error.code, status_error.detail))
    elif not isinstance(status, dict):
        blockers.append(_blocker("moonraker", "moonraker_malformed", "no printer status"))
        status = None
    if status is not None:
        stats = status.get("print_stats")
        raw_state = stats.get("state") if isinstance(stats, dict) else None
        if not isinstance(stats, dict):
            blockers.append(_blocker("machine_idle", "print_stats_missing",
                                     "print_stats is missing from the Moonraker answer"))
        elif not isinstance(raw_state, str) or not raw_state:
            blockers.append(_blocker("machine_idle", "print_state_missing",
                                     "print_stats.state is missing or not a string"))
        else:
            print_state = raw_state
            if raw_state in IDLE_PRINT_STATES:
                checks["machine_idle"] = "pass"
            elif raw_state in ("printing", "paused"):
                checks["machine_idle"] = "fail"
                blockers.append(_blocker("machine_idle", "print_active",
                                         f"a print is {raw_state}"))
            else:
                blockers.append(_blocker("machine_idle", "print_state_unexpected",
                                         f"unexpected print state {raw_state!r}"))

    # -- heaters -------------------------------------------------------------
    heater_targets: dict[str, float | None] = {}
    if status is not None:
        heating = unknown = False
        for name in HEATERS:
            obj = status.get(name)
            raw = obj.get("target") if isinstance(obj, dict) else None
            target = _finite_target(raw)
            heater_targets[name] = target
            if not isinstance(obj, dict):
                unknown = True
                blockers.append(_blocker("heaters_off", "heater_missing",
                                         f"{name} is missing from the Moonraker answer"))
            elif target is None:
                unknown = True
                blockers.append(_blocker("heaters_off", "heater_target_invalid",
                                         f"{name} target {raw!r} is not a finite number >= 0"))
            elif target > 0.0:
                heating = True
                blockers.append(_blocker("heaters_off", "heater_on",
                                         f"{name} target is {target:g}"))
        if heating:
            checks["heaters_off"] = "fail"
        elif not unknown:
            checks["heaters_off"] = "pass"
    else:
        heater_targets = {name: None for name in HEATERS}

    # -- serial exclusivity --------------------------------------------------
    busy_ports: dict[str, list[dict[str, Any]]] = {}
    if not ownership:
        blockers.append(_blocker("serial_exclusive", "no_ports",
                                 "no serial port given, so exclusivity is not verified"))
    else:
        busy = unknown = False
        for port, info in ownership.items():
            if not isinstance(info, dict) or not info.get("exists"):
                unknown = True
                detail = info.get("error") if isinstance(info, dict) else None
                blockers.append(_blocker("serial_exclusive", "port_missing",
                                         f"{port}: {detail or 'not found'}"))
                continue
            owners = info.get("owners")
            if owners:
                busy = True
                busy_ports[port] = owners
                pids = ", ".join(str(o.get("pid")) for o in owners)
                blockers.append(_blocker("serial_exclusive", "port_busy",
                                         f"{port} ({info.get('device')}) is open by pid {pids}"))
            if not isinstance(owners, list) or not info.get("complete"):
                unknown = True
                blockers.append(_blocker("serial_exclusive", "ownership_unknown",
                                         f"{port}: {info.get('error') or 'ownership not verified'}"))
        if busy:
            checks["serial_exclusive"] = "fail"
        elif not unknown:
            checks["serial_exclusive"] = "pass"

    safe = not blockers and all(v == "pass" for v in checks.values())
    return {
        "schema": SCHEMA,
        "safe_for_flash": safe,
        "machine_idle": checks["machine_idle"] == "pass",
        "print_state": print_state,
        "heaters_off": checks["heaters_off"] == "pass",
        "heater_targets": heater_targets,
        "serial_exclusive": checks["serial_exclusive"] == "pass",
        "busy_ports": busy_ports,
        "ports": {port: info for port, info in ownership.items()},
        "checks": checks,
        "blockers": blockers,
    }


def run_preflight(
    ports: list[str],
    *,
    base_url: str = "http://127.0.0.1:7125",
    timeout: float = 3.0,
) -> dict[str, Any]:
    status: dict[str, Any] | None = None
    error: MoonrakerQueryError | None = None
    try:
        status = query_moonraker_status(base_url, timeout=timeout)
    except MoonrakerQueryError as exc:
        error = exc
    ownership = {port: port_ownership(port) for port in ports}
    result = evaluate_preflight(status, ownership, status_error=error)
    result["moonraker"] = base_url
    return result
