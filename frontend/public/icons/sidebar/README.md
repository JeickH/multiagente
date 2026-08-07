# Iconos del Sidebar — Gloma

Iconos del menú lateral de la app multiagente. Reemplazan los emojis actuales en `frontend/components/Sidebar.tsx`.

## Reglas comunes (style guide)

Toda la familia debe respetarse para que los 5 iconos se sientan parte del mismo set:

- **Formato de salida**: PNG cuadrado 512×512, **fondo 100% transparente**.
- **Sin texto**, sin letras, sin marca de agua, sin tipografía.
- **Sin fondo**, sin caja contenedora, sin sombra dura. No "icono dentro de un círculo".
- **Estilo**: line-art outline (vectorial), **trazos color blanco puro #FFFFFF**, grosor uniforme 6–8 px (a 512 px), uniones y extremos redondeados (`stroke-linejoin: round`, `stroke-linecap: round`).
- **Sin relleno** (solo contorno) salvo donde la spec del icono indique un detalle macizo pequeño (ej. pupila del bot, badge).
- **Padding interior** ~12% (≈60 px de margen al borde del lienzo) para que se vea balanceado dentro del sidebar.
- **Estética**: minimalista, friendly, refinada, alineada con la identidad Gloma (warm/earthy). Trazo moderno tipo "Lucide / Phosphor / Tabler Icons".
- **Colocación**: cada icono centrado en el lienzo, perfectamente alineado al pixel, sin rotación caprichosa.
- **Sidebar destino**: fondo `gloma-brown` (#5E503F), por eso los trazos van en blanco — la app cambiará la opacidad/tinte vía CSS para estados hover/active.

## Iconos a generar

### 1. `mensajes.png` — Mensajes
- **Símbolo**: una burbuja de chat (speech bubble) redondeada con la pequeña "cola" hacia la esquina inferior izquierda (estilo WhatsApp).
- **Detalles internos**: 3 líneas horizontales cortas centradas que representen líneas de texto (de longitudes ligeramente distintas para verse natural: ej. 70%, 90%, 50% del ancho interior).
- **Composición**: la burbuja ocupa ~75% del lienzo, centrada.
- **Prompt corto para Canva**: *"Minimalist line-art outline icon of a single rounded chat speech bubble with a small tail at bottom-left and three short horizontal lines inside representing text. Pure white strokes (#FFFFFF) on a 100% transparent background. Stroke width 7px, rounded line caps and joins. No text, no shadow, no background container, no color fill. Square 512x512 PNG. Clean modern Lucide / Phosphor icon style."*

### 2. `campanas.png` — Campañas
- **Símbolo**: un megáfono (no una campana) inclinado ~30° hacia arriba-derecha.
- **Detalles**: el cono del megáfono más ancho a la derecha, mango grueso a la izquierda, y **3 arcos cortos** saliendo del cono representando ondas de sonido.
- **Composición**: balance horizontal, ondas a la derecha sin tocar el borde.
- **Prompt corto para Canva**: *"Minimalist line-art outline icon of a single megaphone tilted 30 degrees up-right, with three short curved sound-wave arcs radiating from the wide end. Pure white strokes (#FFFFFF) on a 100% transparent background. Stroke width 7px, rounded caps and joins. No text, no fill, no shadow, no background. Square 512x512 PNG. Clean modern Lucide / Phosphor icon style."*

### 3. `bots.png` — Bots
- **Símbolo**: cabeza de robot estilo "friendly bot": rectángulo redondeado (head), **antena corta arriba con una bolita en la punta**, dos **ojos circulares macizos** (los únicos elementos rellenos del set, blancos), y una boca opcional como pequeña línea horizontal o tres puntos.
- **Composición**: cabeza centrada vertical, antena dentro del padding, hombros/cuello no necesarios.
- **Prompt corto para Canva**: *"Minimalist line-art outline icon of a friendly robot head: rounded square head, a short antenna on top with a filled circle dot, two solid white circular eyes inside, and a tiny straight mouth line. Pure white strokes and fills (#FFFFFF) on a 100% transparent background. Stroke width 7px, rounded corners. No text, no shadow, no background container. Square 512x512 PNG. Clean modern Lucide / Phosphor icon style."*

### 4. `mi-plan.png` — Mi Plan / Perfil
- **Símbolo**: silueta de persona (busto): **círculo de la cabeza** arriba y **arco/hombros** abajo. Sin contenedor circular alrededor.
- **Detalle "plan"**: una pequeña **estrella maciza** en la esquina superior derecha del busto (badge sutil que sugiere "plan/cuenta premium"). La estrella debe ser ~15% del tamaño del busto.
- **Composición**: persona centrada, estrella tocando la esquina superior derecha del hombro.
- **Prompt corto para Canva**: *"Minimalist line-art outline icon of a user bust silhouette: a circle for the head on top and a wide arc for the shoulders below. A small solid five-point star badge at the top-right corner of the shoulders, slightly overlapping. Pure white strokes (#FFFFFF) and white star fill, on a 100% transparent background. Stroke width 7px, rounded caps and joins. No text, no shadow, no surrounding circle frame, no background. Square 512x512 PNG. Clean modern Lucide / Phosphor icon style."*

### 5. `salir.png` — Salir / Logout
- **Símbolo**: una **puerta abierta** vista de frente con **una flecha apuntando hacia la derecha saliendo de ella**. Mismo concepto que el icono "log-out" de Lucide.
- **Detalles**: marco de puerta como rectángulo abierto en el lado derecho; flecha horizontal con punta clásica saliendo a la derecha. Un pequeño círculo (manija) en el lado izquierdo de la puerta.
- **Composición**: puerta a la izquierda, flecha a la derecha; flecha NO toca el borde del lienzo.
- **Prompt corto para Canva**: *"Minimalist line-art outline logout icon: a vertical door frame open on the right side with a small circular doorknob, and a horizontal arrow pointing right exiting through the opening. Pure white strokes (#FFFFFF) on a 100% transparent background. Stroke width 7px, rounded caps and joins, classic arrowhead. No text, no shadow, no background, no fill. Square 512x512 PNG. Clean modern Lucide / Phosphor icon style — like the Lucide log-out icon."*

## Iteración y revisión

- Los outputs se guardan acá mismo (`frontend/public/icons/sidebar/`).
- Si el CEO pide ajustes en alguno, se regenera con prompt afinado y se sobrescribe el PNG.
- Cuando el set esté aprobado, el Dev Plataforma reemplaza los emojis del Sidebar por `<Image src="/icons/sidebar/<slug>.png" />`.
