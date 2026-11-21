# El menú UEFI dentro del Oculus Go

Al encender el Go, el propietario quiere ver un **monitor rectangular flotante**
con una vista para cada ojo. Desde el monitor podrá elegir una entrada de
arranque, abrir la UEFI Shell, configurar el firmware y el entorno virtual,
consultar los controladores cargados, diagnosticar el hardware y entrar en
recuperación. El texto debe seguir siendo legible al ajustar el tamaño, la
distancia o la posición del monitor y al recentrarlo. La estabilidad visual,
el contraste y la latencia tienen prioridad sobre las animaciones.

## Punto de partida

| Componente | Evidencia actual |
| --- | --- |
| Pantalla en el visor | En SEC, la función C dibujó tras comprobar su pila. El primer byte del píxel produjo azul y el tercero rojo en el framebuffer heredado. La disposición de las vistas y la óptica por ojo siguen por medir. [Observación física](evidence/sec-c-transfer-20261118.json) |
| Gráficos en DXE | Confirmado en el Go. El GOP publicado por InheritedGopDxe dibujó las cinco franjas del ensayo M3. El perfil de texto coloca una copia de cada glifo en cada mitad del framebuffer. La orientación y el encaje bajo las lentes se medirán por ojo. [Prueba física del GOP](evidence/dxe-gop-transfer-20261120.json) · [Consola de texto](DXE_TEXT.md) |
| Arranque e interacción | El volumen actual contiene SEC y DXE. Están pendientes el administrador de arranque, la Shell, el acceso al almacenamiento desde UEFI, la entrada del mando y el compositor. [Composición del firmware](../OculusGoPkg/OculusGoPkg.fdf) · [Matriz de controladores](DRIVER_MATRIX.md) |

## Integración prevista

1. **Monitor por software.** Componer una superficie de texto y dibujarla con
   GOP para cada ojo. En el PC, empezar con orientación fija y después
   simular giros y recentrado. Comprobar proyección, recorte y legibilidad
   al variar tamaño y distancia. La calibración óptica y la orientación real
   de cada vista requieren mediciones en el visor.
2. **Sensores, aceleración y mando.** Incorporar por separado la aceleración
   Adreno 530 y la orientación de cabeza 3DoF. Para el control inalámbrico
   original, verificar primero emparejamiento y botones, después orientación y
   puntero. El puntero permitirá seleccionar entradas y escribir en un teclado
   QWERTY español/inglés compatible con las interfaces de texto de UEFI.
3. **Arranque y recuperación.** Integrar el menú con las entradas de arranque
   y la consola cuando estén disponibles. La VR tendrá una opción de
   compilación. Si falla la GPU, el seguimiento, Bluetooth o el compositor,
   el firmware deberá ofrecer la interfaz convencional y una recuperación que
   funcione sin el mando. El objetivo principal sigue siendo arrancar Windows
   ARM64. La VR en Windows requerirá sus propios controladores después de
   `ExitBootServices()`. [Estado de la plataforma](STATUS.md) · [Recuperación actual](RECOVERY.md)
