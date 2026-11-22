# Lectura de splash desde la UFS de Pacific

## Ruta del lector

Al comenzar la bienvenida, BDS localiza el protocolo UFS Host Controller y enlaza el transporte del volumen de firmware. Abre Extended SCSI Pass Thru y el protocolo de capacidad en ese mismo handle. Busca primero el LUN 4 y valida la respuesta en los dos extremos de su página antes de pedir la GPT. Pasa por alto las unidades especiales, incluidas las de boot y RPMB. Si encuentra los píxeles originales, la bienvenida y la consola reciben el mismo emblema muestreado en RAM. [Lector UFS](../OculusGoPkg/Library/GoUfsSplashLib/UfsSplash.c) · [Integración con BDS](../OculusGoPkg/Drivers/GoBdsDxe/GoBds.c)

Las únicas órdenes SCSI que construye el lector son `READ CAPACITY(10)` y `READ(10)`. La ventana de transferencia alineada mide 64 KiB. Cada respuesta debe indicar éxito del host y del dispositivo y contener el número de bytes solicitado. El código valida la cabecera GPT primaria, el CRC de su tabla de entradas, la etiqueta UTF-16 exacta y los límites de la partición. Rechaza una etiqueta duplicada en una tabla. El decodificador recibe una función de lectura acotada a la partición. Comprueba el tamaño, la cabecera `SPLASH!!` y el CRC del emblema reducido antes de entregarlo al compositor. [Decodificador compartido](../OculusGoPkg/Drivers/GoBdsDxe/OculusLogo.c)

El LUN 4 se comprueba contra la [geometría medida en Pacific](UFS_SHELL_BUFFER.md). La ruta alternativa de descubrimiento de unidades ordinarias admite bloques de 512 a 4096 bytes en potencias de dos, una tabla primaria de hasta 64 KiB y capacidades representables por READ CAPACITY(10). Ante una tabla dañada abandona esa unidad. El código de BDS puede continuar con su ruta de partición UEFI o de framebuffer heredado y con el arranque de la Shell. La operación de lectura es privada de BDS. El volumen normal de la Shell incluye el transporte adaptado de TianoCore. El proveedor DXE de la controladora integrada de Pacific sigue pendiente.

## Ensayo ARM64

Desde el árbol preparado para compilar EDK2 en Debian/WSL, con `splash` apuntando a la copia privada cuyo SHA-256 figura en el inventario, ejecutar

```sh
bash scripts/build-qemu-ufs-drivers.sh
python3 tests/ufs_splash_qemu.py "$splash" build/ufs-splash
```

