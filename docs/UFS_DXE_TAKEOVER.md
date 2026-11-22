# De las colas de LK a las de DXE

La captura en SEC del Go registró `HCE=1`, transferencias y tareas en marcha, y ambos *doorbells* a cero. Las bases capturadas en otro arranque pertenecían al asignador de LK. Para ensayar esa condición en QEMU, el propietario anterior reserva y mapea dos listas propias en cada arranque, programa sus registros y deja de enviar trabajo. Conserva las dos páginas hasta que el controlador se detiene al final de la prueba. Esto permite detectar cualquier acceso posterior a las listas antiguas. [Panel físico](evidence/ufs-handoff-transfer-20261121.json) · [Propietario sintético](../tests/UfsSplashApp/InheritedQueues.c)

## Qué autoriza el cambio

El driver de Pacific y la aplicación de la VM llaman a la misma biblioteca. Primero se pide una cesión explícita en el handle de ese controlador. Después se comprueba la versión que corresponde al hardware y se toman dos muestras de las listas. Para el estado activo se requieren las dos listas en marcha, sin pendientes y con bases estables, distintas, alineadas y diferentes de cero. La biblioteca sólo lee registros. En el Go, la versión exigida sigue siendo `0x00010100`. El transporte se encarga de reiniciar el HCI y obtener sus propias listas mediante el proveedor DMA. [Biblioteca](../OculusGoPkg/Library/GoUfsHandoffLib/UfsHandoff.c) · [Contrato de entrega](../OculusGoPkg/Include/Protocol/PacificUfsHandoff.h) · [Secuencia del transporte EDK2](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Bus/Ufs/UfsPassThruDxe/UfsPassThruHci.c#L2128-L2151)

## Alcance del emulador

El UFS virtual usa registros de listas heredadas con MCQ desactivado. Anuncia UFSHCI 4.0. QEMU 10.0.13 acepta las bases de ambas listas, pero descarta escrituras en `UTMRLRSR` (offset `0x80`). La variante de la prueba conserva el bit de marcha de la lista de tareas vacía y borra ambos bits al deshabilitar el HCI sin pendientes. El transporte de transferencias, el enlace UFS, el backend SCSI y la transferencia de datos usan el código original de QEMU. El ensayo cubre únicamente una entrega en reposo. [Código original](https://github.com/qemu/qemu/blob/v10.0.13/hw/ufs/ufs.c#L685-L752) · [Parche del modelo](../tests/qemu/ufs-idle-task-list-10.0.13.patch)

## Qué se observa en la traza

Con 768 MiB de RAM, las listas heredadas de transferencias y tareas estaban en `0x6EA79400` y `0x6EA78400`. DXE deshabilitó el HCI y comprobó la lectura de vuelta. Después de habilitarlo instaló las listas nuevas en `0x6EA67000` y `0x6EA68000` antes de llamar al primer *doorbell*. QEMU leyó el descriptor en la nueva cola de transferencias. Las dos respuestas válidas de ocho bytes llegaron a `0x6EA65000` y `0x6EA65FF8`. La traza contiene tres envíos de la CDB de capacidad. En el primer intento los ocho bytes de guarda permanecieron en su sitio. Ambas respuestas válidas devolvieron `00 11 FF FF 00 00 10 00`, equivalentes a 1.179.648 bloques de 4096 bytes. El backend del LUN era de sólo lectura y el ensayo terminó con cero operaciones de sector. [Traza y hashes por escenario](evidence/ufs-dxe-takeover-qemu-20261122.json)

Al repetir el arranque con 1536 MiB, las listas nuevas pasaron a `0x9EA67000` y `0x9EA68000`. Las respuestas llegaron a `0x9EA65000` y `0x9EA65FF8`. El verificador coteja las direcciones impresas por el invitado con los accesos al descriptor y a los datos registrados por el modelo. También altera la traza para comprobar que detecta una cola antigua reutilizada, una lectura DMA ausente y operaciones de sector inesperadas. [Verificador de MMIO, DMA y SCSI](../tests/ufs_takeover_qemu.py)

Para probar el periférico se arranca AAVMF con una aplicación que representa al propietario anterior y al proveedor DMA de la placa. El host y el transporte utilizados en ese caso se extraen de la compilación NORMAL y se cotejan con sus PE en el FV. En un arranque aparte se ejercita el propio FD de Pacific con su DTB y se comprueba la publicación del recurso UFS al llegar a `Shell>`. El FD llegó a `Shell>` en EL1, con la misma imagen en ambos ojos y el recurso UFS publicado en la tabla HOB. [Informe del FD NORMAL](evidence/ufs-dxe-takeover-normal-20261122.json) · [Prueba de la Shell](../tests/shell_prompt_qemu.py)

Los controles distinguen dos fallos que podrían parecer un arranque satisfactorio. En QEMU original la cola de tareas leyó cero después de intentar ponerla en marcha, lo que detuvo el ensayo con `EFI_UNSUPPORTED`. En el modelo ampliado, el propietario también pudo conservar dos colas realmente activas al denegar la cesión. Ese caso registró cero comandos SCSI y las páginas antiguas conservaron su contenido. El replay del código de placa pasó 55 casos, incluidos 29 de entrega. [Resultados con el DTB original de Pacific](evidence/ufs-running-board-20261122.json)

## Reproducción

En Linux con el entorno AArch64 del proyecto y las dependencias de compilación de QEMU (Meson, Ninja, compilador C, cabeceras de GLib, pixman y libfdt), obtener el archivo fuente oficial `qemu-10.0.13.tar.xz`. El script verifica el SHA-256 del archivo y del código aplicado, y deja un ejecutable independiente en el directorio de trabajo. El ejecutable de la distribución sirve de control. [Archivo fuente de QEMU](https://download.qemu.org/qemu-10.0.13.tar.xz)

```sh
bash scripts/build-qemu-ufs-handoff.sh "$archive" "$work"
bash scripts/build-qemu-ufs-drivers.sh
bash scripts/build.sh DEBUG 16 NORMAL
python3 -B tests/ufs_takeover_qemu.py --qemu "$work/build/qemu-system-aarch64" \
  --normal-build Build/OculusGo/DEBUG_GCC5 --report logs/ufs-takeover.json
python3 -B tests/pacific_ufs_fdt.py local/ufs-buf4k-reviewed-evt.dtb logs/ufs-takeover-board.json
```

En Pacific queda por demostrar la entrega exclusiva después de LK y proporcionar un mapeo DMA con dirección de bus, duración y coherencia conocidas para las páginas que reserva DXE. Los valores de bus de la VM dependen de sus asignaciones. El siguiente ensayo de placa con ese proveedor será `READ CAPACITY(10)` en ambos extremos de la página antes de acceder al LBA 1. [Investigación del firmware](UFS_LK_EXIT.md)
