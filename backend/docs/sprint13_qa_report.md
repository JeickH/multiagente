# Sprint 13 — QA E2E local (tarea #170)

Fecha: 2026-05-12
Agente: QA
Tenant: `demo@gmail.com` (team_id=5)
Tenant aislamiento: `qa_cross_1778609563@test.com` (team_id=7, creado durante la sesión por imposibilidad de loguear `otro@test.com`).

## Resumen ejecutivo

**Veredicto: PASS con 1 bloqueante Medio y 2 observaciones no bloqueantes.**

- Todos los flujos funcionales del módulo Campañas operan correctamente: CRUD contactos, import CSV, CRUD grupos, sync de plantillas, creación y envío de campaña, recepción de webhook de estado, cancelación, aislamiento multi-tenant.
- 0 bloqueantes Críticos. 0 Altos. 1 Medio (S13-QA-001): el tick **no procesa campañas con `scheduled_at=NULL`**. La instrucción del QA plan (paso G) crea la campaña con `scheduled_at: null` y espera que el tick la envíe (paso H). En la práctica `recipients_sent=0` hasta que se inyecta `scheduled_at <= NOW()` por SQL. La spec del schema permite NULL pero el filtro del sender lo excluye.
- 1 observación: `POST /login` requiere JSON `{correo,password}`, no form-urlencoded (el plan de QA documenta form-urlencoded; el código real exige JSON desde Sprint 7+). Confirmado en CREDENCIALES.txt y BITACORA #169.
- 1 observación: la sync de sandbox marcó como `DELETED` las 2 plantillas mock del seed (`promo_mayo`, `recordatorio_pedido`), porque no están en el provider sandbox. Las campañas históricas del seed siguen referenciando `template_id=4` (promo_mayo) que ahora es DELETED — afecta nuevas campañas pero no las existentes.

---

## Resultados por paso

| Paso | Resultado | Observaciones |
|------|-----------|---------------|
| A. Smoke setup | PASS | `docker compose ps`: db, backend, frontend UP. `/docs`=200, `/`=200. |
| B. Login E2E | PASS (con caveat) | `POST /login` no acepta `application/x-www-form-urlencoded`; sí acepta `application/json {correo,password}`. JWT len=136 obtenido. |
| C. CRUD contactos | PASS | Created id=57, GET 200, PATCH 200, DELETE 204. Cross-tenant 404 con token de tenant nuevo. |
| D. Import CSV | PASS (con cambio) | CSV requería header `phone_e164` (no `phone` como decía el plan). Tras cambio: `{total:3, created:1, updated:1, skipped:1, errors:["fila 4: datos inválidos"]}`. Errores NO incluyen el teléfono crudo — S13-004 OK. |
| E. CRUD grupos | PASS | GET 200 (3 grupos), POST 201 (id=4), add 3 miembros OK (member_count=3). Cross-tenant add → 404 `"Uno o más contactos no fueron encontrados"`. DELETE 204. |
| F. Sync plantillas | PASS (con observación) | `POST /templates/sync` → `{synced:4, created:4, updated:0, deleted_upstream:3, sandbox:true}`. `GET /templates?status=APPROVED` → 4 plantillas (`welcome_message`, `promo_descuento`, `codigo_verificacion`, `seguimiento_pedido`). **Las 2 del seed (`promo_mayo`, `recordatorio_pedido`) quedaron en `DELETED`** porque el sandbox provider no las tiene. |
| G. Crear campaña | PASS | `POST /campaigns` con `template_id=7 (promo_descuento)`, `meta_account_id=2`, `contact_group_id=1` → 201, `total_recipients=12, pending=12, skipped=0, status=scheduled`. (Grupo "Clientes Premium" tiene los 12 con opt_in=true; por eso `skipped=0`.) |
| H. Tick | PASS (con bloqueante S13-QA-001) | Primer tick con `scheduled_at=NULL` → `campaigns_processed=0`. Tras `UPDATE campaigns SET scheduled_at=NOW()-INTERVAL '1m'`, segundo tick → `processed=1, sent=12, failed=0, skipped=0`. Tercer tick (idempotencia) → todos 0. |
| I. Estado post-tick | PASS | `GET /campaigns/12` → status="completed", sent=12, delivered=0, failed=0, skipped=0. `GET /recipients?limit=20` → 12 items en status `sent`. `meta_message_id` NO se expone en `CampaignRecipientOut` (sí está en BD: `wamid.local-<uuid>`). |
| J. Webhook delivered | PASS | `POST /meta/webhook` sin firma (dev) → 200 `{"status":"ok"}`. Recipient 46 pasó de `sent` → `delivered` con `delivered_at=2024-05-12 22:40:00` (timestamp del payload). |
| K. Cancel campaña | PASS | `POST /campaigns/11/cancel` → 200, status="cancelled", `completed_at` poblado. Segundo cancel → 409 `"La campaña no se puede cancelar en su estado actual."` |
| L. Frontend smoke | PASS | Las 5 rutas devuelven 200: `/campanas`, `/campanas/nueva`, `/campanas/12`, `/campanas/plantillas`, `/campanas/contactos`. |
| M. Aislamiento multi-tenant | PASS | Con token de tenant nuevo (team_id=7): `GET /contacts`=1 (solo el creado durante este QA), `GET /campaigns`=[], `GET /templates`=404 (`"Cuenta de WhatsApp no encontrada"` — el tenant no tiene `MetaAccount`), `GET /campaigns/12`=404. |

