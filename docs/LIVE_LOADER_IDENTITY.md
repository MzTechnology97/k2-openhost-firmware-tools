# Live K2 Pro loader identity probe

On 2026-10-04 the development K2 Pro was probed during a guarded hardware power-cycle of the stock T113 `GPIO140 / MCU_PWR_EN` rail.

The probe was deliberately non-flash. It contained no RS-485 `F0/01`, no `F0/06`, no firmware length/data transfer, and no P2P `01 FE`. Sensitive device identifiers are omitted from repository evidence.

## Validated entry sequence

```text
printer ready + standby + heater targets 0
stop Klipper
stop T113 ttyGS<->ttyS bridge processes
GPIO140 = 1
wait 1 s
GPIO140 = 0
wait 1 s
probe T113 physical UARTs
restore applications
restore bridges
restart/FIRMWARE_RESTART Klipper
verify runtime state
```

This validates GPIO140 power-cycle as a common loader-entry mechanism for the K2 Pro peripherals below.

## Live loader identities

| Role | Hardware | Application | Loader transport |
| --- | --- | --- | --- |
| Main | `mcu0_120_G32` | `mcu0_001_000` | P2P ttyS2 @ 115200 |
| Nozzle | `noz0_130_G30` | `noz0_021_000` | P2P ttyS3 @ 115200 |
| Extruder E | `mot2_022_C30` | `mot2_002_071` | P2P through Nozzle transparent mode |
| X/Y motors | `mot2_023_C30` | `mot2_002_071` | RS-485 A1/A0/F0, two devices |
| CFS | `cfs0_050_G32` | `cfs0_000_113` | RS-485 A1/A0/F0 |

No belt or RFID loader device was observed.

The X/Y versus E distinction is important: runtime application fingerprints are identical, but the loader hardware targets are not.

## Exact 1.1.6.7.2 targets

The live identities resolve unambiguously against the extracted K2 Pro `1.1.6.7.2` manifest:

```text
Main    mcu0_120_G32  mcu0_001_000 -> mcu0_001_000  no application change
Nozzle  noz0_130_G30  noz0_021_000 -> noz0_021_000  no application change
X/Y     mot2_023_C30  mot2_002_071 -> mot2_002_081  application differs
E       mot2_022_C30  mot2_002_071 -> mot2_002_081  application differs
CFS     cfs0_050_G32  cfs0_000_113 -> cfs0_000_150  application differs
```

This is exact target resolution, not flash authorization. `flash_allowed=false` remains mandatory.

## Live sector/chunk metadata

A second guarded non-flash probe added only the read-only sector queries `03 FC` and `F0/03`:

| Role | Sector token | Signed | Stock chunk |
| --- | ---: | ---: | ---: |
| Main | `0x02` | `+2` | 2048 B |
| Nozzle | `0x02` | `+2` | 2048 B |
| Extruder E | `0xC0` | `-64` | 256 B |
| X/Y motors | `0xE0` / `0xE0` | `-32` | 128 B |
| CFS | `0xE0` | `-32` | 128 B |

The E result is particularly useful: the live `0xC0` token resolves to exactly **256 bytes**, independently matching Jacob's 256-byte extruder chunk override.

No update request, erase, application length or firmware data was sent during this probe.

### Host-side write-preparation boundary

The host sequences are now resolved up to the first mutating command:

```text
Main / Nozzle / E:
03 FC   read sector
01 FE   first mutating update-request
(no separate host erase command)

X/Y:
F0/03   read sector
F0/01   first mutating update-request
(no F0/06)

CFS:
F0/03   read sector
F0/06   explicit erase
F0/01   update-request
```

This identifies the host-side boundary, but it does not reveal what erase/preparation the Main/Nozzle/E/X/Y loaders perform internally after `01 FE` / `F0/01`.

## Restore behavior

Main and Nozzle returned successful `02 FD` start-app ACKs. Both RS-485 motors and CFS returned successful `F0/02` ACKs; the already validated CFS `0B/01` fallback was also sent.

One Y runtime-address probe timed out immediately after restore. Y was no longer answering as a loader at its temporary address, and the normal `motor_control` retry subsequently recovered the application address. Final state:

```text
Klipper: ready
print: standby
motor_control.motor_ready: true
serial485_transport_ready: true
nozzle_transport_ready: true
CFS: IDLE / OK
heater targets: 0
GPIO140: 0
```

Therefore a future production probe must verify application-level readiness in addition to a loader start-app ACK.

## Remaining write gates

Still not validated:

- device-internal erase/preparation behavior triggered by `01 FE` / `F0/01`;
- post-write verification for Main/Nozzle/E/X/Y;
- interrupted-write device-side recovery;
- any actual erase or firmware write.

No flash command is enabled.

## Exact transfer geometry for 1.1.6.7.2

Using the live sector tokens above and the exact extracted target sizes:

| Role | Target bytes | Chunk | Chunks | Tail | Update needed |
| --- | ---: | ---: | ---: | ---: | --- |
| Main | 30,948 | 2,048 | 16 | 228 | no |
| Nozzle | 30,872 | 2,048 | 16 | 152 | no |
| Extruder E | 116,412 | 256 | 455 | 188 | yes |
| X/Y (each) | 116,396 | 128 | 910 | 44 | yes |
| CFS | 175,104 | 128 | 1,368 | 128 | yes |

For CFS the final chunk is a full 128-byte chunk, so the transfer has no partial tail. These numbers describe transfer geometry only; they do not authorize or execute a write. `flash_allowed=false` remains mandatory.