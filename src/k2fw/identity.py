"""Unified firmware identity contract (schema ``k2fw.identity/1``).

One record per device role (Main, Nozzle, X/Y/E motors, each CFS) that keeps
three kinds of knowledge apart and never converts one into another:

- ``observed``: what the running application reports now (Kalico MCU version,
  motor FLASH_PARAM id 0, CFS VERSION_SN), with its age;
- ``loader``: the Creality hardware/loader identity, only when it comes from
  explicitly supplied, authorized loader-probe evidence;
- ``package``: the firmware artifact a manifest or the stock F012 table
  points at, which is provenance, never a runtime read.

``update_required`` is filled only when the loader identity is verified and
current and the package target is an exact single match; otherwise it is
``None``. ``flash_allowed`` is always ``False``: this contract describes, it
never authorizes a write.
"""

from __future__ import annotations

import datetime as _dt
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

from .live import (
    KNOWN_CFS_RUNTIME_VERSIONS,
    KNOWN_MOTOR_FLASH_PARAM_VERSIONS,
    STOCK_F012_DIRECT_MCU_TARGETS,
)

SCHEMA = "k2fw.identity/1"

FIXED_ROLES = ("main", "nozzle", "motor_x", "motor_y", "motor_e")

ROLE_KINDS = {
    "main": "main_mcu",
    "nozzle": "nozzle_mcu",
    "motor_x": "motor",
    "motor_y": "motor",
    "motor_e": "motor",
}

# Ordered from strongest to weakest.
VERIFICATION_LEVELS = (
    "loader-verified",
    "runtime-fingerprint",
    "runtime-observed",
    "package-provenance",
    "unknown",
)

DEFAULT_MAX_OBSERVATION_AGE_S = 600.0
DEFAULT_MAX_EVIDENCE_AGE_DAYS = 30.0

SOURCE_MATRIX = [
    {
        "source": "Moonraker mcu / mcu nozzle_mcu (mcu_version)",
        "category": "observed",
        "roles": ["main", "nozzle"],
        "reliability": "running Kalico application string; says nothing about "
        "the Creality loader or the stock application token",
    },
    {
        "source": "motor FLASH_PARAM id 0 (MOTOR_READ_PARAM)",
        "category": "observed",
        "roles": ["motor_x", "motor_y", "motor_e"],
        "reliability": "exact fingerprint of known applications "
        "(0x0247 mot2_002_071, 0x024b mot2_002_081); not the hardware target",
    },
    {
        "source": "box cfs_versions VERSION_SN",
        "category": "observed",
        "roles": ["cfs_*"],
        "reliability": "application only (1.1.3, 1.5.0); G30/G32 images are "
        "byte-identical, so never the boot/hardware variant",
    },
    {
        "source": "loader-probe evidence (e.g. "
        "evidence/k2_pro_live_loader_probe_2026-10-04.json)",
        "category": "loader",
        "roles": ["main", "nozzle", "motor_x", "motor_y", "motor_e", "cfs_*"],
        "reliability": "hardware + application from the loader handshake on "
        "this printer, on the evidence date; checked against the runtime "
        "fingerprint where one exists",
    },
    {
        "source": "stock F012 table (live.STOCK_F012_DIRECT_MCU_TARGETS)",
        "category": "package",
        "roles": ["main", "nozzle"],
        "reliability": "the unique stock artifact for the role; "
        "runtime_verified=false",
    },
    {
        "source": "explicit manifest (k2fw scan/compare output)",
        "category": "package",
        "roles": ["all"],
        "reliability": "exact only with a known hardware token and a single "
        "match; motor/CFS without loader identity stay ambiguous",
    },
]


# --- helpers -----------------------------------------------------------------


def _split_identity(token: str | None) -> tuple[str | None, str | None]:
    """'mot2_022_C30-mot2_002_071' -> ('mot2_022_C30', 'mot2_002_071')."""
    if not token or "-" not in str(token):
        return None, None
    hardware, application = str(token).split("-", 1)
    return hardware or None, application or None


def _artifact_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("path", "hardware", "application", "kind", "size", "sha256")
    }


def _under_model(item: dict[str, Any], model: str) -> bool:
    parts = PurePosixPath(str(item.get("path", ""))).parts
    return bool(parts) and parts[0] == model


def _role_of(device: dict[str, Any]) -> str | None:
    name = str(device.get("device", ""))
    if name in FIXED_ROLES or name.startswith("cfs_"):
        return name
    return None


