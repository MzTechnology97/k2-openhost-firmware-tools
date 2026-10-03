from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any


DEVICE_KINDS = {
    "main": "main_mcu",
    "nozzle": "nozzle_mcu",
}


def _artifact_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("path", "hardware", "application", "kind", "size", "sha256")
    }


def _under_model(item: dict[str, Any], model: str) -> bool:
    parts = PurePosixPath(str(item.get("path", ""))).parts
    return bool(parts) and parts[0] == model


def _applications(items: list[dict[str, Any]]) -> list[str]:
    return sorted({
        str(item["application"])
        for item in items
        if item.get("application")
    })


def _compare_direct_mcu(
    device: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    package = device.get("stock_package_candidate") or {}
    hardware = package.get("hardware")
    model = package.get("printer_model")
    kind = DEVICE_KINDS.get(str(device.get("device")))
    matches = [
        item for item in artifacts
        if item.get("hardware") == hardware
        and item.get("kind") == kind
        and (not model or _under_model(item, str(model)))
    ]

    result = {
        "mode": "package-provenance",
        "exact_hardware": hardware,
        "runtime_hardware_verified": False,
        "package_application": package.get("application"),
        "target_selection": "unresolved",
        "update_required": None,
        "flash_allowed": False,
    }
    if not matches:
        result["status"] = "no-package-target"
        result["candidates"] = []
        return result
    if len(matches) != 1:
        result["status"] = "ambiguous-package-target"
        result["candidates"] = [_artifact_view(item) for item in matches]
        return result

    target = matches[0]
    target_application = target.get("application")
    result.update({
        "status": "package-target-present",
        "target_selection": "resolved-from-package-provenance",
        "target_application": target_application,
        "package_application_differs": (
            package.get("application") is not None
            and target_application is not None
            and str(package.get("application")) != str(target_application)
        ),
        "artifact": _artifact_view(target),
        "reason_update_required_unknown": (
            "the running Creality loader hardware/application identity was not "
            "queried; package provenance is not a live bootloader read"
        ),
    })
    return result


def _compare_application_fingerprint(
    device: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(device.get("device", ""))
    if name.startswith("motor_"):
        runtime_application = device.get("matched_application")
        candidates = [
            item for item in artifacts
            if item.get("kind") == "motor" and _under_model(item, "F012")
        ]
        scope = "F012 motor artifacts"
        unresolved_reason = (
            "runtime application fingerprint does not identify the exact motor "
            "hardware target/axis variant"
        )
    elif name.startswith("cfs_"):
        runtime_application = device.get("matched_application")
        family = (
            str(runtime_application).split("_", 1)[0]
            if runtime_application
            else None
        )
        candidates = [
            item for item in artifacts
            if item.get("kind") == "cfs"
            and (
                family is None
                or str(item.get("hardware", "")).startswith(family + "_")
            )
        ]
        scope = f"{family or 'CFS'} firmware family"
        unresolved_reason = (
            "runtime VERSION_SN identifies the application family but not the "
            "exact CFS boot/hardware variant"
        )
    else:
        return {
            "mode": "unmatched",
            "status": "no-safe-matcher",
            "update_required": None,
            "flash_allowed": False,
        }

    applications = _applications(candidates)
    runtime_text = str(runtime_application) if runtime_application else None
    return {
        "mode": "application-fingerprint-only",
        "status": "hardware-unresolved",
        "candidate_scope": scope,
        "runtime_application": runtime_application,
        "runtime_application_present": (
            runtime_text in applications if runtime_text is not None else False
        ),
        "candidate_applications": applications,
        "different_applications": [
            app for app in applications if app != runtime_text
        ],
        "candidates": [_artifact_view(item) for item in candidates],
        "exact_hardware": None,
        "target_selection": "unresolved",
        "unresolved_reason": unresolved_reason,
        "update_required": None,
        "flash_allowed": False,
    }


def compare_live_status_to_manifest(
    live_status: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Attach a read-only manifest comparison without choosing a flash target."""
    result = deepcopy(live_status)
    artifacts = list(manifest.get("artifacts", []))

    for device in result.get("devices", []):
        if device.get("device") in DEVICE_KINDS:
            comparison = _compare_direct_mcu(device, artifacts)
        else:
            comparison = _compare_application_fingerprint(device, artifacts)
        device["manifest_comparison"] = comparison

    result["manifest_comparison"] = {
        "mode": "read-only",
        "manifest_schema": manifest.get("schema"),
        "manifest_release": manifest.get("release"),
        "artifact_count": len(artifacts),
        "target_selection_policy": (
            "exact package provenance for Main/Nozzle; application fingerprints "
            "remain unresolved for motors/CFS without exact hardware identity"
        ),
        "update_decisions_enabled": False,
        "write_enabled": False,
        "flash_allowed": False,
    }
    result["write_enabled"] = False
    return result
