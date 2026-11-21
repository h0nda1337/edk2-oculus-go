# UFS al salir de LK

**CONFIRMED en el Go tras LK.** El operador leyó `UFS DONE` y los trece registros del panel de SEC. La sonda registró alimentación activa, reset liberado y las cuatro ramas de reloj en estados encendidos. `VER=00010100` identifica UFSHCI 1.1 y `HCE=00000001` indica que el host estaba habilitado. [Transcripción original y valores](evidence/ufs-handoff-transfer-20261121.json) · [Imagen revisada y hashes](evidence/ufs-handoff-review-20261121.json)

`HCS=0000010F` indica presencia del dispositivo y disponibilidad de la lista de transferencias, la lista de tareas y el canal UIC. Los indicadores de error de host y de dispositivo en HCS estaban a cero. Los bits 10–8 valían 1 (`PWR_LOCAL`, estado de la solicitud de cambio de modo de energía). El operador transcribió la etiqueta como `HSC`. En esa posición el código de la imagen muestra `HCS`, dirección `0x624030`. [Definiciones del kernel del Go](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufshci.h) · [Etiquetas en SEC](../OculusGoPkg/SecMem/UfsHandoff.c)

Ambas listas tenían el bit Run a uno y sus registros de solicitudes pendientes estaban a cero en las lecturas respectivas. El siguiente paso técnico es identificar las bases de las listas y establecer qué memoria DMA puede utilizar EDK2 antes de enviar la primera lectura al LUN 4. La recuperación del emblema desde el medio físico sigue pendiente.

## Ensayo del logo con la geometría del Go

Se reconstruyó en un archivo disperso el LUN 4 de 4 831 838 208 bytes, con bloques de 4096 bytes. La GPT primaria y sus 36 entradas proceden de la captura privada. Se generaron el MBR protector y una GPT secundaria recíproca para el ensayo. La entrada 34 contiene el respaldo original de `splash`. El contenido de las demás particiones se representó con ceros. Los archivos que contienen datos del Go permanecen locales. [Medición del visor](evidence/ufs-splash-physical-layout-20261120.json)

QEMU recibió el disco en modo de sólo lectura. La traza muestra que EDK2 pidió los LBA 1 y 2–3 del LUN 4 para leer la GPT, el LBA 1 037 582 para leer la cabecera de `splash` y catorce intervalos dentro de esa partición para obtener el emblema. La última lectura terminó en el LBA 1 038 385. El huésped dibujó el emblema y releyó los 68 × 42 píxeles del GOP. El CRC fue `93104dc6`. Los hashes de ambos archivos de disco coincidieron antes y después. Las únicas órdenes SCSI de datos fueron READ CAPACITY(10) y READ(10). El transporte EDK2 también configuró la bandera de inicialización del dispositivo virtual. [Traza de LBA y resultados](evidence/ufs-lun4-geometry-qemu-20261121.json)

## Pantalla de la sonda

La cabecera identifica el último paso. Cada registro leído aparece con ocho dígitos hexadecimales. Cada pareja de columnas cabe en la zona central en ambos ojos. Una foto de un solo ojo o una transcripción de la cabecera y las filas permite conservar los valores.

| Cabecera | Significado |
| --- | --- |
| `UFS DONE` | Terminó todas las lecturas. HCS y las dos parejas de registros de colas ayudan a decidir qué investigar a continuación. |
| `UFS GATED <nombre>` | El dominio indica apagado o colapso solicitado, el reset está activo, o una rama de reloj no indica uno de los dos estados encendidos documentados. Se conserva el primer valor que impidió seguir. |
| `UFS DISABLED HCE` | Las comprobaciones anteriores pasaron. El bit de habilitación de HCE es cero. |
| `UFS INVALID <nombre>` | El valor fue todo unos, o la versión fue cero. La muestra queda sin interpretar. |
| `UFS FAULT <nombre>` | La instrucción de lectura provocó un aborto síncrono recuperable en el EL actual. |
| `UFS READ <nombre>` fijo | Es la última lectura anunciada. Un acceso al bus podría quedar pendiente, o producirse otra excepción. El rótulo por sí solo no distingue la causa. |

