import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rfid_diag_client", ROOT / "rfid_diag_client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

def test_crc_reference():
    # Same CRC-8 polynomial/path used by stock auto_addr_wrapper.py.
    data = bytes((5, 0, 0x57, 0, 0))
    assert client.crc8(data) == 0xDF

def test_detect_frame_roundtrip():
    f = client.build_frame(1, 0x57, bytes((0, 0)))
    assert f.hex() == "f7010500570000df"
    parsed = client.parse_frame(f)
    assert parsed["address"] == 1
    assert parsed["status"] == 0
    assert parsed["command"] == 0x57
    assert parsed["data"] == bytes((0, 0))

def test_auth_frame_shape():
    key = bytes.fromhex("ffffffffffff")
    f = client.build_frame(1, 0x57, bytes((1, 2, 4)) + key)
    parsed = client.parse_frame(f)
    assert parsed["length"] == 12
    assert parsed["data"] == bytes((1, 2, 4)) + key

def test_noauth_frame_shape():
    f = client.build_frame(1, 0x57, bytes((2, 3, 0)))
    parsed = client.parse_frame(f)
    assert parsed["length"] == 6
    assert parsed["data"] == bytes((2, 3, 0))

def test_detect_decoder():
    # ATQA 04 00, UID de ad be ef, matching BCC=22, SAK=08.
    data = bytes.fromhex("0400deadbeef2208")
    d = client.decode_detect(data)
    assert d["uid_hex"] == "deadbeef"
    assert d["bcc_valid"] is True
    assert d["sak_hex"] == "08"

def test_manifest_is_read_only():
    m = json.loads((ROOT / "patch_manifest.json").read_text())
    assert m["protocol"]["command"] == "0x57"
    assert m["safety"]["tag_write_supported"] is False
    assert m["safety"]["tag_emulation_supported"] is False
    assert m["safety"]["proprietary_key_embedded"] is False
    assert m["safety"]["caller_provided_key_only"] is True
    assert m["safety"]["flash_performed"] is False

if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"{len(tests)} tests passed")