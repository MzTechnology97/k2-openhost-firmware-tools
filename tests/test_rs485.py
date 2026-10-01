import unittest

from k2fw.rs485 import build_frame, crc8, decode_response


class Rs485Tests(unittest.TestCase):
    def test_version_request_frame(self):
        self.assertEqual(build_frame(1, 0x14).hex(), "f70103ff1406")

    def test_crc_matches_k2_polynomial(self):
        self.assertEqual(crc8(bytes.fromhex("03ff14")), 0x06)

    def test_decode_version_response(self):
        body = bytes((1, 6, 0, 0x14)) + b"150"
        frame = bytes((0xF7,)) + body + bytes((crc8(body[1:]),))
        reply = decode_response(frame, 1, 0x14)
        self.assertEqual(reply["status"], 0)
        self.assertEqual(reply["payload"], b"150")


if __name__ == "__main__":
    unittest.main()
