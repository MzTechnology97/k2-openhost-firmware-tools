from collections import deque

import pytest

from k2fw.cfs_loader import (
    AUTO_ASSIGN,
    AUTO_DISCOVER,
    AUTO_QUERY,
    CMD_ENTER_BOOTLOADER,
    MODE_APP,
    MODE_LOADER,
    guard_cfs_loader_probe_frame,
    run_cfs_loader_probe_session,
)
from k2fw.rs485 import FRAME_HEAD, crc8


UID = bytes(range(1, 13))
IDENTITY = b"cfs0_050_G32-cfs0_000_150"


def response(address, command, payload=b"", status=0):
    body = bytes((address, len(payload) + 3, status, command)) + bytes(payload)
    return bytes((FRAME_HEAD,)) + body + bytes((crc8(body[1:]),))


def auto_payload(mode):
    return bytes((1, mode)) + UID


class FakeIO:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.frames = []

    def send(self, frame):
        guard_cfs_loader_probe_frame(frame)
        self.frames.append(bytes(frame))

    def exchange(self, frame, timeout=None):
        guard_cfs_loader_probe_frame(frame)
        self.frames.append(bytes(frame))
        if not self.responses:
            raise TimeoutError("scripted timeout")
        item = self.responses.popleft()
        if isinstance(item, Exception):
            raise item
        return item


def success_responses(sector=0xE0):
    return [
        response(0xFE, AUTO_DISCOVER, auto_payload(MODE_LOADER)),
        response(1, AUTO_ASSIGN, auto_payload(MODE_LOADER)),
        response(1, 0xF0, IDENTITY),
        response(1, 0xF0, bytes((sector,))),
        response(1, 0xF0, b"\x75"),
        response(1, AUTO_ASSIGN, auto_payload(MODE_APP)),
        response(1, AUTO_QUERY, auto_payload(MODE_APP)),
    ]


def test_guard_rejects_every_destructive_f0_variant():
    from k2fw.cfs_loader import build_any_address_frame

    for payload in (
        b"\x06",  # erase
        b"\x01",  # update request
        b"\x00\xac\x02\x00",  # application length-like payload
        b"firmware-data",
    ):
        with pytest.raises(ValueError, match="allowlist"):
            guard_cfs_loader_probe_frame(
                build_any_address_frame(1, 0xF0, payload)
            )


def test_successful_loader_probe_reads_identity_sector_and_restores_app():
    io = FakeIO(success_responses())
    result = run_cfs_loader_probe_session(
        io, assigned_address=1, sleep=lambda _seconds: None
    )

    assert result["entered_loader"] is True
    assert result["loader_identity"]["hardware"] == "cfs0_050_G32"
    assert result["loader_identity"]["application"] == "cfs0_000_150"
    assert result["sector_token"] == 0xE0
    assert result["sector_chunk_size"] == 128
    assert result["application_restored"] is True
    assert result["erase_performed"] is False
    assert result["update_request_performed"] is False
    assert result["application_data_sent"] is False
    assert result["flash_allowed"] is False

    commands = [(frame[1], frame[4], frame[5:-1]) for frame in io.frames]
    assert commands[0] == (0xEB, CMD_ENTER_BOOTLOADER, b"")
    assert (1, 0xF0, b"\x06") not in commands
    assert (1, 0xF0, b"\x01") not in commands


def test_probe_always_attempts_restore_when_identity_read_fails():
    scripted = [
        response(0xFE, AUTO_DISCOVER, auto_payload(MODE_LOADER)),
        response(1, AUTO_ASSIGN, auto_payload(MODE_LOADER)),
        RuntimeError("identity read failed"),
        response(1, 0xF0, b"\x75"),
        response(1, AUTO_ASSIGN, auto_payload(MODE_APP)),
        response(1, AUTO_QUERY, auto_payload(MODE_APP)),
    ]
    io = FakeIO(scripted)

    with pytest.raises(RuntimeError, match="identity read failed"):
        run_cfs_loader_probe_session(
            io, assigned_address=1, sleep=lambda _seconds: None
        )

    assert any(frame[4] == 0xF0 and frame[5:-1] == b"\x02" for frame in io.frames)
    assert all(
        not (frame[4] == 0xF0 and frame[5:-1] in (b"\x06", b"\x01"))
        for frame in io.frames
    )


def test_restore_falls_back_to_jacob_0b01_when_f002_path_fails():
    scripted = [
        response(0xFE, AUTO_DISCOVER, auto_payload(MODE_LOADER)),
        response(1, AUTO_ASSIGN, auto_payload(MODE_LOADER)),
        response(1, 0xF0, IDENTITY),
        response(1, 0xF0, b"\xe0"),
        TimeoutError("no F0/02 ack"),
        TimeoutError("first A0 restore failed"),
        TimeoutError("first A2 verify failed"),
        response(1, AUTO_ASSIGN, auto_payload(MODE_APP)),
        response(1, AUTO_QUERY, auto_payload(MODE_APP)),
    ]
    io = FakeIO(scripted)
    result = run_cfs_loader_probe_session(
        io, assigned_address=1, sleep=lambda _seconds: None
    )

    assert result["application_restored"] is True
    assert any(frame[1] == 0xFF and frame[4] == 0x0B for frame in io.frames)


def test_invalid_loader_mode_is_rejected_but_restore_still_runs():
    scripted = [
        response(0xFE, AUTO_DISCOVER, auto_payload(MODE_APP)),
        TimeoutError("F0/02 unavailable"),
        TimeoutError("A2 unavailable"),
    ]
    io = FakeIO(scripted)

    with pytest.raises(RuntimeError, match="did not report loader mode"):
        run_cfs_loader_probe_session(
            io, assigned_address=1, sleep=lambda _seconds: None
        )

    assert any(frame[1] == 0xFF and frame[4] == 0x0B for frame in io.frames)