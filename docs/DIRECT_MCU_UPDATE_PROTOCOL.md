# Stock direct-MCU update protocol recovery

This document records static recovery of Creality `mcu_util` from the K2 Pro host releases `1.1.0.94` and `1.1.6.7.2`.

The path applies to the direct serial controllers used by the K2 Pro Main MCU and Nozzle MCU. No command described here was sent to the development printer while recovering this sequence.

## Stock command-line lifecycle

The stock `mcu_update` service invokes `mcu_util` as separate processes:

```text
-c                 handshake only
-g                 get version; requires prior handshake
-u -f firmware.bin update firmware; auto-start application on success
-u -f firmware.bin -n
                   update without final application start
-s                 start application only; requires prior handshake
-t                 enter transparent mode
-e                 exit transparent mode
```

The newer utility adds `-d/--delay`, microseconds between transmitted bytes. The older utility has no pacing option.

## Boot-transition fingerprint in the F012 images

Both analysed F012 direct-MCU images contain exact 64-bit constants from the CanBoot/Katapult boot-transition ABI:

| Constant | Value | Main offset | Nozzle offset |
| --- | --- | ---: | ---: |
| `CANBOOT_SIGNATURE` | `0x21746f6f426e6143` (`CanBoot!`) | `0x3E0` | `0x3E0` |
| `REQUEST_START_APP` | `0x7b06ec45a9a8243d` | `0x3E8` | `0x3E8` |
| `REQUEST_CANBOOT` | `0x5984e3fa6ca1589b` | absent | absent |

Upstream Katapult uses the signature in its Cortex-M boot entry and `REQUEST_START_APP` to request a reset into the application. Exact byte-for-byte presence of those constants proves reuse of that boot-transition ABI/primitives in the Creality images.

It does **not** prove that the stock direct serial protocol is the upstream Katapult wire protocol: Creality's host still uses the independently recovered `mcu_util` command/checksum state machine below, and `REQUEST_CANBOOT` is not present in the analysed F012 images.

`k2fw inspect-mcu-update` reports this fingerprint offline; it does not enter the loader.

## Checksum

Apart from the one-byte handshake, direct protocol transmissions append the one's-complement of the low eight bits of the byte sum:

```text
checksum = ~sum(payload_bytes) & 0xff
```

This gives the fixed command pairs below.
## Fixed commands

| Operation | Payload + checksum |
| --- | --- |
| handshake | `75` |
| get version | `00 ff` |
| update request | `01 fe` |
| start application | `02 fd` |
| get sector size | `03 fc` |
| enter transparent | `04 fb` |
| exit transparent | `05 fa` |

The command/checksum bytes therefore sum to `0xff`.

## Recovered update sequence

The sender/receiver state machines in both analysed generations recover the same core flow:

| Sender state | Stage | Transmission | Expected response |
| ---: | --- | --- | --- |
| 1 | handshake | `75` | `75` |
| 7 | get version | `00 ff` | 25-byte hardware/application identity + checksum |
| 9 | get sector size | `03 fc` | one sector-token byte + checksum |
| 11 | update request | `01 fe` | `ACK (75)` + checksum |
| 13 | application length | little-endian uint32 length + checksum | `ACK (75)` + checksum |
| 15 | application data | raw firmware chunk + checksum | nonterminal ACK, `DONE (20)`, `NACK (1f)` or `FAIL (21)` |
| 17 | start application | `02 fd` | `ACK (75)` + checksum |

The stock service performs handshake/version comparison before starting the `-u` process, so the update invocation itself begins at get-sector-size rather than re-sending the handshake/version commands.
## Sector token and direct-MCU chunk size

The get-sector-size response byte is loaded with `LDRSB`, so it is signed. Both generations compute the file-read size as:

```text
signed_token = int8(sector_token)

if signed_token == 0:
    invalid
elif signed_token > 0:
    chunk_size = signed_token * 1024
else:
    chunk_size = abs(signed_token) * 4
```

The checked read buffer is `0x4400` bytes. The offline inspector therefore rejects a supplied token whose derived read size exceeds that buffer.

The development K2 Pro has now been queried in a guarded non-flash loader probe. Main and Nozzle both return sector token `0x02` (signed `+2`), which resolves the stock direct-MCU chunk size to **2048 bytes**. The tunneled Extruder E returns `0xC0` (signed `-64`), which resolves to **256 bytes**. That exactly matches Jacob's previously hard-coded 256-byte E override, so the override is now independently explained by the live K2 Pro loader token.

`k2fw inspect-mcu-update` remains offline-only: it still requires an explicit sector token when used to calculate chunking and does not itself enter the loader or perform serial I/O.

## Data response behavior

The application-data confirmation validates its checksum first. With a valid response:

- `0x20 DONE` ends data transfer and moves to start-app unless `--no-startup` was requested;
- `0x1f NACK` enters the retry path;
- `0x21 FAIL` enters the error path;
- another valid nonterminal response continues with the next firmware chunk. The stock ecosystem uses `0x75 ACK` as the success acknowledgement in the surrounding states.

A checksum failure follows the same retry path as NACK.
## Retry behavior differs from a simple chunk retry

The retry path during application-data transfer is important:

1. increment the data retry counter;
2. while it is below three, set the retry-update flag;
3. return to `update_request`;
4. the sender executes `lseek(firmware_fd, 0, SEEK_SET)`;
5. transmit the update request again and restart the image from offset zero.

So a bad data confirmation does **not** merely resend the current chunk. The host starts the firmware transfer over from the beginning.

After three failed data retry cycles, or after an explicit `0x21 FAIL`, the utility enters its error path.

Other stages have their own validation/retry behavior. Version and sector-size checksum errors are retried, application-length confirmation can be retransmitted, and start-app confirmation is retried. The receive loop also terminates after three consecutive one-second select timeouts.

## Old vs. new utility

The recovered protocol semantics are equivalent between the two K2 Pro host releases.

The material transport difference is the new `-d/--delay` option:

- old utility: one `write()` for the current command/data buffer;
- new utility with delay 0: same behavior;
- new utility with delay > 0: one-byte `write()` calls separated by `usleep(delay)`.

This changes pacing, not the command/state sequence.

## Offline inspector

`k2fw inspect-mcu-update` renders this sequence without opening a serial device:

```bash
python -m k2fw inspect-mcu-update \
  /path/to/mcu0_120_G32-mcu0_001_000.bin
```

If a sector token was independently captured:

```bash
python -m k2fw inspect-mcu-update \
  /path/to/noz0_130_G30-noz0_021_000.bin \
  --sector-token 0x04
```
For the 30948-byte F012 Main image, the application-length payload is:

```text
size       0x000078e4
LE payload e4 78 00 00
checksum   a3
wire bytes e4 78 00 00 a3
```

The inspector never emits a serial writer and always reports:

```text
serial_io_performed: false
write_enabled: false
send_enabled: false
flash_allowed: false
```

It deliberately does not enter the loader, erase flash or generate a runnable flashing plan. Real K2 Pro sector tokens have now been captured separately by the guarded maintenance probe.

## Remaining direct-MCU gates

Before any Main/Nozzle write path can be considered:

- obtain or independently confirm the live loader hardware/application identity;
- sector token/chunk sizing: **hardware-validated** (`Main=0x02/2048`, `Nozzle=0x02/2048`, `E=0xC0/256`);
- prove loader re-entry after an interrupted erase/write;
- prove whether failed application data always leaves the controller reachable;
- verify the direct protocol on sacrificial/recoverable hardware;
- keep Main and Nozzle target/recovery validation independent.

Until then, the direct state machine is inspection/test infrastructure only.