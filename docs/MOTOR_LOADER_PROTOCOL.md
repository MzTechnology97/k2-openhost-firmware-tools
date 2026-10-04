# Motor loader protocol recovery

This note records the stock K2 motor-loader path recovered from `mcu_util_485` and the analysed 071/081 motor images.

## Stock discovery and mode gate

The newer stock updater sends motor discovery to group address `0xFD` with payload `FD FD`:

```text
F7 FD 05 00 A1 FD FD CE
```

The common A0/A1/A2 identity response contains:

```text
device_type | mode | 12-byte UniID
```

For motors `device_type=2`. Stock `mcu_util_485` only selects a device for firmware update when `mode==1` (loader). A motor reporting `mode==0` (application) is not sent through the firmware path.

This proves that the stock updater expects the motor to be in loader state before the F0 update phase. No application-side loader-entry command has been recovered; however, a guarded live K2 Pro test now proves that a GPIO140 / MCU_PWR_EN hardware power-cycle exposes both RS-485 motors in `mode=1`.

## Temporary loader addresses

The stock updater expects two type-2 motors on this RS-485 enumeration path. Their temporary loader addresses begin at `0x85` and increment per discovered UniID.

First-device A0 template:

```text
F7 FD 10 00 A0 85 <12-byte-UniID> CRC
```

The two-device count is now hardware-validated for the K2 Pro X/Y bus. Both devices identify in loader as `mot2_023_C30-mot2_002_071`. E is not part of that RS-485 loader enumeration: after the same power-cycle it is read through Nozzle transparent mode with the P2P loader protocol and identifies as `mot2_022_C30-mot2_002_071`.

## Motor F0 path

Once a type-2 device is already in loader mode and temporarily addressed, the stock path is:

```text
F0/00  loader/hardware + application identity
F0/03  sector token
F0/01  update request
<len>  little-endian firmware length
<data> firmware chunks
F0/02  start application
```

Important difference from CFS: device type 2 does **not** receive `F0/06` erase. The motor-side erase/application-preparation mechanism remains unresolved and must not be guessed.

At temporary address `0x85`, the recovered non-write frames are:

```text
F0/00  F7 85 04 00 F0 00 4C
F0/03  F7 85 04 00 F0 03 45
F0/02  F7 85 04 00 F0 02 42
```

## Boot parameters observed live

Read-only application-level probing on X/Y/E returned identical persistent values:

```text
flash_param_version          583 / 0x0247  -> mot2_002_071
boot_key                     17030 / 0x4286
system_startup_delay_ms      100
flash_key_write_retries_num  5
```

RAM and flash readbacks match for these parameters.

`boot_key`, `system_startup_delay_ms`, and `flash_key_write_retries_num` are registered by both analysed 071 and 081 applications. Static application cross-references do not show ordinary consumption of those values beyond registration. The literal `0x4286` is absent from both old and new stock host updater binaries.

This remains consistent with controller/loader-side boot coordination, but the live hardware probe shows that no boot-key write is required to expose the loaders: GPIO140 power-cycle alone is sufficient. The exact semantic meaning of `0x4286` remains unresolved.

## Offline command

```bash
python -m k2fw inspect-motor-loader-probe
```

The command remains an offline renderer for the loader-present RS-485 path. It does not perform the now-validated GPIO140 maintenance power-cycle and always reports serial I/O, erase, update request, data transfer, and flash support as disabled.

## Live entry validation and remaining gates

A guarded K2 Pro maintenance probe now validates:

- GPIO140 power-cycle -> two X/Y loader replies in `mode=1`;
- A0 temporary addresses `0x85` / `0x86`;
- F0/00 identities `mot2_023_C30-mot2_002_071`;
- F0/02 application-start ACK on both devices;
- post-restore application recovery through normal `motor_control` startup.

One Y runtime address probe timed out immediately after restore and recovered on the normal motor-control retry path. Therefore F0/02 ACK alone is not treated as sufficient application-readiness proof.

The loader-entry gate is closed as a research question, but write support remains disabled until motor sector/chunk behavior, write preparation/erase semantics, post-write verification and interrupted-write recovery are hardware-validated.