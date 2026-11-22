# Status

**UFS tras LK.** El DT de Pacific sitúa al maestro UFS en AGGRE2, camino de SNOC. En las 71 referencias IOMMU del árbol no consta una asignación de UFS a ANOC2. Los cinco registros del GCC ya se leyeron en el Go. La ruta de traducción efectiva y el bus de la página CPU `0x80441000` siguen **UNKNOWN**. En QEMU se comprobó la capacidad en ambos extremos con traducción S2 y con bypass explícito. [Topología del Go](UFS_ROUTE_SOURCES.md) · [Resultados y nueva sonda](UFS_ROUTE_VIEW.md)

**Destino directo de UFS.** `0x80441000` es candidato de identidad en Pacific. QEMU verificó ambos extremos y detectó DMA a la página vecina incluso con éxito SCSI. En el arranque físico de `UFS_PRDT`, el slot 0 conservaba el puntero UCD `0x918FDF00` y cero entradas de datos. La dirección de bus de la página propia sigue **UNKNOWN**. [Panel del Go](evidence/ufs-prdt-transfer-20261121.json) [Pruebas e interpretación](UFS_NATIVE_PRDT.md)

**UFS, página propia de 4096 bytes.** En QEMU, el LUN 4 entregó su capacidad en `0x80441000` y `0x80441FF8`, incluso con traducción de bus distinta de la dirección CPU. La dirección de bus de esa página en el Go sigue **UNKNOWN**. En el Go, la respuesta del último descriptor de LK apuntaba a `0x918FDF20`. Dos recorridos estables de cuatro intervalos libres dieron `UFS HEAP NO PAGE` para la página `0x918FD000`. [Panel físico](evidence/ufs-heap4k-transfer-20261121.json) [Página, pruebas y alcance físico](UFS_OWNED_PAGE.md)

