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

The K2 RS-485 bus is shared by closed-loop motors and CFS-related devices. Only one process may own the CM5 `/dev/ttyUSB2` transport at a time. Firmware discovery and update code must serialize requests and must never run concurrently with the normal Kalico RS-485 driver.

## Repository contents

Do not commit Creality `.bin`, `.so`, OTA images, serial numbers or device-specific secrets. Commit only independently written code, documentation, non-sensitive version metadata and cryptographic hashes.
