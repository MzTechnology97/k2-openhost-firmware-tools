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

### F012 stock package targets vs. live identity

The two analysed K2 Pro F012 firmware trees (`1.1.0.94` and `1.1.6.7.2`) each contain exactly one direct-MCU artifact for the Main role and one for the Nozzle role:

| Role | Stock package target | Size | SHA-256 |
| --- | --- | ---: | --- |
| Main | `mcu0_120_G32-mcu0_001_000.bin` | 30948 B | `bec548e946f0dd37d15f87569b23d55fb12410068f1a3ad2a95c45bf89c756d6` |
| Nozzle | `noz0_130_G30-noz0_021_000.bin` | 30872 B | `6915e65bcbc543857a915ea93e4f0000879c851865efe776d83a8c9354be3208` |

The hashes are identical in both compared host releases. Static string inspection of the images exposes the application tokens `mcu0_001_000` / `noz0_021_000` and the `CanBoot!` marker, but not an independent copy of the G32/G30 hardware token.

`k2fw status` therefore includes these values only under `stock_package_candidate`, with `runtime_verified=false`. This says “Creality ships this unique target for F012 and this role”; it does **not** say “the running bootloader returned this identity”.

### Why the exact stock identity is not queried live

Static recovery of `mcu_util` shows the direct-MCU state machine:

- handshake phase sends `0x75` and expects `0x75`;
- version phase sends `00 FF`;
- the version response is 26 bytes: 25 bytes of hardware/application identity plus checksum;
- `mcu_util --get-version` is documented by Creality as requiring the loader handshake;
- the stock `mcu_update` service runs the handshake before version comparison and, when no update is needed, explicitly calls `startup_app`.

This is a loader/update lifecycle, not the normal Klipper application protocol. Obtaining the stock token from a running K2-OpenHost Main/Nozzle would therefore require leaving the current application path or relying on a previously recorded stock result. Neither is done by `k2fw status`.

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

The live firmware-status command intentionally reports identity/version data only. Environment telemetry belongs to the running Kalico Box adapter: on the validated CFS 1.1.3 path, the four-byte command `0x0A` state carries temperature and relative humidity, while command `0x15` is retained as raw hardware-status/self-test diagnostics. `k2fw status` does not duplicate or reinterpret those fields.

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

## Compare with an explicitly selected manifest

`k2fw status --manifest firmware.json` adds a read-only manifest comparison to the same live report. Main and Nozzle use package provenance when no live loader identity is attached; motor/CFS application fingerprints still produce candidate lists when hardware is unknown. A separately validated loader probe may attach exact `loader_identity.hardware`, in which case the comparator resolves one exact artifact and may report an application-version difference while keeping `flash_allowed=false`.

The comparator intentionally leaves `update_required=null` where live hardware identity is not sufficient and always returns `flash_allowed=false`. See `MANIFEST_COMPARISON.md` for the full matching policy and the validation against the extracted K2 Pro `1.1.6.7.2` firmware.


## Separately validated loader identities

A guarded GPIO140 maintenance probe on 2026-10-04 established exact loader identities that are intentionally kept separate from ordinary `status` collection:

```text
Main:   mcu0_120_G32-mcu0_001_000
Nozzle: noz0_130_G30-noz0_021_000
X/Y:    mot2_023_C30-mot2_002_071  (two RS-485 devices)
E:      mot2_022_C30-mot2_002_071  (Nozzle transparent P2P)
CFS:    cfs0_050_G32-cfs0_000_113
```

The maintenance probe is state-changing because it power-cycles `MCU_PWR_EN` and performs temporary loader address assignment. It is therefore not part of the ordinary read-only `status` path. See `LIVE_LOADER_IDENTITY.md`.