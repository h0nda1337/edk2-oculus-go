# Auditoría de arranque y recuperación: Oculus Go (`pacific`)

Revisión offline del 13 de noviembre de 2026. **La superficie de sustitución
documentada por Meta que sirve para probar la entrada a EDK2 es `boot.img`.**
La guía también contempla sustituir `system.img`, pero no es un paso necesario
para medir SEC de EDK2. No se efectuaron escrituras ni
pruebas de aceptación de imágenes modificadas en esta revisión.

## Jerarquía de evidencias

- **Observado:** salida histórica de esta unidad, bytes de los respaldos o
  estructura de un contenedor identificado. El inventario, sin binarios, está
  en [partitions.json](evidence/partitions.json).
- **Documentado:** política publicada para el Go por Meta, o arquitectura
  general de Qualcomm/AOSP cuando así se indica. Un nombre de partición o
  cabecera ELF no demuestra qué componente valida una firma, su clave, la
  cobertura exacta ni si esa imagen se cargó en el arranque observado.
- **Esperado, no probado:** reacción ante una modificación deliberada. No hay
  serie física de pruebas de corrupción por etapa. **UNKNOWN** no equivale a
  «sin protección» ni a «recuperable».

## Etapas y superficies de modificación

El modelo de trabajo es **ROM/PBL → carga temprana (XBL y componentes de
plataforma) → LK/Fastboot → imagen Android → kernel/sistema**. La ROM y el
encadenamiento de etapas son arquitectura general de Qualcomm. En esta unidad
sí están identificados los respaldos XBL y LK y el formato de ambos `boot`;
no está demostrada la secuencia exacta de todos los auxiliares ni su política
de autenticación individual. `_a/_b` indica las dos copias del inventario,
no una garantía de conmutación automática.

| Etapa o datos | Evidencia de esta unidad | Escritura y autenticación | Consecuencia y recuperación |
| --- | --- | --- | --- |
| ROM/PBL y raíz del SoC | El PBL reside en ROM según Qualcomm; no es una partición del inventario. No se leyeron fusibles. | No es un target de escritura UFS. Desbloquear LK/Fastboot no cambia por sí mismo esta capa. | No hay restauración de ROM mediante un backup de partición. No se probó un cambio de configuración de confianza. |
| Carga temprana: `xbl_a/b` | Ambos dumps conservados con magia ELF64; están en LUN distintas. La arquitectura Qualcomm describe autenticación de la etapa inicial de almacenamiento. | No hay sustitución no firmada soportada por Meta para esta etapa. Cobertura y configuración exactas: **UNKNOWN**. | Si una modificación invalida la autenticación o impide cargar XBL, el resultado podría ser ausencia de Fastboot. No hay recuperación de este fallo validada. |
| Servicios de plataforma: `tz_a/b`, `hyp_a/b`, `rpm_a/b`, `pmic_a/b`, `devcfg_a/b`; asociados `ovrtz_a/b`, `cmnlib_a/b`, `cmnlib64_a/b`, `keymaster_a/b`, `modem_a/b`, `bluetooth_a/b` | Nombres y bytes preservados. `tz_a` está identificado como ELF AArch64 por análisis histórico; el resto tiene distintos grados de identificación estática. | El desbloqueo Android no autoriza sustituir estos componentes. Verificador, orden, sectores cubiertos y política de fallos por imagen: **UNKNOWN**. | Una imagen rechazada o incompatible puede impedir el arranque o afectar funciones posteriores; no se observó experimentalmente cuál falla para cada partición. Sin recuperación temprana validada. |
| Bootloader del SO: `aboot_a/b` (LK en el `aboot_a` analizado) | LK identificado en evidencia estática del dump y en el flujo histórico de Fastboot. `Device critical unlocked: false` coexistió con `Device unlocked: true`. | Son dos estados de software reportados, no una prueba de una ACL exacta por partición. No hay un método documentado por Meta para sustituir LK con una imagen propia ni un cambio de firma ensayado. | Si se pierde LK, no debe contarse con USB Update Mode/Fastboot para restaurar el propio `aboot`. El respaldo por sí solo no ofrece un canal de escritura. |
| Imagen Android: `boot_a/b` | Ambos respaldos son contenedores Android v0; el análisis histórico identifica kernel, ramdisk y DTB anexados. | Meta documenta que su bootloader desbloqueado deja de exigir la firma de Oculus en `boot.img`. No se midió escritura persistente ni un arranque EDK2 exitoso en esta unidad. | Una imagen mal formada puede fallar antes de ceder control; una imagen aceptada puede colgarse después. La recuperación por menú se observó tras una prueba temporal, no tras sobrescribir `boot`. |
| Android: `system_a/b` | Ambos respaldos tienen la magia ext en el superblock; no hay particiones separadas `vendor`, `recovery`, `dtbo` ni `vbmeta` en el inventario de esta unidad. | Meta documenta la posibilidad de sustituir el sistema mediante una imagen de arranque propia y la política de dm-verity. La ausencia de `vbmeta` no prueba que no haya verificación de Android. | Un sistema incompatible podría dejar Android sin arranque, incluso si el menú sigue operativo. No se probó una restauración persistente. Excluido de la prueba SEC. |
| Configuración y datos (`devinfo`, `misc`, `sec`, `persist`, `frp`, `cdt`, etc.) | Presencia o respaldo no demuestran su semántica exacta. No se tratan como etapas ejecutables. | Sin base para marcarlos como editables. No son objetivos de EDK2; no usar metadatos, calibración ni tabla de particiones para probar la cadena. | Una alteración puede perder estado o calibración, aunque el cargador siga iniciando. No se probaron modificaciones. |

