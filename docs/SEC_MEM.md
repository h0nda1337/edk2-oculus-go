# SEC_MEM — primer bloque de entrega de memoria

En la prueba anterior, el visor mostró que una función C podía usar una pila
dentro de la imagen. El inicio normal de EDK2 necesita además una lista de
bloques de información (HOB) que DXE pueda recibir. Prevé colocar esa lista
en `0x94000000` y guardar su primer registro de pila en `0x97ffffa0`.
La disponibilidad de toda esa memoria en el momento de la entrega sigue
siendo una incógnita. [Mapa y evidencias de la unidad](MEMORY_MAP.md)

## Qué mide la imagen

1. SEC exige núcleo primario, EL1 o EL2, MMU y caché de datos desactivadas,
   la dirección enlazada de la entrada y el puntero al árbol del dispositivo
   en `0x82000000`. Instala vectores de excepción propios. La pila reservada
   para la prueba está en la primera página de la imagen.
2. Lee el DTB entregado por el bootloader. El lector acepta el formato v17
   observado, con un máximo de 512 KiB, las celdas de dirección y tamaño de
   la unidad y su intervalo de RAM. Comprueba las reservas fijas sobre ambas
   palabras y exige que el árbol describa el banco de RAM observado en el Go.
   Las reservas dinámicas y la actividad de DMA en ese instante siguen sin
   determinarse. [Capturas y asignaciones observadas en Android](MEMORY_MAP.md)
3. Usa el verdadero `HobConstructor` de EDK2. Construye la tabla inicial
   (PHIT) y el marcador de fin en 64 bytes de la imagen. Después comprueba
   sus tipos, longitudes, versión, modo de arranque, límites de memoria y
   puntero de fin antes de regresar al ensamblador. El constructor es el que
   utiliza la plataforma normal. [Implementación upstream fijada](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/EmbeddedPkg/Library/PrePiHobLib/Hob.c)
4. Lee una palabra de 64 bits en cada dirección prevista para HOB y pila.
   Descarta ambos valores. Si las dos lecturas terminan, dibuja cinco bloques
   **cian, amarillo, blanco, amarillo, cian** en las bandas que ya produjeron
   salida visible y se detiene en SEC.

| Acceso | Intervalo físico, extremo superior excluido |
| --- | --- |
| Lectura del árbol | Desde `0x82000000`, limitada por cabecera y máximo de 512 KiB |
| Escritura de la PHIT y su terminador | `[0x80080200, 0x80080240)` |
| Reserva para la pila de prueba | `[0x80080800, 0x80081000)` |
| Lectura de la primera palabra del futuro espacio para HOB | `[0x94000000, 0x94000008)` |
| Lectura de la primera palabra del futuro registro de pila | `[0x97ffffa0, 0x97ffffa8)` |
| Escritura de píxeles BGR | `[0x836a4000, 0x836c5c00)` y `[0x83bea000, 0x83c0bc00)` |

Ver el patrón completo acreditaría que el DTB entregado pasó los controles
descritos, que SEC construyó y verificó la PHIT y que las dos lecturas
terminaron en ese arranque. Un bus puede devolver un valor por defecto.
La prueba no compara los valores leídos con un contenido físico conocido.
Si el bootloader entrega el control en EL1, SEC comprueba la traducción de
etapa 1 del EL activo. La posible traducción de etapa 2 controlada desde EL2
permanece fuera de su observación. Las lecturas describen las direcciones
que ve el procesador en ese momento.
La escritura en RAM alta, la disponibilidad de los 64 MiB, la MMU y la entrada
a DXE requerirán pruebas posteriores. Un logo fijo o una pantalla negra dejan
el último punto alcanzado indeterminado.

## Repetir en el PC

```powershell
.\scripts\build-edk2.ps1 -Target DEBUG -Mode SEC_MEM -Jobs 8
```

El empaquetador existente `tools/android_boot.py` exige el DTB EVT y
`boot_a` originales por su SHA-256. Los artefactos derivados quedan en
`local/`. El arnés QEMU acepta el FD extraído del contenedor, el ELF de SEC
de esa compilación y, mediante `--runtime-fdt`, el árbol conservado en la
sesión de Android. La observación en QEMU se hace con RAM sintética.

La imagen Android preparada ocupa 376832 bytes. El FD de 4 MiB extraído de
ella coincide byte por byte con la compilación. Una segunda codificación
reprodujo el contenedor completo, incluido el DTB EVT original. Para esta
imagen, el cálculo de staging conservado de LK da
`[0x91e00000, 0x91e5c000)` para la descarga y
`[0x91e5d000, 0x9225d000)` para la salida gzip. Son intervalos calculados
a partir del tamaño, aún sin observación directa en esta prueba.

