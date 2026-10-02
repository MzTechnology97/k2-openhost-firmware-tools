from k2fw.live import (
    CFS_BOOT_VARIANT_REASON,
    KNOWN_CFS_RUNTIME_VERSIONS,
    normalize_cfs_runtime,
)


def test_known_cfs_runtime_versions_map_application_only():
    assert KNOWN_CFS_RUNTIME_VERSIONS["1.1.3"] == "cfs0_000_113"
    assert KNOWN_CFS_RUNTIME_VERSIONS["1.5.0"] == "cfs0_000_150"


def test_normalize_cfs_runtime_hides_device_identity_and_keeps_boot_unknown():
    result = normalize_cfs_runtime(
        "1",
        {
            "firmware": "1.1.3",
            "serial": "DO-NOT-EXPOSE",
            "text": "113DO-NOT-EXPOSE",
            "payload": "deadbeef",
            "raw": "f7...",
        },
    )
    assert result["device"] == "cfs_1"
    assert result["address"] == 1
    assert result["running_application_version"] == "1.1.3"
    assert result["matched_application"] == "cfs0_000_113"
    assert result["boot_hardware"] is None
    assert result["boot_hardware_reason"] == CFS_BOOT_VARIANT_REASON
    assert "serial" not in result
    assert "text" not in result
    assert "payload" not in result
    assert "raw" not in result
    assert result["write_enabled"] is False


def test_unknown_cfs_application_is_not_inferred():
    result = normalize_cfs_runtime("2", {"firmware": "9.9.9"})
    assert result["matched_application"] is None
    assert result["boot_hardware"] is None
