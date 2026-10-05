# Firmware identity contract (`k2fw.identity/1`)

One versioned JSON record per device role says:
- what each peripheral is running;
- what its loader reported, if anyone checked;
- which package would target it.

It keeps the three kinds of knowledge apart, so that neither a UI nor a later tool can mistake one for another.

Roles: `main`, `nozzle`, `motor_x`, `motor_y`, `motor_e`, and `cfs_<address>` for each CFS.

```bash
python -m k2fw identity
python -m k2fw identity --loader-evidence evidence/k2_pro_live_loader_probe_2026-10-04.json \
                        --manifest firmware.json
python -m k2fw identity --from-status saved-status.json      # offline, no Moonraker
```

`identity` reuses the reads of `k2fw status`: the Moonraker MCU objects, one `MOTOR_READ_PARAM` per motor, and the CFS `VERSION_SN` already published by `box`.
- It never resets a device, enters a loader or flashes.
- A saved status without `observed_at` counts as stale.

## Three categories, never converted

| Category | Field | Comes from | It is not |
| --- | --- | --- | --- |
| Runtime observation | `observed` | the running application, now: Kalico `mcu_version`, motor FLASH_PARAM id 0, CFS `VERSION_SN` | a hardware or loader identity |
| Loader identity | `loader` | an explicitly supplied, authorized loader-probe evidence file | a current reading: it is dated, and checked against the runtime fingerprint where one exists |
| Package target | `package` | the stock F012 table, or an explicit manifest | a runtime read (`runtime_verified` is always `false`) |

Rules:
- **Runtime does not become loader identity.** A known motor fingerprint (`0x0247`) names the application `mot2_002_071`; `loader.hardware` stays `null`.
- **The Kalico version string is not a Creality token.** For Main/Nozzle `observed.application` is `null`; the string is kept as `fingerprint.kind = "kalico_mcu_version"`.
- **Provenance alone decides nothing.** An exact stock or manifest target without a verified loader identity leaves `update_required` at `null`.
- **`update_required` is set only** when the loader identity is `verified` and the package target is an exact single match.
- **`flash_allowed` is always `false`**, at device and contract level. The UI cannot change it.
- **Unknown stays unknown.** A missing reading is `null`, or `present: null` when the role was not observed. An absent device is `present: false`. Nothing is guessed from names: mot0/mot1/mot2 boards all run `mot2_*` applications, so an application never selects a hardware family.

## Record fields

| Field | Meaning |
| --- | --- |
| `role` | device role |
| `present` | `true`, `false` (reported absent) or `null` (not observed) |
| `observed.application` | Creality application token when the fingerprint is an exact known match, else `null` |
| `observed.fingerprint` | `{kind, value}`: `kalico_mcu_version`, `flash_param_id0` (hex) or `cfs_version_sn` |
| `observed.observed_at`, `age_s`, `fresh` | sample time and age; `fresh` is false past `--max-age` (600 s) or when undated |
| `loader.status` | `absent`, `verified`, `conflict` (runtime application differs: reflashed since?) or `expired` (older than `--max-evidence-days` with no runtime cross-check) |
| `loader.hardware`, `application`, `source`, `evidence_date`, `evidence_age_days` | from the evidence file |
| `loader.cross_check` | `match`, `conflict`, `unchecked` (no fresh fingerprint) or `not-available` (Main/Nozzle: the runtime exposes no Creality token) |
| `package.status` | `exact`, `ambiguous`, `none`, `stock-table` (no manifest; unique stock F012 artifact) or `not-compared` |
| `package.target`, `candidates`, `basis`, `runtime_verified` | the artifact (path, hardware, application, kind, size, SHA-256), or all candidates when not exact |
| `verification` | `loader-verified` > `runtime-fingerprint` > `runtime-observed` > `package-provenance` > `unknown` |
| `update_required` | `true` / `false` / `null`, as above |
| `flash_allowed` | always `false` |
| `notes` | why a decision was withheld |

## Sources and reliability

| Source | Category | Roles | Reliability |
| --- | --- | --- | --- |
| Moonraker `mcu`, `mcu nozzle_mcu` | observed | Main, Nozzle | running Kalico application string only |
| `MOTOR_READ_PARAM` id 0 | observed | X/Y/E | exact fingerprint of known applications (`0x0247` 071, `0x024b` 081), not the hardware target |
| `box.cfs_versions` | observed | CFS | application only; G30/G32 images are byte-identical, so never the board variant |
| loader-probe evidence | loader | all | hardware + application from the loader handshake on this printer, on that date |
| stock F012 table | package | Main, Nozzle | the unique stock artifact for the role |
| manifest (`k2fw scan`) | package | all | exact only with a verified hardware token and one match |

