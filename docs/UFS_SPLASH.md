# Lectura de splash desde la UFS de Pacific

## Ruta del lector

Al comenzar la bienvenida, BDS busca un controlador que publique en el mismo handle los protocolos UFS Host Controller y Extended SCSI Pass Thru de EDK2. La biblioteca del proyecto enumera las unidades ordinarias que el transporte declara activas. Pasa por alto las unidades especiales, incluidas las de boot y RPMB. Si encuentra los píxeles originales, la bienvenida y la consola reciben el mismo emblema muestreado en RAM. [Lector UFS](../OculusGoPkg/Library/GoUfsSplashLib/UfsSplash.c) · [Integración con BDS](../OculusGoPkg/Drivers/GoBdsDxe/GoBds.c)

Las únicas órdenes SCSI que construye el lector son `READ CAPACITY(10)` y `READ(10)`. La ventana de transferencia alineada mide 64 KiB. Cada respuesta debe indicar éxito del host y del dispositivo y contener el número de bytes solicitado. El código valida la cabecera GPT primaria, el CRC de su tabla de entradas, la etiqueta UTF-16 exacta y los límites de la partición. Rechaza una etiqueta duplicada en una tabla. El decodificador recibe una función de lectura acotada a la partición. Comprueba el tamaño, la cabecera `SPLASH!!` y el CRC del emblema reducido antes de entregarlo al compositor. [Decodificador compartido](../OculusGoPkg/Drivers/GoBdsDxe/OculusLogo.c)

Este primer lector admite bloques de 512 a 4096 bytes en potencias de dos, una tabla primaria de hasta 64 KiB y capacidades representables por READ CAPACITY(10). Ante una tabla dañada abandona esa unidad. El código de BDS puede continuar con su ruta de partición UEFI o de framebuffer heredado y con el arranque de la Shell. La operación de lectura es privada de BDS. El transporte genérico de TianoCore sí dispone de otras órdenes y sólo se incorpora al entorno virtual en esta fase.

## Ensayo ARM64

Desde el árbol preparado para compilar EDK2 en Debian/WSL, con `splash` apuntando a la copia privada cuyo SHA-256 figura en el inventario, ejecutar

```sh
bash scripts/build-qemu-ufs-drivers.sh
python3 tests/ufs_splash_qemu.py "$splash" build/ufs-splash
```

El arranque de AAVMF utiliza una ESP VirtIO que sólo contiene tres ejecutables EFI. El respaldo vive en otra conexión, un controlador UFS con varias unidades de sólo lectura. El huésped enlaza el mismo lector y el mismo decodificador que BDS. El programa de prueba inicia cada proveedor mediante su protocolo Driver Binding. La traza de órdenes identifica qué operaciones llegaron a cada unidad. El modelo utiliza registros de controlador, UPIU y transferencias DMA. QEMU no modela la PHY de Qualcomm. [Banco de prueba](../tests/ufs_splash_qemu.py) · [Modelo UFS de QEMU](https://www.qemu.org/docs/master/system/devices/ufs.html)

**CONFIRMED-QEMU.** Se recuperó el emblema con `splash` en la unidad 4, en la 2 y en una configuración con sólo las unidades 0 y 4. El CRC de los 68 × 42 píxeles fue `93104dc6` en los tres casos. El invitado limpió su GOP antes de la búsqueda, dibujó la muestra y volvió a leer sus 2.856 píxeles. El lector rechazó la etiqueta distinta, los dos errores de CRC de GPT, la partición fuera de rango, la etiqueta duplicada y los píxeles alterados. Los hashes de los discos al terminar coincidieron con los iniciales. [Resultados y órdenes por LUN](evidence/ufs-splash-qemu-20261120.json)

En la traza SCSI sólo aparecen las órdenes de capacidad y lectura. En la traza de gestión UFS se ven lectura de descriptor, lectura de bandera y ajuste de bandera. El proveedor EDK2 inicializa el dispositivo virtual mediante `fDeviceInit`. Esta prueba distingue las operaciones sobre el controlador de las escrituras de datos al medio.

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
| H:C:T:L, inicio GPT, tamaño de bloque de esa unidad | Pendiente de leer el enlace SCSI y la GPT primaria de la unidad | UNKNOWN para la integración física |
| Estado de los relojes, PHY, colas de LK y dominio DMA en la entrada a EDK2 | Datos de Android posteriores al arranque | UNKNOWN a la entrada |

La versión del registro UFSHCI y la compatibilidad descrita por el DT son datos distintos. El kernel oficial configura la PHY, los relojes de las vías y el enlace mediante callbacks Qualcomm. El proveedor PCI usado en la máquina virtual sólo reconoce dispositivos PCI. Los dos proveedores virtuales y la aplicación de ensayo se compilan fuera del volumen de firmware de Pacific. [Driver del kernel oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufs-qcom.c) · [Inventario](evidence/partitions.json)

La siguiente captura se hace con Android iniciado y ADB root. El colector verifica la identidad, coteja el enlace `splash` con el inventario y compara sus límites sysfs con los de la GPT. Lee el bloque de cabecera y los bloques de entradas, además de los atributos disponibles de energía y DMA. Guarda el resultado en `local/`. La captura permitirá utilizar la geometría del Go en el emulador y diseñar una observación posterior en la entrada al firmware. [Colector de sólo lectura](../tools/collect_ufs_layout.py)
