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
- unified `k2fw status` for Main + Nozzle + X/Y/E + CFS;
- optional `k2fw status --manifest` comparison against an explicitly selected manifest; application-only motor/CFS records remain unresolved, while separately validated live loader identities can now resolve exact artifacts without enabling writes;
- MOT2 GET index map recovered statically (071/081, both profiles), with `k2fw.mot2_get` parsers for the proven formats:
  - indices 1–10, 14–16 and 18 are field-verified, with units partly candidate;
  - 17 is verified live;
  - 11–13 are subdivision domain (out of scope);
  - ≥19 return stale data;
  - tracking error is not exposed;
  - the supervised hardware check is still required before any telemetry;
- real `1.1.6.7.2` validation: Main/Nozzle package targets resolved, seven F012 motor candidates and two cfs0 CFS candidates remained unresolved, and every update decision stayed `null` / `flash_allowed=false`.

Still required:
- identify a non-mutating source of the exact CFS boot/hardware variant (or require explicit operator provenance) before any CFS write support;
- find an independently recorded/non-mutating source that confirms the Main/Nozzle bootloader token pair at runtime; package targets are known, but the exact loader identity remains intentionally unqueried;

## Phase 3 — stock update protocol recovery

- direct MCU stock version request `00 ff` and 25-byte identity response: **recovered statically**;
- RS-485 updater-stage version request `F0/00`: **recovered statically in both compared updater generations**;
- RS-485 F0 receive dispatcher and embedded state table recovered from both `mcu_util_485` generations;
- corrected core update sequence: `F0/00` get-version, `F0/03` get-sector-size, `F0/06` erase, `F0/01` update-request, raw little-endian application length, firmware data, receive-side `DONE -> update_end`, then `F0/02` start-app;
- embedded F0 response codes recovered: `1F=NACK`, `20=DONE`, `21=FAIL`, `75=ACK`, `FF=NONE`;
- ACK transitions recovered: update-request -> app-len -> app-data; app-data ACK loops, DONE reaches update-end; start-app ACK reaches app-run;
- chunk-size calculation recovered from the signed sector token; the development G32 CFS now returns `0xE0`, giving 128-byte chunks and 1368 chunks for the 1.5.0 image;
- interrupted data behavior recovered: if state 9/update-end is not reached, stock marks the device failed and skips its later start-app command;
- old/new comparison completed for the core F0 path: receive-state semantics are equivalent; the newer updater extends selected handling from device type 1 to types 1/10;
- offline `k2fw inspect-update` planner implemented for exact CFS images, including fixed control-frame rendering and optional trusted sector-token arithmetic, with permanent `serial_io_performed=false` / `write_enabled=false` / `send_enabled=false` / `flash_allowed=false`;
- direct serial MCU update sequence recovered from both `mcu_util` generations: `75` handshake, `00 FF` version, `03 FC` sector-size, `01 FE` update-request, little-endian application length + checksum, firmware chunks + checksum, then `02 FD` start-app; `04 FB`/`05 FA` are transparent-mode controls;
- direct-MCU checksum recovered as one's-complement of the uint8 payload sum; fixed control frames and app-length framing covered by tests;
- direct-MCU sector-token chunk formula recovered: positive signed token -> token × 1024 bytes, negative -> abs(token) × 4 bytes, zero invalid, with stock checked-read buffer size `0x4400`;
- direct-MCU data retry semantics recovered: checksum failure/NACK restarts at `update_request` and seeks the firmware file back to offset 0, up to three data retry cycles;
- old/new direct updater comparison completed: core protocol is equivalent; `1.1.6.7.2` adds `-d/--delay` byte pacing;
- offline `k2fw inspect-mcu-update` implemented for Main/Nozzle images with permanent `serial_io_performed=false` / `write_enabled=false` / `send_enabled=false` / `flash_allowed=false`;
- determine the real Main/Nozzle sector token on recoverable hardware before any writable direct-MCU path;
- static cfs0 image layout recovered: both analysed generations are linked at `0x08010000`, leaving a distinct 64 KiB lower-flash region; the stock bundle contains no separate cfs0 bootloader image;
- G30/G32 application images are byte-identical in both analysed releases, so the board variant does not change application payload bytes, while loader identity remains a safety gate;
- recovered stock host flow carries no flash destination address; erase/write placement is owned by the peripheral loader;
- CFS loader/application mode is now explicit in the Jacob-lineage A0/A1/A2 protocol (`0=app`, `1=loader`), with a recovered `0B/01` loader-to-app recovery path;
- offline `inspect-cfs-loader-probe` added to render loader detection, identity/sector probing and app restore without serial I/O;
- guarded live `probe-cfs-loader` hardware-validated with a hard non-flash TX allowlist, mandatory acknowledgements, port-ownership check and application restore/verification in `finally`;
- independent community reconstruction corroborates an active loader-entry path and application-only erase behavior; these remain external corroboration, not a substitute for our own hardware capture;
- development CFS live identity resolved as `cfs0_050_G32-cfs0_000_113`; sector token `0xE0` resolves stock chunk size to 128 bytes;
- 1.1.6.7.2 exact CFS target resolved to `cfs0_050_G32-cfs0_000_150.bin`, 1368 chunks of 128 bytes;
- live restore verified: `F0/02` ACK alone did not leave loader mode, while Jacob `0B/01` transitioned to application mode; post-start A2 verification is mandatory;
- host-side interruption behavior recovered: retries are transaction-local (max three), there is no resume offset/checkpoint, and a fresh invocation restarts the image from offset 0;
- prove device-side CFS loader reachability/recovery after interrupted erase/data transfer on recoverable hardware;
- RS-485 device matrix recovered: motor=type 2/group 0xFD, belt=3/0xFC, RFID=4/0xFB, CFS=1/0xFE, CFS Pro=10/0xFE;
- stock motor loader-mode gate recovered: A1 group `0xFD` uses payload `FD FD`, A1/A2 identity carries `device_type | mode | UniID`, and only type-2 devices with `mode=1` enter the firmware path;
- stock motor enumeration expects exactly two type-2 devices and assigns temporary addresses starting at `0x85`; live K2 Pro probing validates those two X/Y devices as `mot2_023_C30`, while E is independently proven on the Nozzle transparent P2P loader path as `mot2_022_C30`;
- motor updater path confirmed to share A1/A0/F0 version-sector-update-data-start states with CFS, while explicit F0/06 erase is skipped for motors; live X/Y F0/03 tokens are both `0xE0`, resolving 128-byte chunks;
- development X/Y/E read-only boot parameters confirmed identical: `boot_key=0x4286`, `system_startup_delay_ms=100`, `flash_key_write_retries_num=5`; the 0x4286 literal is absent from both old/new host updater binaries, and no boot-key write or reboot was performed;
- motor package analysis confirms application token embedded at offset 0x200 while hardware/loader token remains package provenance; motor loader placement/entry remains unresolved;
- Toolhead/Nozzle classified under the direct-mcu backend: stock lifecycle, live GPIO140 entry and sector token `0x02`/2048-byte chunk are proven; write/interrupted-recovery behavior remains gated;
- F012 Main and Toolhead/Nozzle images fingerprinted against upstream CanBoot/Katapult ABI constants: exact `CANBOOT_SIGNATURE` at `0x3e0` and `REQUEST_START_APP` at `0x3e8`; `REQUEST_CANBOOT` is absent, so reuse of boot-transition primitives is proven but upstream wire-protocol equivalence is not claimed;
- offline `k2fw inspect-motor-loader-probe` added for the proven loader-present path only; it deliberately omits an unproven loader-entry command and keeps all write/send/flash gates false;
- live K2 Pro application-state baseline: with Klipper ownership released, repeated motor A1 discovery (`f7 fd 05 00 a1 fd fd ce`) on the 230400 RS-485 path for 1.5 s returned zero bytes; loader discovery therefore was not exposed in the normal running-application state, strengthening the hardware power-on/reset hypothesis without proving GPIO140 fan-out or timing;
- live K2 Pro hardware-entry probe now validates GPIO140 MCU-rail power-cycle as the loader gate: Main and Nozzle respond on P2P @115200, E responds through Nozzle transparent mode, two RS-485 motors and one CFS report A1 mode=1 @230400, and all observed applications were restored without erase/update/data;
- post-restore runtime verification passed: `motor_ready=true`, both motor transports ready, CFS `IDLE/OK`, printer `ready/standby`, heater targets zero;
- live sector/chunk metadata hardware-validated without write commands: Main `0x02` -> 2048 B, Nozzle `0x02` -> 2048 B, E `0xC0` -> 256 B, X/Y `0xE0` -> 128 B, CFS `0xE0` -> 128 B;
- exact 1.1.6.7.2 transfer geometry derived offline from live tokens + manifest sizes: Main 16 chunks, Nozzle 16, E 455, X/Y 910 each, CFS 1368 full chunks; no write path enabled;
- E's live 256-byte sector result exactly matches Jacob's prior 256-byte override;
- host-side write-preparation boundary resolved: Main/Nozzle/E first mutate at `01 FE`; X/Y first mutate at `F0/01` and receive no `F0/06`; CFS alone receives explicit `F0/06` before `F0/01`;
- next gated work is device-internal preparation/erase semantics, post-write verification and interrupted-write recovery, not firmware write enablement;
- exact 1.1.6.7.2 live-loader target resolution: Main/Nozzle already match; X/Y `mot2_023_C30` -> `mot2_002_081`, E `mot2_022_C30` -> `mot2_002_081`, CFS `cfs0_050_G32` -> `cfs0_000_150`; all write gates remain closed;
- restore verification tightened: one Y runtime-address probe initially timed out after F0/02 and recovered through the normal motor-control retry path, proving that loader ACK must be followed by application-runtime verification;
- multi-device architecture exposed by `k2fw device-matrix`;
- implement remaining frame codecs with unit tests and captured fixtures;
- stock CFS/Box reset orchestration recovered from both compared `upgrade-server` generations: stop Klipper -> run byte-identical `mcu_reset.sh` -> `CFS=1 /etc/init.d/mcu_update start` -> inspect `/tmp/.485_mcu_version`;
- `mcu_reset.sh` recovered as GPIO 140 / PE12 `MCU_PWR_EN`: 1=power off, 0=power on, default reset is two-second power-off then power-on; electrical rail fan-out remains unproven;
- host “mcu upgrade” separated from serial/RS-485 paths: it is an SWD mechanism using `echo 1 > /sys/devices/platform/swd/swd_update` and `cat /sys/devices/platform/swd/update_progress`;
- verify the electrical scope and recovery effect of GPIO 140 on recoverable hardware before treating stock power-cycle orchestration as a writable recovery path;
- identify any remaining proven recovery/startup commands for interrupted updates.

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