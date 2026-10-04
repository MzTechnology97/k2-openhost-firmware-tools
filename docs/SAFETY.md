# Safety model

Peripheral firmware updates can leave the printer unable to communicate with a controller if power, transport or target selection is wrong. K2-OpenHost therefore treats flashing as a staged capability rather than a normal update-manager action.

## Write support is gated

The repository currently provides only read-only inventory/comparison tooling. A future `flash` command must not be enabled until all of the following are implemented and hardware-tested:

1. positive identification of printer model/board and the exact target device;
2. read-only query of the running boot/application version before any erase/write;
3. SHA-256 manifest for the candidate image and target compatibility check;
4. exclusive ownership of the UART/RS-485 transport — Klipper and any competing bridge consumer must be stopped or quiesced;
5. stable power and an explicit operator confirmation naming target, current version and target version;
6. post-write version verification and application-start verification;
7. a documented recovery route for each device class.

## Never infer a target from file order

Creality firmware trees contain multiple variants. Selection must use the hardware identifier reported by the device and the hardware token embedded in the stock filename/manifest. `mot0`, `mot1` and `mot2` names alone are not sufficient evidence of axis mapping.

## No automatic system OTA

This project does not replace the T113 system/rootfs automatically. Its purpose is to make peripheral firmware state visible and, later, allow controlled peripheral updates without coupling them to a full host firmware upgrade.

## Bus safety

The K2 RS-485 bus is shared by closed-loop motors and CFS-related devices. Direct serial probing requires exclusive ownership of the CM5 `/dev/ttyUSB2` transport and must never race the normal Kalico RS-485 driver.

The validated X/Y/E runtime fingerprint does **not** open `/dev/ttyUSB2` directly. It asks the existing Kalico `motor_control` object to perform a normal application-level `FLASH_PARAM` read of parameter id 0, including E through the Nozzle MCU transparent transport. The tool refuses this query while homing, printing or paused.

The direct Main/Nozzle `mcu_util` identity command is also excluded from runtime probing. Its `00 FF` version request follows a loader handshake and stock `mcu_update` explicitly starts the application afterward. `k2fw status` may report the unique F012 package target for each role, but it marks that target `runtime_verified=false` and never presents it as a live bootloader read.

Manifest comparison is also non-authoritative for flashing. `--manifest` only compares an operator-selected manifest with the live evidence already available. Application-only motor/CFS matches remain hardware-unresolved; a separately validated `loader_identity` may resolve an exact artifact and `update_required`, but it still never enables writes or `flash_allowed`.

The stock updater's `F0/00` command is documented as protocol evidence but is not exposed as the normal runtime motor probe. A live application-mode motor test produced no response, so `k2fw status` deliberately uses the validated parameter read instead.

For CFS 1.1.3, bounded `F0/00` probes with both tested headers returned `INVALID_PARAM`. Stock exact-identity discovery proceeds through A1/A0 address management; because A0 changes bus address state, the read-only tooling does not reproduce it. Future CFS write support must obtain the exact boot/hardware variant from a non-mutating source or require explicit, independently verified target provenance.

## Flash preflight

`python -m k2fw preflight --port <path> [--port <path> ...]` is a read-only precondition check. It answers one question: is the printer in a state where flashing may be considered? It does **not** prove that an image fits the hardware, and it does not enable any write: `flash_allowed` and the write gates above are unchanged.

`safe_for_flash` is true only when every fact is known and good:

| Check | Pass | Fail | Unknown (blocks too) |
| --- | --- | --- | --- |
| `machine_idle` | `print_stats.state` is `standby`, `complete`, `cancelled` or `error` | `printing` or `paused` | `print_stats` or its state missing, not a string, or any other value |
| `heaters_off` | `extruder`, `heater_bed` and `heater_generic chamber_heater` all have a finite target of 0 | a target above 0 | an object or target missing, `null`, a string, a boolean, NaN, infinity or a negative number |
| `serial_exclusive` | every `--port` exists and no process holds it, with every `/proc/<pid>/fd` inspected | a process holds a port | no `--port` given, a port missing, or a process that could not be inspected (run as root) |

The idle states follow Klipper's `print_stats`. `error` is included because it is the state a print is left in after it failed, with the job already ended.

If Moonraker cannot be read, the reason is kept: `moonraker_timeout`, `moonraker_unreachable`, `moonraker_http_error` (for example Klippy shut down) or `moonraker_malformed`. An unreachable Moonraker is never read as an idle printer.

The JSON (`schema: 2`) has:
- `checks`, with `pass`, `fail` or `unknown` for each check;
- `blockers`, a list of `{check, code, detail}`;
- `ports`, keyed by the path you gave, with the resolved `device`, `owners` and whether the scan was `complete`.

The exit code is 0 only when `safe_for_flash` is true, and 3 otherwise.

**Port names:** pass ports by persistent name (`/dev/serial/by-id/...`, or `/dev/serial/by-path/...`). The check follows the link to today's device instead of assuming that `ttyUSB0/1/2` keep their numbers.

