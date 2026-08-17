# Mapeo de fuentes → tabla `mascotas`

Qué publica cada fuente, en qué columna cae, y qué se pierde por el camino.
Actualizado el 2026-08-17, con 315 reportes cargados.

## Las seis fuentes

| `source` | Origen | Tipos que trae | ¿Teléfono? | Cómo se baja |
|---|---|---|---|---|
| `web` | Nuestro propio bot (Huella) | perdida y encontrada | Sí, obligatorio | El ciudadano lo escribe en el chat |
| `royipets` | PDF que manda la fundación RoyiPets (Cali) | encontrada | Sí, el de la fundación | `backend/scripts/extraer_royipets_pdf.py` lee el PDF |
| `petsearch` | [petsearch.neuralync.dev](https://petsearch.neuralync.dev) | perdida y encontrada | **Sí** | API JSON pública |
| `encontradogs` | [encontradogs.co](https://www.encontradogs.co) | perdida y encontrada | **No, a propósito** | HTML del servidor, ficha por ficha |
| `proteccionanimal` | [Protección Animal del Valle](https://proteccionanimal.valledelcauca.gov.co/ayudanos-llegar-casa) | perdida y encontrada (deducido) | A veces, dentro de la descripción | API .NET, listado + detalle |
| `mascotasporcolombia` | mascotasporcolombia.com | encontrada | No | Sitemap + payload de React |
| `patitasacasa` | patitasacasa.com | perdida y encontrada | Enmascarado (`310****57`) | API pública; su WAF bloquea las IPs de AWS |

## Matriz campo × fuente

`●` la fuente lo publica como campo aparte · `~` se deduce leyendo texto libre ·
`—` la fuente no lo tiene.

| Columna | web | royipets | petsearch | encontradogs | proteccionanimal | mascotasporcolombia | patitasacasa |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `tipo_registro` | ● | ● | ● | ● | **~** | ● | ● |
| `especie` | ● | ● | ● | ● | ● | ● | ● |
| `raza` | ● | ● | ● | ● | — | ● | ● |
| `color` | ● | ~ | ~ | ● | ~ | ● | ● |
| `nombre` | ● | ● | ● | ● | ● | ● | ● |
| `sexo` | ● | ● | ~ | ● | ● | ● | ● |
| `edad` | ● | ~ | ~ | ~ | ~ | ● | — |
| `tamano` | ● | ~ | ~ | ● | ~ | ● | ● |
| `senas` | ● | ● | ● | ● | ● | ● | ● |
| `ubicacion` | ● | ● | ● | ● | ● | ● | ● |
| `barrio` | ● | ● | ● | ● | ● | ● | ● |
| `ciudad` | — | ● | ● | ~ | ● | ● | ● |
| `departamento` | — | ● | ● | — | ● | — | — |
| `maps_url` | ● | — | — | — | — | ● | — |
| `contacto_nombre` | ● | ● | — | — | ● | ● | — |
| `contacto_telefono` | ● | ● | ● | — | ~ | — | — |
| `origen_url` | — | — | ● | ● | ● | ● | ● |
| `fecha_evento` | ● | ● | ● | ● | — | ● | ● |
| `esterilizado` | — | ● | — | — | ● | — | — |
| `vacunado` | — | — | — | — | ● | — | — |
| `desparasitado` | — | — | — | — | ● | — | — |
| `peso_kg` | — | — | — | — | ● | — | — |
| `salud` | — | ● | — | — | — | ● | — |
| `resguardo` | — | ● | — | — | ● | ● | — |
| `resguardo_nombre` | — | ● | — | — | ● | — | — |
| `rescatado_por` | — | ● | — | — | — | — | — |
| `rescatado_por_telefono` | — | ● | — | — | — | — | — |
| `recompensa` | — | — | — | — | — | ● | — |
| `estado_origen` | — | ● | ● | ● | ● | ● | ● |
| `publicado_origen_at` | — | — | ● | ● | — | ● | — |

## Lo que hay que saber de cada fuente

### `royipets` — el PDF
Llega como PDF exportado de Excel, **sin rejilla vectorial**: las columnas se
reconstruyen por la coordenada x de cada palabra y las filas por el recuadro de
la foto. Dos filas del reporte no tienen foto y se resuelven por el hueco que
dejan las vecinas — por eso el extractor no puede guiarse solo por las imágenes.

**Excel recorta el texto que no cabe en la celda.** Una descripción de una sola
línea que topa el borde derecho está incompleta, no es corta: el extractor lo
detecta y lo marca en la revisión.

Es la única fuente con `rescatado_por`: quien llevó el animal al refugio, que es
una tercera persona distinta de quien lo cuida y de quien contesta el teléfono.

### `petsearch` — la más limpia
Tres estados en el mismo endpoint: `missing` → perdida, `stray` → encontrada,
`found` → **reencontrada, no se trae**. Es la única fuente externa que publica el
teléfono, así que sus fichas entregan teléfono *y* enlace a la ficha original.

No tiene página por mascota: `origen_url` apunta a la portada.

### `encontradogs` — sin teléfono a propósito
El sitio hace de intermediario entre quien busca y quien encontró, y no publica
contactos. Sus fichas entran solo con `origen_url`, y el bot lo sabe manejar: en
`entregar_contacto` manda a la ficha original en vez de dar un número.

El tipo sale de **la sección de la portada** donde aparece la ficha, no de un
campo. Las que ya volvieron a casa no se listan ahí, y por eso quedan fuera sin
tener que adivinar.

### `proteccionanimal` — la que más ojo necesita
1. **Marca todo como `Perdido`**, incluso los hallazgos. Quien reporta lo escribe
   en el campo del nombre: hay fichas llamadas literalmente `encontrado` o
   `Me perdí`. El tipo se deduce de ahí y **cada deducción queda marcada en la
   revisión** para que un humano la confirme.
2. **El teléfono va dentro de la descripción** (`…mancha blanca en pecho-3XXXXXXXXX`).
   Se extrae al campo de contacto y se **borra del texto**: un número suelto en
   `senas` le tumba el turno al bot por el guardarraíl antiteléfonos.
3. Los campos numéricos (`edad_animal`, `peso_animal`, `tamano_animal`) vienen
   **todos en 0** = sin usar. `_decimal()` descarta el 0 por eso.
4. Las URLs de foto son de S3 **firmadas y vencen en una hora**: hay que bajarlas
   durante la revisión, no al momento de cargar.

### `patitasacasa` — teléfonos enmascarados
Su plataforma protege los números a propósito (`310****57`). No hay forma
legítima de completarlos: para contactar a esas personas hay que ir a su sitio.
Además **su WAF bloquea las IPs de AWS**, así que el importador no corre desde
ECS; hay que ejecutarlo desde una red no bloqueada y subir el resultado.

## Reglas que valen para toda fuente nueva

1. **Ningún número de teléfono puede quedar en `senas` ni en `notas`.** El
   guardarraíl `llm_engine._viola_contacto` descarta el turno completo si el bot
   escribe un número que no vino de `entregar_contacto`. Un teléfono metido en
   una descripción deja al bot mudo justo cuando encontró a la mascota.
2. **Teléfono u `origen_url`, uno de los dos.** `crear_reporte` rechaza el
   reporte si no hay ninguna vía de contacto.
3. **Los rellenos no se guardan.** `anonimo`, `sin nombre`, `RESCATADO`, `N/A` y
   compañía se convierten en NULL (`base.valor_real`): el cruce puntúa el nombre
   y la zona, y "Anonimo" contra "Anonimo" daría un parecido que no existe.
4. **Deduplicación por `(source, origen_id)`**, que es la restricción única de la
   tabla. Es lo que permite re-correr una fuente sin duplicar.
5. **Revisión humana obligatoria** antes de cargar: `--revisar` arma el HTML,
   el CEO lo aprueba, `--cargar` escribe.
