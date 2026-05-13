# Sprint 13 — Schema de BD: Campañas + Plantillas WhatsApp + Contactos/Grupos

**Autor**: Experto BD
**Fecha**: 2026-05-11
**Estado**: Diseño congelado, listo para revisión de Seguridad (tarea #157) y migración Python (tarea #158).
**Target**: PostgreSQL 15 (local docker-compose `db` + RDS `multiagente-db` en `sa-east-1`).

Este documento contiene:

1. DDL completo, idempotente, ejecutable (7 tablas nuevas).
2. Decisiones de diseño (multi-tenant, PII, idempotencia, cache de plantillas, plan de migración).
3. Queries SQL agregadas para los KPIs del dashboard.

Las decisiones de fondo (qué tablas, qué columnas) ya están aprobadas en `BITACORA.md` →
sección "Cambios de BD del Sprint 13 (descripción detallada)". Este documento las
refina, las traduce a DDL ejecutable, y documenta refinamientos (ver §2.6).

---

## 1. DDL ejecutable (PostgreSQL 15)

> Orden de creación obligatorio por dependencias de FK:
> `contacts` → `contact_groups` → `contact_group_members` → `whatsapp_templates` →
> `campaigns` → `campaign_recipients` → `campaign_events`.

Todo el DDL es **idempotente** (`IF NOT EXISTS`), por lo que se puede correr varias
veces sin efecto. El script Python de la tarea #158 lo aplicará vía `SQLAlchemy.text()`
en una sola transacción.

### 1.1 `contacts`

```sql
CREATE TABLE IF NOT EXISTS contacts (
    id              SERIAL       PRIMARY KEY,
    team_id         INTEGER      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    phone_e164      VARCHAR(20)  NOT NULL,
    name            VARCHAR(120),
    email           VARCHAR(255),
    attributes      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    opt_in          BOOLEAN      NOT NULL DEFAULT TRUE,
    opt_in_source   VARCHAR(50),
    created_at      TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_contacts_team_phone UNIQUE (team_id, phone_e164),
    CONSTRAINT ck_contacts_phone_e164 CHECK (phone_e164 ~ '^\+[1-9][0-9]{6,18}$')
);

CREATE INDEX IF NOT EXISTS ix_contacts_team_id        ON contacts(team_id);
CREATE INDEX IF NOT EXISTS ix_contacts_team_name      ON contacts(team_id, name);
CREATE INDEX IF NOT EXISTS ix_contacts_attributes_gin ON contacts USING GIN (attributes);
```

**Refinamientos vs. BITACORA**:
- `attributes` con `DEFAULT '{}'::jsonb NOT NULL` (BITACORA decía `JSONB` sin default;
  un objeto vacío es más cómodo que `NULL` para el frontend y permite `?` operadores
  sin coalesce).
- Añadido `CHECK` regex para E.164 (defensa-en-profundidad; el backend ya valida,
  pero esto evita data sucia si se inserta por psql).
- Añadido índice GIN en `attributes` para soportar segmentación futura
  (`WHERE attributes @> '{"vip": true}'`). Barato y opcional.
- Añadido índice `(team_id, name)` para autocompletado del wizard "agregar destinatarios
  uno-a-uno" (buscar por nombre dentro del team).

### 1.2 `contact_groups`

```sql
CREATE TABLE IF NOT EXISTS contact_groups (
    id           SERIAL       PRIMARY KEY,
    team_id      INTEGER      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name         VARCHAR(120) NOT NULL,
    description  TEXT,
    created_at   TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_contact_groups_team_name UNIQUE (team_id, name)
);

CREATE INDEX IF NOT EXISTS ix_contact_groups_team_id ON contact_groups(team_id);
```

### 1.3 `contact_group_members`

```sql
CREATE TABLE IF NOT EXISTS contact_group_members (
    group_id    INTEGER     NOT NULL REFERENCES contact_groups(id) ON DELETE CASCADE,
    contact_id  INTEGER     NOT NULL REFERENCES contacts(id)       ON DELETE CASCADE,
    added_at    TIMESTAMP   NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, contact_id)
);

CREATE INDEX IF NOT EXISTS ix_contact_group_members_contact ON contact_group_members(contact_id);
```

**Nota multi-tenant**: la integridad team-cruzada (`group.team_id == contact.team_id`)
**no** se enforcer a nivel DDL — sería un CHECK con subconsulta, costoso. El backend
debe validar en el endpoint `POST /contact-groups/{id}/members` que el contacto pertenezca
al mismo team que el grupo. Ver §2.1.

### 1.4 `whatsapp_templates`

```sql
CREATE TABLE IF NOT EXISTS whatsapp_templates (
    id                 SERIAL       PRIMARY KEY,
    meta_account_id    INTEGER      NOT NULL REFERENCES meta_accounts(id) ON DELETE CASCADE,
    meta_template_id   VARCHAR(64),
    name               VARCHAR(120) NOT NULL,
    category           VARCHAR(40),
    language           VARCHAR(20)  NOT NULL,
    status             VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    components_json    JSONB        NOT NULL,
    rejection_reason   TEXT,
    last_synced_at     TIMESTAMP,
    created_at         TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_templates_account_name_lang UNIQUE (meta_account_id, name, language),
    CONSTRAINT ck_templates_status CHECK (
        status IN ('PENDING','APPROVED','REJECTED','DISABLED','PAUSED','DELETED')
    ),
    CONSTRAINT ck_templates_category CHECK (
        category IS NULL OR category IN ('MARKETING','UTILITY','AUTHENTICATION')
    )
);

CREATE INDEX IF NOT EXISTS ix_templates_account_status ON whatsapp_templates(meta_account_id, status);
CREATE INDEX IF NOT EXISTS ix_templates_meta_template  ON whatsapp_templates(meta_template_id);
CREATE INDEX IF NOT EXISTS ix_templates_pending_sync   ON whatsapp_templates(last_synced_at)
    WHERE status = 'PENDING';
```

**Refinamientos vs. BITACORA**:
- Añadido valor `'DELETED'` al CHECK de `status`. Cuando Meta borra una plantilla,
  no la eliminamos físicamente (rompería FK desde `campaigns` históricas); la
  marcamos `'DELETED'` y bloqueamos su uso para campañas nuevas en el backend.
- Añadidos CHECKs de `status` y `category` (defensa-en-profundidad, valores cerrados).
- Índice **parcial** `WHERE status = 'PENDING'` para el scheduler-tick de 30min:
  sólo recorre las plantillas que efectivamente está esperando respuesta de Meta.
  Mucho más barato que `ix_templates_account_status` para esta query específica.
- Índice en `meta_template_id` (sin UNIQUE — puede ser NULL antes del primer sync).

### 1.5 `campaigns`

```sql
CREATE TABLE IF NOT EXISTS campaigns (
    id                        SERIAL       PRIMARY KEY,
    team_id                   INTEGER      NOT NULL REFERENCES teams(id)              ON DELETE CASCADE,
    meta_account_id           INTEGER      NOT NULL REFERENCES meta_accounts(id)      ON DELETE RESTRICT,
    template_id               INTEGER      NOT NULL REFERENCES whatsapp_templates(id) ON DELETE RESTRICT,
    name                      VARCHAR(120) NOT NULL,
    status                    VARCHAR(20)  NOT NULL DEFAULT 'draft',
    scheduled_at              TIMESTAMP,
    started_at                TIMESTAMP,
    completed_at              TIMESTAMP,
    template_variables_json   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id        INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    created_at                TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT ck_campaigns_status CHECK (
        status IN ('draft','scheduled','running','completed','failed','cancelled')
    )
);

CREATE INDEX IF NOT EXISTS ix_campaigns_team_status         ON campaigns(team_id, status);
CREATE INDEX IF NOT EXISTS ix_campaigns_status_scheduled    ON campaigns(status, scheduled_at)
    WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS ix_campaigns_team_created        ON campaigns(team_id, created_at DESC);
```

**Refinamientos vs. BITACORA**:
- `created_by_user_id`: cambiado de `INT FK users(id)` (sin acción) a
  `ON DELETE SET NULL`. Justificación: si borramos un usuario que creó una campaña
  hace 6 meses, no queremos perder la campaña histórica ni romper el delete del
  usuario. Bitácora se mantiene gracias al snapshot en `campaign_recipients`.
- `template_variables_json` con DEFAULT `'{}'` NOT NULL (mismo motivo que en contacts).
- Índice `(status, scheduled_at) WHERE status='scheduled'` parcial: el tick del
  scheduler `WHERE status='scheduled' AND scheduled_at <= now()` lo aprovecha;
  evita escanear miles de campañas `completed`.
- Índice `(team_id, created_at DESC)` para la query del dashboard "últimas N
  campañas del team ordenadas por fecha".

### 1.6 `campaign_recipients`

```sql
CREATE TABLE IF NOT EXISTS campaign_recipients (
    id                SERIAL       PRIMARY KEY,
    campaign_id       INTEGER      NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    contact_id        INTEGER      NOT NULL REFERENCES contacts(id)  ON DELETE RESTRICT,
    phone_e164        VARCHAR(20)  NOT NULL,
    meta_message_id   VARCHAR(80),
    status            VARCHAR(20)  NOT NULL DEFAULT 'queued',
    error_code        VARCHAR(40),
    sent_at           TIMESTAMP,
    delivered_at      TIMESTAMP,
    read_at           TIMESTAMP,
    failed_at         TIMESTAMP,
    CONSTRAINT uq_recipients_campaign_contact   UNIQUE (campaign_id, contact_id),
    CONSTRAINT uq_recipients_meta_message_id    UNIQUE (meta_message_id),
    CONSTRAINT ck_recipients_status CHECK (
        status IN ('queued','sending','sent','delivered','read','failed','skipped')
    )
);

CREATE INDEX IF NOT EXISTS ix_recipients_meta_message_id ON campaign_recipients(meta_message_id);
CREATE INDEX IF NOT EXISTS ix_recipients_campaign_status ON campaign_recipients(campaign_id, status);
```

**Refinamientos vs. BITACORA**:
- `meta_message_id`: añadido **UNIQUE** además del índice. BITACORA pedía sólo
  índice, pero la idempotencia del webhook depende de que un `wamid` mapée a
  **exactamente uno** o **cero** recipients (ver §2.3). El UNIQUE incluye `NULL`s
  (Postgres trata NULLs como distintos), así que recipients aún `queued` sin wamid
  conviven bien.
- Añadido valor `'skipped'` al CHECK de `status` para casos donde el contacto no
  tiene `opt_in=TRUE` o el `phone_e164` resultó inválido en el momento del envío.

### 1.7 `campaign_events`

```sql
CREATE TABLE IF NOT EXISTS campaign_events (
    id                SERIAL       PRIMARY KEY,
    campaign_id       INTEGER      NOT NULL REFERENCES campaigns(id)            ON DELETE CASCADE,
    recipient_id      INTEGER               REFERENCES campaign_recipients(id)  ON DELETE CASCADE,
    event_type        VARCHAR(30)  NOT NULL,
    payload_json      JSONB,
    meta_message_id   VARCHAR(80),
    created_at        TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT ck_events_type CHECK (
        event_type IN ('queued','sent','delivered','read','failed','clicked','sync_warning')
    )
);

CREATE INDEX IF NOT EXISTS ix_events_campaign_type      ON campaign_events(campaign_id, event_type);
CREATE INDEX IF NOT EXISTS ix_events_meta_message_id    ON campaign_events(meta_message_id);
CREATE INDEX IF NOT EXISTS ix_events_campaign_created   ON campaign_events(campaign_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_dedupe
    ON campaign_events(meta_message_id, event_type)
    WHERE meta_message_id IS NOT NULL;
```

**Refinamientos vs. BITACORA**:
- Añadido `event_type='sync_warning'` para errores de sincronización (ej. plantilla
  rechazada por Meta) — útiles en la auditoría pero no son eventos de un wamid
  concreto.
- Añadido **UNIQUE INDEX parcial** `(meta_message_id, event_type) WHERE meta_message_id IS NOT NULL`.
  Bitácora dijo "dedupe en `campaign_events`" pero no especificó cómo: este índice
  parcial garantiza que un mismo wamid+event_type sólo entre una vez (el webhook
  de Meta a veces reentrega), sin bloquear los eventos `sync_warning` que no tienen
  wamid asociado.
- Índice `(campaign_id, created_at DESC)` para timeline en el detalle de campaña.

---

## 2. Decisiones documentadas

### 2.1 Multi-tenancy

**Patrón**: igual al ya consolidado en `conversations`/`messages`. Toda fila con
datos del cliente lleva `team_id` (directo o transitivo) y FK `ON DELETE CASCADE`
hacia `teams`. Si se borra un team se va todo lo suyo.

| Tabla | team_id | Cómo se obtiene |
|-------|---------|-----------------|
| `contacts` | directo | columna `team_id` |
| `contact_groups` | directo | columna `team_id` |
| `contact_group_members` | transitivo | `JOIN contact_groups ON group_id` |
| `whatsapp_templates` | transitivo | `JOIN meta_accounts ON meta_account_id` |
| `campaigns` | directo | columna `team_id` |
| `campaign_recipients` | transitivo | `JOIN campaigns ON campaign_id` |
| `campaign_events` | transitivo | `JOIN campaigns ON campaign_id` |

**Reglas para el Dev Plataforma (endpoints)**:

1. **Toda query** parte de `team_id = current_user.team.id` (resuelto vía dependencia
   FastAPI). Nunca aceptamos `team_id` desde el body/query del cliente.
2. **Verificación cruzada** en operaciones que mezclan recursos:
   - `POST /contact-groups/{group_id}/members` con body `{contact_id}`:
     verificar `group.team_id == contact.team_id == current_user.team.id`.
   - `POST /campaigns` con `template_id`, `recipients[]`: verificar que el template
     pertenece al `meta_account` del team y que cada `contact_id` está dentro del team.
3. **404, no 403**, ante recursos de otro team. No revelamos existencia.
4. **No hay endpoints "admin global"** que crucen teams. Si se necesitan en el
   futuro (soporte), se diseñan aparte con auth diferenciada.

### 2.2 PII (números, nombres, emails)

Aplica regla 2 de Seguridad de `CLAUDE.md`. Los siguientes campos son PII y reciben
trato especial:

- `contacts.phone_e164`, `contacts.name`, `contacts.email`
- `campaign_recipients.phone_e164`
- `campaign_events.payload_json` (puede contener números y mensajes del cliente)

**Reglas**:

1. **`__repr__` redactado** en los modelos SQLAlchemy `Contact`, `CampaignRecipient`,
   `CampaignEvent`. El número se enmascara como `+57***1234` (4 últimos dígitos),
   el email como `m***@dominio.com`, el `payload_json` se omite por completo.
   El logger nunca debe imprimir el objeto entero (`logger.info(contact)` → redactado).
2. **Schemas Pydantic `...Out`**:
   - `ContactOut` puede incluir `phone_e164` y `name` porque es lo que se muestra al
     usuario dueño del team. **No** se expone vía endpoints públicos/no autenticados.
   - `CampaignRecipientOut` incluye `phone_e164` por el mismo motivo (el dueño del
     team lo necesita en el detalle de campaña).
   - `CampaignEventOut` **no** expone `payload_json` por defecto. Lo expone sólo en
     un endpoint específico `GET /campaigns/{id}/events/{event_id}/payload` con un
     extra guard (sólo `role='owner'` o permiso `can_view_raw_payload`). Para
     listados normales se devuelve un resumen.
3. **Import CSV**: el endpoint de importación no debe loggear el contenido del CSV.
   Si falla parsing, log con `logger.exception("CSV parse failed at row N")` sin
   imprimir el row.
4. **Webhook de Meta**: ya está cubierto por `meta_webhook.py` (regla 6 — errores
   sanitizados al cliente). El `payload_json` que se guarda en `campaign_events`
   se persiste por trazabilidad pero **nunca** se devuelve en respuestas hacia
   `webhook.meta.*` (Meta solo necesita 200 OK).

### 2.3 Idempotencia del webhook

Meta puede reentregar el mismo evento varias veces (especificación oficial). Sin
idempotencia, un mensaje "entregado" se contaría 3 veces. Mecanismo:

1. **Correlación**: el webhook recibe `wamid` (Meta message id). Lookup:
   ```sql
   SELECT id, campaign_id, status FROM campaign_recipients
   WHERE meta_message_id = :wamid;
   ```
   Si no hay match → el wamid es de una conversación 1-a-1 (router antiguo), se
   delega al handler de mensajes. Si hay match → es de campaña.
2. **Dedupe nivel recipient**: el `UPDATE` de `campaign_recipients` es idempotente
   por construcción: setea `delivered_at` solo si era NULL. Volverlo a aplicar no
   cambia datos.
3. **Dedupe nivel evento**: `UNIQUE (meta_message_id, event_type) WHERE meta_message_id IS NOT NULL`
   en `campaign_events`. El `INSERT` usa `ON CONFLICT DO NOTHING`. Reentregas no
   duplican filas.
4. **`meta_message_id UNIQUE` en `campaign_recipients`**: garantiza que un wamid
   pertenece a **un solo** recipient. Si el sender intentara reusar un wamid por
   bug, el constraint lo bloquea explícitamente.

### 2.4 Cache de plantillas Meta

Plantillas son un recurso de Meta. Sincronización:

1. **Lazy + explícita**: al entrar a `/campanas/plantillas`, el frontend pega a
   `POST /templates/sync?meta_account_id=X` que trae todo el listado. TTL "fresco"
   = 15 min (si `last_synced_at < 15min`, devolvemos el cache sin pegar a Meta).
2. **Refresh on demand**: botón "Refrescar" en la UI ignora el TTL.
3. **Scheduler para PENDING**: el `bot_scheduler` ya corre cada N minutos
   (`/internal/bot-scheduler/tick`). Añadimos un sub-tick `templates_pending_sync`
   que busca:
   ```sql
   SELECT id, meta_account_id, meta_template_id FROM whatsapp_templates
   WHERE status = 'PENDING'
     AND (last_synced_at IS NULL OR last_synced_at < now() - interval '30 minutes');
   ```
   El índice parcial `ix_templates_pending_sync` la hace trivial.
4. **Borrados upstream**: si Meta deja de devolver una plantilla que sí teníamos
   localmente, **no** la borramos físicamente (rompería FK de `campaigns` históricas).
   La marcamos `status='DELETED'` y emitimos un `campaign_events(event_type='sync_warning')`
   asociado a las campañas que la usaban (si existían y aún estaban en draft).
5. **Crear plantilla local**: al crear, primero `POST` a Meta. Sólo si Meta responde
   200 guardamos la fila con `status='PENDING'` y `last_synced_at=now()`. Si Meta
   falla, no persistimos nada (no queremos plantillas fantasma).
6. **Sólo `APPROVED` se puede usar en campañas**: validado en el endpoint
   `POST /campaigns` antes de crear filas. Bloqueo a nivel app, **no** a nivel DDL
   (un CHECK con subconsulta es prohibitivamente caro).

### 2.5 Plan de migración

Orden de aplicación (idempotente, una sola transacción):

1. `contacts`
2. `contact_groups`
3. `contact_group_members` (depende de 1 y 2)
4. `whatsapp_templates` (depende de `meta_accounts`, que ya existe)
5. `campaigns` (depende de 1, 4 y `meta_accounts`)
6. `campaign_recipients` (depende de 1 y 5)
7. `campaign_events` (depende de 5 y 6)
8. Índices (todos al final, después de los CREATE TABLE).

**Fase 2 (tarea #158)** — Script Python `backend/scripts/migrate_sprint13_campanas.py`:
- Patrón conocido (ver `migrate_sprint10_bot_sessions.py`, `migrate_sprint11_leads.py`).
- `with engine.begin() as conn: conn.execute(text(DDL))` para que todo o nada.
- Idempotente por las cláusulas `IF NOT EXISTS`.
- Aplicar **primero en local** (docker-compose `db`) + commit del log.

**Fase 10 (tarea #173)** — Replicación a RDS:
- `aws ecs run-task --region sa-east-1 --task-definition multiagente-backend:N`
  con `containerOverrides.command = ["python", "scripts/migrate_sprint13_campanas.py"]`.
- Validar con `psql` sobre el endpoint RDS que las 7 tablas existan y que
  `SELECT count(*) FROM information_schema.tables WHERE table_name IN (...)` = 7.
- Adjuntar la salida de ECS en el checkpoint de la tarea #173 (regla de paridad BD).

**Riesgo de rollback**: ninguno. Las 7 tablas son nuevas, no alteran nada existente.
Si algo sale mal: `DROP TABLE ... CASCADE` en orden inverso. (No es lo ideal pero
es seguro porque no hay datos productivos aún).

### 2.6 Resumen de refinamientos vs. diseño original en BITACORA

| # | Refinamiento | Justificación |
|---|-------------|---------------|
| R1 | `JSONB DEFAULT '{}'::jsonb NOT NULL` para `contacts.attributes` y `campaigns.template_variables_json` | Simplifica el código backend y JSON `?` ops |
| R2 | `CHECK (phone_e164 ~ '^\+...')` en `contacts` | Defensa-en-profundidad |
| R3 | `CHECK` valores cerrados en `status` y `category` de `whatsapp_templates`, `campaigns`, `campaign_recipients`, `campaign_events` | Idem |
| R4 | Valor `'DELETED'` añadido al CHECK de `whatsapp_templates.status` | Soporta borrados upstream sin romper FKs |
| R5 | Valor `'skipped'` añadido a `campaign_recipients.status` | Caso opt-in=false o phone inválido en envío |
| R6 | Valor `'sync_warning'` añadido a `campaign_events.event_type` | Trazabilidad de errores de sync |
| R7 | `meta_message_id UNIQUE` en `campaign_recipients` (no sólo índice) | Idempotencia estricta del webhook |
| R8 | `UNIQUE (meta_message_id, event_type) WHERE meta_message_id IS NOT NULL` en `campaign_events` | Dedupe de reentregas de Meta |
| R9 | `campaigns.created_by_user_id` con `ON DELETE SET NULL` | Preservar histórico de campañas al borrar usuarios |
| R10 | Índice parcial `ix_templates_pending_sync` | Optimiza scheduler tick de 30min |
| R11 | Índice parcial `ix_campaigns_status_scheduled` | Optimiza scheduler tick de envíos agendados |
| R12 | Índice GIN en `contacts.attributes` | Soporta segmentación por atributo |
| R13 | Índice `(team_id, name)` en `contacts` | Autocompletado en wizard |
| R14 | Índice `(campaign_id, created_at DESC)` en `campaign_events` | Timeline en detalle de campaña |
| R15 | Integridad team-cruzada no enforce a nivel DDL | Costo de CHECK con subconsulta; se enforce en endpoint |

---

## 3. Queries de KPIs (para Dev Plataforma)

> Todas asumen un parámetro `:team_id` (filtro tenant obligatorio) y opcionalmente
> rangos de fecha `:date_from` / `:date_to`. Los nombres de columna están pensados
> para que SQLAlchemy las exponga directo (`.mappings()`).

### 3.1 KPIs globales del team — para el dashboard `/campanas`

```sql
-- Métricas agregadas sobre todas las campañas del team en un rango de fechas.
SELECT
    COUNT(DISTINCT c.id)                                                                AS total_campaigns,
    COUNT(cr.id)                                                                        AS total_recipients,
    COUNT(*) FILTER (WHERE cr.status IN ('sent','delivered','read'))                    AS sent_count,
    COUNT(*) FILTER (WHERE cr.status IN ('delivered','read'))                           AS delivered_count,
    COUNT(*) FILTER (WHERE cr.status = 'read')                                          AS read_count,
    COUNT(*) FILTER (WHERE cr.status = 'failed')                                        AS failed_count,
    COUNT(*) FILTER (WHERE cr.status = 'queued')                                        AS queued_count,
    COUNT(*) FILTER (WHERE cr.status = 'skipped')                                       AS skipped_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE cr.status IN ('delivered','read'))::numeric
        / NULLIF(COUNT(*) FILTER (WHERE cr.status IN ('sent','delivered','read')), 0),
        2
    )                                                                                   AS delivery_rate_pct,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE cr.status = 'read')::numeric
        / NULLIF(COUNT(*) FILTER (WHERE cr.status IN ('delivered','read')), 0),
        2
    )                                                                                   AS read_rate_pct
FROM campaigns c
LEFT JOIN campaign_recipients cr ON cr.campaign_id = c.id
WHERE c.team_id = :team_id
  AND c.created_at >= :date_from
  AND c.created_at <  :date_to;
```

Índices que la sirven: `ix_campaigns_team_status`, `ix_recipients_campaign_status`.

### 3.2 KPIs por campaña — para el detalle `/campanas/[id]`

```sql
-- Funnel completo de una campaña: queued → sent → delivered → read, + failed.
SELECT
    c.id                                                                                AS campaign_id,
    c.name                                                                              AS campaign_name,
    c.status                                                                            AS campaign_status,
    c.scheduled_at,
    c.started_at,
    c.completed_at,
    COUNT(cr.id)                                                                        AS total_recipients,
    COUNT(*) FILTER (WHERE cr.status = 'queued')                                        AS queued,
    COUNT(*) FILTER (WHERE cr.status = 'sending')                                       AS sending,
    COUNT(*) FILTER (WHERE cr.status IN ('sent','delivered','read'))                    AS sent,
    COUNT(*) FILTER (WHERE cr.status IN ('delivered','read'))                           AS delivered,
    COUNT(*) FILTER (WHERE cr.status = 'read')                                          AS read_count,
    COUNT(*) FILTER (WHERE cr.status = 'failed')                                        AS failed,
    COUNT(*) FILTER (WHERE cr.status = 'skipped')                                       AS skipped
FROM campaigns c
LEFT JOIN campaign_recipients cr ON cr.campaign_id = c.id
WHERE c.id = :campaign_id
  AND c.team_id = :team_id
GROUP BY c.id;
```

Índice que la sirve: PK + `ix_recipients_campaign_status`.

### 3.3 Top plantillas más usadas — extra para insights

```sql
-- Las 10 plantillas con más uso (cantidad de campañas + total de envíos exitosos).
SELECT
    t.id                                                                                AS template_id,
    t.name                                                                              AS template_name,
    t.language,
    t.category,
    COUNT(DISTINCT c.id)                                                                AS campaigns_using,
    COUNT(cr.id) FILTER (WHERE cr.status IN ('sent','delivered','read'))                AS successful_sends
FROM whatsapp_templates t
JOIN campaigns           c  ON c.template_id = t.id
LEFT JOIN campaign_recipients cr ON cr.campaign_id = c.id
WHERE t.meta_account_id IN (SELECT id FROM meta_accounts WHERE team_id = :team_id)
GROUP BY t.id, t.name, t.language, t.category
ORDER BY successful_sends DESC NULLS LAST
LIMIT 10;
```

Índices que la sirven: `ix_templates_account_status`, `ix_campaigns_team_status`.

### 3.4 Contactos sin grupo — extra para limpieza del directorio

```sql
-- Contactos del team que no pertenecen a ningún grupo (huérfanos).
SELECT
    ct.id,
    ct.phone_e164,
    ct.name,
    ct.email,
    ct.created_at
FROM contacts ct
WHERE ct.team_id = :team_id
  AND NOT EXISTS (
      SELECT 1 FROM contact_group_members m WHERE m.contact_id = ct.id
  )
ORDER BY ct.created_at DESC;
```

Índices que la sirven: `ix_contacts_team_id`, `ix_contact_group_members_contact`.

---

## 4. Próximos pasos

1. **Tarea #157** — Seguridad revisa este documento (foco: §2.1, §2.2, §2.3, §2.4).
   Hallazgos Críticos o Altos son bloqueantes antes de proceder.
2. **Tarea #158** — Experto BD escribe `backend/scripts/migrate_sprint13_campanas.py`
   con el DDL de §1, lo aplica en docker-compose `db`, commitea evidencia.
3. **Tarea #159+** — Dev Plataforma implementa modelos SQLAlchemy en `models.py`
   replicando este DDL (mismas columnas, mismas constraints, `__repr__` redactado
   según §2.2).
4. **Tarea #173** — Deploy AWS aplica la misma migración en RDS vía `ecs run-task`.
