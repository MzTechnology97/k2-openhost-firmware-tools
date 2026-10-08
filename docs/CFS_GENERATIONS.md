# K2 Pro CFS firmware generations

## Confirmed old/new application revisions

The compared K2 Pro stock images contain different CFS application firmware generations:

| K2 Pro host release | CFS boot variants | CFS application | Primary image size |
| --- | --- | --- | ---: |
| 1.1.0.94 | `cfs0_050_G30`, `cfs0_050_G32` | `cfs0_000_113` | 151724 B |
| 1.1.6.7.2 | `cfs0_050_G30`, `cfs0_050_G32` | `cfs0_000_150` | 175104 B |

The newer package also contains the separate `cfs6_100_G31-cfs6_220_000` target.

A read-only live `VERSION_SN` query on the K2-OpenHost development K2 Pro reports firmware **1.1.3**, matching the `cfs0_000_113` generation contained in stock host firmware 1.1.0.94. The query was performed over the CM5 `/dev/ttyUSB2` RS-485 bridge with Klipper stopped so the bus had a single owner. No write/update command was sent.

The G30 and G32 1.1.3 application images are byte-identical, so application version 1.1.3 cannot distinguish those boot/hardware variants. Two bounded runtime `F0/00` checks at the assigned CFS address returned `INVALID_PARAM`; K2-OpenHost does not reproduce the stock A1/A0 address-management sequence just to obtain a boot token. The exact G30/G32 value therefore remains unknown in live status.

## Wrapper delta

The stock `box_wrapper.cpython-39.so` also changed substantially between the same releases:

```text
1.1.0.94 : 1762164 bytes
1.1.6.7.2: 2303332 bytes
```

Both generations contain the existing hardware-status/environment concepts:

- `BOX_GET_HARDWARE_STATUS`
- `GET_HARDWARE_STATUS`
- `communication_get_hardware_status`
- `temperature`
- `dry_and_humidity`
- humidity sensor error handling

The newer wrapper adds a large dry-box control surface that is absent from the old wrapper, including auto-dry, humidity targets, dry-mode state, pause/continue dry commands, NTC/fan/heater faults and left/right humidity handling.

This is strong evidence that Creality evolved both the CFS application firmware and the host-side Box implementation. It supports treating protocol shape as firmware-generation-dependent rather than assuming the current Jacob/K2 Plus decoder applies unchanged to an older K2 Pro CFS.

## Environment/status semantics clarified

Subsequent K2-OpenHost firmware analysis and live validation separated two protocol concepts that were previously conflated:

- on the development K2 Pro running CFS application **1.1.3**, command `0x0A` returns the four-byte steady state used by the Kalico adapter: signed temperature °C, relative humidity %, event byte and Box state;
- command `0x15` is a separate 16-byte hardware-status/self-test vector. K2-OpenHost keeps that payload as raw diagnostics and does **not** guess temperature/humidity offsets inside it.

This means temperature/humidity are no longer pending for the validated 1.1.3 K2 Pro path; they come from `0x0A`, not from `HARDWARE_STATUS (0x15)`. The exact environment/state layout for newer CFS generations such as application 1.5.0 must still be validated independently before assuming the 1.1.3 layout applies unchanged.