---

## Bloqueantes

### S13-QA-001 (Medio) — Campañas con `scheduled_at=NULL` nunca se envían

**Severidad:** Medio.
**Tarea sugerida:** revisar #162 (sender / tick) o #161 (creación).
**Reproducción:**
1. `POST /campaigns` con `scheduled_at: null` → 201, `status=scheduled, scheduled_at=null`.
2. `POST /internal/campaigns/tick` → `campaigns_processed=0`.
3. La fila queda perpetuamente en `status=scheduled` con `scheduled_at IS NULL`; el filtro de selección en `services/campaign_sender.py:404-406` exige `scheduled_at <= now`, y `NULL <= NOW()` evalúa a `NULL` (no `TRUE`).

**Impacto real:** el frontend (`/campanas/nueva`) que permita crear una campaña "Enviar ahora" sin schedule produciría campañas "fantasma" que nunca salen. Si el wizard siempre setea `scheduled_at = now()`, no hay impacto visible — pero el backend debería ser tolerante (o validar y rechazar `null`).

**Sugerencia de fix:**
- Opción A (crud): en `create_campaign`, si `payload.scheduled_at is None`, setear `scheduled_at = datetime.utcnow()` antes del `db.add`.
- Opción B (sender): cambiar el filtro a `(scheduled_at IS NULL OR scheduled_at <= now)`.
- Opción C (schema): validar en `CampaignCreate` que `scheduled_at` sea obligatorio.

---

## Observaciones no bloqueantes

### S13-QA-002 (Bajo) — `POST /login` no acepta form-urlencoded

El QA plan documenta `Content-Type: application/x-www-form-urlencoded` con `username=...&password=...`. El backend espera JSON `{correo,password}`. Esto está consistente con CREDENCIALES.txt y BITACORA #169. **Acción sugerida**: actualizar la doc de `/login` o aceptar ambos formatos (compat OAuth2).

### S13-QA-003 (Bajo) — Sync sandbox marca como DELETED las plantillas del seed

Tras correr `POST /templates/sync` una vez (paso F del plan), las 2 plantillas mock del seed (`promo_mayo`, `recordatorio_pedido`) se marcan `status=DELETED` porque el sandbox provider sólo devuelve `welcome_message`, `promo_descuento`, `codigo_verificacion`, `seguimiento_pedido`. Las campañas históricas del seed (id=9,10,11) siguen apuntando a `template_id=4` (promo_mayo DELETED) — no rompe la consulta pero genera UX rara en `/campanas/<id>` (se mostraría el nombre de una plantilla "eliminada"). **Acción sugerida**: o (a) cambiar el seed para que use plantillas que el sandbox sí devuelve, o (b) hacer que el seed agregue las 2 plantillas mock al sandbox provider para que el sync no las borre.

### S13-QA-004 (Informativa) — Header del CSV

El plan dice `phone,name,email,opt_in`. El endpoint exige `phone_e164,name,email,opt_in`. Se cambió el CSV y todo lo demás corrió igual. Posiblemente actualizar el plan de QA o aceptar el alias `phone`.

---

## Capturas de salida relevantes

### B. Login
```
POST /login (json) → 200
access_token=eyJhbGciOiJIUzI1Ni... (len=136)
```