def _kind_of(role: str) -> str | None:
    if role.startswith("cfs_"):
        return "cfs"
    return ROLE_KINDS.get(role)


def _parse_date(text: str) -> float:
    day = _dt.date.fromisoformat(str(text))
    return _dt.datetime(day.year, day.month, day.day,
                        tzinfo=_dt.timezone.utc).timestamp()


# --- loader evidence ---------------------------------------------------------


def loader_identities_from_evidence(
    evidence: dict[str, Any],
    source: str,
    *,
    cfs_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Map an authorized loader-probe evidence file to roles.

    Accepts only the hardware-validated probe format (schema 1) that sent no
    erase, length, data or update request and omitted UniIDs. Returns
    ``{"source", "date", "identities": {role: {...}}, "unassigned": [...]}``.
    """
    safety = evidence.get("safety") or {}
    entry = evidence.get("entry") or {}
    if evidence.get("schema") != 1 or not isinstance(evidence.get("identities"), dict):
        raise ValueError("not a k2fw loader-probe evidence file (schema 1)")
    if not entry.get("hardware_validated"):
        raise ValueError("loader evidence is not marked hardware_validated")
    for flag in ("erase_sent", "firmware_data_sent", "firmware_length_sent",
                 "update_request_sent", "flash_allowed"):
        if safety.get(flag) is not False:
            raise ValueError(f"loader evidence safety flag {flag} is not false")
    if safety.get("uniids_omitted") is not True:
        raise ValueError("loader evidence must omit device UniIDs")
    date = evidence.get("date")
    if not date:
        raise ValueError("loader evidence has no date")

    ids = evidence["identities"]
    out: dict[str, Any] = {}
    unassigned: list[str] = []

    def put(role: str, token: str | None, note: str | None = None) -> None:
        hardware, application = _split_identity(token)
        if hardware is None:
            unassigned.append(f"{role}: malformed identity {token!r}")
            return
        out[role] = {"hardware": hardware, "application": application,
                     "note": note}

    if ids.get("main"):
        put("main", ids["main"])
    if ids.get("toolhead"):
        put("nozzle", ids["toolhead"])
    if ids.get("extruder"):
        put("motor_e", ids["extruder"],
            "read through the Nozzle MCU transparent loader path")
    motors = list(ids.get("rs485_motors") or [])
    if motors:
        if len(motors) == 2 and len(set(motors)) == 1:
            note = ("both RS-485 motors reported this same identity; "
                    "no per-axis attribution is needed")
            put("motor_x", motors[0], note)
            put("motor_y", motors[0], note)
        else:
            unassigned.append(
                "rs485_motors: identities differ or count is not 2, so they "
                "cannot be attributed to X/Y")
    if ids.get("cfs"):
        roles = list(cfs_roles or [])
        if len(roles) == 1:
            put(roles[0], ids["cfs"],
                "the only CFS present; the evidence carries no address")
        else:
            unassigned.append(
                f"cfs: {len(roles)} CFS units present, the evidence has no "
                "address to attribute it")
    return {"source": source, "date": str(date), "identities": out,
            "unassigned": unassigned}


# --- observations ------------------------------------------------------------


def _observation(device: dict[str, Any] | None, observed_at: float | None,
                 now: float, max_age_s: float) -> dict[str, Any]:
    empty = {"application": None, "fingerprint": None, "source": None,
             "observed_at": None, "age_s": None, "fresh": False}
    if not device or device.get("present") is False:
        return empty
    role = _role_of(device) or ""
    if role in ("main", "nozzle"):
        value = device.get("running_application")
        result = {
            # The Kalico version string is not a Creality application token.
            "application": None,
            "fingerprint": {"kind": "kalico_mcu_version", "value": value}
            if value else None,
            "source": "moonraker/" + str(device.get("object") or role),
        }
    elif role.startswith("motor_"):
        raw = device.get("flash_param_version")
        result = {
            "application": KNOWN_MOTOR_FLASH_PARAM_VERSIONS.get(raw)
            if isinstance(raw, int) else None,
            "fingerprint": {"kind": "flash_param_id0", "value": f"0x{raw:04x}"}
            if isinstance(raw, int) else None,
            "source": "moonraker/motor_control MOTOR_READ_PARAM",
        }
    elif role.startswith("cfs_"):
        raw = device.get("running_application_version")
        result = {
            "application": KNOWN_CFS_RUNTIME_VERSIONS.get(raw) if raw else None,
            "fingerprint": {"kind": "cfs_version_sn", "value": raw}
            if raw else None,
            "source": "moonraker/box cfs_versions",
        }
    else:
        return empty
    if result["fingerprint"] is None:
        return empty
    age = None if observed_at is None else max(0.0, now - observed_at)
    result.update({
        "observed_at": observed_at,
        "age_s": None if age is None else round(age, 1),
        "fresh": age is not None and age <= max_age_s,
    })
    return result


# --- package -----------------------------------------------------------------


def _package(role: str, hardware: str | None,
             manifest: dict[str, Any] | None) -> dict[str, Any]:
    kind = _kind_of(role)
    if manifest is None:
        stock = STOCK_F012_DIRECT_MCU_TARGETS.get(role)
        if stock and (hardware is None or hardware == stock["hardware"]):
            return {
                "status": "stock-table",
                "target": {"path": "F012/" + stock["artifact"],
                           "hardware": stock["hardware"],
                           "application": stock["application"],
                           "kind": kind, "size": stock["size"],
                           "sha256": stock["sha256"]},
                "candidates": [],
                "basis": "unique stock artifact for this role in F012 "
                "1.1.0.94 and 1.1.6.7.2",
                "runtime_verified": False,
            }
        return {"status": "not-compared", "target": None, "candidates": [],
                "basis": "no manifest supplied", "runtime_verified": False}

    artifacts = [a for a in manifest.get("artifacts", []) if a.get("kind") == kind]
    if kind in ("main_mcu", "nozzle_mcu", "motor"):
        artifacts = [a for a in artifacts if _under_model(a, "F012")]
    if hardware is None and role in STOCK_F012_DIRECT_MCU_TARGETS:
        hardware = STOCK_F012_DIRECT_MCU_TARGETS[role]["hardware"]
        basis = "stock F012 hardware token for this role (package provenance)"
    elif hardware is None:
        basis = "no verified hardware token: every artifact of this kind is a candidate"
    else:
        basis = "verified loader hardware token"
    if hardware is not None:
        matches = [a for a in artifacts if a.get("hardware") == hardware]
    else:
        # No hardware filter from application names: mot0/mot1/mot2 boards
        # all run mot2_* applications.
        matches = artifacts
    if hardware is not None and len(matches) == 1:
        return {"status": "exact", "target": _artifact_view(matches[0]),
                "candidates": [], "basis": basis, "runtime_verified": False,
                "manifest_release": manifest.get("release")}
    return {
        "status": "none" if not matches else "ambiguous",
        "target": None,
        "candidates": [_artifact_view(a) for a in matches],
        "basis": basis,
        "runtime_verified": False,
        "manifest_release": manifest.get("release"),
    }


# --- contract ----------------------------------------------------------------


def _record(role: str, device: dict[str, Any] | None, present: bool | None,
            loader: dict[str, Any] | None, loader_meta: dict[str, Any] | None,
            manifest: dict[str, Any] | None, observed_at: float | None,
            now: float, max_age_s: float, max_evidence_days: float) -> dict[str, Any]:
    notes: list[str] = []
    observed = _observation(device, observed_at, now, max_age_s)
    if present is None:
        notes.append("not observed: the live status did not report this role")
    if observed["fingerprint"] and not observed["fresh"]:
        notes.append("observation is stale or undated; not used for decisions")

    loader_view = {"status": "absent", "hardware": None, "application": None,
                   "source": None, "evidence_date": None, "evidence_age_days": None,
                   "cross_check": None, "note": None}
    loader_usable = False
    if loader is not None and present is not False:
        age_days = (now - _parse_date(loader_meta["date"])) / 86400.0
        loader_view.update({
            "hardware": loader["hardware"],
            "application": loader["application"],
            "source": loader_meta["source"],
            "evidence_date": loader_meta["date"],
            "evidence_age_days": round(age_days, 1),
            "note": loader.get("note"),
        })
        if role in ("main", "nozzle"):
            cross = "not-available"
        elif not observed["fresh"] or observed["application"] is None:
            cross = "unchecked"
        elif observed["application"] == loader["application"]:
            cross = "match"
        else:
            cross = "conflict"
        loader_view["cross_check"] = cross
        if cross == "conflict":
            loader_view["status"] = "conflict"
            notes.append("running application differs from the loader evidence "
                         "(reflashed since?): loader identity not used")
        elif cross == "match" or age_days <= max_evidence_days:
            loader_view["status"] = "verified"
            loader_usable = True
        else:
            loader_view["status"] = "expired"
            notes.append(f"loader evidence older than {max_evidence_days:g} days "
                         "with no runtime cross-check: not used")

    hardware = loader_view["hardware"] if loader_usable else None
    package = _package(role, hardware, manifest)

    if loader_usable:
        level = "loader-verified"
    elif observed["fresh"] and observed["application"]:
        level = "runtime-fingerprint"
    elif observed["fresh"] and observed["fingerprint"]:
        level = "runtime-observed"
    elif package["target"] is not None and present is not False:
        level = "package-provenance"
    else:
        level = "unknown"

    update_required = None
    target = package["target"]
    if (loader_usable and package["status"] == "exact" and target
            and target.get("application") and loader_view["application"]):
        update_required = loader_view["application"] != target["application"]
    elif package["status"] in ("ambiguous", "none"):
        notes.append("no exact package target: update_required stays unknown")

    if present is False:
        observed = _observation(None, None, now, max_age_s)
        package = {"status": "not-compared", "target": None, "candidates": [],
                   "basis": "device absent", "runtime_verified": False}
        level = "unknown"
        update_required = None

    return {
        "role": role,
        "present": present,
        "observed": observed,
        "loader": loader_view,
        "package": package,
        "verification": level,
        "update_required": update_required,
        "flash_allowed": False,
        "notes": notes,
    }


def build_identity_contract(
    live_status: dict[str, Any] | None,
    *,
    now: float,
    observed_at: float | None = None,
    loader_evidence: dict[str, Any] | None = None,
    loader_evidence_source: str | None = None,
    manifest: dict[str, Any] | None = None,
    max_observation_age_s: float = DEFAULT_MAX_OBSERVATION_AGE_S,
    max_evidence_age_days: float = DEFAULT_MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, Any]:
    """Build the identity contract from data already collected.

    ``live_status`` is a ``k2fw status`` result (or ``None``). A device may be
    reported absent with ``{"device": role, "present": false}``. This function
    performs no I/O and never queries firmware.
    """
    status = deepcopy(live_status) if live_status else {"devices": []}
    if observed_at is None:
        observed_at = status.get("observed_at")
    by_role: dict[str, dict[str, Any]] = {}
    for device in status.get("devices", []):
        role = _role_of(device)
        if role:
            by_role[role] = device

    cfs_roles = sorted((r for r in by_role
                        if r.startswith("cfs_") and by_role[r].get("present") is not False),
                       key=lambda r: int(r.split("_", 1)[1]))
    loader_map: dict[str, Any] = {"identities": {}, "unassigned": [],
                                  "source": None, "date": None}
    if loader_evidence is not None:
        loader_map = loader_identities_from_evidence(
            loader_evidence, loader_evidence_source or "loader evidence",
            cfs_roles=cfs_roles)

    roles = list(FIXED_ROLES) + cfs_roles + sorted(
        (r for r in by_role if r.startswith("cfs_") and r not in cfs_roles),
        key=lambda r: int(r.split("_", 1)[1]))
    devices = []
    for role in roles:
        device = by_role.get(role)
        if device is None:
            present = None if live_status is None or role in FIXED_ROLES else False
        else:
            present = device.get("present", True) is not False
        devices.append(_record(
            role, device, present, loader_map["identities"].get(role),
            loader_map, manifest, observed_at, now,
            max_observation_age_s, max_evidence_age_days))

    return {
        "schema": SCHEMA,
        "generated_at": now,
        "observed_at": observed_at,
        "inputs": {
            "live_status": live_status is not None,
            "loader_evidence": loader_map["source"],
            "loader_evidence_date": loader_map["date"],
            "loader_unassigned": loader_map["unassigned"],
            "manifest_release": (manifest or {}).get("release"),
        },
        "policy": {
            "categories_kept_apart": ["observed", "loader", "package"],
            "update_required": "only with a verified, current loader identity "
            "and an exact single package target",
            "max_observation_age_s": max_observation_age_s,
            "max_evidence_age_days": max_evidence_age_days,
            "flash_allowed": False,
        },
        "devices": devices,
        "write_enabled": False,
        "flash_allowed": False,
    }