### Authorized loader evidence

The file must be in the hardware-validated loader-probe format (schema 1), and must show that the probe:
- marked `entry.hardware_validated: true`;
- sent no erase, application length, firmware data or update request;
- recorded `flash_allowed: false`;
- omitted the device UniIDs (`uniids_omitted: true`).

Anything else is rejected.

How the evidence maps to roles:
- `main` → `main`, `toolhead` → `nozzle`, `extruder` → `motor_e`.
- `rs485_motors` → `motor_x` and `motor_y` only when both entries are identical; otherwise they are not attributed.
- `cfs` → the CFS role only when exactly one CFS is present (the evidence carries no address).

What cannot be attributed is listed in `inputs.loader_unassigned`.

## Example (anonymized, development K2 Pro, 2026-10-05)

```json
{
  "schema": "k2fw.identity/1",
  "inputs": {
    "loader_evidence": "k2_pro_live_loader_probe_2026-10-04.json",
    "loader_evidence_date": "2026-10-04",
    "loader_unassigned": [],
    "manifest_release": "1.1.6.7.2"
  },
  "devices": [
    {
      "role": "motor_x",
      "present": true,
      "observed": {
        "application": "mot2_002_071",
        "fingerprint": {"kind": "flash_param_id0", "value": "0x0247"},
        "source": "moonraker/motor_control MOTOR_READ_PARAM",
        "age_s": 0.0,
        "fresh": true
      },
      "loader": {
        "status": "verified",
        "hardware": "mot2_023_C30",
        "application": "mot2_002_071",
        "evidence_date": "2026-10-04",
        "cross_check": "match",
        "note": "both RS-485 motors reported this same identity; no per-axis attribution is needed"
      },
      "package": {
        "status": "exact",
        "target": {"path": "F012/motor/mot2_023_C30-mot2_002_081.bin", "application": "mot2_002_081"},
        "runtime_verified": false
      },
      "verification": "loader-verified",
      "update_required": true,
      "flash_allowed": false
    },
    {
      "role": "main",
      "present": true,
      "observed": {
        "application": null,
        "fingerprint": {"kind": "kalico_mcu_version", "value": "<kalico mcu version>"},
        "fresh": true
      },
      "loader": {"status": "verified", "hardware": "mcu0_120_G32", "application": "mcu0_001_000", "cross_check": "not-available"},
      "package": {"status": "exact", "target": {"path": "F012/mcu0_120_G32-mcu0_001_000.bin"}, "runtime_verified": false},
      "verification": "loader-verified",
      "update_required": false,
      "flash_allowed": false
    }
  ],
  "flash_allowed": false
}
```

Live result on that day, with the evidence and the 1.1.6.7.2 manifest (`flash_allowed` false everywhere):

| Role | Running | Package target | `update_required` |
| --- | --- | --- | --- |
| Main, Nozzle | `mcu0_001_000`, `noz0_021_000` | same | false |
| X/Y | `mot2_002_071` | `mot2_002_081` | true |
| E | `mot2_002_071` | `mot2_002_081` | true |
| CFS | `cfs0_000_113` | `cfs0_000_150` | true |

Without the evidence file, the motors and the CFS drop to `runtime-fingerprint` with ambiguous targets, and `update_required: null`.

## Integration in Kalico

Not implemented here: this part belongs in `kalico-k2pro`.

- **Read once per session, never on subscribe.** Read motor FLASH_PARAM id 0 once per Klipper session, after the startup override pass while `motor_ready`, and keep it in `MotorParamCache` next to overrides and calibration. Store the value, the read time and the session.
- **Expose it read-only.** `get_status` returns the cached value with its age. A G-code like `MOTOR_IDENTITY_REFRESH` repeats the read on request only: idle, not homing, not printing, the same guards as `k2fw status`.
- **CFS.** `box.cfs_versions` is already cached; expose only the version, never the serial or UniID.
- **Leave out of Kalico.** Loader evidence and manifests stay outside Kalico, and Kalico never sets `update_required` or `flash_allowed`. `k2fw identity --from-status` can build the contract from a saved status that includes the cached values and their `observed_at`.
- **Upstream syncs.** The motor modules come from the Jacob10383 K2 bundle, so keep the patch small and note it in `docs/K2_PRO_OPENHOST.md` so it survives future syncs.

## Display in Mainsail (optional)

- Show per role: running application, verification level, the loader evidence date when present, the package target, and `update_required` when not `null`.
- Show `unknown` as unknown, and a stale observation with its age.
- Never offer a flash action from this data.
- Read only the cached Kalico status; the panel must not trigger firmware reads.
