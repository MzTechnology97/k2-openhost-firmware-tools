# Stock RS-485 update protocol recovery

This document records static recovery of the Creality `mcu_util_485` update path from the K2 Pro host releases `1.1.0.94` and `1.1.6.7.2`.

No update command described here was sent to the development printer.

## Recovered state order

Both updater generations use RS-485 command `0xF0` for the updater-stage protocol. Binary strings provide the stock state names and decompilation correlates them with the transmitted payloads:

| State | Recovered request |
| --- | --- |
| `get_version` | `F0 / 00` |
| `erase_flash` | `F0 / 03` |
| `update_request` | `F0 / 06` |
| stream begin | `F0 / 01` |
| `app_len` | 32-bit little-endian firmware size |
| `app_data` | firmware bytes, at most 255 per read |
| `update_end` | `F0 / 02` |
| `start_app` / `app_run` | receive-side states are visible, but a distinct transmitted start-app subcommand has not yet been proven |

The stock sender retries the relevant `F0` operations up to three times with a 500 ms response timeout.

## Firmware chunking

The stock updater uses a 255-byte buffer. Its first file read depends on `firmware_size % 4`:

| remainder | first read |
| ---: | ---: |
| 0 | 255 |
| 1 | 252 |
| 2 | 248 |
| 3 | 244 |

Subsequent reads request 255 bytes and the final read naturally ends at EOF.

For the real K2 Pro `1.1.6.7.2` CFS image `cfs0_050_G30-cfs0_000_150.bin`:

- size: 175104 bytes;
- SHA-256: `bde552ef5056037989457e294f88cfa7590b4c9251cda5e40adf0a4fae46c5a3`;
- size remainder: 0;
- transfer reads: 687;
- first read: 255 bytes;
- final read: 174 bytes.

## Old vs. new updater

The core `F0` update sequence is structurally unchanged between the two analysed updater generations.

The newer updater extends some device handling paths from device type `1` to `1 || 10`, including firmware selection/update handling. This is an updater capability change around the shared state machine, not evidence of a different CFS flash wire protocol.

## Offline inspector

`k2fw inspect-update firmware.bin` produces a JSON description of the recovered sequence, image identity, chunk schedule and unresolved safety gates.

It performs no serial I/O. The implementation deliberately contains no serial writer and always reports:

```text
serial_io_performed: false
write_enabled: false
flash_allowed: false
```

## Remaining recovery gates

Before writable support can be considered, Phase 3 still requires:

- exact ACK/status and receive-state semantics for each update stage;
- proof of the transition from `update_end` to `start_app/app_run`;
- interrupted-transfer recovery and updater re-entry behavior;
- exact CFS hardware provenance (G30 vs G32) or an equally strong operator-provided provenance rule.

Until those points are proven, the recovered state machine remains inspection/test infrastructure only.