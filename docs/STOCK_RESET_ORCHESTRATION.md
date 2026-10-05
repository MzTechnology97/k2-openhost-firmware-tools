# Stock reset and loader orchestration

This document separates three update/reset domains observed in the K2 Pro stock host firmware. The distinction matters because similarly named log messages do not refer to the same controller or transport.

Compared host releases:

- K2 Pro `1.1.0.94`
- K2 Pro `1.1.6.7.2`

All findings below come from static analysis of the stock firmware images. No reset, power-cycle, loader entry, erase or flash was performed on the development printer.

## 1. `mcu_reset.sh` is a power-cycle

Both releases contain a byte-identical `/usr/bin/mcu_reset.sh`:

```text
size   1021 bytes
sha256 1c436606d7bcc7b3a8811c623dbc9be7dbe128ee21df00ec177ecc6ee1408d3c
```

The script names GPIO 140 / SoC PE12 as `MCU_PWR_EN` and documents the electrical logic as:

```text
0 = power on
1 = power off
```
With no argument, its default reset path performs:

```text
GPIO 140 -> output
write 1   # power off
sleep 2
write 0   # power on
```

The optional `enable` path sets the rail on; `disable` sets it off and unexports the GPIO.

The exact electrical fan-out of this power-enable rail is not proven by the shell script alone. K2-OpenHost therefore describes it only as the stock MCU power-enable rail and does not infer which individual peripheral loads are switched.

## 2. CFS / Box OTA explicitly uses that power-cycle

Static analysis of both `upgrade-server` generations recovers the same consecutive CFS/Box update commands:

```text
/etc/init.d/klipper stop
/usr/bin/mcu_reset.sh
CFS=1 /etc/init.d/mcu_update start
```

Immediately afterward, the OTA path opens/reads:

```text
/tmp/.485_mcu_version
```

This order is present in both compared releases.
Relevant call-site addresses differ because the binaries differ, but the command order is unchanged:

| Release | Klipper stop | `mcu_reset.sh` | CFS `mcu_update` |
| --- | ---: | ---: | ---: |
| 1.1.0.94 | `0x14fac` | `0x14fb4` | `0x14fbc` |
| 1.1.6.7.2 | `0x13b10` | `0x13b18` | `0x13b20` |

The two `upgrade-server` files have the same size but different hashes:

```text
1.1.0.94  120176 bytes  bc695fd91dabd3993ece896afea0543e7cfa84c0c8eb0c359a05cb597944cd6a
1.1.6.7.2 120176 bytes  b0863d3bc444ccdd040e98369da2f27cb89764e50d0413995256daf48b001727
```

The stable CFS command sequence despite those binary differences is strong evidence that the power-cycle is intentional stock orchestration, not an incidental artifact of one release.

It does **not** prove that a power-cycle by itself selects a specific CFS bootloader variant or that it is sufficient for safe recovery after an interrupted flash.
## 3. The stock “mcu upgrade” branch is a separate SWD path

The same `upgrade-server` contains a different branch whose logging includes:

```text
start mcu upgrade ...
mcu1 SWD upgrade ...
reset host mcu
swd cmd = %s
```

Its command buffer is initialized to:

```text
echo 1 > /sys/devices/platform/swd/swd_update
```

and its progress command is:

```text
cat /sys/devices/platform/swd/update_progress
```

This is a host-MCU SWD update mechanism. It must not be conflated with:

- direct serial Main/Nozzle `mcu_util`;
- RS-485 `mcu_util_485`;
- the CFS/Box power-cycle sequence above.
The “reset host mcu” log appears inside this SWD state machine. Reference analysis does not associate that log with `/usr/bin/mcu_reset.sh`; the SWD branch subsequently re-triggers the SWD command and polls `update_progress`.

## Klipper restart is not yet a proven CFS branch step

Both firmware generations contain the command string:

```text
/etc/init.d/klipper restart
```

The newer binary initializes it into a global command table next to the SWD command strings. However, the recovered CFS/Box call-site contains the stop, power-cycle, CFS update, and version-file checks described above; current reference analysis does not establish a direct `klipper restart` invocation in that branch.

K2-OpenHost therefore does not include restart as a proven CFS recovery step until a concrete call-site is recovered.

## Safety consequence

`mcu_reset.sh` is intentionally excluded from all read-only K2-OpenHost status/probe paths.

A future writable updater may use stock-compatible reset/power sequencing only after the affected rail and recovery behavior are verified on recoverable hardware. Until then:

```text
power_cycle_enabled = false
reset_enabled       = false
loader_entry_enabled = false
flash_allowed       = false
```
## What remains unresolved

For direct Main/Nozzle serial updating, the stock loader protocol is now known, but the mechanism that guarantees the controller is in the loader when `mcu_update` starts is still not fully mapped.

For CFS/RS-485, the stock OTA clearly performs the shared power-cycle before `mcu_update`, but further hardware validation is needed to determine:

- which devices are actually powered by GPIO 140 / PE12;
- whether the CFS comes up in application or loader state after that cycle;
- how the stock updater recovers if power is lost after erase but before `DONE`;
- whether a failed update can always be recovered with the same power-cycle;
- whether Klipper must be restarted explicitly or is restored elsewhere in the full OTA lifecycle.

These remain write-support gates, not assumptions.