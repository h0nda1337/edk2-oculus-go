# SEC_MMU en el Oculus Go

**Imagen preparada y probada en QEMU. La observación en el visor está pendiente.** El ensayo mide si SEC puede activar la traducción de direcciones y seguir dibujando en el framebuffer que dejó el cargador. El perfil es terminal. DXE y la Shell corresponden a etapas posteriores.

El punto de partida físico es el ensayo SEC_STACK. En el mismo Go se comprobaron dos escrituras y lecturas completas de los 256 KiB reservados dentro de la imagen, las llamadas C y la recuperación a Android. El orden BGR y las dos franjas proceden de las pruebas anteriores. [Pila comprobada](evidence/sec-stack-transfer-20261118.json) · [Framebuffer medido](evidence/sec-c-transfer-20261118.json)

## Qué observación distingue cada etapa

| Patrón observado de un extremo al otro | Qué llegó a ejecutar SEC |
| --- | --- |
| Logo, pantalla negra o reinicio | El resultado visual por sí solo deja abierta la etapa alcanzada |
| Blanco, negro, blanco, negro, blanco | Dibujó antes de activar la MMU. Puede que la transición fuera demasiado rápida para ver este patrón |
| Azul, amarillo, negro, amarillo, azul | Con la MMU activa, comprobó las traducciones y releyó por completo la señal monocroma. Empezó a repintar |
| **Azul, amarillo, rojo, amarillo, azul** | Llegó a escribir el centro rojo tras verificar en memoria los 276 480 bytes del segundo patrón, con la traducción activa |

Los dos patrones en color difieren únicamente en el centro. Primero se pintan ambas franjas con centro negro, después se releen, y sólo entonces se dibuja el centro rojo. La prueba del visor debe registrar el orden observado y, si se distingue, la cobertura por ojo. El panel y el compositor óptico no se modelan en QEMU. La presencia del patrón final en un ojo confirma el camino de ejecución hasta los píxeles observados.

## Mapa y cambio de MMU

El cargador descomprime un FD de 4 MiB. SEC acepta el núcleo primario en EL1 o EL2, con PC y x0 en las ubicaciones revisadas, datos little-endian, y traducción y caché de datos inicialmente desactivadas. Comprueba la firma del espacio reservado y el relleno inicial de la pila y las tablas antes de usarlos. Las escrituras de la CPU se limitan a estos intervalos ya medidos en el Go. Los extremos superiores son exclusivos.

| Uso | Intervalo físico | Tratamiento al activar la MMU |
| --- | --- | --- |
| Código SEC, literales y vectores | `[0x80081000, 0x80085000)` | Cuatro páginas de sólo lectura, ejecutables en el nivel privilegiado |
| Siete tablas de 4 KiB | `[0x8043f000, 0x80446000)` | Dentro de la reserva comprobada por SEC_STACK. El hardware lee sus descriptores físicamente. Sus direcciones virtuales quedan sin mapear |
| Pila | `[0x8047e000, 0x8047f000)` | Una página de lectura/escritura, sin permiso de ejecución. Hay páginas sin mapear a ambos lados |
| Primera franja de 32 filas | `[0x836a4000, 0x836c5c00)` | 34 páginas, identidad, memoria normal no cacheable |
| Segunda franja de 32 filas | `[0x83bea000, 0x83c0bc00)` | Otras 34 páginas. Cruza un límite de 2 MiB y usa dos tablas de último nivel |

La granularidad de 4 KiB deja 1 KiB adicional mapeado al final de cada franja. El pintor recorre exactamente los 138 240 bytes de cada una. La lista completa de 3 584 descriptores se relee antes de instalarla. El perfil usa tablas de etapa 1, VA de 39 bits y salida de 32 bits para este conjunto de direcciones. Programa MAIR, TCR y TTBR0 del nivel actual, invalida la TLB local y activa el bit M de SCTLR con barreras. Conserva la configuración de la caché de instrucciones y mantiene la caché de datos desactivada. En EL2 comprueba el régimen sin VHE. El mapa de identidad deja fuera el asignador alto y los registros del controlador de pantalla. [Fuentes y constantes](REFERENCES.md) · [Mapa físico](MEMORY_MAP.md)

Tras el cambio comprueba SCTLR, pide a la CPU la traducción de escritura de las 68 páginas de las franjas y la de pila, y exige que cada PA y su atributo no cacheable coincidan con el diseño. Comprueba además que falle la traducción de la guarda superior. Hace una escritura y lectura testigo en la pila traducida. Un fallo lleva a un bucle terminal y se conserva la última señal que alcanzó a pintar.

## Verificación reproducible

Se cotejaron los 4 848 bytes de código y literales enlazados con el FD final y se recorrieron 342 instrucciones alcanzables, incluidas las dos secuencias de activación. QEMU ejecutó **29 casos**. Cuatro alcanzaron el patrón final, en EL1 y EL2 y con la caché de instrucciones inicialmente apagada o encendida. Los otros 25 comprobaron rechazos de entrada, datos iniciales alterados, ausencia de la última página de la segunda franja, salida física errónea, atributo de memoria incorrecto, guarda mapeada, excepción de instrucción o corrupción de un patrón antes de su relectura. Se cotejaron todos los descriptores, la superficie completa con sus guardas y el resto del FD. [Hashes y resultados](evidence/sec-mmu-review-20261118.json)

En Linux o WSL, desde la raíz del repositorio:

```sh
bash scripts/build.sh DEBUG 8 SEC_MMU
elf=Build/OculusGoSecMmu/DEBUG_GCC5/AARCH64/OculusGoSecMmu.debug
python3 tests/sec_mmu_static.py --fd "$FD" --sec-elf "$elf" --report "$STATIC_REPORT"
python3 tests/sec_mmu_qemu.py --fd "$FD" --sec-elf "$elf" --report "$MODEL_REPORT"
```

`FD` es el `OCULUS_GO_DIRECT.fd` del directorio de resultados que imprime el build. Ambas rutas de informe deben ser nuevas. El empaquetador del proyecto utiliza el DTB EVT local. La imagen de arranque pesa **376 832 bytes** y su SHA-256 es `86dd2aaea11086407ff8175c4e7a69ad842b61f925a73c725290f20f2b465fb8`. El código y los hashes se publican en el repositorio privado; los artefactos derivados del visor se conservan localmente.

La compilación normal reprodujo su FD de referencia, SHA-256 `72f602d2eec7d2bff0117bf8d8370218e47ef22fbd7023ab42b3497af9294e58`. Las seis comprobaciones de regresión pasaron, incluida la llegada a DXE y la consulta de TrustMeBro en QEMU en EL1 y EL2. El SHA-256 del informe local es `8d9d1d04ee9d3a4f7125408a96f0cdfd8d36792207562f2f312ed6b88695abc9`. Las 47 pruebas Python de host pasaron en Windows.

## Prueba física pendiente

El punto de partida es Android arrancado, el operador presente y USB conectado. La verificación local se ejecuta con `python tools/run_sec_mmu_once.py`. El ejecutor revisa la imagen y la evidencia, y en una sesión física comprueba el mismo visor, un cotejo reciente de las cuatro particiones y las banderas del Fastboot original. Reserva un solo intento antes de enviar el arranque temporal a RAM. Tras la observación se vuelve a Android por la ruta comprobada y se cotejan de nuevo los cuatro hashes. [Recuperación](RECOVERY.md)

Si se observa el centro rojo, la siguiente cuestión para DXE será proporcionar memoria acotada para los HOB y descomprimir el volumen de firmware. Este ensayo deja abierta la disponibilidad del asignador alto y el funcionamiento de GOP en el visor.
