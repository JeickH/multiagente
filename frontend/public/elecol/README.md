# Assets de la landing `/elecol`

Esta carpeta concentra **todos** los assets visuales (imágenes, renders, videos, logos)
que consume `frontend/pages/elecol.tsx`. Mientras el equipo de diseño entrega los
assets reales, hay placeholders SVG provisionales generados por
`frontend/scripts/generate_elecol_placeholders.mjs` (ver al final).

> **Identidad de marca**: "Infinito Eléctrico — Edición Mar + Sol"
> Paleta: `#03045E` (azul profundo) · `#0077B6` (azul eléctrico) · `#00B4D8` (cian solar) · `#90E0EF` (azul cielo) · `#CAF0F8` (blanco espuma) · `#FFC300` (amarillo energía).
> Referencias visuales: Tesla Energy, Rivian, Apple, Stripe.

---

## Convenciones generales

- **Formato preferido** para fotos / renders: `.webp` (con fallback `.jpg`). Para iconos / logotipos: `.svg`. Para video hero: `.mp4` H.264 + `.webm`.
- **Naming**: `kebab-case`, sin acentos, sin espacios, prefijado por la sección.
- **Densidad**: las imágenes pensadas para ocupar más del 50% del viewport en desktop deben entregarse a **2× la dimensión de display** (para Retina).
- **Peso recomendado por imagen**: ≤ 350 KB (foto) / ≤ 60 KB (logo SVG). El hero video idealmente < 6 MB en `.mp4` (loop ≤ 12 s, sin audio).
- **Color de fondo seguro**: si la imagen tiene transparencias, asumir fondo `#03045E` (azul profundo). Si lleva glow, que el glow sea azul cian (`#00B4D8`) o amarillo solar (`#FFC300`).
- **Prohibido**: fondos blancos planos, iconografía corporativa genérica (engranajes, handshakes), stock photos obvias.

---

## Estructura por sección

### `hero/`

Sección 2 del brief — espacio cinematográfico para presentar la marca.

| Archivo | Tipo | Dimensiones display | Entrega (2×) | Notas |
|---------|------|---------------------|-------------|-------|
| `hero-render.webp` | Imagen estática principal | 1280 × 800 | 2560 × 1600 | Render 3D de electrolinera solar al atardecer, perspectiva ¾, con halo de luz cian. Es el fallback si no hay video. |
| `hero-video.mp4` | Video loop H.264 | 1920 × 1080 | — | Loop cinematográfico ≤ 12 s, sin audio, ≤ 6 MB. Camera move lento (push-in o pan). |
| `hero-video.webm` | Video loop VP9 | 1920 × 1080 | — | Mismo loop en VP9 para navegadores que prefieran webm. |
| `hero-poster.webp` | Poster del video | 1920 × 1080 | — | Primer frame del video. Sirve mientras carga. |

### `infraestructura/`

Sección 3 del brief — split izquierda imagen, derecha 4 cards.

| Archivo | Tipo | Dimensiones display | Entrega (2×) | Notas |
|---------|------|---------------------|-------------|-------|
| `estacion-render.webp` | Render principal | 720 × 900 | 1440 × 1800 | Render lateral de la estación, paneles solares arriba, conector EV inferior. Iluminación nocturna con glow azul. |
| `icon-solar.svg` | Icono card 1 | 64 × 64 | — | Energía solar integrada. Trazo 1.5px, color `#FFC300`. |
| `icon-autonomia.svg` | Icono card 2 | 64 × 64 | — | Operación autónoma 24/7. Trazo 1.5px, color `#00B4D8`. |
| `icon-ev.svg` | Icono card 3 | 64 × 64 | — | Compatibilidad universal EV. Trazo 1.5px, color `#90E0EF`. |
| `icon-carga-rapida.svg` | Icono card 4 | 64 × 64 | — | Carga rápida inteligente. Trazo 1.5px, color `#FFC300`. |

### `software/`

Sección 4 del brief — mockup central de dashboard + 6 features laterales.

