# Recovered Creality peripheral update path

This document records the stock K2 Pro update behaviour recovered from user-supplied Creality firmware images. The binaries were inspected statically; they were not executed during this analysis.

Compared stock images:

- K2 Pro `1.1.0.94`
- K2 Pro `1.1.6.7.2`

## Stock orchestrator

Both releases contain `/etc/init.d/mcu_update`. The scripts are functionally identical for the K2 Pro update path; the newer copy only extends the set of product model names that reuse the `F012` firmware directory.

For the K2-class board IDs, the script assigns:

```text
mcu0_serial=/dev/ttyS2
bed0_serial=/dev/ttyS4
noz0_serial=/dev/ttyS3
rs485_serial=/dev/ttyS5
```

For model `F012` (K2 Pro), it selects `fw_dir=F012`, skips `bed0`, and enables the extruder/RS-485 update phase.

## Direct MCU updater

Stock utility: `/usr/bin/mcu_util`

The init script uses these operations:

```text
mcu_util -i <tty> -c                 handshake
mcu_util -i <tty> -g                 get version
mcu_util -i <tty> -s                 start application
mcu_util -i <tty> -u -f <firmware>   update and start
mcu_util -i <tty> -u -f <firmware> -n update without startup
mcu_util -i <nozzle tty> -t           enter transparent mode
mcu_util -i <nozzle tty> -e           exit transparent mode
```

Static decompilation confirms that the stock direct-MCU version request transmits bytes `00 ff`. The receive path expects 26 bytes: a 25-byte combined hardware/application identity followed by the utility's one-byte checksum. This is part of the stock updater/bootloader protocol; K2-OpenHost does not force Main or Nozzle into bootloader mode merely to obtain a live status report.

Static strings in the utility show a staged update protocol including `update_request`, sector-size confirmation, update start, application-length confirmation and application-data transfer.

The stock shell code compares the version returned by the device with the one matching `.bin` in the selected firmware directory and only flashes when the application revision differs, unless a force flag is used.

## RS-485 updater

Stock utility: `/usr/bin/mcu_util_485`

The K2 Pro script invokes it on `/dev/ttyS5` at 230400 baud. Static strings identify support for:

- motors;
- CFS;
- belt devices;
- RFID devices;
- address discovery/assignment;
- version reads;
- private-flash erase;
- update request/data/end stages.

Observed command-line interface from the binary:

```text
-i, --port       serial port
-f, --force      force update all MCUs
-b, --baud       RS-485 baud rate
-c, --broadcast  broadcast/discover all devices
-d, --dir        machine firmware base directory
-j, --json       CFS update JSON file
```

The stock script first performs a broadcast pass and then an update pass using the model firmware directory. Static decompilation of both `1.1.0.94` and `1.1.6.7.2` shows the same updater-stage version transaction after discovery/address handling: RS-485 header byte `0x00`, function `0xF0`, one-byte payload `0x00`, with a 500 ms timeout. The binary labels the failure path `get version from slave`. Later stages reuse function `0xF0` with other payloads, including `0x03` and `0x06`; those stages are intentionally not exposed by the read-only tooling.

A normal-application test of `F0/00` against an X motor produced no response. Therefore it is treated as an **updater-stage** command, not as the live runtime version API. Live X/Y/E identification instead uses the application `FLASH_PARAM` read of parameter id 0.

During a CFS-targeted OTA, `upgrade-server` creates `/tmp/cfs_update.json` and starts the service with `CFS=1`, causing `mcu_update` to add `-j /tmp/cfs_update.json`.

## OTA server evidence

Static strings in `/usr/bin/upgrade-server` include:

```text
check mcu upgrade
start mcu upgrade ...
check box upgrade
start box upgrade ...
/tmp/cfs_update.json
CFS=1 /etc/init.d/mcu_update start
/tmp/.485_mcu_version
/usr/bin/mcu_reset.sh
```

The same binary also contains an SWD path for a host MCU (`/sys/devices/platform/swd/swd_update`). That path must not be conflated with the serial `mcu_util` path until the exact target and update conditions are mapped.

## K2-OpenHost implication

The CM5 receives the corresponding K2 transports through the T113 bridge:

```text
stock T113 /dev/ttyS2 -> CM5 /dev/ttyUSB0
stock T113 /dev/ttyS3 -> CM5 /dev/ttyUSB1
stock T113 /dev/ttyS5 -> CM5 /dev/ttyUSB2
```

This makes a native K2-OpenHost updater technically feasible. The preferred implementation is a clean, host-native protocol implementation rather than blindly executing the stock ARMv7 utilities on the CM5.

Before write support is enabled, the project will reproduce read-only discovery/version queries and capture the exact update frames used by the stock utilities.
