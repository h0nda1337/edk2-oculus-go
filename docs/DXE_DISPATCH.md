# DXE_DISPATCH

La prueba continúa desde el [punto DXE_DEBUG observado en el Oculus Go](evidence/dxe-debug-transfer-20261119.json). El volumen interior contiene DXE Core y un único driver, DevicePathDxe de TianoCore. Su expresión de dependencia es TRUE, END. El despachador lo descubre a través del protocolo Firmware Volume 2. El cargador lee el PE a partir de la ruta de archivo del volumen, lo relocaliza y registra la imagen en la tabla de depuración. El driver publica Device Path Utilities. Esta interfaz permite a consumidores como la Shell recorrer rutas UEFI.

## Qué acredita la señal

| Franjas de extremo a extremo | Punto alcanzado |
| --- | --- |
| Blanco · rojo · celeste · rojo · blanco | Comprobación anterior de DXE_DEBUG. |
| Blanco · celeste · azul · celeste · blanco | Han vuelto los inicializadores de eventos, volúmenes, extracción de secciones y despachador. Se va a ejecutar el bucle de despacho. |
| Blanco · amarillo · azul · amarillo · blanco | El cargador de DXE entregó un handle para el archivo previsto. Las páginas de texto del driver ya son de sólo lectura y ejecutables. Se va a llamar a StartImage. |
| **Blanco · naranja · verde · naranja · blanco** | StartImage y el despachador devolvieron éxito. LocateProtocol recuperó Device Path Utilities y su método GetDevicePathSize devolvió 4 para un nodo de fin de ruta de cuatro bytes. |

## Permisos de memoria

El perfil conserva la arena de 384 páginas en el FD y las guardas de DXE_DEBUG. SEC hace accesible como datos la página L3 que describe la arena. La página está fuera de ese intervalo, en el espacio de tablas ya reservado en el FD. La dirección se comprueba en compilación contra la disposición de SEC. La imagen del driver se carga con ejecución deshabilitada. Antes de StartImage, la plataforma comprueba el GUID del archivo, la cabecera PE ARM64, el tamaño y orden de sus secciones, el RVA de entrada y los permisos actuales de cada página de texto. Sólo esas páginas cambian a sólo lectura y ejecutables. La transición invalida primero las entradas, sincroniza las traducciones en el EL activo y publica las nuevas entradas antes de sincronizar la caché de instrucciones. Los datos y la pila conservan la prohibición de ejecución.

Este perfil termina tras la primera llamada al protocolo. El cambio de permisos se limita a la imagen que permanece cargada hasta ese punto. Un despachador de uso general necesitará gestionar también la descarga de imágenes y la reutilización de sus páginas.

## Reproducción offline

Desde Debian o WSL en la raíz del proyecto:

```sh
bash scripts/build.sh DEBUG 12 DXE_DISPATCH
python3 tools/android_boot.py --fd "$run/OCULUS_GO_DIRECT.fd" --stock-boot "$boot_original" --dtb "$dtb_evt" --output "$imagen"
bash scripts/check-sec-dxe.sh "$run" "$imagen"
```

`run` es el directorio indicado al final de la compilación. La imagen se guarda bajo `local/`. El observador extrae el FD del contenedor temporal, coteja el PE del driver con la sección del volumen y observa su punto de entrada y su servicio en la RAM del invitado. [Fuentes de TianoCore](REFERENCES.md#dxe_dispatch) · [Observador QEMU](../tests/dxe_dispatch_trace.py)

## Resultado

QEMU 10.0.13 completó 74 casos en TCG AArch64, repartidos entre EL1 y EL2. Seis llegaron a la señal verde con lados naranjas. Cubren el arranque ordinario, la caché de instrucciones inicialmente activa y la reordenación de la tabla de configuración en cada EL. Los otros 68 alcanzaron su punto de rechazo previsto. Los monitores comprobaron la superficie completa de las dos bandas, las guardas y las tablas de traducción. [Resultados por caso](evidence/dxe-dispatch-qemu-20261119.json)

| Observación en el arranque ordinario | Resultado en el invitado |
| --- | --- |
| Volumen interior entregado por SEC | 270.592 bytes, cotejados con el FV compilado |
| Driver cargado por DXE | 65.536 bytes en `0x80258000` |
| Texto en sólo lectura, ejecutable | 13 páginas en `[0x80259000, 0x80266000)` |
| Registro de depuración | Dos imágenes. El registro del driver apunta a su handle y protocolo Loaded Image. |
| Primera operación desde la tabla del protocolo | GetDevicePathSize devolvió 4 |
| FD de 4 MiB | SHA-256 `8cb6ba32f7b9b8051c4a7fd9779afc125aae951d48f750b8de8e5586574f93d1` |
| Imagen temporal local | 479.232 bytes, SHA-256 `7ea650a41aabd0801904037fcda3c9b8de1b275640c3c2f3bc8a2fa772520af2` |

Cuatro controles nuevos ejercitan puntos distintos. Un DEPEX falso en la copia de RAM impidió la llamada al cargador. Una ruta ausente produjo EFI_INVALID_PARAMETER. Un GUID de archivo distinto detuvo la prueba antes de habilitar la ejecución del texto. Un retorno alterado de la primera operación del protocolo impidió la señal final incluso después de un StartImage correcto.

El enlazador informó de segmentos RWX en los ELF intermedios y GCC mantuvo la advertencia de upstream sobre `Prot` en CoreOpenProtocol. Los permisos documentados arriba corresponden a las traducciones de las páginas de la imagen ejecutada. La auditoría de compilación aceptó los orígenes de todos los archivos resueltos. [Avisos de procedencia](../THIRD_PARTY_NOTICES.md)

Dos ejecuciones completas de DXE_DISPATCH con invitados independientes y distintos grados de paralelismo produjeron informes idénticos byte por byte. La regresión de DXE_DEBUG reprodujo los informes estático y de QEMU de la revisión anterior, incluidos sus 66 casos. En Windows pasaron 78 pruebas Python. En Debian pasaron 77 y se omitió una específica de Windows. El ejecutable de host pasó además sus 19 comprobaciones de TrustMeBro.

La prueba del mismo contenedor en el Oculus Go está pendiente. La comprobación local de la [revisión](evidence/dxe-dispatch-review-20261119.json) se ejecuta con `python tools/run_dxe_dispatch_once.py`. El procedimiento físico atendido usa el arranque temporal y el retorno a Android documentados en [recuperación](RECOVERY.md).
