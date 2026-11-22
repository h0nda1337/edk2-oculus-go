# Descripción del controlador y propiedad de la página en Pacific

El SID de UFS tras LK y su dirección de bus para la página CPU `0x80441000` siguen **UNKNOWN**. La página tiene además propietarios distintos según el firmware que esté ejecutándose. [Resultados de los archivos examinados](evidence/ufs-board-routing-20261122.json)

## Qué fuentes de la placa hay disponibles

En una máquina con ACPI, la tabla IORT puede asociar el nombre ACPI completo de un dispositivo de plataforma con un nodo de SMMU y uno o varios identificadores de stream. El kernel coteja el nombre del dispositivo con un *Named Component* y recorre sus registros de asignación de ID. El dato que aportaría esa tabla es la identidad del iniciador en el bus. Determinar la dirección DMA de un búfer concreto requiere también la correspondencia vigente para la asignación. [Linux v6.18, selección por nombre](https://github.com/torvalds/linux/blob/v6.18/drivers/acpi/arm64/iort.c#L251-L279) · [Conversión a SID](https://github.com/torvalds/linux/blob/v6.18/drivers/acpi/arm64/iort.c#L1204-L1218) · [Definición de IORT en el EDK2 fijado](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Include/IndustryStandard/IoRemappingTable.h)

En las seis capturas existentes del directorio Android `/sys/firmware`, los dos hijos enumerados son `devicetree` y `fdt`. Ninguna captura muestra `acpi`. Las seis copias tienen tres SHA-256 distintos y pueden pertenecer a arranques repetidos. El FDT de ejecución revisado tiene 1867 nodos. Su nodo `/chosen` contiene `bootargs`, `linux,initrd-start` y `linux,initrd-end`. Entre las 27 propiedades de `/soc/ufshc@624000` no figura una referencia a un proveedor IOMMU. Esas dos fuentes conservadas dejan sin asignar un SID al controlador. [Huellas e inventarios](evidence/ufs-board-routing-20261122.json) · [Censo del FDT](evidence/ufs-stream-topology-stock-20261121.json)

El build `NORMAL` que mostró la Shell en el visor tiene 23 módulos INF en su informe y el proyecto todavía no genera tablas ACPI para Pacific. El FD comprobado tiene el mismo SHA-256 que el del arranque temporal registrado. Una observación de Android y una tabla generada por el propio proyecto tendrían procedencias distintas a un registro de entrega de LK. [Arranque físico de esa Shell](evidence/oculus-logo-transfer-20261120.json) · [Estado de las tablas de la plataforma](../OculusGoPkg/AcpiTables/README.md)

Otra descripción publicada de esta familia es el árbol de Google para el Pixel Marlin MSM8996Pro. Su nodo `ufshc@624000` describe el controlador, y la placa MTP lo habilita. Los 60 archivos DTS/DTSI del directorio HTC revisado carecen de referencias a `&ufs1`, `ufshc@624000` o `&anoc2_smmu`. La revisión no aporta un SID transferible a Pacific. [SoC de Google, commit 72a7a644](https://android.googlesource.com/kernel/msm/+/72a7a64494e033f2213c9701dbf137d277bf2026/arch/arm/boot/dts/qcom/msm8996.dtsi#1265) · [Placa MTP](https://android.googlesource.com/kernel/msm/+/72a7a64494e033f2213c9701dbf137d277bf2026/arch/arm/boot/dts/qcom/msm8996-mtp.dtsi#45) · [Árbol HTC](https://android.googlesource.com/kernel/msm/+/72a7a64494e033f2213c9701dbf137d277bf2026/arch/arm64/boot/dts/htc/)

## Dónde queda la página en las imágenes verificadas

| Perfil y evidencia | Volumen exterior en RAM, fin exclusivo | Uso de la página `[0x80441000, 0x80442000)` |
| --- | --- | --- |
| `NORMAL`, FD de la Shell observada en Pacific y build posterior inspeccionado | `[0x80081000, 0x80480000)` | Pertenece al volumen de firmware. PrePi publica el intervalo `[0x80080000, 0x80480000)` en un HOB de asignación como `EfiBootServicesCode`. La zona usada para las asignaciones del arranque normal empieza en `0x80480000`. |
| `UFS_DATA`, FD del ensayo de capacidad observado en Pacific | `[0x80081000, 0x8043E000)` | El diseño de este perfil SEC dedica la segunda página de su ventana de 16 KiB a datos. Durante aquel ensayo, el controlador entregó la capacidad en la zona de LK. El bus de la página de EDK2 quedó sin medir. |

La comparación utiliza el campo de longitud de la cabecera FV de cada binario y los valores compilados del perfil. Para una prueba desde la Shell, el driver tendría que pedir su propio búfer a Boot Services y obtener su dirección de dispositivo del proveedor de ese controlador. La página fija corresponde a los perfiles SEC que la reservan expresamente. [Distribución de los FD](../OculusGoPkg/OculusGoPkg.fdf) · [Reserva del firmware en PrePi](../OculusGoPkg/PrePi/Memory.c) · [Resultado físico de UFS_DATA](evidence/ufs-data-transfer-20261121.json)

## Dos medidas independientes desde EDK2 en QEMU

La aplicación AArch64 obtiene la ubicación PCI del mismo *handle* UEFI que proporciona UFS y el transporte SCSI. Lee la IORT publicada por AAVMF en la XSDT. El arnés resuelve la entrada del complejo raíz correspondiente y coteja el identificador de salida con la traza de QEMU durante cada consulta SCSI. Por separado, captura la dirección que devuelve `EDKII_UFS_HOST_CONTROLLER_PROTOCOL.Map` y coteja los ocho bytes y las guardas después de la transferencia. La interfaz `Map` devuelve una dirección de dispositivo y un identificador para `Unmap`. La firma carece de un campo SID. [Aplicación](../tests/UfsSplashApp/UfsIortProbe.c) · [Arnés](../tests/ufs_iort_qemu.py) · [Contrato de EDK2](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Include/Protocol/UfsHostController.h)

| Configuración de la VM | SID obtenido de la tabla y observado en la traza | Bus devuelto por el proveedor, inicio / últimos ocho bytes |
| --- | --- | --- |
| UFS en `00:03.0`, ruta a SMMUv3 | `0x18` | `0x80441000 / 0x80441FF8` |
| UFS en `00:05.0`, ruta a SMMUv3 | `0x28` | `0x80441000 / 0x80441FF8` |
| IORT con ruta directa a ITS | Sin SID DMA atribuible desde esa entrada | `0x80441000 / 0x80441FF8` |
| Máquina de compatibilidad `virt-2.7`, ACPI con XSDT sin IORT | Sin SID publicado por IORT | `0x80441000 / 0x80441FF8` |

En las dos primeras configuraciones el modelo registró `smmuv3_translate_disable` para ambos extremos. El identificador de las transacciones seguía siendo visible con la traducción desactivada. Cada ensayo recibió `00 11 FF FF 00 00 10 00` en el LUN 4. La traza del medio registró cero lecturas y escrituras de sectores. El ensayo anterior con traducción activa de etapa 1 muestra cómo esa dirección de bus también puede diferir de la CPU. [Resultados IORT](evidence/ufs-iort-capacity-20261122.json) · [Resultados de etapa 1](evidence/ufs-stage1-endpoints-20261121.json) · [Generación de IORT en QEMU](https://github.com/qemu/qemu/blob/v10.0.0/hw/arm/virt-acpi-build.c#L250-L392)

La Shell de Pacific incluye un consumidor del protocolo UFS. El proveedor que implementa `Map` para PCI se compila para la VM. El controlador integrado `624000.ufshc` requiere un proveedor de plataforma con una correspondencia DMA verificada en ese arranque. Para atribuir también el SID haría falta, por ejemplo, una descripción de placa de Pacific que identifique expresamente el maestro UFS en la unidad de traducción. Los números PCI de la VM quedan fuera de la configuración de Pacific. [Contenido de la imagen de Shell](evidence/ufs-splash-pacific-shell-20261120.json) · [Transportes de prueba](../tests/UfsSplashApp/Transport.dsc)

## Repetir la comprobación sin visor

Para compilar la aplicación y las dos dependencias de UFS en Debian/WSL y ejecutar las consultas sobre el LUN virtual:

```sh
bash scripts/build-qemu-ufs-drivers.sh
python3 -B tests/test_ufs_iort_decoder.py
python3 -B tests/ufs_iort_qemu.py --report /tmp/ufs-iort.json
```


Desde la raíz del repositorio en Debian/WSL, `ARCHIVE` apunta al directorio `device-info/raw` de las capturas conservadas y `RUNTIME_DTB` al FDT cuyo SHA-256 consta en el informe. Este ejemplo lee los archivos del host y evita imprimir los nombres privados de las capturas.

```sh
for f in "$ARCHIVE"/*/sys-firmware.txt; do sha256sum < "$f"; done | sort | uniq -c
for f in "$ARCHIVE"/*/sys-firmware.txt; do tr -d '\r' < "$f" | rg '^/sys/firmware/[^/]+$'; done | sort | uniq -c
sha256sum < "$RUNTIME_DTB"
fdtget -p "$RUNTIME_DTB" /chosen
fdtget -p "$RUNTIME_DTB" /soc/ufshc@624000
```

El siguiente fragmento vuelve a calcular el SHA-256 y los límites del volumen para cada build del registro e identifica cualquier diferencia.

```python
import hashlib, json, struct
from pathlib import Path

record = json.loads(Path("docs/evidence/ufs-board-routing-20261122.json").read_bytes())
for row in record["inspectedFirmware"]:
    folder = Path("build") / row["build"]
    data = (folder / "OCULUS_GO_DIRECT.fd").read_bytes()
    assert hashlib.sha256(data).hexdigest() == row["fdSha256"]
    base, start = int(row["fdBase"], 16), int(row["fvStart"], 16)
    header = start - base
    assert data[header + 40:header + 44] == b"_FVH"
    length, = struct.unpack_from("<Q", data, header + 32)
    assert start + length == int(row["fvEndExclusive"], 16)
    print(row["build"], hex(start), hex(start + length))
```