| Rótulo | Dirección física | Dato leído |
| --- | --- | --- |
| PWR / RST | `0x375004` / `0x375000` | GDSC UFS, bit 31 de alimentación y bit 0 de solicitud de colapso. BCR, bit 0 de reset. |
| AHB / AXI | `0x37500c` / `0x375008` | Estado de rama de interfaz y de núcleo UFS. |
| NOC / AGG | `0x375038` / `0x383014` | Ramas SYS_NOC_UFS y AGGRE2_UFS. El nibble superior 0 o 2 satisface la condición de rama encendida del kernel oficial. |
| VER / HCE | `0x624008` / `0x624034` | Versión UFSHCI y habilitación del host. |
| HCS | `0x624030` | Presencia del dispositivo y disponibilidad de las listas y del canal UIC indicadas por el host. |
| TRR / TRD | `0x624060` / `0x624058` | Run/Stop y bits de solicitudes pendientes de la lista de transferencias. |
| TMR / TMD | `0x624080` / `0x624078` | Run/Stop y bits de solicitudes pendientes de la lista de gestión de tareas. |

La sonda lee cada dirección como máximo una vez. Las muestras son sucesivas y podrían cambiar entre lecturas. Un host habilitado con listas en marcha todavía requiere determinar el dominio DMA, la propiedad de sus colas y el estado del enlace antes de poder usarlo. La sonda sólo escribe en su pila y en el framebuffer heredado. Usa el mismo tipo de letra EDK2 que la consola. El diagnóstico termina en SEC y deja las colas, la PHY, ICE y los medios fuera de su secuencia de operaciones. [Código del muestreo](../OculusGoPkg/SecMem/UfsHandoff.c) · [Acceso de 32 bits y vectores](../OculusGoPkg/SecMem/UfsEntry.S) · [Procedencia de registros](REFERENCES.md)

## Qué se ejecutó en QEMU

El segundo banco ejecutó el FD físico con el DT de ejecución archivado y bancos de registros sintéticos de sólo lectura. Se vigilaron todos los accesos a los rangos de GCC y del host durante cada caso. Se observaron las direcciones, el orden exacto y la instrucción de carga. Se cotejaron los glifos de las dos vistas contra los valores esperados. En EL1 y EL2 pasaron los trece casos, incluidos un reloj en transición, HCE apagado, identidad de placa distinta y un aborto de alineación inducido en la carga. El perfil contiene un único ejecutable SEC. La inspección binaria comprobó su lista de direcciones, los 16 vectores y el código máquina del acceso. Esta emulación evalúa la lógica de diagnóstico. [Resultados por caso](evidence/ufs-handoff-qemu-20261121.json) · [Inspección del FD](evidence/ufs-handoff-static-20261121.json)

## Reproducción offline

Desde Debian/WSL, con `splash`, `capture` y `runtime` apuntando al respaldo privado, al directorio de captura GPT y al DTB archivado en ejecución respectivamente:

```bash
bash scripts/build-qemu-ufs-drivers.sh
python3 tests/ufs_splash_qemu.py "$splash" build/ufs-real-lun --pacific-layout "$capture"
bash scripts/build.sh DEBUG 8 UFS_HANDOFF
# run es el directorio que imprime build.sh al terminar.
fd="$run/OCULUS_GO_DIRECT.fd"
elf=Build/OculusGoUfsHandoff/DEBUG_GCC5/AARCH64/OculusGoPkg/SecMem/UfsHandoff/DEBUG/OculusGoUfsHandoff.debug
python3 tests/ufs_handoff_qemu.py --fd "$fd" --sec-elf "$elf" --runtime-fdt "$runtime" --report "$run/QEMU.json"
python3 tests/ufs_handoff_static.py --fd "$fd" --sec-elf "$elf" --report "$run/STATIC.json"
```

En Windows, `python tools/run_ufs_handoff_once.py` coteja el contenedor y el expediente local sin contactar con USB. El manifiesto de empaquetado refleja la verificación estructural. La revisión del intento vincula por SHA-256 el FD, el contenedor, las pruebas QEMU y la auditoría de fuentes. Para la prueba física se necesita el Go en Android, el cable de datos y el operador para leer el panel y volver al arranque original. El transporte atendido admite un único `fastboot boot` con los respaldos y el preflight ya empleados en ensayos anteriores. Si el bus se detiene, la ruta física ensayada es apagar con Power y seleccionar «Boot device» desde «USB Update Mode». [Transporte del intento](../tools/run_ufs_handoff_once.py) · [Recuperación](RECOVERY.md)
