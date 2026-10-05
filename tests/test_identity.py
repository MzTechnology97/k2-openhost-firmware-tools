import json
from copy import deepcopy
from pathlib import Path

import pytest

from k2fw.cli import main
from k2fw.identity import (
    SCHEMA,
    VERIFICATION_LEVELS,
    build_identity_contract,
    loader_identities_from_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads(
    (ROOT / "evidence/k2_pro_live_loader_probe_2026-10-04.json").read_text()
)
MANIFEST = json.loads(
    (ROOT / "evidence/relevant_manifest_1.1.6.7.2.json").read_text()
)
EVIDENCE_DAY = 1791072000.0  # 2026-10-04T00:00:00Z
NOW = EVIDENCE_DAY + 3600.0


def live_status(*, x=0x0247, y=0x0247, e=0x0247, cfs="1.1.3"):
    """A `k2fw status`-shaped result, anonymized (no UIDs or serials)."""
    devices = [
        {"device": "main", "object": "mcu",
         "running_application": "v2025.01-k2-test"},
        {"device": "nozzle", "object": "mcu nozzle_mcu",
         "running_application": "v2025.01-k2-test"},
    ]
    for axis, value in (("x", x), ("y", y), ("e", e)):
        if value is None:
            devices.append({"device": f"motor_{axis}", "present": False})
        else:
            devices.append({"device": f"motor_{axis}", "axis": axis,
                            "flash_param_version": value})
    if cfs is not None:
        devices.append({"device": "cfs_1", "address": 1,
                        "running_application_version": cfs})
    return {"schema": 1, "devices": devices}


def by_role(contract):
    return {d["role"]: d for d in contract["devices"]}


def test_contract_shape_and_global_safety():
    c = build_identity_contract(live_status(), now=NOW, observed_at=NOW)
    assert c["schema"] == SCHEMA
    assert c["flash_allowed"] is False and c["write_enabled"] is False
    assert [d["role"] for d in c["devices"]] == [
        "main", "nozzle", "motor_x", "motor_y", "motor_e", "cfs_1"]
    for d in c["devices"]:
        assert d["flash_allowed"] is False
        assert d["verification"] in VERIFICATION_LEVELS
        assert set(d) >= {"observed", "loader", "package", "update_required"}


def test_known_fingerprint_is_runtime_only():
    d = by_role(build_identity_contract(live_status(), now=NOW, observed_at=NOW))
    x = d["motor_x"]
    assert x["observed"]["application"] == "mot2_002_071"
    assert x["observed"]["fingerprint"] == {"kind": "flash_param_id0", "value": "0x0247"}
    assert x["verification"] == "runtime-fingerprint"
    # a runtime fingerprint never becomes a hardware/loader identity
    assert x["loader"]["status"] == "absent" and x["loader"]["hardware"] is None
    assert x["update_required"] is None
    cfs = d["cfs_1"]
    assert cfs["observed"]["application"] == "cfs0_000_113"
    assert cfs["loader"]["hardware"] is None


def test_unknown_fingerprint_stays_unknown():
    d = by_role(build_identity_contract(live_status(x=0x0999, cfs="9.9.9"),
                                        now=NOW, observed_at=NOW))
    assert d["motor_x"]["observed"]["application"] is None
    assert d["motor_x"]["observed"]["fingerprint"]["value"] == "0x0999"
    assert d["motor_x"]["verification"] == "runtime-observed"
    assert d["cfs_1"]["observed"]["application"] is None
    assert d["cfs_1"]["update_required"] is None


def test_main_nozzle_runtime_string_is_not_a_creality_token():
    d = by_role(build_identity_contract(live_status(), now=NOW, observed_at=NOW))
    main = d["main"]
    assert main["observed"]["application"] is None
    assert main["observed"]["fingerprint"]["kind"] == "kalico_mcu_version"
    assert main["verification"] == "runtime-observed"
    # package target from the stock table, explicitly not runtime verified
    assert main["package"]["status"] == "stock-table"
    assert main["package"]["target"]["hardware"] == "mcu0_120_G32"
    assert main["package"]["runtime_verified"] is False
    assert main["update_required"] is None


def test_ambiguous_manifest_target_without_loader_identity():
    d = by_role(build_identity_contract(live_status(), now=NOW, observed_at=NOW,
                                        manifest=MANIFEST))
    x = d["motor_x"]
    assert x["package"]["status"] == "ambiguous"
    assert len(x["package"]["candidates"]) == 7  # every F012 motor artifact
    assert x["update_required"] is None
    assert any("no exact package target" in n for n in x["notes"])
    assert d["cfs_1"]["package"]["status"] == "ambiguous"


def test_package_target_without_runtime_verification():
    d = by_role(build_identity_contract(live_status(), now=NOW, observed_at=NOW,
                                        manifest=MANIFEST))
    main = d["main"]
    assert main["package"]["status"] == "exact"
    assert main["package"]["target"]["path"] == "F012/mcu0_120_G32-mcu0_001_000.bin"
    assert main["package"]["runtime_verified"] is False
    assert main["verification"] == "runtime-observed"
    assert main["update_required"] is None  # provenance alone decides nothing


def test_verified_loader_identity_from_authorized_evidence():
    c = build_identity_contract(
        live_status(), now=NOW, observed_at=NOW, manifest=MANIFEST,
        loader_evidence=EVIDENCE,
        loader_evidence_source="k2_pro_live_loader_probe_2026-10-04.json")
    d = by_role(c)
    for role, hardware in (("main", "mcu0_120_G32"), ("nozzle", "noz0_130_G30"),
                           ("motor_x", "mot2_023_C30"), ("motor_y", "mot2_023_C30"),
                           ("motor_e", "mot2_022_C30"), ("cfs_1", "cfs0_050_G32")):
        rec = d[role]
        assert rec["verification"] == "loader-verified", role
        assert rec["loader"]["hardware"] == hardware
        assert rec["loader"]["status"] == "verified"
        assert rec["package"]["status"] == "exact"
        assert rec["flash_allowed"] is False
    assert d["main"]["update_required"] is False
    assert d["nozzle"]["update_required"] is False
    assert d["motor_x"]["update_required"] is True  # 071 -> 081
    assert d["motor_e"]["package"]["target"]["path"] == "F012/mot2_022_C30-mot2_002_081.bin"
    assert d["cfs_1"]["update_required"] is True  # 113 -> 150
    assert d["motor_x"]["loader"]["cross_check"] == "match"
    assert d["main"]["loader"]["cross_check"] == "not-available"
    assert c["inputs"]["loader_unassigned"] == []


def test_loader_conflict_with_runtime_is_not_used():
    d = by_role(build_identity_contract(
        live_status(x=0x024B), now=NOW, observed_at=NOW, manifest=MANIFEST,
        loader_evidence=EVIDENCE))
    x = d["motor_x"]
    assert x["loader"]["status"] == "conflict"
    assert x["verification"] == "runtime-fingerprint"
    assert x["update_required"] is None


def test_old_sample_is_stale_and_not_used_for_decisions():
    old = NOW - 3600.0
    d = by_role(build_identity_contract(live_status(), now=NOW, observed_at=old,
                                        manifest=MANIFEST))
    x = d["motor_x"]
    assert x["observed"]["fresh"] is False and x["observed"]["age_s"] == 3600.0
    # ambiguous package and no fresh reading: nothing is known
    assert x["verification"] == "unknown"
    # Main keeps its exact stock package target as provenance
    assert d["main"]["verification"] == "package-provenance"
    # undated saved status: stale as well
    d = by_role(build_identity_contract(live_status(), now=NOW))
    assert d["motor_x"]["observed"]["fresh"] is False


def test_old_evidence_needs_a_runtime_cross_check():
    late = EVIDENCE_DAY + 60 * 86400.0
    d = by_role(build_identity_contract(live_status(), now=late, observed_at=late,
                                        manifest=MANIFEST, loader_evidence=EVIDENCE))
    # motors: runtime fingerprint matches the evidence, so it stays usable
    assert d["motor_x"]["loader"]["status"] == "verified"
    # main/nozzle: no runtime cross-check exists, so old evidence expires
    assert d["main"]["loader"]["status"] == "expired"
    assert d["main"]["update_required"] is None
    # stale observation + old evidence: unchecked and expired
    d = by_role(build_identity_contract(live_status(), now=late, observed_at=NOW,
                                        loader_evidence=EVIDENCE))
    assert d["motor_x"]["loader"]["cross_check"] == "unchecked"
    assert d["motor_x"]["loader"]["status"] == "expired"


def test_absent_device():
    d = by_role(build_identity_contract(live_status(y=None, cfs=None), now=NOW,
                                        observed_at=NOW, loader_evidence=EVIDENCE,
                                        manifest=MANIFEST))
    y = d["motor_y"]
    assert y["present"] is False and y["verification"] == "unknown"
    assert y["loader"]["status"] == "absent" and y["update_required"] is None
    assert "cfs_1" not in d  # no CFS reported: nothing invented


def test_cfs_evidence_not_attributed_with_two_units():
    status = live_status()
    status["devices"].append({"device": "cfs_2", "address": 2,
                              "running_application_version": "1.1.3"})
    c = build_identity_contract(status, now=NOW, observed_at=NOW,
                                loader_evidence=EVIDENCE)
    d = by_role(c)
    assert d["cfs_1"]["loader"]["status"] == "absent"
    assert d["cfs_2"]["loader"]["status"] == "absent"
    assert any(u.startswith("cfs:") for u in c["inputs"]["loader_unassigned"])


@pytest.mark.parametrize("path,value", [
    (("safety", "flash_allowed"), True),
    (("safety", "erase_sent"), True),
    (("safety", "uniids_omitted"), False),
    (("entry", "hardware_validated"), False),
    (("schema",), 2),
])
def test_unauthorized_evidence_is_rejected(path, value):
    bad = deepcopy(EVIDENCE)
    node = bad
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValueError):
        loader_identities_from_evidence(bad, "bad.json", cfs_roles=["cfs_1"])


def test_no_live_status_is_unknown_not_absent():
    d = by_role(build_identity_contract(None, now=NOW))
    assert d["motor_x"]["present"] is None
    assert d["motor_x"]["verification"] == "unknown"
    assert d["main"]["verification"] == "package-provenance"


def test_cli_identity_from_saved_status(tmp_path, capsys):
    status = live_status()
    status["observed_at"] = None
    (tmp_path / "status.json").write_text(json.dumps(status))
    (tmp_path / "evidence.json").write_text(json.dumps(EVIDENCE))
    out = tmp_path / "identity.json"
    assert main(["identity", "--from-status", str(tmp_path / "status.json"),
                 "--loader-evidence", str(tmp_path / "evidence.json"),
                 "--max-evidence-days", "100000", "-o", str(out)]) == 0
    c = json.loads(out.read_text())
    assert c["schema"] == SCHEMA and c["flash_allowed"] is False
    roles = by_role(c)
    assert roles["motor_x"]["observed"]["fresh"] is False  # undated file
    assert roles["main"]["loader"]["status"] == "verified"
    text = out.read_text()
    assert "uniid" not in text.lower() and "build_machine_uid" not in text
