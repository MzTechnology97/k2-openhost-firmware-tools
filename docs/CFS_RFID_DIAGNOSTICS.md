# Generic CFS RFID diagnostics

Status: **static implementation complete; not hardware-flashed or hardware-validated yet**.

This work targets the exact stock `cfs0_000_113` application whose SHA-256 is:

```text
386a1106391a332e6a97803c5ce00b87b6d3ddc4c3d61f6fe07fb19fd3125b76
```

The analysed G30 and G32 files are byte-identical.

## Stock firmware findings

Static analysis recovered an MFRC522-compatible ISO14443A/MIFARE path already present in the CFS application:

- request/wakeup command `0x52`;
- anticollision `0x93 0x20`;
- select `0x93 0x70`;
- Key A authentication `0x60`;
- raw 16-byte block read `0x30`;
- stock write primitive `0xA0`.

The stock RT-Thread image also contains an exported `rfid` shell command with `init/read/write/show` subcommands. Its normal read path feeds Creality-specific parsers and does not expose a generic raw block through the application RS-485 protocol.

The patch intentionally never references the stock RFID write routine.

## Read-only extension

The patch reserves runtime application command `0x57`, which is unhandled by the stock 1.1.3 dispatcher.

Application framing is the normal CFS runtime framing recovered from stock `auto_addr_wrapper.py`:

```text
F7 | address | length | status | function | data... | CRC8
length = len(data) + 3
request status = 0
CRC8 polynomial = 0x07 over length,status,function,data
```

Operations:

| op | request data after command | success response |
|---:|---|---|
| 0 | `00 reader` | 8 bytes: ATQA[2] + UID[4] + BCC + SAK |
| 1 | `01 reader block keyA[6]` | 16 raw bytes |
| 2 | `02 reader block` | 16 raw bytes |

Status codes:

| status | meaning |
|---:|---|
| 0 | OK |
| 1 | bad request |
| 2 | no card / select failed |
| 3 | authentication failed |
| 4 | read failed |

The authenticated path accepts a caller-supplied six-byte Key A. No proprietary key is embedded or published.

The implementation mirrors the stock reader limits: reader indices 0..3, blocks 0..63 and the existing cascade-level-1 / four-byte UID path.

## Patch architecture

The real application base is `0x08010000`. The older Ghidra project was imported at a base 0x10000 too low, so all executable addresses were corrected before patch construction.

The stock dispatcher begins at `0x0801A2C4`. The final hook is deliberately placed after its common state-management prologue:

```text
hook runtime address: 0x0801A2E4
handler runtime:      0x080350AC
```

Only four bytes inside the original image are replaced by one `B.W` instruction. The handler is appended to the end of the stock image.

For every command other than `0x57`, the handler reproduces the overwritten `cmp/beq` semantics and returns into the original switch with the comparison flags preserved.

The handler calls only these recovered stock helpers:

- reader hardware init;
- card request/anticollision/select;
- Key A authentication;
- raw 16-byte read;
- stock reader cleanup;
- stock RS-485 response builder.

It does not call the recovered tag-write function.

The patched image is smaller than a later stock CFS image from the same family:

```text
1.1.3 stock:   151724 bytes
patched 1.1.3: 152038 bytes
later stock:   175104 bytes
```

This is useful flash-capacity evidence but does not replace hardware validation.

## Build and validation

The repository stores no Creality firmware binary. The user supplies the exact stock image locally.

Build dependencies:

```bash
python -m pip install keystone-engine capstone
```

Build:

```bash
python tools/cfs_rfid_diag/build_patch.py \
  --input /path/to/cfs0_050_G32-cfs0_000_113.bin \
  --output /tmp/cfs0_050_G32-cfs0_000_113-rfid-diag-ro.bin \
  --manifest /tmp/cfs-rfid-manifest.json \
  --disasm /tmp/cfs-rfid-handler.txt
```

The patcher refuses an input with the wrong SHA-256.

Validation:

```bash
python tools/cfs_rfid_diag/validate_patch.py \
  --input /path/to/stock.bin \
  --patched /tmp/cfs0_050_G32-cfs0_000_113-rfid-diag-ro.bin \
  --manifest /tmp/cfs-rfid-manifest.json \
  --report /tmp/cfs-rfid-validation.json
```

The validator proves that:

- only the four-byte hook changes inside the original image;
- the hook targets the appended handler;
- the stock dispatcher fallback targets are correct;
- all external handler calls belong to an explicit allowlist;
- the RFID write routine is not referenced;
- the output remains below the known larger stock image size.

## Host client

`tools/cfs_rfid_diag/rfid_diag_client.py` builds and parses command `0x57`.

Offline frame generation does not require pyserial:

```bash
python tools/cfs_rfid_diag/rfid_diag_client.py \
  --address 1 --reader 0 --print-frame detect
```

Live serial use requires `pyserial`. Raw RS-485 ownership must be exclusive; on K2-OpenHost it must be coordinated with Klipper/serial_485 rather than opening the same port concurrently.

## Validation state

Current status:

- stock reverse engineering: complete for the required read path;
- G30/G32 1.1.3 equivalence: byte-for-byte confirmed;
- patch build reproducibility: confirmed;
- static branch/call validation: passed;
- protocol unit tests: passed;
- tag write support: absent;
- tag emulation: absent;
- firmware flash: **not performed**;
- live RFID command test: **not performed**.

The first hardware test should be `detect` only. Raw unauthenticated read should follow only if detect is stable; authenticated read should be tested last with a known test key.