# CFS loader probe model

This note separates three facts that are now independently visible in the K2/CFS stack:

1. the `cfs0` application is linked at `0x08010000`, leaving 64 KiB below it;
2. the CFS identity protocol explicitly reports `mode=0` for application and `mode=1` for loader;
3. both community and stock-derived workflows provide an explicit loader-to-application transition.

No command described here has been sent by `k2fw` to the development CFS.

## Loader detection already present in the running K2-OpenHost stack

The installed Jacob-lineage `box_addr.py` queries CFS identities with A2 and discovers unaddressed boxes with A1. The common A0/A1/A2 response payload is:

```text
device_type | mode | 12-byte UniID
```

For CFS, `device_type=1`. The mode values are:

```text
0 = application
1 = loader
```

If a box is returned in loader mode, the address manager deliberately starts the application and verifies that a subsequent A2 reply reports application mode.

The Jacob-lineage recovery command is a general broadcast command `0x0B` with payload `01`. The exact rendered frame is:

```text
f7 ff 04 00 0b 01 c8
```

This is direct protocol evidence that "powered but still in loader" is a supported observable CFS state.

## Updater-loader identity probe

An independent community reconstruction uses this non-flash sequence:

```text
enter loader
A1 discover
A0 assign temporary address
F0/00 read boot/hardware + application identity
F0/03 read sector token
F0/02 start application
```

Its active loader-entry broadcast is:

```text
f7 eb 03 ff 56 cf
```

K2-OpenHost records that frame as independent corroborating evidence only. The compared stock `mcu_util_485` decompilation establishes the later A1/A0/F0 loader state machine, but this exact `0x56` entry frame has not yet been located as a literal in those two host binaries.

## Why this is not called read-only

The identity and sector reads themselves do not erase/program application flash, but the full workflow changes CFS state:

- loader entry changes execution mode;
- A0 changes the temporary RS-485 address;
- F0/02 or 0B/01 changes execution mode back to the application.

Therefore the future live operation is classified as **non-flash, state-changing**, not read-only.

It must remain separate from normal `k2fw status`.

## Cold-boot interpretation

Stock OTA orchestration stops Klipper, power-cycles the stock MCU power rail, and then immediately runs the CFS updater. Combined with the explicit loader-mode field and the loader-to-app recovery path, this strongly supports the model that the updater expects a CFS to be reachable in loader state around reset/startup.

It still does not prove that every ordinary CFS power-on always pauses in loader for a fixed interval, nor that a partially erased application is guaranteed to leave the loader reachable indefinitely. A live capture around a controlled CFS-only power transition is still required before that is promoted to a recovery guarantee.

## Offline inspection command

```bash
python -m k2fw inspect-cfs-loader-probe
```

The command renders both the loader-detected recovery path and the bootloader identity/sector probe plan. It opens no serial port and permanently reports:

```text
serial_io_performed = false
flash_write_present = false
erase_command_present = false
update_request_present = false
live_execution_enabled = false
flash_allowed = false
```

The A0 template deliberately contains a dummy UniID and cannot be copied as a live assignment transaction without replacing it with the discovered identity.

## Guarded live implementation

The live implementation is now present as:

```bash
python -m k2fw probe-cfs-loader   --exclusive   --single-cfs   --ack-state-change   --printer-safe-confirmed
```

It remains intentionally difficult to invoke accidentally. All four flags are mandatory before the serial port is opened:

- `--exclusive`: the operator confirms Klipper and every other consumer released the RS-485 port;
- `--single-cfs`: exactly one CFS is connected, because loader entry is a broadcast operation;
- `--ack-state-change`: the operator acknowledges loader entry, temporary A0 addressing and application restore;
- `--printer-safe-confirmed`: the printer is idle and every heater target is zero.

The serial transport performs a second independent exclusivity check against `/proc/*/fd` before opening the port.

### Hard command allowlist

Every live TX frame passes through a dedicated allowlist. The live probe accepts only:

```text
special 0x56 loader entry
A1 discovery
A0 address assignment
A2 identity/mode query
F0/00 boot identity
F0/03 sector token
F0/02 start application
0B/01 Jacob-compatible loader -> app fallback
```

It rejects `F0/06` erase, `F0/01` update request, application-length packets and arbitrary application-data frames before they reach the serial writer.

### Restore guarantee

Once loader entry has been emitted, application restore runs from a `finally` block even when identity or sector probing fails.

The primary restore path is:

```text
F0/02 -> wait -> A0 restore address -> A2 verify mode=application
```

If that cannot be verified, the code tries the Jacob-compatible fallback:

```text
0B/01 -> wait -> A0 restore address -> A2 verify mode=application
```

A live probe is not considered successful unless the final A2 verification reports `mode=0`.

The implementation is covered with simulated transport tests for successful probing, identity-query failure, failed F0/02 restore, fallback through 0B/01, invalid loader mode and destructive-command rejection.

At this stage the live command exists but has **not** been executed on the development K2 Pro.

## First live validation on the development K2 Pro

The guarded live probe was executed after the printer was confirmed standby, all heater targets were zero, exactly one CFS was online, and Klipper had released the RS-485 port.

Observed loader identity:

```text
hardware    cfs0_050_G32
application cfs0_000_113
sector      0xE0
chunk size  128 bytes
```

No erase, update-request or application-data transaction was emitted.

The restore path exposed an important hardware-specific detail. `F0/02` returned an ACK, but after the settle delay the subsequent A2 query still reported `mode=loader`. The Jacob-compatible `0B/01` fallback was then sent, after which A2 reported `mode=application`.

Therefore on this K2 Pro / CFS generation:

- an `F0/02` ACK is **not sufficient evidence** that the application has actually taken control;
- A2 mode verification is mandatory;
- `0B/01` is a proven recovery path from loader to application on the live hardware.

After the probe, the normal application `0x14` query again returned firmware 1.1.3. Klipper was restarted successfully and the printer returned to `ready/standby` with CFS `IDLE/OK`.

The device serial number is intentionally omitted from repository evidence.