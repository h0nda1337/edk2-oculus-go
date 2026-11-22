# Página propia de 4096 bytes para UFS

## Qué intervalo pertenece a EDK2

En el perfil SEC de diagnóstico, el FD se carga en `0x80080000`. La segunda página de su ventana de datos de 16 KiB empieza en el offset `0x3C1000`. EDK2 reserva para la prueba el intervalo CPU `[0x80441000, 0x80442000)`. Los ocho bytes del extremo superior empiezan en `0x80441FF8`. El volumen de firmware y la pila están fuera de esta ventana. El perfil de Shell tiene otra distribución y requiere su propia asignación en DXE. [Distribución de ambos perfiles](../OculusGoPkg/OculusGoPkg.fdf)

El Go ya recibió la capacidad del LUN 4 mediante DMA de ocho bytes en `0x918EEF80`, dentro de la asignación de colas de LK. En otro arranque, la CPU copió ese resultado a cada página de la ventana. El búfer de cabecera de LK en `0x918D7E80` devolvió dos muestras enteras de ceros. La prueba actual utiliza una página del propio FD para establecer quién puede usar el intervalo por CPU durante el diagnóstico. La dirección de bus de esa página en Pacific sigue **UNKNOWN**. [Transferencia física](evidence/ufs-data-transfer-20261121.json) · [Copia por CPU](evidence/ufs-bounce-transfer-20261121.json) · [Censo de ceros](evidence/ufs-zero4k-transfer-20261121.json)

## Dos transferencias de capacidad

Cada respuesta de `READ CAPACITY(10)` mide ocho bytes. En QEMU, el LUN 4 devolvió `00 11 FF FF 00 00 10 00` en ambos extremos. Los campos big-endian dan último LBA inclusivo `0x0011FFFF` y bloque lógico de 4096 bytes.

| Entorno | CPU inicial / final de la prueba | Bus inicial / final de la prueba | Cómo se obtuvo |
| --- | --- | --- | --- |
| AAVMF y drivers UFS EDK2 | `80441000 / 80441FF8` | `80441000 / 80441FF8` | El test reservó cuatro páginas por Boot Services, usó la segunda y registró el valor devuelto por el proveedor UFS en cada mapeo de ocho bytes. |
| PCI UFS de QEMU detrás de SMMUv3 | `80441000 / 80441FF8` | `88000000 / 88000FF8` | El PRDT contenía los IOVA de un mapeo explícito de una página. Se verificaron los bytes recibidos, el resto de la ventana y la RAM ubicada en el valor numérico del IOVA. |
| Pacific, tras LK | `80441000 / 80441FF8` | **UNKNOWN / UNKNOWN** | Falta una correspondencia de bus vigente para este controlador en este arranque. |

El control negativo del proveedor rechazó el mapeo del extremo final antes del envío. Las cuatro páginas conservaron su patrón de guarda. Un LUN con un bloque menos produjo `Volume Corrupt`. Las trazas de ambos entornos registraron únicamente comandos SCSI de capacidad y cero operaciones de sector. La cobertura de los extremos alcanza 16 bytes distintos dentro de la página. [Proveedor EDK2 y control negativo](evidence/ufs-owned-page-provider-20261121.json) · [Traducción de bus independiente](evidence/ufs-owned-page-translated-20261121.json)

## Resultado de UFS_HEAP4K en Pacific

El Go mostró `UFS HEAP NO PAGE`. En el slot 0, LK había registrado la dirección de bus de descriptor `0x918FDF00`. El desplazamiento de 32 bytes sitúa la respuesta en `0x918FDF20`, dentro de la página `[0x918FD000, 0x918FE000)`. Tras dos recorridos estables de cuatro nodos, ningún intervalo libre tenía espacio útil que cubriera **esa página entera**. El operador confirmó que las etiquetas `FREE` y `END` estaban ausentes. El panel sólo las dibuja cuando encuentra un intervalo que cumpla el criterio. [Transcripción y huellas del arranque temporal](evidence/ufs-heap4k-transfer-20261121.json)

Esta prueba pasiva descarta la candidatura de esa página en el arranque observado. La disponibilidad de otras páginas del montículo y la traducción DMA de la página propia en `0x80441000` siguen por determinar.

