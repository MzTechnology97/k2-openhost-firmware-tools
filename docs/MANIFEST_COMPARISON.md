# Live status vs. selected firmware manifest

`k2fw status --manifest <manifest.json>` compares the live read-only status with a firmware manifest that the operator selected explicitly.

The comparison is informational only. It never chooses a flash operation, never changes a device, and never changes `write_enabled=false`.

## Safety model

The comparator deliberately distinguishes **runtime evidence** from **package provenance**.

For Main and Nozzle the running Kalico application does not expose Creality's 25-byte loader identity. The selected F012 manifest can still contain exactly one package artifact for each role. That artifact is reported as package provenance, not as a live bootloader match.

For motors and CFS, the runtime probes expose an application fingerprint but not the exact hardware target required for safe flashing. The comparator therefore lists compatible-scope artifacts and application revisions without selecting one.

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

The live motor fingerprint identifies the running application generation (`mot2_002_071` on the development K2 Pro), but it does not uniquely identify the exact F012 motor hardware token.

The comparison therefore reports all F012 motor artifacts in the selected manifest, the distinct application revisions they contain, and whether the live application is present. It keeps:

```text
exact_hardware: null
target_selection: unresolved
update_required: null
flash_allowed: false
```

This prevents an application-only match from silently choosing among `mot0_*`, `mot1_*` or `mot2_*` targets.
## CFS

The live CFS `VERSION_SN` identifies application `cfs0_000_113`, but the exact `cfs0_050_G30` / `cfs0_050_G32` boot variant remains unknown.

The comparator limits candidates to the same application family (`cfs0`) but does not select between hardware variants. Even if a selected manifest contains only a newer application generation, `update_required` remains `null` until exact hardware identity is independently established.

## Validation against K2 Pro 1.1.6.7.2

A reduced manifest was generated directly from the user-supplied extracted `1.1.6.7.2` firmware tree and contains 12 relevant F012/CFS artifacts.

Live comparison on 2026-10-03 produced:

```text
Main   package-target-present  mcu0_120_G32-mcu0_001_000   update_required=null
Nozzle package-target-present  noz0_130_G30-noz0_021_000   update_required=null
X/Y/E  hardware-unresolved     candidates use mot2_002_081 update_required=null
CFS    hardware-unresolved     G30 + G32 use cfs0_000_150  update_required=null
```

All device comparisons and the top-level result report `flash_allowed=false` / `write_enabled=false`.
