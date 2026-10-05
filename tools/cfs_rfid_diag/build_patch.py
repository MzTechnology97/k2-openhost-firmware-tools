from pathlib import Path
import argparse
import hashlib
import json

from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB, KS_MODE_LITTLE_ENDIAN
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

EXPECTED_SHA256 = "386a1106391a332e6a97803c5ce00b87b6d3ddc4c3d61f6fe07fb19fd3125b76"
APP_BASE = 0x08010000
HOOK_OFFSET = 0x0000A2E4
HOOK_ADDR = APP_BASE + HOOK_OFFSET
RESUME_ADDR = APP_BASE + 0x0000A2E8
COMMAND_0E_ADDR = APP_BASE + 0x0000A3E0
EXPECTED_HOOK = bytes.fromhex("0e287bd0")

# Runtime addresses. The historical Ghidra project used a base 0x10000 too low.
RFID_HW_INIT = APP_BASE + 0x00007828
RFID_MODE = APP_BASE + 0x00007DA0
CARD_CONNECT = APP_BASE + 0x0000802C
CARD_AUTH = APP_BASE + 0x00008066
CARD_READ = APP_BASE + 0x0000831A
SEND_RESPONSE = APP_BASE + 0x00009BD6

CARD_TABLE = 0x20002E0C
ORIGINAL_DISPATCH_LITERAL = 0x20002E98
COMMAND = 0x57

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def align4(value: int) -> int:
    return (value + 3) & ~3

def assemble(source: str, address: int) -> bytes:
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB | KS_MODE_LITTLE_ENDIAN)
    encoding, _ = ks.asm(source, addr=address, as_bytes=True)
    return bytes(encoding)

