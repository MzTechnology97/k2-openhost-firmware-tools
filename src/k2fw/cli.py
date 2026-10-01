from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import compare_manifests, dump_json, load_manifest, scan_tree
from .preflight import run_preflight
from .rs485 import probe_cfs_version
from .selection import build_candidate_plan


def _write_or_print(data: dict, output: str | None) -> None:
    text = dump_json(data)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(output)
    else:
        sys.stdout.write(text)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k2fw",
        description="K2-OpenHost peripheral firmware inspection tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2