| Archivo | Tipo | Dimensiones display | Entrega (2×) | Notas |
|---------|------|---------------------|-------------|-------|
| `dashboard-mockup.webp` | Mockup principal | 1120 × 700 | 2240 × 1400 | Captura del dashboard ELECOL OS: mapa de estaciones, KPIs de carga, gráfico de potencia entregada. Dark theme con acentos cian + amarillo. |
| `dashboard-mockup-mobile.webp` | Mockup mobile | 360 × 720 | 720 × 1440 | Vista mobile de la app de operador (opcional, para parallax). |
| `icon-reservas.svg` | Feature 1 | 48 × 48 | — | Reservas. Color `#00B4D8`. |
| `icon-remoto.svg` | Feature 2 | 48 × 48 | — | Gestión remota. Color `#90E0EF`. |
| `icon-monitoreo.svg` | Feature 3 | 48 × 48 | — | Monitoreo en tiempo real. Color `#FFC300`. |
| `icon-analitica.svg` | Feature 4 | 48 × 48 | — | Analítica. Color `#00B4D8`. |
| `icon-franquicias.svg` | Feature 5 | 48 × 48 | — | Gestión de franquicias. Color `#90E0EF`. |
| `icon-pagos.svg` | Feature 6 | 48 × 48 | — | Pagos integrados. Color `#FFC300`. |

### `red-latam/`

Sección 5 del brief — mapa oscuro interactivo con puntos luminosos.

| Archivo | Tipo | Dimensiones display | Entrega (2×) | Notas |
|---------|------|---------------------|-------------|-------|
| `mapa-latam.svg` | Mapa principal | 1200 × 800 | — | Mapa vectorial de Latinoamérica, dark theme, países sin bordes brillantes (stroke `#0077B6` 0.5px sobre fondo `#03045E`). Pensado para sobreponer dots animados desde código. |
| `mapa-latam.webp` | Fallback imagen | 1200 × 800 | 2400 × 1600 | Versión raster por si algún navegador no renderiza bien el SVG. |
| `dot-glow.svg` | Punto luminoso reusable | 24 × 24 | — | Círculo con glow radial (cian + amarillo). Se inyecta múltiples veces para marcar ciudades. |

### `cta/`

Sección 7 del brief — bloque CTA final, fondo muy oscuro con iluminación central.

| Archivo | Tipo | Dimensiones display | Entrega (2×) | Notas |
|---------|------|---------------------|-------------|-------|
| `cta-bg.webp` | Fondo full-bleed | 1920 × 900 | 3840 × 1800 | Composición abstracta: líneas de energía + glow azul-amarillo, sin elementos figurativos. Pensado para soportar texto encima sin contraste roto. |
| `cta-bg-mobile.webp` | Fondo mobile | 750 × 1200 | 1500 × 2400 | Versión vertical para mobile. |

### `brand/`

Logotipos y elementos de marca reusables en header, footer y favicon.

| Archivo | Tipo | Dimensiones display | Entrega (2×) | Notas |
|---------|------|---------------------|-------------|-------|
| `logo-elecol.svg` | Logo principal | 160 × 40 | — | Wordmark blanco/cian con isotipo (rayo solar). Versión sobre dark. |
| `logo-elecol-mono.svg` | Logo monocromo | 160 × 40 | — | Para fondos donde el logo color rompe contraste. |
| `isotipo.svg` | Solo isotipo | 64 × 64 | — | Solo la marca gráfica (sin wordmark). Para favicon, app icon. |
| `favicon.ico` | Favicon | 32 × 32 + 16 × 16 | — | ICO multi-resolución. |
| `og-image.png` | Open Graph | 1200 × 630 | — | Imagen para previews en redes (LinkedIn, X, WhatsApp). |

---

## Placeholders provisionales

Mientras llegan los assets reales, ejecuta:

```bash
cd frontend
node scripts/generate_elecol_placeholders.mjs
```

El script genera un SVG por cada filename listado arriba (en su carpeta
correspondiente). Cada placeholder muestra:
- gradiente oscuro `#03045E → #0077B6` con halo `#00B4D8`,
- el nombre del archivo en grande,
- las dimensiones recomendadas,
- una nota "PLACEHOLDER".

Para los archivos con extensión `.webp`, `.mp4`, `.webm`, `.png` o `.ico` (que no
son SVG), el script genera el `.svg` equivalente con un sufijo `.placeholder.svg`
**junto** al filename canónico, y `pages/elecol.tsx` consume directamente el
`.placeholder.svg` cuando no encuentra el real (vía un helper `assetOrPlaceholder`).

> El script es **idempotente** — re-ejecutarlo regenera todos los placeholders y
> NO sobreescribe los assets reales (los reconoce por extensión y por la ausencia
> del sufijo `.placeholder.svg`).

---

## Cuándo reemplazar los placeholders

Cuando el equipo de diseño entregue los assets reales:

1. Coloca el archivo en la carpeta correcta con el filename exacto (ver tablas arriba).
2. Elimina el `.placeholder.svg` correspondiente (opcional pero recomendado para limpiar).
3. Verifica `next dev` o `next build`: no debe haber `404` en assets.
4. Commit con mensaje `feat(elecol): assets reales seccion-X`.
