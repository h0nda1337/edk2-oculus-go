# UFS desde la entrega de LK hasta una dirección DMA comprobable

La página física de CPU `0x80441000` pertenece a EDK2 en el perfil de diagnóstico. La última transferencia que dejó LK en el slot 0 tenía cero entradas PRDT. Su puntero `0x918FDF00` identifica un descriptor, por lo que aún falta la dirección que el UFS de Pacific usaría para los datos de la página. Estado **UNKNOWN**. [Panel físico de UFS_PRDT](evidence/ufs-prdt-transfer-20261121.json)

## Descubrir la dirección antes de entregarla a UFS

En QEMU se puede identificar el emisor PCI de UFS y observar el dominio SMMUv3 que controla el banco de pruebas. El observador lee la configuración en uso y recorre sus tablas buscando las hojas que traducen a la página física de EDK2. Exige que exista una sola correspondencia, que tenga permiso de escritura DMA y que cada tabla esté dentro de la memoria reservada para el ensayo. Las tablas se preparan antes de la prueba y permanecen fijas durante el recorrido y la transferencia. Este observador de qtest implementa únicamente el perfil S2 con hojas de 4 KiB configurado en esta máquina. [Código](../tests/ufs_discover_iova_qemu.py) · [Informe completo](evidence/ufs-reverse-s2-qemu-20261121.json)

| Mapa de la VM | Bus descubierto, primer y último destino de ocho bytes | Resultado en la RAM física de la CPU |
| --- | --- | --- |
| A | `0x81673000` y `0x81673FF8` | En `0x80441000` y `0x80441FF8` llegaron los bytes `00 11 FF FF 00 00 10 00`. |
| B, con la tabla de streams y la raíz reubicadas | `0x88AD0000` y `0x88AD0FF8` | Misma respuesta en ambos extremos. Las guardas y la RAM ubicada en el valor numérico del bus conservaron sus bytes. |
| Diez controles negativos | Ninguna dirección admitida | Cero comandos UFS. Incluyen página ausente, dos alias, otro stream, permisos insuficientes y tablas fuera de la asignación. |

El dispositivo virtual devolvió la capacidad del LUN 4. Cada respuesta cubre ocho bytes. El contenido y CRC de un sector de 4096 bytes quedan para una prueba posterior. [Resultados por ejecución](evidence/ufs-reverse-s2-qemu-20261121.json)

Un segundo ensayo, sólo en QEMU, comprobó el sentido contrario. La CPU alternó dos cabeceras de ocho bytes. La respuesta del modelo SCSI cambió con la cabecera cuando UFS leía el extremo correcto de la página, y permaneció fija cuando leía un alias distinto. QMP confirmó cero lecturas, escrituras y vaciados del medio virtual. Las páginas de parámetros conservaron el mismo hash. Este experimento usa el comportamiento concreto de `scsi-hd` de QEMU y se ejecuta en el host. [Ensayo](../tests/ufs_outbound_witness_qemu.py) · [Resultados](evidence/ufs-outbound-qemu-20261121.json)

## Qué puede medir el Go en el próximo arranque

El firmware RPM original del Go identifica por nombre cuatro ramas del controlador global de relojes (GCC) y el registro de alimentación del dominio AGGRE2. El auditor verifica el ELF contra el SHA-256 de la partición respaldada, localiza cada registro y contrasta los campos con cuatro controles AGGRE0 del kernel oficial. El DT de Pacific describe una SMMU ANOC2. El identificador de stream del UFS y el modo de traducción que empleaba LK siguen pendientes. [Auditoría del RPM y fuentes del kernel](evidence/ufs-route-clocks-stock-20261121.json) · [Evidencia de topología](UFS_NATIVE_PRDT.md)

`UFS_ROUTE_CLOCKS` captura hasta cinco valores de 32 bits del GCC después de validar el DT de Pacific EVT. La imagen SEC usa la CPU y el framebuffer heredado. El transporte UFS, las tablas de traducción y los sectores del medio quedan fuera de esa captura. El panel presenta los valores crudos de una lectura secuencial.

| Fila | Dirección CPU en el GCC | Qué representa |
| --- | --- | --- |
| DOM | `0x00383004` | Alimentación AGGRE2. Bit 31 indica encendido y bit 0 indica solicitud de colapso por software. |
| NAX | `0x00383008` | Rama AXI de AGGRE2 hacia SNOC. |
| NAH | `0x0038300C` | Rama AHB de AGGRE2 hacia CNOC. |
| SAX | `0x0038301C` | Rama AXI de la SMMU de AGGRE2. |
| SAH | `0x00383020` | Rama AHB de la SMMU de AGGRE2. |

`CLOCKS SAMPLED` indica que se obtuvieron las cinco lecturas. Para las cuatro ramas, el nibble superior 0 o 2 indica reloj activo, 8 indica parado y los otros valores quedan sin clasificar. `STOP DOM` conserva la lectura si el dominio figuraba apagado o si había una solicitud de colapso. Ambos bits pueden estar a uno por votos de alimentación de otros clientes. `INVALID` indica una lectura de todos unos y `FAULT` una excepción durante la lectura. Conviene copiar la cabecera y todas las filas visibles, incluida `FD BUS UNKNOWN`. [Driver de relojes](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/clk/msm/clock-local2.c#L668-L705) · [Driver de alimentación](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/clk/msm/gdsc.c#L128-L137)

Incluso con las cuatro ramas activas, para atribuir una dirección a Pacific todavía se necesita identificar el stream del maestro UFS y su dominio o una correspondencia DMA aportada por el proveedor del dispositivo en ese mismo arranque. Una rama parada o en transición deja pendiente comprobar si el bloque era accesible en ese instante. Una vez establecida la correspondencia, la primera transferencia destinada a la página será `READ CAPACITY(10)` en sus dos extremos. Después podrá evaluarse la lectura del LBA 1. [Prueba del destino incorrecto con estado SCSI de éxito](UFS_NATIVE_PRDT.md)

## Reproducir sin visor

Desde la raíz del repositorio en Debian con QEMU 10.0.13 y las herramientas del proyecto:

```sh
python3 -B tests/ufs_discover_iova_qemu.py --report /tmp/ufs-reverse.json
python3 -B tests/ufs_outbound_witness_qemu.py
bash scripts/build.sh DEBUG 8 UFS_ROUTE_CLOCKS
python3 -B tests/ufs_route_clocks_fd_qemu.py --fd "$FD" --sec-elf "$SEC_ELF" --runtime-fdt "$RUNTIME_DTB" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"
```

`OUT` es el directorio del build recién generado, `FD` su `OCULUS_GO_DIRECT.fd`, `SEC_ELF` el ELF de depuración de ese mismo build y `RUNTIME_DTB` el árbol de ejecución respaldado de Pacific. La verificación offline del paquete exacto se ejecuta con `python -B tools/run_ufs_route_clocks_once.py`. [Registro del paquete](evidence/ufs-route-clocks-review-20261121.json) · [Ejecuciones del firmware en QEMU](evidence/ufs-route-clocks-fd-qemu-20261121.json)
