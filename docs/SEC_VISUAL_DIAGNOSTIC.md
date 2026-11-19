# Original terminal SEC visual diagnostic

Status: the operator saw the predicted four colors on November 18. Android
returned and all four post-boot readback hashes matched. The terminal SEC
attempt is consumed. [Physical evidence](evidence/sec-visual-transfer-20261118.json)

The normal platform remains the default. An explicit DEBUG/SEC_VISUAL build
enables `PcdSecVisualDiagnostic` and uses `Build/OculusGoSecVisual`, separate
from the normal platform output. No BootShim, external platform code or old
probe implementation is imported.

```powershell
.\scripts\build-edk2.ps1 -Target DEBUG -Jobs 8 -Mode SEC_VISUAL
```

## Scope and signal

The integrated ARM64 header and EDK2 FV reset branch enter the real SEC
module. Existing EL1/EL2, primary-affinity and MMU/data-cache-off guards run
first. The diagnostic also requires PC `0x80088000`, which must match the
independently verified linked SEC entry of its exact build. Rejected states
loop without any store.

The accepted path masks DAIF, writes two 32-row packed-24-bit bands to the
preserved splash RAM and terminates in a local loop. Each row has four
360-pixel blocks: white, black, green, magenta. These colors are unchanged
by swapping red and blue bytes. The two bands begin at rows 640 and 1920.
The diagnostic never reaches the stack, C, MMU initialization, DXE, GIC,
timer, SMC/PSCI, PMIC, clocks, storage or USB drivers. It does not return or
contain a physical timeout. A host-process timeout cannot stop the visor.

A visible new pattern would demonstrate this bounded EDK2 SEC path, not
DXE, a working protocol on hardware, GOP or Windows. A static logo, black
screen, USB disappearance or Fastboot OKAY would not demonstrate execution
or identify the cause of failure. Watchdog/translation/scanout remain UNKNOWN.

## Data provenance, not copied implementation

Device evidence is separate from permitted source. The original unit's
`aboot_a` SHA-256 is
`6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74`.
Its ELF32 PT_LOAD maps file offset `0x8000` to address `0x91800000`.
The following static facts must be rechecked against that exact local dump:

- `0x918026f8` / `0x91802700`: argument base `0x83400000`.
- `0x918456d8`, `0x91845994`, `0x91845744`: preserve argument, advance by
  `0x1000`, assign the adjusted framebuffer base.
- Resolution records `0x918977bc` and `0x91897814`: width 1440, height 2560.
- Color record `0x918985d4`: 24 bits per pixel.
- `0x918459a0` / `0x918459a8`: width and stride receive the same value.
- The captured runtime DT reserves `cont_splash_mem@83401000`, base
  `0x83401000`, length `0x023ff000`; its preceding DFPS page is not touched.

These are binary/data observations, not source imports or proof of live DMA.
Existing historical reports are locators; do not execute the old runner or
take its earlier review as authorization for this image.

Stride is 4320 bytes; the full static surface is `0x00a8c000` bytes. The only
stores on the diagnostic path are three sequential STRB instructions. Each
band is `32 * 4320 = 138240` bytes, total 276480 bytes, wholly inside the
surface. A fresh offline model must validate exact bounds, patterns, guards,
original arguments, unchanged stack and terminal control flow. This is RAM
only, not MDP/DSI MMIO, and not a claim that physical addressing is proven.

## Physical hold point

Before proposing a single temporary attempt, retain exact source/FD/container
hashes, separate source audit, fresh model results and local data checks.
Revalidate the owner's presence, current stock state and physical recovery.
Disclose the exact temporary command and image; do not clear the full normal
FD, relax its guards, reuse the consumed old contract or add retry/fallback.
No permanent write is part of this diagnostic. There is no validated hard-
brick/EDL recovery path; stock-button recovery is not a universal guarantee.
