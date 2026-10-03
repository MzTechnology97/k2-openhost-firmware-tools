# K2-OpenHost Firmware Tools

Experimental tooling for inspecting, comparing and eventually updating the peripheral firmware used by Creality K2-class printers from a K2-OpenHost host.

The project is intentionally split into two phases:

1. **read-only discovery and validation** — inventory firmware bundles, identify target hardware, compare versions and hashes, and probe the live printer without changing it;
2. **controlled flashing** — only after the stock Creality update protocol and recovery behaviour have been reproduced and validated on hardware.

No Creality firmware binaries are stored in this repository. The tools operate on firmware files supplied locally by the printer owner.

## Why this repository exists

Static analysis of K2 Pro stock firmware shows that Creality already ships dedicated peripheral update utilities rather than relying only on a monolithic system-image update:

- `mcu_util` handles serial MCU firmware handshaking, version queries and application updates;
- `mcu_util_485` handles RS-485 devices including motors, CFS, belt and RFID devices;
- `/etc/init.d/mcu_update` selects the K2 model firmware directory, compares the running hardware/application version with the matching `.bin`, and orchestrates updates;
- `upgrade-server` invokes the MCU/CFS update path during the stock OTA workflow.

The stock K2 Pro script maps the relevant transports as:

```text
/dev/ttyS2  main MCU
/dev/ttyS3  nozzle MCU
/dev/ttyS5  RS-485 peripherals
```

K2-OpenHost exposes the same links to the CM5 through the T113 bridge as `/dev/ttyUSB0`, `/dev/ttyUSB1` and `/dev/ttyUSB2`.

## Important K2 Pro firmware finding

A comparison of stock K2 Pro firmware `1.1.0.94` with `1.1.6.7.2` confirms that the CFS firmware itself changed:

```text
1.1.0.94 : cfs0_050_G30-cfs0_000_113.bin  151724 bytes
1.1.6.7.2: cfs0_050_G30-cfs0_000_150.bin  175104 bytes
```

The G30/G32 CFS images are identical within each release, but the application revision changes from `cfs0_000_113` to `cfs0_000_150`. The newer release also adds a `cfs6_100_G31-cfs6_220_000.bin` variant.

The F012 closed-loop motor firmware also changes from application `mot2_002_071` to `mot2_002_081`, while the compared F012 main MCU, nozzle MCU, belt and RFID images are byte-identical. See `docs/PERIPHERAL_GENERATIONS.md`.

This makes firmware-generation differences a credible explanation for protocol differences observed between older K2 Pro hardware and integrations developed against newer CFS firmware. It does **not** by itself prove which individual protocol fields changed; that still requires wire-level or binary comparison.

## Current scope

The current implementation provides safe firmware-tree scanning, manifest comparison, exact target resolution, CFS probing and a live read-only status path for Main MCU, Nozzle MCU, X/Y/E closed-loop motor controllers and the CFS application. It does **not** contain a flash command.

```bash
python -m k2fw scan /path/to/usr/share/klipper/fw -o firmware.json
python -m k2fw compare old-manifest.json new-manifest.json
python -m k2fw resolve firmware.json \
  --hardware cfs0_050_G30 \
  --kind cfs \
  --parent cfs \
  --current-application cfs0_000_113
```

`resolve` deliberately produces a candidate-only plan with `write_enabled=false`. It requires an exact hardware token and refuses ambiguous targets; it is groundwork for the later updater, not a flashing shortcut.

For live state while Kalico is running:

```bash
python -m k2fw probe-mcus
python -m k2fw probe-motors
python -m k2fw status
python -m k2fw status --manifest firmware.json
python -m k2fw inspect-update /path/to/cfs0_050_G30-cfs0_000_150.bin
python -m k2fw inspect-cfs-loader-probe
python -m k2fw inspect-mcu-update /path/to/mcu0_120_G32-mcu0_001_000.bin
```

`probe-motors` uses the normal motor application protocol and reads parameter id 0 (`flash_param_version`) through the existing Kalico transport. On the development K2 Pro all X/Y/E controllers report `0x0247` (583), which exactly matches the analysed `mot2_002_071` image; the analysed `mot2_002_081` image uses `0x024b` (587). The mapping is intentionally limited to the known K2 Pro artifacts.

