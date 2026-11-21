# Pirámide de bienvenida antes de la Shell

BDS selecciona la consola centrada y dibuja una pirámide de vidrio azul antes de cargar la aplicación Shell del volumen. El modelo tiene cinco vértices, cuatro caras triangulares y una cara inferior cuadrada. La base mide 168 × 168 unidades y el vértice está 153 unidades por encima. La primera versión con esta misma base tenía 181 unidades de altura. La reducción es del 15,5 %. [Geometría y material](../OculusGoPkg/Drivers/GoBdsDxe/Welcome.c)

| Fase | Tiempo de la animación | Movimiento |
| --- | --- | --- |
| Entrada | 0–1,6 s | La pirámide asciende desde debajo de la zona visible y se detiene en el centro. |
| Giro | 1,6–5,8 s | Una vuelta de 360° sobre su eje vertical, con aceleración y frenado suaves. |
| Saludo | 5,8–7,9 s | Las letras azules de `Welcome to EDK2 Go!` se iluminan de izquierda a derecha. |
| Lectura | 7,9–8,9 s | La escena permanece quieta. BDS limpia la ventana y entrega la consola a la Shell. |

La CPU transforma los vértices, los proyecta en perspectiva dos veces y rasteriza las caras traseras y delanteras en ese orden. Cada vista usa una cámara ligeramente desplazada. El paso delantero toma muestras desplazadas de las caras traseras según la normal de la superficie, con una pequeña separación de color. El tinte transmite 217/255 de la luz en cada superficie. Los reflejos y el brillo de las aristas se suman a esa transmisión. La frecuencia objetivo es de 30 fotogramas por segundo y el reloj arquitectónico determina el progreso cuando dibujar un fotograma tarda más. La tipografía utiliza las mismas máscaras de 8 × 19 píxeles que la consola, ampliadas al doble. [Fuente y licencia](../THIRD_PARTY_NOTICES.md#console-font)

El fotograma lógico de 352 × 400 píxeles cabe dentro de la ventana de texto comprobada en el visor. El firmware reserva tres superficies de trabajo en RAM (1 689 600 bytes en total), las presenta con `GOP.Blt()` y las libera antes de arrancar la Shell. Las luces, la refracción y el brillo proyectado bajo la base se calculan en el firmware. La ruta de arranque sigue disponible si falla la animación. Para compilar con el saludo desactivado, se puede fijar `gOculusGoPkgTokenSpaceGuid.PcdGoWelcomeEnabled` a `FALSE` en la configuración de plataforma. [Integración en BDS](../OculusGoPkg/Drivers/GoBdsDxe/GoBds.c)

## Prueba con QEMU

Al comando de arranque de la Shell se le añade `--observe-welcome`. El observador lee el framebuffer del invitado, sigue el contorno durante la subida y el giro, compara las dos proyecciones y reconoce las letras a partir de las máscaras de la Shell. Sólo termina cuando también se lee el prompt centrado. La vista previa adjunta se genera en el PC a partir de esos fotogramas. [Instrucciones de compilación y QEMU](SHELL_BOOT.md#reproducir) · [Observador](../tests/welcome_observer.py)

El archivo de vista previa se puede regenerar en el host con Pillow a partir del directorio devuelto por la prueba.

```sh
uv run --no-project --with pillow python tests/export_welcome_preview.py <directorio-de-la-prueba> piramide.webp
```

![Animación capturada en una vista de QEMU hasta el prompt](evidence/welcome-pyramid-20261120.webp)

La imagen Android preparada se identificó con SHA-256 `10070578236364e171eee002d5a32fef44e1be7baafcc879f71a9e166b1004b6`. El FD extraído de esa imagen produjo 79 muestras de la animación en una corrida de Pacific. Las dos vistas presentaron el saludo legible y después el mismo prompt. El verificador offline del equipo de compilación se ejecuta con `python tools/run_welcome_once.py`. [Medición del FD de Pacific](evidence/welcome-pacific-el1-20261120.json) · [Imagen y hashes](evidence/welcome-review-20261120.json)

La prueba física anterior verificó el texto de la Shell centrada en ambos ojos. El confort binocular de esta animación, la orientación del relieve a través de las lentes y la fluidez en el Go requieren una prueba física propia. La entrada física de comandos sigue pendiente. [Prueba anterior en el Go](evidence/shell-centered-transfer-20261120.json)
