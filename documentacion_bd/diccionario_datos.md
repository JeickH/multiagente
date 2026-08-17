# Diccionario de datos

> Generado por `documentacion_bd/generar.py` leyendo la base local el 2026-08-17. La fuente de verdad del esquema es `backend/app/models.py`.

Qué fuente llena cada campo está en [`mapeo_fuentes.md`](mapeo_fuentes.md).

## `mascotas`

> **Un teléfono en `senas` o `notas` deja mudo al bot**  
> El guardarraíl `llm_engine._viola_contacto` descarta el turno completo si el bot escribe un número que no vino de `entregar_contacto`. Es lo que impide que un modelo pequeño «recuerde» un teléfono plausible y mande a una familia angustiada a marcar un número equivocado. Por eso todo importador borra los números del texto libre.

> **Teléfono <b>u</b> <code>origen_url</code>, uno de los dos**  
> Se valida en `services/mascotas`, no en la base: el motivo es de negocio, no de integridad referencial. Un reporte sin ninguna vía de contacto no sirve para reunir a nadie.

> **<code>UNIQUE (source, origen_id)</code> es lo que hace idempotentes a los importadores**  
> Re-correr una fuente no duplica nada: en la revisión solo aparece lo que todavía no está.

| Columna | Tipo | Nulo | Qué es |
|---|---|:--:|---|
| `id` | integer | no | Clave primaria. |
| `codigo` | varchar(16) | no | Identificador legible que ve el ciudadano (`MC-00042`) y que nombra la carpeta de fotos en el storage. Se deriva del `id` al crear. |
| `tipo_registro` | varchar(16) | no | `perdida` (una familia la busca) o `encontrada` (alguien la tiene o la vio). El cruce siempre compara una contra la otra. |
| `especie` | varchar(24) | no | `perro`, `gato` u `otra`. **Es el único filtro duro del cruce**: nada más descarta un candidato. |
| `especie_otra` | varchar(60) | sí | Qué animal es cuando `especie = otra`. |
| `raza` | varchar(80) | sí | Peso 5 en el cruce. Los sinónimos se colapsan antes de comparar (criollo = mestizo = callejero). |
| `color` | varchar(80) | sí | Peso 5 en el cruce, empatado con la raza: es lo que de verdad identifica a un animal en la calle. |
| `nombre` | varchar(80) | sí | **Peso 1, el más bajo.** Quien encuentra un animal en la calle no sabe cómo se llama. |
| `sexo` | varchar(16) | sí | `macho`, `hembra` o `desconocido`. `desconocido` **no puntúa** en el cruce. |
| `edad` | varchar(40) | sí | Texto libre: «2 años», «cachorro». |
| `tamano` | varchar(24) | sí | `pequeño`, `mediano` o `grande`. Peso 3. |
| `senas` | text | sí | Señas particulares: «collar azul», «mancha en la pata». Aporta hasta 5 puntos. **Nunca puede contener un teléfono** (ver la nota de guardarraíl). |
| `ubicacion` | varchar(255) | no | **Obligatoria.** Dónde se perdió, o dónde está ahora la encontrada. El link de Maps es opcional a propósito: mucha gente sabe dar la dirección pero no compartir una ubicación. |
| `maps_url` | varchar(500) | sí | Enlace de Google Maps, cuando la persona lo compartió. |
| `barrio` | varchar(120) | sí | La zona fina, que es la que puntúa en el cruce (peso 2). **No descarta**: el animal camina, y quien lo encuentra reporta dónde está, no dónde se perdió. |
| `contacto_nombre` | varchar(120) | sí | A nombre de quién está el teléfono. Puede llevar dos, separados por `/`, cuando el animal está en hogar de paso. |
| `contacto_telefono` | varchar(32) | sí | **Solo se entrega cuando la persona confirma que reconoce a la mascota.** Admite uno o dos números separados por `/`: la fundación y la casa donde duerme el animal. |
| `fecha_evento` | date | sí | Cuándo se perdió o se encontró. |
| `estado` | varchar(24) | no | `activo` · `reconocida` (alguien dijo en el chat que es suya, falta confirmar) · `reunida` · `cerrado`. |
| `notas` | text | sí | Contexto que no tiene columna propia. **Nunca puede contener un teléfono.** |
| `bot_id` | integer | sí | Bot que creó el reporte, si entró por chat. |
| `source` | varchar(24) | no | De dónde salió el reporte. `web` es nuestro bot; el resto son fuentes externas. Permite deshacer un lote entero. |
| `created_at` | timestamp | no | Cuándo entró a nuestra base. |
| `updated_at` | timestamp | no | Última modificación. |
| `origen_url` | varchar(500) | sí | Ficha original en la plataforma de donde vino. **Es la vía de contacto** cuando la fuente no publica teléfono. |
| `origen_id` | varchar(120) | sí | Identificador en el sitio de origen. Junto con `source` forma la clave única que hace idempotentes a los importadores. |
| `reconocida_at` | timestamp | sí | Cuándo alguien dijo en el chat que reconocía a esta mascota (el momento en que el bot entregó el contacto). Sirve para saber a quién llamar. |
| `reconocida_chat` | varchar(64) | sí | Desde qué conversación se reconoció. |
| `ciudad` | varchar(120) | sí | Municipio. Las zonas genéricas (`Cali`, `Valle`) **no puntúan** en el cruce: las trae casi todo reporte importado e inflaban cualquier par. |
| `departamento` | varchar(120) | sí | Departamento. Hoy solo lo publican PetSearch y Protección Animal. |
| `esterilizado` | boolean | sí | Tri-estado: NULL = la fuente no lo dice, que no es lo mismo que `false`. |
| `vacunado` | boolean | sí | Tri-estado. Hoy solo lo publica Protección Animal. |
| `desparasitado` | boolean | sí | Tri-estado. Hoy solo lo publica Protección Animal. |
| `peso_kg` | numeric(5) | sí | En kilos. Se descarta el 0 al importar: varias fuentes lo usan como «sin dato» y un animal de 0 kg no existe. |
| `salud` | varchar(255) | sí | Lesiones o estado reportado, en texto corto. |
| `resguardo` | varchar(40) | sí | Dónde está durmiendo hoy: `hospital` · `hogar_de_paso` · `albergue` · `con_quien_la_encontro` · `en_la_calle` · `con_su_familia`. **Sin CHECK a propósito**: lo alimentan fuentes externas y una restricción rompería un importador cada vez que aparezca un valor nuevo. |
| `resguardo_nombre` | varchar(120) | sí | Nombre del hogar de paso o del albergue. |
| `rescatado_por` | varchar(120) | sí | Quién llevó el animal al refugio. Es una tercera persona: quien lo recogió de la calle no siempre es quien lo cuida. |
| `rescatado_por_telefono` | varchar(32) | sí | Teléfono de esa persona. No lo entrega el bot. |
| `recompensa` | boolean | sí | Si la familia ofrece recompensa. Lo publica Mascotas por Colombia. |
| `estado_origen` | varchar(60) | sí | El estado tal como lo escribe la fuente («DISPONIBLE (ADAPTACIÓN)», «stray», «Perdido»). No se traduce: sirve para auditar de dónde salió nuestro `tipo_registro` cuando hubo que deducirlo. |
| `publicado_origen_at` | timestamp | sí | Cuándo lo publicó la fuente. Distinto de `created_at`, que es cuándo lo trajimos nosotros. |
| `sincronizado_at` | timestamp | sí | Última vez que vimos este reporte en su fuente. |

