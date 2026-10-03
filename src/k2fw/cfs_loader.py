from __future__ import annotations

from typing import Any

from .rs485 import FRAME_HEAD, crc8
from .rs485_update import CMD_STOCK_FIRMWARE, SUB_GET_SECTOR_SIZE, SUB_GET_VERSION, SUB_START_APP

AUTO_ASSIGN = 0xA0
AUTO_DISCOVER = 0xA1
AUTO_QUERY = 0xA2
LOADER_TO_APP = 0x0B

MODE_APP = 0
MODE_LOADER = 1

ADDRESS_BROADCAST = 0xFE
ADDRESS_GENERAL_BROADCAST = 0xFF
ADDRESS_IAP_BROADCAST = 0xEB

CMD_ENTER_BOOTLOADER = 0x56


def build_any_address_frame(
    address: int,
    command: int,
    payload: bytes = b"",
    *,
    header: int = 0x00,
) -> bytes:
    """Build the Creality RS-485 envelope, including reserved broadcast addresses."""
    if not 0 <= address <= 0xFF:
        raise ValueError("address must be a byte")
    if not 0 <= command <= 0xFF or not 0 <= header <= 0xFF:
        raise ValueError("command/header must be bytes")
    payload = bytes(payload)
    declared_len = len(payload) + 3
    if declared_len > 0xFF:
        raise ValueError("payload is too large")
    body = bytes((address, declared_len, header, command)) + payload
    return bytes((FRAME_HEAD,)) + body + bytes((crc8(body[1:]),))


def parse_auto_mode_payload(payload: bytes) -> dict[str, Any]:
    """Decode the A0/A1/A2 identity payload used by the Jacob CFS driver."""
    payload = bytes(payload)
    if len(payload) != 14:
        raise ValueError("auto-address payload must be 14 bytes")
    device_type, mode = payload[:2]
    if device_type != 1:
        raise ValueError("auto-address payload is not a CFS device")
    if mode not in (MODE_APP, MODE_LOADER):
        raise ValueError("auto-address payload has an unknown mode")
    uniid = payload[2:]
    if not any(uniid):
        raise ValueError("auto-address payload has a zero UniID")
    return {
        "device_type": device_type,
        "mode": mode,
        "mode_name": "loader" if mode == MODE_LOADER else "application",
        "uniid_hex": uniid.hex(),
    }


