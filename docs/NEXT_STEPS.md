# Next steps

**Siguiente arranque físico.** Con el visor disponible, ejecutar el perfil temporal `UFS_HEAP4K` y transcribir el panel completo. Si aparece `CANDIDATE`, registrar por separado el puntero de bus y el intervalo CPU libre. Seguir con un mapeo verificable para una página reservada antes de probar DMA en Pacific. [Procedimiento e interpretación](UFS_OWNED_PAGE.md)

**UFS de Pacific.** El censo físico de `UFS_ZERO4K` confirmó los 4096 bytes en cero. Para avanzar hacia la GPT del LUN 4, falta identificar una región cuyo uso durante el comando corresponda a EDK2 y cuya dirección de bus pueda atribuirse al UFS del Go. En el búfer de LK siguen pendientes ambas comprobaciones. Con un destino respaldado por esa evidencia, la siguiente medición activa sería `READ CAPACITY(10)` de ocho bytes en cada extremo antes de leer el LBA 1. [Medición física](evidence/ufs-zero4k-transfer-20261121.json) · [Pruebas del mapeo en QEMU](UFS_GPT_HEADER.md)

**Aplicación del volumen confirmada en el Go.** DXE arrancó `ConsoleProbe.efi` y el operador leyó su fila verde «5 APP EFI 6» debajo de «1 EDK2 GO 2» en blanco. [Carga de la aplicación](DXE_APP.md) · [Registro físico](evidence/dxe-app-transfer-20261120.json)

BDS selecciona ahora la consola del Go y lanza la Shell ARM64 desde el volumen. El primer arranque físico mostró `hell>` por el ojo izquierdo y parte de la consola por el derecho. En el arranque temporal de la imagen de 24 × 12 celdas se leyeron el prompt entero y las líneas superiores con cada ojo. [Prueba en el visor](evidence/shell-centered-transfer-20261120.json) Para introducir comandos habrá que conectar una fuente de teclas a la entrada de ConSplitter. [Arranque normal y prueba visual](SHELL_BOOT.md)

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
