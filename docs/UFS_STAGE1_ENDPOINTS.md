# Del SID de UFS a la página de EDK2

La página reservada por SEC en Pacific es el intervalo CPU `[0x80441000, 0x80442000)`. El SID del controlador tras LK y la dirección de bus que alcanza esa página siguen **UNKNOWN**. El árbol del Go identifica la conexión UFS→DDR. El kernel oficial toma los SID de dispositivos de plataforma de la propiedad `iommus`, ausente en el nodo UFS de los dos árboles conservados. El número 95 del maestro de interconexión y el 68 de RPM pertenecen a otros espacios de identificadores. [Investigación de fuentes y logs](UFS_SID_SOURCES.md) · [Topología de Pacific](UFS_ROUTE_SOURCES.md)

## Dos consultas de capacidad en QEMU

El banco creó una traducción de etapa 1 en la SMMUv3 de QEMU, con entrada y salida de 36 bits y páginas de 4096 bytes. El controlador UFS virtual se identifica por PCI y su SID 8 se obtiene del árbol de la VM. El medio virtual del LUN 4 usa la geometría observada en el visor. Para cada destino se comprobó la traducción registrada por QEMU y se compararon los 16 KiB de RAM de la ventana después de cada transferencia. [Arnés](../tests/ufs_stage1_route_qemu.py) · [Resultados completos](evidence/ufs-stage1-endpoints-20261121.json)

| Ensayo | Dirección de bus en la VM | Destino observado en RAM de la VM | Resultado |
| --- | --- | --- | --- |
| Primeros ocho bytes | `0x85120000` | `0x80441000` | `00 11 FF FF 00 00 10 00` |
| Últimos ocho bytes | `0x85120FF8` | `0x80441FF8` | Misma respuesta |
| Extremo final dirigido a la página vecina | `0x85121FF8` | `0x80442FF8` | Estado SCSI cero. El destino solicitado conservó sus ocho bytes `A5` y el verificador detectó el error. |

La respuesta da último LBA inclusivo `0x0011FFFF` y bloque lógico de 4096 bytes. El transporte sólo consultó la capacidad, con cero operaciones de sector en la traza. Estas direcciones de bus y el SID 8 son datos de la VM. Cada consulta cubre ocho bytes. La lectura de los 4096 bytes del LBA 1 queda para un ensayo posterior. [Registro QEMU](evidence/ufs-stage1-endpoints-20261121.json)

La prueba complementaria con una aplicación AArch64 en EDK2/AAVMF pidió las direcciones a `EDKII_UFS_HOST_CONTROLLER_PROTOCOL.Map`. En ese entorno el proveedor devolvió identidad en ambos extremos. El banco también comprobó el rechazo del mapeo final y el de un LUN con otra geometría. Este resultado y la traducción no idéntica de etapa 1 son reproducibles con dos configuraciones diferentes de QEMU. [Resultado del proveedor EDK2](evidence/ufs-owned-page-provider-20261121.json)

## Próxima comprobación en el visor

Con Android ya arrancado, el colector consulta sólo las entradas `of_node`, `driver` e `iommu_group` del dispositivo de plataforma `624000.ufshc`. Comprueba que el transporte corresponde al Go conocido, el producto es `pacific` y dos muestras consecutivas coinciden. Registra por separado un enlace exportado, la ausencia de la entrada en el directorio y una muestra incompleta por falta de acceso. El resultado queda en `local/ufs-binding-*/REPORT.json`. Basta Android con depuración USB y el equipo autorizado. [Colector](../tools/collect_ufs_binding.py) · [Qué publica el kernel del Go](UFS_SID_SOURCES.md)

Un número de grupo observado pertenece al kernel Android. El SID del maestro al salir de LK requiere evidencia que vincule el iniciador con su proveedor en ese momento. La dirección dada por un proveedor para una página de LK tampoco se puede extender a la página de EDK2. Si Android carece de un enlace de grupo, se conserva ese resultado sin asignar un SID ni una dirección de bus. La GPT del LUN 4 sigue pendiente para el driver de EDK2 en Pacific.

## Repetir las pruebas de host

Desde la raíz en Debian, con el UFS virtual y los drivers de prueba compilados:

```sh
python3 -B tests/ufs_stage1_route_qemu.py --report /tmp/ufs-stage1.json
python3 -B tests/ufs_capacity_map_qemu.py --owned-page --report /tmp/ufs-provider.json
```

La comparación comprueba la entrega de 16 bytes distintos en la página. Para leer una cabecera GPT completa hará falta comprobar la transferencia de un bloque entero y validar su contenido.
