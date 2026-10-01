import pytest

from k2fw.selection import build_candidate_plan, select_target


def _manifest():
    return {
        "artifacts": [
            {
                "path": "cfs/cfs0_050_G30-cfs0_000_150.bin",
                "hardware": "cfs0_050_G30",
                "application": "cfs0_000_150",
                "kind": "cfs",
                "size": 175104,
                "sha256": "a" * 64,
            },
            {
                "path": "F008/motor/mot0_023_C30-mot2_002_081.bin",
                "hardware": "mot0_023_C30",
                "application": "mot2_002_081",
                "kind": "motor",
                "size": 116396,
                "sha256": "b" * 64,
            },
            {
                "path": "F012/motor/mot0_023_C30-mot2_002_081.bin",
                "hardware": "mot0_023_C30",
                "application": "mot2_002_081",
                "kind": "motor",
                "size": 116396,
                "sha256": "b" * 64,
            },
        ]
    }


def test_resolve_unique_cfs_candidate():
    item = select_target(_manifest(), "cfs0_050_G30", kind="cfs")
    assert item["application"] == "cfs0_000_150"


def test_duplicate_hardware_requires_parent():
    with pytest.raises(ValueError, match="ambiguous"):
        select_target(_manifest(), "mot0_023_C30", kind="motor")
    item = select_target(
        _manifest(), "mot0_023_C30", kind="motor", parent="F012/motor"
    )
    assert item["path"].startswith("F012/")


def test_candidate_plan_never_enables_write():
    plan = build_candidate_plan(
        _manifest(),
        "cfs0_050_G30",
        kind="cfs",
        parent="cfs",
        current_application="cfs0_000_113",
    )
    assert plan["update_required"] is True
    assert plan["target_application"] == "cfs0_000_150"
    assert plan["write_enabled"] is False
    assert plan["safety"]["flash_allowed"] is False
