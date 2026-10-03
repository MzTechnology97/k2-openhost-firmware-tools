from k2fw.cli import build_parser


def test_probe_motors_command_is_registered():
    args = build_parser().parse_args(["probe-motors"])
    assert args.command == "probe-motors"
    assert args.moonraker == "http://127.0.0.1:7125"


def test_status_command_is_registered():
    args = build_parser().parse_args(["status"])
    assert args.command == "status"
    assert args.moonraker == "http://127.0.0.1:7125"


def test_status_manifest_option_is_explicit_and_optional():
    args = build_parser().parse_args(["status"])
    assert args.manifest is None

    args = build_parser().parse_args(["status", "--manifest", "firmware.json"])
    assert args.manifest == "firmware.json"


def test_inspect_update_sector_token_is_explicit_and_optional():
    args = build_parser().parse_args(["inspect-update", "fw.bin"])
    assert args.sector_token is None
    assert args.address == 1

    args = build_parser().parse_args(
        [
            "inspect-update",
            "fw.bin",
            "--address",
            "7",
            "--sector-token",
            "0xc1",
        ]
    )
    assert args.sector_token == 0xC1
    assert args.address == 7

    alias = build_parser().parse_args(
        ["inspect-update", "fw.bin", "--sector-code", "0xfe"]
    )
    assert alias.sector_token == 0xFE

def test_inspect_mcu_update_sector_token_is_explicit_and_optional():
    args = build_parser().parse_args(
        ["inspect-mcu-update", "mcu0_120_G32-mcu0_001_000.bin"]
    )
    assert args.sector_token is None

    args = build_parser().parse_args(
        [
            "inspect-mcu-update",
            "noz0_130_G30-noz0_021_000.bin",
            "--sector-token",
            "0x04",
        ]
    )
    assert args.sector_token == 0x04