# BITACORA - Multiagente (Plataforma WhatsApp Business)

> Última actualización: 2026-04-08

---

## Sprint 0 - Setup del Proyecto

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 1 | Crear repo multiagente con estructura monorepo (frontend + backend) | Dev Plataforma | ✅ Completado | Basado en frontend_oraculo3 + backend_oraculo3 |
| 2 | Configurar sistema de agentes en CLAUDE.md | PM | ✅ Completado | 5 agentes: PM, Deploy AWS, Dev, BD, QA |
| 3 | Crear BITACORA.md con tareas | PM | ✅ Completado | Este archivo |
| 4 | Adaptar Sidebar con nuevos módulos | Dev Plataforma | ✅ Completado | 4 módulos: Mensajes, Campañas, Bots, Mi Plan |
| 5 | Crear páginas "Próximamente" para módulos 1, 2, 3 | Dev Plataforma | ✅ Completado | mensajes.tsx, campanas.tsx, bots.tsx |
| 6 | Adaptar módulo de Plan/Datos de usuario | Dev Plataforma | ✅ Completado | usuario.tsx con endpoint /usuario/me |
| 7 | Conectar login y registro frontend ↔ backend | Dev Plataforma | ✅ Completado | JWT auth con localStorage |
| 8 | Crear routers backend para nuevos módulos | Dev Plataforma | ✅ Completado | mensajes.py, campanas.py, bots.py (stubs) |
| 9 | Configurar CORS en backend | Dev Plataforma | ✅ Completado | FastAPI CORSMiddleware |
| 10 | Crear Dockerfiles (frontend + backend) | Deploy AWS | ✅ Completado | Dockerfile.frontend, Dockerfile.backend |
| 11 | Crear docker-compose para desarrollo local | Deploy AWS | ✅ Completado | 3 servicios: db, backend, frontend |
| 12 | Crear .env.example y .gitignore | Deploy AWS | ✅ Completado | Variables documentadas |
| 13 | Inicializar repo Git y push a GitHub | Dev Plataforma | ⬜ Pendiente | |

---

## Sprint 1 - Tareas del CEO (Bloqueantes)