## Separar hardware, política y resultado

1. **Hardware:** arranque desde ROM y raíz de confianza del SoC. El estado de
   fusibles y la configuración de confianza de esta unidad no se midieron.
2. **Acceso de escritura:** disponibilidad de un canal de escritura y permisos
   del cargador. `critical unlocked` es un indicador de política distinto de
   una verificación de firma. La guía genérica de AOSP **no** acredita comandos
   ni una lista de secciones críticas específicos del Go.
3. **Aceptación de `boot.img` y dm-verity:** política de Android independiente
   de la autenticación de etapas anteriores. `Secure boot: true`, `secure: yes`,
   `Device unlocked: true`, `Device critical unlocked: false`, `Verity enabled:
   false` y `Verified boot enabled: false` son resultados históricos de Fastboot,
   no mediciones físicas independientes. Véase la [sesión registrada](evidence/stock-recovery-session-20261025.json).
4. **Ejecución:** formato aceptado, transferencia completada y entrega al código
   son eventos distintos. Asimismo, el Secure Boot de un eventual firmware UEFI
   sería su propia política para consumidores posteriores de UEFI, no la ROM Qualcomm.

## Qué ocurrió al probar y qué recuperación conocemos

- El 1 de octubre de 2026 (hora de Ciudad de México), un diagnóstico temporal
  histórico, **distinto de EDK2**, recibió `OKAY`; el operador vio un logo fijo.
  La auditoría histórica de LK sitúa ese `OKAY` antes de la entrega al payload.
  Ni el `OKAY`, ni el logo, ni la pérdida de USB identifican si entró código o
  dónde se detuvo. No clasificarlo como rechazo criptográfico. El intento antiguo
  quedó consumido y no se reutiliza.
- Se comprobó apagar y volver al menú original; en la prueba del 1 de octubre
  se regresó a Android mediante un reinicio normal desde Fastboot. En la
  sesión del 25 de octubre (histórica), se verificó de nuevo `Boot device` y
  coincidieron los hashes completos de `boot_a/b` y `aboot_a/b` con los respaldos.
  Eso no mide fusibles ni las otras 46 particiones en el visor. [Recuperación](RECOVERY.md).
- Si el menú no aparece tras un fallo temprano, **no** se dispone de una
  restauración validada: no se ha validado EDL/programador firmado ni una imagen
  oficial completa de fábrica. El paquete oficial SW Unlock no se ha validado
  como restauración integral. A/B no garantiza arrancar otro slot coherente si
  falla una etapa temprana; no se cambiarán slots por tanteo.

## Opciones para EDK2, en orden de utilidad

1. **Medición temporal de SEC con la cadena original intacta.** Es la alternativa
   concreta: [SEC_VISUAL](SEC_VISUAL_PHYSICAL_REVIEW.md), imagen ya empaquetada y
   revisada, 12 escenarios QEMU, sin escritura permanente. Las dos bandas serían
   evidencia positiva del checkpoint SEC, no de DXE/GOP. Su ausencia no permite
   separar problemas de entrega, estado de CPU, watchdog o scanout. El 18 de
   noviembre el operador vio los cuatro colores en este único intento. Android
   volvió y coincidieron los cuatro hashes de recuperación.
   [Resultado físico](evidence/sec-visual-transfer-20261118.json).
