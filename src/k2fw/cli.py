from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cfs_loader import inspect_cfs_loader_probe, probe_cfs_loader_live
from .device_matrix import inspect_device_matrix
from .live import query_klipper_mcus, query_motor_runtime_versions, query_printer_status
from .manifest import compare_manifests, dump_json, load_manifest, scan_tree
from .mcu_update import inspect_mcu_update
from .preflight import run_preflight
from .rs485 import probe_cfs_version
from .rs485_update import inspect_rs485_update
from .selection import build_candidate_plan
from .status_compare import compare_live_status_to_manifest


def _write_or_print(data: dict, output: str | None) -> None:
    text = dump_json(data)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(output)
    else:
        sys.stdout.write(text)


def cmd_device_matrix(args: argparse.Namespace) -> int:
    _write_or_print(inspect_device_matrix(), args.output)
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    _write_or_print(scan_tree(args.root), args.output)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    result = compare_manifests(load_manifest(args.old), load_manifest(args.new))
    _write_or_print(result, args.output)
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    result = build_candidate_plan(
        load_manifest(args.manifest),
        args.hardware,
        current_application=args.current_application,
        kind=args.kind,
        parent=args.parent,
    )
    _write_or_print(result, args.output)
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    result = run_preflight(
        args.port,
        base_url=args.moonraker,
        timeout=args.timeout,
    )
    _write_or_print(result, args.output)
    return 0 if result["safe_for_flash"] else 3


def cmd_probe_cfs(args: argparse.Namespace) -> int:
    if not args.exclusive:
        raise ValueError(
            "live serial probing requires --exclusive after Klipper has released the RS-485 port"
        )
    result = probe_cfs_version(
        args.port,
        address=args.address,
        baud=args.baud,
        timeout=args.timeout,
    )
    _write_or_print(result, args.output)
    return 0


def cmd_probe_cfs_loader(args: argparse.Namespace) -> int:
    missing = []
    if not args.exclusive:
        missing.append("--exclusive")
    if not args.single_cfs:
        missing.append("--single-cfs")
    if not args.ack_state_change:
        missing.append("--ack-state-change")
    if not args.printer_safe_confirmed:
        missing.append("--printer-safe-confirmed")
    if missing:
        raise ValueError(
            "live CFS loader probing is state-changing and requires explicit "
            "confirmation flags: " + ", ".join(missing)
        )

    result = probe_cfs_loader_live(
        args.port,
        assigned_address=args.address,
        baud=args.baud,
        timeout=args.timeout,
    )
    _write_or_print(result, args.output)
    return 0


def cmd_inspect_cfs_loader_probe(args: argparse.Namespace) -> int:
    result = inspect_cfs_loader_probe(address=args.address)
    _write_or_print(result, args.output)
    return 0


def cmd_inspect_update(args: argparse.Namespace) -> int:
    result = inspect_rs485_update(
        args.firmware,
        address=args.address,
        sector_token=args.sector_token,
    )
    _write_or_print(result, args.output)
    return 0


def cmd_inspect_mcu_update(args: argparse.Namespace) -> int:
    result = inspect_mcu_update(
        args.firmware,
        sector_token=args.sector_token,
    )
    _write_or_print(result, args.output)
    return 0


def cmd_probe_mcus(args: argparse.Namespace) -> int:
    result = query_klipper_mcus(args.moonraker, timeout=args.timeout)
    _write_or_print(result, args.output)
    return 0


