# Qué vincula al UFS de Pacific con AGGRE2 después de LK

**CONFIRMED.** En el árbol de ejecución del Go, el nodo interconector `/soc/ad-hoc-bus/mas-ufs` tiene identificador 95, puerto de QoS 2 e identificador RPM 68. Sus propiedades `qcom,bus-dev` y `qcom,connections` se resuelven respectivamente a `fab-a2noc` y `slv-a2noc-snoc`. Esta última referencia continúa hacia el tejido SNOC. Android emplea estos nodos para describir el ancho de banda y la conectividad del interconector. El panel de EDK2 ya comprobó en el visor el estado encendido del dominio AGGRE2 y de sus cuatro ramas de reloj. [Fuente oficial del interconector](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/arch/arm/boot/dts/qcom/msm8996-bus.dtsi#L353-L366) · [Lecturas tras LK](evidence/ufs-route-clocks-transfer-20261121.json)

**UNKNOWN.** Falta identificar el stream que las transacciones de datos de UFS presentan a la unidad de traducción o determinar por medición su dirección de bus efectiva. El nombre `ANOC2` aparece tanto en el DT de Pacific como en las imágenes originales de firmware. El modelo de interconexión y ese nombre no codifican una relación stream→página. [Registros de ANOC2 en las imágenes originales](UFS_NATIVE_PRDT.md)

## Censo completo del DT de ejecución

El FDT conservado tiene SHA-256 `0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929` y 1867 nodos. Se resolvió cada celda de proveedor de `iommus` contra su phandle y se consumió el número de argumentos declarado en `#iommu-cells`, incluidos los proveedores con cero argumentos. El resultado abarca 29 nodos consumidores, 71 referencias y nueve proveedores. En todo el árbol hay cero propiedades `mmu-masters`, `iommu-map`, `iommu-map-mask` o `dma-ranges`. [Censo del DT real](evidence/ufs-stream-topology-stock-20261121.json) · [Auditoría reproducible](../tools/audit_ufs_stream_topology.py) · [Identificación de la captura](evidence/ufs-bus-pages-20261121.json)

El DTB original adjunto a la imagen Android tiene SHA-256 `70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35`. También se recorrieron sus referencias y se obtuvieron las mismas cuentas. En ambas copias, el rango de `/soc` traduce la base de ANOC2 por identidad para la CPU y la región tiene tamaño `0x20000`. La traducción DMA de un periférico es una propiedad distinta. [Empaquetador del proyecto](../tools/android_boot.py)

| Proveedor en `/soc` | Referencias en propiedades `iommus` |
| --- | ---: |
| `arm,smmu-venus@d40000` | 44 |
| `arm,smmu-lpass_q6@1600000` | 9 |
| `arm,smmu-vfe@da0000` | 4 |
| `arm,smmu-anoc0@1640000` | 3 |
| `arm,smmu-jpeg@d80000` | 3 |
| `arm,smmu-mdp@d00000` | 2 |
| `arm,smmu-rot@d20000` | 2 |
| `arm,smmu-cpp_fd@d60000` | 2 |
| `arm,smmu-kgsl@b40000` | 2 |

`/soc/arm,smmu-anoc2@1680000` carece de `phandle` y de `linux,phandle`. La propiedad `attach-impl-defs` contiene 74 pares de palabras. El kernel oficial los interpreta como desplazamiento y valor de registro para su programación cuando se adjunta un cliente. Esos pares no atribuyen ninguno de sus valores al identificador de UFS. [Interpretación de los pares](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L3313-L3355) · [Uso de los pares](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L1931-L1942)

Para inspeccionar las fuentes de estas cuentas, con el FDT privado respaldado y `dtc` instalado, se puede generar una copia textual en un directorio temporal del host. El siguiente filtro muestra la lista completa de consumidores con la codificación de cada referencia.

```sh
sha256sum "$RUNTIME_DTB"
dtc -q -I dtb -O dts -o /tmp/pacific-route.dts "$RUNTIME_DTB"
rg '^[[:space:]]*iommus = ' /tmp/pacific-route.dts
fdtget -p "$RUNTIME_DTB" '/soc/arm,smmu-anoc2@1680000'
```

## Registros que permiten precisar la siguiente medición

El driver oficial describe los registros de identificación ID0, ID1 e ID2 en los desplazamientos globales `0x20`, `0x24` y `0x28`. El control global está en `0x0` en la vista ordinaria. Este árbol carece de `calxeda,smmu-secure-config-access`, la propiedad que el driver consulta para usar el alias especial de los registros no seguros. Los registros de identificación describen capacidades. El control global describe la política visible en ese instante. Para asignar una traducción a la página de EDK2 sigue haciendo falta identificar el emisor y el contexto efectivo en el mismo arranque, o conseguir una correspondencia DMA del proveedor de UFS. [Registros de la implementación oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L65-L135) · [Selección del alias](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/iommu/arm-smmu.c#L470-L480)
