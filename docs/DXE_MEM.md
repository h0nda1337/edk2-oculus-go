# DXE_MEM — servicios de memoria en DXE Core

Prueba temporal para Oculus Go. SEC_DXE ya demostró la entrada física en DxeMain y la salida al framebuffer. DXE_MEM continúa por el inicializador de memoria de EDK2 y se detiene antes de inicializar los servicios de imagen. La ejecución de DXE_MEM en el visor está pendiente. [Prueba física anterior](evidence/sec-dxe-transfer-20261119.json)

## Resultado en QEMU

Pasaron 28 casos de la imagen empaquetada. Cuatro arranques alcanzaron el centro verde en EL1 y EL2 con la caché de instrucciones inicialmente encendida o apagada. Los otros 24 casos alcanzaron el punto de rechazo previsto. Entre los controles específicos, alterar una palabra de la arena impidió construir los HOB. Retirar el atributo TESTED impidió volver del callback de DXE. Alterar el último byte de las páginas o del pool, o modificar el descriptor devuelto por GetMemoryMap, conservó la señal naranja con centro negro.

| Observación en los cuatro arranques válidos | Valor del modelo |
| --- | --- |
| Intervalo inicial del asignador, fin exclusivo | `[0x80201000, 0x802dc000)`, 219 páginas de 4 KiB |
| Dos páginas de EfiLoaderData | `0x802d9000` |
| Pool de 257 bytes | `0x802d8018` |
| Clave del mapa con las asignaciones vivas y después de las liberaciones | 5 → 7 |
| Descriptores devueltos en cada mapa | 6 → 4 |
| FD extraído (4 MiB) | SHA-256 `e0b4305f90107396030f2aadf5e4b8041cb8bb8602f4cea4588fb728d97dd712` |
| Imagen Android temporal (462848 bytes) | SHA-256 `162d9f05bb70a3672ac808aa10bf88a7d6d884f46b0a2f6609da2cb8f429034c` |

El observador cotejó el FV interior, la sección ejecutable relocalizada, los descriptores de traducción y la lista de HOB en los caminos sin alteración deliberada del handoff. Las direcciones y las claves son mediciones del modelo. [Resultados por caso](evidence/dxe-mem-qemu-20261119.json) · [Revisión del candidato](evidence/dxe-mem-review-20261119.json)

## Qué se comprueba

1. SEC reconoce la misma arena dentro de la imagen, desde `0x80200000` hasta `0x80380000` (fin exclusivo). Con la caché de datos y la traducción apagadas, escribe una palabra de 64 bits dependiente de cada dirección, la relee, repite con el patrón complementario y restaura el relleno. Verifica también las dos páginas de guarda. Sólo entonces publica el atributo PI `EFI_RESOURCE_ATTRIBUTE_TESTED` para esa región.
2. El callback de depuración de DXE verifica la lista HOB y la presencia de un único descriptor de RAM probada. Comprueba que el intervalo libre del PHIT, redondeado hacia dentro a páginas, esté separado de todas las asignaciones HOB. Regresa a la ruta original de DxeMain.
3. DxeMain llama al `CoreInitializeMemoryServices` original y crea las tablas System y Runtime con dos asignaciones de pool. Exclusivamente en esta imagen de diagnóstico, el enlace redirige la siguiente llamada, `CoreInitializeImageServices`, a un punto terminal del proyecto. El punto elegido permite usar la tabla Boot Services ya instalada en la System Table. Esta prueba termina antes de GCD, del despacho de drivers y de la consola.
4. El código solicita dos páginas contiguas de `EfiLoaderData` y 257 bytes de `EfiBootServicesData`. Comprueba límites y ausencia de solapamiento, escribe y relee 8 449 bytes y llama a `GetMemoryMap`. Valida el paso y versión de los descriptores, la cobertura del intervalo libre y el tipo de las páginas. Libera el pool y las páginas, obtiene un segundo mapa y exige que las páginas vuelvan a `EfiConventionalMemory` y que cambie la clave del mapa. **Es un mapa temprano del asignador**, limitado a la RAM que se le entregó antes de GCD.

## Señales en el visor

| Patrón sostenido | Último punto demostrado |
| --- | --- |
| Blanco · azul · negro · azul · blanco | SEC publicó los HOB, después de probar la arena |
| Blanco · amarillo · negro · amarillo · blanco | Volumen y ejecutable validados |
| Blanco · cian · negro · cian · blanco | SEC preparó la transferencia a DXE Core |
| Blanco · verde · magenta · verde · blanco | El callback comprobó el handoff de DXE |
| Blanco · naranja · negro · naranja · blanco | DxeMain regresó del inicializador y llegó al punto posterior a las dos asignaciones de las tablas |
| **Blanco · azul · verde · azul · blanco** | **Las asignaciones, escrituras, lecturas, dos mapas y liberaciones pasaron** |

Las bandas se escriben en el framebuffer BGR heredado. La secuencia final se observa en reposo. Si sólo aparece una marca anterior, documentar su color y el centro sin atribuir el fallo a una instrucción concreta.

## Controles de la compilación

La auditoría de fuentes pasó con el árbol EDK2 fijado e íntegro. El FD extraído del contenedor y la imagen Android reempaquetada coincidieron byte por byte. Dos ejecuciones de la auditoría estática y del modelo produjeron informes idénticos. Las 53 pruebas Python de host pasaron en Windows. La recompilación de SEC_DXE reprodujo el FD que arrancó en el visor, SHA-256 `565c5a57dfca2d69e68ce8967e7d5908a9081c2af36f502fe3105a2e175a5bdb`, y volvió a pasar sus 18 casos de QEMU.

GCC 14 conserva la advertencia de `Prot` en `CoreOpenProtocol` de la revisión upstream. Ese servicio queda fuera del recorrido medido. El enlazador también avisa de segmentos RWX en los ELF auxiliares. La verificación inspecciona el PE entregado y compara los 32768 bytes de las tablas de traducción en el camino a DXE. Los permisos observados después de activar la MMU son RX para el texto del núcleo y RW con ejecución impedida para el intervalo del asignador.

## Reproducción en el PC

Desde el repositorio activo en Debian/WSL:

```sh
bash scripts/build.sh DEBUG 12 DXE_MEM
python3 tools/android_boot.py --fd "$run/OCULUS_GO_DIRECT.fd" --stock-boot "$boot_original" --dtb "$dtb_evt" --output "$img"
bash scripts/check-sec-dxe.sh "$run" "$img"
```

`run` es el directorio `build/DEBUG-DXE_MEM-…` generado por la compilación. La variable `img` es un archivo nuevo bajo `local/`. El empaquetador comprueba el boot y el DTB locales por SHA-256. Se extrae el FD exacto del contenedor y se comparten las comprobaciones de FV, PE, MMU y framebuffer con SEC_DXE. QEMU observa también las llamadas de Boot Services, valores de retorno, todo el contenido de los buffers y los descriptores devueltos. Se comparan todos los bytes de la superficie y las guardas, y se vigilan las escrituras en el resto de la RAM. En Windows, `python tools/run_dxe_mem_once.py` valida la revisión y el estado del intento sin contactar con el visor.
