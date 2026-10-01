import json
import tempfile
import unittest
from pathlib import Path

from k2fw.manifest import compare_manifests, parse_firmware_name, scan_tree


class FirmwareNameTests(unittest.TestCase):
    def test_cfs_name(self):
        item = parse_firmware_name("cfs0_050_G30-cfs0_000_150.bin")
        self.assertEqual(item["kind"], "cfs")
        self.assertEqual(item["hardware"], "cfs0_050_G30")
        self.assertEqual(item["application"], "cfs0_000_150")

    def test_motor_name(self):
        item = parse_firmware_name("mot1_023_C30-mot2_002_081.bin")
        self.assertEqual(item["kind"], "motor")
        self.assertEqual(item["hardware"], "mot1_023_C30")


class ScanTests(unittest.TestCase):
    def test_scan_and_compare_version_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old"
            new = root / "new"
            old.mkdir()
            new.mkdir()
            (old / "cfs0_050_G30-cfs0_000_113.bin").write_bytes(b"old")
            (new / "cfs0_050_G30-cfs0_000_150.bin").write_bytes(b"new")
            (new / "version.json").write_text(
                json.dumps({"CFSs": [{"app_ver": "cfs0_000_150"}]}),
                encoding="utf-8",
            )

            old_manifest = scan_tree(old)
            new_manifest = scan_tree(new)
            result = compare_manifests(old_manifest, new_manifest)

            self.assertEqual(result["summary"]["changed"], 1)
            self.assertEqual(result["summary"]["added"], 0)
            self.assertEqual(result["summary"]["removed"], 0)
            change = result["changed"][0]
            self.assertEqual(change["before"]["application"], "cfs0_000_113")
            self.assertEqual(change["after"]["application"], "cfs0_000_150")
            self.assertEqual(new_manifest["version_files"][0]["data"]["CFSs"][0]["app_ver"], "cfs0_000_150")


if __name__ == "__main__":
    unittest.main()
