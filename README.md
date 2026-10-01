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

This makes firmware-generation differences a credible explanation for protocol differences observed between older K2 Pro hardware and integrations developed against newer CFS firmware. It does **not** by itself prove which individual protocol fields changed; that still requires wire-level or binary comparison.

## Current scope

The first implementation provides a safe firmware-tree scanner and manifest comparer. It does not contain a flash command yet.

```bash
python -m k2fw scan /path/to/usr/share/klipper/fw
python -m k2fw compare old-manifest.json new-manifest.json
```

See `docs/STOCK_UPDATE_PATH.md` for the recovered stock update flow and `docs/SAFETY.md` for the validation gates required before write support is enabled.

## Project relationship

This repository is part of the K2-OpenHost project and is separate from the Kalico, Mainsail and Cartographer forks. Original Creality firmware remains Creality software; this repository stores only independently written tooling, documentation, hashes and metadata derived from user-supplied images.
