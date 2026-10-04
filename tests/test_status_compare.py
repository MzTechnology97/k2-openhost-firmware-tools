from k2fw.status_compare import compare_live_status_to_manifest


def _artifact(path, hardware, application, kind, sha):
    return {
        "path": path,
        "hardware": hardware,
        "application": application,
        "kind": kind,
        "size": 123,
        "sha256": sha * 64,
    }


def _manifest():
    return {
        "schema": 1,
        "artifacts": [
            _artifact(
                "F012/mcu0_120_G32-mcu0_001_000.bin",
                "mcu0_120_G32",
                "mcu0_001_000",
                "main_mcu",
                "a",
            ),
            _artifact(
                "F012/noz0_130_G30-noz0_021_001.bin",
                "noz0_130_G30",
                "noz0_021_001",
                "nozzle_mcu",
                "b",
            ),
            _artifact(
                "F012/motor/mot0_023_C30-mot2_002_081.bin",
                "mot0_023_C30",
                "mot2_002_081",
                "motor",
                "c",
            ),
            _artifact(
                "F012/motor/mot1_023_C30-mot2_002_081.bin",
                "mot1_023_C30",
                "mot2_002_081",
                "motor",
                "d",
            ),
            _artifact(
                "cfs/cfs0_050_G30-cfs0_000_150.bin",
                "cfs0_050_G30",
                "cfs0_000_150",
                "cfs",
                "e",
            ),
            _artifact(
                "cfs/cfs0_050_G32-cfs0_000_150.bin",
                "cfs0_050_G32",
                "cfs0_000_150",
                "cfs",
                "f",
            ),
            _artifact(
                "cfs/cfs6_100_G31-cfs6_220_000.bin",
                "cfs6_100_G31",
                "cfs6_220_000",
                "cfs",
                "0",
            ),
        ],
    }


def _live_status():
    return {
        "schema": 1,
        "source": "live-read-only",
        "write_enabled": False,
        "devices": [
            {
                "device": "main",
                "running_application": "kalico-main",
                "stock_package_candidate": {
                    "printer_model": "F012",
                    "hardware": "mcu0_120_G32",
                    "application": "mcu0_001_000",
                    "runtime_verified": False,
                },
                "write_enabled": False,
            },
            {
                "device": "nozzle",
                "running_application": "kalico-nozzle",
                "stock_package_candidate": {
                    "printer_model": "F012",
                    "hardware": "noz0_130_G30",
                    "application": "noz0_021_000",
                    "runtime_verified": False,
                },
                "write_enabled": False,
            },
            {
                "device": "motor_x",
                "matched_application": "mot2_002_071",
                "write_enabled": False,
            },
            {
                "device": "cfs_1",
                "matched_application": "cfs0_000_113",
                "boot_hardware": None,
                "write_enabled": False,
            },
        ],
    }


def test_direct_mcu_uses_package_provenance_without_claiming_live_identity():
    result = compare_live_status_to_manifest(_live_status(), _manifest())
    main = result["devices"][0]["manifest_comparison"]
    nozzle = result["devices"][1]["manifest_comparison"]

    assert main["status"] == "package-target-present"
    assert main["artifact"]["hardware"] == "mcu0_120_G32"
    assert main["package_application_differs"] is False
    assert main["runtime_hardware_verified"] is False
    assert main["update_required"] is None
    assert main["flash_allowed"] is False

    assert nozzle["status"] == "package-target-present"
    assert nozzle["target_application"] == "noz0_021_001"
    assert nozzle["package_application_differs"] is True
    assert nozzle["update_required"] is None
    assert nozzle["flash_allowed"] is False