def inspect_cfs_loader_probe(address: int = 1) -> dict[str, Any]:
    """Describe two non-flash CFS loader workflows without touching serial hardware."""
    if not 1 <= address <= 4:
        raise ValueError("CFS assigned address must be 1..4")

    dummy_uid = bytes([0x11]) * 12
    enter = build_any_address_frame(
        ADDRESS_IAP_BROADCAST, CMD_ENTER_BOOTLOADER, header=0xFF
    )
    discover = build_any_address_frame(
        ADDRESS_BROADCAST, AUTO_DISCOVER,
        bytes((ADDRESS_BROADCAST, ADDRESS_BROADCAST)),
    )
    assign = build_any_address_frame(
        ADDRESS_BROADCAST, AUTO_ASSIGN,
        bytes((address,)) + dummy_uid,
    )
    query = build_any_address_frame(address, AUTO_QUERY)
    get_version = build_any_address_frame(
        address, CMD_STOCK_FIRMWARE, bytes((SUB_GET_VERSION,))
    )
    get_sector = build_any_address_frame(
        address, CMD_STOCK_FIRMWARE, bytes((SUB_GET_SECTOR_SIZE,))
    )
    updater_start_app = build_any_address_frame(
        address, CMD_STOCK_FIRMWARE, bytes((SUB_START_APP,))
    )
    jacob_loader_to_app = build_any_address_frame(
        ADDRESS_GENERAL_BROADCAST, LOADER_TO_APP, b"\x01"
    )

    return {
        "schema": 1,
        "mode": "offline-loader-probe-plan",
        "assigned_address": address,
        "protocol_evidence": {
            "auto_mode_field": {
                "device_type": 1,
                "application": MODE_APP,
                "loader": MODE_LOADER,
            },
            "application_link_base": "0x08010000",
            "lower_region_bytes": 0x10000,
            "stock_ota_power_cycles_before_cfs_update": True,
            "jacob_loader_recovery_present": True,
            "community_active_loader_entry_frame": enter.hex(),
        },
        "paths": {
            "loader_detected_during_normal_enumeration": [
                {
                    "stage": "query_or_discover",
                    "commands": ["A2", "A1"],
                    "purpose": "observe mode=0 application or mode=1 loader",
                },
                {
                    "stage": "assign_if_unaddressed",
                    "command": "A0",
                    "state_changing": True,
                },
                {
                    "stage": "loader_to_app",
                    "command": "0B/01",
                    "frame_hex": jacob_loader_to_app.hex(),
                    "state_changing": True,
                },
                {
                    "stage": "verify_application",
                    "command": "A2",
                    "expected_mode": MODE_APP,
                },
            ],
            "bootloader_identity_probe": [
                {
                    "stage": "enter_loader",
                    "command": "special 0x56 broadcast",
                    "frame_hex": enter.hex(),
                    "provenance": "independent community reconstruction",
                    "state_changing": True,
                },
                {
                    "stage": "discover_loader",
                    "command": "A1",
                    "frame_hex": discover.hex(),
                },
                {
                    "stage": "assign_address",
                    "command": "A0",
                    "frame_template_hex": assign.hex(),
                    "note": "template uses dummy UniID 11*12; a live plan must insert the discovered UniID",
                    "state_changing": True,
                },
                {
                    "stage": "read_boot_identity",
                    "command": "F0/00",
                    "frame_hex": get_version.hex(),
                },
                {
                    "stage": "read_sector_token",
                    "command": "F0/03",
                    "frame_hex": get_sector.hex(),
                },
                {
                    "stage": "start_application",
                    "command": "F0/02",
                    "frame_hex": updater_start_app.hex(),
                    "state_changing": True,
                },
                {
                    "stage": "verify_application",
                    "command": "A2",
                    "frame_hex": query.hex(),
                    "expected_mode": MODE_APP,
                },
            ],
        },
        "safety": {
            "serial_io_performed": False,
            "flash_write_present": False,
            "erase_command_present": False,
            "update_request_present": False,
            "application_data_present": False,
            "state_changing": True,
            "why_state_changing": [
                "loader entry changes execution mode",
                "A0 changes the temporary RS-485 address",
                "start-app changes execution mode",
            ],
            "live_execution_enabled": False,
            "flash_allowed": False,
        },
    }

# ---------------------------------------------------------------------------
# Guarded live probe implementation
# ---------------------------------------------------------------------------

LOADER_SETTLE_SECONDS = 1.0
APP_SETTLE_SECONDS = 2.0


def _decode_wire_request(frame: bytes) -> tuple[int, int, int, bytes]:
    frame = bytes(frame)
    if len(frame) < 6 or frame[0] != FRAME_HEAD:
        raise ValueError("invalid RS-485 request envelope")
    if len(frame) != frame[2] + 3:
        raise ValueError("request length byte does not match frame length")
    if frame[-1] != crc8(frame[2:-1]):
        raise ValueError("request CRC is invalid")
    return frame[1], frame[3], frame[4], frame[5:-1]


def guard_cfs_loader_probe_frame(frame: bytes) -> None:
    """Hard allowlist for the non-flash loader probe.

    Any future caller using this guard is physically prevented from emitting
    erase (F0/06), update-request (F0/01), application length/data, or any
    unrelated CFS command through this probe path.
    """
    address, header, command, payload = _decode_wire_request(frame)

    allowed = False
    if (address, header, command, payload) == (
        ADDRESS_IAP_BROADCAST, 0xFF, CMD_ENTER_BOOTLOADER, b""
    ):
        allowed = True
    elif (address, header, command, payload) == (
        ADDRESS_BROADCAST, 0x00, AUTO_DISCOVER,
        bytes((ADDRESS_BROADCAST, ADDRESS_BROADCAST)),
    ):
        allowed = True
    elif address == ADDRESS_BROADCAST and header == 0x00 and command == AUTO_ASSIGN:
        allowed = (
            len(payload) == 13
            and 1 <= payload[0] <= 4
            and any(payload[1:])
        )
    elif 1 <= address <= 4 and header == 0x00 and command == AUTO_QUERY and not payload:
        allowed = True
    elif 1 <= address <= 4 and header == 0x00 and command == CMD_STOCK_FIRMWARE:
        allowed = payload in (
            bytes((SUB_GET_VERSION,)),
            bytes((SUB_GET_SECTOR_SIZE,)),
            bytes((SUB_START_APP,)),
        )
    elif (address, header, command, payload) == (
        ADDRESS_GENERAL_BROADCAST, 0x00, LOADER_TO_APP, b"\x01"
    ):
        allowed = True

    if not allowed:
        raise ValueError(
            "frame is outside the non-flash CFS loader-probe allowlist"
        )


