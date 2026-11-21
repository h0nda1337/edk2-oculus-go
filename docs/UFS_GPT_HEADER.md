# Primera lectura de un bloque UFS en el búfer de cabecera de LK

**CONFIRMED en QEMU.** SEC recibió los 4096 bytes de la cabecera GPT primaria del LUN 4 por DMA en `[0x918D7E80, 0x918D8E80)`. El bloque coincidió byte por byte con la captura privada del visor. **CONFIRMED por CPU en el Go.** Dos lecturas completas al salir de Fastboot fueron idénticas. La dirección de bus efectiva y la lectura física del LBA 1 desde EDK2 siguen **UNKNOWN**. [Panel físico](evidence/ufs-buf4k-transfer-20261121.json) [Informe de QEMU](evidence/ufs-gpt-header-fd-qemu-20261121.json) · [Auditoría del binario de LK](evidence/ufs-header-buffer-stock-20261121.json)

## Por qué esta dirección

En el ELF original de `aboot_a`, las instrucciones entre `0x9183AE90` y `0x9183AEB4` preparan un puntero constante en R2, cargan la longitud desde `0x918E18D4` en R3 y llaman al lector de almacenamiento. A continuación se comparan los primeros ocho bytes con `ANDROID!`. El mismo destino aparece en otros dos sitios de llamada. En `0x91839200` la longitud es 2048 redondeada al tamaño de bloque, lo que da 4096 para la geometría medida. En la ruta UFS de LK el puntero del solicitante llega al primer PRD. En la inicialización del almacenamiento, ambos accesores de tamaño terminan leyendo el campo `+0x10` del contexto UFS. LK guarda los resultados en `0x918E18D4` y `0x918D8E84`. Las dos cabeceras originales de `boot` especifican páginas de 4096 bytes. [Auditor reproducible](../tools/audit_lk_header_buffer.py) · [Camino del puntero en LK](UFS_LK_DMA.md)

| Región | Intervalo o dirección | Uso |
| --- | --- | --- |
| Fragmento en la primera página | `[0x918D7E80, 0x918D8000)` | 384 bytes |
| Fragmento en la segunda página | `[0x918D8000, 0x918D8E80)` | 3712 bytes |
| Otra variable de LK | `0x918D8E84` | LK almacena aquí el resultado de su consulta de tamaño de bloque |
| Listas UTR y UTM | `0x918EE400` y `0x918EEC00` | Asignaciones independientes ya observadas en el Go |

El bloque está dentro de la BSS de LK y del intervalo de identidad CPU confirmado en el visor. El puntero está alineado a 128 bytes. Un tamaño de página distinto o un cambio entre dos lecturas impide que la sonda acepte la muestra. [Medición física del descriptor de LK](evidence/ufs-lk-map-transfer-20261121.json)

## Ensayo del sector

El firmware de modelo reutiliza las colas de LK y la ruta original de `READ CAPACITY(10)`. Tras verificar ocho bytes en el búfer de control, prueba los ocho primeros y los ocho últimos bytes del candidato. La SMMU virtual da acceso a las dos páginas del candidato y a la página de las colas. El caso positivo emite un solo `READ(10)` al LUN 4, LBA 1, longitud de un bloque. El backend es un archivo disperso de 4,5 GiB abierto en modo de sólo lectura con la cabecera privada en el segundo bloque. [Implementación SEC](../OculusGoPkg/SecMem/UfsGptModel.c) · [Banco QEMU](../tests/ufs_header_fd_qemu.py)

