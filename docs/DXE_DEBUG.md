# DXE_DEBUG — tabla de depuración e imagen de DXE Core

El inicializador de TianoCore intenta reservar 1.025 páginas contiguas para localizar dentro de ellas una página alineada a 4 MiB. Tras liberar los sobrantes, la estructura `EFI_SYSTEM_TABLE_POINTER` sólo ocupa 24 bytes en AArch64. El diagnóstico conserva la arena de 384 páginas que ya llegó a DXE en el Oculus Go. Reserva en el FD su única página situada en un límite de 4 MiB. [Asignación de TianoCore y contrato UEFI](REFERENCES.md#dxe_debug) · [Prueba física anterior](evidence/dxe-tables-transfer-20261119.json)

| Intervalo con fin exclusivo | Uso en este perfil |
| --- | --- |
| `0x80080000–0x80480000` | FD completo que entrega el contenedor Android. |
| `0x80200000–0x80380000` | Arena inicial para HOB, memoria de DXE y la imagen relocalizada. |
| `0x803ff000–0x80400000` | Guarda inferior sin traducción. |
| `0x80400000–0x80401000` | Localizador del depurador, en el offset `0x380000` del FD. |
| `0x80401000–0x80402000` | Guarda superior sin traducción. |

SEC mapea la página como datos sin caché y con ejecución deshabilitada. Antes de transferir el control, usa la instrucción `AT` para comprobar identidad, permiso de escritura y atributos, y verifica que las dos guardas carecen de traducción. DXE comprueba que todo el contenido inicial coincide con la imagen y que el GCD todavía no tiene registrado el recurso. Escribe y lee dos patrones complementarios dependientes de la dirección a lo largo de los 4.096 bytes. Sólo después admite esa página a través de `AddMemorySpace` y pide a los servicios de arranque `AllocatePages(AllocateAddress, EfiBootServicesData, 1, …)`. Coteja el propietario en el GCD y el tipo y la extensión en el mapa EFI. [Ubicación en el FD](../OculusGoPkg/OculusGoPkg.fdf) · [Implementación](../OculusGoPkg/DxeCheckpoint/DebugImage.c)

El código de plataforma inicializa el localizador con la firma UEFI, la dirección de la tabla del sistema y un CRC32 de la estructura completa con el campo CRC puesto inicialmente a cero. La biblioteca `BaseLib` calcula el CRC local del puntero mientras el servicio de arranque de CRC sigue pendiente. La cabecera de la tabla del sistema tiene su propio CRC, que EDK2 actualiza más adelante. El localizador se guarda en `mDebugTable` para que `CoreUpdateDebugTableCrc32` pueda actualizarlo cuando se publique el protocolo de runtime. El código publica por GUID la cabecera original de TianoCore y entrega el control a `DxeMain`. La llamada original a `CoreNewDebugImageInfoEntry` crea el registro de imagen. El array de registros y la entrada individual se asignan desde el pool ordinario de DXE. La reserva de una página corresponde al localizador alineado. El diagnóstico vuelve a recorrer la tabla, comprueba el handle y el protocolo de imagen cargada del núcleo y coteja el CRC antes de pintar la señal final. El registro queda disponible para el código original de actualización y retirada de imágenes. El despacho de drivers y la consola quedan para etapas posteriores. [Punto de llamada](REFERENCES.md#dxe_debug)

| Patrón de un extremo al otro | Última comprobación completada |
| --- | --- |
| Blanco · verde · naranja · verde · blanco | Regresaron los constructores y se comprobaron los tres GUID de DXE_TABLES. |
| Blanco · naranja · cian · naranja · blanco | La página pasó los dos patrones y figura asignada al núcleo. El localizador tiene CRC y los servicios de arranque aceptaron la publicación del cuarto GUID. |
| **Blanco · rojo · cian · rojo · blanco** | El registro de DXE Core está completo. La tabla tiene una entrada de tipo normal y la marca de actualización en curso está despejada. Coinciden el handle, el protocolo de imagen cargada, la tabla del sistema y el CRC del localizador. |

## Resultado en QEMU

El FD de 4.194.304 bytes se extrajo del contenedor Android y se ejecutó en QEMU 10.0.13. Pasaron los 66 casos en EL1 y EL2. Seis llegaron a la señal final, con la caché de instrucciones inicialmente activa o inactiva y con entradas de configuración reordenadas. Los otros 60 terminaron en el punto de rechazo esperado. En los dos controles de tamaño, el asignador original de DXE recibió la petición de 1.025 páginas con `AllocateMaxAddress` y devolvió `EFI_OUT_OF_RESOURCES`. En los arranques positivos, `AllocateAddress` devolvió exactamente la página prevista. [Resultados por caso](evidence/dxe-debug-qemu-20261119.json)

| Resultado del arranque EL1 ordinario | Valor observado |
| --- | --- |
| Página, tipo EFI y propietario GCD | `0x80400000`, una página `EfiBootServicesData`, propiedad del handle de DXE Core |
| Tabla del sistema y CRC32 del localizador | `0x802c0018` y `a262ac63` |
| Entradas de configuración y de imágenes | 4 GUID publicados, 1 registro de imagen normal |
| SHA-256 del FD | `a71bf9c6f72fbe60c44d23eff98920528472a33e5a45817aae8999360923557a` |
| Imagen de arranque temporal | 466.944 bytes · `bdb706210e8a1dfa6e4160ff05f10f4f9fd10dd2bed087a8ea74f0313216fc4b` |

La repetición desde un directorio independiente reprodujo byte por byte el FD extraído y los informes estático y de QEMU. DXE_TABLES reprodujo sus 52 casos anteriores. En Windows pasaron 73 pruebas Python. En Debian pasaron las 72 aplicables y los 19 controles de TrustMeBro. La auditoría de fuentes aceptó las 12 entradas de código de plataforma y el árbol fijado de TianoCore. GCC mantuvo la advertencia de upstream sobre `Prot` en `CoreOpenProtocol` y el enlazador avisó de segmentos RWX en los ELF auxiliares. El observador cotejó las traducciones activas, el texto relocalizado y las guardas del FD.

## Resultado en el Oculus Go

El 19 de noviembre de 2026, Fastboot informó que Secure Boot estaba activo y aceptó el arranque temporal. El operador observó «blanco, rojo, celeste, rojo, blanco». El centro celeste entre franjas rojas corresponde a la señal final. Para pintarla, el firmware tuvo que asignar la página de 4 KiB en `0x80400000`, comprobar la propiedad de la página, recalcular el CRC32 del localizador y encontrar por GUID la tabla de depuración con un registro completo de DXE Core. El handle y el protocolo de imagen cargada coincidieron con los del núcleo. El valor numérico del CRC, los punteros dinámicos y el nivel de excepción del visor siguen sin medirse directamente. [Registro físico](evidence/dxe-debug-transfer-20261119.json) · [Revisión de la imagen](evidence/dxe-debug-review-20261119.json)

Android volvió a arrancar en el slot A. La lectura posterior de 130 MiB confirmó que los SHA-256 de `aboot_a`, `aboot_b`, `boot_a` y `boot_b` coincidían con la lectura previa y con los cuatro respaldos originales. [Cotejo posterior](evidence/dxe-debug-transfer-20261119.json)

La siguiente llamada de inicialización relevante en `DxeMain` es `CoreInitializeEventServices`.

## Reproducción

Desde Debian o WSL, en la raíz del proyecto, con los respaldos locales de boot y del DTB Pacific EVT ya identificados:

```sh
bash scripts/build.sh DEBUG 12 DXE_DEBUG
# run es el directorio de salida indicado por el build; img es una ruta nueva bajo local/.
python3 tools/android_boot.py --fd "$run/OCULUS_GO_DIRECT.fd" --stock-boot "$boot_original" --dtb "$dtb_evt" --output "$img"
bash scripts/check-sec-dxe.sh "$run" "$img"
```

El observador lee la RAM del invitado y recorre la cadena desde la página alineada hasta la imagen cargada. Calcula el CRC32 con zlib, independiente de `BaseLib`. Los controles alteran el último byte inicial, la segunda lectura de prueba, el tamaño solicitado al asignador, el tipo de página EFI, el CRC, el handle de la imagen o el cuarto GUID. Cada control se ejecuta exclusivamente en QEMU. [Observador](../tests/dxe_debug_trace.py)

La comprobación local con `python tools/run_dxe_debug_once.py` coteja la imagen con la revisión y con la identificación archivada del visor. El único arranque temporal de esta revisión ya se consumió en la prueba atendida. [Recuperación](RECOVERY.md)