2. **Otro diagnóstico temporal con mejor señal:** sólo tras interpretar el primero
   y revisar de nuevo el canal de observación, el mapa y el binario exacto. No
   retirar guards ni tomar una pérdida de USB como confirmación de ejecución.
3. **Sustitución persistente de `boot.img`: opción condicional**, no un siguiente
   paso automático. La política Meta es pertinente, pero no establece que el
   payload EDK2 funcione. Antes de proponer una escritura, demostrar ejecución
   temporal útil, identificar exactamente una partición y su conjunto de slot,
   preparar restauración verificada con el stock conservado y obtener autorización
   separada tras mostrar comando, imagen, tamaño, hash, consecuencias y reversión.
4. **Arranque desde Linux mediante `kexec`: no demostrado.** En la revisión
   pública fijada del kernel oficial no aparece `CONFIG_KEXEC` en
   [pacific_defconfig](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/arch/arm64/configs/pacific_defconfig),
   ni un `KEXEC` en [Kconfig ARM64](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/arch/arm64/Kconfig)
   ni `machine_kexec` en el [Makefile del kernel ARM64](https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/arch/arm64/kernel/Makefile).
   Eso no identifica el kernel realmente instalado. Incluso si hubiera soporte,
   el estado que deja Linux no es el contrato de entrada que se está probando
   desde LK; no es un sustituto directo del diagnóstico.
5. **Firmware temprano:** sólo cabría evaluar un mecanismo soportado para imágenes
   autorizadas por el proveedor si apareciera evidencia específica del Go. No hay
   uno verificado para este objetivo. No se propone un parche que neutralice la
   autenticación, programación de fusibles ni un ensayo de corrupción de firmware.

## Verificación de los archivos preservados

`tools/audit_partition_backups.py` abre únicamente archivos locales en lectura,
recalcula tamaño y SHA-256 completos y emite indicios de formato por magia. No
invoca ADB/Fastboot, no verifica firmas criptográficas y no cambia los respaldos.

```powershell
python tools/audit_partition_backups.py --backup-dir '<directorio-local-de-los-50-backups>'
```

Resultado: **50/50, 6.620.180.480 bytes coincidentes**. En los 50 se identificaron
dos magias Android, 22 ELF (10 ELF32 + 12 ELF64), tres magias ext en el offset
estándar y 23 sin clasificar por esta comprobación. Un resultado sin clasificar
no demuestra que el contenido esté vacío, dañado o sin firmar. Este resultado
rehace la comprobación de las copias del disco del PC, no su lectura del visor.
El reporte íntegro permanece local bajo `build/local-partition-backup-audit-20261113.json`;
véase el [resumen verificable](evidence/local-partition-backup-audit-20261113.json).

## Fuentes externas

- [Oculus: guía específica del Go](https://developers.meta.com/vr/blog/unlocking-oculus-go/) y [ficha SW Unlock](https://developers.meta.com/vr/downloads/package/oculus-go-sw-unlock/).
- [Qualcomm: Secure Boot and Image Authentication, §1 (2016)](https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/secure-boot-image-authentication_11.30.16.pdf). Contexto de ROM y autenticación encadenada, no una especificación de `pacific`.
- [AOSP: protección de secciones críticas](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking#protect-critical-sections). Modelo general, no autorización para el Go.
- [UEFI 2.11: Secure Boot and Driver Signing](https://uefi.org/specs/UEFI/2.11/32_Secure_Boot_and_Driver_Signing.html). Capa posterior y distinta de la cadena Qualcomm.

Proveniencia local histórica: `docs/LK_AUDIT.md`,
`docs/TRUSTZONE_AUDIT.md`, `docs/FASTBOOT_AUDIT.md` y
`docs/FIRST_TEMPORARY_PROBE_20261001.md` del proyecto preservado, visibles en
el commit `f0e8c82fbc47550a6d2a96aa8c9ef174fc61391b`. Se reutilizan
observaciones, no el ejecutor ni implementaciones del port anterior.