def _decode_probe_reply(frame: bytes, expected_address: int, expected_command: int) -> dict[str, Any]:
    from .rs485 import decode_response

    return decode_response(frame, expected_address, expected_command)


def _decode_auto_probe_reply(
    frame: bytes,
    expected_address: int,
    expected_command: int,
    expected_uniid: bytes | None = None,
) -> dict[str, Any]:
    reply = _decode_probe_reply(frame, expected_address, expected_command)
    if reply["status"] != 0:
        raise RuntimeError(
            f"auto-address command 0x{expected_command:02x} returned "
            f"status 0x{reply['status']:02x}"
        )
    decoded = parse_auto_mode_payload(reply["payload"])
    if expected_uniid is not None and bytes.fromhex(decoded["uniid_hex"]) != bytes(expected_uniid):
        raise RuntimeError("auto-address response returned a different CFS identity")
    return decoded


def _decode_f0_status_reply(frame: bytes, address: int) -> dict[str, Any]:
    reply = _decode_probe_reply(frame, address, CMD_STOCK_FIRMWARE)
    if reply["status"] != 0:
        raise RuntimeError(
            f"F0 request returned outer status 0x{reply['status']:02x}"
        )
    return reply


class _SerialLoaderProbeIO:
    """Minimal serial transport used only by the guarded loader probe."""

    def __init__(self, port: str, baud: int, timeout: float):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.device = None

    def __enter__(self):
        from .rs485 import port_owners

        owners = port_owners(self.port)
        if owners:
            detail = ", ".join(
                f"pid {item['pid']} {item['command']}" for item in owners
            )
            raise RuntimeError(f"serial port is already in use: {detail}")
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required for live probing") from exc

        self.device = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=self.timeout,
            write_timeout=self.timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self.device.reset_input_buffer()
        self.device.reset_output_buffer()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.device is not None:
            self.device.close()
            self.device = None

    def _write(self, frame: bytes) -> None:
        guard_cfs_loader_probe_frame(frame)
        assert self.device is not None
        self.device.reset_input_buffer()
        self.device.write(frame)
        self.device.flush()

    def send(self, frame: bytes) -> None:
        self._write(frame)

    def exchange(self, frame: bytes, timeout: float | None = None) -> bytes:
        from .rs485 import _read_frame

        self._write(frame)
        assert self.device is not None
        old_timeout = self.device.timeout
        if timeout is not None:
            self.device.timeout = timeout
        try:
            return _read_frame(self.device)
        finally:
            self.device.timeout = old_timeout


def _query_auto(io, address: int, command: int, payload: bytes = b"", timeout: float = 1.0):
    frame = build_any_address_frame(address, command, payload)
    return io.exchange(frame, timeout=timeout)


