from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def _parent(item: dict[str, Any]) -> str:
    return str(PurePosixPath(str(item.get("path", ""))).parent)


def select_target(
    manifest: dict[str, Any],
    hardware: str,
    *,
    kind: str | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    """Resolve exactly one firmware artifact without guessing hardware family."""
    hardware = str(hardware).strip()
    if not hardware:
        raise ValueError("hardware must not be empty")

    matches = []
    for item in manifest.get("artifacts", []):
        if item.get("hardware") != hardware:
            continue
        if kind is not None and item.get("kind") != kind:
            continue
        if parent is not None and _parent(item) != parent:
            continue
        matches.append(item)

    if not matches:
        detail = f"hardware={hardware}"
        if kind is not None:
            detail += f" kind={kind}"
        if parent is not None:
            detail += f" parent={parent}"
        raise ValueError(f"no firmware artifact matches {detail}")

    if len(matches) != 1:
        locations = ", ".join(str(item.get("path")) for item in matches)
        raise ValueError(
            "firmware target is ambiguous; specify --parent or a narrower kind: "
            + locations
        )
    return matches[0]


def build_candidate_plan(
    manifest: dict[str, Any],
    hardware: str,
    *,
    current_application: str | None = None,
    kind: str | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    target = select_target(manifest, hardware, kind=kind, parent=parent)
    target_application = target.get("application")
    update_required = None
    if current_application is not None and target_application is not None:
        update_required = str(current_application) != str(target_application)

    return {
        "schema": 1,
        "mode": "candidate-only",
        "write_enabled": False,
        "hardware": hardware,
        "kind": target.get("kind"),
        "parent": _parent(target),
        "current_application": current_application,
        "target_application": target_application,
        "update_required": update_required,
        "artifact": target,
        "safety": {
            "exact_hardware_match": True,
            "bootloader_generation_verified": False,
            "recovery_path_verified": False,
            "flash_allowed": False,
        },
    }
