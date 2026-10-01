from __future__ import annotations

import os
from pathlib import Path
from typing import Any


FRAME_HEAD = 0xF7
CMD_VERSION_SN = 0x14


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_frame(address: int, command: int, payload: bytes = b"", header: int = 0xFF) -> bytes:
    if not 1 <= address <= 0xFE:
        raise ValueError("address must be 1..254")
    if not 0 <= command <= 0xFF or not 0 <= header <= 0xFF:
        raise ValueError("command/header must be bytes")
    payload = bytes(payload)
    declared_len = len(payload) + 3
    if declared_len > 0xFF:
        raise ValueError("payload is too large")
    body = bytes((address, declared_len, header, command)) + payload
    return bytes((FRAME_HEAD,)) + body + bytes((crc8(body[1:]),))


def decode_response(frame: bytes, address: int, command: int) -> dict[str, Any]:
    frame = bytes(frame)
    if len(frame) < 6:
        raise ValueError("response is shorter than the six-byte envelope")
    if frame[0] != FRAME_HEAD:
        raise ValueError("response header is not 0xf7")
    if len(frame) != frame[2] + 3:
        raise ValueError("response length byte does not match frame length")
    if frame[1] != address:
        raise ValueError("response came from an unexpected address")
    if frame[4] != command:
        raise ValueError("response command does not match request")
    expected = crc8(frame[2:-1])
    if frame[-1] != expected:
        raise ValueError(
            f"response CRC mismatch: got 0x{frame[-1]:02x}, expected 0x{expected:02x}"
        )
    return {
        "address": frame[1],
        "status": frame[3],
        "command": frame[4],
        "payload": frame[5:-1],
        "raw": frame,
    }


def port_owners(port: str) -> list[dict[str, Any]]:
    """Best-effort Linux /proc check for processes already holding a serial port."""
    target = os.path.realpath(port)
    owners: list[dict[str, Any]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return owners
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        fd_dir = process / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except (OSError, PermissionError):
            continue
        for fd in fds:
            try:
                if os.path.realpath(fd) != target:
                    continue
                cmdline = (process / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                    "utf-8", "replace"
                ).strip()
                owners.append({"pid": int(process.name), "command": cmdline})
                break
            except (OSError, PermissionError):
                continue
    return owners


def _read_frame(serial_port) -> bytes:
    prefix = serial_port.read(3)
    if len(prefix) != 3:
        raise TimeoutError("timeout waiting for RS-485 response header")
    if prefix[0] != FRAME_HEAD:
        raise ValueError(f"unexpected RS-485 response head 0x{prefix[0]:02x}")
    remaining = prefix[2]
    tail = serial_port.read(remaining)
    if len(tail) != remaining:
        raise TimeoutError("timeout waiting for complete RS-485 response")
    return prefix + tail


def probe_cfs_version(
    port: str,
    address: int = 1,
    baud: int = 230400,
    timeout: float = 1.0,
) -> dict[str, Any]:
    owners = port_owners(port)
    if owners:
        detail = ", ".join(f"pid {o['pid']} {o['command']}" for o in owners)
        raise RuntimeError(f"serial port is already in use: {detail}")

    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is required for live probing") from exc

    request = build_frame(address, CMD_VERSION_SN)
    with serial.Serial(
        port=port,
        baudrate=baud,
        timeout=timeout,
        write_timeout=timeout,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    ) as device:
        device.reset_input_buffer()
        device.reset_output_buffer()
        device.write(request)
        device.flush()
        frame = _read_frame(device)

    reply = decode_response(frame, address, CMD_VERSION_SN)
    text = reply["payload"].rstrip(b"\x00").decode("ascii", "replace")
    firmware = None
    serial_number = None
    if len(text) >= 3 and text[:3].isdigit():
        firmware = ".".join(text[:3])
        serial_number = text[3:] or None

    return {
        "port": port,
        "baud": baud,
        "address": address,
        "status": reply["status"],
        "firmware": firmware,
        "serial": serial_number,
        "ascii": text,
        "request_hex": request.hex(),
        "response_hex": frame.hex(),
    }

# Stock mcu_util_485 read-only version request recovered from K2 Pro 1.1.0.94
# and 1.1.6.7.2.  The same 0xF0 command is also used by the stock updater for
# destructive stages with DIFFERENT payloads; this module deliberately exposes
# only the payload-0 version query.
CMD_STOCK_FIRMWARE = 0xF0
STOCK_VERSION_QUERY = b"\x00"
STOCK_VERSION_LENGTH = 25


def build_stock_version_request(address: int) -> bytes:
    """Build only the stock read-only firmware-version request (F0/00)."""
    return build_frame(address, CMD_STOCK_FIRMWARE, STOCK_VERSION_QUERY, header=0x00)


def parse_stock_version_payload(payload: bytes) -> dict[str, str]:
    payload = bytes(payload)
    if len(payload) != STOCK_VERSION_LENGTH:
        raise ValueError(
            f"stock version payload must be {STOCK_VERSION_LENGTH} bytes, got {len(payload)}"
        )
    try:
        version = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("stock version payload is not ASCII") from exc
    if any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in version):
        raise ValueError("stock version payload contains non-printable bytes")
    hardware, sep, application = version.partition("-")
    if not sep or not hardware or not application:
        raise ValueError("stock version payload is not hardware-application form")
    return {
        "version": version,
        "hardware": hardware,
        "application": application,
    }


def probe_rs485_firmware_version(
    port: str,
    address: int,
    baud: int = 230400,
    timeout: float = 1.0,
) -> dict[str, Any]:
    """Read one RS-485 device's 25-byte stock updater-stage identity.

    This sends exactly one F0/00 query.  It does not discover/assign addresses,
    erase private flash, request an update, transfer data, or start/reset an app.
    Stock analysis places this transaction after discovery/address handling and
    a normal running motor application does not respond to it, so this helper is
    protocol-recovery infrastructure rather than the normal runtime probe.
    The port must already be exclusively owned by this process.
    """
    owners = port_owners(port)
    if owners:
        detail = ", ".join(f"pid {o['pid']} {o['command']}" for o in owners)
        raise RuntimeError(f"serial port is already in use: {detail}")

    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is required for live probing") from exc

    request = build_stock_version_request(address)
    with serial.Serial(
        port=port,
        baudrate=baud,
        timeout=timeout,
        write_timeout=timeout,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    ) as device:
        device.reset_input_buffer()
        device.reset_output_buffer()
        device.write(request)
        device.flush()
        frame = _read_frame(device)

    reply = decode_response(frame, address, CMD_STOCK_FIRMWARE)
    if reply["status"] != 0:
        raise RuntimeError(f"version query returned status 0x{reply['status']:02x}")
    identity = parse_stock_version_payload(reply["payload"])
    return {
        "port": port,
        "baud": baud,
        "address": address,
        "status": reply["status"],
        **identity,
        "request_hex": request.hex(),
        "response_hex": frame.hex(),
        "protocol_scope": "stock updater stage",
        "write_enabled": False,
    }
