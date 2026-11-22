# Ruta DMA de UFS después de LK

**Pacific.** El DT de ejecución permite seguir al maestro UFS por la interconexión AGGRE2 hacia SNOC. En el arranque anterior se leyeron los cuatro relojes asociados en estado activo. El DT enlaza a 29 consumidores con proveedores IOMMU, pero deja sin identificar el stream de UFS y el contexto que recibiría la petición. Tanto el modo de traducción que LK dejó para UFS como la dirección de bus de la página CPU `0x80441000` siguen **UNKNOWN**. [Censo y procedencia](UFS_ROUTE_SOURCES.md) · [Panel físico anterior](evidence/ufs-route-clocks-transfer-20261121.json)

## Prueba de los dos extremos

En el banco QEMU se identificó el controlador UFS por su clase PCI. Luego se siguió el `iommu-map` del DT de la máquina virtual para obtener el stream 8. El decodificador de prueba consume un conjunto sintético de registros SMMUv2 y contrasta su selección con la entrada y la raíz de traducción del SMMUv3 que QEMU ejecuta. El UFS virtual recibe las peticiones reales de `READ CAPACITY(10)` dirigidas al LUN 4. [Prueba reproducible](../tests/ufs_v2_route_qemu.py) · [Resultados y versión](evidence/ufs-v2-route-qemu-20261121.json)

| Ruta comprobada en la VM | Dirección de bus para los 8 bytes iniciales | Dirección de bus para los 8 bytes finales |
| --- | --- | --- |
| Traducción de etapa 2 | `0x85120000` | `0x85120FF8` |
| Bypass explícito | `0x80441000` | `0x80441FF8` |

Las dos configuraciones entregaron `00 11 FF FF 00 00 10 00` en las direcciones **CPU** `0x80441000` y `0x80441FF8`. Los ocho bytes codifican el último LBA inclusivo `0x0011FFFF` y el bloque lógico de 4096 bytes. Tras cada transferencia se cotejaron los 16 KiB que rodean los destinos. Los catorce controles negativos detuvieron el envío. Entre ellos están el SID desconocido, dos coincidencias, una página vecina, una raíz distinta y una declaración de bypass que contradice la ruta efectiva del emulador. La traza contiene cero accesos a sectores del LUN 4. El SID 8 y las direcciones de bus de la tabla pertenecen a la máquina virtual. [Resultados por caso](evidence/ufs-v2-route-qemu-20261121.json)

El banco UEFI complementario ejercita `EDKII_UFS_HOST_CONTROLLER_PROTOCOL.Map` desde una aplicación AArch64 en AAVMF. Verifica ambos destinos, la negativa a mapear el extremo final y el rechazo de una geometría distinta. [Aplicación y arnés](../tests/ufs_capacity_map_qemu.py) · [Informe del proveedor](evidence/ufs-owned-page-provider-20261121.json)

## Vista global de ANOC2 observada en el Go

`UFS_ROUTE_VIEW` utiliza la CPU para tomar una muestra de la vista global ordinaria de ANOC2 al entrar en EDK2. Valida el nodo y la traducción de direcciones MMIO del bus padre en el DT entregado por LK. En ese mismo arranque vuelve a comprobar dominio y relojes. Si se cumplen las condiciones, lee **cuatro** palabras del bloque ANOC2, una vez cada una. El panel conserva los valores crudos. El firmware carece de transporte UFS y de código para configurar la SMMU. [Código SEC](../OculusGoPkg/SecMem/UfsRouteClocks.c) · [Criterios del árbol](../OculusGoPkg/SecMem/Fdt.c)

El operador transcribió `UFS ROUTE SAMPLED` y los cuatro registros globales siguientes. La cabecera acredita que SEC completó las nueve lecturas previstas. [Panel físico](evidence/ufs-route-view-transfer-20261121.json)

