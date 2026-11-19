# Prueba de la pila y el patrón de color desde C en SEC

El primer ensayo llegó a SEC y mostró morado, verde, negro y blanco en el
visor. Los cuatro colores se conservan si se intercambian los canales rojo
y azul. El candidato `SEC_C` permite comprobar si SEC usa una pila privada,
entra en una función C y dibuja desde ella. El patrón también indica qué
color produce cada byte extremo de un píxel en el visor.

## Código ejecutado

Tras comprobar el nivel de excepción, la afinidad del procesador, el estado
de la MMU/caché de datos y la dirección de entrada, SEC enmascara las
interrupciones. Reserva su pila en la mitad superior de la página que
contiene la cabecera ARM64 del propio FD, `[0x80080800, 0x80081000)`.
El volumen de firmware empieza en el extremo superior y la pila crece hacia
abajo. La prueba en emulación comprueba que ese intervalo está libre en la
imagen original y que el contenido del resto del FD se conserva.

El ensamblador guarda los argumentos entrantes, SP y LR. La función C escribe
y vuelve a leer un testigo local de 32 bits antes de dibujar. Usa los dos
mismos intervalos de RAM del framebuffer que utilizó la prueba anterior. Al
regresar a ensamblador, se restauran los registros y se entra en un bucle
terminal. Este recorrido termina antes de inicializar la pila normal de la
plataforma, las tablas de traducción, los controladores de DXE o el GOP.

## Cómo interpretar la pantalla

Cada banda tiene dos grupos. El primero dibuja una marca blanca rodeada por
el color que produce el primer byte de cada píxel. El segundo dibuja una
marca negra rodeada por el color que produce el tercer byte. Se usan vecinos
de color para poder leer el resultado incluso con la imagen girada.

| Observación física | Interpretación |
| --- | --- |
| Rojo a ambos lados de la marca blanca y azul a ambos lados de la negra | Orden compatible con R, G, B |
| Azul a ambos lados de la marca blanca y rojo a ambos lados de la negra | Orden compatible con B, G, R |
| Marcas o colores ambiguos, pantalla negra o logo fijo | Registrar lo observado y mantener el orden como desconocido |

El propietario observó «en orden de arriba hacia abajo: rojo, negro, rojo, azul, blanco, azul».
Las dos marcas identifican el primer
byte como azul y el tercero como rojo en el framebuffer heredado. El patrón
confirma que la función C dibujó después de comprobar el testigo de pila.
La dirección de barrido del panel sigue sin determinarse. El retorno desde
C se verificó en QEMU. [Registro físico](evidence/sec-c-transfer-20261118.json)

## Pruebas offline

```powershell
.\scripts\build-edk2.ps1 -Target DEBUG -Mode SEC_C -Jobs 8
```

Desde Linux o WSL, con el FD que acaba de compilarse y sus símbolos SEC:

```sh
python3 tests/sec_c_qemu.py --fd build/DEBUG-SEC_C-<fecha>/OCULUS_GO_DIRECT.fd \
  --sec-elf Build/OculusGoSecC/DEBUG_GCC5/AARCH64/OculusGoPkg/PrePi/PrePi/DEBUG/OculusGoSec.dll
```

Se ejecutan entradas válidas y dos rechazos (caché de datos activa y
reubicación) en EL1 y EL2. La prueba compara los bytes de toda la superficie,
sus márgenes y todo el FD. Comprueba la dirección de retorno a ensamblador,
el resultado de C, el testigo en la pila, los argumentos y SP/LR. Los
intervalos observados en QEMU describen ese modelo. El informe de la primera
prueba física y sus hashes de recuperación se conservan por separado.
[Primer ensayo](evidence/sec-visual-transfer-20261118.json)

El FD de 4 MiB tiene SHA-256
`3ee7a88df0d44ae7b68dc0ded6774b23a41e9e3f4ce0cffaef38b640ebc8e6f6`.
Se extrajo de la imagen Android empaquetada antes de ejecutar las seis pruebas
en QEMU. Un análisis independiente cotejó 93 instrucciones del ELF con el FD
y verificó una sola llamada a C en el recorrido normal. Las escrituras de pila
abarcan 52 bytes en `[0x80080fcc, 0x80081000)`. Las dos bandas ocupan
`[0x836a4000, 0x836c5c00)` y `[0x83bea000, 0x83c0bc00)`. El inventario de
fuentes aceptó 5 archivos propios, 434 de EDK2 y 144 generados.
[Revisión y hashes de los informes](evidence/sec-c-review-20261118.json)

## Ensayo físico del 18 de noviembre

La imagen local `local/OculusGo-SEC-C-20261118.img` ocupa 487424 bytes. Su
SHA-256 es `3cd2cbfd824ca726029e8810abbfb12a90f5b1653155c972a109a68ccc5d5055`.
La comprobación por defecto lee sólo archivos del PC:

```powershell
python tools/run_sec_c_once.py
```

Antes del envío, el ejecutor comprobó los hashes de las cuatro particiones
en el informe de Android y verificó el visor, el slot `_a` y los dos
indicadores de Secure Boot en Fastboot. El único intento se consumió al
reservar el envío temporal a RAM. El comando registrado equivale a:

```powershell
fastboot -s <serie-local-verificada> boot local/OculusGo-SEC-C-20261118.img
```

El diagnóstico tiene un bucle terminal después del retorno desde C.
Para recuperar desde ese estado se desconecta USB y se mantiene sólo Power.
Soltar al apagarse o al llegar a 20 segundos. Si se apaga, usar Power y
volumen menos hasta el menú original y elegir únicamente **Boot device**.
Si falla el apagado o el menú, detener la prueba y registrar lo ocurrido.
El propietario confirmó el regreso a Android. ADB verificó el arranque
completo en el mismo visor y slot A. Se volvieron a leer los 130 MiB de
`aboot_a`, `aboot_b`, `boot_a` y `boot_b`. Los cuatro SHA-256 coinciden con
los de antes del ensayo y con las copias originales.
[Hashes y observación del propietario](evidence/sec-c-transfer-20261118.json)