def main():
    ap = argparse.ArgumentParser(description="Build generic read-only RFID diagnostics patch for exact CFS 1.1.3 image")
    ap.add_argument("--input", required=True, help="stock cfs0_050_G30/G32-cfs0_000_113.bin")
    ap.add_argument("--output", help="patched output .bin")
    ap.add_argument("--manifest", help="patch manifest JSON")
    ap.add_argument("--disasm", help="handler disassembly text")
    args = ap.parse_args()

    source_path = Path(args.input).resolve()
    outdir = source_path.parent if args.output is None else Path(args.output).resolve().parent
    output = Path(args.output).resolve() if args.output else source_path.with_name(source_path.stem + "-rfid-diag-ro.bin")
    manifest_path = Path(args.manifest).resolve() if args.manifest else output.with_suffix(".manifest.json")
    disasm_path = Path(args.disasm).resolve() if args.disasm else output.with_suffix(".handler.txt")
    output.parent.mkdir(parents=True, exist_ok=True)

    original = source_path.read_bytes()
    if sha256(original) != EXPECTED_SHA256:
        raise SystemExit("Input SHA-256 mismatch; refusing to patch an unknown CFS image.")
    if original[HOOK_OFFSET:HOOK_OFFSET + 4] != EXPECTED_HOOK:
        raise SystemExit(
            "Dispatcher prologue mismatch at hook: "
            + original[HOOK_OFFSET:HOOK_OFFSET + 4].hex()
        )

    inject_offset = align4(len(original))
    inject_addr = APP_BASE + inject_offset

    asm = f"""
        /*
         * Hook is after the stock dispatcher prologue and state bookkeeping.
         * r0 already contains the command code and r4 points to the parsed packet.
         */
        cmp r0, #{COMMAND}
        beq diag_entry

        /* Reproduce overwritten stock cmp/beq, preserving flags for the BGT at RESUME_ADDR. */
        cmp r0, #0x0e
        bne stock_resume
        b.w 0x{COMMAND_0E_ADDR:08x}
    stock_resume:
        b.w 0x{RESUME_ADDR:08x}

    diag_entry:
        /*
         * The stock function already pushed {{r3-r7,lr}}.
         * Reserve exactly 16 bytes for one raw block while keeping 8-byte stack alignment.
         */
        sub sp, #16
        ldrb r5, [r4, #4]
        cmp r5, #0
        beq op_detect
        cmp r5, #1
        beq op_read_auth
        cmp r5, #2
        beq op_read_noauth
        b status_bad_request

    op_detect:
        ldrb r0, [r4, #1]
        cmp r0, #5
        bne status_bad_request
        ldrb r6, [r4, #5]
        cmp r6, #4
        bhs status_bad_request

        mov r0, r6
        bl 0x{RFID_HW_INIT:08x}
        mov r0, r6
        movs r1, #0
        bl 0x{CARD_CONNECT:08x}
        cmp r0, #0
        bne status_no_card

        mov r0, r6
        movs r1, #0
        bl 0x{RFID_MODE:08x}
        movw r2, #{CARD_TABLE & 0xffff}
        movt r2, #{CARD_TABLE >> 16}
        add.w r2, r2, r6, lsl #4
        movs r0, #{COMMAND}
        movs r1, #0
        movs r3, #8
        bl 0x{SEND_RESPONSE:08x}
        b diag_done

    op_read_auth:
        ldrb r0, [r4, #1]
        cmp r0, #12
        bne status_bad_request
        ldrb r6, [r4, #5]
        cmp r6, #4
        bhs status_bad_request
        ldrb r7, [r4, #6]
        cmp r7, #0x40
        bhs status_bad_request

        mov r0, r6
        bl 0x{RFID_HW_INIT:08x}
        mov r0, r6
        movs r1, #0
        bl 0x{CARD_CONNECT:08x}
        cmp r0, #0
        bne status_no_card

        movw r3, #{CARD_TABLE & 0xffff}
        movt r3, #{CARD_TABLE >> 16}
        add.w r3, r3, r6, lsl #4
        adds r3, #2
        bic r1, r7, #3
        adds r2, r4, #7
        mov r0, r6
        bl 0x{CARD_AUTH:08x}
        cmp r0, #0
        bne auth_cleanup_failed

        mov r0, r6
        mov r1, r7
        mov r2, sp
        bl 0x{CARD_READ:08x}
        mov r7, r0
        mov r0, r6
        movs r1, #0
        bl 0x{RFID_MODE:08x}
        cmp r7, #0
        bne status_read_failed

        movs r0, #{COMMAND}
        movs r1, #0
        mov r2, sp
        movs r3, #16
        bl 0x{SEND_RESPONSE:08x}
        b diag_done

    auth_cleanup_failed:
        mov r0, r6
        movs r1, #0
        bl 0x{RFID_MODE:08x}
        b status_auth_failed

    op_read_noauth:
        ldrb r0, [r4, #1]
        cmp r0, #6
        bne status_bad_request
        ldrb r6, [r4, #5]
        cmp r6, #4
        bhs status_bad_request
        ldrb r7, [r4, #6]
        cmp r7, #0x40
        bhs status_bad_request

        mov r0, r6
        bl 0x{RFID_HW_INIT:08x}
        mov r0, r6
        movs r1, #0
        bl 0x{CARD_CONNECT:08x}
        cmp r0, #0
        bne status_no_card

        mov r0, r6
        mov r1, r7
        mov r2, sp
        bl 0x{CARD_READ:08x}
        mov r7, r0
        mov r0, r6
        movs r1, #0
        bl 0x{RFID_MODE:08x}
        cmp r7, #0
        bne status_read_failed

        movs r0, #{COMMAND}
        movs r1, #0
        mov r2, sp
        movs r3, #16
        bl 0x{SEND_RESPONSE:08x}
        b diag_done

    status_bad_request:
        movs r1, #1
        b send_empty
    status_no_card:
        movs r1, #2
        b send_empty
    status_auth_failed:
        movs r1, #3
        b send_empty
    status_read_failed:
        movs r1, #4

    send_empty:
        movs r0, #{COMMAND}
        movs r2, #0
        movs r3, #0
        bl 0x{SEND_RESPONSE:08x}

    diag_done:
        movs r0, #0
        add sp, #16
        pop {{r3, r4, r5, r6, r7, pc}}
    """

    handler = assemble(asm, inject_addr)
    hook = assemble(f"b.w 0x{inject_addr:08x}", HOOK_ADDR)
    if len(hook) != 4:
        raise SystemExit(f"Unexpected hook size: {len(hook)}")

    patched = bytearray(original)
    if len(patched) < inject_offset:
        patched.extend(b"\x00" * (inject_offset - len(patched)))
    patched[HOOK_OFFSET:HOOK_OFFSET + 4] = hook
    patched.extend(handler)

    # 1.1.5/1.5.0 CFS images from the same product family are 0x2ac00 bytes,
    # so this append remains well below a firmware size already accepted by the loader.
    known_larger_image_size = 0x2AC00
    if len(patched) >= known_larger_image_size:
        raise SystemExit("Patched image unexpectedly reaches/exceeds known later-image size.")

    output.write_bytes(patched)

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    lines = []
    for insn in md.disasm(handler, inject_addr):
        lines.append(
            f"{insn.address:08x}: {insn.bytes.hex():<12} "
            f"{insn.mnemonic:<8} {insn.op_str}"
        )
    disasm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "schema": 1,
        "purpose": "generic read-only RFID diagnostics",
        "source": {
            "name": source_path.name,
            "size": len(original),
            "sha256": sha256(original),
        },
        "output": {
            "name": output.name,
            "size": len(patched),
            "sha256": sha256(patched),
        },
        "layout": {
            "application_base": f"0x{APP_BASE:08x}",
            "hook_offset": f"0x{HOOK_OFFSET:x}",
            "hook_runtime_address": f"0x{HOOK_ADDR:08x}",
            "original_hook_bytes": EXPECTED_HOOK.hex(),
            "replacement_hook_bytes": hook.hex(),
            "handler_offset": f"0x{inject_offset:x}",
            "handler_runtime_address": f"0x{inject_addr:08x}",
            "handler_size": len(handler),
            "known_larger_stock_image_size": known_larger_image_size,
        },
        "protocol": {
            "command": f"0x{COMMAND:02x}",
            "operations": {
                "0": {
                    "name": "detect",
                    "request_payload": ["op=0", "reader"],
                    "response_data": "8 bytes: ATQA[2] + UID/BCC[5] + SAK[1]",
                },
                "1": {
                    "name": "read-auth",
                    "request_payload": ["op=1", "reader", "block", "keyA[6]"],
                    "response_data": "16 raw bytes",
                },
                "2": {
                    "name": "read-noauth",
                    "request_payload": ["op=2", "reader", "block"],
                    "response_data": "16 raw bytes",
                },
            },
            "status": {
                "0": "ok",
                "1": "bad_request",
                "2": "no_card_or_select_failed",
                "3": "authentication_failed",
                "4": "read_failed",
            },
        },
        "safety": {
            "tag_write_supported": False,
            "tag_emulation_supported": False,
            "proprietary_key_embedded": False,
            "caller_provided_key_only": True,
            "stock_command_behavior_preserved_for_non_0x57": True,
            "flash_performed": False,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()