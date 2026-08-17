# Manual operativo — Recupera Tu Mascota

> **Léeme al inicio de cada sesión que toque este módulo.** Concentra todo lo que hay
> que saber para operar la cuenta `recuperatumascota@gmail.com` sin romper nada ni
> repetir errores ya cometidos.

---

## 1. Qué es

Iniciativa solidaria y gratuita para reunir mascotas perdidas con sus familias tras el
**terremoto en Colombia**. Un bot (Huella) atiende por chat web; un panel privado deja
al equipo revisar y gestionar los casos.

| Qué | Dónde |
|---|---|
| Chat ciudadano (público, sin login) | https://mascotasperdidascolombia.com |
| Panel privado | https://app.glomabeauty.com → menú **🐾 Mascotas** |
| Cuenta | `recuperatumascota@gmail.com` / `Mascotas2026*` |
| API | `https://api.glomabeauty.com` |
| Firma del sitio público | Footer **"Tecnología de Gloma App"** → [@gloma_app](https://www.instagram.com/gloma_app/). Solo ahí; la app y la landing de Gloma no se tocan sin aviso |

---

## 2. Reglas que no se rompen

1. **NUNCA borrar datos sin confirmación explícita del CEO.** Ya pasó una vez: se
   borraron 16 casos productivos interpretando "deja solo los productivos". Los datos
   se recuperaron por point-in-time de RDS, **pero las fotos se perdieron para siempre**
   (el bucket no tiene versionado). Antes de cualquier borrado: preguntar, y sacar
   respaldo.
2. **El teléfono de contacto no se inventa jamás.** Solo sale de `entregar_contacto`.
   Hay un guardarraíl en `llm_engine._viola_contacto` que descarta el turno si el modelo
   escribe un número que no vino de la herramienta. No debilitarlo.
3. **Ubicación y teléfono son obligatorios** en todo reporte propio. Se pueden corregir,
   nunca vaciar. Excepción: los importados de otras plataformas no traen teléfono y se
   resuelven con `origen_url`.
4. **De las plataformas hermanas solo se importan las mascotas ENCONTRADAS** (salvo que
   el CEO diga otra cosa). Importar perdidas ajenas llena el cruce de ruido.
5. **El listado en Excel que entrega el bot es solo de encontradas.** Los reportes de
   familias buscando llevan datos de contacto y no se reparten en un archivo.
6. **Paridad local ↔ RDS**: toda migración se aplica en los dos entornos en el mismo PR.

---

## 3. Arquitectura

```
Chat web (mascotasperdidascolombia.com)
  → POST /api/mascotas/chat  → routers/mascotas.py
      → services/llm_engine.advance()   (Claude vía Bedrock, modelo Haiku)
          → tools de mascotas → services/mascotas.py → tabla `mascotas`
```

**Backend** (`backend/app/`)
| Archivo | Qué hace |
|---|---|
| `routers/mascotas.py` | Chat público, subida de fotos, panel privado, exports, conversaciones |
| `services/mascotas.py` | Storage de fotos, scoring de búsqueda, cruce, Excel, export ZIP/JSON |
| `services/llm_engine.py` | Motor LLM compartido; las tools de mascotas viven ahí |
| `services/mascotasporcolombia.py` | Importador (sitemap + payload de React) |
| `services/patitasacasa.py` | Importador (API pública JSON) |
| `bot_contexts/mascotas_cali.md` | Contexto a priori del bot Huella |

**Tablas**: `mascotas`, `mascota_fotos`, `mascota_coincidencias`, y `bot_llm_decisions`
(con `chat_ref` / `chat_contacto` para el registro de conversaciones).

**Storage**: bucket privado `gloma-mascotas-747456040509`, prefijo `mascotas/<codigo>/`.
El backend hace de proxy en `GET /mascotas/foto/{codigo}/{id}` — el bucket nunca se abre
al público. ⚠️ **No tiene versionado**: lo que se borra, se pierde.

---

## 3.1 Peso de las fotos

El algoritmo vive en `app/services/imagenes.py` y lo usan dos caminos. Los dos bajan a
2000 px de lado largo, guardan JPEG progresivo y **descartan el EXIF** — con la
geolocalización que traen las fotos de celular adentro.

**Al subir** (`guardar_foto`, automático): una pasada a calidad 85, ~200 ms para una foto
de 4 MB. La foto nace con `optimizada=TRUE`. Si la imagen viene corrupta o no se gana
nada, se guarda el original sin marcar y el barrido la toma después: nunca se pierde una
foto por un error de compresión.

**El barrido del bucket** (`optimizar_fotos_mascotas.py`, manual): para lo que ya estaba
guardado. Prueba varias calidades y se queda con la más baja que aún pasa SSIM ≥ 0.96.

```bash
conda activate multiagente
python backend/scripts/optimizar_fotos_mascotas.py --dry-run   # ver qué haría
python backend/scripts/optimizar_fotos_mascotas.py             # sólo lo pendiente
python backend/scripts/optimizar_fotos_mascotas.py --restaurar <clave>   # revertir una
```

**Corre siempre desde el equipo del CEO**: el bucket es privado y la BD no se alcanza
desde fuera de la VPC. Lo que hay que saber:

- **Nunca repite trabajo**: lleva registro en `registro_optimizacion_fotos.csv` (se abre
  en Excel), deja la marca `optimizado=v1` en el objeto de S3, y la columna
  `mascota_fotos.optimizada` en la BD. Una foto nueva con la misma clave sí se reprocesa
  (cambia el ETag).
- **Respalda antes de sobreescribir** en `respaldos_fotos_mascotas/` (git-ignorado). Es
  el único camino de vuelta mientras el bucket no tenga versionado.
- **Deja un manifiesto** `registro_optimizacion_pendientes_bd.json` con lo que falta
  reflejar en la BD. Se aplica desde dentro de la VPC:
  ```bash
  aws s3 cp backend/scripts/registro_optimizacion_pendientes_bd.json \
      s3://gloma-mascotas-747456040509/import/optimizacion_fotos.json --region sa-east-1
  TASKDEF=multiagente-backend:15 ./backend/scripts/rds_exec.sh \
      backend/scripts/sync_fotos_bd_mascotas.py
  aws s3 rm s3://gloma-mascotas-747456040509/import/optimizacion_fotos.json --region sa-east-1
  ```
- **Los PNG pasan a JPG**, o sea que cambia la clave del objeto. El PNG viejo **no se
  borra** ahí mismo (regla 1): queda como residuo hasta que el CEO autorice limpiarlo.

**Limpiar el residuo** — objetos del bucket que ninguna fila de `mascota_fotos`
referencia. Necesita autorización explícita del CEO cada vez:

```bash
./backend/scripts/rds_query.sh "SELECT storage_key FROM mascota_fotos" | tail -n +3 > /tmp/keys.txt
python backend/scripts/limpiar_residuo_fotos.py --claves /tmp/keys.txt            # enumera
python backend/scripts/limpiar_residuo_fotos.py --claves /tmp/keys.txt --borrar   # borra
```

Aborta si la lista de claves vivas llega con menos de 50 (sin ella, todo parecería
residuo) y baja una copia de cada objeto a `respaldos_fotos_mascotas/` antes de borrarlo.

Resultado de la primera corrida (2026-08-16): 100 fotos, **88.3 MB → 16.7 MB**. Detalle
en BITACORA #359.

---

## 4. El bot (Huella)

Tres casos de uso, y nada más:
1. **Buscar** una mascota perdida.
2. **Reportar** una encontrada.
3. **Descargar** el listado en Excel (solo encontradas).

Comportamiento que costó trabajo afinar — no revertir sin motivo:
- Busca apenas tiene **especie + 2 datos**. Pedir cuatro cosas antes de buscar es el
  peor error con alguien angustiado.
- Registra apenas tiene **ubicación + teléfono**; lo demás lo completa después con
  `completar_reporte`.
- **Sin coincidencias**: dice que la lista se actualiza a diario, que el caso queda
  guardado, pide teléfono y registra.
- Tras registrar una perdida, **pregunta si hay otra mascota** que registrar.
- Fuera de los 3 casos: lo aclara una vez y, si insisten, cierra y **pausa el canal 20
  minutos**.
- El saludo lleva el **aviso de uso de datos**.

**Modelo**: Haiku. Se intentó Sonnet pero Bedrock lo rechaza en esta cuenta
(`INVALID_PAYMENT_INSTRUMENT`, blocker abierto desde el Sprint 19). Si se resuelve el
medio de pago: cambiar `model_id` en `seed_bot_mascotas.py` y re-sembrar.

---

## 5. Matching (cómo se cruzan los casos)

`services/mascotas._evaluar()` puntúa campo a campo. **Nada es obligatorio**: lo que la
persona no sabe, no puntúa. La especie es el único filtro duro.

| Campo | Peso | Por qué |
|---|---|---|
| raza, color | 5 | Lo que de verdad identifica |
| señas | hasta 5 | "collar azul", "mancha en la pata" |
| tamaño | 3 | |
| zona | 2 | **No descarta**: el animal camina, y quien lo encuentra reporta dónde está, no dónde se perdió |
| sexo, edad, especie | 2 | |
| **nombre** | **1** | Quien encuentra un animal en la calle no sabe cómo se llama |

No puntúan: sexo `desconocido` y las zonas genéricas (`Cali`, `Valle`…), porque los trae
casi todo reporte importado e inflaban cualquier par.

Sinónimos que se colapsan antes de comparar: criollo=mestizo=callejero, café=marrón,
dorado=amarillo=beige, gris=plateado, atigrado=rayado, etc. (`_SINONIMOS`).

**Umbrales**: búsqueda en vivo ≥3; cruce diario ≥12 y máximo 3 candidatas por caso
(con 250×50 pares, umbral 6 daba 5.284 coincidencias y el panel era inservible).

**Estado actual: el cruce automático está PAUSADO** (EventBridge `mascotas-cruce-diario`
en DISABLED, por decisión del CEO). El botón "🔗 Buscar coincidencias" del panel sí
funciona.

---

## 6. Importadores

| Origen | Cómo | Ojo con |
|---|---|---|
| `mascotasporcolombia.com` | Sitemap + payload de React. `/mascotas/` = perdidas, `/found-pets/` = encontradas | Respeta robots.txt. Separa fichas con varias mascotas en un registro por animal |
| `patitasacasa.com` | Su **API pública** `/prod/pets/<ciudad>?limit=100` | **Su WAF bloquea las IPs de AWS (403)**: no se puede correr desde ECS. Hay que ejecutarlo desde una red no bloqueada y subir el resultado |

Ambos deduplican por `(source, origen_id)` y son idempotentes.

**Los teléfonos de patitasacasa vienen enmascarados** (`310****57`) — su plataforma los
protege a propósito. No hay forma legítima de obtener el número completo: para contactar
a esas personas hay que ir a su sitio y usar su botón de contacto.

**Procedimiento para importar patitasacasa a producción** (por el bloqueo del WAF):
1. Local: `docker compose -p wati exec -T backend python scripts/import_patitasacasa.py`
2. Exportar los casos + fotos a un JSON.
3. Subir metadatos y fotos a `s3://gloma-mascotas-747456040509/import/`.
4. Correr un script en ECS que los lea de S3 y los cargue (los overrides de ECS tienen
   límite de 8 KB, por eso va por S3).
5. Limpiar el prefijo `import/`.

---

## 7. Panel

- **Coincidencias**: pares del cruce, con puntaje y qué campos coincidieron. Las
  descartadas quedan **archivadas** (ocultas, con un botón para verlas).
- **Se buscan / Encontradas**: tablas con filtros (texto, especie, zona, estado, solo con
  foto), visor de fotos a pantalla completa con la ruta `s3://`, edición completa,
  borrado y **subida de fotos** (`+ foto`).
- **Conversaciones**: una fila por hilo con el contacto y **los caminos que tomó el bot**;
  los mensajes solo al desplegar.
- **Botones**: 🔄 Actualizar tabla · 🔗 Buscar coincidencias · 📊 Excel · 📦 ZIP · 🧾 JSON.
  (El de sincronizar se retiró: el WAF del origen impide correrlo desde el servidor.)

Acceso: solo la cuenta de la iniciativa. Cualquier otra recibe 403 y no ve el menú.

---

## 8. Despliegue

```bash
# Backend
docker build --platform linux/amd64 -f Dockerfile.backend \
  -t 747456040509.dkr.ecr.sa-east-1.amazonaws.com/multiagente-backend:<tag> .
docker push 747456040509.dkr.ecr.sa-east-1.amazonaws.com/multiagente-backend:<tag>
# clonar la task-def, cambiar la imagen, registrar, y:
aws ecs update-service --cluster multiagente-cluster \
  --service multiagente-backend-service --task-definition multiagente-backend:<rev> \
  --force-new-deployment --region sa-east-1

# Frontend: push a main → Amplify buildea solo (app d1cfl9ey07f61o)

# Scripts contra RDS (la BD no es accesible desde fuera de la VPC)
TASKDEF=multiagente-backend:<rev> ./backend/scripts/rds_exec.sh <script.py> [VAR=valor]
```

⚠️ `rds_exec.sh` manda el archivo como `python -c`: **el script no puede usar `__file__`**.

**Env vars propias del módulo** (task-def): `MASCOTAS_BUCKET`, `MASCOTAS_PUBLIC_BASE`,
`AWS_REGION`.

---

## 9. Recuperación ante desastre

RDS `multiagente-db` tiene backups automáticos con **1 día** de retención y
point-in-time recovery:

```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier multiagente-db \
  --target-db-instance-identifier multiagente-db-rescate \
  --restore-time <ISO8601 UTC anterior al incidente> \
  --db-subnet-group-name multiagente-db-subnet \
  --vpc-security-group-ids sg-056f67098a4f41cf6 \
  --db-instance-class db.t3.micro --no-multi-az --no-publicly-accessible \
  --region sa-east-1
```
Tarda ~20 min. Después: extraer las filas y copiarlas a producción, y **borrar la
instancia** para no dejar costo.

**Las fotos NO tienen respaldo** (bucket sin versionado). Pendiente abierto: activarlo.

---

## 10. Pendientes abiertos

Ver BITACORA, sprint "Ayuda a Cali" (#347–#354). Los principales:
- **#347** Conectar el bot a un WhatsApp Business (el pendiente grande).
- **#348** Avisar automáticamente a quien busca cuando aparece una coincidencia.
- **#350** Retención/borrado de datos y aviso de privacidad formal (habeas data).
- **#351** Moderación de fotos.
- **#352** Búsqueda visual por foto (subiría muchísimo la tasa de acierto).
- **#361** Borrar los 36 PNG viejos que quedaron tras la conversión a JPG (26.5 MB) —
  necesita visto bueno explícito del CEO.
- **Activar versionado en el bucket de fotos** (lección del borrado accidental).
