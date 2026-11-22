# Búfer DMA propio de la Shell

El lector del emblema que usa BDS reserva su área de trabajo con `AllocatePages(AllocateAnyPages, EfiBootServicesData)`. El controlador UFS recibe dos órdenes síncronas `READ CAPACITY(10)` del LUN 4. Una deposita ocho bytes al principio de la primera página de datos y la otra a partir del desplazamiento `0xFF8`. Cada orden obtiene su propia dirección de bus. El transporte comunica la que usó para construir el PRDT de esa orden y completa `Unmap` antes de que el lector compruebe los bytes. [Lector](../OculusGoPkg/Library/GoUfsSplashLib/UfsSplash.c) · [Contrato](../OculusGoPkg/Include/Protocol/GoUfsCapacity.h)

El resultado esperado es `00 11 FF FF 00 00 10 00` en cada extremo. El lector comprueba la geometría, la longitud y las guardas en RAM. Descarta el resultado completo ante un error. La prueba aislada libera la reserva al terminar. En el arranque normal, el lector conserva la misma reserva para pedir el primer bloque de la GPT. Las lecturas posteriores obtienen un nuevo mapeo para su propia longitud. La zona de trabajo ampliada permite procesar la tabla de particiones y el emblema por lotes de hasta 64 KiB. [Medición de la geometría](evidence/ufs-splash-physical-layout-20261120.json)

El lector da prioridad al LUN 4 que anuncia la controladora. Si está presente y falla la validación, termina la búsqueda UFS en esa controladora. Para los discos virtuales anteriores que presentan `splash` en otra unidad ordinaria, se conserva la búsqueda por etiqueta cuando el LUN 4 está ausente.

## Resultados en QEMU

Los ocho escenarios terminaron con el resultado esperado. En los tres positivos, ambos extremos recibieron la respuesta completa. Estas direcciones corresponden a las máquinas virtuales de la prueba. [Informe de capacidad](evidence/ufs-shell-buffer-20261122.json)

| Prueba | CPU, inicio y final | DMA utilizada, inicio y final |
| --- | --- | --- |
| 768 MiB | `0x6EA64000` / `0x6EA64FF8` | `0x6EA64000` / `0x6EA64FF8` |
| 1536 MiB | `0x9EA64000` / `0x9EA64FF8` | `0x9EA64000` / `0x9EA64FF8` |
| Búfer de rebote, 768 MiB | `0x6EA64000` / `0x6EA64FF8` | `0x6EA61000` / `0x6EA61000` |

El proveedor de prueba reutilizó la misma dirección de rebote para dos peticiones sucesivas. En los otros cinco escenarios se rechazaron la geometría incorrecta, un mapa denegado, un mapa de sólo cuatro bytes, una guarda alterada y la ausencia del proveedor. Se observaron 19 mapeos de datos aceptados y 19 liberados, 18 órdenes de capacidad y cero lecturas o escrituras de sectores.

Después se ejecutó el lector del emblema sobre una reconstrucción virtual de sólo lectura con la GPT y la partición preservadas. La traza registró tres órdenes de capacidad, incluido el reintento inicial, antes de la primera lectura del LBA 1. El lector verificó la GPT, encontró `splash` en la entrada 34 y dibujó el emblema. La lectura de píxeles de GOP coincidió con la huella esperada `93104DC6`. [Traza de bloques y resultado gráfico](evidence/ufs-shell-buffer-pacific-gpt-qemu-20261122.json)

Los diez casos de regresión del lector cubrieron también una GPT con CRC inválido, entradas duplicadas o fuera de rango, etiquetas equivocadas, un emblema inválido y una controladora que ubica la partición en otro LUN. En el caso de geometría inesperada del LUN 4, las únicas órdenes fueron dos intentos de capacidad. El lector terminó antes de solicitar el LBA 1. [Regresión del lector con discos sintéticos](evidence/ufs-shell-buffer-gpt-regression-20261122.json)

El control de arranque ejecutó en QEMU el FD `NORMAL` de la plataforma, en EL1 con el DTB EVT preservado y sin una controladora UFS conectada. La aplicación Shell y el driver `UfsPassThruDxe` dentro del volumen coincidieron byte a byte con sus binarios compilados. La auditoría cotejó 103 listas de dependencias y las fuentes del transporte con los hashes fijados. El framebuffer mostró `Shell>` completo en ambos ojos. [Arranque del FD y hashes](evidence/ufs-shell-buffer-normal-qemu-20261122.json)

## Estado de Pacific al probar el transporte PCI

**UNKNOWN** para la dirección DMA física de una página dinámica. BDS busca un handle con `EDKII_UFS_HOST_CONTROLLER_PROTOCOL`. El volumen normal incluye el transporte SCSI que se enlaza a ese handle. La siguiente dependencia en Pacific es un proveedor para el controlador UFS integrado que pueda mapear, sincronizar y liberar la memoria del cliente durante DXE. QEMU aporta un proveedor PCI para su propio dispositivo. La dirección de una asignación caduca al liberar su mapeo. La lectura continua de 4.096 bytes requiere un mapeo de esa longitud y una prueba propia. El antiguo `0x80441000` está ocupado por el FV de la Shell. [Mapa del FD y estado del controlador](UFS_BOARD_ROUTING.md)

La integración posterior ya incorpora el enumerador del DTB y el driver de host al FV normal. La traducción física sigue dependiendo del servicio DMA de la placa y de la entrega de las colas. [Controlador integrado en DXE](UFS_PLATFORM_DXE.md)

## Reproducción en QEMU

Desde Debian/WSL, en la raíz del proyecto, compilar los binarios del emulador y ejecutar la aplicación de capacidad antes del ensayo de lectura de sectores.

```sh
bash scripts/build-qemu-ufs-drivers.sh
python3 tests/ufs_shell_buffer_qemu.py --report logs/ufs-shell-buffer.json
bash scripts/build.sh DEBUG 12 NORMAL
```

La regresión del emblema verifica el SHA-256 del respaldo privado antes de construir el disco virtual. La segunda orden usa además la captura local del encabezado y las entradas GPT.

```sh
python3 tests/ufs_splash_qemu.py "$splash_img" build/ufs-shell-buffer-fixtures
python3 tests/ufs_splash_qemu.py "$splash_img" build/ufs-shell-buffer-captured --pacific-layout "$layout_dir"
```
