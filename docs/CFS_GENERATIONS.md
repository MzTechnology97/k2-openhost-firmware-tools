# K2 Pro CFS firmware generations

## Confirmed old/new application revisions

The compared K2 Pro stock images contain different CFS application firmware generations:

| K2 Pro host release | CFS boot variants | CFS application | Primary image size |
| --- | --- | --- | ---: |
| 1.1.0.94 | `cfs0_050_G30`, `cfs0_050_G32` | `cfs0_000_113` | 151724 B |
| 1.1.6.7.2 | `cfs0_050_G30`, `cfs0_050_G32` | `cfs0_000_150` | 175104 B |

The newer package also contains the separate `cfs6_100_G31-cfs6_220_000` target.

A read-only live `VERSION_SN` query on the K2-OpenHost development K2 Pro reports firmware **1.1.3**, matching the `cfs0_000_113` generation contained in stock host firmware 1.1.0.94. The query was performed over the CM5 `/dev/ttyUSB2` RS-485 bridge with Klipper stopped so the bus had a single owner. No write/update command was sent.

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

## What is not yet proven

The evidence above does not yet identify which bytes in the K2 Pro `HARDWARE_STATUS` response represent temperature and relative humidity. The old CFS responds to the read-only hardware-status opcode, but field decoding remains pending. We will not guess those offsets.

The next protocol step is to recover or capture the stock `communication_get_hardware_status` field mapping for both CFS generations and then add a version-aware decoder to K2-OpenHost.
