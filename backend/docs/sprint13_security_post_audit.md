# Sprint 13 — Auditoría de Seguridad Post-Código

**Agente**: Seguridad (ejecutado por PM inline tras corte de uso del subagente).
**Fecha**: 2026-05-12
**Alcance**: código del módulo Campañas + Plantillas WhatsApp + Contactos/Grupos.

## Veredicto

**APROBADO** — todos los hallazgos del diseño (S13-001 a S13-015) están mitigados en código y un hallazgo nuevo detectado durante esta auditoría (S13-016, **Alto**) fue corregido inline antes de cerrar el dictamen. **Deploy a RDS/ECS (tareas #173/#174) autorizado**.

## Estado de mitigaciones del diseño (S13-001 a S13-015)

| ID | Severidad original | Estado | Evidencia (archivo:línea o función) |
|---|---|---|---|
| S13-001 IDOR cross-tenant | Alto | ✅ Mitigado | `routers/{contacts,templates,campaigns}.py` aplican `Depends(get_current_user)` y filtran por `team_id`/`meta_account_id` resuelto vía team. `crud.create_campaign` valida cadena `template ↔ meta_account ↔ team` + `COUNT(*) WHERE id IN(?) AND team_id=?` para cada `contact_id` y resuelve `contact_group` por team. 404 (no 403) en todos los casos. Verificado E2E en #170 paso C.6 y M. |
| S13-002 Anti-abuso envío | Alto | ✅ Mitigado | `crud.py:1335-1340` aplica `MAX_RECIPIENTS_PER_CAMPAIGN=10000` ANTES del INSERT, devolviendo 422. `services/campaign_sender.py` implementa `_TokenBucket` por `meta_account_id` (default 10 rps, env `META_RATE_LIMIT_RPS`). `tenacity` con `wait_exponential_jitter` 1-8s + `stop_after_attempt(3)` sobre HTTP 429 y códigos Meta 80007/131056. Rate-limit en `routers/templates.py POST /templates/sync` 1/60s/user en memoria — **caveat documentado**: no es cross-process; si se escala >1 réplica ECS, migrar a Redis. |
| S13-003 Opt-in fail-closed | Alto | ✅ Mitigado | **Doble barrera**. Al encolar: `crud.py:1369-1381` carga contactos y los `opt_in=False` se insertan con `status='skipped', error_code='opt_out_at_enqueue'`. Al enviar: `services/campaign_sender.py:467-484` re-lookup de `contact.opt_in`; si cambió a False entre encolar y enviar → `status='skipped', error_code='opt_out_at_send'` + evento `sync_warning`. Verificado en #170 paso G (campaña con opt-out devuelve `skipped=N`). |
| S13-004 Logging webhook con PII | Alto | ✅ Mitigado | `routers/meta_webhook.py:118-137` `_sanitize_payload_for_log()` recursivo: enmascara teléfonos E.164 con regex + redacta por nombre de campo (`phone_e164`, `from`, `wa_id`, `recipient_id`, `display_phone`). Aplicado en `logger.info` línea 427. Payload bruto persiste sólo en `campaign_events.payload_json` (BD, no logs). En `routers/contacts.py POST /import-csv` los errores devueltos al cliente no contienen el teléfono crudo (verificado #170 paso D). |
| S13-005 HMAC fail-closed en prod | Alto | ✅ Mitigado | `routers/meta_webhook.py:179-216` `_verify_signature`: `APP_ENV=production` + sin `META_APP_SECRET` → `False` + `logger.error`. Prod + firma ausente → `False`. Dev sin secret → `True` + `logger.warning("FAIL-OPEN ...")`. Endpoint responde 403 en prod, 401 en dev. |
| S13-006 Sanitización `rejection_reason` | Medio | ✅ Mitigado | `schemas.py:404-412` `_sanitize_rejection_reason()` strip HTML tags + truncate 500 chars antes de salir en `WhatsappTemplateOut`. Crudo persiste en BD para auditoría. |
| S13-007 Errores Meta sanitizados | Medio | ✅ Mitigado | `services/meta_templates.py` y `campaign_sender.py`: errores Meta loggean detalle vía `logger.exception` server-side; al cliente sólo mensaje genérico. Verificado en routers que envuelven con `try/except HTTPException(status, "...generic...")`. |
| S13-008 Rate-limit sync templates | Medio | ✅ Mitigado | `routers/templates.py POST /templates/sync` 1/60s/user en memoria. Devuelve 429 con `Retry-After`. UI también throttlea cliente 60s. |
| S13-009 Errores CSV sin PII | Medio | ✅ Mitigado | `crud.py import_contacts_csv` formatea errores como `"fila N: <motivo>"` sin echo del teléfono. Verificado E2E #170 paso D. |
| S13-010 Schemas Out sin `MetaAccount` embebido | Medio | ✅ Mitigado | `WhatsappTemplateOut` expone sólo `meta_account_id: int`, no la relación con token. `CampaignOut` y `CampaignDetailOut` igual. Inspección manual confirmó que ningún schema `...Out` del Sprint 13 expone `encrypted_access_token`, `hashed_password`, ni `app_secret` directa o transitivamente. |
| S13-011 `extra='forbid'` en payloads Pydantic | Bajo | ✅ Mitigado | Schemas Sprint 13 declaran `model_config = ConfigDict(extra="forbid")` para rechazar campos desconocidos. |
| S13-012 `__repr__` redactado | Bajo | ✅ Mitigado | `Contact.__repr__`, `CampaignRecipient.__repr__`, `WhatsappTemplate.__repr__` redactan PII/secretos. |
| S13-013 FK `ON DELETE` adecuado | Bajo | ✅ Mitigado | `campaigns.created_by_user_id ON DELETE SET NULL`, `campaigns.template_id ON DELETE RESTRICT` (preserva histórico), `campaign_recipients.contact_id ON DELETE RESTRICT` (snapshot), demás CASCADE donde corresponde. |
| S13-014 Índices parciales para schedulers | Bajo | ✅ Mitigado | `ix_templates_pending_sync WHERE status='PENDING'` y `ix_campaigns_status_scheduled WHERE status='scheduled'` aplicados por #158. |
| S13-015 Dedupe webhook | Bajo | ✅ Mitigado | UNIQUE parcial `uq_events_dedupe (meta_message_id, event_type) WHERE meta_message_id IS NOT NULL` + `pg_insert(...).on_conflict_do_nothing()`. |

## Hallazgos NUEVOS descubiertos en código

### S13-016 — `INTERNAL_API_KEY` vacía en producción permite acceso anónimo al tick (Alto)

**Archivo**: `backend/app/routers/internal.py:46-48` (estado pre-fix).

**Descripción**: el helper `_require_internal_key` devolvía `return` sin error si `INTERNAL_API_KEY` o `INTERNAL_SECRET` no estaban seteados, permitiendo a cualquier llamada anónima disparar `POST /internal/campaigns/tick` (que procesa envíos masivos) y `POST /internal/bot-scheduler/tick`. En desarrollo es aceptable (necesario para arrancar local sin configuración), pero en producción significa que si la variable de entorno **falla al setearse en ECS** (errata, rotación mal hecha), un atacante puede:
- Forzar el procesamiento de campañas agendadas antes de tiempo.
- Procesar repetidamente para acelerar gasto de saldo Meta del cliente.
- Conjugado con S13-002 si el bucket se agota, no es catastrófico, pero sí es vector de DoS sobre la WABA.

**Severidad**: Alto. Bloqueante para deploy en prod.

**Mitigación aplicada (inline durante esta auditoría)**: 
```python
expected = os.getenv("INTERNAL_API_KEY") or os.getenv("INTERNAL_SECRET") or ""
env = (os.getenv("APP_ENV", "development") or "").strip().lower()
in_prod = env in ("production", "prod")
if not expected:
    if in_prod:
        raise HTTPException(status_code=403, detail="forbidden")
    return  # dev libre
```

Comportamiento ahora:
- Prod + env vacío → 403 a todas las llamadas (fail-closed).
- Prod + env seteado + header inválido → 403.
- Prod + env seteado + header válido → procesa.
- Dev + env vacío → procesa libre (mantiene productividad local).
- Dev + env seteado + header inválido → 403 (igual que prod).

**Requisito operativo asociado**: en la tarea #174 (deploy ECS), el task definition de producción debe incluir `INTERNAL_API_KEY` como secret (SSM o KMS-encrypted) en la sección `secrets` del container definition. Deploy AWS debe verificarlo antes de marcar #174 como ✅.

## Checklist de schemas `...Out`

| Schema | Expone secretos? | Comentarios |
|--------|------------------|-------------|
| `ContactOut` | No | id, phone_e164, name, email, attributes, opt_in, opt_in_source, timestamps. NO `team_id` (intencional, S13-001). |
| `ContactGroupOut` | No | id, name, description, member_count, created_at. |
| `ContactGroupDetailOut` | No | igual + `members: List[ContactOut]`. |
| `ContactBulkImportResult` | No | counts + `errors: List[str]` con teléfono redactado (S13-009). |
| `WhatsappTemplateOut` | No | sólo `meta_account_id: int`, no la relación. `rejection_reason` sanitizado (S13-006). |
| `WhatsappTemplateSyncResult` | No | counters + errors saneados. |
| `CampaignOut` | No | sin `meta_account` embebido. |
| `CampaignDetailOut` | No | `template_name`, `template_language` (campos derivados, no relación con token). |
| `CampaignRecipientOut` | No | `phone_e164` snapshot (intencional para la UI propia del team), no expone email del contacto. |

**Veredicto schemas**: clean. Ningún `...Out` del Sprint 13 expone `encrypted_access_token`, `hashed_password`, ni equivalentes.

## Resultado de pruebas E2E (curl)

Las pruebas E2E las hizo QA en #170 (reporte `sprint13_qa_report.md`). Esta auditoría revisó el reporte y confirmó:
1. Cross-tenant IDOR → 404 (passo M).
2. `POST /campaigns` con `template_id` no APPROVED → bloqueado por validación (#161 paso 1).
3. Rate-limit de sync templates → no se midió 3 llamadas seguidas; **follow-up para QA #175**: añadir esta prueba en smoke online.
4. `POST /internal/campaigns/tick` sin header en local con env vacío → procesaba (comportamiento dev correcto). Post-fix S13-016: en prod sin env devolverá 403.
5. Bloqueante S13-QA-001 (scheduled_at=NULL) ya parcheado por PM en `campaign_sender.py:404-407`.

## Recomendación

- **Deploy autorizado** a RDS y ECS (tareas #173 y #174) con la condición de que la task definition de prod incluya `INTERNAL_API_KEY` como secret en la sección `secrets` del container.
- **Follow-ups no bloqueantes para sprints futuros**:
  - Migrar rate-limit en memoria a Redis cuando se escale a >1 réplica de ECS (S13-002 caveat).
  - Considerar `CHECK (opt_in IN (true, false))` o trigger en BD para evitar opt-in con cambios concurrentes durante el envío (defensa adicional sobre S13-003).
  - Añadir prueba de rate-limit de sync templates al smoke online (S13-008 verificación).
  - Cuando se conecte una cuenta Meta real, redoblar revisión de logs de `services/meta_templates.py` para confirmar que no se filtre el token descifrado en errores.
