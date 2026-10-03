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

Manifest comparison is also non-authoritative for flashing. `--manifest` only compares an operator-selected manifest with the live evidence already available. Package provenance may resolve a filename without proving the running bootloader identity, while application-only motor/CFS matches remain hardware-unresolved. The comparator never promotes these observations into a flash decision.

The stock updater's `F0/00` command is documented as protocol evidence but is not exposed as the normal runtime motor probe. A live application-mode motor test produced no response, so `k2fw status` deliberately uses the validated parameter read instead.

For CFS 1.1.3, bounded `F0/00` probes with both tested headers returned `INVALID_PARAM`. Stock exact-identity discovery proceeds through A1/A0 address management; because A0 changes bus address state, the read-only tooling does not reproduce it. Future CFS write support must obtain the exact boot/hardware variant from a non-mutating source or require explicit, independently verified target provenance.

## Interrupted RS-485 update risk

Static recovery now shows that a stock RS-485 target reaches `update_end` only when the `app_data` receive handler sees `DONE`. If transfer exits before that transition, `mcu_util_485` marks the device update as failed and the later `start_app` loop skips that device. This makes proven updater re-entry/recovery mandatory before K2-OpenHost can expose any RS-485 write command.

## Repository contents

Do not commit Creality `.bin`, `.so`, OTA images, serial numbers or device-specific secrets. Commit only independently written code, documentation, non-sensitive version metadata and cryptographic hashes.

## Offline update inspection

`k2fw inspect-update` is intentionally disconnected from the serial transport. It accepts only an exact CFS firmware image, can render the recovered fixed control-frame bytes offline, and has no code path that opens `/dev/ttyUSB2` or sends those frames. Chunk sizing remains unresolved unless a trusted previously captured `F0/03` sector token is provided explicitly. Its output always keeps `serial_io_performed=false`, `write_enabled=false`, `send_enabled=false` and `flash_allowed=false`.

## CFS application / loader boundary

The analysed `cfs0` application images are linked at `0x08010000`, leaving 64 KiB below the application region. The stock `mcu_util_485` update protocol does not transmit a host-selected flash destination address, so erase/write placement is controlled by the peripheral loader. This is strong evidence of an application/loader separation, but it is not proof that the loader always survives an interrupted erase/write. Hardware recovery validation is still required before CFS writes can be enabled.