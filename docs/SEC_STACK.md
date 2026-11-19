# SEC_STACK en el Oculus Go

**Confirmado en el Oculus Go.** SEC escribió y releyó dos patrones en los 256 KiB reservados dentro de la imagen y usó esa región como pila durante las llamadas a C. [Registro del ensayo](evidence/sec-stack-transfer-20261118.json) En SEC_MEM el visor ya ejecutó C, construyó una tabla de entrega PI (PHIT) dentro de la imagen y leyó una palabra de 64 bits en cada una de dos direcciones altas. La propiedad y estabilidad de la RAM alta siguen abiertas. [Resultado físico anterior](evidence/sec-mem-transfer-20261118.json)

## Memoria que toca el ensayo

Los intervalos son físicos y excluyen el extremo superior. El perfil SEC_STACK declara la región en el FDF, fuera del volumen de firmware y dentro de los 4 MiB que descomprime el cargador original. La dirección de carga de la imagen y las dos superficies visibles proceden de los ensayos anteriores. Las divisiones de la imagen las define este perfil. [Mapa de memoria y fuentes](MEMORY_MAP.md)

| Intervalo | Uso durante SEC_STACK |
| --- | --- |
| `[0x80080200, 0x80080240)` | Constructor PI de EDK2 y marcador de fin de la lista HOB, dentro de la cabecera |
| `[0x80081000, 0x8043e000)` | Volumen SEC ejecutado en el sitio de carga |
| `[0x8043e000, 0x8043f000)` | Guarda inferior de 4 KiB. Comienza con la firma de formato `GOSTACK1` |
| `[0x8043f000, 0x8047f000)` | Pila de 256 KiB. El registro de entrada de 96 bytes comienza en `0x8047efa0` |
| `[0x8047f000, 0x80480000)` | Guarda superior de 4 KiB |
| `[0x836a4000, 0x836c5c00)`, `[0x83bea000, 0x83c0bc00)` | Dos franjas de 32 filas en el framebuffer heredado |

La entrada comprueba EL1/EL2, afinidad primaria, MMU y caché de datos desactivadas, dirección de ejecución y el valor de x0. Instala vectores de excepción del perfil. Antes de la primera escritura comprueba las dos guardas y que cada palabra de la futura pila conserve el relleno que se empaquetó. El código sigue utilizando registros durante esa comprobación.

1. Recorre 32 768 palabras de 64 bits. Escribe un patrón distinto para cada dirección, ejecuta una barrera y relee el rango completo.
2. Invierte todos los bits del patrón y repite escritura y lectura en orden descendente. Vuelve a comprobar ambas guardas.
3. Cambia SP, escribe el registro de entrada de PrePi y llama cuatro veces a la misma función C con profundidad de 3 a 0. Cada invocación mantiene 1 KiB de datos propios durante la llamada siguiente. La más profunda construye y valida la PHIT con la biblioteca original de EDK2.
4. Cada invocación relee sus datos al volver. La entrada comprueba SP, la firma del registro y el SP/LR guardado, recupera los argumentos y comprueba las guardas por última vez. Sólo entonces pinta **verde, magenta, blanco, magenta, verde** y se detiene.

El perfil mide el acceso desde SEC con la MMU y la caché de datos apagadas en ese intervalo de tiempo. El rango `[0x94000000, 0x98000000)` del asignador normal queda fuera del ensayo. La continuidad tras activar la MMU, el comportamiento frente a DMA y un asignador para descomprimir DXE requieren mediciones adicionales.

## Verificación en el PC

Se compararon los 4 592 bytes de la sección de código y literales del ELF con el SEC empaquetado, incluida la reubicación del literal de entrada. El análisis recorrió 290 instrucciones alcanzables y verificó las llamadas, retornos, sitios de escritura e instrucciones de sistema. QEMU comprobó los 16 vectores y ejecutó 25 casos. En los dos positivos, uno por nivel de excepción, reprodujo todo el patrón de 256 KiB en cada pasada. La diferencia entre el extremo superior de la pila y SP al entrar al constructor PI fue **4 336 bytes**. Los cinco bloques de color coincidieron byte por byte con las dos franjas esperadas.

Los 23 casos negativos cubren reubicación, x0 incorrecto, caché activa, MMU activa en EL1, contaminación inicial de la pila, fallo de guarda, corrupción de una palabra en cada pasada, corrupción de un marco exterior mientras se ejecutaba una llamada interior, una PHIT alterada y una excepción. Cada caso alcanzó su bucle de rechazo y conservó la pantalla inicial. El modelo vigiló escrituras fuera de los rangos permitidos en sus 2 GiB de RAM y accesos al asignador alto. [Revisión, hashes e identidad de los artefactos](evidence/sec-stack-review-20261118.json)

Desde la raíz del repositorio, en WSL:

```sh
bash scripts/build.sh DEBUG 8 SEC_STACK
elf=Build/OculusGoSecStack/DEBUG_GCC5/AARCH64/OculusGoSecStack.debug
python3 tests/sec_stack_static.py --fd "$FD" --sec-elf "$elf" --report "$STATIC_REPORT"
python3 tests/sec_stack_qemu.py --fd "$FD" --sec-elf "$elf" --report "$MODEL_REPORT"
```

`FD` apunta al fichero `OCULUS_GO_DIRECT.fd` de esa compilación. Las rutas de los dos informes deben ser nuevas. El empaquetador del proyecto combina ese FD con el DTB EVT preservado y valida el hash de la imagen de arranque original. La reproducción requiere las copias privadas. El verificador local del ensayo se ejecuta con `python tools/run_sec_stack_once.py`.

## Regresión del arranque normal

El perfil normal recompilado produjo el mismo FD de referencia, SHA-256
`72f602d2eec7d2bff0117bf8d8370218e47ef22fbd7023ab42b3497af9294e58`.
En QEMU llegó a DXE y consultó el protocolo TrustMeBro tanto en EL1 como en
EL2. El SHA-256 del informe de las seis etapas de validación es
`9924a24077001749bab47b7fa88445ed47c97c64942ae5bd9a473b81e95680cf`.
Las 44 pruebas Python de host pasaron en Windows, incluida la del bloqueo
del archivo de imagen durante su lectura. Los informes del perfil anterior
SEC_MEM (QEMU y análisis estático) también reprodujeron sus hashes originales.

## Sesión física del 18 de noviembre

Android arrancó en el slot A y los 130 MiB de las cuatro particiones de arranque coincidieron con los originales antes del ensayo. El Fastboot original comunicó `Secure boot: true` y aceptó el arranque temporal de la imagen revisada. El propietario observó «verde, morado, blanco, morado, verde». La cobertura por ojo quedó sin especificar. El único intento quedó consumido. [Registro del ensayo](evidence/sec-stack-transfer-20261118.json)

Después del ensayo, el propietario volvió a Android y reconectó USB. ADB verificó el arranque completo en el mismo visor y slot A. Los hashes de las lecturas completas de `aboot_a`, `aboot_b`, `boot_a` y `boot_b` coincidieron con los de antes del arranque temporal y con los originales.

El siguiente paso hacia la Shell es establecer espacio de trabajo para las tablas de páginas y los HOB del arranque normal, y conservar el framebuffer durante el cambio de MMU. Después se podrá comprobar la entrada a DXE, conectar la consola de texto a GOP y cargar la Shell desde el volumen de firmware.