**Klipper running:** the preflight blocks with `port_busy`, because Klippy owns the gadget ports. That is the expected answer.

## Stock power/reset action is not a read-only primitive

Both compared stock OTA servers stop Klipper and invoke `/usr/bin/mcu_reset.sh` before the CFS-specific `mcu_update` pass. That script drives GPIO 140 / PE12 (`MCU_PWR_EN`) high for two seconds (power off) and then low (power on). It is a physical power-cycle, not an identity/status query.

K2-OpenHost still never calls `mcu_reset.sh` from ordinary `status` or the offline inspectors. A separately guarded maintenance probe has now hardware-validated the GPIO140 power-cycle as loader entry for Main, Nozzle, E, X/Y and CFS. This remains a state-changing maintenance operation, not a normal read-only status primitive. See `LIVE_LOADER_IDENTITY.md` and `STOCK_RESET_ORCHESTRATION.md`.

## Interrupted RS-485 update risk

Static recovery now shows that a stock RS-485 target reaches `update_end` only when the `app_data` receive handler sees `DONE`. If transfer exits before that transition, `mcu_util_485` marks the device update as failed and the later `start_app` loop skips that device. This makes proven updater re-entry/recovery mandatory before K2-OpenHost can expose any RS-485 write command.

## Repository contents

Do not commit Creality `.bin`, `.so`, OTA images, serial numbers or device-specific secrets. Commit only independently written code, documentation, non-sensitive version metadata and cryptographic hashes.

## Offline update inspection

`k2fw inspect-update` is intentionally disconnected from the serial transport. It accepts only an exact CFS firmware image, can render the recovered fixed control-frame bytes offline, and has no code path that opens `/dev/ttyUSB2` or sends those frames. Chunk sizing remains unresolved unless a trusted previously captured `F0/03` sector token is provided explicitly. Its output always keeps `serial_io_performed=false`, `write_enabled=false`, `send_enabled=false` and `flash_allowed=false`.

`k2fw inspect-mcu-update` follows the same rule for Main/Nozzle images. It renders the recovered direct-loader control bytes and checksum logic, but contains no serial writer and never performs the `0x75` loader handshake. A sector token may be supplied only for offline arithmetic; the tool does not query one from the printer. Its output also permanently keeps `serial_io_performed=false`, `write_enabled=false`, `send_enabled=false` and `flash_allowed=false`.

## CFS application / loader boundary

The analysed `cfs0` application images are linked at `0x08010000`, leaving 64 KiB below the application region. The stock `mcu_util_485` update protocol does not transmit a host-selected flash destination address, so erase/write placement is controlled by the peripheral loader. This is strong evidence of an application/loader separation, but it is not proof that the loader always survives an interrupted erase/write. Hardware recovery validation is still required before CFS writes can be enabled.

## CFS loader probe classification

The loader identity/sector workflow is **non-flash but state-changing**. Entering loader mode, A0 address assignment, and returning to the application alter runtime state even though they do not erase/program application flash. `k2fw inspect-cfs-loader-probe` renders the sequence offline, while the guarded live implementation enforces exclusive RS-485 ownership, explicit single-CFS/state-change/printer-safe acknowledgements, automatic application restore, post-restore A2 verification, and a hard TX allowlist that rejects `F0/06`, `F0/01`, application length and application-data frames. It has been hardware-validated on the development CFS without erase/write; post-`F0/02` A2 verification and the `0B/01` fallback are mandatory because an ACK alone did not prove application takeover.

## Motor and Toolhead loader gates

GPIO140 hardware power-cycle has now been validated as a common loader-entry mechanism on the development K2 Pro. Two X/Y-class RS-485 motors answer A1 group `0xFD` in `mode=1` and identify as `mot2_023_C30-mot2_002_071`. E identifies separately as `mot2_022_C30-mot2_002_071` through Nozzle P2P transparent mode. Main and Nozzle also answer the direct P2P loader identity query after the same power-cycle.

Loader entry, exact identity and read-only sector/chunk metadata are now hardware-validated for Main, Nozzle, E, X/Y and CFS. Main/Nozzle return `0x02` -> 2048-byte chunks, E returns `0xC0` -> 256 bytes, and X/Y/CFS return `0xE0` -> 128 bytes. These reads are non-flash but still occur inside a state-changing maintenance workflow.

The **write/recovery gates remain closed**. For Main/Nozzle/E, `01 FE` is the first mutating command after the sector read; for X/Y it is `F0/01`; motors do not receive `F0/06`. Device-internal erase/preparation behavior after those update requests and interrupted-write recovery remain unproven.

Application restore must be verified beyond the ACK. During the validated probe both X/Y returned `F0/02` ACK; one Y runtime address probe initially timed out, then the normal motor-control retry path recovered and `motor_ready=true`. CFS similarly retains its stronger A2/`0B/01` verification requirement.


Transfer geometry may now be calculated exactly from the live sector tokens and verified manifest sizes, but this is still offline arithmetic. Chunk counts/tails must never be treated as authorization to send `01 FE`, `F0/01`, `F0/06`, application length or firmware data.

No firmware write is enabled.