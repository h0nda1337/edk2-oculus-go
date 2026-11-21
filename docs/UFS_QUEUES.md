# Colas UFS tras LK y memoria para DMA

**Resultado en QEMU.** El FD de Pacific observa las direcciones de las dos listas y examina 16 KiB propios desde la CPU. En un ensayo separado, un controlador UFS PCI emulado completó una transacción NOP con descriptores en cada una de las cuatro páginas. **En el visor siguen pendientes las bases que programó LK y el mapeo DMA de esta ventana.** El panel de la [prueba física anterior](evidence/ufs-handoff-transfer-20261121.json) confirmó UFSHCI 1.1, ambas listas en marcha y ambos registros de solicitudes pendientes a cero.

## Qué mide la imagen temporal

1. SEC valida la identidad EVT, el FDT, la pila y los estados de alimentación y reloj del ensayo anterior. Requiere la versión de host observada, dispositivo presente, canal UIC disponible, listas disponibles y en marcha, sin indicadores de error de host/dispositivo ni bits de solicitudes pendientes.
2. Lee dos veces la serie CAP, UTRLBA, UTRLBAU, UTMRLBA, UTMRLBAU. Comprueba que las dos series coinciden y vuelve a consultar habilitación, disponibilidad, Run/Stop y doorbells al final. Una diferencia entre muestras detiene la evaluación. Son lecturas sucesivas y un cambio transitorio entre ellas puede pasar inadvertido.
3. Combina las mitades altas y bajas en direcciones de bus de 64 bits. Con CAP calcula el número de slots de cada lista y la extensión compatible con esa capacidad. Un UTRD mide 32 bytes y un UTMRD, 80. Comprueba alineación de 1024 bytes, anchura de dirección, aritmética sin desbordamiento y separación entre las listas. Un valor nulo o ambiguo queda sin interpretar. El extremo exclusivo que coincidiría con 2⁶⁴ también se rechaza. La longitud calculada describe la capacidad del host. La asignación efectiva que hizo LK queda pendiente de corroboración. [Driver del kernel del Go](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufshcd.c) · [Registros y formatos](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/drivers/scsi/ufs/ufshci.h)
4. Comprueba la ventana CPU del FD entre `0x80440000` y `0x80444000` (fin exclusivo). En este perfil ocupa una región explícita del FDF, separada del volumen ejecutable, la pila activa, el FDT y el framebuffer. Descarta cualquier coincidencia numérica con las extensiones de las listas y cualquier intersección con una reserva FDT fija o de la tabla de reservas. Sólo entonces lee las 4096 palabras de cuatro bytes que la imagen dejó a `FFFFFFFF`. Un valor distinto detiene la prueba. La dirección de una lista nunca se usa como puntero CPU. [Sonda](../OculusGoPkg/SecMem/UfsQueues.c) · [Disposición del FD](../OculusGoPkg/OculusGoPkg.fdf)

La reserva de 16 KiB pertenece exclusivamente a `UFS_QUEUES`. En el diseño actual de `NORMAL`, esas direcciones caen dentro de `FVCOMPACT`. La integración en DXE necesitará una asignación propia y una dirección DMA válida para esa asignación.

La captura local de `/soc/ufshc@624000` carece de propiedades `iommus` y `dma-ranges`. Tampoco se encontró `dma-ranges` en sus ancestros `/soc` y `/`. El inventario de Android dejó sin resolver el grupo IOMMU y la máscara DMA. Las reservas dinámicas del kernel se asignan en otra etapa. CAP indica la anchura admitida por la interfaz, mientras que la dirección que realmente alcanza la RAM depende del mapeo del controlador. El kernel del Go solicita direcciones DMA al asignador coherente. La traducción, los permisos y la coherencia que heredó el firmware siguen **UNKNOWN**. [Procedencia y revisiones](REFERENCES.md)

## Cómo leer el panel

