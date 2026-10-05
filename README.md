# K2-OpenHost Firmware Tools

Experimental tooling for inspecting, comparing and eventually updating the peripheral firmware used by Creality K2-class printers from a K2-OpenHost host.

> [!WARNING]
> **Experienced users only — use at your own risk.** K2-OpenHost voids the manufacturer's warranty and can damage the printer beyond repair, brick its firmware or, in case of malfunction, cause a fire. The authors accept no liability for damage to property or persons.
> In OpenHost mode the **nozzle and chamber cameras** cannot be managed by the T113 and must be rewired directly to the external Linux host, and the printer's **external USB port** cannot be used to print and stops working completely in gadget mode.
> Read the [disclaimer and hardware limitations](https://github.com/MzTechnology97/K2-OpenHost/blob/main/docs/en/DISCLAIMER.md) ([italiano](https://github.com/MzTechnology97/K2-OpenHost/blob/main/docs/it/DISCLAIMER.md)) before using this repository.

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

The current implementation provides safe firmware-tree scanning, manifest comparison, exact target resolution, a multi-device firmware architecture model, CFS probing and a live read-only status path for Main MCU, Toolhead/Nozzle MCU, X/Y/E closed-loop motor controllers and the CFS application. It does **not** contain a flash command.

```bash
python -m k2fw device-matrix
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
python -m k2fw preflight --port /dev/serial/by-id/<gadget>-if02-port0   # read-only; see docs/SAFETY.md
python -m k2fw probe-mcus
python -m k2fw probe-motors
python -m k2fw status
python -m k2fw status --manifest firmware.json
python -m k2fw identity --loader-evidence evidence/k2_pro_live_loader_probe_2026-10-04.json --manifest firmware.json
python -m k2fw inspect-update /path/to/cfs0_050_G30-cfs0_000_150.bin
python -m k2fw inspect-cfs-loader-probe
python -m k2fw inspect-motor-loader-probe
python -m k2fw inspect-mcu-update /path/to/mcu0_120_G32-mcu0_001_000.bin
```

`probe-motors` uses the normal motor application protocol and reads parameter id 0 (`flash_param_version`) through the existing Kalico transport. On the development K2 Pro all X/Y/E controllers report `0x0247` (583), which exactly matches the analysed `mot2_002_071` image; the analysed `mot2_002_081` image uses `0x024b` (587). The mapping is intentionally limited to the known K2 Pro artifacts.

Read-only motor probing also confirms identical X/Y/E `boot_key=17030 (0x4286)`, `system_startup_delay_ms=100` and `flash_key_write_retries_num=5`. A guarded GPIO140 power-cycle has now hardware-validated loader entry on the development K2 Pro: the two X/Y RS-485 controllers identify as `mot2_023_C30-mot2_002_071`, while E identifies separately as `mot2_022_C30-mot2_002_071` through Nozzle transparent P2P. No boot-key write was required. See `docs/MOTOR_LOADER_PROTOCOL.md` and `docs/LIVE_LOADER_IDENTITY.md`.

`status` also reads the already-published CFS `VERSION_SN` state from Moonraker. On the development K2 Pro it reports application `1.1.3`, mapped to the analysed `cfs0_000_113` application. It deliberately reports the boot/hardware variant as unknown: Cortex-M analysis did not identify a runtime path that accepts the stock `F0/00` identity query, and bounded live checks with both operational and addressing headers returned `INVALID_PARAM`. Stock `mcu_util_485` reaches `F0/00` only after its A1/A0 address-management sequence; `status` does not reproduce that state-changing sequence.

For Main and Nozzle, `status` keeps the live Kalico identity separate from the stock F012 package target. The analysed F012 trees contain exactly one direct-MCU artifact for each role: `mcu0_120_G32-mcu0_001_000.bin` for Main and `noz0_130_G30-noz0_021_000.bin` for Nozzle. These package targets are reported with `runtime_verified=false`; they are not presented as bootloader identities read from the device. Creality's exact 25-byte identity query belongs to the `mcu_util` loader state machine, which K2-OpenHost does not enter for status collection.

With `--manifest`, application-only motor/CFS status remains `hardware-unresolved`. When a separately validated `loader_identity` is available, the comparator now prefers that exact live hardware token and can resolve an exact target plus `update_required`, while still keeping `flash_allowed=false`. On the development K2 Pro this resolves X/Y to `mot2_023_C30`, E to `mot2_022_C30`, and CFS to `cfs0_050_G32`. See `docs/MANIFEST_COMPARISON.md`.

`identity` builds the versioned firmware identity contract (`k2fw.identity/1`) for every role from the same reads. It keeps three kinds of data apart:
- the runtime observation;
- a loader identity, taken only from authorized, dated evidence and cross-checked against the runtime fingerprint;
- the package target.

`update_required` appears only with a verified loader identity and an exact target; `flash_allowed` is always false. See `docs/FIRMWARE_IDENTITY_CONTRACT.md`.

Motor GET (function 0x08) readings were mapped statically in all four analysed motor images (`docs/MOT2_GET_READINGS.md`):
- indices 0–18, with no default case;
- reference/feedback of the position, speed and two current loops;
- phase currents, stall flag, encoder counts (int32, not float), MCU temperature and supply voltage.

`k2fw.mot2_get` decodes only the proven formats. Only the temperature has been observed live; a supervised hardware check is proposed, not run.

The guarded multi-device loader probe has now validated the common GPIO140 loader-entry path for Main, Nozzle, E, X/Y and CFS without erase or firmware transfer. The exact live identities and restore observations are documented in `docs/LIVE_LOADER_IDENTITY.md`.

Phase 3 now also includes an offline CFS RS-485 update inspector. Forced decompilation of the stock `F0` receive handler corrected the exact sequence: `00` get-version, `03` get-sector-size, `06` private-flash erase, `01` update-request, raw 32-bit application length, firmware data, then `02` start-app after the final data reply reaches `DONE`. Chunk size is derived from the one-byte sector token returned by the target; the inspector does not invent a schedule when that runtime token is unknown. It can render the fixed control-frame bytes offline for review, but has no serial writer and always keeps `send_enabled=false`. See `docs/RS485_UPDATE_PROTOCOL.md`. Static CFS image-layout and recovery-boundary analysis is documented in `docs/CFS_RECOVERY_ANALYSIS.md`. The explicit loader-mode protocol and guarded non-flash live probe are documented in `docs/CFS_LOADER_PROBE.md`. Cross-device motor/CFS/Main/Toolhead architecture is documented in `docs/FIRMWARE_DEVICE_ARCHITECTURE.md`.

The direct Main/Nozzle serial updater has now been recovered as well. `mcu_util` uses `75` handshake and complemented control pairs `04 FB` enter-transparent, `05 FA` exit-transparent, `00 FF` get-version, `03 FC` get-sector-size, `01 FE` update-request and `02 FD` start-app; application length and data chunks carry the same one's-complement checksum. Both analysed F012 Main and Nozzle images also contain the exact CanBoot/Katapult `CANBOOT_SIGNATURE` at offset `0x3E0` and `REQUEST_START_APP` immediately at `0x3E8`; the upstream `REQUEST_CANBOOT` magic is absent. This proves reuse of those boot-transition ABI constants, not equivalence with the upstream Katapult wire protocol. `k2fw inspect-mcu-update` now reports that fingerprint offline. See `docs/DIRECT_MCU_UPDATE_PROTOCOL.md`.

Stock reset orchestration is now separated from those protocol paths. Both compared `upgrade-server` generations perform the CFS/Box sequence `klipper stop -> mcu_reset.sh -> CFS=1 mcu_update`, while their “mcu upgrade” branch is a distinct host-MCU SWD mechanism using `/sys/devices/platform/swd/swd_update`. The byte-identical `mcu_reset.sh` power-cycles GPIO 140/PE12 for two seconds; K2-OpenHost does not expose that action. See `docs/STOCK_RESET_ORCHESTRATION.md`.

For a live CFS query, first release the RS-485 port from Klipper and then explicitly acknowledge exclusive ownership:

```bash
python -m k2fw probe-cfs --port /dev/ttyUSB2 --exclusive
```

For the separate **state-changing but non-flash** loader identity/sector probe, Kalico must already have released the port and exactly one CFS must be connected:

```bash
python -m k2fw probe-cfs-loader   --exclusive   --single-cfs   --ack-state-change   --printer-safe-confirmed
```

This command is guarded by a TX allowlist and mandatory application restore/verification. It has now been validated on the development K2 Pro: the CFS identifies as `cfs0_050_G32-cfs0_000_113`, returns sector token `0xE0` (128-byte stock chunks), and required the Jacob `0B/01` fallback before A2 verified application mode.

See `docs/LIVE_READ_ONLY_STATUS.md` for the validated live probes, `docs/MANIFEST_COMPARISON.md` for live-vs-manifest comparison, `docs/DIRECT_MCU_UPDATE_PROTOCOL.md` for the recovered Main/Nozzle serial protocol, `docs/STOCK_RESET_ORCHESTRATION.md` for the stock power/reset boundaries, `docs/STOCK_UPDATE_PATH.md` for the stock orchestration, `docs/PERIPHERAL_GENERATIONS.md` for the old/new device deltas and `docs/SAFETY.md` for the validation gates required before write support is enabled.

## Project relationship

This repository is part of the K2-OpenHost project and is separate from the Kalico and Mainsail forks and the Cartographer plugin. Original Creality firmware remains Creality software; this repository stores only independently written tooling, documentation, hashes and metadata derived from user-supplied images.