El banco observa el CDB, la PRDT, el estado y los 4096 bytes antes de que SEC recupere el control. Verifica las dos páginas completas, la página de las colas y el panel en ambos ojos. El CRC32 de los 92 bytes de la cabecera, con el campo CRC a cero, es `4C32247E`. El CRC32 del bloque completo es `DF7E0B12`. Se comprueban además la firma, la revisión, los límites del LUN y el espacio declarado para las entradas. La traza del modelo separa los comandos de capacidad de las lecturas efectivas de sectores. La matriz de entradas y el contenido de `splash` quedan para lecturas posteriores. [Registro del sector original](evidence/ufs-splash-physical-layout-20261120.json) · [Especificación UEFI 2.10, sección 5.3](https://uefi.org/specs/UEFI/2.10/05_GUID_Partition_Table_Format.html)

En EL1 y EL2 se observó un único bloque leído y cero escrituras por arranque positivo. Con la segunda página fuera del dominio DMA, QEMU devolvió `OCS=0` y `SCSI=0` en la consulta de capacidad del extremo alto, pero los ocho bytes esperados no llegaron. SEC se detuvo antes de emitir `READ(10)`. Otros casos rechazaron un CRC de cabecera incorrecto, un LBA alternativo fuera de la geometría esperada con CRC válido, y un cambio en el último byte del sector. Un búfer inicial sin la cabecera reconocida detuvo el modelo antes de emitir comandos. El banco usa el controlador PCI UFS y la SMMUv3 virtuales de QEMU. Los registros específicos de Pacific que el modelo no implementa se suministran a partir de capturas de la placa. [Resultados por caso](evidence/ufs-gpt-header-fd-qemu-20261121.json)

La reconstrucción de `UFS_DATA` y `UFS_BOUNCE` produjo FD idénticos byte por byte a sus compilaciones anteriores. También pasaron los diez casos previos de DMA de datos. QEMU emitió avisos de GLib sobre `g_timer_elapsed` al cerrar instancias. El banco comprobó el contenido de RAM, el panel y la traza de cada caso antes de aceptar el resultado.

## Medición física en el Go

La imagen temporal **`UFS_BUF4K`** se ejecutó en el Go. Este SEC lee por CPU el tamaño que dejó LK. Si vale 4096, toma dos muestras completas y compara todas sus palabras. El panel muestra `BUF`, `LKPG`, el CRC32 en `OLD`, la clasificación de la cabecera y `CPU ONLY`. `BOOT A` y `BOOT B` significan que coinciden la firma, el tamaño y el CRC32 con el respaldo correspondiente. `OTHER` también es una observación válida. La sonda carece de rutina de envío de comandos UFS. El intento de arranque temporal de esta imagen quedó consumido. [Código de la medición](../OculusGoPkg/SecMem/UfsHeaderBuffer.c) · [Pruebas de su FD](evidence/ufs-buf4k-fd-qemu-20261121.json) · [Revisión del paquete](evidence/ufs-buf4k-review-20261121.json)

El operador leyó `UFS BUF4K DONE`, `BUF 918D7E80`, `LKPG 00001000`, `OLD C71C0011`, `OTHER`, `TWO SAMPLES MATCH` y `CPU ONLY`. La comparación palabra por palabra demuestra igualdad entre las muestras durante la prueba. Un bloque de 4096 bytes en cero produce ese mismo CRC32. La imagen no comparó cada palabra contra cero. En QEMU se reprodujo el mismo panel con un bloque en cero y el perfil activo se detuvo en `STOP ORIGINAL` antes de enviar comandos. El valor del CRC por sí solo tampoco establece que LK haya cedido el búfer. [Panel físico](evidence/ufs-buf4k-transfer-20261121.json) · [Casos del modelo](evidence/ufs-gpt-header-fd-qemu-20261121.json)

## Reproducción sin USB

En Debian/WSL, desde la raíz del proyecto, definir `ABOOT`, `BOOT_A`, `BOOT_B`, `HEADER` y `DT` como las rutas a los respaldos originales, la cabecera primaria de 4096 bytes y el FDT de ejecución. Para cada compilación, `OUT` es el directorio de informe que imprime el build y `ELF` es el fichero de símbolos de su SEC.

```bash
python3 -B tools/audit_lk_header_buffer.py --aboot "$ABOOT" --boot-a "$BOOT_A" --boot-b "$BOOT_B" --gpt-header "$HEADER" --report build/ufs-header-buffer-stock.json
bash scripts/build.sh DEBUG 8 UFS_GPT_MODEL
python3 -B tests/ufs_header_fd_qemu.py --fd "$OUT/OCULUS_GO_DIRECT.fd" --sec-elf "$ELF" --runtime-fdt "$DT" --boot-a "$BOOT_A" --gpt-header "$HEADER" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"
bash scripts/build.sh DEBUG 8 UFS_BUF4K
# Actualizar OUT y ELF para el FD pasivo.
python3 -B tests/ufs_header_fd_qemu.py --passive --fd "$OUT/OCULUS_GO_DIRECT.fd" --sec-elf "$ELF" --runtime-fdt "$DT" --boot-a "$BOOT_A" --gpt-header "$HEADER" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"
```

En Windows, `python -B tools/run_ufs_buf4k_once.py` comprueba la imagen revisada y su procedencia sin usar USB. La imagen con el DT y las capturas originales se conservan en archivos locales.
