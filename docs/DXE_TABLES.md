# DXE_TABLES — constructores y tabla del sistema

El candidato parte del punto que alcanzó DXE_GCD en el Oculus Go. El núcleo DXE original recibe el mismo tipo de HOB de recursos, la misma arena de 1,5 MiB y la misma pila de 64 KiB. Tras el retorno del GCD, `DxeMain` llama a la lista de constructores generada por EDK2. El diagnóstico conserva esa llamada, las instalaciones originales y la búsqueda por GUID de `UefiLib`. [Prueba anterior en el Go](evidence/dxe-gcd-transfer-20261119.json) · [Código del candidato](../OculusGoPkg/DxeCheckpoint/ConfigTables.c)

| Patrón en las dos bandas BGR | Comprobación que acaba de pasar |
| --- | --- |
| Blanco · magenta · cian · magenta · blanco | DXE_GCD ha terminado y ha liberado su mapa. |
| Blanco · azul · amarillo · azul · blanco | Regresó la lista de constructores. El handle y las tablas de sistema, arranque y ejecución coinciden con los del núcleo. El registro de secciones guiadas está inicializado y vacío. |
| Blanco · cian · azul · cian · blanco | La búsqueda por el GUID de servicios DXE devolvió la tabla del núcleo. Su método `GetMemorySpaceDescriptor` encontró la pila con base, tamaño, tipo reservado y propietario correctos. |
| **Blanco · verde · naranja · verde · blanco** | La búsqueda por el GUID de HOB devolvió la copia migrada. Sus bytes coinciden con los de la lista original protegida. La entrada de información de tipos de memoria apunta al objeto esperado. |

## Qué mide QEMU

