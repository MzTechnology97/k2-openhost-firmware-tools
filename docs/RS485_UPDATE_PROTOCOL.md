# Stock RS-485 update protocol recovery

This document records static recovery of the Creality `mcu_util_485` update path from the K2 Pro host releases `1.1.0.94` and `1.1.6.7.2`.

No update command described here was sent to the development printer.

## RX dispatch table

The newer updater dispatch table is:

| Command | Handler |
| --- | --- |
| `0xA1` | discovery/device-info handler |
| `0xA0` | address-assignment handler |
| `0xA2` | device-info handler |
| `0xF0` | updater-state response handler |

The older updater has the same four command classes and an equivalent `0xF0` state handler.

## Stock updater states

The state-name table is embedded directly in the binary:

| State | Name |
| ---: | --- |
| 0 | `unknown` |
| 1 | `get_salve_info` |
| 2 | `set_salve_addr` |
| 3 | `get_version` |
| 4 | `get_sector_size` |
| 5 | `erase_flash` |
| 6 | `update_request` |
| 7 | `app_len` |
| 8 | `app_data` |
| 9 | `update_end` |
| 10 | `start_app` |
| 11 | `app_run` |
| 12 | `end` |
| 13 | `error` |
| 14 | `timeout` |

## Correct recovered F0 sequence

Both analysed updater generations use command `0xF0` with the following sequence:

| State | Transmission | Receive behavior |
| --- | --- | --- |
| `get_version` (3) | payload `00` | copies a 25-byte hardware-application identity |
| `get_sector_size` (4) | payload `03` | stores one returned sector token byte |
| `erase_flash` (5) | payload `06` | status byte is logged |
| `update_request` (6) | payload `01` | `ACK` advances to state 7 |
| `app_len` (7) | raw 32-bit little-endian firmware length | `ACK` advances to state 8 |
| `app_data` (8) | raw firmware chunk | `ACK` stays in state 8; `DONE` advances to state 9 |
| `update_end` (9) | no independent transmission | reached by the final `DONE` response during data transfer |
| `start_app` (10) | payload `02` | `ACK` advances to state 11 |
| `app_run` (11) | no transmission | successful running state |

This corrects an earlier intermediate interpretation that associated `03`, `06`, `01` and `02` with the following state names rather than the transmissions that enter them.

## Response codes

The stock response-name table is also embedded in the binary:

| Code | Meaning |
| ---: | --- |
| `0x1F` | `NACK` |
| `0x20` | `DONE` |
| `0x21` | `FAIL` |
| `0x75` | `ACK` |
| `0xFF` | `NONE` |

The important state transitions are therefore:

```text
update_request --ACK--> app_len
app_len        --ACK--> app_data
app_data       --ACK--> app_data
app_data       --DONE-> update_end
start_app      --ACK--> app_run
```

A `NACK` or `FAIL` does not create the successful transition.

## Retry behavior

The sender retries the relevant `F0` transaction up to three times when the transport helper times out waiting for a response. The receive thread posts the sender semaphore when an `F0` reply is received, including a protocol-level `NACK` or `FAIL`.

This means the three-attempt loop is principally a **transport timeout retry**, not a generic retry-on-NACK mechanism. The state transition remains the authoritative indication of protocol success.

## Sector token and data chunking

The `get_sector_size` response is stored as a signed byte. Forced decompilation makes the source explicit in both generations: the old handler at `0x12174` and the new handler at `0x11eac` copy `response[9]` into the per-device sector-token field; the sender later loads that same field with `LDRSB` before the data-read loop. Static ARM disassembly therefore shows the updater computing the file-read size from that returned byte, not from `firmware_size % 4`.

The recovered calculation is:

```text
signed_token = int8(sector_token)

if signed_token == 0:
    invalid sector size
elif signed_token > 0:
    recovered path reaches a zero-length read
else:
    chunk_size = uint8(signed_token * 0xFC)
```

The transfer buffer is 255 bytes, while an `F0` frame can carry at most 252 payload bytes because the stock length byte includes three protocol bytes in addition to the payload.

The exact sector token returned by the development CFS boot/update state has **not** been queried. Therefore the offline inspector does not claim a chunk count unless the operator supplies a previously captured token explicitly.

For example, token `0xC1` is signed `-63` and the recovered formula yields a 252-byte chunk size. This is a mathematical example of the recovered formula, not a claim that the CFS returns `0xC1`.

## Interrupted transfer behavior

The stock updater considers firmware-data transfer successful only if the F0 receive state reaches state 9, `update_end`, which occurs when an `app_data` response is `DONE`.

If data transfer exits without reaching state 9, the stock updater marks that device's update status as failed. The later loop that sends `start_app` explicitly skips devices with failed update status.

Therefore an interrupted or failed data transfer can leave a target without the normal stock `start_app` transaction. Whether the target can always be rediscovered and safely re-entered by launching the updater again remains unproven and is still a mandatory recovery gate.

## Old vs. new updater

The F0 receive-state transitions above are equivalent in the two analysed updater generations.

The newer updater additionally extends selected device handling paths from device type `1` to `1 || 10`. That change is outside the core F0 state machine.

## Offline inspector

`k2fw inspect-update firmware.bin` reports the recovered state machine without opening a serial device. It accepts CFS images only and can render the fixed `F0` control frames for an offline address (default 1); data frames are never generated.

If a sector token has been obtained independently, it can be supplied only for offline calculation:

```bash
python -m k2fw inspect-update firmware.bin --sector-token 0xc1
```


For address 1, fixed frames include:

```text
F0/00 get-version          f7 01 04 00 f0 00 4c
F0/03 get-sector-size      f7 01 04 00 f0 03 45
F0/06 erase-private-flash  f7 01 04 00 f0 06 5e
F0/01 update-request       f7 01 04 00 f0 01 4b
F0/02 start-app            f7 01 04 00 f0 02 42
```

For the real 175104-byte `cfs0_000_150` image, the little-endian length payload is `00 ac 02 00`, producing address-1 frame `f7 01 07 00 f0 00 ac 02 00 82`. These bytes are rendered only; no send path exists.

This still performs no serial I/O and always reports:

```text
serial_io_performed: false
write_enabled: false
send_enabled: false
flash_allowed: false
```

## Interrupted transfer and host re-entry

Static analysis of both stock updater generations shows no host-side resume offset or persistent transfer checkpoint. The firmware file is opened, its size is measured with an end seek, and the descriptor is explicitly returned to offset 0 before transfer.

Each individual control request or data chunk is retried up to three times. If an app-data transaction exhausts those retries before the receive state reaches `update_end`, the device is marked failed and the later `start_app` request is skipped for that device.

A fresh updater process therefore starts its host workflow from the beginning: discovery/address handling, version/sector query, erase/update setup and a new transfer from file offset 0. This describes the **host behavior only**. Static analysis does not prove that a CFS interrupted during erase/write will always remain reachable in a loader state, so device-side recovery after power loss or a killed update remains a hardware-validation gate.

## Remaining recovery gates

Before writable support can be considered:

- capture or independently determine the exact CFS sector token in updater state;
- prove updater re-entry and recovery after interruption;
- determine whether a failed/partially erased CFS remains discoverable through the stock A1/A0 path;
- obtain exact CFS hardware provenance (G30 vs G32), or require equally strong operator-provided provenance;
- validate all of the above on sacrificial/recoverable hardware before exposing any write command.

Until those points are proven, the recovered state machine remains inspection/test infrastructure only.