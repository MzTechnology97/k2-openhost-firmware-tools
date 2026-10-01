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
- live CM5 flash preflight: print state, heater targets and serial-port ownership are checked read-only; with normal Klipper running the preflight correctly blocks because `/dev/ttyUSB0..2` are owned by Klippy.

Still required:

- discover CFS boot/hardware variant without entering update mode;
- query X/Y/E motor hardware/application versions without changing parameters;
- query main MCU and nozzle MCU boot/application versions;
- produce one `k2fw status` report combining live devices with a selected local firmware tree.

## Phase 3 — stock update protocol recovery

- recover serial MCU update frame sequence from `mcu_util`;
- recover RS-485 bootloader/update frame sequence from `mcu_util_485`;
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
