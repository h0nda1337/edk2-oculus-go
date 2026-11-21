# Next steps

**Siguiente prueba física: lectura de la consola.** Tras el patrón BGR observado en el Go, QEMU ya dibuja dos líneas mediante `gST->ConOut->OutputString()`. En un arranque temporal de `DXE_TEXT`, comprobar por separado si cada ojo puede leer ambas líneas y en qué orientación. [GOP en el visor](evidence/dxe-gop-transfer-20261120.json) · [Consola en QEMU](DXE_TEXT.md)

Para llegar al prompt, queda integrar la selección de consola en el arranque normal y lanzar la Shell ARM64 desde el volumen con los servicios de carga de imágenes. Para probar comandos hará falta además una fuente de entrada que publique `ConIn`.

**M2 is complete.** The stock loader accepted the reviewed temporary image
with both security indicators active. The owner saw the SEC pattern, Android
returned and each of the four boot partition hashes matched on readback.
[Physical evidence](evidence/sec-visual-transfer-20261118.json)

The DXE GOP driver passed 22 calls per exception level in QEMU using the
observed packed BGR layout. The Go's inherited framebuffer at SEC
displayed byte 0 as blue and byte 2 as red. The owner saw the C pattern after
the stack witness check. Android returned on slot A and all four partition
hashes matched the originals after the trial. The `SEC_C` attempt is consumed.
[Physical record](evidence/sec-c-transfer-20261118.json) · [BGR test results](evidence/gop-bgr-qemu-20261118.json)

1. The five-color `SEC_MEM` checkpoint was observed on the Go. Android
   recovered on slot A and all four hashes matched. Before enabling the
   normal stack and allocator, establish which RAM the firmware can own
   and write at handoff. The two completed loads cover 8 bytes each.
   [Trial record](evidence/sec-mem-transfer-20261118.json) · [Memory evidence](MEMORY_MAP.md)
   SEC_STACK subsequently verified two full-span patterns and nested C calls
   on a guarded 256 KiB stack inside the loaded image. The owner reported
   the five-color checkpoint. [Physical record](evidence/sec-stack-transfer-20261118.json)
2. SEC_MMU reached the red-center checkpoint with stage-1 translation active
   on the Go. The bounded in-FD workspace and compressed volume passed the SEC_DXE model.
   The physical SEC_DXE observation subsequently confirmed the handoff into DxeMain.
   [Attended MMU trial](evidence/sec-mmu-transfer-20261118.json)
3. The optional floating monitor can be prototyped offline over the BGR model
   with simulated orientation. [UEFI VR menu design](VR_MENU.md)
