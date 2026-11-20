# DXE_GOP

Este perfil parte de `DXE_DISPATCH`, cuyo primer driver respondió en el visor. Prueba el paso siguiente en la misma ruta de arranque temporal. El volumen DXE contiene el núcleo, `DevicePathDxe` de EDK2 e `InheritedGopDxe` del proyecto. La dependencia del segundo driver exige que el primero publique Device Path Utilities. El segundo usa esa interfaz para construir su ruta de dispositivo y publica en el mismo handle la ruta y Graphics Output Protocol. [Prueba física anterior](evidence/dxe-dispatch-transfer-20261119.json) · [Descripción de los protocolos](REFERENCES.md#dxe_gop)

## Qué dibuja

DXE comprueba que existe un único GOP, que la ruta identifica al driver esperado y que los métodos QueryMode y Blt pertenecen a sus páginas de código. QueryMode debe devolver un modo PixelBltOnly de 1440 × 2560. En cada una de las dos bandas heredadas, de 32 filas a partir de las filas 640 y 1920, DXE pinta cinco bloques de 288 píxeles. Primero deja negro el bloque central. Tras leer de vuelta los cinco colores de ambas bandas, pinta y relee los dos centros amarillos.

| Señal estable, de extremo a extremo | Qué acredita |
| --- | --- |
| Blanco · naranja · verde · naranja · blanco | El primer driver respondió. Este punto precede al despacho del GOP. |
| **Azul · rojo · amarillo · rojo · azul** | El GOP del segundo driver dibujó las bandas. El firmware llega a su bucle final después de comprobar las dos lecturas del amarillo. |
| Blanco · morado · negro · morado · blanco | La comprobación del GOP, el dibujo o la lectura devolvieron un resultado inesperado. El diagnóstico sustituyó el dibujo parcial. |

El buffer BLT usa cuatro bytes por píxel y el scanout consume tres. Para azul, rojo y amarillo se esperan respectivamente `ff 00 00`, `00 00 ff` y `00 ff ff` en memoria del scanout. La traza QEMU observa las llamadas al método real, lee los bytes en la RAM del invitado y contrasta la superficie completa con el patrón y las guardas. El firmware conserva el modo de pantalla heredado durante toda la prueba. [Driver](../OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopDxe.c) · [Consumidor DXE](../OculusGoPkg/DxeCheckpoint/GopBlt.c) · [Observador](../tests/dxe_gop_trace.py)

## Reproducción offline

Desde Debian o WSL en la raíz del proyecto, `run` denota la carpeta que imprime el build, `boot_original` y `dtb_evt` son las copias locales verificadas y `imagen` es un nombre nuevo bajo `local/`.

```sh
bash scripts/build.sh DEBUG 12 DXE_GOP
python3 tools/android_boot.py --fd "$run/OCULUS_GO_DIRECT.fd" --stock-boot "$boot_original" --dtb "$dtb_evt" --output "$imagen"
DXE_QEMU_JOBS=6 bash scripts/check-sec-dxe.sh "$run" "$imagen"
```

La auditoría vuelve a extraer el FD del contenedor de Android, descomprime el FV y comprueba los PE y las expresiones de dependencia de ambos drivers. En el modelo, cada EL observa las entradas de los dos PE y la instalación de los protocolos. Los controles específicos del GOP cambian el GUID de dependencia, el GUID de archivo cargado, un píxel de lectura o el estado devuelto por el último relleno. Los dos últimos casos deben mostrar el diagnóstico de error.

## Resultado en QEMU

QEMU 10.0.13 (AArch64, TCG) completó 41 casos en EL1 y 41 en EL2. Llegaron al patrón final los seis arranques previstos (ordinario, caché de instrucciones activa al entrar y tabla de configuración reordenada, en ambos EL). Los otros 76 terminaron en sus respectivos puntos de rechazo. En cada caso coincidieron la superficie, las guardas y los accesos permitidos. Una segunda ejecución completa desde el mismo contenedor reprodujo byte por byte los informes estático y QEMU. [Resultados por caso](evidence/dxe-gop-qemu-20261119.json)

La dependencia ausente mantuvo el segundo driver sin cargar, y un GUID de archivo incorrecto detuvo su arranque. Un píxel de lectura alterado y un error devuelto por el último relleno activaron la señal de fallo, incluso cuando ya se había escrito amarillo en la RAM. Así se distingue un dibujo parcial del punto final.

## Imagen y ejecución ordinaria

La imagen Android ocupa 483 328 bytes. Su SHA-256 es `77b6cb3ed321e61c6eedd603a5d98174fd00213b5aff1e6b33ebb60807364253`. El FD reextraído ocupa 4 MiB y su SHA-256 es `22a5ed94dd8a5689053c2868f829109e03a01312f397ce420b5028253bf7ca81`. El FV interior ocupa 299 328 bytes. La auditoría del compilador identificó 17 entradas originales del proyecto. El resto procede del EDK2 fijado o de sus herramientas de generación.

En los arranques ordinarios de EL1 y EL2, QEMU observó DevicePathDxe en `0x8023f000` (65 536 bytes) e InheritedGopDxe en `0x80252000` (28 672 bytes). Su texto abarca `[0x80253000, 0x80257000)`. Son asignaciones observadas del cargador. El firmware valida los rangos que obtiene en cada arranque. El observador registró 12 rellenos y 12 lecturas mediante GOP por ejecución. En la RAM de ambas bandas encontró azul, rojo, amarillo, rojo y azul.

El enlazador GNU avisó de segmentos LOAD RWX en los ELF intermedios del núcleo y del GOP. La comprobación del contenedor y la traza inspeccionan los PE finales y las traducciones del invitado. Las páginas de texto de los dos drivers pasan a sólo lectura y ejecutables antes de entrar a ellas. La arena de datos y el framebuffer se mantienen sin permiso de ejecución.

## Prueba en el visor

El [manifiesto de revisión](evidence/dxe-gop-review-20261119.json) fija el contenedor, el FD, los informes, las fuentes y el cotejo posterior a la prueba anterior. `python tools/run_dxe_gop_once.py` sin opciones valida estos archivos en el PC.

El 20 de noviembre de 2026 el gestor de arranque original del Go aceptó la imagen temporal en el slot A con Secure Boot activo. El operador observó «azul, rojo, amarillo, rojo, azul». En esta imagen sólo el protocolo que publica el segundo driver dibuja esa secuencia. El amarillo central se pinta después de comprobar las diez lecturas de los bloques iniciales. La observación acredita salida física por GOP (M3). El PC exacto, el nivel de excepción y la cobertura por ojo en el visor siguen sin medirse. [Registro físico](evidence/dxe-gop-transfer-20261120.json)

Android volvió a arrancar en la misma unidad y en el slot A. ADB confirmó el arranque completo. El cotejo posterior leyó 136 314 880 bytes y los hashes SHA-256 de `aboot_a`, `aboot_b`, `boot_a` y `boot_b` coincidieron con los previos y con los respaldos originales.
