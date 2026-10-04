# Jacob K2 Plus motor updater reference

This document records behavior recovered from Jacob's unpacked K2 Plus custom-firmware rootfs. It is a reference implementation, not direct proof that every model-specific count, hardware token, or boot path is identical on the K2 Pro.

Source artifact:

```text
/usr/bin/motor_updater.py
SHA-256 0ba8d5fad79029ebbe16b907b0fb06d547d77a693a0265076025c723a52b3d62
```

## Boot orchestration

`motor-updater.service` runs as a oneshot under `sysinit.target`; `klipper.service` starts after it. The updater states that GPIO140 / `MCU_PWR_EN` boots with the rail OFF (`1`). Its default startup enables the rail (`0`) and waits 1.0 second before launching updater workers. `--power-cycle` first turns the rail OFF for 1.0 second; normal power-on then follows and waits another 1.0 second.

This is strong reference evidence for a hardware boot-orchestration model: devices are expected to expose their loaders after power-on, and the updater does not first send an application-side command asking them to enter loader mode.

Do not reinterpret the live K2 Pro `system_startup_delay_ms=100` parameter as a proven loader timeout. The Jacob reference deliberately waits one second after power-on and still expects loader access.

## Three parallel updater paths

After power-on the updater starts three independent workers:

| path | port | baud | role |
| --- | --- | ---: | --- |
| RS-485 | `ttyS5` | 230400 | motors + CFS; belt/RFID discovery/version/start |
| Main P2P | `ttyS2` | 115200 | mainboard MCU |
| Nozzle P2P | `ttyS3` | 115200 | nozzle MCU + extruder via transparent mode |

These bootloader baud rates must not be confused with the 230400 Kalico application-runtime links used by the current K2-OpenHost topology.

## P2P protocol

The custom updater uses:

```text
75        handshake / echo
00 ff     get version
03 fc     get sector
01 fe     update request
<len+cs>  LE32 image length + one's-complement checksum
<data+cs> firmware chunk + one's-complement checksum
02 fd     start application
04 fb     enter Nozzle transparent mode
05 fa     exit Nozzle transparent mode
```

Normal ACK is `75 8a`. A short final data chunk expects `20 df`. For a valid sector response, the reference computes direct-MCU chunk size as `sector_byte * 1024`; the extruder path overrides chunk size to 256 bytes.

## Extruder is not treated like the RS-485 motor path

This is the most important architectural finding from the reference.

The Nozzle worker:

```text
Nozzle 0x75 handshake
04 fb enter transparent
00 ff query Extruder identity
03 fc / 01 fe / length / data for Extruder if needed
05 fa exit transparent
then update/start Nozzle itself
```

The extruder does not use the RS-485 `A1/A0/F0` packet framing in this script. It uses the direct P2P control/checksum protocol through the Nozzle transparent tunnel.

The reference does not issue a separate `0x75` handshake to the extruder after entering transparent mode, and it does not explicitly send `02 fd` start-app to the extruder after an update. Those behaviors are therefore reference facts, not yet fully explained protocol semantics.

For K2-OpenHost this means E must remain a separately gated loader path. The fact that X/Y/E share the same application `flash_param_version` does not prove identical bootloader transport.

## RS-485 reference behavior

The reference assigns:

```text
motor group  0xfd -> temporary addresses from 0x85
belt group   0xfc -> temporary addresses from 0x23
RFID group   0xfb -> temporary addresses from 0x11
CFS group    0xfe -> temporary addresses from 0x01
```

The K2 Plus reference expects 4 motors, 2 belts, 1 RFID and 4 CFS devices. These counts are model-specific and must not replace the independently recovered K2 Pro stock topology.

RS-485 update behavior matches the recovered core model:

```text
F0/00 identity
F0/03 sector token
F0/01 update request
F0 + LE32 image length
F0 + data chunks
F0/02 start application
```

Motors do not receive `F0/06`. CFS devices do. The reference uses the same signed-byte RS-485 chunk-size formula already recovered from stock `mcu_util_485` and retries data chunks up to five times.

## Reference firmware targets

The unpacked K2 Plus rootfs contains:

```text
cfs0_050_G32-cfs0_000_142.bin
mcu0_140_G32-mcu0_022_000.bin
mot2_023_C30-mot2_002_081.bin
noz0_130_G30-noz0_021_000.bin
```

Several identifiers differ from the K2 Pro artifacts already analysed, which is why this rootfs is used as protocol/boot evidence rather than as a K2 Pro target manifest.

## Safety consequence

No write support is enabled from this reference. The useful next hardware experiment on the K2 Pro is a guarded power-cycle/loader observation using the already recovered GPIO140 control plane: stop conflicting services, ensure heaters are off, power-cycle the MCU rail, then probe loader identities only and restore applications. That test remains separately gated.