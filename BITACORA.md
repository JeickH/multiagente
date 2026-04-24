# BITACORA - Multiagente (Plataforma WhatsApp Business)

> Última actualización: 2026-04-24

## Índice

| Sprint | Objetivo | Estado |
|--------|----------|--------|
| [Sprint 0](#sprint-0---setup-del-proyecto--cerrado) | Setup del monorepo, agentes, Docker local | CERRADO |
| [Sprint 1](#sprint-1---tareas-del-ceo-bloqueantes--cerrado) | Cuenta AWS + dominio (tareas del CEO) | CERRADO |
| [Sprint 2](#sprint-2---backend-funcional--cerrado) | Esquemas de BD y módulos backend iniciales | CERRADO |
| [Sprint 3](#sprint-3---frontend-funcional--cerrado) | UIs iniciales de los módulos | CERRADO |
| [Sprint 4](#sprint-4---infraestructura-aws--cerrado) | Provisionamiento AWS (ECS, RDS, Amplify, ALB) | CERRADO |
| [Sprint 5](#sprint-5---qa--cerrado) | Validaciones QA del flujo base | CERRADO |
| [Sprint Pendientes](#sprint-pendientes--tareas-consolidadas-de-sprints-05) | Backlog consolidado de tareas abiertas | ABIERTO |
| [Sprint 6](#sprint-6---módulo-responder-mensajes-meta-whatsapp-cloud-api) | Módulo Mensajes con Meta WhatsApp Cloud API | DONE |
| [Sprint 7](#sprint-7---seguridad-agente-experto-en-seguridad--credenciales-meta-cifradas) | Seguridad: credenciales Meta cifradas per-tenant | DONE |
| [Sprint 8](#sprint-8---módulo-bots-inteligentes-visualización-read-only) | Módulo Bots (visualización read-only) | DONE |
| [Sprint 9](#sprint-9---bots-due%C3%B1o-por-cuenta-triggers-export-y-simulador) | Bots: dueño por cuenta, triggers, export JSON, simulador | DONE |
| [Sprint 10](#sprint-10---motor-de-bots-real-ruta-a) | Motor de bots contra WhatsApp (Ruta A: síncrono + scheduler) | DONE |
| [Sprint 11](#sprint-11---landing-page-gloma--reactivaci%C3%B3n-aws) | Landing page Gloma + reactivación de servicios AWS | DONE |
| [Sprint 12](#sprint-12---dominio-propio-glomabeautycom) | Dominio propio `glomabeauty.com` (Route 53 + HostGator + Amplify) | DONE |

---

## Sprint 0 - Setup del Proyecto — CERRADO

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
| 13 | Inicializar repo Git y push a GitHub | Dev Plataforma | ✅ Completado | PR #2 mergeado a main (2026-04-10) |

---

## Sprint 1 - Tareas del CEO (Bloqueantes) — CERRADO

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 14 | **Crear cuenta AWS** | CEO | ✅ Completado | Cuenta 747456040509, usuario `multiagente-admin`, región `sa-east-1` |
| 15 | **Registrar/elegir dominio personalizado** | CEO | ⬜ Pendiente | Trasladado a Sprint Pendientes |

---

## Sprint 2 - Backend Funcional — CERRADO

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 16 | Diseñar esquema de BD para mensajes y conversaciones | Experto BD | ✅ Completado | Completado en Sprint 6 (7 tablas: teams, members, permisos, meta_accounts, conversaciones, mensajes, contacts) |
| 17 | Diseñar esquema de BD para campañas masivas | Experto BD | ⬜ Pendiente | Trasladado a Sprint Pendientes |
| 18 | Diseñar esquema de BD para bots | Experto BD | ⬜ Pendiente | Trasladado a Sprint Pendientes |
| 19 | Configurar integración API WATI | Dev Plataforma | ❌ Cancelado | Pivote a Meta WhatsApp Cloud API (Sprint 6) |
| 20 | Implementar módulo de atención a mensajes (backend) | Dev Plataforma | ✅ Completado | Completado en Sprint 6 (routers mensajes + meta_webhook) |
| 21 | Implementar módulo de campañas masivas (backend) | Dev Plataforma | ⬜ Pendiente | Trasladado a Sprint Pendientes |
| 22 | Implementar módulo de bots (backend) | Dev Plataforma | ⬜ Pendiente | Trasladado a Sprint Pendientes |

---

## Sprint 3 - Frontend Funcional — CERRADO

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 23 | UI módulo de mensajes (bandeja de entrada tipo chat) | Dev Plataforma | ✅ Completado | Completado en Sprint 6 (inbox con header, lista, panel chat y modal nueva conversación) |
| 24 | UI módulo de campañas (crear, enviar, historial) | Dev Plataforma | ⬜ Pendiente | Trasladado a Sprint Pendientes |
| 25 | UI módulo de bots (editor de flujos) | Dev Plataforma | ⬜ Pendiente | Trasladado a Sprint Pendientes |

---

## Sprint 4 - Infraestructura AWS — CERRADO

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 26 | Crear ECR repository y subir imagen backend | Deploy AWS | ✅ Completado | Completado en Sprint 7 — `747456040509.dkr.ecr.sa-east-1.amazonaws.com/multiagente-backend` |
| 27 | Configurar ECS Fargate (cluster, task definition, service) | Deploy AWS | ✅ Completado | Completado en Sprint 7 — cluster `multiagente-cluster`, task-def rev 3 |
| 28 | Configurar Amplify para frontend | Deploy AWS | ✅ Completado | Completado en Sprint 7 — app id `d1cfl9ey07f61o`, job 6 SUCCEED |
| 29 | Crear RDS PostgreSQL (db.t3.micro) | Deploy AWS | ✅ Completado | Completado en Sprint 7 — `multiagente-db.cvosucssebn3.sa-east-1.rds.amazonaws.com` |
| 30 | Configurar ALB (Application Load Balancer) | Deploy AWS | ✅ Completado | Completado en Sprint 7 — `multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com` |
| 31 | Configurar Route 53 + dominio personalizado | Deploy AWS | ⬜ Pendiente | Trasladado a Sprint Pendientes. Depende de tarea #15 |
| 32 | Configurar GitHub Actions para CI/CD | Deploy AWS | ⬜ Pendiente | Trasladado a Sprint Pendientes |

---

## Sprint 5 - QA — CERRADO

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 33 | Validar flujo login → dashboard → módulos (local) | QA | ✅ Completado | Completado en Sprint 7 — smoke test local con docker-compose + venv dedicado |
| 34 | Validar deploy en AWS funcional | QA | ✅ Completado | Completado en Sprint 7 — validación E2E contra ALB (register + login + meta-account + teams) |
| 35 | Test de carga (~10 usuarios concurrentes) | QA | ⬜ Pendiente | Trasladado a Sprint Pendientes |

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

## Sprint Pendientes — Tareas consolidadas de Sprints 0–5

> Creado el 2026-04-23. Concentra todas las tareas no completadas de los Sprints 0 al 5
> al momento de su cierre. Las tareas completadas implícitamente durante Sprints 6-7
> fueron marcadas como ✅ en sus sprints de origen.

| # | Tarea | Sprint origen | Responsable | Estado | Notas |
|---|-------|---------------|------------|--------|-------|
| 15 | Registrar/elegir dominio personalizado | Sprint 1 | CEO | ⬜ Pendiente | Bloqueante para tarea #31 (Route 53) |
| 17 | Diseñar esquema de BD para campañas masivas | Sprint 2 | Experto BD | ⬜ Pendiente | Tablas: campaigns, campaign_messages, templates |
| 18 | Diseñar esquema de BD para bots | Sprint 2 | Experto BD | ⬜ Pendiente | Tablas: bots, bot_flows, bot_responses |
| 21 | Implementar módulo de campañas masivas (backend) | Sprint 2 | Dev Plataforma | ⬜ Pendiente | Depende de #17 |
| 22 | Implementar módulo de bots (backend) | Sprint 2 | Dev Plataforma | ⬜ Pendiente | Depende de #18 |
| 24 | UI módulo de campañas (crear, enviar, historial) | Sprint 3 | Dev Plataforma | ⬜ Pendiente | Depende de #21 |
| 25 | UI módulo de bots (editor de flujos) | Sprint 3 | Dev Plataforma | ⬜ Pendiente | Depende de #22 |
| 31 | Configurar Route 53 + dominio personalizado | Sprint 4 | Deploy AWS | ⬜ Pendiente | Depende de #15 |
| 32 | Configurar GitHub Actions para CI/CD | Sprint 4 | Deploy AWS | ⬜ Pendiente | |
| 35 | Test de carga (~10 usuarios concurrentes) | Sprint 5 | QA | ⬜ Pendiente | Infraestructura AWS ya disponible |
| 101 | Aplicar migración Sprint 8 en RDS (regla paridad BD) | Sprint 8 | Deploy AWS | ⏸️ Diferido | Servicios AWS apagados por ahora. Cuando se reactiven: build imagen `:sprint8` → push ECR → update-service → `create_all()` crea tablas nuevas. |
| 103 | Limpieza de ramas residuales y PR huérfano | Sprint 8 | Dev Plataforma | ✅ Completado 2026-04-24 | PR #1 cerrado (superseded por PR #2, commit `41b0a9a`). Ramas `feature/modulo-mensajes-meta` y `feature/seguridad-meta-credentials` borradas local + remoto. |

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

### Deploy Sprint 7 — 2026-04-10

**Estado al retomar**: branch `feature/seguridad-meta-credentials` @ `3e78b78`.
Infra ya provisionada en sesiones previas: ECR `:sprint7`, SSM
`/multiagente/prod/APP_ENCRYPTION_KEY`, policy `multiagente-ssm-read`,
task-def `multiagente-backend:3`. Servicio ya migrado a rev 3.

**Bug crítico encontrado en producción**: después del drop de `meta_accounts`
el backend nunca fue reiniciado, por lo que `create_all()` no recreó la tabla
→ GET `/usuario/me/meta-account` crasheaba con 500 / `relation "meta_accounts"
does not exist`. Además, el modelo `User` del Sprint 7 agregó `created_at` a
una tabla que ya existía en RDS desde antes del Sprint 6: `POST /login`
crasheaba con 500 / `column users.created_at does not exist`. Causa raíz:
`SQLAlchemy.Base.metadata.create_all()` **no aplica ALTER TABLE** a tablas
preexistentes.

**Regla permanente añadida** (por solicitud del CEO, documentada en
CLAUDE.md > "Convenciones de operación"):

> La base de datos local (`docker-compose db`) y la de producción (RDS
> `multiagente-db`) deben tener siempre el mismo schema. Todo ALTER/DROP/
> índice se aplica en ambos entornos en el mismo PR. Follow-up: adoptar
> Alembic para migraciones versionadas.

**Fixes aplicados**:
- `backend/scripts/migrate_sprint7_add_columns.py` — migración idempotente
  usando `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Primera entrada:
  `users.created_at TIMESTAMP NOT NULL DEFAULT NOW()`.
- Ejecutado en RDS vía `aws ecs run-task` con command override del task-def
  rev 3 (hereda VPC + secret APP_ENCRYPTION_KEY). Salida:
  `users_columns=id,nombre,tipo_documento,documento,correo,hashed_password,created_at`.
- `aws ecs update-service --force-new-deployment` forzó rearranque del
  backend → `create_all()` recreó `meta_accounts` con el schema nuevo.

**Validación E2E contra ALB**
(`http://multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com`):

| Paso | Request | Resultado |
|------|---------|-----------|
| 1 | `POST /register` (smoke user) | 200 UserOut |
| 2 | `POST /login` | 200 JWT |
| 3 | `GET /usuario/me/meta-account` | 200 `{"registered":false,"can_manage_meta_account":true,…}` |
| 4 | `POST /usuario/me/meta-account` con token falso | **400** con mensaje sanitizado — S-04/S-07 OK |
| 5 | `GET /teams/me` | 200 con permisos owner |

**Nota de auditoría**: la API sigue devolviendo errores genéricos al cliente
(hallazgo S-04/S-11 se mantiene respetado en runtime).

### Tareas de cierre pendientes

| # | Tarea | Responsable | Estado |
|---|-------|------------|--------|
| 82 | Smoke test local con docker-compose + aplicar `migrate_sprint7_add_columns.py` al volumen local (regla paridad BD) | QA | ⬜ Pendiente |
| 83 | Follow-ups abiertos: S-13 (rate limit POST register), S-14 (config.py en main.py fail-fast), S-26 (rotar SECRET_KEY en ECS), S-28 (reintentos + timeout en `get_phone_number_info`) — como TODOs en código, no resolver en este PR | Dev Plataforma | ⬜ Pendiente |
| 84 | Adoptar Alembic (follow-up permanente derivado del bug de migración) | Dev Plataforma / Experto BD | ⬜ Pendiente |
| 85 | Amplify: mergear PR #2 a `main` → auto-deploy del frontend (decisión del CEO 2026-04-10) | PM + Deploy AWS | ⬜ Pendiente |

---

## Sprint 8 - Módulo Bots Inteligentes (visualización read-only)

**Rama**: `feature/modulo-bots-readonly` (desde `main`)

**Contexto**: la plataforma ya resuelve respuestas manuales (Sprint 6) y seguridad
de credenciales (Sprint 7). El siguiente incremento es el módulo de Bots
inteligentes. Por ahora el cliente final NO edita bots: nosotros los
configuramos y el usuario los visualiza en su panel.

### Alcance del Sprint 8

1. Listado de bots por cuenta (`/bots`) replicando el mock
   `referencia/chatbot_dash.png`: tabs ("Tus bots" con badge verde), tabla con
   columnas Nombre, Disparado, Pasos terminados, Terminada, Modificado el,
   Acciones; iconos de canales (WhatsApp, Instagram, Messenger) e icono de
   diamante dorado para bots premium.
2. Vista de detalle de un bot (`/bots/[id]`): se abre en **pestaña nueva**
   (`target="_blank"`) y renderiza **sin sidebar** (canvas pantalla completa).
   Muestra un canvas con fondo cuadriculado y los bloques del flujo conectados
   con flechas punteadas, según la referencia `referencia/ver_bot.png` — pero
   **sin** la columna izquierda de componentes arrastrables (ese panel es
   para edición, no para el modo visualización). Solo lectura.
3. Schema de BD que permita: varios bots por team, varios pasos por bot,
   tipos básicos de paso (enviar texto, enviar template, enviar media,
   esperar input, delay, condición, fin).
4. Seed: un bot de ejemplo con 5 pasos asignado al team de
   `prueba@gmail.com` para validar visualmente.

### Fuera de alcance
- Editor visual de flujos, drag&drop, creación desde la UI.
- Ejecución del bot (motor de flujos) contra mensajes entrantes.
- Analítica real: los contadores "Disparado/Pasos terminados/Terminada" se
  almacenan como columnas pero en este sprint quedan en 0 (o los valores
  seed). El incremento en tiempo real vendrá en sprints posteriores.

### Decisiones de diseño
- **Multi-tenant**: cada bot pertenece a un `team_id`. Las queries SIEMPRE
  filtran por el team del usuario autenticado.
- **Canales vinculados**: se modelan como columna CSV (`whatsapp,instagram,messenger`).
  Es suficiente para el MVP de solo visualización y evita una tabla extra.
  Follow-up: migrar a tabla `bot_channels` cuando se agregue edición.
- **Pasos**: cada `bot_step` guarda `step_type`, `label`, `position`
  (orden horizontal) y `config` (JSON serializado) con el payload específico
  del bloque. El `next_step_id` apunta al siguiente paso (flujo lineal MVP;
  para ramificación se añadirá en el futuro un `branches` JSON).
- **Permiso**: se reutiliza `can_manage_bots` de `AVAILABLE_PERMISSIONS`
  para futuros endpoints de edición. Para este sprint (solo lectura), todo
  usuario autenticado del team puede listar y ver sus bots.

### Tareas del Sprint 8

| # | Tarea | Responsable | Estado | Notas |
|---|-------|-------------|--------|-------|
| 86 | Fix: login falla vía proxy Next.js (`BACKEND_URL` bakeado en build) | Dev Plataforma | ✅ Completado | `Dockerfile.frontend`: `ARG BACKEND_URL`; `docker-compose.yml`: `build.args.BACKEND_URL: http://backend:8000` |
| 87 | Abrir BITACORA con Sprint 8 y diseño | PM | ✅ Completado | Este bloque |
| 88 | Diseñar schema `bots` + `bot_steps` | Experto BD | ✅ Completado | FK al team con cascade, CSV de canales, JSON config, índice `(team_id, updated_at)`, UNIQUE `(bot_id, position)` |
| 89 | Migración idempotente `migrate_sprint8_add_bots.py` | Experto BD | ✅ Completado | Aplicada en local vía docker-compose. Queda aplicar en RDS (follow-up) |
| 90 | Modelos SQLAlchemy `Bot` y `BotStep` en `models.py` | Dev Plataforma | ✅ Completado | Relaciones + `order_by=position` + cascade |
| 91 | Schemas Pydantic `BotListItem`, `BotDetail`, `BotStepOut` | Dev Plataforma | ✅ Completado | Solo lectura; canales como `List[str]` |
| 92 | CRUD: `list_bots_by_team`, `get_bot_for_team` (verifica `team_id`) | Dev Plataforma | ✅ Completado | Filtro obligatorio por team. Helpers `bot_to_list_item` y `bot_to_detail` parsean CSV/JSON |
| 93 | Router `/bots`: GET `/bots` + GET `/bots/{id}` | Dev Plataforma | ✅ Completado | Usa `get_current_membership`. 404 en IDOR cross-team |
| 94 | Seed: crear bot de ejemplo con 5 pasos para `prueba@gmail.com` | Dev Plataforma | ✅ Completado | `seed_bot_demo.py` idempotente. Crea `catalogo_talulah` (5 pasos) + `Confirmación de pedido` (premium, 4 pasos, 3 canales) |
| 95 | UI `/bots`: tabla con tabs, iconos de canales, badge premium, acciones | Dev Plataforma | ✅ Completado | Link azul a `/bots/{id}` con `target="_blank"`. Acciones en botones deshabilitados |
| 96 | UI `/bots/[id]`: canvas sin sidebar (pestaña nueva) con bloques + flechas punteadas | Dev Plataforma | ✅ Completado | SVG con bezier punteado + marker flecha; nodos con color por tipo; fondo grid; sin layout global |
| 97 | Actualizar sidebar: link `/bots` activo | Dev Plataforma | ✅ Completado | Ya existía; no requiere cambios |
| 98 | QA: E2E listado + detalle + seed aplicado contra docker-compose | QA | ✅ Completado | `prueba@gmail.com` ve 2 bots, detalle id=1 devuelve 5 pasos |
| 99 | Seguridad: revisión multi-tenant (filtro por team, sin IDOR) | Seguridad | ✅ Completado | Usuario `otro@test.com` → lista vacía `[]`; GET `/bots/1` → 404 |
| 100 | Fix infra: `BACKEND_URL` como build-arg en Dockerfile.frontend | Deploy AWS | ✅ Completado | Next.js bakea rewrites en build. Documentar para Amplify |
| 101 | Follow-up: aplicar migración Sprint 8 en RDS (regla paridad BD) | Deploy AWS | ⏸️ Diferido | Movido a Sprint Pendientes. Servicios AWS apagados por decisión del CEO (2026-04-24) |
| 102 | Commit + push a `main` | PM | ✅ Completado | Commit `cf77351` directo a `main` (no hubo rama feature en Sprint 8). Push a `origin/main` el 2026-04-24 |

---

## Sprint 9 - Bots: dueño por cuenta, triggers, export y simulador

**Rama**: trabajo directo en `main` (continuidad con Sprint 8)

**Contexto**: tras probar el Sprint 8 el CEO pidió ajustes de modelo y UX:
el dueño del bot debe ser la cuenta (no el team), el listado se vuelve más
limpio (sin acciones, sin premium, sin iconos de canales al lado del
nombre), y se introduce la noción de **trigger** (cómo se activa un bot) y
**bot default** (catch-all para mensajes nuevos). Además se arranca el
motor de ejecución del flujo, reutilizable para "probar bot" en pop-up y,
en el futuro, para responder a mensajes reales entrantes.

### Decisiones clave

- **Dueño = `user_id` + visibilidad por team**: cada bot tiene `user_id`
  (dueño/creador) en vez de `team_id`. El listado de `/bots` resuelve la
  visibilidad por el owner del team del usuario autenticado: cualquier
  miembro del team ve los bots del owner. Así en el MVP (1 team por user)
  no cambia nada práctico, y cuando entren agents reales el "dueño"
  sigue siendo la cuenta owner — no hay bots duplicados por miembro.
- **Triggers**: enum en `trigger_type` — `default` | `keyword` | `manual`.
  `trigger_config` guarda parámetros (ej: `{"keywords": ["hola","menu"]}`).
  Solo un bot por user puede tener `trigger_type='default'` (constraint
  con UNIQUE parcial en Postgres).
- **Todos los bots son activables por otro bot**: no se introduce un
  booleano aparte. El caso de "este bot solo se invoca desde otro" queda
  cubierto por `trigger_type='manual'`.
- **Motor de ejecución en `services/bot_engine.py`**: lógica pura
  (stateless) que recibe `(bot, state, user_input)` y retorna
  `{actions, next_state}`. En simulación el estado vive en el frontend;
  en ejecución real contra Meta vivirá en una tabla `bot_sessions`
  (fuera de alcance de este sprint).

### Fuera de alcance

- Editor visual del flujo del bot (sigue solo lectura).
- Tabla `bot_sessions` y ejecución contra mensajes entrantes reales
  (vendrá cuando se integre con el webhook de Meta).
- Migración de este sprint en RDS (servicios AWS apagados).

### Tareas del Sprint 9

| # | Tarea | Responsable | Estado | Notas |
|---|-------|-------------|--------|-------|
| 104 | Índice de sprints al inicio de BITACORA | PM | ✅ Completado | Enlaces a todas las secciones |
| 105 | Schema: agregar `bots.user_id`, `trigger_type`, `trigger_config`; drop `is_premium` | Experto BD | ✅ Completado | UNIQUE parcial `uq_one_default_bot_per_user` WHERE trigger_type='default' |
| 106 | Migración idempotente `migrate_sprint9_bots_ownership_triggers.py` | Experto BD | ✅ Completado | ADD/DROP IF EXISTS + backfill `user_id` desde `teams.owner_user_id`. Aplicada local |
| 107 | Modelos + schemas + CRUD: `list_bots_visible_to_member`, `get_bot_visible_to_member`, `bot_to_export_dict` | Dev Plataforma | ✅ Completado | Visibilidad por owner del team (cualquier miembro ve los bots del owner). IDOR-safe |
| 108 | Motor `services/bot_engine.py` — `advance(bot, state, user_input)` | Dev Plataforma | ✅ Completado | Puro y stateless. 7 tipos de paso. Tope `MAX_STEPS_PER_TURN=50` |
| 109 | Endpoints: `GET /bots/export` (JSON) + `POST /bots/{id}/simulate` | Dev Plataforma | ✅ Completado | Export con `Content-Disposition attachment`; simulate retorna `{actions, next_state, finished}` |
| 110 | Seed actualizado con triggers | Dev Plataforma | ✅ Completado | `catalogo_talulah` = default; `Confirmación de pedido` = keyword `["pedido","compra","orden"]` |
| 111 | UI `/bots`: tabla minimalista + columna Activación + descarga JSON | Dev Plataforma | ✅ Completado | Sin Plantillas / Acciones / Pasos terminados / Terminada / iconos / premium / Agregar. Badges ⭐Default, 🔑Keyword, 🔗Manual |
| 112 | UI `/bots/[id]`: solo botón "Probar" + pop-up modal tipo chat | Dev Plataforma | ✅ Completado | Modal 600px con burbujas WhatsApp-style. Estado en cliente. Reset. Auto-scroll |
| 113 | E2E: migración + re-seed + listado + export + simulate 2-turnos + multi-tenant | QA | ✅ Completado | Simulate turno 1 → `say+ask` (2 acciones); turno 2 con `"catalogo"` → `say_media+say+end` (3 acciones, finished=true). `otro@test.com` → `[]` y 404 |
| 114 | Commit + push a `main` | PM | ⬜ En curso | Trabajo directo sobre main (sin rama feature) |

---

## Sprint 10 - Motor de bots real (Ruta A)

**Rama**: trabajo directo en `main`.

**Contexto**: el motor `bot_engine.advance` existe (Sprint 9) pero solo
se usa en el pop-up de simulación. Sprint 10 lo conecta al webhook real
de Meta para que cuando un cliente escriba al WhatsApp de una cuenta
registrada, el backend responda con el flujo del bot correspondiente.

**Arquitectura elegida (Ruta A — síncrono):**
```
Meta webhook → meta_webhook.py (HMAC + dedupe) →
    resolve_bot_for_message() →
        bot_engine.advance(bot, session.state, user_input) →
            persist session + send actions to Meta
```

Para pasos `delay` largos se introduce tabla `bot_pending_actions` y
un tick (`POST /internal/bot-scheduler/tick`) que se puede disparar con
cron externo cada 60s (en local, CronCreate; en AWS, EventBridge Rule).

### Tareas del Sprint 10

| # | Tarea | Agente | Estado | Notas |
|---|-------|--------|--------|-------|
| 115 | Modelo `BotSession` + `BotPendingAction` + migración idempotente `migrate_sprint10_bot_sessions.py` | Experto BD | ✅ Completado | FK cascade a conversation + bot. `state` TEXT (JSON). Status `running`/`waiting`/`finished`/`cancelled`. Índice `(conversation_id, status)` |
| 116 | `services/bot_router.py` — `resolve_bot_for_incoming_message()` | Dev Plataforma | ✅ Completado | Prioridad: sesión activa > keyword match > default. Sin match → None (humano toma la conversación) |
| 117 | `services/bot_runner.py` — `run_turn()` + `process_pending_action()` | Dev Plataforma | ✅ Completado | Orquesta motor + sesión + envío Meta. Dedupe por `meta_message_id` en webhook. `_send_text` captura cualquier `Exception` para que un envío fallido no rompa el turno |
| 118 | Endpoint interno `POST /internal/bot-scheduler/tick` | Dev Plataforma | ✅ Completado | `routers/internal.py`. Protegido por `X-Internal-Secret` (opcional en dev). Procesa N pending_actions vencidas por llamada |
| 119 | Seguridad: dedupe webhook + try/except defensivo + sanitización | Seguridad | ✅ Completado | `meta_message_id` dedupe, errores del runner no propagan 500, logs via `logger.exception`. Pendiente rate-limit explícito → Sprint Pendientes |
| 120 | QA: simulación E2E local con payload Meta fake | QA | ✅ Completado | Webhook 200, dedupe por msg_id OK, sesión creada (bot_id=3, conv_id=1, status=running), motor ejecutó; envío outbound queda `status=failed` con `InvalidToken` (token dummy, esperable). Flujo real completo requiere token Meta válido → Sprint 11 |
| 121 | Commit + push Sprint 10 | PM | ✅ Completado | Se commitea junto con Sprint 11 (levantamiento AWS) |

---

## Sprint 11 - Landing page Gloma + reactivación AWS

**Rama**: trabajo directo en `main`.

**Contexto**: nace la marca **Gloma** (glow al mayor) — plataforma de
automatización de ventas por WhatsApp para distribuidores mayoristas de
moda y belleza. El CEO quiere una landing pública en la ruta `/gloma` del
dominio AWS actual, servida desde Amplify. Se aprovecha para reactivar
todos los servicios de AWS (apagados desde Sprint 8) y validar los
sprints 8, 9 y 10 en producción.

**Identidad Gloma** (ver `identidad_gloma/branding_gloma_v2.html`):
- Paleta: Rosa Empolvado `#F7D1CD`, Marrón Tierra `#5E503F`, Crema `#FDFBF7`.
- Tipografía: `Syne` (títulos, Extra Bold) + `Inter` (cuerpo).
- Tono: sofisticado, cercano, profesional. Concepto "Soft Cyber".

**Estructura de la landing:**
1. Header con banner de fondo + frase "tecnología que resalta tu catálogo".
2. Preview con 3 tarjetas (texto + imagen) de propuesta de valor.
3. Funcionalidades clave (6 items con espacio para icono).
4. Estadísticas (3 métricas con espacio para icono).
5. Contacto: link WhatsApp + form (email + teléfono).
6. Footer: email + teléfono + dirección de prueba + logo.

### Tareas del Sprint 11

| # | Tarea | Agente | Estado | Notas |
|---|-------|--------|--------|-------|
| 122 | Copiar assets de `identidad_gloma/` a `frontend/public/gloma/` | Dev Plataforma | ✅ Completado | 7 assets: banner, 3 previews, 3 variantes del logo |
| 123 | Crear página `pages/gloma.tsx` con todas las secciones | Dev Plataforma | ✅ Completado | Header con banner, 3 previews intercaladas, 6 features, 3 stats, contacto, footer. Mobile-first |
| 124 | Agregar Syne + Inter vía Google Fonts | Dev Plataforma | ✅ Completado | `<link>` dentro de `<Head>` de la página Gloma |
| 125 | Backend: modelo `Lead` + migración `migrate_sprint11_leads.py` + endpoint `POST /landing/leads` | Experto BD + Dev Plataforma | ✅ Completado | `routers/landing.py` con validación Pydantic + rate-limit 5/IP/h en memoria |
| 126 | Form landing → `/api/landing/leads` con estado enviado/error | Dev Plataforma | ✅ Completado | Mensaje verde/rojo in-line |
| 127 | AWS: encender RDS + aplicar migraciones 8 + 9 + 10 + 11 | Deploy AWS | ✅ Completado | RDS `available`. Migraciones via `ecs run-task` con command override, todas exit=0 |
| 128 | AWS: build + push imagen backend `:sprint10` y `:sprint11` a ECR | Deploy AWS | ✅ Completado | Imágenes `linux/amd64`, push OK |
| 129 | AWS: crear ALB + TG + Listener (se había borrado) + task-def rev 5 + service desired=1 | Deploy AWS | ✅ Completado | Nuevo ALB DNS: `multiagente-alb-673139873.sa-east-1.elb.amazonaws.com`. TG healthy. Rollout COMPLETED |
| 130 | AWS: actualizar Amplify env var `BACKEND_URL` al nuevo ALB + trigger build | Deploy AWS | ✅ Completado | Job 8 lanzado |
| 131 | QA: validar online (login, listado, detalle, landing, form leads) | QA | ✅ Completado | Amplify job 9 SUCCEED. `/gloma` 200, `/login` 200, `POST /api/login` 200, `POST /api/landing/leads` 200, `GET /api/bots` devuelve los 2 bots seed (`catalogo_talulah` + `Confirmación de pedido`) |
| 132 | Commit + push Sprint 10 + Sprint 11 | PM | ✅ Completado | Commit `fc397a6` en `main` |

---

## Sprint 12 - Dominio propio glomabeauty.com

**Rama**: trabajo directo en `main`.

**Contexto**: el CEO compró `glomabeauty.com` en HostGator y quiere usarlo en
lugar del subpath `/gloma` y del dominio por defecto de Amplify. Se decide la
ruta profesional: **delegar la zona DNS a Route 53** para poder manejar apex +
www + subdominios futuros (`app.`, `api.`) con ALIAS/CloudFront nativamente,
en vez de quedar atados al CNAME-at-apex que HostGator no soporta.

### Arquitectura DNS

```
Registrador del dominio:    HostGator (glomabeauty.com)
                            │
                            ▼ (nameservers apuntan a)
Route 53 Hosted Zone:       Z0523904259PXITAV9OOV
   - glomabeauty.com        A (alias)  → CloudFront de Amplify
   - www.glomabeauty.com    CNAME      → CloudFront de Amplify
   - _e642...validation     CNAME      → ACM validation record
                            │
                            ▼
Amplify app:                d1cfl9ey07f61o (branch: main)
                            │
                            ▼
CloudFront distribution:    dzbhyoqtp2mc4.cloudfront.net
                            + ACM certificate (auto-managed por Amplify)
                            │
                            ▼
Frontend Next.js            → /api/* (rewrite proxy)
                            ▼
ALB:                        multiagente-alb-673139873.sa-east-1.elb.amazonaws.com
                            ▼
ECS Fargate backend (FastAPI) → RDS
```

### Tareas del Sprint 12

| # | Tarea | Agente | Estado | Notas |
|---|-------|--------|--------|-------|
| 133 | Crear hosted zone `glomabeauty.com` en Route 53 | Deploy AWS | ✅ Completado | Zone `Z0523904259PXITAV9OOV`. 4 nameservers entregados al CEO |
| 134 | Cambiar nameservers en HostGator apuntando a Route 53 | CEO | ✅ Completado | Propagación instantánea desde proveedor |
| 135 | `aws amplify create-domain-association` con apex + www | Deploy AWS | ✅ Completado | `--enable-auto-sub-domain` para que Amplify maneje los CNAMEs |
| 136 | DNS records (ACM validation + apex A-alias + www CNAME) | Deploy AWS | ✅ Completado | Amplify creó los records automáticamente al detectar la zone |
| 137 | Esperar validación ACM y status `AVAILABLE` de Amplify | Deploy AWS | ✅ Completado | Tomó ~2 min tras cambio de nameservers |
| 138 | Smoke test HTTPS + API | QA | ✅ Completado | `https://glomabeauty.com` 200, `https://www.glomabeauty.com` 200, `/login` 200, `POST /api/login` 200 |
| 139 | Commit + push Sprint 12 | PM | ⬜ En curso | |

### Follow-ups abiertos (no bloqueantes)

- Redirigir `www.glomabeauty.com` → `glomabeauty.com` (o al revés) para una sola URL canónica. Hoy ambas funcionan con el mismo contenido.
- Mover la plataforma interna a un subdominio `app.glomabeauty.com` para separarla semánticamente de la landing (cuando el equipo escale).
- Cuando se cree webhook público de Meta: usar `api.glomabeauty.com` apuntado al ALB directamente (con Listener HTTPS y cert ACM propio en `sa-east-1`).

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
| 2026-04-10 | PM | Sprint 7 retomado. Regla permanente paridad BD local↔AWS añadida a CLAUDE.md. |
| 2026-04-10 | Experto BD | Migración `migrate_sprint7_add_columns.py` creada (idempotente, `ADD COLUMN IF NOT EXISTS`). Aplicada en RDS vía `aws ecs run-task`. `users` ahora tiene `created_at`. |
| 2026-04-10 | Deploy AWS | `aws ecs update-service --force-new-deployment` → `create_all()` recreó `meta_accounts` con el schema nuevo. Service estable en task-def rev 3. |
| 2026-04-10 | QA | Validación E2E contra ALB: register + login + GET/POST/DELETE meta-account + teams/me. POST con token falso → 400 sanitizado. |
| 2026-04-10 | QA | Smoke test local con docker-compose + venv dedicado. Migración aplicada al volumen local (regla paridad BD). Fix SQLAlchemy 1.4 en el script (engine.begin()). E2E: register, login, GET meta-account, POST con validación Pydantic, teams/me con permisos owner. |
| 2026-04-10 | Deploy AWS | docker-compose.yml: APP_ENCRYPTION_KEY con fail-fast, APP_ENV y META_API_VERSION como defaults. |
| 2026-04-10 | PM | PR #2 mergeado a main (squash) → commit `41b0a9a`. |
| 2026-04-10 | Deploy AWS | Amplify: env vars BACKEND_URL + NEXT_PUBLIC_BACKEND_URL añadidas al app. Job 6 SUCCEED. Proxy Next.js /api/* → ALB validado (HTTPS Amplify → HTTP ALB sin mixed content). |
| 2026-04-10 | PM | Documento `PRUEBAS_SPRINT_7.md` creado con instrucciones paso a paso para probar el módulo de mensajes en AWS y local. **Sprint 7 DONE**. |
| 2026-04-23 | PM | Sprints 0-5 cerrados. Tareas pendientes consolidadas en Sprint Pendientes. Tareas completadas implícitamente en Sprints 6-7 marcadas como ✅ en sus sprints de origen. |
| 2026-04-24 | Dev Plataforma | Fix login local: `BACKEND_URL` como `ARG` en `Dockerfile.frontend` (Next.js bakea rewrite destino en build); `docker-compose.yml` pasa `build.args.BACKEND_URL=http://backend:8000`. Rebuild frontend. |
| 2026-04-24 | PM | Sprint 8 arrancado. Rama planificada `feature/modulo-bots-readonly`. 17 tareas (86-102). |
| 2026-04-24 | Experto BD | Modelos `Bot`/`BotStep` + migración idempotente `migrate_sprint8_add_bots.py` (`CREATE TABLE IF NOT EXISTS` + índices). Aplicada local. |
| 2026-04-24 | Dev Plataforma | Schemas Pydantic + CRUD con parseo CSV→`List[str]` y JSON→`dict`. Router `/bots` con 2 GET. Seed: 2 bots para `prueba@gmail.com` (`catalogo_talulah` 5 pasos + `Confirmación de pedido` premium). |
| 2026-04-24 | Dev Plataforma | UI `/bots`: tabla estilo mock con tabs "Tus bots" + badge verde, iconos de canales (W/I/M), diamante dorado premium, acciones deshabilitadas. Link azul con `target="_blank"`. |
| 2026-04-24 | Dev Plataforma | UI `/bots/[id]`: pantalla completa sin sidebar, fondo grid, nodos con color-coded por tipo de paso, conexiones SVG bezier punteadas con flecha. Botones Guardar/Probar/Más deshabilitados (vista read-only). |
| 2026-04-24 | QA + Seguridad | Validación E2E: `prueba@gmail.com` ve 2 bots, detalle OK con 5 pasos + next_step_id. Multi-tenant: `otro@test.com` → `[]` y 404 al acceder `/bots/1`. |
| 2026-04-24 | PM | Sprint 9 arrancado: dueño = cuenta, triggers, export JSON, simulador pop-up. Índice de sprints añadido al inicio de BITACORA. |
| 2026-04-24 | Experto BD | Migración Sprint 9: `bots.user_id` (FK users, backfill desde team.owner), `trigger_type`, `trigger_config`, drop `is_premium`, UNIQUE parcial `uq_one_default_bot_per_user`. Aplicada en local. |
| 2026-04-24 | Dev Plataforma | Motor `services/bot_engine.py` puro/stateless (reutilizable simulación ↔ webhook real). Endpoints `GET /bots/export` (JSON con `Content-Disposition`) y `POST /bots/{id}/simulate` ({actions, next_state, finished}). Seed con triggers actualizados. |
| 2026-04-24 | Dev Plataforma | UI `/bots` minimalista: sin Plantillas, sin iconos, sin Acciones, sin premium, sin "Agregar". Columna Activación con badges ⭐/🔑/🔗. Botón descargar JSON. UI `/bots/[id]`: solo "Probar Chatbot" + modal pop-up con chat WhatsApp-style. |
| 2026-04-24 | QA | E2E post-Sprint 9 OK: login, listado (2 bots con triggers), export JSON (1827 bytes), simulate multi-turno (turno 1: say+ask; turno 2 input="catalogo": say_media+say+end finished=true), multi-tenant: `otro@test.com` ve [] y 404. |
| 2026-04-24 | PM | Sprint 10 + Sprint 11 planeados con agentes asignados (tareas 115–132). |
| 2026-04-24 | Experto BD + Dev Plataforma | Sprint 10 código completo: tablas `bot_sessions`/`bot_pending_actions`, `services/bot_router.py` y `services/bot_runner.py`, dedupe por `meta_message_id` en webhook, endpoint `/internal/bot-scheduler/tick`. |
| 2026-04-24 | Dev Plataforma | Sprint 11: landing `/gloma` con identidad completa (Syne/Inter, paleta rosa empolvado + marrón tierra, 7 assets en `public/gloma/`). Endpoint `/landing/leads` con rate-limit 5/IP/h. |
| 2026-04-24 | Deploy AWS | Reactivación total de servicios AWS: RDS arrancado, imagen `:sprint11` en ECR, ALB nuevo (`multiagente-alb-673139873`), task-def rev 5, service desired=1 healthy. Migraciones 8+9+10+11 aplicadas en RDS, seed para `ceo@gloma.co`. |
| 2026-04-24 | Deploy AWS | Amplify env vars actualizadas al nuevo ALB DNS. Job 9 SUCCEED. |
| 2026-04-24 | QA | Validación E2E online: `https://main.d1cfl9ey07f61o.amplifyapp.com/gloma` OK, `/login` OK, `/bots` devuelve 2 bots. Plataforma y landing online. |
| 2026-04-24 | Deploy AWS | Sprint 12: hosted zone `glomabeauty.com` en Route 53 (`Z0523904259PXITAV9OOV`). Domain association en Amplify con apex + www, ACM cert auto-validado. |
| 2026-04-24 | CEO | Nameservers de `glomabeauty.com` cambiados en HostGator a los 4 de Route 53. |
| 2026-04-24 | QA | Smoke test dominio propio: `https://glomabeauty.com`, `https://www.glomabeauty.com`, `/login` y `POST /api/login` todos 200. Landing Gloma ahora vive en la raíz del dominio. |