El observador arranca el FD extraído del contenedor Android. Lee los retornos de cada constructor en AArch64 y comprueba los valores guardados por las bibliotecas y las tres asignaciones de la biblioteca de secciones guiadas. En cada llamada real a `CoreInstallConfigurationTable`, comprueba el GUID, el puntero, el estado devuelto y las entradas visibles en la RAM del emulador. El contador debe pasar de cero a uno, dos y tres. Sigue la llamada a GCD y comprueba la estructura devuelta. Finalmente lee ambas bandas BGR y sus guardas. [Observador](../tests/dxe_tables_trace.py) · [Contratos y fuentes](REFERENCES.md#dxe_tables)

Los seis controles de error alteran en el emulador el puntero de Boot Services guardado por la biblioteca, el contador de entradas, el puntero de servicios DXE, el destino de la entrada HOB, un byte de la copia o la unicidad del GUID. Un control positivo intercambia las entradas primera y tercera antes de la consulta por GUID. El perfil DEBUG detiene la ejecución ante un ASSERT de EDK2.

## Resultado en QEMU y estado físico

El 19 de noviembre de 2026, QEMU 10.0.13 completó 52 casos en EL1 y EL2 sobre el FD extraído de la imagen. Seis llegaron a la señal final, incluidos dos con las entradas reordenadas. Los otros 46 alcanzaron el rechazo previsto. Una segunda ejecución independiente reprodujo byte por byte el FD extraído y los informes estático y de QEMU. [Resultados por caso](evidence/dxe-tables-qemu-20261119.json) · [Revisión de la imagen](evidence/dxe-tables-review-20261119.json)

| Medición en los seis casos positivos | Resultado |
| --- | --- |
| Constructores y retornos | 5 de 5 con `EFI_SUCCESS` |
| Consultas por GUID | Servicios DXE, lista HOB e información de tipos de memoria |
| HOB comparados | 1.232 bytes iguales a los de la página protegida |
| Recurso consultado a través de los servicios publicados | 65.536 bytes de pila reservados a DXE Core |
| CRC32 de la cabecera de la tabla del sistema en este punto | 0. El servicio de cálculo de CRC está pendiente de inicialización. |
| FD local | 4.194.304 bytes · `4233a1a15569148e939ba138cb3bbc00aa6a5e124d5e6d338079d8bb4769e9c3` |
| Imagen Android local | 462.848 bytes · `ef3d54d49981b397cc27a86db9b7574e9c30cb401e846a901b9a40b361816956` |

Los constructores corresponden a depuración por serial, servicios de ejecución, servicios de arranque, UefiLib y extracción de secciones guiadas. La biblioteca de puerto serie enlazada es la implementación nula de EDK2. La señal se dibuja en el framebuffer. La auditoría aceptó los orígenes de la compilación. GCC emitió la advertencia conocida sobre `Prot` en `CoreOpenProtocol` y el enlazador avisó de segmentos RWX en los ELF auxiliares. El observador cotejó las traducciones y el texto ejecutado.

También se reprodujeron los 38 casos de la imagen anterior DXE_GCD con informes idénticos a los archivados. En Windows pasaron las 67 pruebas Python. En Debian pasaron las 66 aplicables y los 19 controles de TrustMeBro. La prueba de bloqueo de archivos depende de Windows.

## Resultado en el Oculus Go

El 19 de noviembre de 2026 el operador describió «blanco, verde, naranja, verde, blanco» tras un arranque temporal de la imagen revisada. Fastboot informó que Secure Boot estaba activo. El centro naranja entre franjas verdes corresponde al último punto de comprobación. En el visor, la lista de constructores regresó y el código localizó las tres entradas por GUID. Los servicios DXE devolvieron el descriptor de la pila reservada de 64 KiB y la copia migrada de los HOB coincidió con los bytes originales. Los retornos individuales de los constructores y los valores numéricos de los punteros se observaron en QEMU. [Registro físico](evidence/dxe-tables-transfer-20261119.json)

Android volvió a arrancar en el slot A. En la primera consulta el visor todavía no aparecía autorizado en ADB. Una vez disponible, la lectura completa de 130 MiB confirmó que los SHA-256 de `aboot_a`, `aboot_b`, `boot_a` y `boot_b` coincidían con la lectura previa y con los respaldos originales. [Cotejo posterior](evidence/dxe-tables-transfer-20261119.json)

## Reproducción y prueba atendida

Desde la raíz del repositorio en Debian/WSL, usa los respaldos locales verificados de boot y del DTB Pacific EVT. Asigna a `run` el directorio de salida que imprima la compilación y a `img` una ruta nueva bajo `local/`.

```sh
bash scripts/build.sh DEBUG 12 DXE_TABLES
python3 tools/android_boot.py --fd "$run/OCULUS_GO_DIRECT.fd" --stock-boot "$boot_original" --dtb "$dtb_evt" --output "$img"
bash scripts/check-sec-dxe.sh "$run" "$img"
```

El comando `python tools/run_dxe_tables_once.py` valida en el PC los archivos de la revisión congelada. El intento registrado de DXE_TABLES ya se consumió durante la prueba atendida. Se cotejan los hashes de las cuatro particiones desde Android, se identifica el visor en Fastboot y se envía la imagen por arranque temporal. El operador describe el patrón antes de volver a Android para el cotejo posterior. El intento queda registrado en un archivo local exclusivo de DXE_TABLES. [Recuperación](RECOVERY.md)

## Siguiente tramo hacia la Shell

El diagnóstico se detiene justo antes de `CoreInitializeDebugImageInfoTable`. En la revisión fijada, ese inicializador solicita 1.025 páginas contiguas para seleccionar una página alineada a 4 MiB. La arena publicada tiene 384 páginas y ocupa el intervalo semiabierto `0x80200000–0x80380000`. Dentro de ese intervalo tampoco hay una dirección múltiplo de 4 MiB. Para conservar el inicializador original hay que demostrar una región libre suficiente. Un asignador más pequeño también requeriría demostrar que DXE puede ser propietario de una página en una dirección alineada. Más adelante habrá que despachar drivers desde el volumen y conectar una consola de texto al GOP para presentar la Shell. [Asignador de la tabla de depuración](REFERENCES.md#dxe_tables)

El perfil posterior DXE_DEBUG utiliza la página alineada del propio FD en `0x80400000`. La incorpora al GCD después de cualificarla y mantiene los registros de imágenes en el pool de DXE. [Implementación y pruebas de DXE_DEBUG](DXE_DEBUG.md)
