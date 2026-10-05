# K2 Pro peripheral firmware generations

This page records byte-level differences between the K2 Pro stock bundles `1.1.0.94` and `1.1.6.7.2`. It does not infer compatibility from filenames alone.

## F012 devices

| Device class | 1.1.0.94 | 1.1.6.7.2 | Result |
| --- | --- | --- | --- |
| Main MCU | `mcu0_120_G32-mcu0_001_000` | same | byte-identical |
| Nozzle MCU | `noz0_130_G30-noz0_021_000` | same | byte-identical |
| Belt | `bet0_023_C03-bet0_000_001` | same | byte-identical |
| RFID | `rfd0_010_G21-rfd0_000_009` | same | byte-identical |
| Closed-loop motors | `mot2_002_071` | `mot2_002_081` | changed |
| CFS cfs0 family | `cfs0_000_113` | `cfs0_000_150` | changed |

The motor application change is present in both the root F012 motor images and the `F012/motor/` variants. The newer motor binaries are also larger, so the change is not only a renamed version token.

The Main and Nozzle artifacts are not only name-stable but byte-identical across the compared releases:

```text
mcu0_120_G32-mcu0_001_000.bin
  30948 bytes
  sha256 bec548e946f0dd37d15f87569b23d55fb12410068f1a3ad2a95c45bf89c756d6

noz0_130_G30-noz0_021_000.bin
  30872 bytes
  sha256 6915e65bcbc543857a915ea93e4f0000879c851865efe776d83a8c9354be3208
```

These are the unique F012 package targets for their roles. They are useful selection evidence, but their hardware tokens must not be described as a live bootloader identity unless the device itself (or a trusted prior stock log) supplied that identity.

### Runtime motor fingerprint

Static decompilation gives an application-level fingerprint that can be read without entering the updater/bootloader path:

| Motor application | `flash_param_version` | Decimal |
| --- | ---: | ---: |
| `mot2_002_071` | `0x0247` | 583 |
| `mot2_002_081` | `0x024b` | 587 |

On 2026-10-02 the development K2 Pro returned 583 from X, Y and E through the normal motor `FLASH_PARAM` read command, so all three match the analysed `mot2_002_071` generation. This is an exact match within the firmware artifacts analysed by this project, not a claim that 583 uniquely identifies every Creality motor firmware ever released.

## CFS

The old G30/G32 images are 151724 bytes and share the same SHA-256. The newer G30/G32 images are 175104 bytes and also share the same SHA-256 within that release. The newer bundle additionally introduces the separate `cfs6_100_G31-cfs6_220_000` target.

A live read-only query on the development printer reports CFS firmware `1.1.3`, matching the old `cfs0_000_113` application generation. See `CFS_GENERATIONS.md` and the evidence JSON for hashes.

## Updater utilities also changed

The host-side flashing utilities are not identical between these releases:

| Utility | 1.1.0.94 size | 1.1.6.7.2 size |
| --- | ---: | ---: |
| `mcu_util` | 13912 B | 13928 B |
| `mcu_util_485` | 38444 B | 42540 B |

Both generations expose the same broad update model, including CFS handling, but the newer `mcu_util_485` contains additional code. Therefore a future K2-OpenHost updater must version the protocol implementation against observed device/updater generations rather than assuming one binary protocol forever.

## Development consequence

Updating the complete T113 operating-system image is not required merely to bring peripheral firmware forward. The stock design already treats these peripherals as separately updatable devices. K2-OpenHost will therefore continue toward explicit per-device update support, while retaining exact hardware matching and recovery gates.

The first writable target should not be selected until the read-only probe can identify the boot/hardware generation required to distinguish a valid `cfs0_050_G30`/`G32` target and the update/recovery framing has been reproduced.