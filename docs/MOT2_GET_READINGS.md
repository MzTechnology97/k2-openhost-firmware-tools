# MOT2 GET readings: current, voltage, encoder, tracking error

Research for [#10](https://github.com/MzTechnology97/k2-openhost-firmware-tools/issues/10). Static analysis only:
- no firmware was run or emulated;
- no GET was sent to a controller;
- no index was scanned on the bus.

Microstep/subdivision is out of scope by the project owner's decision; the indices that belong to it are marked and not analysed.

Machine-readable evidence: [`evidence/mot2_get_index_map_2026-10-05.json`](../evidence/mot2_get_index_map_2026-10-05.json). Parser: `k2fw.mot2_get`.

## Sources

| Image (F012) | SHA-256 | GET handler | Command table |
| --- | --- | --- | --- |
| `mot*_022_C30-mot2_002_071.bin` (identical) | `412947fa…6d75` | `0x0000f200` | `0x000060c4` |
| `motor/mot*_021/023_C30-mot2_002_071.bin` (identical) | `a797c95e…8ecd0` | `0x0000f1c4` | `0x00006076` |
| `mot*_022_C30-mot2_002_081.bin` | `67b364a6…b3f7` | `0x000102d0` | `0x000060fc` |
| `motor/mot*_021/023_C30-mot2_002_081.bin` | `92ff3130…5826` | `0x000102a4` | `0x000060b0` |

**Method.** Ghidra with the project's `RISCV:LE:32:QingKe` profile, checked on 44 LLVM XW vectors (see the motor reverse-engineering report). Addresses are RAM addresses with the image linked at `0x3000`. Every statement below can be checked by opening the named function in that image.

**Identity of the command.** The command table registers function code 8 with the handler above, next to `sys_param` (6), `flash_param` (7), `protection` (0x0C) and `rs485_addr` (0x0E). It is the same function code Kalico's `MotorFirmwareClient.get_value` sends.

## How the handler works

- **Request:** one byte, the index.
- **Answer:** four little-endian bytes, the **raw bits** of a firmware field. Depending on the field, they are float32, int32 or uint16 zero-extended.
- **Cases:** indices 0–18 have a case. **There is no default case:** for an index ≥ 19 the handler sends the previous answer unchanged, so an index scanner would mistake stale data for a reading.

The fields live in four objects. In the 071 `mot*_022` image the system object is `0x20001df0`, built by `0x0000af92`:

| System slot | Object | Proof |
| --- | --- | --- |
| +4 | controller `0x20000000` | parameter registry: `pos.kp` at +0xfc, `spd.kp` +0x1c8, `cur.kp` +0x294 |
| +8 | driver board `0x20000968` | registry: `driver_board_power_supply_V` +0x1c, `R_of_current_sample` +0x20, `amp_gain` +0x2c |
| +0xc | encoder `0x20000af8` | count methods `0x5b94`, `0x5c18`, `0x5be4` |
| itself | system object | stall flag, step-pulse input |

### Controller: four PID blocks

From the PID function `0x00009920` (071) / `0x00009a0e` (081), with the gains cross-checked against the parameter registry:
- **Blocks:** position at `0xf4`, speed `0x1c0`, current 1 `0x28c`, current 2 `0x358` (stride `0xcc`). The block at `0x358` gets a copy of the `0x28c` gains.
- **Layout of a block:** +0x08 kp, +0x0c ki, +0x10 kd, +0x14 kc, +0x24 **reference**, +0x28 **feedback**, +0x2c output, +0x30 error.

The stall detector `0x0000b50c` tells the two current loops apart:
- in current mode it compares `|controller+0x37c|`, the current 2 reference, with `stall_cur_A`, so current 2 is the torque (q) loop, in amperes;
- in position mode it compares the position error with `stall_pos_err_rad`;
- either way, on a stall it sets the system flag at +0x38 (071) / +0x40 (081).

### Measurements

- **Phase currents.** The acquisition tick `0x0000b6d2` stores two driver-board results in `controller+0x7c` and `+0x80`:
  - `0x5ede` reads ADC channel 0 and subtracts its offset (the "IaIb value/offset" pair of the text console);
  - `0x5f1a` does the same on channel 1, multiplied by +1.0 or -1.0 from a system flag;
  - `0x5eba` scales both to amperes: `Vref x counts / 4096 / (amp_gain x R_shunt)`.
- **Supply voltage.** `0x5f7e` writes `driver_board+0x48 = Vref x divider x ADC / 4096`, in volts.
- **MCU temperature.** `0x5fb0` writes `driver_board+0x4c` from the internal sensor, using the factory calibration word at `0x1ffff720`, in °C. Kalico already polls this as index 17.
- **Encoder.** `+0x24` is the position within one turn; `+0x2c` is turns × resolution + that position (`0x5b94`). Both are integer counts.

## Index matrix

| # | Name | Field | Type | Unit | Status |
| --- | --- | --- | --- | --- | --- |
| 0 | zero | constant | — | — | verified-static |
| 1 | pos_ref | controller +0x118 | float32 | rad (candidate) | verified-static |
| 2 | spd_ref | controller +0x1e4 | float32 | rad/s (candidate) | verified-static |
| 3 | id_ref | controller +0x2b0 | float32 | A (candidate) | verified-static |
| 4 | iq_ref | controller +0x37c | float32 | A | verified-static |
| 5 | pos_fdb | controller +0x11c | float32 | rad (candidate) | verified-static |
| 6 | spd_fdb | controller +0x1e8 | float32 | rad/s (candidate) | verified-static |
| 7 | id_fdb | controller +0x2b4 | float32 | A (candidate) | verified-static |
| 8 | iq_fdb | controller +0x380 | float32 | A | verified-static |
| 9 | phase_current_a | controller +0x7c | float32 | A | verified-static |
| 10 | phase_current_b | controller +0x80 | float32 | A | verified-static |
| 11–13 | step-pulse input fields | system object | int32 / uint16 | — | **out-of-scope** (subdivision) |
| 14 | stall_detected | system +0x38 / +0x40 | uint16 (0/1) | — | verified-static |
| 15 | encoder_single_turn | encoder +0x24 | **int32** | counts | verified-static |
| 16 | encoder_multi_turn | encoder +0x2c | **int32** | counts | verified-static |
| 17 | mcu_temperature | driver board +0x4c | float32 | °C | **verified** (live in Kalico) |
| 18 | supply_voltage | driver board +0x48 | float32 | V | verified-static |
| ≥ 19 | — | none | — | — | **unsupported** (stale answer) |

Notes on the statuses:
- **verified-static:** the field and its type are the same in all four images, and the unit follows from the code. The value has not been observed live yet.
- **Candidate units:** they are what the comparisons in the code imply. Example: the position error compared with `stall_pos_err_rad` makes radians likely, but a FAL stage sits between them.
- **d axis:** `id` is the d axis by elimination only.

Across the images, indices 0–10 and 15–18 read identical offsets. Indices 11–14 read system fields that moved in 081; index 14 stays the stall flag (checked in `081` at the detector).

### Format consequences

- Indices 14, 15 and 16 are integers. Decoding them as float32, as a generic GET reader would, returns meaningless tiny numbers. For example the count 123456 decodes as about 1.7e-40.
- `k2fw.mot2_get.decode_get_payload` decodes each index by its proven type. It flags NaN and infinity as invalid, and refuses wrong lengths, the out-of-scope indices and the unsupported ones.

### Tracking error

**No index exposes it.** The firmware keeps the position PID error at `controller+0x124`, which the stall detector uses, and the protection stage has its own `protect_pos_tracking_error_*` limits. Neither is in the GET table.

Index 1 minus index 5 is only a host-side approximation: the two readings come from separate transactions taken at different instants.

## What is not claimed

- No value except index 17 has been seen on a real controller.
- The calibration constants Vref and the voltage divider were not read, so the absolute scale of indices 9, 10 and 18 still needs the hardware check.
- The encoder resolution (counts per turn) was not decoded.
- Indices 11–13 were not analysed (subdivision domain).
- Nothing here changes Kalico. A Kalico hook is a separate PR, only after the hardware check, and off by default.

## Proposed supervised hardware check (not authorized by #10)

**Conditions:**
- printer idle (`standby`), heaters off, not homing;
- one bus owner: Kalico, through a temporary G-code calling the existing `get_value` path, with the decoding from `k2fw.mot2_get`;
- no other tool on RS-485.

**Acquisition:**
- **Indices per axis:** 1–10, 14, 15, 16, 18, plus 17 as the control value. Never 11–13, and never anything ≥ 19.
- **Rate:** at most one GET every 200 ms over all axes, 3 rounds per axis.
- **Bus load:** a request is about 8 bytes and an answer about 12, so 5 GET/s is about 100 B/s, under 0.5% of the 230400-baud bus. The USB bridge benchmarks measured about 13 B/s of RS-485 traffic at rest with RFID reads.

**Checks:**

| Index | Expected |
| --- | --- |
| 17 | equal to Kalico's reading |
| 18 | close to the board supply (compare with SYS_PARAM 26 `driver_board_power_supply_V`) |
| 9/10, 7/8 | near 0 A while holding |
| 15/16 | stable at rest; 16 changes by the expected counts after a small manual X move (`FORCE_MOVE` 1 mm, owner present) |
| 5 vs 1 | follow each other |
| 14 | 0 |

**Stop at the first of these:**
- any NACK, timeout or CRC error;
- `serial_485` timeouts above 0;
- a new protection warning or error code;
- `motor_ready` false;
- any print or homing state.

**Metrics:**
- GET round trip per transaction;
- `serial_485` timeouts and CRC errors before and after;
- the RS-485 bridge counters.

**Afterwards:** only if the values match, propose optional telemetry:
- cached, polled at most every 10 s per axis, after the protections in priority;
- never read on subscribe;
- disabled by default.
