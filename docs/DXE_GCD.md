# DXE_GCD — imagen cargada, migración de HOB y mapa de recursos

Esta imagen continúa desde el punto verde de DXE_MEM. Ejecuta los dos inicializadores originales de TianoCore y se detiene antes de los constructores de DXE. La medición termina en el framebuffer heredado. [Implementación del diagnóstico](../OculusGoPkg/DxeCheckpoint/ImageGcd.c) · [Fuentes](REFERENCES.md#dxe_gcd)

| Patrón de un extremo al otro | Última comprobación completada |
| --- | --- |
| Blanco · azul · verde · azul · blanco | Pasaron las pruebas del asignador de DXE_MEM. Comienza la inicialización de los servicios de imagen. |
| Blanco · amarillo · magenta · amarillo · blanco | El inicializador regresó con éxito. El protocolo de imagen cargada consultado mediante el handle de DXE Core coincide con el módulo PE y la tabla del sistema. |
| Blanco · naranja · blanco · naranja · blanco | El GCD regresó con éxito. El puntero devuelto y el puntero global conducen a la misma copia de la lista HOB. Todos los bytes coinciden con la copia tomada antes de la llamada. La página original conserva el GUID de la imagen y figura como `EfiBootServicesData` en el mapa EFI. |
| **Blanco · magenta · cian · magenta · blanco** | El mapa GCD cubre el espacio del CPU HOB de extremo a extremo, identifica la arena como RAM y la pila como reservada, ambas asignadas al núcleo. Se liberó el buffer del mapa. |

El CPU HOB que ya empleaba el diagnóstico declara 32 bits de direccionamiento. Dentro de ese espacio, el único recurso de RAM declarado es la arena de 1,5 MiB dentro del firmware. La pila activa ocupa otros 64 KiB, de `0x8046f000` a `0x8047f000` (fin exclusivo). SEC entrega un HOB de recurso reservado y el HOB de asignación de pila para ese mismo intervalo. El mapa esperado clasifica el resto como `EfiGcdMemoryTypeNonExistent`. La dirección del framebuffer sigue mapeada por las tablas de traducción de SEC para la señal visual. El inventario físico de RAM y MMIO del SoC tiene un alcance distinto. [Mapa del proyecto](MEMORY_MAP.md)

El despachador de esta revisión de EDK2 conserva un puntero al GUID del módulo en la lista original. SEC publica una asignación de una página de 4 KiB al principio de la arena como `EfiBootServicesData`. Tras la migración, el diagnóstico consulta el mapa EFI y comprueba que tanto la copia como los bytes originales siguen intactos. [Inicialización y consumo del GUID](REFERENCES.md#dxe_gcd)

La imagen registrada en esta prueba es DXE Core. La carga de otro ejecutable con `LoadImage` y `StartImage`, el despacho de drivers, el GOP físico y la Shell son hitos posteriores. La prueba consulta el mapa GCD de memoria. El espacio de puertos de E/S queda fuera de la medición.

## Resultado en el Oculus Go

El 19 de noviembre de 2026, el operador observó «blanco, morado, celeste, morado, blanco» tras el arranque temporal con `Secure boot: true`. El centro celeste y los lados morados coinciden con la señal final de esta imagen. Esa señal confirma en el visor la consulta del protocolo de imagen cargada, la migración de los HOB con la página original preservada, la clasificación y propiedad de la RAM y de la pila, y la liberación del buffer del mapa GCD. Los valores numéricos de los punteros y el nivel de excepción del visor siguen sin medirse. [Registro físico](evidence/dxe-gcd-transfer-20261119.json)

Android completó el arranque en el slot A. ADB estuvo temporalmente `offline` y una primera lectura de `boot_a` llegó incompleta. La repetición leyó los 130 MiB de `aboot_a`, `aboot_b`, `boot_a` y `boot_b`. Los cuatro SHA-256 coincidieron con la lectura anterior al ensayo y con los respaldos originales. [Comprobación posterior](evidence/dxe-gcd-transfer-20261119.json)

## Resultado en QEMU

QEMU 10.0.13 ejecutó 38 casos sobre el FD extraído del contenedor. En EL1 y EL2 se alcanzó `TrialGcdComplete` con la caché de instrucciones inicialmente encendida y apagada. Los otros 34 casos terminaron en el punto de rechazo previsto. La prueba comparó las dos bandas completas y sus guardas. La segunda ejecución produjo informes estático y de QEMU idénticos byte por byte. [Informe por caso](evidence/dxe-gcd-qemu-20261119.json) · [Revisión de la imagen](evidence/dxe-gcd-review-20261119.json)

| Medición en los cuatro arranques positivos | Resultado |
| --- | --- |
| Tamaño de DXE Core en el protocolo y el PE relocalizado | 200 704 bytes |
| Lista HOB copiada y cotejada | 1 232 bytes |
| RAM en el mapa GCD | 1 572 864 bytes, asignados al núcleo |
| Pila en el mapa GCD | 65 536 bytes reservados, asignados al núcleo |
| Página que contiene el GUID | 4 096 bytes asignados como `EfiBootServicesData` en el mapa EFI |
| FD y SHA-256 | 4 194 304 bytes · `b5a56101b528ebbb3343606fa6cba4030074b6f4a8c26fb3f3ec8d2909c1534e` |
| Imagen Android y SHA-256 | 462 848 bytes · `a0594d52bd4077dec0e940b9aff68a298003135f9bef8818a327abf8c145a5d2` |

La auditoría aceptó los archivos originales del proyecto y la revisión fijada de EDK2. Las 60 pruebas de host pasaron en Windows. Debian pasó los 19 controles de TrustMeBro y todas las pruebas Python aplicables. La prueba del bloqueo de archivos de Windows se ejecutó en Windows. SEC_DXE y DXE_MEM reprodujeron sus informes con el FD y los símbolos de cada compilación. GCC 14 conserva la advertencia de upstream en `CoreOpenProtocol`. El enlazador avisa de segmentos RWX en ELF auxiliares. El observador comprueba los permisos del texto relocalizado y la tabla de traducción que usa el procesador emulado.

## Qué cambió durante la prueba

El primer FD llegaba a los dos inicializadores, pero el mapa etiquetaba la pila como inexistente a pesar de que DXE Core figuraba como propietario. El observador rechazó ese resultado en EL1. Añadir el HOB de recurso reservado corrigió el tipo de la pila. El observador también confirmó que `gDxeCoreFileName` seguía apuntando a la lista original tras la migración. El candidato incorpora la reserva de la página del GUID. Los prototipos intermedios quedaron en el PC.

## Reproducción

Desde la raíz del repositorio en Debian/WSL, con el boot y el DTB originales en las rutas locales indicadas y un nombre de salida nuevo bajo `local/`:

```sh
bash scripts/build.sh DEBUG 12 DXE_GCD
# Usar como run el directorio DEBUG-DXE_GCD indicado por el build.
python3 tools/android_boot.py --fd "$run/OCULUS_GO_DIRECT.fd" --stock-boot "$boot_original" --dtb "$dtb_evt" --output "$img"
bash scripts/check-sec-dxe.sh "$run" "$img"
```

El verificador extrae el FD del contenedor, coteja los bytes del FV y del PE empaquetados, y arranca ese FD bajo QEMU. El observador contrasta las llamadas reales, la copia de los HOB, los descriptores, las dos bandas del framebuffer y las guardas. En los controles negativos específicos modifica en la RAM del emulador el tamaño de la imagen registrada, un byte de la lista recién copiada, el tipo EFI de la página original, el propietario de la RAM o el tipo de la pila en el mapa devuelto. Cada control debe detenerse en su señal anterior. [Observador](../tests/dxe_gcd_trace.py)