| # | Tarea | Responsable | Estado | Datos necesarios para continuar |
|---|-------|------------|--------|-------------------------------|
| 14 | **Crear cuenta AWS** | CEO | ⬜ Pendiente | Entregar: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` (recomendado: us-east-1). Configurar con `aws configure` en terminal. |
| 15 | **Registrar/elegir dominio personalizado** | CEO | ⬜ Pendiente | Entregar: nombre del dominio elegido (ej: multiagente.com). Se puede registrar directamente en Route 53 (~$12/año para .com) o transferir uno existente. |

### Instrucciones para el CEO - Tarea #14: Crear cuenta AWS

1. Ir a [aws.amazon.com](https://aws.amazon.com) y crear cuenta
2. En la consola AWS, ir a **IAM** → **Usuarios** → Crear usuario con acceso programático
3. Asignar permisos: `AdministratorAccess` (para inicio; luego se restringirá)
4. Guardar las credenciales:
   - `AWS_ACCESS_KEY_ID` (ej: AKIA...)
   - `AWS_SECRET_ACCESS_KEY` (ej: wJalr...)
5. Instalar AWS CLI: `brew install awscli`
6. Configurar: `aws configure`
   - Region: `us-east-1`
   - Output: `json`
7. Crear archivo `.env` en la raíz del proyecto con las variables (ver .env.example)

### Instrucciones para el CEO - Tarea #15: Dominio

1. Decidir nombre de dominio
2. Opciones:
   - **Registrar en Route 53**: Consola AWS → Route 53 → Registrar dominio (~$12/año .com)
   - **Transferir dominio existente**: Obtener código de autorización del registrador actual
3. Entregar: nombre del dominio al equipo de desarrollo

---

## Sprint 2 - Backend Funcional

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 16 | Diseñar esquema de BD para mensajes y conversaciones | Experto BD | ⬜ Pendiente | Tablas: conversations, messages, contacts |
| 17 | Diseñar esquema de BD para campañas masivas | Experto BD | ⬜ Pendiente | Tablas: campaigns, campaign_messages, templates |
| 18 | Diseñar esquema de BD para bots | Experto BD | ⬜ Pendiente | Tablas: bots, bot_flows, bot_responses |
| 19 | Configurar integración API WATI | Dev Plataforma | ⬜ Pendiente | Requiere cuenta WATI activa |
| 20 | Implementar módulo de atención a mensajes (backend) | Dev Plataforma | ⬜ Pendiente | Depende de #16 y #19 |
| 21 | Implementar módulo de campañas masivas (backend) | Dev Plataforma | ⬜ Pendiente | Depende de #17 y #19 |
| 22 | Implementar módulo de bots (backend) | Dev Plataforma | ⬜ Pendiente | Depende de #18 y #19 |

---

## Sprint 3 - Frontend Funcional

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 23 | UI módulo de mensajes (bandeja de entrada tipo chat) | Dev Plataforma | ⬜ Pendiente | Depende de #20 |
| 24 | UI módulo de campañas (crear, enviar, historial) | Dev Plataforma | ⬜ Pendiente | Depende de #21 |
| 25 | UI módulo de bots (editor de flujos) | Dev Plataforma | ⬜ Pendiente | Depende de #22 |

---

## Sprint 4 - Infraestructura AWS

| # | Tarea | Responsable | Estado | Bloqueo |
|---|-------|------------|--------|---------|
| 26 | Crear ECR repository y subir imagen backend | Deploy AWS | ⬜ Pendiente | Requiere #14 |
| 27 | Configurar ECS Fargate (cluster, task definition, service) | Deploy AWS | ⬜ Pendiente | Requiere #14 |
| 28 | Configurar Amplify para frontend | Deploy AWS | ⬜ Pendiente | Requiere #14 |
| 29 | Crear RDS PostgreSQL (db.t3.micro) | Deploy AWS | ⬜ Pendiente | Requiere #14 |
| 30 | Configurar ALB (Application Load Balancer) | Deploy AWS | ⬜ Pendiente | Requiere #14 |
| 31 | Configurar Route 53 + dominio personalizado | Deploy AWS | ⬜ Pendiente | Requiere #14 y #15 |
| 32 | Configurar GitHub Actions para CI/CD | Deploy AWS | ⬜ Pendiente | Requiere #14 |

---

## Sprint 5 - QA

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 33 | Validar flujo login → dashboard → módulos (local) | QA | ⬜ Pendiente | |
| 34 | Validar deploy en AWS funcional | QA | ⬜ Pendiente | Requiere Sprint 4 |
| 35 | Test de carga (~10 usuarios concurrentes) | QA | ⬜ Pendiente | Requiere Sprint 4 |

---

## Resumen de Servicios AWS (Costo ~$42-47/mes para 10 usuarios)

| Servicio | Configuración | Costo estimado |
|----------|--------------|----------------|
| ECS Fargate | 1 task, 0.25 vCPU, 0.5GB RAM | ~$10/mes |
| ECR | 1 repositorio | ~$1/mes |
| Amplify | Frontend Next.js | ~$0-5/mes |
| RDS PostgreSQL | db.t3.micro | ~$15/mes |
| ALB | Application Load Balancer | ~$16/mes |
| Route 53 | 1 hosted zone | ~$0.50/mes |

---

## Sprint 6 - Módulo Responder Mensajes (Meta WhatsApp Cloud API)

> Rama: `feature/modulo-mensajes-meta`
> Objetivo: Permitir al usuario ver conversaciones y responder manualmente mediante la API oficial de Meta WhatsApp Cloud, con sistema de equipos y permisos extensible.

### Decisiones clave
- Se usa **Meta WhatsApp Cloud API** (graph.facebook.com/v22.0) en lugar de WATI para este módulo.
- Modelo de permisos con flags booleanos extensibles (tabla `team_permissions`) para añadir fácilmente nuevos permisos en el futuro.
- Cada usuario registrado se auto-aprovisiona un `Team` y un `TeamMember` con rol `owner` (todos los permisos en `true`).
- Credenciales Meta almacenadas en `.env` con bloques comentados (prod/test) para fácil switch.

### Credenciales Meta recibidas del CEO
| Dato | Valor |
|------|-------|
| Ad Account ID | 1240419961584629 |
| Pixel ID | 1662995571566146 |
| Número (prod) | +573003187871 |
| Phone Number ID (prod) | 1036567489546838 |
| WABA ID (prod) | 1272393681746114 |
| Phone Number ID (test) | 988594284346297 |
| WABA ID (test) | 758411907207213 |
| Token permanente | EAAXJ9jEBv8wBRNI...wZDZD |

### Credenciales pendientes del CEO (opcionales)
| # | Dato | Uso | Obligatorio |
|---|------|-----|-------------|
| A | **App Secret** de Meta | Validar firma HMAC del webhook (X-Hub-Signature-256) | Recomendado para producción |
| B | **URL pública** (ngrok o AWS) | Recibir webhooks de Meta en local | Solo para recibir mensajes en local |
| C | Verify Token | Lo define el equipo y se configura en panel Meta | Generado automáticamente |

### Tareas
| # | Tarea | Responsable | Estado | Notas |
|---|-------|-------------|--------|-------|
| 36 | Crear rama `feature/modulo-mensajes-meta` | PM | ✅ | Branch creada |
| 37 | Actualizar BITACORA con sprint | PM | ✅ | Este bloque |
| 38 | Añadir credenciales Meta a `.env` (switch fácil prod/test) | Deploy AWS | ✅ | Bloques prod/test comentados |
| 39 | Actualizar `.env.example` con variables Meta | Deploy AWS | ✅ | Variables documentadas |
| 40-45 | Diseño de modelos extensibles | Experto BD | ✅ | 7 tablas creadas |
| 46 | Implementar modelos SQLAlchemy | Dev Plataforma | ✅ | `backend/app/models.py` |
| 47 | Implementar schemas Pydantic | Dev Plataforma | ✅ | `backend/app/schemas.py` |
| 48 | Implementar funciones CRUD | Dev Plataforma | ✅ | `backend/app/crud.py` |
| 49 | Crear servicio `meta_whatsapp.py` | Dev Plataforma | ✅ | `backend/app/services/meta_whatsapp.py` |
| 50 | Crear router `teams.py` | Dev Plataforma | ✅ | CRUD teams + permisos |
| 51 | Actualizar router `mensajes.py` | Dev Plataforma | ✅ | Endpoints conversaciones + envío |
| 52 | Crear router `meta_webhook.py` | Dev Plataforma | ✅ | GET verify + POST receive (con HMAC opcional) |
| 53 | Auto-provisionar Team + owner al registrarse | Dev Plataforma | ✅ | Hook en register y login |
| 54 | Endpoint `/teams/me` con permisos | Dev Plataforma | ✅ | Frontend usa para mostrar/ocultar input |
| 55 | UI módulo `/mensajes` tipo inbox | Dev Plataforma | ✅ | Header + lista + panel chat + modal nueva |
| 56 | Permiso `can_reply_messages` en UI | Dev Plataforma | ✅ | Composer condicional |
| 57 | Ajustar `next.config.js` (BACKEND_URL configurable) | Dev Plataforma | ✅ | Defaults a localhost:8000 |
| 58 | Prueba local (levantar entorno y validar envío) | QA + CEO | ⬜ | Meta API: en espera de revisión de cuenta (24h). Se asume OK vía curl. |
| 59 | Restringir asignación de MetaAccount a `META_OWNER_EMAIL` | Dev Plataforma | ✅ | Solo `prueba@gmail.com` recibe la cuenta. Resto ve "Sin cuenta de Meta registrada". Swap vía `.env`. |
| 60 | Añadir `verified_name` a MetaAccount y mostrarlo en "Mi Plan" | Dev Plataforma | ✅ | Endpoint `/usuario/me/meta-account`. UI muestra nombre visible ("Tienda Zeniv") + teléfono. |
| 61 | QA: validar flujo con `prueba@gmail.com` y `test2@gmail.com` | QA | ✅ | SQLite in-memory: prueba@ recibe cuenta, test2@ no. Cleanup de leftovers OK. |
| 62 | Commit + push + Pull Request | PM | ⬜ | Listo para crear PR |

### Estado de validación interna (sin tocar Meta API)
- ✅ Imports del backend OK (todos los módulos compilan)
- ✅ Schema SQL creado correctamente (7 tablas)
- ✅ CRUD validado contra SQLite in-memory: usuario, team, member, permisos, meta account, conversación, mensaje
- ✅ FastAPI registra 19 rutas (auth, usuario, mensajes/4, teams/4, meta/2, etc.)
- ⬜ Prueba E2E con Meta API real (pendiente del CEO)

### Nuevos endpoints
| Método | Ruta | Permiso | Descripción |
|--------|------|---------|-------------|
| GET | `/teams/me` | autenticado | Devuelve team + permisos del usuario actual |
| GET | `/teams/me/members` | autenticado | Lista miembros del equipo |
| POST | `/teams/me/members` | `can_manage_team` | Invita un nuevo miembro |
| PUT | `/teams/me/members/{id}/permissions` | `can_manage_team` | Actualiza permisos de un miembro |
| GET | `/mensajes/conversaciones` | autenticado | Lista conversaciones del team |
| GET | `/mensajes/conversaciones/{id}` | autenticado | Detalle con mensajes |
| POST | `/mensajes/conversaciones/{id}/enviar` | `can_reply_messages` | Envía texto libre por Meta |
| POST | `/mensajes/conversaciones/nueva` | `can_reply_messages` | Inicia conversación con template |
| GET | `/meta/webhook` | público | Verificación inicial Meta |
| POST | `/meta/webhook` | público (HMAC) | Recibe mensajes entrantes |
| GET | `/usuario/me/meta-account` | autenticado | Estado de la cuenta de Meta del usuario (registered + verified_name + display_phone) |

### Esquema de permisos (extensible)
Tabla `team_permissions`: filas por cada `(team_member_id, permission_key)`:
- `can_reply_messages` — responder mensajes manualmente (scope del sprint actual)
- `can_send_broadcasts` — enviar campañas masivas (futuro)
- `can_manage_bots` — editar bots de WhatsApp (futuro)
- `can_manage_team` — invitar/editar miembros del equipo (futuro)
- `can_view_analytics` — ver reportes (futuro)

Para añadir un permiso nuevo basta con insertar filas con una nueva `permission_key`.

---

## Sprint 7 - Seguridad: Agente Experto en Seguridad + Credenciales Meta cifradas

**Rama**: `feature/seguridad-meta-credentials` (desde `feature/modulo-mensajes-meta`)

**Contexto**: el Sprint 6 dejó un hallazgo crítico: los tokens de Meta vivían en `.env`
en texto plano y se provisionaban vía seed hardcoded a `prueba@gmail.com`. Rompe multi-tenant
y expone un token permanente. El CEO pidió: (1) crear un agente permanente "Experto en
Seguridad"; (2) aplicar el refactor a DB cifrada con validación previa contra Graph API.

### Tareas del Sprint 7

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 60 | Crear agente `.claude/agents/seguridad.md` | PM | ✅ Completado | Auditor de diseño/código, severidades, checklist OWASP, reglas |
| 61 | Registrar agente en `CLAUDE.md` (tabla + reglas delegación + sección Seguridad) | PM | ✅ Completado | 6 reglas permanentes añadidas |
| 62 | Auditoría del diseño Sprint 7 por el agente `seguridad` | Seguridad | ✅ Completado | Ver informe abajo. Veredicto: APROBADO CON CAMBIOS OBLIGATORIOS |
| 63 | `backend/requirements.txt`: pinear `cryptography`, `python-jose`, `passlib` | Dev Plataforma | ⬜ Pendiente | |
| 64 | `backend/app/services/crypto.py`: Fernet + MultiFernet + encrypt/decrypt_secret | Dev Plataforma | ⬜ Pendiente | `@lru_cache`, `CryptoError`, validación al arranque |
| 65 | `backend/scripts/gen_encryption_key.py`: generador de clave Fernet | Dev Plataforma | ⬜ Pendiente | Warning anti-reuso multi-ambiente |
| 66 | `backend/app/models.py`: rename `access_token`→`encrypted_access_token` + `status`, `last_validated_at`, `validation_error`, `registered_by_user_id`, `updated_at`, `__repr__`/`__str__` redactor, UNIQUE sobre `phone_number_id` | Experto BD | ⬜ Pendiente | Rename ruidoso para forzar migración |
| 67 | `backend/scripts/reset_meta_accounts.py`: DROP TABLE con guardarraíl anti-producción | Experto BD | ⬜ Pendiente | Rehusar si DATABASE_URL no es localhost sin `--force-production` |
| 68 | `backend/app/schemas.py`: `MetaAccountRegisterIn` + extender `MetaAccountStatusOut` con `status`, `can_manage_meta_account`; `extra='forbid'` en `MetaAccountOut` | Dev Plataforma | ⬜ Pendiente | |
| 69 | `backend/app/crud.py`: eliminar `upsert_default_meta_account_for_team`; añadir `register_meta_account`, `disconnect_meta_account`, `is_meta_account_usable` | Dev Plataforma | ⬜ Pendiente | |
| 70 | `backend/app/dependencies.py`: `get_current_owner_membership` | Dev Plataforma | ⬜ Pendiente | Docstring "1 team por user (MVP)", 403 genérico |
| 71 | `backend/app/services/meta_whatsapp.py`: descifrar al vuelo + `get_phone_number_info` + sanitización de errores/headers | Dev Plataforma | ⬜ Pendiente | Bloqueante #4 del informe de seguridad |
| 72 | `backend/app/routers/meta_webhook.py`: fail-closed en producción + `hmac.compare_digest` + sanitización de logs | Dev Plataforma | ⬜ Pendiente | Bloqueante #5 del informe de seguridad |
| 73 | `backend/app/routers/usuario.py`: `GET` extendido + `POST` + `DELETE` (owner-only, validados por Graph API) | Dev Plataforma | ⬜ Pendiente | Rate limiting mínimo 5/h/user |
| 74 | `backend/app/routers/mensajes.py`: reemplazar chequeo por `is_meta_account_usable` | Dev Plataforma | ⬜ Pendiente | |
| 75 | `backend/app/routers/auth.py`: eliminar upsert, `authenticate_user` timing-constant | Dev Plataforma | ⬜ Pendiente | |
| 76 | `backend/app/config.py`: Pydantic `BaseSettings` con validación al arranque (SECRET_KEY, ALGORITHM, APP_ENCRYPTION_KEY, META_APP_SECRET) | Dev Plataforma | ⬜ Pendiente | Centraliza y falla ruidosamente si falta |
| 77 | `frontend/pages/usuario.tsx`: modal Conectar/Desconectar con `type=password`, `autocomplete=off`, `data-lpignore` | Dev Plataforma | ⬜ Pendiente | Prohibición explícita de localStorage para token Meta |
| 78 | `.env` y `.env.example`: eliminar META_PHONE_NUMBER_ID/WABA_ID/ACCESS_TOKEN/DISPLAY_PHONE/VERIFIED_NAME/OWNER_EMAIL; añadir APP_ENCRYPTION_KEY | Deploy AWS | ⬜ Pendiente | |
| 79 | Tests unitarios `backend/tests/test_crypto.py` + integración SQLite del flujo register/disconnect | QA | ⬜ Pendiente | Incluye test de `MetaAccountOut` sin campos sensibles |
| 80 | Re-auditoría del código por el agente `seguridad` post-implementación | Seguridad | ⬜ Pendiente | Cierra hallazgos o abre nuevos |
| 81 | Commit + PR + notificación al CEO | PM | ⬜ Pendiente | |

### Informe de Seguridad — 2026-04-09 — Sprint 7 (credenciales Meta cifradas)

**Auditor**: Experto en Seguridad
**Scope**: `crud.py`, `models.py`, `routers/usuario.py`, `routers/auth.py`, `routers/meta_webhook.py`, `services/meta_whatsapp.py`, `schemas.py`, `dependencies.py`, `requirements.txt`, `.env.example`, `frontend/pages/usuario.tsx`, plan Sprint 7.

#### Hallazgos críticos (bloqueantes)

| # | Archivo:línea | Hallazgo | Corrección | Asignado a |
|---|---------------|----------|-----------|-----------|
| S-01 | `models.py:115` | `access_token` permanente en texto plano en DB | Rename a `encrypted_access_token`, cifrar con `crypto.encrypt_secret` en `register_meta_account` | Dev Plataforma + Experto BD |
| S-02 | `crud.py:148-200` + `auth.py:25-50` | Seed `META_OWNER_EMAIL=prueba@gmail.com` rompe multi-tenant y expone token permanente a cualquiera que registre ese correo | Eliminar `upsert_default_meta_account_for_team` por completo. `_ensure_team_for_user` solo crea team+owner | Dev Plataforma |
| S-03 | `.env.example:21-31` | Inventario filtra plantilla con token Meta + seed OWNER_EMAIL | Eliminar todas las líneas META_PHONE_NUMBER_ID/WABA_ID/ACCESS_TOKEN/DISPLAY_PHONE/VERIFIED_NAME/OWNER_EMAIL. Añadir APP_ENCRYPTION_KEY con comentario de generación | Dev Plataforma + Deploy AWS |

#### Hallazgos altos (bloqueantes #4 y #5; demás rastreados en-sprint)

| # | Archivo:línea | Hallazgo | Corrección | Asignado a |
|---|---------------|----------|-----------|-----------|
| S-04 | `services/meta_whatsapp.py:20-51` | `MetaWhatsAppError.payload` puede contener el header `Authorization` o el body del request con token | Añadir `_sanitize_meta_payload()` que remueva `Authorization`, `access_token`, `request.headers`. Usar obligatoriamente en todo `raise` y `logger.exception` | Dev Plataforma |
| S-05 | `routers/meta_webhook.py:43-46` | `_verify_signature` es fail-open si `APP_SECRET==""` | Fail-closed: si `APP_ENV=production` y `APP_SECRET` vacío → 403. En dev, warning log por request | Dev Plataforma |
| S-06 | Plan fase 4 paso 2 | `APP_ENCRYPTION_KEY` en env var del task ECS es dumpable desde RCE del host | Aceptar con 3 controles: (a) documentar modelo de amenaza, (b) claves distintas dev/prod, (c) follow-up migrar a AWS Secrets Manager | Deploy AWS (follow-up) |
| S-07 | Plan fase 4 paso 9 (`get_phone_number_info`) | Token en query string leak si se pasa por error; errores de Graph API pueden contener el token | (a) Token SOLO en header Authorization; (b) regex scrub de substrings `EAA...` antes de loggear o devolver | Dev Plataforma |
| S-08 | Plan fase 4 paso 12 (`POST /usuario/me/meta-account`) | Sin rate limiting: bruteforce de tokens y abuso del rate limit de Meta | Rate limit 5/h/usuario + 20/h/IP con contador en memoria o `slowapi` | Dev Plataforma |
| S-09 | Plan fase 4 paso 13 (modal usuario.tsx) | Leak del token en DevTools/localStorage/autocomplete | `type=password`, `autocomplete=off`, `data-lpignore=true`, `spellcheck=false`; limpieza de estado post-submit; prohibición explícita de `localStorage` | Dev Plataforma |
| S-10 | `schemas.py:80-90` (`MetaAccountOut`) | Comentario "NEVER add the token field" no es un control | Añadir `model_config=ConfigDict(extra='forbid')` + test unitario que afirme `'encrypted_access_token' not in MetaAccountOut.model_fields` | Dev Plataforma + QA |
| S-11 | Plan fase 4 paso 4 (`__repr__` redactor) | `__repr__` no cubre `logger.info(account.__dict__)`, `jsonable_encoder(account)`, `SQLAlchemy echo=True` | Implementar `__str__` también; regla explícita en CLAUDE.md; helper `log_meta_account_safe()`; `echo=False` en prod | Dev Plataforma |

#### Hallazgos medios (11 — rastreados; los más importantes)

| # | Archivo:línea | Hallazgo | Corrección |
|---|---------------|----------|-----------|
| S-12 | `auth.py` + `usuario.py` + `dependencies.py` | Triplicación de `load_dotenv()` y lectura directa de env vars; `SECRET_KEY=None` silencioso | `backend/app/config.py` con Pydantic `BaseSettings` + `field_validator` que crashea al arranque |
| S-14 | `crud.py:37-43` (`authenticate_user`) | Timing-attack: usuario inexistente retorna ~0ms, existente con password errado ~100ms (bcrypt) → enumeración de correos | Ejecutar `pwd_context.verify(password, DUMMY_HASH)` si `user is None` |
| S-15 | Plan fase 4 paso 5 (`reset_meta_accounts.py`) | `DROP TABLE` destructivo sin guardarraíl anti-producción | Rehusar si `DATABASE_URL` no es localhost/127.0.0.1/db sin `--force-production`; requerir escribir nombre de DB para confirmar |
| S-18, S-19 | `meta_webhook.py:68,125-128` | `logger.info("Webhook Meta recibido: %s", payload)` loggea PII + texto de mensajes; `logger.exception` imprime `repr(exc)` que puede contener headers con token | Loggear solo `entries=%d`; `logger.exception("type=%s", type(exc).__name__)`; detalle solo bajo flag `DEBUG_WEBHOOKS` |
| S-20 | `usuario.py:63-70` | `phone_number_id` y `waba_id` devueltos a cualquier miembro (no solo owner) | Condicionar inclusión a `member.role == "owner"` |
| S-21 | Plan fase 4 paso 8 (`get_current_owner_membership`) | IDOR latente en multi-team (asume 1 team por user); mensaje de error 403 verbose | Docstring "1 team por user (MVP)"; 403 genérico "No autorizado" |
| S-22 | `meta_webhook.py:31-40` | `hub_verify_token == VERIFY_TOKEN` no es constant-time | `hmac.compare_digest(hub_verify_token or "", VERIFY_TOKEN)` |

> Observación crítica adicional: **UNIQUE a nivel DB sobre `phone_number_id`** en `MetaAccount` para prevenir spoofing de tenant (dos tenants registrando el mismo phone_number_id). → **Experto BD**.

#### Hallazgos bajos (6 — rastreados como follow-up)

S-23 pin de dependencias + pip-audit · S-24 CSP + security headers + X-Frame-Options · S-25 validación de `SECRET_KEY` contra placeholder en prod · S-26 `.env.example` no debe contener valor ejemplo de `APP_ENCRYPTION_KEY` · S-27 manejador global de 401 en frontend · S-28 audit log (`audit_logs` table) para acciones sensibles.

#### Resumen
- **Críticos**: 3 (todos bloqueantes → S-01, S-02, S-03)
- **Altos**: 8 (bloqueantes S-04 y S-05; resto en-sprint)
- **Medios**: 11
- **Bajos**: 6 (follow-up)

**Veredicto**: **APROBADO CON CAMBIOS OBLIGATORIOS**. Implementar según fases del plan incorporando los fixes S-01 a S-11. Re-auditar post-implementación.

---

## Log de Cambios

| Fecha | Agente | Acción |
|-------|--------|--------|
| 2026-04-08 | PM | Creación del proyecto, estructura base, CLAUDE.md y BITACORA.md |
| 2026-04-08 | Dev Plataforma | Adaptación frontend (Sidebar, Login, Register, módulos) y backend (auth, routers, CORS) |
| 2026-04-08 | Deploy AWS | Dockerfiles, docker-compose.yml, .env.example |
| 2026-04-09 | PM | Sprint 6 arrancado. Rama creada. Tareas 36-59 definidas. |
| 2026-04-09 | Dev Plataforma | Implementación completa Sprint 6: modelos, schemas, CRUD, servicio Meta, routers (teams, mensajes, meta_webhook), UI inbox. |
| 2026-04-09 | Dev Plataforma | Restricción MetaAccount a `META_OWNER_EMAIL` (prueba@gmail.com). Añadido `verified_name`. Endpoint `/usuario/me/meta-account`. UI "Mi Plan" muestra estado. Cleanup de leftovers. |
| 2026-04-09 | QA | Validación SQLite in-memory: prueba@ recibe cuenta con nombre "Tienda Zeniv" y teléfono +573003187871; test2@ queda sin cuenta; cleanup de leftovers OK; swap por `.env` OK. |
| 2026-04-09 | PM | Sprint 7 arrancado. Rama `feature/seguridad-meta-credentials`. Agente `seguridad` creado y registrado en CLAUDE.md. |
| 2026-04-09 | Seguridad | Auditoría del diseño Sprint 7. 3 críticos + 8 altos + 11 medios + 6 bajos. Veredicto: APROBADO CON CAMBIOS. |