En el ensayo posterior, `UFS_PRDT` observó el mismo puntero UCD en el slot 0 y cero entradas PRDT. La muestra carecía de una dirección de datos que comparar con la página propia. [Panel del Go](evidence/ufs-prdt-transfer-20261121.json) · [Interpretación y control en QEMU](UFS_NATIVE_PRDT.md)

## Cómo se interpreta el panel

La copia original de `aboot_a` del Go muestra que LK reserva el descriptor de comando UFS con alineación de 128 bytes, escribe la dirección en el descriptor de transferencia y codifica la respuesta a 32 bytes de la base. En la ruta de finalización devuelve la asignación a su montículo. La lista de intervalos libres tiene la cabecera en `0x918E3170` y almacena anterior, siguiente y tamaño en las primeras tres palabras de cada nodo. [Auditoría reproducible del ELF](../tools/audit_lk_response_heap.py) · [Direcciones y huella de la copia](evidence/ufs-response-heap-stock-20261121.json) · [Límites iniciales del montículo](evidence/ufs-header-lifetime-20261121.json)

`UFS_HEAP4K` es una sonda pasiva para una posible segunda página. Lee el último descriptor del slot 0 en la cola conocida y dos instantáneas de la lista de LK. Valida el estado de las colas, los enlaces, tamaños, límites del montículo y la estabilidad del descriptor. Excluye los metadatos y las asignaciones conocidas de las colas. Lee la lista usando direcciones CPU ya acotadas. La dirección de bus del descriptor sólo se usa como número para la comparación.

| Fila / resultado | Interpretación |
| --- | --- |
| `UCD` / `RSP` / `PAGE` | Dirección de bus guardada en el descriptor, dirección calculada de respuesta y página que contiene esa respuesta. |
| `NODES` / `FREE` / `END` | Número de intervalos comprobados, inicio del nodo que cubre los 4096 bytes y límite exclusivo del intervalo. |
| `HEAP CANDIDATE` | Una página con la misma dirección numérica cabe íntegra en un intervalo libre observado. Queda por demostrar adónde traduce el UFS ese número y quién puede reservar la página durante una transferencia. |
| `SHARED QUEUE PAGE`, `HEAP NO PAGE` | La dirección comparte página con las colas o falta un intervalo libre utilizable. |
| `STOP`, `FAULT`, `CHANGED` | La sonda no pudo validar el descriptor, el estado de las colas o la lista. El último campo identifica el punto de parada. |

El control con alias de QEMU produce el mismo panel `CANDIDATE` que el caso con mapeo identidad. El UFS escribió su respuesta NOP en RAM distinta en los dos casos. Esto delimita exactamente lo que demostraría el panel del Go. La imagen enlaza únicamente SEC y carece del transporte para enviar comandos UFS. [Trece ejecuciones del FD y paneles](evidence/ufs-heap4k-fd-qemu-20261121.json) · [Revisión del arranque temporal](evidence/ufs-heap4k-review-20261121.json)

Para avanzar al LBA 1 físico hace falta obtener o establecer un mapeo de una página reservada para EDK2 durante todo el comando y validar los dos extremos con la capacidad conocida. La lectura del sector completo será una medición independiente con su propia comparación contra el respaldo.

## Reproducción sin visor

Desde Debian, después de preparar las dependencias del proyecto, estos comandos generan los dos informes de capacidad y el FD pasivo. El ensayo del FD necesita el DTB de ejecución conservado localmente y el ELF sin despojar del mismo build.

```sh
bash scripts/build-qemu-ufs-drivers.sh
python3 -B tests/ufs_capacity_map_qemu.py --owned-page --report build/owned4k-provider.json
python3 -B tests/ufs_owned_bus_qemu.py --report build/owned4k-nonidentity.json
bash scripts/build.sh DEBUG 8 UFS_HEAP4K
python3 -B tests/ufs_heap_fd_qemu.py --fd "$FD" --sec-elf "$SEC_ELF" --runtime-fdt "$RUNTIME_DTB" --report "$BUILD/QEMU.json" --static-report "$BUILD/STATIC.json"
```

En el host del proyecto, `python -B tools/run_ufs_heap4k_once.py` comprueba la imagen, el FD, el origen de los archivos compilados, los ensayos y la evidencia anterior, todo sin acceder al USB.