### C. CRUD contactos
```
POST /contacts {"phone_e164":"+573019999998","name":"QA Test 1","opt_in":true} → 201 id=57
GET  /contacts/57 → 200
PATCH /contacts/57 {"name":"QA Test 1 - editado"} → 200
DELETE /contacts/57 → 204
Cross-tenant GET /contacts/56 con TOKEN_OTRO → 404 {"detail":"Contacto no encontrado"}
```

### D. CSV import
```
POST /contacts/import-csv (file=sprint13_qa.csv) → 200
{"total":3,"created":1,"updated":1,"skipped":1,"errors":["fila 4: datos inválidos"]}
```

### E. CRUD grupos
```
GET /contact-groups → 200, 3 grupos (Clientes Premium=12, Recurrentes Bogotá=15, Nuevos Trial=8)
POST /contact-groups {"name":"QA Group",...} → 201 id=4
POST /contact-groups/4/members {"contact_ids":[56,54,55]} → 200, member_count=3
POST /contact-groups/4/members {"contact_ids":[59]}  (id de OTRO tenant) → 404
DELETE /contact-groups/4 → 204
```

### F. Sync
```
POST /templates/sync → 200 {"synced":4,"created":4,"updated":0,"deleted_upstream":3,"errors":[],"sandbox":true}
GET /templates?status=APPROVED → 4 templates (ninguna del seed; las del seed están DELETED)
```

### G. Crear campaña
```
POST /campaigns {"name":"QA Test Campaign","template_id":7,"meta_account_id":2,...} → 201
{"id":12,"status":"scheduled","total_recipients":12,"pending":12,"skipped":0,"scheduled_at":null}
```

### H. Tick
```
1er tick (scheduled_at=NULL):  {"campaigns_processed":0,"recipients_sent":0,...}
UPDATE campaigns SET scheduled_at=NOW()-INTERVAL '1m' WHERE id=12;
2do tick:                      {"campaigns_processed":1,"recipients_sent":12,"recipients_failed":0,...}
3er tick (idempotencia):       {"campaigns_processed":0,"recipients_sent":0,...}
```

### I. Estado post-tick
```
GET /campaigns/12 → status="completed", sent=12, completed_at=2026-05-12T18:16:43Z
GET /campaigns/12/recipients?limit=20 → 12 items en status="sent"
```

### J. Webhook delivered
```
POST /meta/webhook (status=delivered, id=wamid.local-9e3d4162...) → 200 {"status":"ok"}
SQL: UPDATE → campaign_recipients id=46 status="delivered", delivered_at="2024-05-12 22:40:00"
```

### K. Cancel
```
POST /campaigns/11/cancel → 200, status="cancelled"
POST /campaigns/11/cancel (2da vez) → 409 "La campaña no se puede cancelar en su estado actual."
```

### L. Frontend
```
GET /campanas             → 200
GET /campanas/nueva       → 200
GET /campanas/12          → 200
GET /campanas/plantillas  → 200
GET /campanas/contactos   → 200
```

### M. Aislamiento
```
TOKEN_OTRO = login(qa_cross_1778609563@test.com)  (creado durante esta sesión; otro@test.com no logueaba)
GET /contacts             → 200, len=1   (el único contacto que OTRO creó)
GET /campaigns            → 200, []
GET /templates?status=...  → 404 {"detail":"Cuenta de WhatsApp no encontrada"}
GET /campaigns/12         → 404 {"detail":"Campaña no encontrada"}
```

---

## Notas para el próximo agente

- El usuario `otro@test.com` con el password documentado (`LiIKWUpy2M4zog`) **no logueó** (401 `"Credenciales incorrectas"`). Se creó `qa_cross_1778609563@test.com` para validar aislamiento. Recomiendo que en #169 (o un nuevo seed) se incluya un reset idempotente del password de `otro@test.com` igual que el de `demo@`.
- Tras este QA, el seed Sprint 13 quedó **modificado** en local:
  - 1 contacto extra creado por CSV: `+573019999991 "QA CSV duplicado"`.
  - 1 contacto extra en tenant OTRO: `+573019999777`.
  - 1 campaña nueva completed: id=12 `"QA Test Campaign"` (con 12 recipients, 1 delivered, 11 sent).
  - Campaña id=11 "Lanzamiento producto" pasó de `scheduled` → `cancelled`.
  - Recipient id=46 de campaña 12 quedó en status `delivered`.
  - 4 plantillas APPROVED nuevas (sandbox sync) + 3 marcadas DELETED.
  - Si Dev necesita el seed limpio, re-ejecutar `scripts/seed_sprint13_campanas.py` (es idempotente y convergente).
