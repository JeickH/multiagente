# Sprint 13 — Revisión de Seguridad (pre-implementación)

**Auditor**: Experto en Seguridad
**Fecha**: 2026-05-11
**Tarea**: BITACORA #157
**Scope auditado**:
- `backend/docs/sprint13_schema.md` (Experto BD)
- `identidad_gloma/diseno_campanas.html` (UI/UX wireframes)
- Sección "Sprint 13" de `BITACORA.md`
- Patrones existentes en `backend/app/models.py` (`MetaAccount`) y `backend/app/routers/meta_webhook.py`

---

## Veredicto

**APROBADO CON CAMBIOS** — bloqueante para Dev Plataforma (tareas #159–#163) hasta resolver los hallazgos **Altos** S13-001, S13-002, S13-003, S13-004 y S13-005.

El diseño de BD es sólido (multi-tenancy estricto, idempotencia explícita con `UNIQUE meta_message_id` y dedupe parcial en `campaign_events`, índices parciales, CHECKs cerrados). Los hallazgos son del nivel de **endpoints y operación**, no del schema: faltan controles de autorización cruzada (anti-IDOR), rate-limit en cara a Meta, límites anti-abuso por campaña, filtro de `opt_in` y reglas de logging de PII. Ninguno es Crítico (ningún secreto se filtra, el patrón de cifrado de `MetaAccount` se respeta) pero los Altos son **bloqueantes para merge**.

## Resumen ejecutivo

- 0 Críticos · **5 Altos** · 6 Medios · 4 Bajos · Total **15 hallazgos**.
- Bloqueantes para merge: S13-001 a S13-005.
- El modelo de amenazas dominante es: (a) IDOR entre teams via IDs numéricos enumerables (`SERIAL PK`), (b) usuario malicioso o comprometido que dispara envíos masivos para gastar saldo WABA del tenant o triggerear suspensión por Meta, (c) leaks de PII por logging en frío del CSV / payloads del webhook / objetos SQLAlchemy redactables.
- La regla 2 (schemas `...Out` sin secretos) está respetada por construcción del DDL (las plantillas y campañas no exponen tokens), pero hay dos puntos a vigilar en código: `WhatsappTemplateOut`/`CampaignOut` **no deben serializar `meta_account` completo** vía relación SQLAlchemy.

---

## Hallazgos

### S13-001 · Alto · IDOR cruzado en `POST /contact-groups/{id}/members` y `POST /campaigns`

**Zona**: Tarea #159 (`POST /contact-groups/{id}/members`), tarea #161 (`POST /campaigns`).

**Descripción**: el schema designó IDs `SERIAL` (numéricos, enumerables). Si los endpoints filtran sólo el recurso raíz por `team_id` pero confían en los IDs del body sin re-validar, un atacante puede:
- añadir un `contact_id` ajeno a un `contact_group` propio → leak de teléfonos cuando luego liste el grupo;
- crear una campaña con `template_id` o `meta_account_id` de otro team → usa la WABA de un competidor para enviar.

El §2.1 del schema ya identifica la necesidad de "verificación cruzada", pero **no existe constraint a nivel DDL** (decidido por costo) → la única defensa es en el endpoint.

**Mitigación obligatoria** (Dev Plataforma debe implementarla):

```python
# helper común en backend/app/dependencies.py
def require_owned(db, model, pk: int, team_id: int):
    obj = db.query(model).filter(model.id == pk).first()
    if not obj or _team_id_of(obj) != team_id:
        raise HTTPException(404)  # 404, no 403 (no revelamos existencia)
    return obj

# uso
contact = require_owned(db, Contact, body.contact_id, current_user.team_id)
group   = require_owned(db, ContactGroup, group_id,   current_user.team_id)
# `template.meta_account.team_id == current_user.team_id` y
# `meta_account.team_id == current_user.team_id` ANTES de cualquier INSERT.
```

Aplica también a: `POST /campaign-recipients`, `GET /contacts/{id}`, `GET /campaigns/{id}`, `GET /campaigns/{id}/recipients`, `GET /templates/{id}`, `DELETE /templates/{id}`, `POST /templates`, `GET /campaigns/{id}/events/{event_id}/payload`.

---

### S13-002 · Alto · Falta de límite de destinatarios por campaña + ausencia de rate-limit al envío

**Zona**: Tarea #162 (`services/campaign_sender.py`).

**Descripción**: el diseño no define cota máxima de `campaign_recipients` por `campaigns.id` ni rate-limit de envío por team/hora. Vectores:
1. Usuario malicioso o cuenta comprometida crea una campaña con 200k destinatarios → gasta todo el saldo MARKETING de la WABA del tenant.
2. Sin throttling Meta puede marcar la WABA como abusiva (rate-limit / suspension), afectando a todos los teams que compartan infra.
3. Sender sin backoff exponencial al recibir `429`/`80007` de Meta reintenta agresivamente y empeora el ban.

**Mitigación obligatoria**:
- Constante `MAX_RECIPIENTS_PER_CAMPAIGN` (sugerido 10 000) validada en `POST /campaigns` → 400 con mensaje genérico si se excede.
- Rate-limit en `campaign_sender` por `meta_account_id`: máximo N msg/s (configurable, default conservador 10/s) implementado con un token-bucket en memoria o Redis. Documentar default en el servicio.
- Backoff exponencial + jitter sobre `429`, `500-504`, error code Meta `80007` (rate limit hit). `tenacity` ya está en el stack del proyecto.
- `Campaign.status='running'` debe llevar `started_at`; si `now() - started_at > X horas`, marcar `failed` y abrir investigación (alerta operativa).

---

### S13-003 · Alto · Filtro `opt_in=TRUE` no documentado como obligatorio en el sender

**Zona**: Tarea #162 (`campaign_sender`), tarea #161 (`POST /campaigns`).

**Descripción**: el schema define `contacts.opt_in BOOLEAN DEFAULT TRUE` y el wireframe muestra "🔕 12 contactos sin opt-in serán excluidos" + el aviso final "Solo destinatarios con opt-in válido recibirán el mensaje", pero **no es una regla técnica documentada en `sprint13_schema.md`**, sólo UX. Si el sender sólo lee `campaign_recipients` (snapshot) y no consulta `contacts.opt_in` en el momento del envío, un contacto que retire opt-in entre la creación de la campaña y el envío programado **recibirá el mensaje**. Esto es un riesgo regulatorio (LGPD-BR, Habeas Data CO) y de banneo por Meta.

**Mitigación obligatoria**:
- Al **encolar** (POST /campaigns): excluir contactos con `opt_in=FALSE` y registrar `campaign_recipients.status='skipped'` con `error_code='opt_out_at_enqueue'` (el campo `'skipped'` ya está en el CHECK).
- Al **enviar** (sender tick): re-leer `contacts.opt_in` justo antes del POST a Meta; si cambió a FALSE, marcar `status='skipped'` con `error_code='opt_out_at_send'` y NO llamar a Meta.
- Auditable: `campaign_events(event_type='sync_warning', payload_json={"reason":"opt_out", "contact_id":N})` para trazabilidad.

---

### S13-004 · Alto · Logging de PII en webhook (`logger.info("Webhook Meta recibido: %s", payload)`) y futuro logueo de `payload_json`

**Zona**: `backend/app/routers/meta_webhook.py:70` (preexistente, **tarea #163 lo va a tocar**) y nuevo flujo de eventos Sprint 13.

**Descripción**: la línea actual loguea el payload completo del webhook a `INFO`. Cuando Sprint 13 extienda el webhook para campañas, **cada entrega/lectura va a loguear PII en bruto** (teléfono del destinatario, posiblemente nombre, mensaje crudo si es respuesta inbound). Esto viola la regla 1 de seguridad de CLAUDE.md ("nunca loggear PII en bruto"). El issue ya existía pero el Sprint 13 lo amplifica (más volumen, más eventos).

**Mitigación obligatoria** (la pide la propia tarea #163):
- Reemplazar `logger.info("Webhook Meta recibido: %s", payload)` por un resumen redactado:
  ```python
  logger.info(
      "webhook.meta event_count=%d phone_number_ids=%s",
      _count_events(payload),
      _phone_ids(payload),
  )
  ```
- En la nueva ruta de ingestión de campañas: log estructurado **sin** `phone_e164` ni contenido del mensaje. Sólo `campaign_id`, `recipient_id` (interno), `event_type`, `wamid_hash` (sha256[:12]).
- Cuando un evento se persiste en `campaign_events.payload_json`, **no se reloguea**. Una sola copia, en DB cifrada en reposo (RDS encryption-at-rest ya está habilitado).
- `Contact.__repr__` y `CampaignRecipient.__repr__` deben enmascarar `phone_e164` (sólo últimos 4 dígitos) y `name` (primera letra + `***`). El §2.2 del schema ya lo pide; debe quedar **implementado** en `models.py` antes del merge de #159.

---

### S13-005 · Alto · `Webhook fail-open` en dev sigue presente al añadir el handler de campañas

**Zona**: `backend/app/routers/meta_webhook.py:47-48` (preexistente, recordatorio del informe de Sprint 6).

**Descripción**: el `_verify_signature` retorna `True` si `APP_SECRET == ""`. Heredado de Sprint 6, sigue abierto. Cuando Sprint 13 extienda el webhook, **toda la lógica de campañas se ejecuta sin verificación si la env var falta**. En producción ECS la var está cargada, pero un misconfig silencioso (typo en task-def) abriría la puerta a inyección de eventos falsos: un atacante podría POSTear `delivered`/`read` arbitrarios al webhook y manipular KPIs, o peor, hacerse pasar por Meta para correlacionar wamids falsos contra `campaign_recipients`.

**Mitigación obligatoria** (cerrar definitivamente este hallazgo en Sprint 13):
```python
def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    if not APP_SECRET:
        if os.getenv("APP_ENV", "dev") == "prod":
            logger.error("META_APP_SECRET ausente en prod — webhook bloqueado")
            return False  # fail-CLOSED en prod
        logger.warning("META_APP_SECRET ausente — fail-open SOLO en dev")
        return True
    ...
```
Y task-def en prod debe **fallar al arranque** si la env var falta (`APP_ENV=prod` + `not APP_SECRET` → raise en startup). El Deploy AWS lo refleja en #173/#174.

---

### S13-006 · Medio · `rejection_reason` y errores de Meta llegan crudos al cliente

**Zona**: Tarea #160 (`services/meta_templates.py`), tarea #161 (errores al crear campaña).

**Descripción**: `whatsapp_templates.rejection_reason TEXT` recibe el texto que Meta devuelve. Si se renderiza tal cual en la UI (`identidad_gloma/diseno_campanas.html` lo muestra como tooltip de la badge "Rechazado"), un texto de Meta con HTML/JS podría inyectarse (XSS si el frontend no escapa) o exponer info interna de Meta al user-agent. Lo mismo aplica para mensajes de error al hacer `POST /templates` (regla 6 — errores sanitizados).

**Mitigación recomendada**:
- Persistir el texto crudo en BD (auditoría), pero al exponerlo en `WhatsappTemplateOut.rejection_reason`: truncar a 500 chars + `bleach.clean(text, tags=[], strip=True)`.
- React/Next ya escapa por defecto en JSX, pero **no** usar `dangerouslySetInnerHTML` para este campo.
- Errores 4xx/5xx desde `services/meta_templates.py` se mapean a un set fijo: `"template_name_taken"`, `"template_rejected_by_meta"`, `"meta_api_unavailable"`. El traceback va a `logger.exception`.

---

### S13-007 · Medio · Rate-limit faltante en `POST /templates/sync` y `POST /templates`

**Zona**: Tarea #160.

**Descripción**: ambos endpoints llaman a Meta. Sin rate-limit por usuario, un usuario puede:
- Forzar 100 syncs/min → Meta nos rate-limitea a nivel app, afectando a otros tenants.
- Crear 50 plantillas seguidas → spam de submissions a Meta, potencial flag de la WABA.

**Mitigación recomendada**:
- Decorador `@rate_limit("10/min")` en `POST /templates/sync` por (user_id, meta_account_id).
- `POST /templates`: límite de 5/hora por team (las plantillas se crean raramente; este límite no afecta uso legítimo).
- El TTL de 15 min de cache lazy (§2.4 del schema) ya mitiga parcialmente, pero el botón "Refrescar" lo ignora — ahí el rate-limit es la única defensa.

---

### S13-008 · Medio · `phone_e164` en URLs de export CSV y query strings

**Zona**: Wireframe línea 547 (`Exportar CSV` en detalle de campaña), futura ruta de export.

**Descripción**: si el export genera una URL firmada o un GET con query (`?campaign_id=X&format=csv`), el contenido (números de teléfono) puede quedar:
- en logs del ALB,
- en historial del navegador,
- en CDN/proxies intermedios.

**Mitigación recomendada**:
- Export como `POST` que retorna `Content-Disposition: attachment` con `Content-Type: text/csv` y body inline (no via URL pre-firmada S3 a menos que sea time-limited + KMS-encrypted).
- Header `Cache-Control: no-store, private` en la respuesta.
- Logear sólo `{user_id, campaign_id, row_count, bytes}` — nunca el archivo.

---

### S13-009 · Medio · Import CSV: tamaño, MIME, validación E.164 y opt-in source

**Zona**: Tarea #159 (`POST /contacts/import` por CSV — UI línea 1020).

**Descripción**: el wireframe declara "máx 2MB" pero el backend debe enforce-arlo. Faltan:
- whitelist MIME (`text/csv`, `application/vnd.ms-excel`) — rechazar otros con 415.
- límite de filas (sugerido 50 000) → 413 si excede.
- validación E.164 por fila antes de INSERT (el CHECK del DDL lo atrapará, pero un error claro al user es mejor).
- `opt_in_source='import_csv'` obligatorio al cargar masivo; sin `opt_in=TRUE` por defecto si la columna no viene (asumir FALSE para cumplir reg).
- **NO loggear el row** ante error de parsing (el §2.2 del schema ya lo pide; reforzarlo aquí).

**Mitigación recomendada**: validación en streaming (`csv.reader` sobre `request.stream()`), rechazar duplicados a `(team_id, phone_e164)` con `ON CONFLICT DO NOTHING` + reportar `{inserted, skipped_duplicates, invalid_rows}` al usuario.

---

### S13-010 · Medio · `WhatsappTemplateOut`/`CampaignOut` con relación SQLAlchemy a `MetaAccount`

**Zona**: Tarea #160 (`schemas.py` para templates) y #161 (para campaigns).

**Descripción**: `whatsapp_templates.meta_account_id` y `campaigns.meta_account_id` son FK. Tentación natural en Pydantic v2 con `from_attributes=True` y `model_config`:
```python
class WhatsappTemplateOut(BaseModel):
    meta_account: MetaAccountOut  # ← PELIGRO si MetaAccountOut filtra
```
Si `MetaAccountOut` se expande mañana para incluir `encrypted_access_token` (por error), todos los `templates` y `campaigns` lo expondrían transitivamente. Regla 2 explícita.

**Mitigación recomendada**:
- `WhatsappTemplateOut` y `CampaignOut` **sólo exponen `meta_account_id` (int)** + opcionalmente `meta_account_display_name` (string). Nunca el modelo entero.
- Test unitario en `tests/test_schemas.py`: serializar `WhatsappTemplate`/`Campaign` con un mock y assert `"encrypted_access_token" not in serialized`.

---

### S13-011 · Medio · `CampaignEventOut` con `payload_json` por defecto

**Zona**: Tarea #161/#163, `schemas.py`.

**Descripción**: el §2.2 del schema dice que `CampaignEventOut` **no expone `payload_json`** por defecto, pero conviene blindarlo:
- listado `GET /campaigns/{id}/events` → resumen sin payload.
- detalle `GET /campaigns/{id}/events/{event_id}/payload` → requiere permiso extra (role='owner' del team). Justificable porque el payload puede incluir respuestas del usuario final que el operador agent no debería leer en bruto.

**Mitigación recomendada**: dos schemas separados: `CampaignEventSummaryOut` (default) y `CampaignEventPayloadOut` (sólo en endpoint guardado).

---

### S13-012 · Bajo · Enumeración de teams por IDs `SERIAL` predecibles

**Zona**: Schema general.

**Descripción**: con IDs incrementales un atacante puede iterar y estimar tamaño del competidor, tasa de crecimiento, etc. No es leak de datos pero sí metadata.

**Mitigación recomendada (no bloqueante)**: para Sprint 13 mantener `SERIAL` (cambiar ahora rompe muchas cosas). Tarea de follow-up: añadir `uuid_external VARCHAR(36) UNIQUE` y usar en URLs públicas, mantener `id` interno. Aplica a `campaigns`, `contacts`, `contact_groups`, `whatsapp_templates`. Documentar en backlog.

---

### S13-013 · Bajo · Falta cifrado de `email` y `attributes` JSONB a nivel app

**Zona**: `contacts.email`, `contacts.attributes`.

**Descripción**: RDS encryption-at-rest está activo (KMS), pero `attributes JSONB` puede recibir campos arbitrarios (potencialmente PII sensible: dirección, RFC, etc.). Hoy el backend no marca qué claves son sensibles.

**Mitigación recomendada (no bloqueante)**: documentar en `docs/sprint13_schema.md` que `attributes` **no** debe usarse para datos altamente sensibles (DNI, número de tarjeta, salud). Si en el futuro se requiere, columna dedicada cifrada con Fernet (patrón `MetaAccount.encrypted_access_token`).

---

### S13-014 · Bajo · `template_variables_json` puede contener PII de ejemplo del CEO al crear plantilla

**Zona**: Tarea #160 (`POST /templates`), tarea #161 (`campaigns.template_variables_json`).

**Descripción**: cuando el operador crea una plantilla, los `example` values que se envían a Meta para aprobación pueden incluir un teléfono real o nombre de un cliente real ("Hola María, tu pedido de $50000..."). Esto:
- queda almacenado en `whatsapp_templates.components_json`,
- se transmite a Meta,
- queda en logs si se loguea el body.

**Mitigación recomendada**: warning en UI ("usa valores de ejemplo genéricos, no datos reales de clientes"). Backend: no logger el body de `POST /templates` (sólo metadata: name, category, language). Esto va alineado con S13-004.

---

### S13-015 · Bajo · `campaigns.created_by_user_id ON DELETE SET NULL` puede romper auditoría de quién envió

**Zona**: §2.5 del schema, tarea #158.

**Descripción**: si se borra un usuario, las campañas que él creó pierden el atribución. En contextos regulados (auditoría LGPD/Habeas Data) puede ser necesario saber **quién** envió aunque ya no esté.

**Mitigación recomendada (no bloqueante)**: añadir `created_by_email_snapshot VARCHAR(255)` que se llena en el INSERT con el email del creador al momento del envío. Permite SET NULL en la FK + preservar identidad histórica. Documentar como follow-up; no bloqueante para Sprint 13.

---

## Requisitos para Dev Plataforma (tareas #159-#163) — checklist

Bloqueantes (verifico yo en la auditoría post-código, tarea #171):

- [ ] **Helper `require_owned(model, pk, team_id)`** en `dependencies.py`; usado en TODOS los endpoints que reciban `*_id` por path/body. Tests de IDOR con `otro@test.com` accediendo a IDs de `demo@gmail.com` → 404.
- [ ] **Validación cruzada** en `POST /campaigns`: `template.meta_account.team_id == campaign.meta_account_id == current_user.team_id` y `template.status == 'APPROVED'`. Test unitario para cada uno de los 3 ramos.
- [ ] **Filtro `contacts.opt_in=TRUE`** aplicado dos veces: al encolar y al enviar. Recipients filtrados → `status='skipped'`, `error_code='opt_out_at_enqueue|opt_out_at_send'`.
- [ ] **`MAX_RECIPIENTS_PER_CAMPAIGN = 10000`** validado en `POST /campaigns` → 400.
- [ ] **Rate-limit en `campaign_sender`** por `meta_account_id`, default 10 msg/s, backoff exponencial sobre 429/80007.
- [ ] **`Contact.__repr__`, `CampaignRecipient.__repr__`, `CampaignEvent.__repr__`** redactados (números → `+57***1234`, email → `m***@x.com`, payload omitido).
- [ ] **`_verify_signature` fail-CLOSED en prod** (`APP_ENV=prod` + falta `APP_SECRET` → return False + log error).
- [ ] **Logging webhook redactado**: sin `phone_e164` ni `content` crudos. Sólo metadata.
- [ ] **Schemas `WhatsappTemplateOut`/`CampaignOut`**: sólo `meta_account_id` (int), NUNCA `MetaAccountOut` embebido. Test unitario que verifique que `"encrypted_access_token"` no aparece nunca en la respuesta.
- [ ] **`CampaignEventSummaryOut` (default, sin `payload_json`)** vs **`CampaignEventPayloadOut` (guard role=owner)**.
- [ ] **`rejection_reason` sanitizado** con `bleach.clean(text, tags=[], strip=True)` antes de exponer.
- [ ] **Errores Meta mapeados** a códigos genéricos al cliente (`"template_rejected_by_meta"`, etc.); stack al `logger.exception`.
- [ ] **Import CSV**: 2 MB / 50 000 filas / MIME whitelist / NO logger del row crudo.
- [ ] **Export CSV**: `POST`, `Content-Disposition`, `Cache-Control: no-store`, log sólo `{user_id, campaign_id, row_count}`.
- [ ] **Rate-limit en `POST /templates/sync` (10/min/user)** y **`POST /templates` (5/h/team)**.

Recomendaciones no bloqueantes (backlog post-Sprint 13):

- [ ] UUID externo para URLs públicas (S13-012).
- [ ] `created_by_email_snapshot` en campaigns (S13-015).
- [ ] Documentar en CLAUDE.md que `contacts.attributes` no recibe PII altamente sensible (S13-013).

---

## Próximos pasos

1. Experto BD puede proceder con #158 (migración Python) sin cambios al DDL — los hallazgos son a nivel app.
2. Dev Plataforma arranca #159–#163 **incorporando el checklist anterior desde el primer commit**.
3. QA (#170) añade casos E2E de:
   - IDOR contra `/contacts/{id}`, `/campaigns/{id}`, `/templates/{id}` con `otro@test.com`.
   - Crear campaña con `template.status='PENDING'` → 400.
   - Importar CSV de 60 000 filas → 413.
   - POST `/meta/webhook` sin firma con `APP_ENV=prod` → 401.
4. Yo audito el código en #171 con este documento como checklist; cierro o reabro cada hallazgo. Sólo si quedan 0 Altos abiertos, se autoriza el deploy a RDS (#173).
