# CFS recovery boundary analysis

This note records the static evidence available for the CFS application/loader boundary. It does not claim that interrupted writes are recoverable until that behavior is validated on recoverable hardware.

## Application link address

Both analysed `cfs0` generations are raw Cortex-M application images whose reset vectors point into a region beginning at `0x08010000`.

| host release | app | size | reset vector | inferred app base | end (exclusive) |
| --- | --- | ---: | --- | --- | --- |
| 1.1.0.94 | cfs0_000_113 | 151724 | `0x08015801` | `0x08010000` | `0x080350ac` |
| 1.1.6.7.2 | cfs0_000_150 | 175104 | `0x0801a759` | `0x08010000` | `0x0803ac00` |

For both images the reset handler resolves to a valid offset inside the supplied binary. This leaves `0x10000` bytes (64 KiB) below the linked application region, from the normal MCU flash origin `0x08000000` to `0x0800ffff`.

That lower region is **consistent with** a resident loader/bootloader or other immutable lower-flash code. The stock firmware bundle does not contain a separate `cfs0` bootloader image, so this analysis does not independently prove the contents of that lower region.

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

## What is proven

Static evidence now supports all of the following:

- `cfs0` application code is linked at `0x08010000`;
- there is a separate 64 KiB lower-flash region below the application;
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
- that G30 and G32 return the same sector token;
- that every interrupted update can be recovered without SWD/programmer access.

For that reason `flash_allowed` remains false.