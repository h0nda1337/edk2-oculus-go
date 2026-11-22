# Dirección de datos que dejó LK para UFS

**Pacific, página CPU `0x80441000`.** La hipótesis de identidad da bus `0x80441000` al inicio y `0x80441FF8` para los ocho bytes finales. La traducción física vigente para el UFS sigue **UNKNOWN**. El dato de hardware anterior fue `0x918FDF00` para el descriptor de comando y `0x918FDF20` para la respuesta UPIU. El PRDT es la tabla que describe el destino de los datos. [Panel real de UFS_HEAP4K](evidence/ufs-heap4k-transfer-20261121.json)

## Evidencia de la máquina original

En el `aboot_a` de este Go, LK toma el puntero de datos del campo `+8` del comando nativo. Lo introduce en el primer PRD en `0x9182C27C`, con la parte alta a cero. Para peticiones grandes avanza la dirección en pasos de 256 KiB y escribe los segmentos siguientes. LK obtiene la etiqueta de tarea de un contador en `HBA+0x174`. El observador comprueba que petición y respuesta comparten esa etiqueta incluso cuando vale `0x9D` en el slot 0. Un UTRD conserva el número de entradas y el desplazamiento del PRDT en palabras de cuatro bytes. Esto identifica el número que el software programó. Los descriptores se liberan al terminar, por lo que los bytes que sobreviven al arranque sólo pueden aportar evidencia histórica. [Auditoría del ELF](../tools/audit_lk_prdt.py) · [Resultados sobre el respaldo](evidence/ufs-native-prdt-stock-20261121.json)

