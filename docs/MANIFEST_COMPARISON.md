# Live status vs. selected firmware manifest

`k2fw status --manifest <manifest.json>` compares the live read-only status with a firmware manifest that the operator selected explicitly.

The comparison is informational only. It never chooses a flash operation, never changes a device, and never changes `write_enabled=false`.

## Safety model

The comparator deliberately distinguishes **runtime evidence**, **live loader identity**, and **package provenance**.

For Main and Nozzle the running Kalico application does not expose Creality's 25-byte loader identity. The selected F012 manifest can still contain exactly one package artifact for each role. That artifact is reported as package provenance, not as a live bootloader match.

For motors and CFS, application-only runtime probes still do not expose the exact hardware target required for safe selection. The comparator therefore keeps that case unresolved. When a separately validated loader probe supplies `loader_identity.hardware`, the comparator prefers that exact live identity and may resolve one exact artifact. It can then report whether the application revision differs, while keeping `flash_allowed=false`.

No comparison mode returns `update_required=true` while exact live hardware identity is missing.
## Main and Nozzle

The live record already carries a `stock_package_candidate` derived from the analysed F012 package:

- Main: `mcu0_120_G32-mcu0_001_000`
- Nozzle: `noz0_130_G30-noz0_021_000`

When an explicitly selected manifest contains the exact package hardware for that role, the comparator reports:

```text
mode: package-provenance
status: package-target-present
runtime_hardware_verified: false
target_selection: resolved-from-package-provenance
update_required: null
flash_allowed: false
```

`package_application_differs` only says whether the selected package contains a different application token from the known package baseline. It is **not** an update decision for the running MCU.
## X/Y/E motors

The normal application fingerprint identifies the running application generation (`mot2_002_071` on the development K2 Pro), but by itself does not identify the hardware variant.

The 2026-10-04 guarded loader probe established:

```text
X/Y: mot2_023_C30-mot2_002_071
E:   mot2_022_C30-mot2_002_071
```

With those exact live identities, the selected `1.1.6.7.2` manifest resolves:

```text
X/Y -> F012/motor/mot2_023_C30-mot2_002_081.bin
E   -> F012/mot2_022_C30-mot2_002_081.bin
```

The comparator may therefore report `update_required=true` for the application difference, but `flash_allowed=false` remains unchanged.

## CFS

The normal CFS `VERSION_SN` identifies application `cfs0_000_113` but not the G30/G32 hardware variant, so application-only status remains unresolved.

The guarded loader probe independently identifies the development unit as `cfs0_050_G32-cfs0_000_113`. With that exact loader identity, the `1.1.6.7.2` manifest resolves `cfs/cfs0_050_G32-cfs0_000_150.bin` and reports an application revision difference. `flash_allowed` remains false.

## Validation against K2 Pro 1.1.6.7.2

A reduced manifest was generated directly from the user-supplied extracted `1.1.6.7.2` firmware tree and contains 12 relevant F012/CFS artifacts.

Application-only comparison on 2026-10-03 remained unresolved for motors/CFS as designed.

After the guarded live loader probe on 2026-10-04, the exact hardware identities resolve:

```text
Main    mcu0_120_G32  mcu0_001_000 -> mcu0_001_000  update_required=false
Nozzle  noz0_130_G30  noz0_021_000 -> noz0_021_000  update_required=false
X/Y     mot2_023_C30  mot2_002_071 -> mot2_002_081  update_required=true
E       mot2_022_C30  mot2_002_071 -> mot2_002_081  update_required=true
CFS     cfs0_050_G32  cfs0_000_113 -> cfs0_000_150  update_required=true
```

These are target-resolution results, not flash authorization. All comparisons still report `flash_allowed=false` / `write_enabled=false`.