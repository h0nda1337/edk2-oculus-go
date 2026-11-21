# DMA de datos del LUN 4 antes de leer la GPT

La sonda `UFS_DATA` usa `READ CAPACITY(10)` en el LUN 4. La respuesta ocupa ocho bytes. Los primeros cuatro codifican el último LBA y los cuatro siguientes el tamaño del bloque, ambos en big-endian. La medición de Android predice `00 11 FF FF 00 00 10 00`, equivalente a 1 179 648 bloques de 4096 bytes. El comando consulta geometría sin seleccionar ningún sector. [Inventario del LUN](evidence/ufs-splash-physical-layout-20261120.json)

## Qué cuenta como prueba

SEC envía el comando por el slot 1 de las colas UFSHCI 1.1 heredadas de LK y verifica el tag, el LUN, el estado SCSI, el resultado del descriptor, los bytes recibidos y los límites de memoria. Una entrada PRDT de ocho bytes sitúa el destino de datos en una dirección de bus independiente del UCD. El control inicial usa `0x918EEF80`, en la misma página que recibió el NOP físico. Una respuesta de unidad recién reiniciada admite un solo reintento para esa petición. Cada finalización normal repone los descriptores de LK y coteja las dos asignaciones completas. Ante una cola aún activa o memoria ajena al destino que haya cambiado, el panel muestra `HOLD` y la sonda deja de enviar comandos. [Implementación](../OculusGoPkg/SecMem/UfsData.c) · [NOP físico](evidence/ufs-nop11-transfer-20261121.json)

Para probar la ventana, el llamador debe proporcionar las cuatro direcciones de bus de esa asignación. SEC coloca un patrón en los 16 KiB y pide una respuesta en cada una de las posiciones de CPU siguientes.

| Página | Primer byte de la muestra | Máscara acumulada al recibir la geometría correcta |
| ---: | --- | --- |
| 0 | `0x80440000` | `0x1` |
| 1 | `0x80441FF8` | `0x3` |
| 2 | `0x80442000` | `0x7` |
| 3 | `0x80443FF8` | `0xF` |

Se verifican todos los bytes de guarda y, al completar las cuatro transferencias, se restaura y coteja la ventana. La cobertura son cuatro muestras de ocho bytes. Un bloque de 4096 bytes sigue siendo una prueba aparte.

## Resultados de QEMU

El banco conecta un controlador UFS PCI de QEMU a una SMMUv3 con traducciones explícitas y a un LUN 4 virtual de solo lectura con el tamaño medido. Reproduce las señales de la placa que necesita SEC. El controlador emulado interpreta los descriptores y ejecuta el DMA.

- La prueba del FD ejecuta el mismo binario ARM64 en EL1 y EL2. Con la entrada de Pacific se ve `UFS LK DATA DONE`. Para ensayar la ventana en ese binario, el depurador suministra en la entrada de la función el mapa que el banco programó en la SMMU virtual. El banco lee los ocho bytes en la RAM de destino inmediatamente después del doorbell y antes de que SEC vuelva a ejecutarse. El panel de los dos ojos llega a `UFS FD DATA DONE` y máscara `F`. [Resultados del FD](evidence/ufs-data-fd-qemu-20261121.json)
- El banco de diez casos cubre mapas contiguos y dispersos, una página denegada, una traducción a la página equivocada, dirección física usada como dirección de bus, lista parcial o duplicada, ventana ocupada y geometría distinta. Al faltar la cuarta traducción, QEMU devuelve éxito de transporte y estado SCSI cero, pero los ocho bytes siguen en `A5`. La sonda conserva máscara `7` y muestra `STOP CAPACITY`. [Diez casos](evidence/ufs-data-window-qemu-20261121.json)

QEMU 10.0.13 también emitió una advertencia de GLib sobre `g_timer_elapsed` al ejecutar el banco del FD. Las cuatro máquinas alcanzaron el punto de parada, los datos se observaron en RAM y la traza de comandos se cotejó en cada caso.

## Resultado físico en Pacific

El operador transcribió `UFS LK DATA DONE`, `OCS 00000000`, `SCSI 00000000`, `LAST 0011FFFF` y `SIZE 00001000`. La sonda había llenado de `A5` los ocho bytes de destino en `0x918EEF80`. La respuesta recibida equivale a 1 179 648 bloques de 4096 bytes, un total de 4 831 838 208 bytes (4,5 GiB). Coincide con el inventario independiente de Android. El encabezado final indica que SEC repuso y cotejó las dos asignaciones de LK. [Panel completo y registro del arranque](evidence/ufs-data-transfer-20261121.json) · [Geometría de Android](evidence/ufs-splash-physical-layout-20261120.json)

El panel mostró `PAGE MASK 00000000` y `WINDOW DMA UNTESTED`. El alcance físico se limita a los ocho bytes en la página de LK. El acceso DMA a las cuatro páginas en `0x80440000` sigue **UNKNOWN**. La lectura previa de sysfs identificó el driver `ufshcd` para `624000.ufshc`. El grupo IOMMU y las máscaras DMA quedaron sin determinar con esa interfaz. Falta vincular las direcciones de bus de la ventana con el estado heredado de LK antes de probarlas en el Go. [Colector Android](../tools/collect_ufs_dma_sysfs.py) · [Evidencia de LK](UFS_LK_DMA.md)

La imagen Android v0 ocupa 385 024 bytes y su SHA-256 es `50f52e6b7ce079abc81ef0405304606936bd063594272ae4afb9497eba6934de`. El empaquetador volvió a extraer y cotejar el FD completo y el DTB de Pacific. El perfil carga únicamente SEC. La consola Shell y el acceso a sectores corresponden a etapas posteriores. El paquete se verifica localmente con `python -B tools/run_ufs_data_once.py`. En la sesión atendida se verifican los cuatro hashes de arranque, se envía únicamente la imagen temporal y se transcribe el panel antes de regresar a Android. [Revisión del paquete](evidence/ufs-data-review-20261121.json)

El operador volvió a Android y ADB confirmó el arranque del mismo Go en el slot `_a`. Los SHA-256 de `aboot_a`, `aboot_b`, `boot_a` y `boot_b` coincidieron con la lectura previa y los respaldos originales. Las cuatro particiones sumaron 136 314 880 bytes en cada comparación. [Verificación del retorno](evidence/ufs-data-transfer-20261121.json)

## Reproducción sin visor

Desde Debian/WSL en la raíz, compilar con `bash scripts/build.sh DEBUG 8 UFS_DATA`. Ejecutar `python3 -B tests/ufs_data_qemu.py --report build/ufs-data-window.json`. Para la prueba del FD, usar `python3 -B tests/ufs_data_fd_qemu.py --fd "$FD" --sec-elf "$ELF" --runtime-fdt "$DT" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"`. FD es el archivo de la compilación, ELF es `OculusGoUfsData.dll` del directorio DEBUG del módulo, DT es el FDT de ejecución archivado y OUT el directorio del informe. Las capturas y las imágenes permanecen en el equipo del propietario.
