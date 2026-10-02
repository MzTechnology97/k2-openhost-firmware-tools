# Live read-only firmware status

This page records the live probes validated on the K2-OpenHost development K2 Pro on 2026-10-02.

No firmware flash, erase, update request, bootloader entry, application reset, RS-485 address assignment or motor-parameter write was performed to obtain the results below.

## Main and Nozzle MCU

While Kalico is connected, Moonraker already exposes the identity returned by each running Klipper MCU application. `k2fw probe-mcus` reads those objects only.

Validated development-printer result:

| Device | MCU | Running application |
| --- | --- | --- |
| Main | `gd32f303xe` | `1.1.0.48-312-gcd5c2b81-dirty-20241227_092331-ubuntu` |
| Nozzle | `gd32f303xb` | `1.1.0.48-293-g493f9a0f-dirty-20241220_143931-ubuntu1804` |

These are running Klipper/Kalico application identities, not stock bootloader hardware/application tokens. `bootloader_version` is therefore reported as `null` rather than guessed.

## X/Y/E closed-loop motors

The normal motor application exposes `flash_param_version` as parameter id 0. `k2fw probe-motors` asks the existing Kalico motor transport to read the live and flash-backed value; it does not open the RS-485 device behind Kalico and does not write/apply/save any parameter.

Static decompilation of the two known K2 Pro motor images established:

```text
mot2_002_071 -> flash_param_version 0x0247 -> 583
mot2_002_081 -> flash_param_version 0x024b -> 587
```

Live result:

```text
X -> 583 / 0x0247 -> mot2_002_071
Y -> 583 / 0x0247 -> mot2_002_071
E -> 583 / 0x0247 -> mot2_002_071
```

The application mapping is scoped to the firmware artifacts analysed by this project. Unknown values remain unknown rather than being inferred.

## CFS runtime identity and boot/hardware limit

`k2fw status` now consumes the CFS state already exposed by the running Kalico `box` object. It copies only the application firmware version and deliberately drops the CFS serial number, raw payload and full VERSION_SN text.

Validated development-printer result:

```text
CFS address 1
running application version: 1.1.3
matched application: cfs0_000_113
boot hardware: unknown
```

The missing G30/G32 value is intentional, not an unresolved parser bug. Static Cortex-M/Thumb analysis of the 151724-byte `cfs0_050_G30-cfs0_000_113.bin` application (SHA-256 `386a1106391a332e6a97803c5ce00b87b6d3ddc4c3d61f6fe07fb19fd3125b76`) recovered 606 functions. The normal application exposes `0x14` VERSION_SN and `0x15` diagnostics; the analysis did not identify a runtime path that accepts the stock `F0/00` exact-identity query. The same 1.1.3 G30 and G32 application images are byte-identical and contain the application token `cfs0_000_113`, not a G30/G32 boot token.

Two bounded live checks matched that result: both operational-header `FF/F0/00` and addressing-header `00/F0/00` returned status `0x01` (`INVALID_PARAM`) with no identity payload at the already assigned CFS address. No erase, update request, reset, address reassignment or bootloader-entry command was sent.

Static analysis of stock `mcu_util_485` shows that its exact-identity `F0/00` read occurs after its own discovery/address-management sequence, including A1/A0. Reproducing A0 would change RS-485 address state, so K2-OpenHost deliberately stops before that point. An exact G30/G32 value therefore remains a safety gate for future write support, not something `status` guesses.

## Stock updater version commands

Static analysis recovered two other version mechanisms:

- direct `mcu_util`: request `00 ff`, response 25-byte identity plus checksum;
- `mcu_util_485`: function `0xF0`, payload `0x00` after stock discovery/address handling.

Both are updater-path protocol evidence. The RS-485 `F0/00` request was confirmed in both compared host updater generations. On the development K2 Pro, bounded runtime probes returned `INVALID_PARAM` for both tested headers; the stock utility reaches its identity read only after discovery/address management. It is therefore not used by `k2fw status`.

## Commands

```bash
python -m k2fw probe-mcus
python -m k2fw probe-motors
python -m k2fw status
```

`probe-motors` refuses to run while homing, printing or paused. Every returned device record includes `write_enabled=false`.

The separate CFS runtime probe remains available as `probe-cfs` and requires explicit exclusive ownership of `/dev/ttyUSB2`.