`status` also reads the already-published CFS `VERSION_SN` state from Moonraker. On the development K2 Pro it reports application `1.1.3`, mapped to the analysed `cfs0_000_113` application. It deliberately reports the boot/hardware variant as unknown: Cortex-M analysis did not identify a runtime path that accepts the stock `F0/00` identity query, and bounded live checks with both operational and addressing headers returned `INVALID_PARAM`. Stock `mcu_util_485` reaches `F0/00` only after its A1/A0 address-management sequence; `status` does not reproduce that state-changing sequence.

For Main and Nozzle, `status` keeps the live Kalico identity separate from the stock F012 package target. The analysed F012 trees contain exactly one direct-MCU artifact for each role: `mcu0_120_G32-mcu0_001_000.bin` for Main and `noz0_130_G30-noz0_021_000.bin` for Nozzle. These package targets are reported with `runtime_verified=false`; they are not presented as bootloader identities read from the device. Creality's exact 25-byte identity query belongs to the `mcu_util` loader state machine, which K2-OpenHost does not enter for status collection.

With `--manifest`, the live report is compared against an explicitly selected firmware manifest. Main/Nozzle can resolve their unique F012 package artifact while still reporting `runtime_verified=false`; motors and CFS remain `hardware-unresolved` when only an application fingerprint is known. The comparison never sets `update_required=true` or `flash_allowed=true` without exact live hardware identity. See `docs/MANIFEST_COMPARISON.md`.

Phase 3 now also includes an offline CFS RS-485 update inspector. Forced decompilation of the stock `F0` receive handler corrected the exact sequence: `00` get-version, `03` get-sector-size, `06` private-flash erase, `01` update-request, raw 32-bit application length, firmware data, then `02` start-app after the final data reply reaches `DONE`. Chunk size is derived from the one-byte sector token returned by the target; the inspector does not invent a schedule when that runtime token is unknown. It can render the fixed control-frame bytes offline for review, but has no serial writer and always keeps `send_enabled=false`. See `docs/RS485_UPDATE_PROTOCOL.md`. Static CFS image-layout and recovery-boundary analysis is documented in `docs/CFS_RECOVERY_ANALYSIS.md`. The explicit loader-mode protocol and the offline non-flash probe model are documented in `docs/CFS_LOADER_PROBE.md`; the live transition remains disabled.

The direct Main/Nozzle serial updater has now been recovered as well. `mcu_util` uses `75` handshake and complemented control pairs `04 FB` enter-transparent, `05 FA` exit-transparent, `00 FF` get-version, `03 FC` get-sector-size, `01 FE` update-request and `02 FD` start-app; application length and data chunks carry the same one's-complement checksum. `k2fw inspect-mcu-update` renders this path offline only. See `docs/DIRECT_MCU_UPDATE_PROTOCOL.md`.

Stock reset orchestration is now separated from those protocol paths. Both compared `upgrade-server` generations perform the CFS/Box sequence `klipper stop -> mcu_reset.sh -> CFS=1 mcu_update`, while their “mcu upgrade” branch is a distinct host-MCU SWD mechanism using `/sys/devices/platform/swd/swd_update`. The byte-identical `mcu_reset.sh` power-cycles GPIO 140/PE12 for two seconds; K2-OpenHost does not expose that action. See `docs/STOCK_RESET_ORCHESTRATION.md`.

For a live CFS query, first release the RS-485 port from Klipper and then explicitly acknowledge exclusive ownership:

```bash
python -m k2fw probe-cfs --port /dev/ttyUSB2 --exclusive
```

See `docs/LIVE_READ_ONLY_STATUS.md` for the validated live probes, `docs/MANIFEST_COMPARISON.md` for live-vs-manifest comparison, `docs/DIRECT_MCU_UPDATE_PROTOCOL.md` for the recovered Main/Nozzle serial protocol, `docs/STOCK_RESET_ORCHESTRATION.md` for the stock power/reset boundaries, `docs/STOCK_UPDATE_PATH.md` for the stock orchestration, `docs/PERIPHERAL_GENERATIONS.md` for the old/new device deltas and `docs/SAFETY.md` for the validation gates required before write support is enabled.

## Project relationship

This repository is part of the K2-OpenHost project and is separate from the Kalico, Mainsail and Cartographer forks. Original Creality firmware remains Creality software; this repository stores only independently written tooling, documentation, hashes and metadata derived from user-supplied images.