**Búfer de LK.** En el arranque temporal de `UFS_ZERO4K`, el Go mostró `NZ 00000000`, `FIRST NONE` y `ZERO EXACT`. Las dos muestras por CPU coincidieron en los 4096 bytes a partir de `0x918D7E80`. LK inicializa ese intervalo a cero en su BSS. La disponibilidad para uso exclusivo de EDK2 y el DMA de UFS a sus extremos siguen **UNKNOWN**. [Panel del Go](evidence/ufs-zero4k-transfer-20261121.json) · [Diez pruebas en QEMU](UFS_GPT_HEADER.md#censo-de-los-4096-bytes-con-ufs_zero4k)

**Cabecera GPT del LUN 4.** SEC leyó el LBA 1 completo en QEMU en el búfer de cabecera de LK de `0x918D7E80`. Los 4096 bytes coincidieron con el respaldo de Android. En el Go, la CPU leyó dos veces los 4096 bytes en ese intervalo. Las dos muestras coincidieron y dieron CRC32 `C71C0011` y clasificación `OTHER`. El acceso DMA a ese búfer sigue pendiente. [Panel físico](evidence/ufs-buf4k-transfer-20261121.json) [Resultado y sonda física](UFS_GPT_HEADER.md)

**Ventana UFS de 16 KiB.** DXE obtuvo del proveedor UEFI las cuatro direcciones de bus en QEMU y recibió la capacidad del LUN 4 en cada página. Las direcciones directas del Go siguen **UNKNOWN**. En el Go, `UFS_BOUNCE` entregó ocho bytes a cada página mediante cuatro copias por CPU desde la dirección DMA de LK. El panel terminó en `UFS LK COPY DONE` con máscara `0x0F`. [Panel físico](evidence/ufs-bounce-transfer-20261121.json) [Resultados por página y paquete](UFS_BUS_PAGES.md)

**Primer DMA de datos UFS confirmado en el Go.** La sonda recibió los ocho bytes de capacidad del LUN 4 en la página de LK. El último LBA fue `0x0011FFFF` y el bloque lógico mide 4096 bytes. El DMA directo a las cuatro páginas propias se ha probado en QEMU. [Panel físico](evidence/ufs-data-transfer-20261121.json) · [Alcance de la prueba](UFS_DATA.md)

**Primer NOP UFS confirmado en el Go.** En el slot 1 de las colas heredadas de LK, el controlador devolvió `NOP IN` con tag 1 y `OCS 00000000`. El visor mostró `RAM RESTORED` después de que la sonda cotejara las dos asignaciones. La dirección DMA de la ventana propia de 16 KiB y la primera lectura de un sector del LUN 4 siguen pendientes. [Registro físico](evidence/ufs-nop11-transfer-20261121.json) · [Sonda y pruebas QEMU](UFS_NOP11.md)

**UFS.** QEMU recuperó el logo con la GPT y la geometría medidas del LUN 4. La sonda SEC llegó a `UFS DONE` en el Go. LK entregó el host UFSHCI 1.1 habilitado y ambas listas en marcha, con los dos doorbells a cero. La [sonda de colas](UFS_QUEUES.md) llegó a `UFS QUEUES DONE` en el visor. UTR estaba en `0x918EE400` y UTM en `0x918EEC00`. Siguen pendientes el mapeo DMA del Go y la primera lectura de un sector del LUN 4 desde EDK2. [Resultados y procedimiento](UFS_HANDOFF.md)

Reconstruction started 2026-10-22. Offline verification extended 2026-10-25.

| Milestone | New tree |
| --- | --- |
| Device evidence/backups | Preserved locally in the preceding project |
| Allowed-source platform | Original board code + pinned official EDK2; compiler/link inputs audited |
| Standalone EDK2 build | DEBUG. Historical checkpoint images use a 4 MiB FD. The normal Shell image includes a 16 MiB boot arena in a 20 MiB FD. |
| TrustMeBro protocol | PASS: 19 host checks; installed, located and queried from real DXE in QEMU EL1/EL2 |
| Direct-entry image without BootShim | PASS: header/FV/SEC structure; original Android container roundtrip/reproducibility |
| Early ARM64 entry in QEMU | PASS: 10 cases, stop before first BL |
| SEC to DXE in QEMU | PASS: EL1 and EL2, HOBs, memory setup, decompression and loaded DXE entry |
| Execution on Oculus Go | M2 CONFIRMED in terminal SEC by the operator's visual observation on November 18 |
| SEC private stack and C color checkpoint | CONFIRMED on the Go. After the stack witness check, C drew the observed blue–white–blue and red–black–red groups. Byte 0 is blue and byte 2 is red in the inherited framebuffer. Return from C is verified only in QEMU. [Physical record](evidence/sec-c-transfer-20261118.json) |
| PI memory handoff diagnostic | CONFIRMED on the Go. The owner saw “celeste, amarillo, blanco, amarillo, celeste” after SEC validated the PHIT in the loaded image and completed both 64-bit loads. The packaged FD also passed 23 QEMU cases. [Physical record](evidence/sec-mem-transfer-20261118.json) |
| UEFI Graphics Output Protocol | CONFIRMED-QEMU. The DXE dispatcher started InheritedGopDxe after DevicePathDxe at EL1 and EL2. The published GOP filled two bands and read the colors back. Guest RAM confirmed packed BGR888 across both bands. M3 CONFIRMED-DEVICE. The owner saw blue, red, yellow, red and blue on the Go during a temporary boot. [Physical observation](evidence/dxe-gop-transfer-20261120.json) [Two-driver trial](DXE_GOP.md) · [Standalone GOP operations](evidence/gop-bgr-qemu-20261118.json) |
| UEFI text output over GOP | CONFIRMED-QEMU at EL1 and EL2. Both calls through `ConOut->OutputString()` returned success. The two framebuffer views matched the expected letter rasters byte for byte. CONFIRMED-DEVICE. The owner read both lines after turning the headset. Text appeared upside down in its usual orientation. [Physical observation](evidence/dxe-text-transfer-20261120.json) [Capture and procedure](DXE_TEXT.md) |
| Text orientation | CONFIRMED-DEVICE. In the normal wearing position the owner read both lines upright and complete through each eye, with markers 1 and 2 on top and 3 and 4 below. [Orientation trial](DXE_TEXT_UPRIGHT.md) |
| Standalone FV application | CONFIRMED-QEMU. DXE reads the application PE from the FV, enters it, observes its text in both views and receives its return status. CONFIRMED-DEVICE. During the temporary boot, the owner read the application’s green “5 APP EFI 6” below the white DXE line. [Application trial](DXE_APP.md) |
| Normal BDS and upstream Shell | CONFIRMED-QEMU. The Pacific FD recovered from the Android container printed `UEFI Basic Shell v2.2` and `Shell>` through the inherited display console in both views. CONFIRMED-DEVICE. The operator read `hell>` in the left eye and saw less of the output in the right. The centered image placed the prompt at (448, 720) per eye in QEMU. On the Go the operator read the complete `Shell>` prompt and upper lines through each lens separately. Physical key input remains untested. [Centered Shell trial](evidence/shell-centered-transfer-20261120.json) Stock Android returned with all four original hashes. [Physical trial](evidence/shell-transfer-20261120.json) [Shell trial](SHELL_BOOT.md) |
| 3D welcome before Shell | CONFIRMED-QEMU. Both views rendered the blue glass pyramid and the greeting. The complete centered Shell prompt followed. On the Go, the operator saw the welcome and confirmed the Shell appeared afterward. Binocular depth, frame pacing and the exact greeting remain unverified on hardware. [Physical record](evidence/welcome-repeat-transfer-20261120.json) · [Scene and capture](WELCOME.md) |
| Panoramic Shell and centered emblem | CONFIRMED-QEMU for the repacked Pacific FD. The 65 × 13 console used a 650 × 325 viewport in both eyes. Both 68 × 42 emblems matched the original pixel samples at (606, 699), inside the frame. The same FD reached the prompt with an empty initial scanout. On the physical Go the operator saw the Shell in both eyes. The emblem was absent during the welcome and inside the Shell frame. Android recovered and the four boot partition hashes matched. [Physical run](evidence/oculus-logo-transfer-20261120.json) · [With the stock splash](evidence/oculus-logo-pacific-el1-20261120.json) · [Without the stock splash](evidence/oculus-logo-pacific-blank-20261120.json) |
| Direct UFS splash reader | CONFIRMED-QEMU. Three UFS layouts returned the original pixels and GOP readback passed. Six invalid inputs were rejected. Android on Pacific confirmed the GPT extent on LUN 4 with 4096-byte blocks. Physical reads from EDK2 remain pending. [Measured geometry](evidence/ufs-splash-physical-layout-20261120.json) · [QEMU results](evidence/ufs-splash-qemu-20261120.json) |
| Stock Oculus emblem from storage | CONFIRMED in an ARM64 EDK2 QEMU guest using a read-only GPT disk. The Pacific reader found the stock pixels on `splash` and rejected the same bytes under another label. The physical Go still lacks a connected UFS Block I/O handle. [Disk test](evidence/oculus-logo-virtual-gpt-20261120.json) |
| Storage/USB/ACPI/Windows | Pending |
| SEC stage-1 translation and scanout | SEC_MMU passed 29 QEMU cases across EL1 and EL2. CONFIRMED on the Go. The operator saw the sealed red center after the translated stack witness and full framebuffer readbacks. [Physical record](evidence/sec-mmu-transfer-20261118.json) |
| HOB arena and compressed DXE FV inside the FD | SEC_DXE passed 18 packaged-image QEMU cases. Four reached the terminal checkpoint inside upstream DXE Core across EL1 and EL2. CONFIRMED on the Go. The operator saw the five-block signal with green sides and a purple center from inside upstream DXE Core after the HOB checks. Stock Android recovered on slot A and all four partition hashes matched the originals and preflight. [Attended trial](evidence/sec-dxe-transfer-20261119.json) · [Image review](evidence/sec-dxe-review-20261118.json) · [Trace results](evidence/sec-dxe-qemu-20261118.json) |
| Early DXE page and pool services | DXE_MEM passed 28 packaged-image QEMU cases. Four positive boots at EL1/EL2 allocated, wrote, read, mapped and freed memory through the live Boot Services table. CONFIRMED on the Go. The operator saw white, blue, green, blue, white after DXE validated both maps and released both allocations. Android returned on slot A and all four control hashes matched. [Physical trial](evidence/dxe-mem-transfer-20261119.json) · [Test and image](DXE_MEM.md) |
| DXE image services and Global Coherency Domain | CONFIRMED on the Go. The operator observed the final magenta sides and cyan center after the Loaded Image lookup, HOB migration, GUID-page check, GCD map validation and buffer release. Android recovered on slot A and all four complete readbacks matched the originals and preflight. [Physical trial](evidence/dxe-gcd-transfer-20261119.json) · [QEMU results](DXE_GCD.md) |
| DXE constructors and EFI configuration tables | CONFIRMED in QEMU EL1/EL2. Five constructors returned success. All three GUID lookups worked, including a call through published DXE Services and a byte comparison of the migrated HOB list. CONFIRMED on the Go by the final orange center, green sides and white ends. [Physical record](evidence/dxe-tables-transfer-20261119.json) [Model and candidate](DXE_TABLES.md) |
| DXE debug image support | CONFIRMED in QEMU EL1/EL2. A one-page allocation at the 4 MiB boundary holds the CRC-checked system table locator. The published debug GUID leads to the real DXE Core image record. CONFIRMED on the Go by the final white, red, cyan, red and white pattern. [Physical record](evidence/dxe-debug-transfer-20261119.json) · [Candidate and results](DXE_DEBUG.md) |
| First firmware-volume driver dispatch | CONFIRMED-QEMU at EL1 and EL2. The DXE dispatcher discovered and started upstream DevicePathDxe. A call through its published protocol returned 4 bytes for an end node. CONFIRMED-DEVICE on the Go by the orange bands and green center after the protocol call. [Physical record](evidence/dxe-dispatch-transfer-20261119.json) [Model and candidate](DXE_DISPATCH.md) |
| Guarded 256 KiB stack inside the FD | CONFIRMED on the Go. The operator saw the five-color checkpoint after both full-span patterns, nested C calls, PI handoff validation and final guard checks. [Physical record](evidence/sec-stack-transfer-20261118.json) |

The original offline FD below passed the early-entry, SEC and DXE tests. No emulator-only
board addresses replace the production map. QEMU supplies ordinary RAM that
contains the selected addresses; tests stop after the diagnostic protocol,
before normal board-driver dispatch. This does not emulate Kryo, secure-world
handoff, the panel, watchdog or Go peripherals.

```text
FD: 4194304 bytes
SHA-256: a4acf898e51a814ad6ed4c84a9dacd8788120ad272c3fa528fb0b7579b698230
Android candidate: 487424 bytes
SHA-256: cbccd484b056f16ddb55f2bf9170673e92beba6d7456b37d779a6347d841426c
```

The Android candidate is local-only and marked NOT-FOR-DEVICE-EXECUTION.
Gzip decompression reproduces the complete FD and leaves exactly the original
365129-byte EVT DTB. Three locally generated containers have identical hashes.
No partition binary or generated device image is uploaded to GitHub.

Source audit covers 66 compiler dependency lists and 67 static archives:
5 original project inputs, 434 EDK2 inputs, and 144 generated files. The
official EDK2 commit/origin, tracked-file membership and clean tree are also
checked. No rejected input; optional Brotli code is not present or compiled.

M1 was reached for the new build in October. See the November 18 physical result below.
No ADB/Fastboot command was issued during the completed offline reconstruction.
In a subsequent owner-confirmed device session on 2026-10-25, the read-only
preflight passed: Android/root/identity checked, slot A, APQ8096pro ID 312
revision 1.1, and boot A/B plus aboot A/B readbacks matched the original hashes.
Battery was 18%, charging by USB. No headset reboot, payload or partition-write
command was issued. See READONLY_PREFLIGHT.md and its sanitized evidence record.
The complete FD is not cleared for a physical execution test.

## 2026-11-13 offline recheck (Mexico City)

- Rebuilt normal FD `72f602d2eec7d2bff0117bf8d8370218e47ef22fbd7023ab42b3497af9294e58` passed host, structural, source audit, and normal entry/SEC/DXE tests. The three changed bytes relative to the original FD encode two generated assertion line numbers; the handoff instruction and inner FV match. The normal FD is still not cleared for the headset.
- The separate opt-in terminal SEC FD `5cd4fc047a44df5f4322fc7634dbcb0a730261d4f94bb881f69382504dc51db0` passed all 12 offline cases again, with the model report byte-identical to the October run. No payload was sent, no physical attempt consumed. See [measurement review](SEC_VISUAL_PHYSICAL_REVIEW.md).
- The original-slot readback and stock recovery observations from October are historical. A future attended test requires fresh Android preflight and live Fastboot identity/lock checks.

The rebuilt normal validation report is local at `build/validation-20261114-040751/REPORT.json` (UTC directory name), SHA-256 `eb051bca7f6f28926c3f9bea56bda74cdb2fff33bdd7d994fa7327d19a958424`.

## 2026-11-18 — EDK2 via the original unlocked loader

This experiment used a temporary Android boot image with the original Qualcomm
boot chain in place. Meta documents the unlocked Go's policy for
`boot.img`. [Meta's Go unlock guide](https://developers.meta.com/vr/blog/unlocking-oculus-go/)

| Measured on local files | Preserved `boot_a` | Reviewed `SEC_VISUAL` image |
| --- | --- | --- |
| Android format and page size | v0, 4096 bytes | v0, 4096 bytes |
| ARM64 text offset and flags | `0x80000`, flags 0 | `0x80000`, flags 0 |
| Compressed / expanded payload | 9,035,401 / 21,396,992 bytes (Linux) | 114,499 / 4,194,304 bytes (EDK2 FD) |
| Appended device trees | CNC and EVT | Exact stock EVT, 365,129 bytes |
| Ramdisk | 9,217,382 bytes | Empty |

The complete candidate SHA-256 is `07eb55d5ac04c175c5101789672d45e0f584118d7a478898cea7193eefb4be14`.
We extracted the FD from those delivery bytes, verified its hash and the EVT
hash against the existing review, and ran all 12 EL1/EL2 visual-model cases
on the extracted FD. The eight accepted entries produced both complete bands
in emulated RAM. Four other entries rejected before drawing. The resulting
`build/packaged-visual-20261119T030249Z/model/REPORT.json` has SHA-256
`baa417b05343eb8b89066c5dbf1c6d9615ecf62b19e47e83160890ea22ceb000`.
QEMU started at the simulated handoff after unpacking. These tests exercise
neither Qualcomm authentication nor the physical panel. The [attended test](SEC_VISUAL_PHYSICAL_REVIEW.md)
is the first opportunity to observe those bands in the visor.

An additional QEMU/TCG test installed identity page tables at EL1 and enabled
stage-1 translation before entering the FD header. The harness and EDK2 read
the same `SCTLR_EL1=0xc50839`. Single-stepping the actual firmware reached
the MMU rejection branch before any framebuffer store. All nine sentinels and
the incoming arguments, SP and LR were intact. Run
`wsl -d Debian -- python3 tests/sec_visual_mmu_el1.py` to repeat this case.
The subsequent visual observation implies that the entry guard passed in
the selected EL. The exact EL and complete SCTLR value were not captured.

### Attended temporary boot, November 18 (Mexico City)

The Android preflight found `pacific`, APQ8096pro revision 1.1, slot
`_a` and root. Full readbacks of both `aboot` and both `boot` partitions
matched the preserved originals. The stock loader then reported both
`secure: yes` and `Secure boot: true`. It returned `OKAY` for Sending
and Booting the reviewed SEC_VISUAL image. The single attempt was consumed.
The owner reported purple, green, black and white. Those are the colors drawn
only after the diagnostic reaches its SEC stores. **M2 is confirmed on this
Go.** Eye coverage, exact geometry and red/blue byte order were not measured.
The owner reported returning to Android. ADB then confirmed boot completion
on the same unit and slot. All 136,314,880 bytes of `boot_a/b` and `aboot_a/b`
were read again and each SHA-256 matched both the preflight and the preserved
backup. [Session evidence](evidence/sec-visual-transfer-20261118.json)

## Earlier, separate experiment

The previous experiment accepted one temporary diagnostic image and showed
only a static logo. It did not prove EDK2 execution. Android was recovered;
boot A/B and aboot A/B hashes matched the original backups. No partition-write
command was issued by the project. This is historical evidence, not a test of
the new implementation.