| Artefacto local | SHA-256 |
| --- | --- |
| Imagen Android `local/OculusGo-SEC-MEM-c15da640f829.img` | `cdcc745e718ed53cb6542f20e4a438d445dc5a1b853ea878a2ce7ef39c848138` |
| FD `OCULUS_GO_DIRECT.fd` | `c15da640f8292d226924d06f63d5a1cd7f15d41215ce02b4ab0123675f505091` |

El FD incluye únicamente el módulo SEC de este experimento. La compilación
enlazó el constructor PI de EDK2 sin modificaciones. La auditoría de entradas
identificó 3 archivos propios, 127 de EDK2 y 27 generados. El volumen de
firmware de esta prueba termina antes de cargar un núcleo DXE.

El FD extraído pasó 23 casos QEMU: 12 en EL1 y 11 en EL2. En cuatro casos
positivos, con árboles sintéticos y con la captura real, el depurador
observó ambas lecturas, sus direcciones y sus resultados en RAM sintética.
Se compararon todos los bytes de los 64 MiB antes y después. En los otros
19 casos el programa se detuvo antes de alcanzar las lecturas altas. Se
probaron reservas sobre las palabras, un puntero de árbol incorrecto, un
PHIT alterado, estados de entrada incompatibles y una excepción en cada EL.
El análisis ELF/FD cotejó 632 instrucciones alcanzables incluidos los
16 vectores. El uso máximo de pila calculado fue de 176 bytes. Los informes
de QEMU y del análisis estático se reprodujeron byte por byte en una segunda
ejecución. [Revisión de la imagen y hashes de los resultados](evidence/sec-mem-review-20261118.json)

También se recompiló el perfil normal. Sus 4 MiB coincidieron byte por byte
con la referencia anterior, SHA-256
`72f602d2eec7d2bff0117bf8d8370218e47ef22fbd7023ab42b3497af9294e58`.
Pasaron las pruebas de entrada, SEC y DXE en QEMU, junto con la auditoría
de fuentes y las pruebas de host. El SHA-256 del informe local de regresión
es `87b6843c462bf13f0bd27bf55db314b5e70d5b319c75a954c7d7b20999134f70`.

Con el FD extraído y el ELF de esa misma compilación, las pruebas se pueden
repetir desde la raíz del proyecto en Linux o WSL:

```sh
python3 tests/sec_mem_fdt_host.py --runtime "$RUNTIME_DTB" --stock "$EVT_DTB"
python3 tests/sec_mem_static.py --fd "$EXTRACTED_FD" --sec-elf "$SEC_ELF"
python3 tests/sec_mem_qemu.py --fd "$EXTRACTED_FD" --sec-elf "$SEC_ELF" --runtime-fdt "$RUNTIME_DTB"
```

## Sesión física del 18 de noviembre

El Fastboot original aceptó el envío y el arranque temporal después de
verificar los cuatro hashes desde Android. El intento quedó consumido.
[Registro del ensayo](evidence/sec-mem-transfer-20261118.json)

Con el propietario presente, comprobar primero por ADB el mismo equipo, Android
arrancado en el slot A y los cuatro hashes completos de `boot_a/b` y
`aboot_a/b`. En el Fastboot original se verifican el producto y los estados
de bloqueo antes de un único `fastboot boot` a RAM. Esta prueba termina
intencionadamente en un bucle. El visor puede conservar el logo o perder USB
hasta el apagado manual. Tras unos 15 segundos se registra lo que se ve.

El ejecutor `python tools/run_sec_mem_once.py` valida por defecto sólo los
archivos del PC. En una futura sesión con el visor, el modo `--execute`
requiere además `--operator-present`, el ejecutable de Fastboot revisado, el
número de serie local y un informe de integridad de Android de menos de
una hora. Reserva el único intento antes de emitir este comando equivalente:

```powershell
fastboot -s <serie-local-verificada> boot local/OculusGo-SEC-MEM-c15da640f829.img
```

Para recuperar, desconectar USB y mantener sólo Power. Soltar al apagarse o
al llegar a 20 segundos. Desde apagado, Power y volumen menos llevan a
**USB Update Mode**. Elegir únicamente **Boot device**, volver a Android,
reconectar USB y cotejar los cuatro hashes. Si falla el apagado o el menú,
detener la prueba y registrar el estado. [Recuperación anterior comprobada](evidence/sec-c-transfer-20261118.json)