| Registro | Dirección MMIO | Lectura del Go | Interpretación de los campos |
| --- | --- | --- | --- |
| `ID0` | `0x01680020` | `48014C09` | `S1TS=1`, `S2TS=0`, `NTS=0`. La unidad anuncia etapa 1 y selección por coincidencia de stream (`SMS=1`) con nueve grupos (`NUMSMRG=9`). |
| `ID1` | `0x01680024` | `30008008` | Ocho bancos de contexto (`NUMCB=8`) y cero bancos dedicados a etapa 2 (`NUMS2CB=0`). |
| `ID2` | `0x01680028` | `00007111` | Capacidades de direcciones de 36 bits (`IAS=OAS=UBS=1`). Admite gránulos de tabla de 4, 16 y 64 KiB. |
| `CR0` | `0x01680000` | `00200626` | `CLIENTPD=0` habilita el acceso de clientes. `USFCFG=1` selecciona un fallo para los streams que lleguen a esta unidad y carezcan de coincidencia. |

Los desplazamientos proceden del driver oficial del Go. El nodo de Pacific declara `qcom,skip-init` y el árbol carece en ese nodo de las opciones de alias especial y de bancos estáticos. La sonda se limita a la vista normal de sólo lectura. [Registros e interpretación](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L65-L135) · [Lecturas de identificación en el driver](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L3359-L3476)

El control global por sí solo deja pendiente atribuir una coincidencia a UFS. Los resultados S2 del ensayo QEMU ilustran una ruta virtual. Para determinar el bus efectivo de Pacific se necesita identificar el emisor y su tratamiento durante el mismo arranque, u obtener una correspondencia del proveedor DMA. Una vez resuelto, el primer ensayo sobre la página consultará la capacidad en cada extremo antes de leer la GPT del LUN 4. [Política para streams sin coincidencia en el driver oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L3137-L3141)

## Resultado del build para el visor

El FD AArch64 pasó 54 arranques en QEMU, 27 en EL1 y 27 en EL2. El arnés vigiló el GCC, el controlador UFS y ANOC2. Cada caso verificó los accesos en orden y el resultado en ambos ojos del framebuffer. Se probaron relojes detenidos, abortos síncronos de lectura, capacidad de identificación incoherente y árboles con otra dirección, estado o vista de registros. Al volver a escribir el mismo valor de `reg` en una copia del árbol correcto, la lectura completa siguió funcionando. La inspección del FD confirmó el módulo SEC, las nueve direcciones MMIO y los 16 vectores. [Informe del firmware](evidence/ufs-route-view-fd-qemu-20261121.json)

El contenedor de arranque temporal mide 380 928 bytes y su SHA-256 es `fb8d8518cc9aab7f457e537f9d58617a9249e1dbe64c8cd49dd45aa790fc5371`. [Manifiesto de la revisión](evidence/ufs-route-view-review-20261121.json)

## Reproducción offline

Desde Debian, con las herramientas y respaldos del proyecto:

```sh
python3 -B tests/ufs_v2_route_qemu.py --report /tmp/ufs-v2-route.json
python3 -B tests/ufs_capacity_map_qemu.py --owned-page --report /tmp/ufs-provider.json
bash scripts/build.sh DEBUG 8 UFS_ROUTE_VIEW
python3 -B tests/ufs_route_view_fd_qemu.py --fd "$FD" --sec-elf "$SEC_ELF" --runtime-fdt "$RUNTIME_DTB" --report "$OUT/QEMU.json" --static-report "$OUT/STATIC.json"
```

`FD` y `SEC_ELF` pertenecen al mismo build, `OUT` a su directorio de informes y `RUNTIME_DTB` al árbol de ejecución respaldado. En Windows, `python -B tools/run_ufs_route_view_once.py` verifica el paquete sin usar USB. La imagen que contiene el DT de Pacific permanece local. [Ensayos del firmware](evidence/ufs-route-view-fd-qemu-20261121.json) · [Revisión del arranque temporal](evidence/ufs-route-view-review-20261121.json)