| Rótulo | Lectura |
| --- | --- |
| `UFS QUEUES    DONE` | Se completaron los controles de la sonda y la lectura CPU de la ventana. |
| `CAP` y `ADDR` | Capacidad bruta y anchura DMA que anuncia el host. |
| `UTR` / `UTM` | Dirección DMA programada para la lista de transferencias / tareas. En cada fila van primero los ocho dígitos altos y luego los ocho bajos. |
| `LEN` | Bytes calculados para transferencias a la izquierda y gestión de tareas a la derecha, ambos en hexadecimal. |
| `FD` / `CPU WINDOW CLEAN` | Dirección CPU, longitud y comprobación del patrón del FD en ese instante. |
| `DMA MAP UNKNOWN` | La sonda física termina antes de lanzar DMA. La lectura del sector de `splash` requiere aún establecer el mapeo del Go. |
| `BUSY`, `NOT READY`, `VERSION`, `GATED`, `DISABLED` | El estado inicial no permitió comprobar las bases. El nombre de la cabecera identifica el registro. |
| `CHANGED`, `INVALID`, `OVERLAP`, `CONFLICT FDT`, `DIRTY FD`, `FAULT` | La cabecera identifica la comprobación que detuvo la prueba. Los números visibles en una captura parcial deben conservar ese contexto. |

Ante una lectura que se quede detenida, la última cabecera `READ` identifica el registro que se intentaba leer. El operador puede tomar una foto de una lente o copiar el panel por filas. La secuencia termina en SEC, con el texto fijo. El retorno utiliza Power y «Boot device» en el menú original, según el procedimiento ensayado. [Recuperación](RECOVERY.md)

## Dos ensayos independientes

**Firmware.** QEMU ejecuta el mismo FD que se empaqueta para el Go. Se reutilizan la captura FDT y las trece lecturas físicas anteriores. Las bases, CAP y los estados cambiantes son sintéticos. Pasaron 52 casos, 26 en EL1 y 26 en EL2. Las comprobaciones cubren las cargas MMIO, el orden de acceso, los límites de escritura en RAM, el texto en ambos ojos y las salidas por conflicto o excepción. La prueba altera deliberadamente el resultado de una carga en los casos de transición y provoca un aborto de alineación en el caso de fallo. La inspección estática valida el único ejecutable SEC del volumen, sus tablas de registros, el acceso MMIO, los vectores y las 16 384 posiciones iniciales del FD. [Resultados de la sonda](evidence/ufs-queues-qemu-20261121.json) · [Inspección del binario](evidence/ufs-queues-static-20261121.json)

**Acceso DMA del controlador virtual.** Un programa exclusivo del PC inicializa la función PCI UFS de QEMU, con la CPU invitada detenida, sin IOMMU virtual y sin almacenamiento conectado. Coloca un descriptor NOP en cada página por turno y espera una respuesta NOP IN con el tag correcto y OCS cero. Compara los 16 KiB antes y después, permitiendo cambios sólo en el estado del descriptor y el espacio de respuesta. La traza registró cuatro NOP y cero órdenes SCSI o consultas UFS. Esto demuestra que el controlador virtual puede leer y devolver respuestas en las cuatro páginas con ese mapeo. Las transacciones de este banco de prueba sólo existen en el PC. [Resultados DMA](evidence/ufs-queues-pci-dma-20261121.json) · [Banco virtual](../tests/ufs_queue_dma_model.py)

## Reproducción

Desde Debian/WSL, con `runtime` apuntando a la copia local del DTB de ejecución y `run` al directorio que imprime la compilación:

```bash
bash scripts/build.sh DEBUG 8 UFS_QUEUES
fd="$run/OCULUS_GO_DIRECT.fd"
elf=Build/OculusGoUfsQueues/DEBUG_GCC5/AARCH64/OculusGoPkg/SecMem/UfsQueues/DEBUG/OculusGoUfsQueues.debug
python3 tests/ufs_queues_qemu.py --fd "$fd" --sec-elf "$elf" --runtime-fdt "$runtime" --report "$run/QEMU.json"
python3 tests/ufs_queues_static.py --fd "$fd" --sec-elf "$elf" --report "$run/STATIC.json"
python3 tests/ufs_queue_dma_model.py --report "$run/PCI-DMA.json"
```

En Windows, el modo de compilación es `UFS_QUEUES`. El comando `python tools/run_ufs_queues_once.py` verifica el expediente y el contenedor privado sin contactar el visor. El siguiente paso físico es un arranque temporal atendido de esa imagen. [Revisión del contenedor](evidence/ufs-queues-review-20261121.json)
