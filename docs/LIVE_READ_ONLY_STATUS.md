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

## Stock updater version commands

Static analysis recovered two other version mechanisms:

- direct `mcu_util`: request `00 ff`, response 25-byte identity plus checksum;
- `mcu_util_485`: function `0xF0`, payload `0x00` after stock discovery/address handling.

Both are updater-path protocol evidence. The RS-485 `F0/00` request was also confirmed in both compared host updater generations, but an application-mode X motor did not respond to it. It is therefore not used by `k2fw status`.

## Commands

```bash
python -m k2fw probe-mcus
python -m k2fw probe-motors
python -m k2fw status
```

`probe-motors` refuses to run while homing, printing or paused. Every returned device record includes `write_enabled=false`.

The separate CFS runtime probe remains available as `probe-cfs` and requires explicit exclusive ownership of `/dev/ttyUSB2`.
