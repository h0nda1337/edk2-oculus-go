# Las cuatro páginas de EDK2 y el bus UFS de Pacific

**El Go confirmó una transferencia de ocho bytes a `0x918EEF80` en la asignación de LK. Las cuatro direcciones de bus directas de la ventana propia siguen siendo UNKNOWN.** La tabla distingue la dirección que devuelve el proveedor UEFI en la máquina virtual de lo que se pudo atribuir al controlador integrado del visor. [Panel físico anterior](evidence/ufs-data-transfer-20261121.json) · [Medición del proveedor UEFI](evidence/ufs-capacity-provider-20261121.json)

| Página | Base física CPU en Pacific | Bus para los primeros 8 bytes en QEMU/AAVMF | Bus directo en Pacific |
| ---: | --- | --- | --- |
| 0 | `0x80440000` | `0x80440000` | UNKNOWN |
| 1 | `0x80441000` | `0x80441000` | UNKNOWN |
| 2 | `0x80442000` | `0x80442000` | UNKNOWN |
| 3 | `0x80443000` | `0x80443000` | UNKNOWN |

## Evidencia de Pacific

- **LK.** El código de LK usa el puntero del solicitante en el primer PRD. El descriptor L2 de CPU observado en el visor es `0x0040000080400451` y cubre las cuatro páginas con una traducción de identidad. El resultado físico en la página de LK respalda la identidad como **HYPOTHESIS** para la ventana. Sigue faltando el enlace entre el maestro UFS y cada una de sus cuatro páginas. [Auditoría de LK y rangos de instrucciones](UFS_LK_DMA.md)
- **Árbol de dispositivo.** En el DT de ejecución, `/soc/ufshc@624000`, `/soc` y la raíz carecen de `iommus`, `iommu-map` y `dma-ranges`. Los doce estados de ancho de banda contienen dos pares de puertos, UFS→DDR (95→512) y CPU→configuración UFS (1→650). Son identificadores de interconexión. El árbol también describe una SMMU ANOC2 con `qcom,skip-init`. Ninguno de esos datos identifica un stream UFS o una traducción de esas cuatro páginas. [Auditoría reproducible](evidence/ufs-bus-pages-20261121.json) · [IDs de interconexión del kernel oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/include/dt-bindings/msm/msm-bus-ids.h)
- **Kernel original.** La configuración extraída de `boot_a` habilita SMMU, SWIOTLB y el driver UFS de plataforma. `DMA_API_DEBUG` e `IOMMU_DEBUG_TRACKING` están desactivados. El helper ARM64 `phys_to_dma()` devuelve la dirección física, pero el driver somete sus segmentos a `scsi_dma_map()`. Una dirección devuelta por el proveedor depende de la configuración activa. En Android el intervalo `0x80080000–0x812E0FFF` está ocupado por código del kernel e incluye las cuatro páginas. La sonda trabaja después del arranque temporal de EDK2, cuando las páginas pertenecen a su propio FD. [Auditoría y huellas de las capturas](evidence/ufs-bus-pages-20261121.json) · [API DMA ARM64](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/arch/arm64/include/asm/dma-mapping.h) · [Driver UFS](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufshcd.c)

## READ CAPACITY con el proveedor de DXE

La aplicación de pruebas reserva la dirección exacta en AAVMF y conecta los proveedores PCI UFS y SCSI de EDK2 al mismo controlador. Solicita ocho bytes al comienzo de cada página mediante `READ CAPACITY(10)` del LUN 4. Un observador temporal en la VM delega cada llamada a `Map` sin alterar parámetros ni resultados y registra el `DeviceAddress` devuelto durante la transferencia. La aplicación verifica los ocho bytes en la dirección CPU al regresar de `PassThru` y coteja los bytes de guarda de toda la ventana. Las direcciones de la tabla se observaron en llamadas de ocho bytes. El ensayo no midió la cobertura de una transferencia de 4096 bytes. [Aplicación de prueba](../tests/UfsSplashApp/CapacityMap.c) · [Proveedor PCI de EDK2](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Bus/Pci/UfsPciHcDxe/UfsPciHcDxe.c)

Los cuatro resultados fueron `00 11 FF FF 00 00 10 00`. Un LUN virtual con un bloque menos fue rechazado. El backend de solo lectura carece de contenido de disco. La traza UFS confirma que el único opcode SCSI fue `0x25` en el LUN 4 y que no hubo lecturas de sectores. El banco SEC independiente también verificó asignaciones contiguas y dispersas en la SMMU virtual, además del rechazo de una dirección equivocada. [Resultados de DXE](evidence/ufs-capacity-provider-20261121.json) · [Cobertura de traducciones en SEC](evidence/ufs-data-window-qemu-20261121.json)

## Próxima prueba física: UFS_BOUNCE

La sonda usa cuatro consultas independientes. En cada una, la única dirección de datos que se programa en la PRDT es `0x918EEF80`. Una vez completada la petición, SEC captura el contenido recibido, restaura las colas de LK y copia por CPU esos ocho bytes al inicio de la página elegida. Verifica todos los bytes de guarda antes y después de la copia. Al terminar muestra `UFS LK COPY DONE`, `COPY MASK 0000000F` y `FD DIRECT UNTESTED`. Este modo ofrece un camino indirecto para entregar respuestas pequeñas a búferes de EDK2. La capacidad de una transferencia completa de bloque y la dirección DMA directa de cada página permanecen pendientes. [Código SEC](../OculusGoPkg/SecMem/UfsData.c)

QEMU ejecutó el FD con una única página visible para DMA UFS, la de LK. El banco observó la PRDT y la respuesta en esa página en cada doorbell, verificó el instante previo a cada copia y leyó los cuatro destinos por CPU antes de la restauración. Una segunda geometría dejó la máscara en cero. En EL1 y EL2 se cotejaron las dos mitades del panel y la memoria final. El banco de este FD emite ocasionalmente una advertencia de GLib sobre `g_timer_elapsed`; la comprobación de datos, el framebuffer y la traza se verifican de forma independiente. [Informe del FD](evidence/ufs-bounce-fd-qemu-20261121.json)

Imagen temporal de 385 024 bytes. SHA-256 `64de5d43b9089bb2befaab37976a29744a92b6318edafd966b19a7ad484b5ad6`. Permanece bajo `local/`. El siguiente arranque requiere el visor; el verificador sin argumentos revisa el paquete sin usar USB. [Expediente del paquete](evidence/ufs-bounce-review-20261121.json)

## Reproducción

Desde la raíz en Debian/WSL, con los respaldos privados existentes:

```bash
python3 tools/audit_ufs_bus_pages.py --boot "$STOCK_BOOT" --runtime-fdt "$DT" --iomem "$IOMEM" --report build/ufs-bus-pages.json
bash scripts/build-qemu-ufs-drivers.sh
python3 -B tests/ufs_capacity_map_qemu.py --report build/ufs-capacity-provider.json
bash scripts/build.sh DEBUG 8 UFS_BOUNCE
python3 -B tests/ufs_bounce_fd_qemu.py --fd "$FD" --sec-elf "$ELF" --runtime-fdt "$DT" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"
```

`IOMEM` es la captura de Android, `DT` es su FDT de ejecución, `FD` y `ELF` son la imagen y los símbolos del perfil `UFS_BOUNCE`, y `OUT` es el directorio del informe. Para verificar la revisión exacta ya empaquetada desde Windows, ejecutar `python -B tools/run_ufs_bounce_once.py`.
