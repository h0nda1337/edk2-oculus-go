# SEC_DXE — entrada en DXE Core

Esta imagen de diagnóstico comprueba si el cargador original entrega suficiente RAM dentro del FD para construir el handoff PI, descomprimir un volumen con LZMA y ejecutar el DXE Core de EDK2. El 19 de noviembre el propietario observó «blanco, verde, morado, verde, blanco» en el Oculus Go. El patrón confirma la entrada física en DxeMain, la validación de los HOB y la escritura del framebuffer desde el DXE Core relocalizado. El nivel de excepción físico y la cobertura por ojo siguen sin determinar. [Registro del visor](evidence/sec-dxe-transfer-20261119.json)

## Resultado en el PC

Pasaron 18 casos en QEMU. En cuatro arranques válidos, con caché de instrucciones inicialmente activa o inactiva en EL1 y EL2, la entrada PE fue `0x802dd000`, DxeMain fue `0x802dd39c` y el PC terminal fue `0x802fb4d8`. El FV interior en `0x8030c000` coincidió en sus 196736 bytes con la salida de la compilación. Quedaron 899984 bytes libres en la arena, entre los HOB y las asignaciones de páginas. Estas direcciones de ejecución son observaciones del modelo.

Los catorce controles de rechazo cubren en cada EL el argumento x0 incorrecto, carga desplazada, caché de datos inicialmente activa, arena ocupada, guarda ocupada, checksum inválido del FV descomprimido y GUID del HOB del módulo alterado. La prueba cotejó los 32768 bytes de las ocho tablas en los casos que llegaron al salto y vigiló escrituras en la RAM invitada fuera de las regiones autorizadas. Al alterar el checksum quedó la banda azul. Al alterar el HOB del módulo quedó la banda cian.

| Artefacto revisado | Tamaño | SHA-256 |
| --- | ---: | --- |
| Imagen Android temporal | 462848 bytes | `1f4a7ebd46d9f3d2079d771b3b442c64d2a33fa001fc765814cd852ce7bcbe4a` |
| FD extraído del contenedor | 4194304 bytes | `565c5a57dfca2d69e68ce8967e7d5908a9081c2af36f502fe3105a2e175a5bdb` |
| Volumen interior descomprimido | 196736 bytes | `96891657648605572be141f409bb012a14f55810a387bc329d8984f0c04f8117` |

[Resultados por escenario](evidence/sec-dxe-qemu-20261118.json) · [Revisión de la imagen y las fuentes](evidence/sec-dxe-review-20261118.json)

## Qué hace el firmware

SEC comprueba la dirección de entrada, el registro x0, el nivel de excepción, el estado inicial de traducción y caché de datos, la firma del FD y la zona de pila. Comprueba también que la arena y sus dos páginas de guarda contienen el relleno de la imagen. El PHIT y los HOB crecen desde el extremo inferior de la arena. El asignador de páginas de PrePi reserva espacio desde arriba para el descompresor, el volumen descomprimido y la imagen ejecutable. El único descriptor de RAM de uso general que publica este perfil cubre la arena. La pila se describe por separado.

El contenedor exterior contiene el SEC del proyecto y un archivo FV_IMAGE con una sección guiada LZMA. El volumen interior contiene un solo DXE Core. SEC valida los límites del volumen, su checksum de cabecera, el tipo y GUID del archivo y las secciones del PE AArch64. El cargador PE/COFF de EDK2 lo relocaliza y se publica un HOB de módulo con la entrada real. La carga se completa antes de activar la MMU. Una vez activada, las páginas de código del PE son de sólo lectura y ejecutables. Los datos del PE, los HOB y la pila se mapean para lectura y escritura con ejecución impedida.

SEC llama a la entrada del PE pasando el PHIT en x0. El punto de observación dentro de DXE es la llamada de DxeMain a InitializeDebugAgent, después de inicializar los manejadores de excepciones. La implementación de diagnóstico comprueba el PHIT, el terminador, un HOB de volumen interior y el HOB que contiene tanto su propio PC como la entrada del módulo. En ese punto dibuja y se detiene. Boot Services, despacho de drivers, GOP y Shell quedan para pruebas posteriores.

## Memoria del perfil

| Uso | Inicio inclusivo | Fin exclusivo |
| --- | --- | --- |
| FD que entrega el cargador | 0x80080000 | 0x80480000 |
| Volumen exterior | 0x80081000 | 0x80100000 |
| Guarda inferior de la arena | 0x801ff000 | 0x80200000 |
| Arena para HOB, descompresión y PE | 0x80200000 | 0x80380000 |
| Guarda superior de la arena | 0x80380000 | 0x80381000 |
| Ocho tablas de traducción de 4 KiB | 0x8043f000 | 0x80447000 |
| Pila de 64 KiB, incluida en la prueba SEC_STACK | 0x8046f000 | 0x8047f000 |

