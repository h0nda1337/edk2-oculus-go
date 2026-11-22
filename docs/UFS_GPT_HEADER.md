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

## ¿Dejó LK libre el búfer?

**CONFIRMED en el binario original.** En la entrada de LK, el bucle de `0x918000E8` a `0x91800100` escribe cero en cada palabra de `[0x918CD2AC, 0x918E84AC)`. El búfer de 4096 bytes está enteramente dentro. Más adelante, la inicialización del asignador usa `[0x918E84AC, 0x91C00000)` para su área inicial. Esto explica por qué el búfer puede contener ceros desde el inicio, incluso sin una operación de liberación al final. El inventario posterior de Android cubre ambos extremos con una sola entrada `System RAM`. [Auditoría del ELF y de iomem](evidence/ufs-header-lifetime-20261121.json)

LK materializa la base en once pares de instrucciones revisados. Además de la lectura de la cabecera de Android, la ruta de información del sistema de archivos pasa dos direcciones interiores, `0x918D82F8` y `0x918D8308`, para presentar campos del volumen. La ruta de arranque temporal guarda en R5 el segundo argumento del handler `boot`, obtiene de ese argumento los campos de la imagen descargada y llama al traspaso en `0x9183D1BC`. La rama ARM64 prepara sus argumentos en otra zona, en `0x918D3000`. En esos tramos revisados no se identificó una cesión del búfer a EDK2. El análisis abarca rutas concretas y deja abiertas las referencias indirectas y la actividad de otros maestros. [Auditor reproducible](../tools/audit_lk_header_lifetime.py)

**UNKNOWN en el Go.** Falta establecer el uso exclusivo del intervalo durante la prueba y la traducción que conserva el maestro UFS para sus dos páginas. La región de RAM publicada posteriormente por Android y la tabla de traducción de CPU pertenecen a observaciones distintas de la vista DMA. Para una prueba activa hay que poder atribuir las dos direcciones de bus al búfer en ese arranque y su uso a EDK2 durante el comando. Otra vía es usar un búfer reservado por EDK2 con una asignación DMA verificable para ese controlador. [Evidencia del bus UFS de Pacific](UFS_BUS_PAGES.md)

## Censo de los 4096 bytes con UFS_ZERO4K

El nuevo SEC toma dos muestras por CPU. Al coincidir las 1024 palabras y mantenerse el tamaño de bloque, recorre cada byte de la copia, cuenta los distintos de cero y conserva el primer desplazamiento. El visor muestra `NZ` en hexadecimal y `FIRST NONE / ZERO EXACT` o `OFF / NONZERO`. Si las muestras difieren aparece `CHANGED BUFFER`. Un tamaño distinto de 4096 produce `STOP LKPG`. El FD pasivo carece de código de envío de comandos UFS. [Implementación](../OculusGoPkg/SecMem/UfsHeaderBuffer.c) · [Revisión de la imagen temporal](evidence/ufs-zero4k-review-20261121.json)

| Prueba sobre el FD en QEMU | Resultado |
| --- | --- |
| 4096 ceros a EL1 y EL2 | CRC32 `C71C0011`, `NZ 0`, `ZERO EXACT` |
| Un byte en los desplazamientos 0, 383, 384 o 4095 | Cada ejecución informó `NZ 1` y su desplazamiento exacto |
| Cinco bytes distintos de cero desde 382, a caballo entre páginas | Mismo CRC32 `C71C0011`, `NZ 5`, `OFF 0000017E`, `NONZERO` |
| Todos los bytes a `FF` | `NZ 00001000`, primer desplazamiento 0 |
| El banco altera el primer byte durante la primera muestra | `CHANGED BUFFER` |
| LK anuncia 2048 bytes | `STOP LKPG` |

Los diez casos cotejaron el panel, el intervalo completo con sus guardas y la página de colas. La traza de cada invitado mostró cero órdenes de la sonda. El NOP previo pertenece al banco que prepara el controlador virtual. QEMU emitió avisos GLib al cerrar instancias. Pasaron las comprobaciones de RAM, pantalla y traza. [Resultados del FD](evidence/ufs-zero4k-fd-qemu-20261121.json)

Por separado se repitieron los siete casos del perfil activo `UFS_GPT_MODEL`. Con la cabecera de Android conocida y ambas hojas del IOMMU virtual preparadas, `READ CAPACITY(10)` entregó `00 11 FF FF 00 00 10 00` en `0x918D7E80` y en `0x918D8E78`. Sin la segunda hoja, el segundo destino conservó el patrón del banco y el firmware terminó en `STOP CAPACITY` antes de leer el LBA 1. Con el búfer inicial lleno de ceros volvió a `STOP ORIGINAL` y envió cero comandos. El resultado coincide con el informe publicado de los siete casos. El uso de esos destinos DMA en el Go sigue pendiente. [Informe del perfil DMA](evidence/ufs-gpt-header-fd-qemu-20261121.json)

## Censo físico en el Go

El operador leyó las ocho filas del arranque temporal de `UFS_ZERO4K`. `LKPG 00001000` corresponde a 4096 bytes en `0x918D7E80`. Las dos lecturas por CPU coincidieron, y el recuento dio `NZ 00000000`, `FIRST NONE` y `ZERO EXACT`. El CRC32 fue `C71C0011`. El panel coincidió fila por fila con el caso de ceros de QEMU. El diagnóstico terminó en `CPU ONLY` y su único intento quedó consumido. La disponibilidad del búfer para EDK2 y el acceso DMA a los extremos siguen **UNKNOWN**. [Panel físico y registro del arranque](evidence/ufs-zero4k-transfer-20261121.json)

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

Para reproducir el nuevo perfil, `IOMEM` apunta al inventario original de Android. El banco de ceros sólo necesita el FDT verificado como entrada del dispositivo. Tras el build, actualizar `OUT` y `ELF` a los de `UFS_ZERO4K`.

```bash
python3 -B tools/audit_lk_header_lifetime.py --aboot "$ABOOT" --iomem "$IOMEM" --report build/ufs-header-lifetime.json
bash scripts/build.sh DEBUG 8 UFS_ZERO4K
python3 -B tests/ufs_header_fd_qemu.py --zero --fd "$OUT/OCULUS_GO_DIRECT.fd" --sec-elf "$ELF" --runtime-fdt "$DT" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"
```

En Windows, `python -B tools/run_ufs_zero4k_once.py` coteja localmente el paquete temporal, el FD, la procedencia y las pruebas.
