# Cómo entrega LK la memoria a UFS

**CONFIRMED en el binario original.** El inicializador de UFS entrega a los registros del host los punteros bajos de sus propias listas, extendidos con cero. El camino de preparación de datos también conserva el puntero recibido en la primera entrada PRD. LK configura por separado una traducción para la CPU ARM de 32 bits. La accesibilidad desde UFS de `[0x80440000, 0x80444000)` en el Go sigue **UNKNOWN**. [Informe de LK](evidence/ufs-lk-dma-stock-20261121.json) · [Medición anterior de las colas](evidence/ufs-queues-transfer-20261121.json)

## Prueba en el Oculus Go

El operador leyó `UFS LK MAP MATCH`. HBA mostró `0x00624000`. Las bases de las listas guardadas en el contexto de LK coincidieron con UTRLBA y UTMRLBA al final del ensayo. En dos muestras, la entrada L1 señaló la tabla de segundo nivel en `0x918E5000`. [Lectura del visor](evidence/ufs-lk-map-transfer-20261121.json)

| Fila | Descriptor retenido | Rango de identidad para la CPU, fin exclusivo |
| --- | --- | --- |
| FD | `0x0040000080400451` | `[0x80400000, 0x80600000)`, incluye los 16 KiB en `0x80440000` |
| LK | `0x0000000091800451` | `[0x91800000, 0x91A00000)`, incluye UTR en `0x918EE400` y UTM en `0x918EEC00` |

La última fila fue `DMA WINDOW UNTESTED`. Queda pendiente comprobar la ruta del maestro UFS hasta la ventana. La sonda terminó antes de emitir un NOP o leer el LUN 4. Android volvió a arrancar en el mismo Go, en el slot `_a`. Los hashes SHA-256 de ambas particiones `aboot` y ambas `boot` coincidieron con los respaldos antes y después de la prueba. [Informe de la prueba y del retorno](evidence/ufs-lk-map-transfer-20261121.json)

## Qué se pudo reconstruir

| Dirección en el ELF original | Observación |
| --- | --- |
| `0x91800ED0–0x91800EE8` | La placa pasa el contexto `0x918E3230` y guarda la base del host `0x00624000` en el campo `+4`. |
| `0x9182CEE4`, `0x9182CF4C`, `0x9184DAA0` | Los dos caminos solicitan 1024 bytes por lista. La envoltura devuelve el puntero de la asignación que también entrega a mantenimiento de caché. Los 640 bytes calculados para ocho descriptores de tareas caben en su asignación de 1024 bytes. |
| `0x9182BA50–0x9182BB00` | El contexto guarda las dos bases en `+0x178` y `+0x1B8`. Tras inicializar el enlace, LK carga los punteros bajos de esos campos, escribe UTRLBA y UTMRLBA, escribe cero en sus mitades altas y arranca las listas. |
| `0x9182C054`, `0x9182C0C4`, `0x9182C240` | Para acceder a un slot por CPU usa la base de UTR más índice × 32. Empaqueta la dirección de la asignación del UCD en el UTRD. El primer PRD recibe directamente el puntero de datos de 32 bits con parte alta cero, y una longitud menos uno. |
| `0x9183476C`, `0x91834794`, `0x9182C12C` | En su camino ARM32, LK limpia/invalida por dirección virtual en pasos de 128 bytes y usa barreras antes y después del doorbell. La sonda SEC admite entrada con caché de datos desactivada. |
| `0x91835194–0x918351C4`, `0x91834E58` | LK construye las tablas largas, escribe TTBR0 con `0x918E4000` y configura TTBCR con `0x80000500`. Su reserva inicial de tablas de segundo nivel contiene tres páginas desde `0x918E5000`. |
| `0x91804304`, `0x9180422C`, `0x91898D40` | Para la rama de tamaño de RAM de 3 GiB, el constructor recibe el mismo origen virtual y físico `0x80000000` para 88 MiB. La entrada fija de 4 MiB que empieza en `0x91800000` también es identidad. La imagen verifica qué quedó realmente en las tablas. |
| `0x91801468`, `0x9183B0C0`, `0x9183B190` | En el camino de lectura del cuerpo de la imagen de arranque, el área intermedia empieza en `0x95E00000`. La carga final de nuestro FD por LK, por sí sola, no acredita una transferencia UFS a la ventana de EDK2. |

El DT capturado del Go carece de `iommus` en el nodo UFS y de `dma-ranges` en dicho nodo y sus antecesores. El enlace entre la dirección que LK entrega, la traducción efectiva del maestro UFS y los permisos sobre la ventana de EDK2 requiere evidencia adicional. [Datos del hardware](UFS_QUEUES.md) · [Referencias y procedencia](REFERENCES.md)

## Acceso efectivo en QEMU

El programa ARM64 arranca sobre un host PCI UFS ya habilitado, con las bases numéricas observadas en Pacific y la lista de transferencias iniciada. El programa comprueba que esté libre, detiene sólo esa lista, instala temporalmente un UTRD propio y emite un NOP OUT sin PRDT. Al recibir NOP IN comprueba el identificador, el estado OCS y la respuesta, y restaura la base y el estado de marcha. Cuatro arranques independientes sitúan el área de respuesta de 32 bytes justo al final de cada página. El banco compara cada byte de los 16 KiB, la página de las listas heredadas y dos páginas de guarda. Así cubre puntos concretos de las cuatro páginas. [Código ARM64](../tests/ufs_lk_nop_guest.c) · [Banco y resultados](evidence/ufs-lk-nop-qemu-20261121.json)