El arranque de AAVMF utiliza una ESP VirtIO que sólo contiene tres ejecutables EFI. El respaldo vive en otra conexión, un controlador UFS con varias unidades de sólo lectura. El huésped enlaza el mismo lector y el mismo decodificador que BDS. El programa de prueba inicia cada proveedor mediante su protocolo Driver Binding. La traza de órdenes identifica qué operaciones llegaron a cada unidad. El modelo utiliza registros de controlador, UPIU y transferencias DMA. QEMU no modela la PHY de Qualcomm. [Banco de prueba](../tests/ufs_splash_qemu.py) · [Modelo UFS de QEMU](https://www.qemu.org/docs/master/system/devices/ufs.html)

**CONFIRMED-QEMU.** Se recuperó el emblema con `splash` en la unidad 4, en la 2 y en una configuración con sólo las unidades 0 y 4. El CRC de los 68 × 42 píxeles fue `93104dc6` en los tres casos. El invitado limpió su GOP antes de la búsqueda, dibujó la muestra y volvió a leer sus 2.856 píxeles. El lector rechazó la etiqueta distinta, los dos errores de CRC de GPT, la partición fuera de rango, la etiqueta duplicada y los píxeles alterados. Los hashes de los discos al terminar coincidieron con los iniciales. [Resultados y órdenes por LUN](evidence/ufs-splash-qemu-20261120.json)

En la traza SCSI sólo aparecen las órdenes de capacidad y lectura. En la traza de gestión UFS se ven lectura de descriptor, lectura de bandera y ajuste de bandera. El proveedor EDK2 inicializa el dispositivo virtual mediante `fDeviceInit`. Esta prueba distingue las operaciones sobre el controlador de las escrituras de datos al medio.

El FD `NORMAL` de Pacific compiló en DEBUG, pasó la auditoría de procedencia y arrancó en el modelo EL1 con framebuffer vacío. El observador verificó la bienvenida y leyó `Shell>` en las dos vistas sin emblema cuando faltaba el transporte de almacenamiento. Esta ejecución comprueba la continuidad del arranque. El ensayo AAVMF anterior comprueba la lectura desde UFS. [Resultado del FD de Pacific](evidence/ufs-splash-pacific-shell-20261120.json)

### Dos fallos reproducidos durante el ensayo

En el primer comando después del encendido, QEMU devolvió `UNIT ATTENTION` con ASC/ASCQ `29/00`. El lector comprueba la información de sense devuelta por el transporte y repite esa lectura una sola vez. Exige una transferencia completa para aceptar sus datos.

Con unidades virtuales 0 y 4 y las direcciones intermedias vacías, el transporte EDK2 original sólo anunció la 0. Una consulta fallida a un descriptor dejaba a cero la longitud para la siguiente. El parche de la plataforma repone el tamaño antes de consultar cada unidad y comprueba que el descriptor devuelto corresponde a ese índice. El script extrae el módulo del commit fijado, prepara una copia de compilación privada y aplica el cambio. [Parche de enumeración](../tests/UfsSplashApp/ufs-sparse-units.patch)

## Enlace con el hardware físico

| Dato | Evidencia | Estado |
| --- | --- | --- |
| Host integrado `624000.ufshc`, rango `0x624000 + 0x2500`, `jedec,ufs-1.1`, variante `qcom,ufs_variant` | DT de ejecución del Go, nodo `ufshc@624000` | CONFIRMED en Android |
| PHY QMP de 14 nm a `0x627000 + 0xda8`, ICE a `0x630000 + 0x8000` | Nodos `ufsphy@627000` y `ufsice@630000` del mismo DT | CONFIRMED como recursos de placa |
| Una vía por dirección, gear 3 en funcionamiento | DT y mensajes archivados `ufshcd_print_pwr_info` de Android | CONFIRMED después de inicializar Linux |
| `splash` en `/dev/block/sde34`, 34 226 176 bytes | Inventario por nombre y SHA-256 del respaldo privado | CONFIRMED para el respaldo |
| H:C:T:L `0:0:0:4`, bloques de 4096 bytes, LBA 1 037 582 a 1 045 937 inclusive | Enlace SCSI de `sde`, sysfs y entrada 34 de la GPT primaria | CONFIRMED en el Go físico |
| Alimentación, cuatro ramas de reloj, versión y colas a la entrada en SEC | [Panel físico tras LK](evidence/ufs-handoff-transfer-20261121.json) | CONFIRMED en este arranque. UFSHCI 1.1 habilitado, ambas listas en marcha y ambos doorbells a cero. La [sonda posterior](evidence/ufs-queues-transfer-20261121.json) observó las bases DMA de ambas listas. Quedan pendientes el estado detallado de la PHY y la traducción DMA. |

La versión del registro UFSHCI y la compatibilidad descrita por el DT son datos distintos. El kernel oficial configura la PHY, los relojes de las vías y el enlace mediante callbacks Qualcomm. El proveedor PCI usado en la máquina virtual sólo reconoce dispositivos PCI. El proveedor PCI y la aplicación de ensayo se cargan desde la ESP virtual. El transporte que traduce las órdenes SCSI a UFS se compila desde la misma fuente para el volumen normal y el emulador. [Driver del kernel oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufs-qcom.c) · [Inventario](evidence/partitions.json)

La lectura física situó `splash` entre los bytes `0xFD50E000` y `0xFF5B1FFF` del LUN 4, ambos incluidos. Los 8356 bloques suman 34 226 176 bytes. Se verificaron los CRC de la cabecera GPT y del conjunto de entradas. El inicio y el tamaño de sysfs, expresados en sectores de 512 bytes, dieron exactamente el mismo intervalo. [Medición física](evidence/ufs-splash-physical-layout-20261120.json)

La prueba con la GPT capturada reprodujo esos LBA en QEMU. En el visor, la sonda de SEC completó las trece lecturas y mostró `UFS DONE`. [LUN 4 y entrega de LK](UFS_HANDOFF.md)
