from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PREFIX_KIND = {
    "mcu": "main_mcu",
    "noz": "nozzle_mcu",
    "bed": "bed_mcu",
    "mot": "motor",
    "cfs": "cfs",
    "rfd": "rfid",
    "bet": "belt",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_hardware(hardware: str) -> str:
    prefix = "".join(ch for ch in hardware.lower() if ch.isalpha())[:3]
    return PREFIX_KIND.get(prefix, "unknown")


def parse_firmware_name(name: str) -> dict[str, Any]:
    if not name.lower().endswith(".bin"):
        raise ValueError(f"not a .bin firmware name: {name}")
    stem = name[:-4]
    if "-" not in stem:
        return {
            "hardware": stem,
            "application": None,
            "kind": classify_hardware(stem),
        }
    hardware, application = stem.split("-", 1)
    return {
        "hardware": hardware,
        "application": application,
        "kind": classify_hardware(hardware),
    }


def _read_version_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def scan_tree(root: str | Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"firmware root does not exist: {root}")

    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.bin")):
        parsed = parse_firmware_name(path.name)
        parsed.update({
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
        artifacts.append(parsed)

    version_files = []
    for path in sorted(root.rglob("version.json")):
        version_files.append({
            "path": path.relative_to(root).as_posix(),
            "data": _read_version_json(path),
        })

    return {
        "schema": 1,
        "root": str(root),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "version_files": version_files,
    }


def _key(item: dict[str, Any]) -> tuple[str, str]:
    # Creality changes the application token in the filename between releases.
    # Match the same hardware target by its left-hand hardware identifier so a
    # version transition is reported as changed instead of removed + added.
    return (
        str(item.get("kind", "unknown")),
        str(item.get("hardware", "")),
    )


def _index(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = _key(item)
        if key in result:
            raise ValueError(
                "duplicate firmware target in manifest: %s/%s" % key
            )
        result[key] = item
    return result


def compare_manifests(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_map = _index(old.get("artifacts", []))
    new_map = _index(new.get("artifacts", []))

    added = []
    removed = []
    changed = []
    unchanged = []

    for key in sorted(old_map.keys() | new_map.keys()):
        before = old_map.get(key)
        after = new_map.get(key)
        if before is None:
            added.append(after)
        elif after is None:
            removed.append(before)
        elif before.get("sha256") != after.get("sha256"):
            changed.append({"before": before, "after": after})
        else:
            unchanged.append(after)

    return {
        "schema": 1,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
    }


def load_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
