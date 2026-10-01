from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import compare_manifests, dump_json, load_manifest, scan_tree


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2
