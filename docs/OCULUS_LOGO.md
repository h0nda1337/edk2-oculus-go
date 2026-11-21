# El emblema de Oculus bajo EDK2 Go

La pirámide conserva su animación y el saludo azul. Debajo de las letras aparece el emblema gris original, centrado a la misma altura en ambos ojos. Al entrar en la Shell, el emblema se muestra dentro del marco, en su centro. En coordenadas por ojo ocupa 68 × 42 píxeles desde `(606, 699)`. Si la escritura lo alcanza o el texto se desplaza, la consola retira el dibujo entero para dar paso a los caracteres. Al limpiar la pantalla en modo panorámico con fondo negro se vuelve a mostrar. La consola utiliza 65 columnas y 13 filas en celdas de 10 × 25 píxeles. La ventana de 650 × 325 tiene un 20,64 % más de superficie que la anterior de 384 × 456. Los caracteres reducen su ancho un 37,5 % y su alto un 34,2 %. El modo 2 conserva la ventana anterior.

## De dónde vienen los píxeles

BDS intenta primero abrir la partición GPT llamada exactamente `splash`. Comprueba el tamaño, la cabecera y los píxeles mediante `EFI_DISK_IO_PROTOCOL.ReadDisk`. Si el almacenamiento está ausente o los datos no coinciden, busca el símbolo en el framebuffer heredado antes de seleccionar el modo de texto. La traza BDS indica `GPT splash`, `inherited framebuffer` o `absent`. El Go aún necesita un controlador UFS para exponer sus particiones a EDK2. La bienvenida y la Shell arrancan también cuando ninguna de las dos fuentes contiene el emblema esperado. [Lector de la plataforma](../OculusGoPkg/Drivers/GoBdsDxe/OculusLogo.c)

La partición original mide 34 226 176 bytes. El respaldo tiene SHA-256 `d8ba4434e87f8bfc55f33091c2d78401fcea22a068105942285edb2da6869d4a`. La cabecera comienza con `SPLASH!!`, indica 1440 × 2560, tipo 0 y cuenta de bloques comprimidos 0. A partir del byte 512 se leen los píxeles de 24 bits con un paso de 4320 bytes. Los recortes nativos empiezan en `(657,558)` y `(657,1799)` y miden 126 × 204 píxeles. El lector gira las muestras hasta la orientación de lectura, promedia áreas de 3 × 3 y descarta el fondo casi negro. Los CRC32 de los dos recortes reducidos son `93104dc6` y `05be5f49`. Sirven para reconocer este arte concreto. El FD contiene geometría y huellas. Los 2856 valores de luminancia se obtienen durante el arranque y sólo permanecen en RAM. [Inventario](evidence/partitions.json) · [Framebuffer](../OculusGoPkg/Include/Display/Framebuffer.h)

## Reproducir

Desde WSL, pasa la ruta del respaldo privado de `splash` a la prueba de host. Esta enlaza el lector real con una partición de sólo lectura simulada, comprueba los píxeles de ambos ojos y ejercita errores de medio, cabecera, identidad y contenido.

```sh
bash scripts/test-host.sh "$splash"
```

La prueba QEMU añade `--observe-welcome --stock-splash "$splash"` al comando de la [Shell](SHELL_BOOT.md#reproducir). El host carga temporalmente los píxeles en el framebuffer inicial del invitado. El observador compara cada píxel de ambos emblemas bajo el saludo y en el centro de la ventana de la Shell con una reducción independiente del respaldo. También verifica el giro, las letras y los márgenes. Ejecuta el mismo FD sin `--stock-splash` para comprobar el arranque con el framebuffer inicial vacío. Los fotogramas y el respaldo se conservan localmente. La lectura de la UFS del Go y el contenido exacto que deja el Fastboot físico son comprobaciones separadas.

### Lectura directa de la partición en una máquina virtual

```sh
python3 tests/logo_disk_qemu.py "$splash" build/oculus-logo-virtual-gpt
```

El anfitrión construye un disco GPT temporal con el contenido intacto del respaldo. QEMU lo presenta como disco VirtIO de sólo lectura. Una aplicación ARM64 de prueba enlaza el mismo `OculusLogo.c` del BDS y llama exclusivamente al lector de particiones. El invitado debe obtener los píxeles esperados de `splash` y rechazar el mismo contenido con otro nombre GPT. La aplicación de prueba y el disco temporal quedan fuera del FD de Pacific. El ensayo usa AAVMF y prueba el camino GPT/Disk I/O. El controlador UFS integrado de Qualcomm sigue pendiente. [Resultado](evidence/oculus-logo-virtual-gpt-20261120.json)

### Imagen de prueba

El FD de Pacific extraído del contenedor Android mostró el emblema en ambos ojos dentro del marco panorámico y llegó a `Shell>`. El mismo FD con el framebuffer inicialmente vacío llegó al prompt con el centro vacío. Los modelos instrumentados de EL1 y EL2 registraron `inherited framebuffer` y verificaron los píxeles del saludo y de la Shell. La comprobación offline del contenedor es `python tools/run_oculus_logo_once.py`. En el arranque temporal del Go, el operador vio la Shell con cada ojo. El emblema faltó tanto bajo el saludo como en el centro del marco. Android volvió al slot `_a` y los cuatro hashes de `boot_a/b` y `aboot_a/b` coincidieron con los respaldos. [Prueba física](evidence/oculus-logo-transfer-20261120.json) [Revisión y SHA-256 del contenedor](evidence/oculus-logo-review-20261120.json) · [FD de Pacific con el splash original](evidence/oculus-logo-pacific-el1-20261120.json)

El mismo resultado de búsqueda alimenta la bienvenida y la consola. La ausencia del símbolo en ambas es compatible con una búsqueda sin coincidencias. La prueba física no capturó la fuente elegida ni las huellas de las dos regiones de pantalla. Una comprobación que muestre estos datos antes de limpiar la pantalla permitiría distinguir un fallo de reconocimiento de uno de dibujo.

### Qué falta para leer la UFS del Go

El kernel del visor describe un controlador UFS integrado en `624000.ufshc`. En el EDK2 fijado, `UfsPassThruDxe` consume `EDKII_UFS_HOST_CONTROLLER_PROTOCOL` y publica el paso de órdenes SCSI. El proveedor `UfsPciHcDxe` requiere un controlador PCI. En Pacific falta el proveedor para el controlador integrado y validar el estado de relojes, PHY y DMA que deja LK. Después habrá que conectar los drivers de bloques, enumerar el LUN correcto, localizar la partición por su nombre GPT y verificar la huella leída del dispositivo. Ver el emblema por el framebuffer heredado sólo demuestra esa vía. [Hardware inventariado](HARDWARE.md) · [Contrato de UfsPassThruDxe](../edk2/MdeModulePkg/Bus/Ufs/UfsPassThruDxe/UfsPassThruDxe.inf) · [Proveedor PCI](../edk2/MdeModulePkg/Bus/Pci/UfsPciHcDxe/UfsPciHcDxe.inf)