En las imágenes originales `hyp_a` y `tz_a` aparecen sendos pares de registros de datos con el nombre ANOC2 junto a la base `0x01680000`. Coinciden con la base del DT de ejecución. El identificador de flujo de UFS y una traducción para esta página siguen sin identificar. En el kernel oficial el reloj `aggre2_noc_clk` se solicita a RPM y el reloj de rama AXI de UFS se describe aparte en `GCC_AGGRE2_UFS_AXI_CBCR`. El estado observado de la rama UFS por sí solo es insuficiente para acceder a registros del SMMU. La sonda utiliza el UTRD y RAM normal. [DT de ejecución](evidence/ufs-bus-pages-20261121.json) · [Definiciones del kernel oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/clk/msm/clock-gcc-8996.c) · [Identificación de streams en Arm SMMUv2, §2.4](https://documentation-service.arm.com/static/5f900d34f86e16515cdc08fb)

## Prueba de los dos extremos en QEMU

Se repitió `READ CAPACITY(10)` con el proveedor UEFI y con un UFS virtual detrás de SMMUv3. Los resultados positivos reproducen byte por byte los informes archivados. El LUN 4 devolvió `00 11 FF FF 00 00 10 00`, último LBA inclusivo `0x0011FFFF` y bloque lógico de 4096 bytes. Los ocho bytes de cada extremo son independientes. [Mapeo de AAVMF](evidence/ufs-owned-page-provider-20261121.json) · [Mapeo no idéntico](evidence/ufs-owned-page-translated-20261121.json)

| Ensayo | Dirección del PRD inicial / final | Destino CPU observado |
| --- | --- | --- |
| AAVMF | `80441000 / 80441FF8` | Ambos extremos de la página reservada |
| SMMUv3 con el mapeo correcto | `88000000 / 88000FF8` | Ambos extremos de la misma página |
| SMMUv3 con otro destino al final | `88000000 / 88001FF8` | Primer extremo correcto, segundo en `80442FF8` |

En el tercer ensayo el controlador completó el comando con OCS y estado SCSI cero. Los ocho bytes en `80441FF8` conservaron `A5`. La guarda de la página vecina recibió la capacidad y los demás bytes quedaron intactos. La prueba detectó el fallo comparando memoria. Las trazas contienen exclusivamente solicitudes SCSI de capacidad y cero accesos al medio. [Control negativo y datos recibidos](evidence/ufs-prdt-wrong-tail-20261121.json)

## Arranque temporal UFS_PRDT

La imagen lee por CPU el slot 0 de la cola de LK. Sólo inspecciona el UCD si el puntero coincide exactamente con el de la prueba física anterior y cabe en la ventana fija `[0x918FDF00, 0x918FE000)`. Comprueba dos muestras de los metadatos, el estado de las colas, dirección de transferencia, UPIU, etiqueta, estado de respuesta, longitud y límites de los segmentos. Las lecturas del UCD se limitan a las palabras necesarias para el descriptor aceptado. La sonda admite capacidad y lecturas SCSI de 10 o 16 bytes en el CDB retenido. El FD sólo enlaza el observador pasivo. [Código de la sonda](../OculusGoPkg/SecMem/UfsPrdt.c) · [Revisión de la imagen](evidence/ufs-prdt-review-20261121.json)

| Panel | Qué se puede concluir |
| --- | --- |
| `PRDT COVERS` | El intervalo **numérico** de bus en el descriptor retenido cubre la página entera. `FIRST` y `LAST` son inclusivos. La correspondencia con RAM CPU requiere evidencia independiente. |
| `PRDT PARTIAL` o `OUTSIDE` | El intervalo candidato cubre parte de la página o cae fuera de ella. |
| `PRDT NO DATA` | El slot indicó cero entradas de datos. |
| `STOP UCD MOVED` | El slot apuntó a otra dirección. La sonda terminó antes de leer ese UCD. |
| Otro `STOP` | No se pudo validar la muestra. Las filas visibles indican hasta dónde llegó. |

Se probó el FD completo en QEMU con 15 ejecuciones, incluyendo EL1 y EL2. Los casos con traducción identidad y con otra RAM de respaldo produjeron el mismo panel para la misma dirección de bus. Los casos de cobertura usan metadatos sintéticos de READ(10) y READ(16). La preparación de la cola emplea capacidad real del UFS virtual. El observador no envió comandos ni leyó sectores en ninguno de los casos. [Paneles y resultados](evidence/ufs-prdt-fd-qemu-20261121.json)

## Resultado en el Go

El panel físico mostró `UFS PRDT NO DATA`, `UCD 918FDF00`, `NPRD 00000000` y `CPU ONLY`. La sonda leyó dos veces el descriptor del slot 0 con las colas en reposo. El recuento de cero entradas hizo que terminara antes de acceder al UCD. No se obtuvo opcode, LUN ni intervalo de datos para el comando anterior. Las cuatro líneas coincidieron con el caso `zero-prd` de QEMU. La dirección de bus para la página CPU `0x80441000` sigue **UNKNOWN**. [Transcripción física y registro del arranque](evidence/ufs-prdt-transfer-20261121.json)

Antes de una lectura física del LBA 1 se necesita un destino de datos que el UFS pueda usar en ese arranque y verificar en RAM las dos transferencias de ocho bytes. Un intervalo retenido cubriendo ambas direcciones, por sí solo, es insuficiente para autorizar DMA directo.

## Reproducción

Desde Debian, con las dependencias del proyecto y los drivers de la prueba ya compilados, estas órdenes sólo trabajan en el host.

```sh
python3 -B tests/ufs_capacity_map_qemu.py --owned-page --report build/prdt-provider.json
python3 -B tests/ufs_owned_bus_qemu.py --report build/prdt-translated.json
python3 -B tests/ufs_owned_bus_qemu.py --misdirect-tail --report build/prdt-wrong-tail.json
python3 -B tools/audit_lk_prdt.py --backup-directory "$BACKUP" --report build/native-prdt.json
bash scripts/build.sh DEBUG 8 UFS_PRDT
python3 -B tests/ufs_prdt_fd_qemu.py --fd "$FD" --sec-elf "$SEC_ELF" --runtime-fdt "$RUNTIME_DTB" --report "$BUILD/QEMU.json" --static-report "$BUILD/STATIC.json"
```

En Windows, `python -B tools/run_ufs_prdt_once.py` verifica sin USB la imagen local contra las huellas revisadas.