def test_motor_comparison_lists_apps_but_never_selects_hardware():
    result = compare_live_status_to_manifest(_live_status(), _manifest())
    motor = result["devices"][2]["manifest_comparison"]

    assert motor["mode"] == "application-fingerprint-only"
    assert motor["status"] == "hardware-unresolved"
    assert motor["exact_hardware"] is None
    assert motor["runtime_application"] == "mot2_002_071"
    assert motor["runtime_application_present"] is False
    assert motor["candidate_applications"] == ["mot2_002_081"]
    assert len(motor["candidates"]) == 2
    assert motor["update_required"] is None
    assert motor["flash_allowed"] is False


def test_cfs_comparison_stays_ambiguous_between_g30_and_g32():
    result = compare_live_status_to_manifest(_live_status(), _manifest())
    cfs = result["devices"][3]["manifest_comparison"]

    assert cfs["mode"] == "application-fingerprint-only"
    assert cfs["status"] == "hardware-unresolved"
    assert cfs["runtime_application"] == "cfs0_000_113"
    assert cfs["candidate_applications"] == ["cfs0_000_150"]
    assert len(cfs["candidates"]) == 2
    assert {x["hardware"] for x in cfs["candidates"]} == {
        "cfs0_050_G30",
        "cfs0_050_G32",
    }
    assert cfs["update_required"] is None
    assert cfs["flash_allowed"] is False


def test_top_level_manifest_comparison_never_enables_decisions_or_writes():
    result = compare_live_status_to_manifest(_live_status(), _manifest())
    meta = result["manifest_comparison"]

    assert result["write_enabled"] is False
    assert meta["mode"] == "read-only"
    assert meta["artifact_count"] == 7
    assert meta["update_decisions_enabled"] is False
    assert meta["write_enabled"] is False
    assert meta["flash_allowed"] is False

def test_live_loader_identity_resolves_exact_motor_target_without_enabling_flash():
    live = _live_status()
    live["devices"][2]["loader_identity"] = {
        "hardware": "mot2_023_C30",
        "application": "mot2_002_071",
        "source": "live-loader-probe",
    }
    manifest = _manifest()
    manifest["artifacts"].append(_artifact(
        "F012/motor/mot2_023_C30-mot2_002_081.bin",
        "mot2_023_C30",
        "mot2_002_081",
        "motor",
        "1",
    ))
    result = compare_live_status_to_manifest(live, manifest)
    motor = result["devices"][2]["manifest_comparison"]
    assert motor["mode"] == "live-loader-identity"
    assert motor["status"] == "exact-target-present"
    assert motor["exact_hardware"] == "mot2_023_C30"
    assert motor["runtime_hardware_verified"] is True
    assert motor["runtime_application"] == "mot2_002_071"
    assert motor["target_application"] == "mot2_002_081"
    assert motor["update_required"] is True
    assert motor["target_selection"] == "resolved-from-live-loader-identity"
    assert motor["flash_allowed"] is False


def test_live_loader_identity_resolves_exact_cfs_variant():
    live = _live_status()
    live["devices"][3]["loader_identity"] = {
        "hardware": "cfs0_050_G32",
        "application": "cfs0_000_113",
        "source": "live-loader-probe",
    }
    result = compare_live_status_to_manifest(live, _manifest())
    cfs = result["devices"][3]["manifest_comparison"]
    assert cfs["mode"] == "live-loader-identity"
    assert cfs["status"] == "exact-target-present"
    assert cfs["exact_hardware"] == "cfs0_050_G32"
    assert cfs["target_application"] == "cfs0_000_150"
    assert cfs["update_required"] is True
    assert cfs["flash_allowed"] is False


def test_live_loader_identity_overrides_package_provenance_for_direct_mcu():
    live = _live_status()
    live["devices"][0]["loader_identity"] = {
        "hardware": "mcu0_120_G32",
        "application": "mcu0_001_000",
        "source": "live-loader-probe",
    }
    result = compare_live_status_to_manifest(live, _manifest())
    main = result["devices"][0]["manifest_comparison"]
    assert main["mode"] == "live-loader-identity"
    assert main["runtime_hardware_verified"] is True
    assert main["update_required"] is False
    assert main["flash_allowed"] is False