Estas reservas pertenecen al diseño de este FD. La propiedad de la zona alta de 64 MiB del perfil normal sigue pendiente en hardware. El perfil SEC_DXE dibuja directamente en las dos bandas BGR heredadas que ya se observaron en SEC_MMU. La primera comienza en 0x836a4000 y la segunda en 0x83bea000. Cada banda ocupa 32 filas de 4320 bytes.

## Cómo leer las bandas

| Cinco bloques de un extremo al otro | Última operación demostrada |
| --- | --- |
| Blanco · azul · negro · azul · blanco | SEC construyó los HOB iniciales |
| Blanco · amarillo · negro · amarillo · blanco | SEC descomprimió y validó el volumen, el archivo y el PE |
| Blanco · cian · negro · cian · blanco | SEC cargó el PE, publicó el módulo y comprobó traducciones antes del salto |
| **Blanco · verde · magenta · verde · blanco** | **Código dentro de DXE Core validó el handoff y dibujó desde la imagen relocalizada** |

Las señales intermedias pueden sucederse demasiado rápido para distinguirlas. Registrar el patrón que permanece y, si difiere entre ojos, describir cada uno. Un logo fijo, una pantalla negra o una banda parcial se registran tal como se ven. La aceptación por Fastboot mide el transporte.

El perfil NORMAL recompilado conserva el FD anterior con SHA-256 `72f602d2eec7d2bff0117bf8d8370218e47ef22fbd7023ab42b3497af9294e58`. En su prueba de regresión llegó a consultar el protocolo TrustMeBro en EL1 y EL2. El perfil SEC_MMU recompilado también reprodujo su FD físico original byte por byte y pasó su auditoría estática de 342 instrucciones y sus 29 casos de QEMU. También pasaron las 22 pruebas sintéticas existentes del transporte.

## Alineación observada en QEMU

En el primer FD, `34b271a9d17535b3c574ace395ca0e79d75df3c5115ae0844c5ce2730fdce292`, el PE empezaba a 100 bytes del inicio del FV. Al leer la firma PE y el campo Machine, QEMU EL1 entró en el vector de excepción con `ELR_EL1=0x80082cf8`, `FAR_EL1=0x8030cebc` y `ESR_EL1=0x96000021`. El opcode era una carga de 64 bits en una dirección alineada sólo a 4 bytes, antes de activar traducción. El perfil final exige 8 bytes de alineación tanto para el PE como para su cabecera NT. La prueba estática verifica ambos desplazamientos dentro del volumen descomprimido.

## Reproducción en el PC

Desde el proyecto, en Debian/WSL, compilar con `bash scripts/build.sh DEBUG 12 SEC_DXE`. Empaquetar el FD con `tools/android_boot.py` y los archivos locales originales según su ayuda. Ejecutar `bash scripts/check-sec-dxe.sh build/DEBUG-SEC_DXE-<fecha> local/OculusGo-SEC-DXE-<prefijo>.img`. El script vuelve a extraer el FD del contenedor, lo compara byte a byte, verifica el FV interior y el PE y ejecuta el binario en QEMU. Los ELF auxiliares sólo aportan símbolos al observador.

Con GCC 14, el compilador avisa que `Prot` puede estar sin inicializar en `CoreOpenProtocol` del EDK2 fijado. El ajuste de compilación conserva ese aviso en el DXE Core de diagnóstico. El punto terminal precede al uso de servicios de protocolo. El enlazador también puede marcar un segmento del ELF auxiliar como RWX. Las comprobaciones del candidato inspeccionan las secciones del PE entregado y todos los descriptores de traducción activos después de habilitar la MMU.

La revisión vincula por SHA-256 los artefactos, informes y fuentes. La comprobación predeterminada en Windows es `python tools/run_sec_dxe_once.py`. El único intento temporal de esta revisión se consumió el 19 de noviembre con el visor a mano, tras identificar la misma unidad y cotejar las cuatro particiones de control. Tras observar el visor se sale mediante el procedimiento físico ya comprobado y se cotejan de nuevo los cuatro hashes. Véanse [recuperación](RECOVERY.md) y [registro físico de SEC_MMU](evidence/sec-mmu-transfer-20261118.json).

Tras la observación, el propietario volvió a Android con «Boot device» y reconectó USB. ADB verificó el arranque completo del mismo visor en el slot A. Las lecturas posteriores de `aboot_a`, `aboot_b`, `boot_a` y `boot_b` (130 MiB en total) coincidieron con las lecturas previas y con los respaldos originales. [Registro de recuperación y hashes](evidence/sec-dxe-transfer-20261119.json)