**Índices**

- `ix_mascotas_barrio` — `btree (barrio)`
- `ix_mascotas_bot_id` — `btree (bot_id)`
- `ix_mascotas_ciudad` — `btree (ciudad)`
- `ix_mascotas_codigo` — `btree (codigo)`
- `ix_mascotas_created_at` — `btree (created_at)`
- `ix_mascotas_departamento` — `btree (departamento)`
- `ix_mascotas_especie` — `btree (especie)`
- `ix_mascotas_estado` — `btree (estado)`
- `ix_mascotas_origen_id` — `btree (origen_id)`
- `ix_mascotas_reconocida_at` — `btree (reconocida_at)`
- `ix_mascotas_resguardo` — `btree (resguardo)`
- `ix_mascotas_source` — `btree (source)`
- `ix_mascotas_tipo_estado` — `btree (tipo_registro, estado)`
- `ix_mascotas_tipo_registro` — `btree (tipo_registro)`
- `mascotas_codigo_key` — `btree (codigo)`
- `uq_mascota_origen` — `btree (source, origen_id) WHERE (origen_id IS NOT NULL)`

## `mascota_fotos`

> **El bucket no tiene versionado**  
> Lo que se borra, se pierde. Ya costó fotos irrecuperables una vez. Antes de cualquier borrado: preguntar y sacar respaldo.

