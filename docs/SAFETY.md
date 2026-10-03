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

The stock updater's `F0/00` command is documented as protocol evidence but is not exposed as the normal runtime motor probe. A live application-mode motor test produced no response, so `k2fw status` deliberately uses the validated parameter read instead.

For CFS 1.1.3, bounded `F0/00` probes with both tested headers returned `INVALID_PARAM`. Stock exact-identity discovery proceeds through A1/A0 address management; because A0 changes bus address state, the read-only tooling does not reproduce it. Future CFS write support must obtain the exact boot/hardware variant from a non-mutating source or require explicit, independently verified target provenance.

## Repository contents

Do not commit Creality `.bin`, `.so`, OTA images, serial numbers or device-specific secrets. Commit only independently written code, documentation, non-sensitive version metadata and cryptographic hashes.