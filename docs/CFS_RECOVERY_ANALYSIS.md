# CFS recovery boundary analysis

This note records the static evidence available for the CFS application/loader boundary. It does not claim that interrupted writes are recoverable until that behavior is validated on recoverable hardware.

## Application link address versus physical update placement

The original analysis inferred a **nominal linked image window** at `0x08010000` from the stock Cortex-M reset vectors. **Do not use this inference as the physical load/write address.** Later analysis of the G32 loader and the merged [T113 bootstrap #13](https://github.com/MzTechnology97/k2-openhost-t113-bootstrap/pull/13) established a physical application placement beginning at **`0x08003000`**; the updater's current custom-image validator and tests use that origin.

| Host release | Application | Image bytes | Reset vector in image | Physical APP start | Physical end (exclusive) |
| --- | --- | ---: | --- | --- | --- |
| 1.1.0.94 | `cfs0_000_113` | 151724 | `0x08015801` | `0x08003000` | `0x080280ac` |
| 1.1.6.7.2 | `cfs0_000_150` | 175104 | `0x0801a759` | `0x08003000` | `0x0802dc00` |

Reset-vector addresses are **absolute execution addresses** and do not alone identify the physical first flash byte of the file. In particular, the previous end values `0x080350ac` and `0x0803ac00` were calculated using the nominal `0x08010000` origin, not the later-verified physical placement.

This also corrects the earlier claim that the CFS must reserve **64 KiB** below the application. The loader/application boundary identified in subsequent work is **`0x3000` (12 KiB) from `0x08000000`** for this loader generation; neither dimension establishes the full contents of the protected loader region without a complete dump. The original stock bundle does not contain a separate `cfs0` bootloader image.

Historical patched-stock builders may still encode the nominal `0x08010000` coordinate system in callsite tables or linker offsets. **Do not globally change their origin without a complete relocation and validation of every hook.**

## Host update addressing

The recovered stock `mcu_util_485` flow never supplies a destination flash address:

- `F0/06` requests erase;
- `F0/01` requests update mode;
- the firmware length is sent as a raw little-endian 32-bit value;
- application data is then streamed as raw chunks;
- `F0/02` requests application start.

No erase/write transaction contains a host-selected flash destination. The peripheral loader therefore owns the erase/write placement policy.

This substantially reduces the chance of an ordinary host-side updater bug accidentally targeting `0x08000000`, but it does not prove that the loader implementation can never erase itself.

## G30 vs G32

The `cfs0` G30 and G32 application images are byte-identical in both analysed host releases:

- 1.1.0.94: G30 == G32, SHA-256 `386a1106391a332e6a97803c5ce00b87b6d3ddc4c3d61f6fe07fb19fd3125b76`;
- 1.1.6.7.2: G30 == G32, SHA-256 `bde552ef5056037989457e294f88cfa7590b4c9251cda5e40adf0a4fae46c5a3`.

Therefore G30/G32 does **not** change the application payload bytes for these two releases.

It remains a safety-relevant loader identity because the bootloader version can still affect sector-token semantics, loader capabilities or recovery behavior even when the application payload is identical.

## Loader-mode protocol corroboration

The installed Jacob-lineage CFS driver adds direct protocol evidence beyond the image layout. A0/A1/A2 identity replies contain a CFS device type plus an explicit mode byte: `0=application`, `1=loader`. If enumeration finds a CFS in loader mode, the address manager starts the application and verifies that a subsequent A2 query reports application mode. The recovered loader-to-app broadcast is command `0x0B` with payload `01`.

An independent community flasher reproduces the same updater loader and uses a non-flash probe sequence to read `F0/00` boot identity and `F0/03` sector token before starting the application again. This independently corroborates the application/loader split and application-only updater design. It does not by itself prove the exact cold-boot timing or guarantee fallback after every interrupted write.

## Live loader identity and sector token

A guarded live probe has now confirmed the development K2 Pro CFS loader identity as `cfs0_050_G32` with current application `cfs0_000_113`. The loader returned sector token `0xE0`, which the recovered stock arithmetic maps to a 128-byte transfer chunk.

This removes the G30/G32 ambiguity for this machine and resolves the exact 1.5.0 package target to `cfs0_050_G32-cfs0_000_150.bin`.

The 1.5.0 image is 175104 bytes, therefore a stock transfer using the live G32 token consists of exactly 1368 chunks of 128 bytes with no partial tail.

Live restore also showed that `F0/02` can ACK while A2 still reports loader mode. The Jacob `0B/01` command then transitioned the same device to application mode successfully. Post-command A2 verification is therefore required; ACK alone must not be treated as proof of application startup.

## What is proven

Static evidence now supports all of the following:

- historical stock-image reset vectors are consistent with a nominal `0x08010000` execution window, while the later-verified physical APP placement is `0x08003000`;
- the loader/application boundary for the researched G32 generation is at `0x08003000` (12 KiB above normal flash origin); the precise protected loader extent needs a full loader dump;
- the firmware package updates the application image, not a bundled bootloader image;
- G30 and G32 receive identical application bytes in both analysed releases;
- the host updater does not choose the flash destination address;
- host-side transfer retry/restart behavior is known.

## What is not proven

The following remain hardware-validation gates:

- that the lower 64 KiB region is definitely the complete CFS bootloader;
- that the loader always validates the app before jumping to it;
- that a corrupted or partially erased application forces the loader to remain on RS-485;
- that power loss during erase/program cannot corrupt loader metadata;
- that G30 returns the same sector token as the now-confirmed G32 token `0xE0`;
- that every interrupted update can be recovered without SWD/programmer access.

For that reason `flash_allowed` remains false.