| Columna | Tipo | Nulo | Qué es |
|---|---|:--:|---|
| `id` | integer | no | Clave primaria. |
| `mascota_id` | integer | sí | NULL mientras la foto está en el limbo: el ciudadano suele mandar las fotos ANTES de que el bot termine de recoger los datos. |
| `upload_session` | varchar(64) | sí | uuid efímero del chat contra el que se subió la foto, hasta que el reporte se crea y la adopta. |
| `storage_key` | varchar(400) | no | Ruta en el storage: `mascotas/<codigo>/<uuid>.jpg`. **El mismo layout en S3 y en `media_local/`**, para que las claves de la BD sirvan en los dos entornos. |
| `content_type` | varchar(60) | no | Tipo MIME. Se acepta jpeg, png, webp y heic. |
| `bytes_size` | integer | sí | Peso actual, ya comprimido. |
| `created_at` | timestamp | no | Cuándo se subió. |
| `optimizada` | boolean | no | Si ya pasó por la compresión. Evita reprocesarla. |
| `optimizada_at` | timestamp | sí | Cuándo se comprimió. |
| `bytes_original` | integer | sí | Lo que pesaba antes de comprimir. |

**Índices**

- `ix_mascota_fotos_mascota_id` — `btree (mascota_id)`
- `ix_mascota_fotos_optimizada` — `btree (optimizada)`
- `ix_mascota_fotos_upload_session` — `btree (upload_session)`

## `mascota_coincidencias`

> **El cruce automático está pausado**  
> EventBridge `mascotas-cruce-diario` en DISABLED, por decisión del CEO. El botón «🔗 Buscar coincidencias» del panel sí funciona.

| Columna | Tipo | Nulo | Qué es |
|---|---|:--:|---|
| `id` | integer | no | Clave primaria. |
| `perdida_id` | integer | no | El reporte de la familia que busca. |
| `encontrada_id` | integer | no | El reporte de quien la tiene o la vio. |
| `score` | integer | no | Suma del scoring campo a campo. Umbral 12 en el cruce diario; 3 en la búsqueda en vivo. |
| `detalle` | jsonb | sí | JSONB con qué campos coincidieron y cuánto aportó cada uno, para que el panel lo muestre. |
| `estado` | varchar(16) | no | `nueva` · `revisada` · `confirmada` · `descartada`. Las descartadas quedan **archivadas** (ocultas con un botón para verlas), no se borran. |
| `notas` | text | sí | Lo que anota el equipo al revisar el par. |
| `created_at` | timestamp | no | Cuándo la detectó el cruce. |
| `updated_at` | timestamp | no | Última vez que alguien la tocó desde el panel. |

**Índices**

- `ix_mascota_coincidencias_created_at` — `btree (created_at)`
- `ix_mascota_coincidencias_encontrada_id` — `btree (encontrada_id)`
- `ix_mascota_coincidencias_estado` — `btree (estado)`
- `ix_mascota_coincidencias_id` — `btree (id)`
- `ix_mascota_coincidencias_perdida_id` — `btree (perdida_id)`
- `ix_mascota_coincidencias_score` — `btree (score)`
- `ix_match_created_at` — `btree (created_at)`
- `ix_match_encontrada` — `btree (encontrada_id)`
- `ix_match_estado` — `btree (estado)`
- `ix_match_estado_score` — `btree (estado, score)`
- `ix_match_perdida` — `btree (perdida_id)`
- `ix_match_score` — `btree (score)`
- `uq_mascota_par` — `btree (perdida_id, encontrada_id)`
