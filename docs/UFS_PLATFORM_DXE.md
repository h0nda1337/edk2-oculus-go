# El controlador UFS integrado en DXE

El firmware normal describe el controlador del Pacific EVT y contiene el driver de host para enlazarlo al transporte UFS de EDK2. Durante el arranque, el lector de la Shell pide páginas a Boot Services. Cada comando obtiene su dirección de bus del servicio DMA vinculado al handle de esa controladora.

## Desde el DTB hasta la Shell

1. PrePi valida el árbol recibido por la entrada ARM64. Comprueba el modelo Pacific EVT, el bus padre, su traducción de direcciones, el estado del controlador, la compatibilidad UFS 1.1 y el único recurso de registros. El DTB del Go describe `0x00624000` con longitud `0x2500`. PrePi reserva para MMIO las tres páginas CPU que cubren ese intervalo y entrega a DXE los límites exactos en un GUID HOB. [Parser](../OculusGoPkg/PrePi/PacificUfsFdt.c) · [Mapa](../OculusGoPkg/PrePi/Memory.c)
2. `PacificUfsDxe` registra ese recurso como UFS mediante el mecanismo de EDK2 para dispositivos integrados. Antes de ceder el controlador al transporte, exige confirmación de propiedad de los registros, alimentación, PHY y colas durante Boot Services. Comprueba además la versión del HCI, el estado de las listas y las peticiones pendientes. El transporte de EDK2 puede reiniciar el HCI y configurar sus propias listas durante el enlace. [Enumerador](../OculusGoPkg/Drivers/PacificUfsDxe/PacificUfsDxe.c) · [Contrato de entrega](../OculusGoPkg/Include/Protocol/PacificUfsHandoff.h)
3. `GoUfsHcDxe` abre el servicio DMA del mismo handle y verifica una página de memoria compartida antes de publicar el protocolo de host. El servicio usa la interfaz de funciones de `EDKII_IOMMU_PROTOCOL` bajo un GUID propio. El puente PCI del EDK2 fijado busca el GUID estándar globalmente. Usar ese GUID para un servicio exclusivo de UFS puede desviar las transferencias del propio puente. La operación de prueba de memoria compartida termina antes de que se emita el primer comando SCSI. [Driver de host](../OculusGoPkg/Drivers/GoUfsHcDxe/GoUfsHc.c) · [Selección del servicio por PCI](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Bus/Pci/PciHostBridgeDxe/PciHostBridge.c#L405-L423)
4. BDS conecta el handle con un nodo de fin de ruta. Esto permite iniciar el transporte sin enumerar los discos hijos por anticipado. El lector solicita dos `READ CAPACITY(10)` al LUN 4, primero en los bytes 0–7 de una página dinámica y después en los bytes 4088–4095. Comprueba las respuestas, la geometría y la memoria circundante. El primer comando puede repetirse una vez si el medio informa de un cambio de estado al encender (`UNIT ATTENTION`). Leer LBA 1 requiere después un nuevo mapeo para los 4096 bytes del bloque. [Lector](../OculusGoPkg/Library/GoUfsSplashLib/UfsSplash.c) · [Mapeo y liberación](../OculusGoPkg/Drivers/GoUfsHcDxe/Dma.c)

Cada dirección DMA sólo vale para la petición que mantiene el mapeo. El host pide la ventana de direcciones de 32 bits del proveedor y permite que éste traduzca o use una página intermedia. Sigue la secuencia de conceder acceso al dispositivo, retirarlo y liberar el mapeo. Si falla una liberación, el driver conserva su registro. Antes de devolver la memoria del cliente a Boot Services, el lector comprueba que el dispositivo ya no tiene acceso. Una liberación que sigue fallando conserva esas páginas hasta reiniciar. [Contrato de la página](../OculusGoPkg/Include/Protocol/GoUfsDmaGuard.h)

## Resultado del LUN 4 en QEMU

Pasaron 14 arranques con el driver de host y el transporte extraídos de la misma compilación que el FD normal. Se cotejaron byte por byte con los ejecutables de ese FV antes de iniciar la matriz. La aplicación de medida y el proveedor de placa son propios de la VM. Con 768 MiB, la Shell recibió `00 11 FF FF 00 00 10 00` tanto en el comienzo de su página como en el último grupo de ocho bytes. El bloque mide 4096 bytes y el último LBA es `0x0011FFFF`. Cambiar la RAM del invitado desplazó la asignación. [Trazas y resultados de cada caso](evidence/ufs-platform-hc-qemu-20261122.json)

| Ensayo de la VM | Dirección CPU, primero / segundo | Dirección DMA, primero / segundo |
| --- | --- | --- |
| Directo | `0x6EA75000` / `0x6EA75FF8` | `0x6EA75000` / `0x6EA75FF8` |
| Con página intermedia | `0x6EA75000` / `0x6EA75FF8` | `0x6EA63000` / `0x6EA63000` |

La última fila corresponde a dos mapeos sucesivos que reutilizaron una dirección de bus. Los ocho bytes llegaron al extremo previsto en cada operación. Los casos de proveedor ausente, instalado en otro handle, cesión de placa denegada y permiso inicial denegado registraron cero accesos MMIO al UFS. Con sólo un LUN 2 disponible, el lector integrado terminó sin consultar otro LUN.

En el último arranque de la matriz, BDS enlazó los dos drivers y ejecutó `0x25, 0x25, 0x25` antes del primer `0x28`. Se leyó un bloque en LBA 1, cuatro desde LBA 2 y uno en LBA 2048 con un marcador sintético de `splash`. Se comprobó la huella del disco virtual antes y después. Las pruebas de sólo capacidad registraron cero lecturas de sectores y en toda la matriz hubo cero escrituras de sectores.

El replay del código del enumerador pasó 35 casos con el DTB original, árboles modificados, HOB de prueba y registros simulados. Entre ellos se confirmó el registro del intervalo exacto, y que una entrega ausente o denegada devuelve el control sin leer registros. [Resultado del replay](evidence/ufs-platform-board-20261122.json)

El FD normal de 20 MiB arrancó a EL1 en QEMU con el DTB EVT. Al llegar al prompt, la lista HOB publicada en la tabla del sistema UEFI contenía `0x624000 + 0x2500`, la marca de DMA no coherente y una reserva MMIO de tres páginas. Se cotejaron los tres drivers UFS del FV con sus binarios AArch64. La auditoría de fuentes verificó 107 listas de dependencias. [Prompt, tabla UEFI y hashes del FD](evidence/ufs-platform-normal-qemu-20261122.json)

El [ensayo de entrega con listas en marcha](UFS_DXE_TAKEOVER.md) extiende estos resultados al estado observado tras LK y comprueba la identidad de las listas desde la traza del dispositivo.

## Qué falta en el Go

**CONFIRMED en la captura del Go.** El DTB identifica los registros. En la prueba física anterior, LK dejó habilitado el HCI y las dos listas en marcha. El controlador respondió a capacidad usando memoria de LK. [Panel del HCI](UFS_HANDOFF.md) · [Geometría y mapeos comprobados](UFS_SHELL_BUFFER.md)

**UNKNOWN en el visor.** Siguen sin determinarse la entrega exclusiva de esas colas en el arranque normal, la ruta del maestro UFS y el mapeo de una página dinámica de Boot Services. Los dos contratos de placa permiten incorporar esa evidencia. Mientras falten, la Shell puede arrancar y el lector devuelve el control sin iniciar el transporte. La [auditoría de la salida ARM64](UFS_LK_EXIT.md) confirmó que el arranque temporal detiene USB y omite la rutina de reposo de MMC en la rama UFS. Las listas seguían en marcha en la muestra física. Para el proveedor DMA son válidas una traducción documentada del maestro o un área dedicada con relación CPU–bus, tamaño y coherencia conocidos que permita una copia intermedia. Una prueba física de capacidad requerirá primero un proveedor que garantice propiedad y sincronización durante todo el comando. [Fuentes contrastadas para Pacific](UFS_BOARD_ROUTING.md)

## Reproducción

Desde Debian/WSL en la raíz del repositorio, con la copia privada del EVT cuya huella verifica la prueba:

```sh
python3 tests/pacific_ufs_fdt.py local/ufs-buf4k-reviewed-evt.dtb logs/ufs-platform-board.json
bash scripts/build-qemu-ufs-drivers.sh
bash scripts/build.sh DEBUG 16 NORMAL
python3 tests/ufs_platform_hc_qemu.py --normal-build Build/OculusGo/DEBUG_GCC5 --report logs/ufs-platform-qemu.json
python3 tests/shell_prompt_qemu.py Build/OculusGo/DEBUG_GCC5/FV/OCULUS_GO_DIRECT.fd Build/OculusGo/DEBUG_GCC5/AARCH64/Shell.efi build/ufs-platform-prompt --pacific-dtb local/ufs-buf4k-reviewed-evt.dtb
```

El arnés de QEMU toma la ventana de registros del UFS virtual y presenta un controlador integrado al driver que lleva el FD. Sólo en la VM, las funciones del proveedor de DMA usan el backend PCI del periférico virtual. La prueba distingue los accesos al modelo mediante su traza y usa una imagen sintética para la GPT. El informe registra el SHA-256 de cada binario utilizado y del medio virtual. [Aplicación UEFI de prueba](../tests/UfsSplashApp/PlatformBuffer.c) · [Arnés y aserciones](../tests/ufs_platform_hc_qemu.py)
