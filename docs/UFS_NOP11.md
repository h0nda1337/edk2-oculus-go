# Primer NOP en las colas UFS de LK

`UFS_NOP11` prepara un intercambio NOP OUT / NOP IN durante un arranque temporal en Pacific. El controlador UFS puede responder antes de seleccionar un LUN o leer bloques. Esto permite evaluar el transporte por separado de la lectura de la GPT y de `splash`. En el Go, la última medición confirmó las bases de las colas y la traducción de la CPU. La ejecución física de este NOP y la dirección DMA de la ventana de 16 KiB siguen **UNKNOWN**. [Lectura física anterior](evidence/ufs-lk-map-transfer-20261121.json)

## Memoria y registro que utiliza la sonda

| Recurso | Dirección | Uso |
| --- | --- | --- |
| Slot 1 de UTR | `0x918EE420` | 32 bytes para el descriptor. El slot 0 aporta evidencia previa de una petición completada. |
| NOP OUT | `0x918EEE80` | 32 bytes en el espacio posterior a los ocho descriptores de tareas de LK. |
| NOP IN | `0x918EEF00` | 32 bytes para la respuesta, en la misma asignación. |
| UTRLDBR | `0x00624058` | Una escritura del valor `2` envía el slot 1. |
| Ventana propia de EDK2 | `[0x80440000, 0x80444000)` | La sonda física verifica el contenido inicial. El NOP del Go utiliza las colas heredadas. |

Los respaldos y el panel anterior identifican las dos asignaciones de LK, de 1024 bytes cada una. Al iniciar, SEC comprueba la identidad de la placa, la alimentación y los relojes, las bases y el estado de las listas, el mapa de la CPU y el descriptor del slot 0. El NOP usa el tag 1, tipo de comando 2 y cero entradas de datos. El kernel oficial construye los NOP de administración con `DMA_NONE`. [Análisis de LK](UFS_LK_DMA.md) · [Fuente de la sonda](../OculusGoPkg/SecMem/UfsNop11.c) · [Driver oficial](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufshcd.c)

Si el controlador retira la petición y las listas coinciden con el estado previsto, SEC repone los 96 bytes y vuelve a comprobar ambas asignaciones. Si el doorbell sigue activo al vencer el plazo, SEC mantiene los buffers en RAM y muestra `HOLD TIMEOUT`. El panel permanece en pantalla para que el operador lo lea. Un bloqueo puede requerir apagar y volver a arrancar el visor. Las particiones no reciben comandos de escritura.

## Resultados del emulador

- **Imagen de Pacific.** QEMU ejecutó el FD en EL1 y EL2. En cada nivel probó un NOP correcto, un tag incorrecto, una cola ocupada, un slot 0 sin evidencia previa y una traducción de CPU distinta. El banco reproduce los registros de placa necesarios y enlaza el doorbell con el controlador UFS PCI virtual, que genera la respuesta mediante DMA. El ensayo comprueba los caracteres de ambos ojos y compara la página de las colas antes y después. [Diez resultados del FD](evidence/ufs-nop11-fd-qemu-20261121.json)
- **Ventana de EDK2.** En una prueba independiente, la SMMUv3 de QEMU tradujo cuatro páginas consecutivas desde la dirección de bus `0x88000000` a RAM en `0x80440000`. Cada página recibió la respuesta esperada. Al usar la dirección física como dirección de bus, la solicitud quedó pendiente. Al omitir el mapa, la sonda se detuvo antes del envío. La dirección de bus pertenece a ese modelo virtual. [Seis resultados de traducción](evidence/ufs-nop11-window-qemu-20261121.json)

La repetición desde el firmware descomprimido produjo los mismos diez resultados y la misma auditoría estática. Dos compilaciones limpias del auxiliar de traducción produjeron el mismo ELF y los mismos seis resultados. El enlazador descarta la tabla de símbolos del auxiliar, donde GCC incluía un nombre de objeto temporal aleatorio.

## Paquete para arranque temporal

| Archivo local | Bytes | SHA-256 |
| --- | ---: | --- |
| `local/OculusGo-UFS-NOP11-de576f5ca9e3.img` | 385024 | `6f92260b616ab8c643a2713f5b6975c42663605d61867807e2c1a5005616e47b` |
| `OCULUS_GO_DIRECT.fd` | 4194304 | `de576f5ca9e33e6405c444aded8682f3dbcc626a5ad51359a96d586eedd5268b` |
| DTB de Pacific adjunto al flujo gzip | 365129 | `70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35` |

El empaquetador del proyecto comprueba el respaldo de `boot_a`, construye una imagen Android v0 y valida su cabecera, alineación y contenido descomprimido. El firmware y el DTB se conservan localmente. Para revisar el paquete de esta compilación desde la raíz del repositorio, con el visor desconectado, ejecutar `python -B tools/run_ufs_nop11_once.py`. La salida esperada es `PASS-OFFLINE-ONLY`. [Revisión con hashes](evidence/ufs-nop11-review-20261121.json) · [Empaquetador](../tools/android_boot.py)

## Lectura del panel en la sesión física

La sesión comienza con el Go en Android. Después de cotejar las particiones de arranque por lectura y confirmar que el operador está mirando, el transporte envía una sola vez `fastboot -s <serie-verificada> boot local/OculusGo-UFS-NOP11-de576f5ca9e3.img`. El siguiente panel indicaría que el controlador respondió y que la sonda restauró las colas.

```text
UFS NOP IN    DONE
TAG 01  CT 02
UCD 918EEE80
UTR 918EE420
OCS 00000000
RSP 01000020
RAM RESTORED
FD DMA UNTESTED
```

Registrar el texto que realmente aparezca, incluidos `STOP`, `BAD`, `FAULT` o `HOLD` con su motivo. Si la imagen se detiene antes del panel final, registrar la última fila visible. Después de la lectura, el operador puede seguir la secuencia de apagado y retorno a Android ya probada en este visor. El cotejo de hashes posterior documenta el retorno. Incluso con `DONE`, quedará por demostrar el acceso físico a la ventana propia antes de leer el LUN 4. [Recuperación](RECOVERY.md)