def _best_effort_restore_application(
    io,
    *,
    assigned_address: int,
    uniid: bytes | None,
    sleep,
    app_settle: float,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    verified = False

    # First prefer the stock updater's address-specific start-app command when
    # we know the temporary loader address.
    try:
        frame = build_any_address_frame(
            assigned_address, CMD_STOCK_FIRMWARE, bytes((SUB_START_APP,))
        )
        response = io.exchange(frame, timeout=1.0)
        reply = _decode_f0_status_reply(response, assigned_address)
        ack = reply["payload"][:1] == b"\x75"
        attempts.append({"method": "F0/02", "ack": ack})
    except Exception as exc:
        attempts.append({"method": "F0/02", "error": str(exc)})

    sleep(app_settle)

    # Re-assign the application address after loader startup when the identity
    # is known. Jacob's discovery path performs the same second A0 assignment.
    if uniid is not None:
        try:
            assign = build_any_address_frame(
                ADDRESS_BROADCAST,
                AUTO_ASSIGN,
                bytes((assigned_address,)) + bytes(uniid),
            )
            response = io.exchange(assign, timeout=1.5)
            _decode_auto_probe_reply(
                response, assigned_address, AUTO_ASSIGN, expected_uniid=uniid
            )
            attempts.append({"method": "A0-after-start", "ok": True})
        except Exception as exc:
            attempts.append({"method": "A0-after-start", "error": str(exc)})

    try:
        response = _query_auto(io, assigned_address, AUTO_QUERY, timeout=0.5)
        decoded = _decode_auto_probe_reply(
            response, assigned_address, AUTO_QUERY,
            expected_uniid=uniid,
        )
        verified = decoded["mode"] == MODE_APP
        attempts.append(
            {
                "method": "A2-verify",
                "mode": decoded["mode_name"],
                "ok": verified,
            }
        )
    except Exception as exc:
        attempts.append({"method": "A2-verify", "error": str(exc)})

    if verified:
        return {"verified": True, "attempts": attempts}

    # Last-resort Jacob-compatible general loader->app command. It is still
    # inside the hard allowlist and carries no erase/write semantics.
    try:
        fallback = build_any_address_frame(
            ADDRESS_GENERAL_BROADCAST, LOADER_TO_APP, b"\x01"
        )
        io.send(fallback)
        attempts.append({"method": "0B/01-fallback", "sent": True})
        sleep(app_settle)

        if uniid is not None:
            assign = build_any_address_frame(
                ADDRESS_BROADCAST,
                AUTO_ASSIGN,
                bytes((assigned_address,)) + bytes(uniid),
            )
            response = io.exchange(assign, timeout=1.5)
            _decode_auto_probe_reply(
                response, assigned_address, AUTO_ASSIGN, expected_uniid=uniid
            )

        response = _query_auto(io, assigned_address, AUTO_QUERY, timeout=0.5)
        decoded = _decode_auto_probe_reply(
            response, assigned_address, AUTO_QUERY,
            expected_uniid=uniid,
        )
        verified = decoded["mode"] == MODE_APP
        attempts.append(
            {
                "method": "A2-verify-after-fallback",
                "mode": decoded["mode_name"],
                "ok": verified,
            }
        )
    except Exception as exc:
        attempts.append({"method": "fallback-verify", "error": str(exc)})

    return {"verified": verified, "attempts": attempts}




class CfsLoaderProbeError(RuntimeError):
    def __init__(self, message: str, result: dict[str, Any]):
        super().__init__(message)
        self.result = result

def run_cfs_loader_probe_session(
    io,
    *,
    assigned_address: int = 1,
    sleep=None,
    loader_settle: float = LOADER_SETTLE_SECONDS,
    app_settle: float = APP_SETTLE_SECONDS,
) -> dict[str, Any]:
    """Run the non-flash loader identity probe against an injected transport.

    The injected transport is used by unit tests and by the live serial wrapper.
    The command allowlist is enforced by the live transport before every write.
    """
    if not 1 <= assigned_address <= 4:
        raise ValueError("CFS assigned address must be 1..4")
    if sleep is None:
        import time
        sleep = time.sleep

    entered_loader = False
    uniid: bytes | None = None
    restored: dict[str, Any] = {"verified": False, "attempts": []}
    result: dict[str, Any] = {
        "mode": "live-non-flash-state-changing-probe",
        "assigned_address": assigned_address,
        "entered_loader": False,
        "loader_identity": None,
        "sector_token": None,
        "sector_chunk_size": None,
        "application_restored": False,
        "restore_attempts": [],
        "flash_write_performed": False,
        "erase_performed": False,
        "update_request_performed": False,
        "application_data_sent": False,
        "flash_allowed": False,
    }

    probe_error: Exception | None = None
    try:
        enter = build_any_address_frame(
            ADDRESS_IAP_BROADCAST, CMD_ENTER_BOOTLOADER, header=0xFF
        )
        io.send(enter)
        entered_loader = True
        result["entered_loader"] = True
        sleep(loader_settle)

        discover = _query_auto(
            io,
            ADDRESS_BROADCAST,
            AUTO_DISCOVER,
            bytes((ADDRESS_BROADCAST, ADDRESS_BROADCAST)),
            timeout=1.2,
        )
        discovered = _decode_auto_probe_reply(
            discover, ADDRESS_BROADCAST, AUTO_DISCOVER
        )
        if discovered["mode"] != MODE_LOADER:
            raise RuntimeError("CFS discovery did not report loader mode")
        uniid = bytes.fromhex(discovered["uniid_hex"])
        result["loader_discovery"] = {
            "mode": discovered["mode_name"],
            "uniid_present": True,
        }

        assign_frame = build_any_address_frame(
            ADDRESS_BROADCAST,
            AUTO_ASSIGN,
            bytes((assigned_address,)) + uniid,
        )
        assigned_frame = io.exchange(assign_frame, timeout=1.5)
        assigned = _decode_auto_probe_reply(
            assigned_frame,
            assigned_address,
            AUTO_ASSIGN,
            expected_uniid=uniid,
        )
        if assigned["mode"] != MODE_LOADER:
            raise RuntimeError("assigned CFS did not remain in loader mode")

        version_frame = build_any_address_frame(
            assigned_address,
            CMD_STOCK_FIRMWARE,
            bytes((SUB_GET_VERSION,)),
        )
        version_response = io.exchange(version_frame, timeout=1.0)
        version_reply = _decode_f0_status_reply(version_response, assigned_address)
        from .rs485 import parse_stock_version_payload
        identity = parse_stock_version_payload(version_reply["payload"])
        result["loader_identity"] = identity

        sector_frame = build_any_address_frame(
            assigned_address,
            CMD_STOCK_FIRMWARE,
            bytes((SUB_GET_SECTOR_SIZE,)),
        )
        sector_response = io.exchange(sector_frame, timeout=1.0)
        sector_reply = _decode_f0_status_reply(sector_response, assigned_address)
        if len(sector_reply["payload"]) != 1:
            raise RuntimeError("F0/03 sector response did not contain one byte")
        sector = sector_reply["payload"][0]
        result["sector_token"] = sector
        from .rs485_update import stock_data_chunk_size
        result["sector_chunk_size"] = stock_data_chunk_size(sector)

    except Exception as exc:
        probe_error = exc
    finally:
        if entered_loader:
            restored = _best_effort_restore_application(
                io,
                assigned_address=assigned_address,
                uniid=uniid,
                sleep=sleep,
                app_settle=app_settle,
            )
            result["application_restored"] = restored["verified"]
            result["restore_attempts"] = restored["attempts"]

    result["probe_ok"] = probe_error is None
    if probe_error is not None:
        result["probe_error"] = str(probe_error)
        restore_text = (
            "application restore verified"
            if result["application_restored"]
            else "application restore NOT verified"
        )
        raise CfsLoaderProbeError(
            f"loader probe failed: {probe_error}; {restore_text}",
            result,
        ) from probe_error
    if not result["application_restored"]:
        raise CfsLoaderProbeError(
            "loader probe completed but application-mode restore could not be verified",
            result,
        )
    return result


def probe_cfs_loader_live(
    port: str,
    *,
    assigned_address: int = 1,
    baud: int = 230400,
    timeout: float = 1.0,
    sleep=None,
) -> dict[str, Any]:
    """Live wrapper for the guarded non-flash CFS loader probe."""
    with _SerialLoaderProbeIO(port, baud, timeout) as io:
        result = run_cfs_loader_probe_session(
            io,
            assigned_address=assigned_address,
            sleep=sleep,
        )
    result.update(
        {
            "port": port,
            "baud": baud,
            "live_execution": True,
            "state_changing": True,
        }
    )
    return result