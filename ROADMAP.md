# Roadmap

## Phase 1 — firmware inventory and evidence ✅

- classify Creality peripheral `.bin` files;
- calculate SHA-256 and sizes;
- ingest `version.json` manifests;
- compare old/new firmware trees by hardware target;
- document stock `mcu_update`, `mcu_util` and `mcu_util_485` orchestration;
- confirm the development K2 Pro currently reports CFS firmware 1.1.3;
- confirm the K2 Pro `1.1.0.94` -> `1.1.6.7.2` peripheral deltas: CFS and closed-loop motors changed, while the compared F012 main MCU, nozzle MCU, belt and RFID images are byte-identical.

## Phase 2 — read-only live probing 🚧

Completed/validated:

- CFS runtime `VERSION_SN` probe over RS-485;
- exact local firmware candidate resolver that refuses ambiguous hardware matches and never enables writes;
- candidate resolver validated against the real extracted `1.1.6.7.2` bundle (`cfs0_050_G30` -> `cfs0_000_150`, expected SHA-256);
- live CM5 flash preflight: print state, heater targets and serial-port ownership are checked read-only; with normal Klipper running the preflight correctly blocks because `/dev/ttyUSB0..2` are owned by Klippy;
- X/Y/E runtime firmware fingerprint via application `FLASH_PARAM` id 0 (`583/0x0247` = known `mot2_002_071`; analysed `081` uses `587/0x024b`);
- Main MCU and Nozzle MCU running Klipper/Kalico application identity via Moonraker;
- F012 Main/Nozzle stock package targets pinned separately from live identity (`mcu0_120_G32-mcu0_001_000` and `noz0_130_G30-noz0_021_000`), with exact sizes/SHA-256 and `runtime_verified=false`;
- direct-MCU loader identity boundary recovered: `mcu_util` handshakes with `0x75`, reads the 25-byte identity via `00 FF`, and stock `mcu_update` later calls `startup_app`; K2-OpenHost does not move a running MCU into this path for status;
- CFS application identity added to `k2fw status` without exposing its serial/UniID;
- CFS 1.1.3 runtime boot/hardware investigation completed: G30/G32 is absent from the byte-identical application images, and both bounded runtime `F0/00` probes returned `INVALID_PARAM`; stock `mcu_util_485` reaches its exact identity read after A1/A0 address management, so runtime status reports the boot variant as `unknown` rather than mutating address state;
- unified `k2fw status` for Main + Nozzle + X/Y/E + CFS.

Still required:
- identify a non-mutating source of the exact CFS boot/hardware variant (or require explicit operator provenance) before any CFS write support;
- find an independently recorded/non-mutating source that confirms the Main/Nozzle bootloader token pair at runtime; package targets are known, but the exact loader identity remains intentionally unqueried;
- combine the live report with an explicitly selected local firmware tree.

## Phase 3 — stock update protocol recovery

- direct MCU stock version request `00 ff` and 25-byte identity response: **recovered statically**;
- RS-485 updater-stage version request `F0/00`: **recovered statically in both compared updater generations**;
- recover the remaining serial MCU update frame sequence from `mcu_util`;
- recover the remaining RS-485 bootloader/update frame sequence from `mcu_util_485`;
- compare old/new updater implementations (already confirmed to be different binaries);
- implement frame codecs with unit tests and captured read-only fixtures;
- identify recovery/startup commands for interrupted updates.

## Phase 4 — controlled flashing

Write support remains disabled until Phase 2 and Phase 3 are complete.

The first writable implementation will update one explicitly selected device at a time and require:

- exact model/target match;
- current and target versions displayed before write;
- SHA-256-verified local image;
- exclusive serial ownership;
- printer idle and heaters off;
- explicit confirmation;
- post-write version verification;
- recovery instructions for that device class.

The first experimental write target is expected to be the CFS only after its cfs0 boot/hardware generation and recovery sequence are identified. Motors and MCU targets remain independently gated.

Only after those paths are hardware-validated should integration with Moonraker/Mainsail Update Manager be considered.