La página cero se ensaya dos veces en una VM con la misma topología SMMUv3. La política de paso directo devuelve el NOP IN y el control negativo activa el rechazo de DMA. La CPU sigue escribiendo y leyendo la misma RAM. UFS deja el doorbell pendiente, la respuesta conserva el patrón inicial y OCS permanece en 15. Al vencer el plazo, el programa conserva la base y los descriptores en uso hasta apagar la VM. Otros cuatro casos ejercitan un dominio sin identificar, una lista parada, una base heredada distinta y una ventana ocupada. En conjunto hubo cuatro NOP completados, cero órdenes SCSI y cero consultas UFS. La finalización normal conserva los bits de estado pendientes y puede añadir el bit de finalización de transferencia.

QEMU 10.0.13 devuelve `0x400` para versión del host y devuelve cero al leer Run/Stop de la lista de tareas incluso después de escribir uno. En el Go esos registros dieron `0x00010100` y uno, respectivamente. El invitado del banco PCI tiene comprobaciones propias para ese hardware virtual. Está excluido del FD de Pacific. [Sonda física anterior](UFS_HANDOFF.md) · [Controlador virtual](https://github.com/qemu/qemu/blob/v10.0.0/hw/ufs/ufs.c)

## Imagen temporal UFS_LK_MAP

Esta imagen SEC califica el EVT, los relojes, HCI, las dos colas y la ventana de 16 KiB con las comprobaciones de la [sonda anterior](UFS_QUEUES.md). Muestrea dos veces los campos del contexto de LK y las entradas de tabla que cubren la ventana y las colas. Sólo permite la entrada L1 en su BSS y tres posibles páginas L2. Comprueba de nuevo las bases del HCI antes de emitir el resultado. Los únicos destinos de escritura de la sonda son su pila y el panel heredado. Las lecturas cubren los campos del controlador y las tablas de RAM. El panel indica el resultado antes de cualquier acceso al medio.

El mismo FD destinado al Go pasó 30 casos en QEMU, 15 en EL1 y 15 en EL2. Se comprobaron ambas mitades del panel, el rechazo de tablas fuera de la reserva, bloques ausentes o con otra dirección de salida, cambios entre muestras, una lista ocupada y una ventana sucia. La inspección del FD identificó el único módulo SEC y verificó los 16 KiB iniciales. [Resultados del firmware](evidence/ufs-lk-map-qemu-20261121.json) · [Inspección estática](evidence/ufs-lk-map-static-20261121.json)

| Fila del panel | Qué significa al transcribirla |
| --- | --- |
| `HBA`, `UTR`, `UTM` | Base del HCI guardada por LK y pares alto/bajo de las bases guardadas en RAM. Se cotejan con los registros reales. |
| `L1` | Descriptor que eligió la tabla de segundo nivel para ambas direcciones. |
| `FD`, `LK` | Descriptores completos para el bloque que contiene los 16 KiB y para el bloque de las colas. Cada fila muestra alto, luego bajo. |
| `UFS LK MAP    MATCH` | Ambas muestras coincidieron, los punteros concuerdan con HCI y las tablas retenidas describen identidad CPU en los dos bloques. |
| `MISMATCH`, `UNKNOWN`, `CHANGED` o `FAULT` | El campo indicado delimita la discrepancia. Conviene copiar también las filas disponibles. |
| `DMA WINDOW UNTESTED` | La ventana sigue pendiente de una respuesta del controlador físico. |

Para una prueba física activa se debe establecer el destino del DMA UFS sobre esta asignación y mantener sus descriptores propios mientras exista una solicitud pendiente. El primer intercambio de dispositivo previsto es un NOP, antes de cualquier lectura del LUN 4. [Procedimiento de recuperación](RECOVERY.md)

## Reproducción offline

```bash
python3 tools/audit_lk_ufs_dma.py --aboot "$stock_aboot_a" --report "$out/stock.json"
python3 tests/ufs_lk_nop_qemu.py --report "$out/nop.json"
bash scripts/build.sh DEBUG 8 UFS_LK_MAP
elf=Build/OculusGoUfsLkMap/DEBUG_GCC5/AARCH64/OculusGoPkg/SecMem/UfsLkMap/DEBUG/OculusGoUfsLkMap.debug
python3 tests/ufs_lk_map_qemu.py --fd "$run/OCULUS_GO_DIRECT.fd" --sec-elf "$elf" \
  --runtime-fdt "$runtime_fdt" --report "$run/QEMU.json" --static-report "$run/STATIC.json"
python3 tools/run_ufs_lk_map_once.py
```

`stock_aboot_a` y `runtime_fdt` designan capturas privadas existentes. `out` es un directorio de resultados y `run` es el que imprime la compilación. El último comando verifica el expediente de la imagen revisada sin contactar el USB. [Pruebas del FD](evidence/ufs-lk-map-qemu-20261121.json) · [Revisión de la imagen](evidence/ufs-lk-map-review-20261121.json)