def cmd_probe_motors(args: argparse.Namespace) -> int:
    result = query_motor_runtime_versions(args.moonraker, timeout=args.timeout)
    _write_or_print(result, args.output)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    result = query_printer_status(args.moonraker, timeout=args.timeout)
    if args.manifest:
        result = compare_live_status_to_manifest(
            result, load_manifest(args.manifest)
        )
    _write_or_print(result, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k2fw",
        description="K2-OpenHost peripheral firmware inspection tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    matrix = sub.add_parser(
        "device-matrix",
        help="show the recovered K2 firmware-device transport/update architecture",
    )
    matrix.add_argument("-o", "--output", help="write JSON result to this path")
    matrix.set_defaults(func=cmd_device_matrix)

    scan = sub.add_parser("scan", help="inventory a local Creality firmware tree")
    scan.add_argument("root", help="firmware root, normally usr/share/klipper/fw")
    scan.add_argument("-o", "--output", help="write JSON manifest to this path")
    scan.set_defaults(func=cmd_scan)

    compare = sub.add_parser("compare", help="compare two scan manifests")
    compare.add_argument("old", help="older manifest JSON")
    compare.add_argument("new", help="newer manifest JSON")
    compare.add_argument("-o", "--output", help="write comparison JSON to this path")
    compare.set_defaults(func=cmd_compare)

    resolve = sub.add_parser(
        "resolve",
        help="resolve one exact local firmware candidate without enabling writes",
    )
    resolve.add_argument("manifest", help="scan manifest JSON")
    resolve.add_argument("--hardware", required=True, help="exact hardware token")
    resolve.add_argument("--kind", help="optional artifact kind filter")
    resolve.add_argument(
        "--parent",
        help="exact parent path inside the firmware tree, e.g. F012/motor or cfs",
    )
    resolve.add_argument(
        "--current-application",
        help="currently running application token, used only to report whether an update differs",
    )
    resolve.add_argument("-o", "--output", help="write JSON plan to this path")
    resolve.set_defaults(func=cmd_resolve)

    preflight = sub.add_parser(
        "preflight",
        help="read-only check of print state, heaters and serial-port ownership",
    )
    preflight.add_argument(
        "--moonraker", default="http://127.0.0.1:7125", help="Moonraker base URL"
    )
    preflight.add_argument(
        "--port",
        action="append",
        default=[],
        help="serial device that must be exclusively owned; repeat for multiple ports",
    )
    preflight.add_argument("--timeout", type=float, default=3.0)
    preflight.add_argument("-o", "--output", help="write JSON result to this path")
    preflight.set_defaults(func=cmd_preflight)

    probe = sub.add_parser(
        "probe-cfs",
        help="read the CFS runtime version over an exclusively owned RS-485 port",
    )
    probe.add_argument("--port", default="/dev/ttyUSB2")
    probe.add_argument("--address", type=int, default=1)
    probe.add_argument("--baud", type=int, default=230400)
    probe.add_argument("--timeout", type=float, default=1.0)
    probe.add_argument(
        "--exclusive",
        action="store_true",
        help="confirm Klipper/other bus consumers have released this port",
    )
    probe.add_argument("-o", "--output", help="write JSON result to this path")
    probe.set_defaults(func=cmd_probe_cfs)

    probe_loader = sub.add_parser(
        "probe-cfs-loader",
        help=(
            "live non-flash CFS loader identity/sector probe with mandatory "
            "application restore"
        ),
    )
    probe_loader.add_argument("--port", default="/dev/ttyUSB2")
    probe_loader.add_argument("--address", type=int, default=1)
    probe_loader.add_argument("--baud", type=int, default=230400)
    probe_loader.add_argument("--timeout", type=float, default=1.0)
    probe_loader.add_argument(
        "--exclusive",
        action="store_true",
        help="confirm Klipper/other consumers have released the RS-485 port",
    )
    probe_loader.add_argument(
        "--single-cfs",
        action="store_true",
        help="confirm exactly one CFS is connected because loader entry is broadcast",
    )
    probe_loader.add_argument(
        "--ack-state-change",
        action="store_true",
        help="acknowledge loader entry, temporary A0 assignment and app restore",
    )
    probe_loader.add_argument(
        "--printer-safe-confirmed",
        action="store_true",
        help="confirm printer is idle and all heater targets are zero",
    )
    probe_loader.add_argument(
        "-o", "--output", help="write JSON result to this path"
    )
    probe_loader.set_defaults(func=cmd_probe_cfs_loader)

    inspect_loader = sub.add_parser(
        "inspect-cfs-loader-probe",
        help=(
            "render the non-flash CFS loader probe/recovery sequence offline; "
            "does not open a serial port"
        ),
    )
    inspect_loader.add_argument(
        "--address", type=int, default=1,
        help="offline assigned CFS address used only to render frame bytes",
    )
    inspect_loader.add_argument(
        "-o", "--output", help="write JSON result to this path"
    )
    inspect_loader.set_defaults(func=cmd_inspect_cfs_loader_probe)

    inspect_update = sub.add_parser(
        "inspect-update",
        help="inspect the recovered stock RS-485 update sequence without serial I/O",
    )
    inspect_update.add_argument("firmware", help="local CFS .bin firmware image")
    inspect_update.add_argument(
        "--address",
        type=int,
        default=1,
        help="offline address used only to render fixed control-frame bytes",
    )
    inspect_update.add_argument(
        "--sector-token",
        "--sector-code",
        dest="sector_token",
        type=lambda value: int(value, 0),
        help=(
            "optional trusted F0/03 response byte (for example 0xc1); "
            "used only for offline chunk arithmetic"
        ),
    )
    inspect_update.add_argument("-o", "--output", help="write JSON result to this path")
    inspect_update.set_defaults(func=cmd_inspect_update)

    inspect_mcu_update_cmd = sub.add_parser(
        "inspect-mcu-update",
        help="inspect the recovered direct Main/Nozzle update sequence offline",
    )
    inspect_mcu_update_cmd.add_argument(
        "firmware", help="local Main/Nozzle direct-MCU .bin image"
    )
    inspect_mcu_update_cmd.add_argument(
        "--sector-token",
        type=lambda value: int(value, 0),
        help=(
            "optional trusted one-byte get-sector-size response; "
            "used only for offline chunk arithmetic"
        ),
    )
    inspect_mcu_update_cmd.add_argument(
        "-o", "--output", help="write JSON result to this path"
    )
    inspect_mcu_update_cmd.set_defaults(func=cmd_inspect_mcu_update)

    probe_mcus = sub.add_parser(
        "probe-mcus",
        help="read Main/Nozzle running MCU application identities from Moonraker",
    )
    probe_mcus.add_argument(
        "--moonraker", default="http://127.0.0.1:7125", help="Moonraker base URL"
    )
    probe_mcus.add_argument("--timeout", type=float, default=3.0)
    probe_mcus.add_argument("-o", "--output", help="write JSON result to this path")
    probe_mcus.set_defaults(func=cmd_probe_mcus)

    probe_motors = sub.add_parser(
        "probe-motors",
        help="read X/Y/E runtime motor firmware fingerprints without writes",
    )
    probe_motors.add_argument(
        "--moonraker", default="http://127.0.0.1:7125", help="Moonraker base URL"
    )
    probe_motors.add_argument("--timeout", type=float, default=3.0)
    probe_motors.add_argument("-o", "--output", help="write JSON result to this path")
    probe_motors.set_defaults(func=cmd_probe_motors)

    status = sub.add_parser(
        "status",
        help="read Main, Nozzle, X/Y/E and CFS runtime firmware identities",
    )
    status.add_argument(
        "--moonraker", default="http://127.0.0.1:7125", help="Moonraker base URL"
    )
    status.add_argument("--timeout", type=float, default=3.0)
    status.add_argument(
        "--manifest",
        help=(
            "explicit firmware manifest to compare read-only against live status; "
            "never enables target flashing"
        ),
    )
    status.add_argument("-o", "--output", help="write JSON result to this path")
    status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2