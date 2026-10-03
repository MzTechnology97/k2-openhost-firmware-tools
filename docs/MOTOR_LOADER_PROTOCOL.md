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

This proves that the stock updater expects the motor to be in loader state before the F0 update phase. No host-side motor loader-entry command has been recovered.

## Temporary loader addresses

The stock updater expects two type-2 motors on this RS-485 enumeration path. Their temporary loader addresses begin at `0x85` and increment per discovered UniID.

First-device A0 template:

```text
F7 FD 10 00 A0 85 <12-byte-UniID> CRC
```

The two-device count proves the path for the stock X/Y bus enumeration. The E motor is known to use the same runtime motor application protocol through the Toolhead transparent transport, but equivalence of its stock loader enumeration has not yet been proven.

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

This is consistent with controller/loader-side boot coordination, but does not prove what value selects loader mode or whether `0x4286` is an entry key, an unlock key, or another boot policy field. No boot-key write or motor reset has been performed.

## Offline command

```bash
python -m k2fw inspect-motor-loader-probe
```

The command renders only the proven loader-present path. It deliberately omits any loader-entry transaction and always reports serial I/O, erase, update request, data transfer, and flash support as disabled.

## Remaining gate

Before a live motor loader probe can exist, at least one of the following must be proven independently:

- a non-destructive command that moves an application motor into loader mode; or
- a controlled reset/power sequence that reliably produces `mode=1`, with a proven application-restore path.

Until then, motor loader entry and all motor writes remain disabled.