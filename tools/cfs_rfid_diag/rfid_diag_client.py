#!/usr/bin/env python3
import argparse
import json
import time


HEAD = 0xF7
COMMAND = 0x57
STATUS = {
    0: "ok",
    1: "bad_request",
    2: "no_card_or_select_failed",
    3: "authentication_failed",
    4: "read_failed",
}

def crc8(data):
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc

def build_frame(address, command, data=b""):
    data = bytes(data)
    if not 0 <= address <= 0xFF:
        raise ValueError("address must fit in one byte")
    if len(data) > 0xFC:
        raise ValueError("data too long")
    body = bytes((len(data) + 3, 0, command)) + data
    return bytes((HEAD, address)) + body + bytes((crc8(body),))

def parse_frame(frame):
    frame = bytes(frame)
    if len(frame) < 6 or frame[0] != HEAD:
        raise ValueError("invalid frame header/size")
    length = frame[2]
    if len(frame) != length + 3:
        raise ValueError("frame length mismatch")
    if crc8(frame[2:-1]) != frame[-1]:
        raise ValueError("CRC mismatch")
    return {
        "address": frame[1],
        "length": length,
        "status": frame[3],
        "command": frame[4],
        "data": frame[5:-1],
    }

def read_frame(ser, timeout):
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            buf.extend(ser.read(waiting))
        else:
            time.sleep(0.002)
        while True:
            try:
                start = buf.index(HEAD)
            except ValueError:
                buf.clear()
                break
            if start:
                del buf[:start]
            if len(buf) < 3:
                break
            total = buf[2] + 3
            if total < 6:
                del buf[0]
                continue
            if len(buf) < total:
                break
            candidate = bytes(buf[:total])
            del buf[:total]
            try:
                return parse_frame(candidate)
            except ValueError:
                continue
    raise TimeoutError("no valid CFS response")

def decode_detect(data):
    if len(data) != 8:
        raise ValueError("detect response must contain 8 bytes")
    atqa = data[0:2]
    uid_bcc = data[2:7]
    return {
        "atqa_hex": atqa.hex(),
        "uid_hex": uid_bcc[:4].hex(),
        "bcc_hex": f"{uid_bcc[4]:02x}",
        "bcc_valid": (uid_bcc[0] ^ uid_bcc[1] ^ uid_bcc[2] ^ uid_bcc[3]) == uid_bcc[4],
        "sak_hex": f"{data[7]:02x}",
        "raw_hex": data.hex(),
    }

def make_payload(args):
    if args.operation == "detect":
        return bytes((0, args.reader))
    if args.operation == "read-auth":
        key = bytes.fromhex(args.key)
        if len(key) != 6:
            raise ValueError("Key A must contain exactly 6 bytes / 12 hex digits")
        return bytes((1, args.reader, args.block)) + key
    if args.operation == "read-noauth":
        return bytes((2, args.reader, args.block))
    raise ValueError("unsupported operation")

def main():
    ap = argparse.ArgumentParser(description="Generic read-only CFS RFID diagnostic client")
    ap.add_argument("--port", help="serial port (for example /dev/ttyUSB2 or COM5)")
    ap.add_argument("--baud", type=int, default=230400)
    ap.add_argument("--address", type=lambda x: int(x, 0), default=1)
    ap.add_argument("--reader", type=int, choices=range(4), default=0)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--print-frame", action="store_true", help="build request only; do not open serial")
    sub = ap.add_subparsers(dest="operation", required=True)
    sub.add_parser("detect")
    p = sub.add_parser("read-auth")
    p.add_argument("block", type=lambda x: int(x, 0), choices=range(64))
    p.add_argument("key", help="6-byte Key A as 12 hex digits")
    p = sub.add_parser("read-noauth")
    p.add_argument("block", type=lambda x: int(x, 0), choices=range(64))
    args = ap.parse_args()

    payload = make_payload(args)
    request = build_frame(args.address, COMMAND, payload)
    if args.print_frame:
        print(json.dumps({"request_hex": request.hex()}, indent=2))
        return
    if not args.port:
        ap.error("--port is required unless --print-frame is used")

    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for live serial access: python -m pip install pyserial") from exc

    serial_kwargs = dict(port=args.port, baudrate=args.baud, timeout=0, write_timeout=1)
    try:
        import os
        if os.name == "posix":
            serial_kwargs["exclusive"] = True
    except Exception:
        pass

    with serial.Serial(**serial_kwargs) as ser:
        ser.reset_input_buffer()
        ser.write(request)
        ser.flush()
        response = read_frame(ser, args.timeout)

    if response["command"] != COMMAND:
        raise SystemExit(f"unexpected command in response: 0x{response['command']:02x}")
    status = response["status"]
    output = {
        "status": status,
        "status_name": STATUS.get(status, "unknown"),
        "address": response["address"],
        "data_hex": response["data"].hex(),
    }
    if status == 0 and args.operation == "detect":
        output["tag"] = decode_detect(response["data"])
    elif status == 0 and args.operation.startswith("read"):
        if len(response["data"]) != 16:
            raise SystemExit("successful read returned a non-16-byte payload")
        output["block"] = args.block
        output["raw_block_hex"] = response["data"].hex()
    print(json.dumps(output, indent=2))
    if status != 0:
        raise SystemExit(2)

if __name__ == "__main__":
    main()