# K2 firmware-device architecture

K2-OpenHost firmware tooling is not CFS-specific. Static analysis of the stock F012 updater shows two distinct backends.

## RS-485 peripheral backend

`mcu_util_485` handles multiple RS-485 device families with the same discovery/address/version/sector/update/start state machine.

| family | type | A1 group | version | sector | explicit erase | update | startup |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| motor | 2 | `0xFD` | `F0/00` | `F0/03` | no | `F0/01` + length/data | `F0/02` |
| belt | 3 | `0xFC` | `F0/00` | `F0/03` | no | shared F0 path | `F0/02` |
| RFID | 4 | `0xFB` | `F0/00` | `F0/03` | no | shared F0 path | `F0/02` |
| CFS | 1 | `0xFE` | `F0/00` | `F0/03` | `F0/06` | `F0/01` + length/data | `F0/02` |
| CFS Pro | 10 | `0xFE` | `F0/00` | `F0/03` | `F0/06` | shared F0 path | `F0/02` |

The important motor difference is that stock `mcu_util_485` does not send `F0/06` erase to device type 2. It still sends `F0/01`, application length, application data and `F0/02`. The exact motor-side erase/preparation policy therefore remains unresolved and must not be guessed.

## Motor evidence

The K2 Pro motor images are WCH CH32V30x / QingKe RISC-V firmware.

- 071 fingerprint: `flash_param_version=0x0247` (583), app token `mot2_002_071`.
- 081 fingerprint: `flash_param_version=0x024B` (587), app token `mot2_002_081`.
- Live X/Y/E all report 583, therefore all three currently run the analysed 071 generation.
- Read-only live X/Y/E `boot_key` is 17030 (`0x4286`) in RAM and flash.
- Read-only live X/Y/E `system_startup_delay_ms` is 100 ms in RAM and flash.
- Both 071 and 081 expose `boot_key`, a reboot command and flash-related strings.

This supports an application/boot coordination mechanism, but does not prove that writing `boot_key=0x4286` enters the loader. No boot-key write or motor reboot has been performed.

The motor package name separates hardware/loader and application identities, e.g. `mot0_022_C30-mot2_002_081.bin`. The application token is embedded at offset `0x200`; the `mot0_022_C30` hardware token is not embedded in the image. Unlike CFS, the image has no obvious lower-flash application gap.

CH32V30x silicon has manufacturer System FLASH/BOOT memory separate from Code FLASH, but there is no evidence yet that Creality's RS-485 `F0` loader lives there.

## Stock motor topology

F012 stock `mcu_update` enters nozzle transparent mode, runs `mcu_util_485` to update all RS-485 slave devices, then exits transparent mode. Thus motors and CFS are peers under the stock RS-485 updater.

In K2-OpenHost runtime X/Y use the main `serial_485` transport while E uses the nozzle-MCU transparent transport. Future motor firmware support must share the motor loader protocol but use different host transport adapters.

## Direct Main / Toolhead MCU backend

Main and Toolhead/Nozzle use `mcu_util`, not `mcu_util_485`. Recovered loader sequence:

```text
0x75   handshake
00 FF  loader identity
03 FC  sector size
01 FE  update request
length + one's-complement checksum
data chunks + one's-complement checksum
02 FD  start application
```

The Toolhead/Nozzle MCU also supplies the transparent tunnel used for downstream RS-485 updates.

For F012 the nozzle target is `noz0_130_G30-noz0_021_000.bin`. Its vector table starts at `0x08000000`, reset vector resolves to `0x080033F8`, application token is at offset `0x200`, `CanBoot!` is present at `0x3E0`, and the hardware token `noz0_130_G30` is not embedded in the image. Main follows the same pattern.

The direct loader lifecycle is proven in the stock host, but live loader entry, real sector token and interrupted-update recovery are still hardware-validation gates.

## Tool architecture

```text
k2fw
 +-- runtime inventory: Main, Toolhead, motors X/Y/E, CFS
 +-- direct-MCU loader backend: Main, Toolhead/Nozzle
 +-- RS-485 loader backend: motors, CFS, later belt/RFID/CFS Pro
```

Each family must independently define runtime identity, loader identity, loader entry, sector/chunk semantics, erase policy, update framing, startup verification and interrupted-update recovery.

Current write gates remain closed: CFS loader probing is validated but CFS writes are disabled; motor loader entry/writes are disabled; Main/Toolhead loader entry/writes are disabled.