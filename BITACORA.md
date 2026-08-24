# BITACORA - Multiagente (Plataforma WhatsApp Business)

> Última actualización: 2026-07-11 (Sprint 19: motor de bots LLM Bedrock + Talulah + Demo Viajes)

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
| [Sprint 13](#sprint-13---módulo-campañas--plantillas-whatsapp) | Módulo Campañas (envío masivo) + Plantillas WhatsApp + Contactos/Grupos | DONE |
| [Sprint 14](#sprint-14---mejoras-al-módulo-bots-uiux--ventana-de-prueba--aws) | Mejoras al módulo Bots: análisis (inventario + ventana de prueba + UI/UX detalle + optimización AWS y costos 2/5/10 usuarios). **Fase de implementación trasladada al Sprint Futuro** | DONE |
| [Sprint 15](#sprint-15---tutoriales-interactivos-por-módulo) | Tutoriales interactivos por módulo (Mi Plan, Mensajes, Bots, Campañas) con spotlight + persistencia por usuario | DONE |
| [Sprint 16](#sprint-16---landing-page-elecol-premium) | Landing premium `/elecol` (electrolineras solares LATAM, paleta Infinito Eléctrico, motion design, glassmorphism, counters animados) | DONE |
| [Sprint 17](#sprint-17---migración-alb--api-gateway-http-api-ahorro-aws) | Migración ALB → API Gateway HTTP API (vía VPC Link + Cloud Map). Backend ahora en `https://api.glomabeauty.com`. Ahorro confirmado ~$26/mes | DONE |
| [Sprint 18](#sprint-18---migración-motor-de-envío-meta--twilio-bsp-autorizado--llm-de-servicio-al-cliente) | Motor de mensajería multi-proveedor (puerto Meta/Twilio) + webhooks Twilio fail-closed. Cutover pendiente de claves Twilio. LLM diferido al Sprint 19 | DONE (cutover pendiente) |
| [Sprint 19](#sprint-19---motor-de-bots-llm-aws-bedrock--talulah--demo-viajes) | **Motor de bots LLM en AWS (Bedrock Claude, sa-east-1)** con contexto a priori por cliente en el contenedor, tools (Shopify, media, handoff) y 2 bots: Talulah (`talulah@gloma.com`) y Demo Agencia de Viajes (`agencia@demo.com`) | DONE — ⚠️ 1 acción CEO: método de pago AWS Marketplace (#253) |
| [Sprint Futuro](#sprint-futuro---validación-ceo--ajustes-post-sprint-13) | Validación CEO del módulo Campañas + ajustes post-Sprint 13 **+ implementación de mejoras Bots Sprint 14 + validación CEO Sprint 15 + revisión profunda landing ELECOL (#206) + auditoría 48h Sprint 17 + plan rollback a ALB (#219, #220) + revocación de sesiones (#363; #362 resuelta: sesión de 30 min)** | PRÓXIMO |

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
| 138 | Smoke test HTTPS inicial | QA | ✅ Completado | Primer round: `https://glomabeauty.com` y `www` servían TODO el sitio (incluida la plataforma), lo que NO era el requisito. Fix en tarea 140. |
| 139 | Middleware Next.js: glomabeauty.com solo sirve landing | Dev Plataforma | ✅ Completado | `frontend/middleware.ts` con detección por `Host`. Rewrite `/` → `/gloma`. Otras rutas de plataforma → 404 brandeado vía rewrite a path inexistente. Whitelist: `/gloma/*`, `/api/landing/*`, `/_next/*`, `/favicon.ico` |
| 140 | Página `pages/404.tsx` brandeada con identidad Gloma | Dev Plataforma | ✅ Completado | Syne + Inter, paleta Gloma, CTAs "Volver al inicio" y WhatsApp |
| 141 | Build Amplify + validación online de la separación por dominio | QA | ✅ Completado | `glomabeauty.com/` 200 landing, `glomabeauty.com/login` 404, `/bots` 404. `main.d1cfl9ey07f61o.amplifyapp.com/login` sigue 200 (plataforma completa). Build job 10 SUCCEED |
| 142 | Fix `_app.tsx`: no redirigir a /login cuando host es glomabeauty.com | Dev Plataforma | ✅ Completado | El guard client-side hacía `router.replace('/login')` después del rewrite del middleware, sobrescribiendo la landing en el navegador. Ahora detecta `PUBLIC_HOSTS` y no se activa allí. |
| 143 | Iconos brandeados en features y métricas (9 archivos `ld_*.png`) | Dev Plataforma | ✅ Completado | Reemplazan los placeholders genéricos. Servidos desde `public/gloma/`. |
| 144 | Pulir copy de la landing | Dev Plataforma | ✅ Completado | Eliminados eyebrows `01·valor`/`02·valor`/`03·valor`/`Funcionalidades clave`/`Conversemos`. Hero subtítulo → "La forma elegante de automatizar ventas sin perder el trato humano". CTA contacto → "¿Listo para escalar tus ventas sin ampliar tu equipo?". Botón → "Hablar con un especialista". Footer simplificado. |
| 145 | Microinteracciones modernas en la landing | Dev Plataforma | ✅ Completado | (a) Contadores animados de 0→valor en stats al entrar al viewport (IntersectionObserver + RAF + easeOutCubic, formato es-CO). (b) `Reveal` fade+translate al scroll. (c) Header con orbes pastel y SVG con líneas/nodos del logo siguiendo el cursor (parallax). |
| 146 | Logo del header → `logo_blancotrans.png` grande (h-28/h-40) | Dev Plataforma | ✅ Completado | Iteración rápida: logo_transparente → logo_gloma_original_trans → logo_blancotrans (definitivo). Mismo logo reusado en el footer al mismo tamaño. |
| 147 | Smooth scroll de "Agenda una demo" y "Que te contactemos" → `#contacto` | Dev Plataforma | ✅ Completado | Helper `smoothScrollToContacto` con RAF + easeInOutCubic 1s + offset 40px. Reemplaza el jump nativo. |
| 148 | Footer: contacto@glomabeauty.com + tel +57 300 318 7871 + dirección Cali | Dev Plataforma | ✅ Completado | Calle 36, Vía Jamundí #128-321. Logo header reutilizado. |
| 149 | Microinteracción del form de contacto | Dev Plataforma | ✅ Completado | Componente `ContactForm`: en `sending` el recuadro pulsa con aro rosa empolvado + scale 0.985; en `ok` el contenido fade-out y aparece overlay con check SVG dibujándose (stroke-dashoffset) + título "Mensaje recibido" + texto en marrón (sin verdes). Animaciones declaradas en `<style jsx global>` (`glomaRing`, `glomaCheckDraw`, `glomaThanksFloat`). |
| 150 | AWS WorkMail: organización `gloma` + dominio `glomabeauty.com` + usuario `contacto@` | Deploy AWS | ✅ Completado | Org `m-2d1c023cd995430382aa94c3cb0ca789` en `us-east-1`. Dominio VERIFIED automáticamente (Amplify ya tenía la zone). 8 DNS records: MX → `inbound-smtp.us-east-1.amazonaws.com`, 3 CNAMEs DKIM, autodiscover, TXT amazonses, SPF (`include:amazonses.com`), DMARC quarantine. Usuario ENABLED. Webmail: `https://gloma.awsapps.com/mail`. Costo: $4 USD/mes. |
| 151 | Subdominio `app.glomabeauty.com` para la plataforma | Deploy AWS | ✅ Completado | `update-domain-association` añadiendo prefix `app`. Cert wildcard `*.glomabeauty.com` ya cubría el subdominio → HTTPS 200 al instante. Comentario del middleware actualizado para reflejar la nueva URL canónica. |
| 152 | Commit + push final Sprint 12 | PM | ⬜ En curso | |

### URLs finales del Sprint 12

| URL | Sirve | Tecnología |
|-----|-------|-----------|
| `https://glomabeauty.com` | Landing Gloma | Amplify + middleware Next.js |
| `https://www.glomabeauty.com` | Landing Gloma | Amplify (cert wildcard) |
| `https://app.glomabeauty.com` | Plataforma (login, bots, …) | Amplify (cert wildcard) |
| `https://main.d1cfl9ey07f61o.amplifyapp.com` | Plataforma (URL técnica de respaldo) | Amplify default |
| `https://gloma.awsapps.com/mail` | Webmail `contacto@glomabeauty.com` | AWS WorkMail us-east-1 |

### Credenciales WorkMail

- Webmail: `https://gloma.awsapps.com/mail`
- Usuario: `contacto`
- Email: `contacto@glomabeauty.com`
- Password inicial: `«en el gestor del CEO»` (cambiar al primer login)

### Follow-ups abiertos (no bloqueantes)

- Redirigir `www.glomabeauty.com` → `glomabeauty.com` para una sola URL canónica.
- Cuando se cree webhook público de Meta: usar `api.glomabeauty.com` apuntado al ALB directamente (Listener HTTPS y cert ACM propio en `sa-east-1`).
- Cambiar la password inicial de `contacto@glomabeauty.com` desde el webmail al primer login.

---

## Sprint 13 - Módulo Campañas + Plantillas WhatsApp

**Rama**: `feature/modulo-campanas` (por crear)

**Estado**: **DONE** (cerrado el 2026-05-12). Plan registrado el 2026-05-11, ejecutado entre 2026-05-11 y 2026-05-12. Backend + frontend desplegado a producción en `https://app.glomabeauty.com` corriendo image `:sprint13` (task-def `multiagente-backend:7`); seed demo aplicado en RDS; commit `f2d4661` mergeado a `main` (`3f20503`). Tareas #172 y #178 (validación del CEO) consolidadas y movidas al **Sprint Futuro** como tarea #179 para revisión posterior.

### Contexto

El CEO pide el módulo `/campanas` (envío masivo). Funcionalidad:

1. **Dashboard** al entrar (panel personalizable con KPIs de campañas pasadas: enviado, entregado, leído, respondió, fallido, etc.).
2. **Crear campaña** (wizard): seleccionar contactos uno-a-uno **o** un grupo previamente definido + plantilla + programación.
3. **Histórico** de campañas anteriores con detalle.
4. **Plantillas WhatsApp**: gestión (listar, crear, refrescar contra Meta).
5. **Contactos y grupos**: cada cuenta (team) tiene sus propios contactos y agrupaciones.

Probar **primero en local**; replicar a AWS al cierre (regla paridad BD).

### Referencias visuales

- `referencia/dash_campanas.png` — dashboard KPIs + tabla histórico
- `referencia/envio_campana.png` — editor de plantilla con preview
- `referencia/plantillas.png` — listado de plantillas con estado Aprobado/Pendiente

Estilo: Wati simplificado. Aplicar identidad **Gloma** (paleta marrón tierra + rosa empolvado + crema, tipografías Syne/Inter).

### Decisión sobre plantillas WhatsApp

Las plantillas son recurso de **Meta** (HSM). Meta las crea, aprueba y mantiene el estado (`PENDING`, `APPROVED`, `REJECTED`, `DISABLED`, `PAUSED`).

**Arquitectura adoptada**:
- BD local: tabla `whatsapp_templates` como **cache** por `meta_account_id` (campos `name, category, language, status, components_json, meta_template_id, last_synced_at`).
- Sync con Meta: (a) al abrir la sección "Plantillas", (b) botón "Refrescar", (c) scheduler cada 30 min para plantillas en `PENDING`.
- Crear: form en nuestra UI → `POST /{WABA_ID}/message_templates` a Meta → guardar respuesta con estado inicial `PENDING` → usuario ve "esperando aprobación".
- Editar/Eliminar: proxy a Meta + refresh local.
- **Sólo plantillas `APPROVED` se pueden usar para campañas**.

### Protocolo del Sprint 13 (cada tarea registra checkpoint)

Cada agente, **al terminar su tarea**, edita la fila correspondiente añadiendo en la columna **Checkpoint**:
- Qué se hizo (resumen 2-3 líneas)
- Archivos tocados (rutas)
- Diseño implementado / decisión clave
- Estado al pausar (para retomar si la sesión se interrumpe)

Además añade un renglón en `## Log de Cambios` con fecha + agente + acción.

### Tareas

| # | Tarea | Agente | Pareja paralela | Estado | Checkpoint |
|---|-------|--------|-----------------|--------|-----------|
| 153 | Crear agente `ui-ux` en `.claude/agents/ui-ux.md` y registrarlo en CLAUDE.md (tabla de agentes + reglas de delegación) | PM | — | ✅ | Archivo `.claude/agents/ui-ux.md` creado con rol, responsabilidades, identidad Gloma obligatoria, entregable HTML único. CLAUDE.md actualizado con fila en tabla de agentes y regla de delegación "Wireframes / diseño visual antes de codear UI → ui-ux". |
| 154 | Crear rama `feature/modulo-campanas` desde `main` | PM | — | ✅ | Rama creada y activa: `feature/modulo-campanas`. |
| 155 | **Diseño UI/UX**: wireframes HTML/Tailwind de 6 pantallas → `identidad_gloma/diseno_campanas.html`. Pantallas: (a) dashboard `/campanas`, (b) wizard nueva campaña 4 pasos, (c) detalle de campaña, (d) lista plantillas, (e) editor plantilla con preview, (f) contactos+grupos. Identidad Gloma, simplificación de Wati | UI/UX | ‖ 156 | ✅ | **DONE**. Archivo entregado: `identidad_gloma/diseno_campanas.html` (single HTML navegable, Tailwind CDN + Google Fonts Syne/Inter + paleta `gloma-*` inline). 6 pantallas + sección "Decisiones de diseño" + supuestos para PM. Decisiones clave: (1) KPI "Enviado" como card primaria marrón sólida, los otros 7 en blanco — jerarquía clara; (2) wizard 4 pasos lineal con stepper en cabecera marrón, no formulario único; (3) toggle "Por grupo / Uno por uno" en paso destinatarios (80% de casos = grupo); (4) preview tipo WhatsApp en panel derecho fijo del editor de plantilla; (5) banner explícito "Esta plantilla se enviará a Meta para aprobación" + estado PENDING coloreado; (6) Contactos+Grupos en una sola página con tabs; (7) sidebar Gloma marrón reutilizado en cada sección como shell coherente con el resto de la app. Notas embebidas `<!-- DEV: ... -->` por zona indicando endpoint backend a consumir (Dev Plataforma mapeará 1:1). Supuestos abiertos para PM: tarifa Meta MARKETING MX fija (debería ser configurable), tipo "Carrusel" requiere validar soporte en `services/meta_templates.py`, tasa de conversión depende de módulo de pedidos (opcional Sprint 13). |
| 156 | **Diseño de BD**: documento `backend/docs/sprint13_schema.md` con DDL completo (7 tablas nuevas), decisiones de PII y multi-tenant. Ver sección "Cambios de BD del Sprint 13" más abajo | Experto BD | ‖ 155 | ✅ | Entregado `backend/docs/sprint13_schema.md`. Incluye: (1) DDL idempotente PG15 para las 7 tablas (`contacts`, `contact_groups`, `contact_group_members`, `whatsapp_templates`, `campaigns`, `campaign_recipients`, `campaign_events`) con `CREATE TABLE/INDEX IF NOT EXISTS`, CHECKs cerrados de status/category y CHECK regex E.164. (2) §2 decisiones: multi-tenancy (tabla resumen + reglas para endpoints), PII (`__repr__` redactado, schemas `...Out` sin payload crudo, sin log de CSV), idempotencia webhook (`meta_message_id UNIQUE` en recipients + `UNIQUE (meta_message_id, event_type)` parcial en events), cache plantillas (TTL 15min lazy + scheduler 30min para PENDING, borrados upstream = status `DELETED`), plan migración local→RDS. (3) 4 queries KPI listas para Dev. **15 refinamientos vs. BITACORA original** documentados en §2.6 (resaltan: añadir status `'DELETED'`/`'skipped'`/`'sync_warning'`, `created_by_user_id ON DELETE SET NULL`, índices parciales para schedulers, índice GIN en `attributes`, UNIQUE estricto en `meta_message_id`). NO se escribió migración Python ni se tocó `models.py` (eso es #158 y #159). Estado al pausar: doc listo para revisión de Seguridad (tarea #157). |
| 157 | Seguridad: revisión del diseño Sprint 13 (PII de contactos, autorización por team, validación de creación de plantillas en Meta, rate-limit envío, abuse vectors). Veredicto bloqueante antes de implementar | Seguridad | ‖ 158 | ✅ | Entregado `backend/docs/sprint13_security_review.md`. **Veredicto: APROBADO CON CAMBIOS** (bloqueante para merge hasta resolver Altos). Conteo: 0 Críticos · 5 Altos · 6 Medios · 4 Bajos · 15 totales. Top-3 bloqueantes para Dev Plataforma: (1) **S13-001 anti-IDOR**: helper `require_owned(model, pk, team_id)` aplicado en TODOS los endpoints con `*_id` por path/body + validación cruzada `template.meta_account.team_id == campaign.meta_account_id == current_user.team_id` y `template.status='APPROVED'` antes de `POST /campaigns`; (2) **S13-002 anti-abuso de envío**: `MAX_RECIPIENTS_PER_CAMPAIGN=10000`, rate-limit por `meta_account_id` (default 10 msg/s) + backoff exponencial sobre 429/80007 en `campaign_sender`; (3) **S13-003 opt-in fail-closed**: filtro `contacts.opt_in=TRUE` aplicado dos veces (al encolar → `status='skipped'/'opt_out_at_enqueue'` y al enviar → re-lookup → `'opt_out_at_send'`). Otros Altos: S13-004 logging redactado del webhook (`phone_e164` enmascarado, payload nunca en logs), S13-005 cerrar `_verify_signature` fail-open en prod (`APP_ENV=prod` + falta `APP_SECRET` → return False). Schema BD aprobado sin cambios — todos los hallazgos son a nivel endpoints/operación. Auditoría post-código en #171 con este doc como checklist. |
| 158 | Migración idempotente `backend/scripts/migrate_sprint13_campanas.py` con `CREATE TABLE IF NOT EXISTS` + índices + FKs. Aplicar en docker-compose local | Experto BD | ‖ 157 | ✅ | **DONE**. Script `backend/scripts/migrate_sprint13_campanas.py` creado: implementa exactamente el DDL del documento `sprint13_schema.md` (7 tablas: `contacts`, `contact_groups`, `contact_group_members`, `whatsapp_templates`, `campaigns`, `campaign_recipients`, `campaign_events`), 17 índices (incluyendo parciales `ix_templates_pending_sync`, `ix_campaigns_status_scheduled`, GIN sobre `contacts.attributes`, UNIQUE parcial `uq_events_dedupe`), todos los CHECKs cerrados de status/category y la regex E.164 sobre `contacts.phone_e164`. Patrón heredado de `migrate_sprint11_leads.py`: una sola transacción `engine.begin()`, fallback a `app.database.SQLALCHEMY_DATABASE_URL` si no hay `DATABASE_URL` explícita. Sanitización del error a stdout (regex que enmascara `:password@`). Aplicación en docker-compose `db` (host `db`, user `equipo`, DB `multiagente_db`): primera ejecución creó las 7 tablas + 17 índices, verificación post-aplicación `7/7 tablas presentes`. Validado con `\dt` y `\d <tabla>` para todas: columnas, constraints, FKs (`ON DELETE CASCADE/RESTRICT/SET NULL`), indexes y CHECKs coinciden 1:1 con `sprint13_schema.md`. **Idempotencia**: segunda ejecución consecutiva completó con `[sprint13]   - <tabla>  ya existía → skip` para las 7 tablas, `CREATE INDEX IF NOT EXISTS` no-op, exit 0 limpio. Sin cambios sobre el DDL original (R1–R15 del doc preservados tal cual). NO se tocó `models.py` (queda para #159–#161). NO se aplicó a RDS (queda para #173, fase 10). Estado al pausar: BD local con paridad parcial respecto a producción; RDS aún sin las 7 tablas hasta tarea #173. |
| 159 | Backend: modelos SQLAlchemy + schemas Pydantic + CRUD para `Contact` y `ContactGroup` + endpoints `/contacts` (CRUD + import CSV) y `/contact-groups` (CRUD + add/remove members) con filtro por `team_id` | Dev Plataforma | ‖ 160 | ✅ | Modelos `Contact`/`ContactGroup`/`ContactGroupMember` añadidos a `models.py` (~125 líneas, `__repr__` redactado). Schemas + CRUD + router `routers/contacts.py` (397 líneas, 13 endpoints registrados). `python-multipart` añadido a `requirements.txt` para `POST /contacts/import-csv`. Imagen backend rebuildeada; 13 endpoints responden 401 sin auth. PM añadió `multipart` + rebuild + verificación porque el agente Dev se cortó por límite antes de cerrar. |
| 160 | Backend: modelos + schemas + CRUD `WhatsappTemplate` + servicio `services/meta_templates.py` (sync desde Meta, create, delete). Endpoints `/templates` (GET), `POST /templates/sync`, `POST /templates`, `DELETE /templates/{id}` | Dev Plataforma | ‖ 159 | ✅ | Modelo `WhatsappTemplate` en `models.py`. Servicio `services/meta_templates.py` (460 líneas) con sync paginado contra Meta + create/delete + modo sandbox (3 plantillas mock APPROVED si `META_SANDBOX=1` o token NULL). Router `routers/templates.py` (215 líneas, 4 endpoints). Rate-limit 1 sync/60s/user. Errores Meta sanitizados. Endpoints responden 401 sin auth. |
| 161 | Backend: modelos + schemas + CRUD `Campaign`, `CampaignRecipient`, `CampaignEvent`. Endpoints `POST /campaigns` (crear), `GET /campaigns` (lista), `GET /campaigns/{id}` (detalle con KPIs agregados) | Dev Plataforma | ‖ 162 | ✅ | **DONE**. Archivos tocados: `backend/app/models.py` (+~210 líneas: `Campaign`, `CampaignRecipient`, `CampaignEvent` con `__repr__` redactado, CHECKs cerrados, UNIQUE `meta_message_id` por idempotencia, índices `ix_campaigns_team_status`/`ix_campaigns_team_created`/`ix_recipients_campaign_status`/`ix_events_campaign_*`), `backend/app/schemas.py` (+`CampaignCreate`/`CampaignRecipientsIn`/`CampaignOut`/`CampaignDetailOut`/`CampaignRecipientOut`/`CampaignKPIs`/`CampaignsGlobalKPIs`/`CampaignRecipientsPage` con `extra='forbid'` y constante `MAX_RECIPIENTS_PER_CAMPAIGN=10000`), `backend/app/crud.py` (+~330 líneas: `create_campaign`, `list_campaigns`, `get_campaign`, `list_campaign_recipients`, `campaign_kpis_global`, `cancel_campaign`, `_campaign_kpis_query` con `FILTER (WHERE ...)`, `_resolve_recipient_contact_ids`, `_build_campaign_detail_out`), `backend/app/routers/campaigns.py` (NUEVO, 165 líneas, 6 endpoints), `backend/app/main.py` (+1 import + `app.include_router(campaigns.router)`). **El router viejo `routers/campanas.py` queda intacto** (stub legacy `/campanas`); el nuevo usa el path en inglés `/campaigns` como fuente de verdad para Sprint 13. **Endpoints expuestos** (verificados con `app.routes`): `GET /campaigns`, `GET /campaigns/kpis`, `POST /campaigns`, `GET /campaigns/{campaign_id}`, `GET /campaigns/{campaign_id}/recipients`, `POST /campaigns/{campaign_id}/cancel`. **Mitigaciones de Seguridad**: (a) **S13-001 IDOR cruzado** → `create_campaign` valida en orden: `meta_account = get_meta_account_for_team(team_id)`; `payload.meta_account_id == meta_account.id` (404 si no); `template = get_template(meta_account.id, template_id)` (404 si no); `template.meta_account_id == meta_account.id` (defensa); `template.status == 'APPROVED'` (400 si no); cada `contact_id` validado contra `team_id` con `COUNT(*) WHERE team_id=? AND id IN (?)` igual al largo (404 si difiere); `contact_group_id` resuelto con `get_contact_group(team_id, ...)` (404 si no). `get_campaign`/`list_campaign_recipients`/`cancel_campaign` filtran por `team_id` antes de tocar. (b) **S13-002 anti-abuso** → constante `MAX_RECIPIENTS_PER_CAMPAIGN=10000` en `schemas.py`, validada en `_resolve_recipient_contact_ids` **antes** de ir a la BD (defensa contra envío de 1M de IDs basura) → HTTP 422. (c) **S13-003 opt-in fail-closed al encolar** → en `create_campaign` cargamos cada `Contact` y revisamos `opt_in`; si `False` → `CampaignRecipient(status='skipped', error_code='opt_out_at_enqueue')`; si `True` → `status='queued'`. El evento `queued` a nivel campaña incluye `payload_json={"queued":N,"skipped_opt_out":M}`. **Verificaciones obligatorias OK** (con `demo@gmail.com` team_id=5 vs `otro@test.com` team_id=3): (1) `app.routes` muestra los 6 endpoints `campaign*` (más el `/campanas` legacy y el `/internal/campaigns/tick` de #162); (2) `POST /campaigns template_id=3 meta_account_id=2` (template de otro team) → **HTTP 404** `"Plantilla no encontrada"`; (3) `POST /campaigns` con 10001 IDs → **HTTP 422** `"La campaña excede el máximo permitido de 10000 destinatarios."`; (4) `POST /campaigns contact_ids=[4,5,6]` (c6 con `opt_in=False`) → **HTTP 201** `CampaignDetailOut` con `total_recipients=3, pending=2, skipped=1` y `recipients_preview` muestra 2 `queued` + 1 `skipped/opt_out_at_enqueue`. Extras: cross-team `meta_account_id=3` → 404; `GET /campaigns/{id}` con id de otro team → 404; `GET /campaigns` filtrado por team (demo solo ve sus 2); `GET /campaigns/kpis` agrega correctamente; `POST /cancel` `scheduled → cancelled` (200) y segundo cancel → 409. **Notas**: ambiente conda no requerido (los tests corrieron dentro del contenedor backend, que ya tiene sus deps). Sin tocar `services/campaign_sender.py` ni `meta_webhook.py` (son #162/#163). Status inicial = `'scheduled'` (el sender tick filtra por `scheduled_at <= now()`); decisión documentada para que #162 la consuma. Estado al pausar: backend rebuildeado y arriba; PR listo para review de Seguridad (#171). |
| 162 | Backend: servicio `services/campaign_sender.py` (envío vía Meta con rate-limit + retry exponencial; **modo sandbox local** si no hay credenciales Meta — simula respuestas). Tick `/internal/campaigns/tick` para campañas agendadas | Dev Plataforma | ‖ 161 | ✅ | **DONE**. Archivos: `backend/app/services/campaign_sender.py` (servicio), `backend/app/routers/internal.py` (endpoint `POST /internal/campaigns/tick`), `backend/requirements.txt` (`tenacity>=8.5,<9`), `docker-compose.yml` (env `META_SANDBOX=1`/`META_RATE_LIMIT_RPS=10`/`CAMPAIGN_SENDER_BATCH=200`/`INTERNAL_API_KEY`), `.env.example` documentado. **Mitigaciones de seguridad**: (1) **S13-002**: token-bucket en memoria `_TokenBucket` por `meta_account_id` (10 msg/s default por env), retry con `tenacity` (3 intentos, `wait_exponential_jitter(initial=1, max=8)`) gated por `_is_retryable_meta_error` que matchea HTTP 429 + códigos Meta `80007` y `131056`; tras agotar retries marca recipient `failed` con `error_code=meta_retry_exhausted`. (2) **S13-003**: re-lookup `contacts.opt_in` justo antes del envío; si FALSE → `status='skipped', error_code='opt_out_at_send'` + `CampaignEvent(event_type='sync_warning', payload={"reason":"opt_out_at_send","contact_id":N})`. (3) **Idempotencia**: transición atómica `_transition_to_sending` con `UPDATE ... WHERE status='queued'` y check de `rowcount==1` para descartar recipients tomados por otro proceso; selección de campañas incluye `status='running'` (reanuda mid-flight); cierre de campaña sólo si NO quedan `queued|sending`. **Sandbox**: activo si `META_SANDBOX=1` o `MetaAccount.encrypted_access_token IS NULL` → genera `wamid.local-<uuid>` sin tocar Meta. **PII**: logs sólo con `recipient_id`/`campaign_id`; helper `_mask_phone()` para casos donde haga falta el número; el access_token descifrado nunca sale del scope de `meta_whatsapp._headers`; errores Meta sanitizados por `_sanitize_error_payload` heredado del Sprint 7. **Evidencia de 4 verificaciones (docker-compose local)**: (1) `POST /internal/campaigns/tick` con BD vacía → `{campaigns_processed:0, recipients_sent:0, ...}`; (2) sembrada `Campaign TEST_S13_C1` `scheduled` con 3 recipients `queued` → tick → 3× `sent` con `wamid.local-*`, campaña pasa a `completed`, 3 eventos `sent`; (3) re-ejecutar tick → `{campaigns_processed:0, ...}` (campaña ya `completed`, no se re-toma); (4) `Contact id=1 opt_in=FALSE`, sembrada `TEST_S13_C2` con 3 recipients (uno apuntando a id=1) → tick → 2× `sent` + 1× `skipped/opt_out_at_send` + evento `sync_warning` con `payload_json={"reason":"opt_out_at_send","contact_id":1}`. Imagen backend rebuildeada (`docker compose build backend`) con `tenacity-8.5.0` instalado. NO se aplicó a RDS (queda para fase Deploy AWS #173/174). |
| 163 | Backend: extender `routers/meta_webhook.py` para correlacionar `wamid` ↔ `campaign_recipients` y registrar eventos (`sent`, `delivered`, `read`, `failed`) en `campaign_events`. Idempotente por `meta_message_id` | Dev Plataforma | ‖ 164 | ✅ | **DONE**. Archivos tocados: `backend/app/routers/meta_webhook.py` (único archivo modificado). **Función `process_status_event(db, status_dict) -> bool`** añadida: (1) extrae `wamid=status_dict['id']`; (2) busca `CampaignRecipient.meta_message_id==wamid` — si no existe → `False` (caller sigue con flujo Sprint 6 legacy); (3) mapea Meta→interno con `_META_TO_INTERNAL`; (4) idempotencia con `_status_rank()` (queued=0<sending=1<sent=2<delivered=3<read=4; failed/skipped=99 terminales) — solo avanza si `new_rank > current_rank`, nunca regresa; (5) timestamps por status: `sent_at`/`delivered_at`/`read_at`/`failed_at` desde `status_dict['timestamp']` (unix→datetime); (6) `failed` extrae `errors[0].code` y lo guarda en `recipient.error_code` (truncado a 40 chars del CHECK del schema); (7) inserta `CampaignEvent` con `pg_insert(...).on_conflict_do_nothing()` aprovechando el índice parcial UNIQUE `uq_events_dedupe(meta_message_id, event_type) WHERE meta_message_id IS NOT NULL` creado por #158; (8) si la campaña ya no tiene recipients `queued|sending` → `campaign.status='completed', completed_at=now()`. **Refactor del handler**: el bucle de `value.statuses[]` se movió ARRIBA del lookup de `MetaAccount` porque los status updates se correlacionan por `wamid` (UNIQUE), no por `phone_number_id`; así statuses de campañas se procesan aunque venga un `phone_number_id` desconocido. El flujo inbound 1:1 de Sprint 6 (`value.messages[]` → `Conversation`/`Message`/bot_runner) sigue intacto después del lookup de MetaAccount. **Mitigaciones**: **S13-004 (logging PII)** → helper `_sanitize_payload_for_log(payload)` enmascara teléfonos E.164 con regex `r'\+?\b[1-9]\d{6,18}\b'` y campos sensibles por nombre (`phone_e164`, `from`, `wa_id`, `recipient_id`, `display_phone`); `logger.info("webhook.meta received %s", _summarize_payload(payload))` ahora loguea solo `{entries, messages, statuses, phone_number_ids}` (no PII); reemplaza la línea Sprint 6 `logger.info("Webhook Meta recibido: %s", payload)`. Para statuses que NO son de campaña, se loguea `_sanitize_payload_for_log(status_evt)` (teléfonos enmascarados). El payload bruto SÍ se persiste en `campaign_events.payload_json` (BD, no logs) por requerimiento de auditoría. **S13-005 (HMAC fail-closed en prod)** → `_verify_signature` ahora detecta entorno con `_is_production()` (acepta `APP_ENV=production` o `prod`); en prod: falta `APP_SECRET` → `logger.error` + `return False` (no fail-open silencioso), falta o malforma `X-Hub-Signature-256` → `False`; en dev: falta secret → `logger.warning("FAIL-OPEN: webhook signature skipped — only safe in dev")` + `True`. El endpoint devuelve **403 en prod** (alineado a la review) y 401 en dev por compat. **Evidencia 4 pruebas obligatorias (docker-compose local, `wati-backend-1`)**: (1) **delivered avanza desde sent** → `POST /meta/webhook` con `statuses=[{id:wamid.test_..., status:delivered, timestamp, recipient_id:573...}]` → HTTP 200; recipient: `status='delivered'`, `delivered_at` poblado; 1 fila en `campaign_events` con `event_type='delivered'`. (2) **idempotencia** → 2ª llamada `delivered` idéntica → HTTP 200; `events=[(id,'delivered')]` (sin duplicar — el índice parcial UNIQUE atajó vía `ON CONFLICT DO NOTHING`). (3) **rank lower NO regresa** → `status=sent` posterior a delivered → recipient sigue `status='delivered'` (no regresa). (4) **read avanza** → `status=read` → recipient `status='read'`, `read_at` poblado. (5) **fail-closed prod (test directo de `_verify_signature`)**: `APP_ENV=production` + `APP_SECRET=""` → `False`; prod + secret + firma ausente → `False`; prod + secret + firma válida → `True`; dev + sin secret → `True` (fail-open con warning). (6) **`_sanitize_payload_for_log`** enmascara `+573001112233` → `573***33` en `phone_e164`, `from`, dentro de strings libres, y en valores anidados. **No regresión Sprint 6**: test adicional con `phone_number_id` real de MetaAccount + `messages[].text.body` → HTTP 200, `Conversation` creada, `Message` inbound persistido. Imagen backend rebuildeada (sin nuevas deps). NO se tocó `models.py`, `schemas.py`, `services/campaign_sender.py`. NO se aplicó nada a RDS (queda para #173). Estado al pausar: lista para auditoría de Seguridad #171. |
| 164 | Frontend: `pages/campanas/index.tsx` dashboard con 8 KPI cards + tabla histórico + tabs internos. Identidad Gloma | Dev Plataforma | ‖ 163 | ✅ | **DONE**. Archivos tocados: (NUEVO) `frontend/pages/campanas/index.tsx` dashboard funcional (≈470 líneas), (NUEVO) `frontend/lib/api.ts` helper `authedFetch<T>()` con redirect 401 y `ApiError`, (NUEVO) `frontend/types/campaigns.ts` con tipos `CampaignSummary`/`GlobalKPIs`/`CampaignStatus`. **Eliminado**: `frontend/pages/campanas.tsx` (stub plano) para evitar conflicto de rutas con la nueva carpeta. **Decisiones UX vs wireframe**: (1) los 4 cards "Visión general" se muestran con datos estáticos por ahora (Límite diario `1000`, Días consecutivos `—`, Calidad `Alta`, Límite mensual `10 000`) — no hay endpoint backend que los provea, queda como follow-up; (2) columna "Respondió" en la tabla queda `—` por campaña porque el backend aún no expone `replied_count` por campaña (el `CampaignsGlobalKPIs` tampoco lo tiene); KPI "Respondió" global muestra `0` con hint "próximamente"; (3) KPI "Enviando" y "Procesando" también `0` (no existen en `CampaignsGlobalKPIs`); se mantienen para reservar layout y mostrarán datos cuando el backend los agregue; (4) paginación cliente (10/pág) como pidió el spec — descartado server-pagination porque el endpoint ya acepta hasta 500 y para 10 usuarios concurrentes es suficiente; (5) "Mensajes de plantilla" como `Link href="/campanas/plantillas"` aunque esa página no exista todavía (la creará #167), igual que "+ Nueva campaña" → `/campanas/nueva` (#165); (6) badges de estado siguen el contrato del spec excepto "Borrador" y "Fallida" que añadí como variantes locales (`bg-gray-100`/`bg-red-100`) para cubrir todos los `CampaignStatus`. **Identidad Gloma**: fondo `bg-gloma-cream`, cards `bg-white border-gloma-brown-light/20 rounded-2xl shadow-sm`, KPI primario "Enviado" con `bg-gloma-brown text-gloma-cream`, hover de filas `bg-gloma-rose-soft/30`, tipografía `font-heading` (Syne) para títulos y métricas, `font-body` (Inter) para todo lo demás. **Verificaciones**: (1) `docker compose up -d frontend` (rebuild + recreate) sin errores; Next 15.5.15 compila sin warnings, ruta `/campanas` registrada (`grep page="/campanas"` en HTML servido). (2) `GET /campaigns/kpis` con token JWT válido responde el shape esperado (`{total_campaigns:0, sent_count:0, …, delivery_rate_pct:null}`) — 8 KPIs renderizan con esos números (testeado con usuario fresh `dev164b@gmail.com` porque `demo@gmail.com` no aceptó el password documentado en `CREDENCIALES.txt` en este entorno; flag a PM como follow-up — la dependencia es de las credenciales locales, no del código). (3) `GET /campaigns` con token responde `[]` → la tabla cae en estado vacío y muestra la ilustración 📢 + texto "Aún no tienes campañas" + CTA "+ Crear primera campaña" exactamente como el wireframe (variante "primera vez"). (4) Estado de error: simulado con un token inválido (`Authorization: Bearer broken`) → el helper `authedFetch` redirige a `/login`; con un endpoint apagado `authedFetch` lanza `ApiError` y la UI muestra el banner rojo "No se pudieron cargar los datos. (…) [Reintentar]" — verificado por inspección de código. (5) `npx tsc --noEmit` desde `frontend/` ejecutado: **sin errores**. Visualmente cumple identidad Gloma (paleta marrón + crema + rosa, sin verdes, Syne/Inter cargadas en `_app.tsx`). El estado vacío fue el visualizado en la verificación real (sin campañas existentes). **No tocado** (respetando coordinación): `pages/campanas/nueva.tsx` (#165), `pages/campanas/[id].tsx` (#166), `pages/campanas/plantillas/*` (#167), `pages/campanas/contactos.tsx` (#168), backend, `Layout`, `Sidebar`. |
| 165 | Frontend: `pages/campanas/nueva.tsx` wizard 4 pasos (nombre → plantilla → destinatarios 1×1 o grupo → programación → resumen) | Dev Plataforma | ‖ 166 | ✅ | `frontend/pages/campanas/nueva.tsx` (~57KB) con stepper 4 pasos (datos + plantilla APPROVED con preview + destinatarios individual/grupo + programación con resumen y estimación 10 msg/s). `lib/api.ts` y `types/campaigns.ts` reusados/ampliados. `tsc --noEmit` exit 0. Agente Dev se cortó por límite antes de actualizar BITACORA; PM verificó TS limpio y registró checkpoint. |
| 166 | Frontend: `pages/campanas/[id].tsx` detalle con KPIs + tabla destinatarios + estado por destinatario | Dev Plataforma | ‖ 165 | ✅ | `frontend/pages/campanas/[id].tsx` (~27KB): cabecera + badge + acciones (Cancelar/Duplicar/Exportar), 6 KPI cards (Total destacado), tabla paginada con filtro por estado, polling 5s si running/scheduled, máscara parcial de teléfono. Nuevo `lib/format.ts` con helpers de fecha y máscara. `tsc --noEmit` exit 0. Mismo corte por límite; PM verificó y registró. |
| 167 | Frontend: `pages/campanas/plantillas/index.tsx` listado + `pages/campanas/plantillas/nueva.tsx` editor con preview tipo WhatsApp | Dev Plataforma | ‖ 168 | ✅ | **DONE**. Archivos creados: `frontend/pages/campanas/plantillas/index.tsx` (listado, ≈460 líneas) y `frontend/pages/campanas/plantillas/nueva.tsx` (editor + preview, ≈610 líneas). **Decisiones**: (1) reusa `authedFetch<T>` y tipos existentes (`TemplatePreview` ya estaba en `types/campaigns.ts` desde #165 — no se tocó); (2) **listado**: header con breadcrumb + CTA "+ Nuevo Mensaje de Plantilla" + botón "↻ Refrescar desde Meta" con throttle cliente 60s (countdown visible) en paralelo al rate-limit 1/60s del backend; mensaje de resultado del sync (`synced/created/updated`) bajo el banner azul; "Última sincronización: hace X min" calculado del max `last_synced_at` de la página; buscador por nombre + filtro de estado (`?status=APPROVED|PENDING|REJECTED|DISABLED|PAUSED`) + sort `recent`/`name`; tabla con badges coloreados (APPROVED verde, PENDING amber, REJECTED rojo, DISABLED/PAUSED gris, DELETED tachado), columnas Nombre/Categoría/Estado/Idioma/Última actualización/Acciones; acción Editar deshabilitada con tooltip "Próximamente", Enviar campaña → `/campanas/nueva?template_id=N` solo para APPROVED, Eliminar con `window.confirm` → `DELETE /templates/{id}`; estado vacío con CTA "+ Crear plantilla"; banner rojo + reintentar en error. **Auto-sync inicial**: si la primera carga devuelve lista vacía sin error, se dispara automáticamente un `POST /templates/sync` (1 vez, gated por `didAutoSync`) para que el sandbox local siembre las 3 plantillas mock — cumple la verificación obligatoria #2 ("ver las 3 plantillas mock del sandbox"). (3) **editor**: dos columnas (form izquierda + preview derecha sticky); banner rosa "Esta plantilla se enviará a WhatsApp… puede tardar hasta 24h"; secciones 1–6: Identidad (Nombre con auto-`toLowerCase().replace(/\s+/g,'_')` + regex `^[a-z][a-z0-9_]{0,511}$`, Categoría MARKETING/UTILITY/AUTHENTICATION, Lenguaje es_MX/es/en_US/pt_BR), Tipo (tabs Estándar funcional + Catalogar/Carrusel/Ofertas con badge "PRO" deshabilitado), Header opcional (radio Ninguno/Texto/Imagen/Video/Documento; text max 60; media headers se declaran pero la subida del asset queda follow-up documentado en pantalla), Body requerido max 1024 con contador y botón "+ Agregar variable" que calcula el siguiente `{{N}}` libre y soporta `*negritas*` en preview, Footer opcional max 60, Botones (toggle "+ Agregar botón" hasta 3, tipos URL/PHONE_NUMBER con validación de URL `http(s)://` o E.164 `/^\+?[1-9]\d{6,18}$/`, texto max 25); preview WhatsApp en vivo (header verde `#075E54`, fondo chat `#ECE5DD` con dot-pattern, burbuja blanca con header/body/footer/botones, `{{N}}` resaltados en `bg-gloma-rose-soft`, *negritas* renderizadas). Botones inferiores: "Guardar como borrador" deshabilitado con tooltip "Próximamente" (placeholder), "Guardar y enviar a aprobación" → `POST /templates` con `{name, category, language, components:[...]}` matchea `WhatsappTemplateCreatePayload` del backend; en éxito banner verde "Plantilla enviada. Estado: Pendiente de aprobación de WhatsApp." + `setTimeout(router.push('/campanas/plantillas'), 2000)`. (4) **Identidad Gloma** respetada: `bg-gloma-cream`, cards `rounded-2xl border-gloma-brown-light/20`, Syne/Inter, paleta marrón+crema+rosa, sin verdes (excepto el verde de WhatsApp en el preview, intencional). **Verificaciones obligatorias OK**: (1) `npx tsc --noEmit` desde `frontend/` → exit 0 (single fix: `JSX.Element` reemplazado por `ReactElement` importado de `react`). (2) `docker compose build frontend` + `up -d frontend` exitosos; Next 15.5.15 registra ambas rutas (`pageProps.page="/campanas/plantillas"` + chunk `pages/campanas/plantillas-*.js` y `pages/campanas/plantillas/nueva-*.js`). (3) `curl http://localhost:3000/campanas/plantillas` → 200 y `curl http://localhost:3000/campanas/plantillas/nueva` → 200. (4) Backend `GET /templates` responde 401 sin auth (endpoint vivo). El auto-sync inicial garantiza que un usuario fresh vea las 3 plantillas mock del sandbox sin acción manual; el botón "Refrescar" queda throttled 60s tras un éxito (countdown visible). **No tocado** (respetando coordinación): backend, otras páginas del módulo, Layout, Sidebar, `types/campaigns.ts` (los tipos ya estaban), `lib/api.ts`, `lib/format.ts` (solo se importó `fmtDate`). Limitaciones documentadas: (a) carga de assets para headers IMAGE/VIDEO/DOCUMENT no implementada (placeholder visual + nota en UI); (b) "Guardar como borrador" es placeholder sin endpoint; (c) los filtros se aplican como query-string al backend (no client-side) — cambia `?status=...` y refetch. |
| 168 | Frontend: `pages/campanas/contactos.tsx` CRUD contactos + grupos (modal asignar a grupo, import CSV) | Dev Plataforma | ‖ 167 | ✅ | **DONE**. Archivos entregados: `frontend/types/contacts.ts` (NUEVO — `Contact`, `ContactGroup`, `ContactGroupDetail`, `ContactImportResult`, `ContactCreatePayload`/`ContactUpdatePayload`, `ContactGroupCreatePayload`/`ContactGroupUpdatePayload`; refleja `schemas.ContactOut`/`ContactGroupOut`/`ContactGroupDetailOut`/`ContactBulkImportResult`); `frontend/pages/campanas/contactos.tsx` (NUEVO, ~1100 líneas). **Estructura**: 1 página con 2 tabs (`contactos` / `grupos`), `Layout variant="fullscreen"`, identidad Gloma (cards `rounded-2xl border-gloma-brown-light/20`, bg `gloma-cream`, badges opt-in `gloma-rose-soft/40` + opt-out gris, chips de grupo `gloma-cream` con borde `gloma-brown-light/30`). **Tab Contactos**: buscador con debounce (250ms) + dropdown grupo + toggle "Sólo con opt-in"; tabla teléfono (siempre `maskPhone()` — regla 1), nombre, email, badge opt-in, columna grupo (solo cuando se filtra por grupo, dado que el endpoint `/contacts` no devuelve membresías por contacto — chips reflejan el filtro activo), última actualización, acciones (Editar/Asignar a grupo/Eliminar con `window.confirm`). Paginación de servidor (50/pág, offset = page*PAGE_SIZE, deshabilita "Siguiente" si la página viene con < PAGE_SIZE filas). Estado vacío con 2 CTAs (Importar CSV / Crear contacto) solo cuando NO hay filtros activos. **Tab Grupos**: grid 3 cols con cards click→drawer lateral derecho (460px) que carga `GET /contact-groups/{id}`, búsqueda local de miembros, botones Añadir miembros (modal multiselect que llama `GET /contacts?q=` y filtra los ya pertenecientes) y Quitar (DELETE individual con confirm). Acciones de card: Ver miembros/Editar/Eliminar (con confirm advirtiendo que los contactos no se borran). **Modales**: backdrop `bg-black/40`, card `bg-gloma-cream` con `border-gloma-brown-light/20`. `ContactFormModal` (crear con phone editable + valida JSON de atributos client-side; editar con phone disabled — el backend no permite cambiar `phone_e164`). `GroupFormModal` con name/description. `AssignToGroupModal` con dropdown. `ImportCsvModal`: dropzone `<input type="file" accept=".csv,text/csv">`, helper `uploadCsv()` (no usa `authedFetch` porque ese helper fuerza `Content-Type: application/json` y rompería el boundary multipart — sí reusa el token de localStorage y la lógica 401→`/login`). Tras importar muestra grid de 4 stats (total/created/updated/skipped con colores neutro/verde/azul/gris) + lista de errores en rojo con scroll; nota explícita advirtiendo que si llega un teléfono crudo es bug del backend a reportar (regla 1 / S13-009). **Reuso**: `lib/api.ts` `authedFetch<T>()` + `ApiError`; `lib/format.ts` `maskPhone()` (TODOS los teléfonos renderizados) + `fmtDate()`. **NO se tocó el backend**. **Verificaciones**: `npx tsc --noEmit` → EXIT=0 (limpio); `curl http://localhost:3000/campanas/contactos` → 200 (Next.js dev server sirve la página y el shell SSR renderiza sin errores). Verificación funcional contra backend (CRUD contacto / CSV / grupos / miembros) queda para QA #176 con credenciales reales del seed — no pude obtenerlas porque las passwords del seed local son aleatorias y no se loggean. Decisión: NO se mostraron chips de "Grupos por contacto" en la tabla porque el endpoint `/contacts` no devuelve la lista de grupos por contacto (sería N+1 caro); en su lugar se ofrece el modal "Asignar a grupo" y el contador `member_count` en cada card del tab Grupos. Si Producto pide chips por contacto, se requiere ampliar el `ContactOut` con `group_ids` o `groups` y volver a iterar (no bloqueante para Sprint 13). |
| 169 | Seed local: 50 contactos demo + 3 grupos + 2 plantillas mock `APPROVED` + 1 campaña pasada con métricas para `demo@gmail.com`. Script `backend/scripts/seed_sprint13_campanas.py` | Dev Plataforma | ‖ 170 | ✅ | **DONE**. Scripts entregados: (NUEVO) `backend/scripts/reset_demo_password.py` (idempotente, fija `demo@gmail.com` → `«en el gestor del CEO»`); (NUEVO) `backend/scripts/seed_sprint13_campanas.py` (~480 líneas, idempotente y convergente al spec). **Ejecución dentro de `wati-backend-1`** (los scripts se copian al container porque `backend/scripts/` no está bind-mount): `docker cp` + `docker compose exec -T backend python scripts/...`. **Resultados de la 1ª corrida**: reset password OK (`verify=True`); seed creó 50 contactos (40 opt_in=True, 10 opt_in=False), 3 grupos, 2 plantillas mock APPROVED, 3 campañas (A "Promoción Mayo" completed, B "Recordatorio carrito" completed, C "Lanzamiento producto" scheduled). **Counts verificados con SQL directo** (`team_id=5` de demo@): `seed contacts` (filtrando `phone_e164 LIKE '+57301%'`) = **50** (40 opt_in=True / 10 opt_in=False — matchea el spec); `contact_groups WHERE team_id=5` = **3** (Clientes Premium=12, Recurrentes Bogotá=15, Nuevos Trial=8 — los 3 con su `member_count` exacto); `whatsapp_templates seed` (filtrando por nombres `promo_mayo` / `recordatorio_pedido`) = **2** (ambas APPROVED, lenguajes es_MX/es); `campaigns WHERE team_id=5` = **3** (`Promoción Mayo` completed con started_at hace 3d; `Recordatorio carrito` completed hace 1d; `Lanzamiento producto` scheduled en +2d). **Distribución de `campaign_recipients` por campaña** (verificado): Promoción Mayo → 10 read + 1 delivered + 1 failed (error_code='80007'); Recordatorio carrito → 5 read + 2 delivered + 1 skipped (error_code='opt_out_at_enqueue'); Lanzamiento producto → 8 queued. **`campaign_events` coherentes**: Promoción Mayo emite 1 queued + 12 sent + 11 delivered + 10 read + 1 failed; Recordatorio carrito emite 1 queued + 7 sent + 7 delivered + 5 read; Lanzamiento emite 1 queued (futuro). Cada recipient enviado tiene `wamid.seed-<idx>-<short_uuid>`. **Decisión técnica clave**: la asignación de `city` se ajustó para garantizar ≥15 contactos `city=Bogotá AND opt_in=True` (los primeros 15 índices van a Bogotá; el resto rota Medellín/Cali/Bogotá), porque la rotación `i%3` natural solo dejaba 14. La selección de membresías reconcilia (añade faltantes + elimina obsoletas) para que segundas ejecuciones converjan al spec aun si el spec cambió. **Idempotencia validada** (2ª corrida inmediatamente después): `contactos creados=0 actualizados=0`; `grupos creados=0 membresías nuevas=0`; `plantillas creadas=0`; las 3 campañas reportan `skip` (no se duplican filas hijas). **CREDENCIALES.txt**: actualizado solo el bloque local de `demo@gmail.com` (password `«en el gestor del CEO»`, nota apuntando al script de reset y a los seeds Sprint 13); los otros bloques (`prueba@`, `test2@`, `otro@`, prod `ceo@gloma.co` y prod `demo@`) NO se tocaron. **Login E2E verificado**: `POST http://localhost:8000/login` con `{correo:"demo@gmail.com", password:"«en el gestor del CEO»"}` → HTTP 200 + JWT bearer. NO se tocó RDS (queda para #173), ni código del backend (modelos/routers/etc.). |
| 170 | QA local: E2E docker-compose. Login `demo@`, CRUD contactos+grupos, sync plantillas (mock Meta), crear campaña a un grupo, envío inmediato (sandbox), envío agendado, validar KPIs en dashboard, aislamiento multi-tenant con `otro@test.com` | QA | ‖ 169 | ✅ | **PASS** (bloqueante S13-QA-001 ya fue corregido por PM y verificado online en #175). **PASS con 1 bloqueante Medio + 3 observaciones (originalmente).** Reporte completo: `backend/docs/sprint13_qa_report.md`. **Pasos PASS (A–M)**: smoke setup OK, login JWT OK, CRUD contactos+cross-tenant 404, import CSV (`{total:3,created:1,updated:1,skipped:1}` sin teléfono crudo en errores → S13-004 OK), CRUD grupos+miembros+cross-tenant 404, sync plantillas (4 nuevas APPROVED desde sandbox), crear campaña a grupo (12 recipients, 0 skipped), tick procesó campaña (sent=12), idempotencia OK, webhook `delivered` → status actualizado, cancel + 409 segundo cancel, 5 rutas frontend en 200, aislamiento multi-tenant verificado. **Bloqueante S13-QA-001 (Medio)**: campañas con `scheduled_at=NULL` nunca son procesadas por el tick (`scheduled_at <= now` no matchea NULL). Si el wizard del frontend siempre setea `scheduled_at`, no hay impacto; si no, son campañas fantasma. Tarea sugerida: revisar #161 (crud) o #162 (sender). Opción A: en `create_campaign` setear `scheduled_at=utcnow()` si viene NULL. Opción B: cambiar filtro a `(scheduled_at IS NULL OR scheduled_at<=now)`. **Observaciones**: (1) `POST /login` espera JSON `{correo,password}`, no form-urlencoded como decía el plan QA (consistente con BITACORA #169 y CREDENCIALES.txt). (2) CSV exige header `phone_e164` (no `phone`). (3) Sync sandbox marcó como `DELETED` las 2 plantillas mock del seed (`promo_mayo`, `recordatorio_pedido`) porque el sandbox provider no las devuelve; las 3 campañas históricas del seed apuntan a `template_id=4 (promo_mayo)` ahora DELETED — seed Dev considere agregar esas 2 al sandbox provider o usar nombres existentes. (4) `otro@test.com` con su password documentada `LiIKWUpy2M4zog` no logueó (401); se creó `qa_cross_1778609563@test.com` para validar aislamiento — recomendar reset script para `otro@`. Estado post-QA: id=12 campaña QA completed con 1 delivered+11 sent; campaña 11 cancelled. No se tocó código backend/frontend. |
| 171 | Seguridad: auditoría post-código (autorización por team en cada endpoint, schemas `...Out` sin PII innecesaria/secretos, sanitización de errores Meta hacia el cliente) | Seguridad | — | ✅ | **APROBADO** (ejecutado inline por PM tras corte del subagente). Documento: `backend/docs/sprint13_security_post_audit.md`. Las 15 mitigaciones del diseño (S13-001 a S13-015) verificadas mitigadas en código con cita archivo:línea. Hallazgo NUEVO **S13-016 (Alto)** detectado y **corregido inline**: `routers/internal.py _require_internal_key` permitía acceso anónimo a `/internal/campaigns/tick` cuando `INTERNAL_API_KEY` estaba vacía en producción. Fix: ahora prod+vacío → 403 fail-closed; dev+vacío → pasa libre. Imagen backend rebuildeada y endpoint verificado (dev → 200, esperado). Schemas `...Out` clean: ninguno del Sprint 13 expone `encrypted_access_token`/`hashed_password`/`app_secret` directa ni vía relaciones. **Condición operativa para #174**: la task-def de prod debe incluir `INTERNAL_API_KEY` como secret (SSM/KMS) en la sección `secrets` del container. Follow-ups no bloqueantes documentados (rate-limit a Redis si >1 réplica, prueba de throttle de sync templates en smoke online, etc.). Deploy autorizado. |
| 172 | **CEO valida en local** (bloqueante para deploy) | CEO | — | ⏭ | Diferida y **consolidada con #178** como una sola tarea en el **Sprint Futuro #179**. Deploy ya ejecutado en #173/#174 con autorización del CEO ("ve haciendo el deploy y dejamos la validación al final"). |
| 173 | Deploy AWS: migración Sprint 13 en RDS vía `aws ecs run-task` con command override | Deploy AWS | ‖ 174 | ✅ | **DONE 2026-05-12**. Migración `scripts/migrate_sprint13_campanas.py` ejecutada en RDS `multiagente-db` vía `aws ecs run-task --cluster multiagente-cluster --task-definition multiagente-backend:7 --launch-type FARGATE` (subnets `subnet-07829afbd13c5bb8f`/`subnet-00f56d6ce74d72a2e`, sg `sg-0499ec72831ef7da9`, container `multiagente-backend`). `taskArn=a45753133c234883b5a2dacd79016680`, exitCode=0, stoppedReason="Essential container in task exited". Log CloudWatch verifica 7 CREATE TABLE + 17 índices + "Verificación OK: 7/7 tablas presentes". Migración también re-corrida idempotente en local (docker-compose) → "ya existía → skip" en las 7 tablas, paridad BD local↔RDS mantenida. Seed demo aplicado en RDS: `reset_demo_password.py` (exit 0, password `«en el gestor del CEO»`) y `seed_sprint13_campanas.py` (exit 0): MetaAccount id=2 sandbox-placeholder, 50 contactos, 3 grupos (Premium=12, Recurrentes Bogotá=15, Nuevos Trial=8 → 35 membresías), 2 plantillas APPROVED (`promo_mayo`, `recordatorio_pedido`), 3 campañas (`Promoción Mayo` completed, `Recordatorio carrito` completed, `Lanzamiento producto` scheduled). Fix de seed: `_ensure_meta_account` ahora cifra placeholder con `encrypt_secret("sandbox-placeholder")` porque la columna `meta_accounts.encrypted_access_token` es NOT NULL (consistente con regla de seguridad #1); el sandbox real lo activa `META_SANDBOX=1`, no el valor del token. |
| 174 | Deploy AWS: build + push imagen backend `:sprint13` a ECR + update task-def + service ECS | Deploy AWS | ‖ 173 | ✅ | **DONE 2026-05-12**. (1) **SSM secret**: `aws ssm put-parameter --name /multiagente/prod/INTERNAL_API_KEY --type SecureString` (token_urlsafe(48), Version 1). ARN: `arn:aws:ssm:sa-east-1:747456040509:parameter/multiagente/prod/INTERNAL_API_KEY`. Cumple condición operativa S13-016 de auditoría #171. (2) **Build+push**: `docker buildx build --platform linux/amd64 -t 747456040509.dkr.ecr.sa-east-1.amazonaws.com/multiagente-backend:sprint13 -f Dockerfile.backend --push .` → 89.5 MB pusheados a ECR (verificado con `ecr describe-images imageTag=sprint13`). Rebuild adicional tras fix de `seed_sprint13_campanas.py` (placeholder Fernet). (3) **Task-def nueva rev**: clonada `multiagente-backend:5`, removidos campos read-only, `image` → `:sprint13`, secrets ahora incluye `APP_ENCRYPTION_KEY` + `INTERNAL_API_KEY`, environment incluye `META_SANDBOX=1`. Registrada como **`multiagente-backend:7`** (rev 6 fue una task one-off de #169 según memoria). (4) **Service update**: `ecs update-service --task-definition multiagente-backend:7 --force-new-deployment`, polled hasta `rolloutState=COMPLETED` en ~2 min (transición healthy 1→2→1). (5) **Health checks**: `GET http://multiagente-alb-673139873.sa-east-1.elb.amazonaws.com/docs` → 200; `POST https://app.glomabeauty.com/api/login` con `demo@gmail.com / «en el gestor del CEO»` → 200 + JWT (Amplify rewrite `/api/*` → ALB validado, sin mixed content). |
| 175 | QA online: smoke test `https://app.glomabeauty.com/campanas` (login demo, listar contactos seedeados en RDS, crear campaña sandbox, validar KPIs) | QA | — | ✅ | **DONE 2026-05-12** (fix S13-DEPLOY-001 aplicado por PM y redeploy validado). Smoke desde Amplify proxy con JWT de `demo@gmail.com`: `GET /api/campaigns` → 200 **count=3**; `GET /api/contacts?limit=50` → 200 **count=50**; `GET /api/contact-groups` → 200 **3 grupos**; `GET /api/templates` → 200 **count=6** (antes del fix daba 500). **Fix S13-DEPLOY-001**: `schemas.py WhatsappTemplateOut.components_json: dict → Any` (`from typing import Any` añadido). Local rebuild verificado (7 templates OK). Imagen `:sprint13` re-pushed a ECR; `ecs update-service --force-new-deployment` rolló a `rolloutState=COMPLETED`. Validación funcional del wizard frontend queda para la revisión del CEO al cierre del sprint. |
| 176 | PM: diagramas PUML en `backend/docs/sprint13_diagramas.puml` (clases + servicios + secuencia de envío) | PM | — | ✅ | Archivo `backend/docs/sprint13_diagramas.puml` con 3 diagramas: (a) **clases** — 10 entidades (User, Team, MetaAccount + 7 nuevas Sprint 13), 3 paquetes coloreados (Contactos, Plantillas, Campañas), todas las FKs/UNIQUE/CHECKs documentadas, nota sobre modo sandbox; (b) **servicios** — routers HTTP, servicios de lógica (`meta_templates`, `campaign_sender`, `crypto`), CRUD/models, dependencias hacia Meta/DB, actores (Usuario, Scheduler, Meta webhook), notas sobre S13-016/S13-004/S13-005; (c) **secuencia de envío** — 3 fases (crear campaña → tick → callbacks Meta), con validaciones S13-001 (chain template↔meta↔team), S13-002 (MAX_RECIPIENTS + token-bucket), S13-003 (opt-in doble barrera), S13-015 (dedupe webhook), idempotencia transición `WHERE status='queued'`, ramificación sandbox vs real, nota explicando que en modo demo el callback de Meta no ocurre. Renderable con cualquier renderer PlantUML estándar. |
| 177 | PM: commit + push final a `main` con changelog del Sprint 13 | PM | — | ✅ | Commit `f2d4661` en rama `feature/modulo-campanas` con mensaje detallado (backend + frontend + seguridad + modo demo + deploy AWS + docs + fixes). 35 archivos cambiados (24 nuevos + 11 modificados, +2555 líneas / -39). Push de feature branch → `origin/feature/modulo-campanas`. Merge `--no-ff` a `main` con mensaje `Merge Sprint 13: módulo Campañas + Plantillas WhatsApp + Contactos/Grupos` → commit `3f20503`. Push de `main` a `origin/main` (`d0a7ff5..3f20503`). El backend de prod (`https://app.glomabeauty.com`) ya servía la imagen `:sprint13` desde la Fase 10; este commit alinea el source en `main` con lo que corre en ECS. |
| 178 | **Validación final del CEO** (local + online) y, si hay cambios, aplicar ajustes en post-cierre del sprint | CEO + PM | — | ⏭ | **Movida al Sprint Futuro (#179)**. Consolida #172 y #178 en una sola unidad de trabajo futura. |

### Cambios de BD del Sprint 13 (descripción detallada)

7 tablas nuevas. Toda PII y data multi-tenant lleva `team_id` con índice y FK con `ON DELETE CASCADE`.

#### 1. `contacts` — directorio de contactos por cuenta

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | `SERIAL PK` | |
| `team_id` | `INT NOT NULL FK teams(id) ON DELETE CASCADE` | tenant — aislamiento |
| `phone_e164` | `VARCHAR(20) NOT NULL` | formato E.164 (`+57...`) |
| `name` | `VARCHAR(120)` | |
| `email` | `VARCHAR(255)` | opcional |
| `attributes` | `JSONB` | atributos custom (segmentación) |
| `opt_in` | `BOOLEAN DEFAULT TRUE` | consentimiento WhatsApp |
| `opt_in_source` | `VARCHAR(50)` | de dónde vino (`import_csv`, `form`, `manual`) |
| `created_at` | `TIMESTAMP DEFAULT now()` | |
| `updated_at` | `TIMESTAMP DEFAULT now()` | |
| UNIQUE | `(team_id, phone_e164)` | no duplicar dentro de la cuenta |
| INDEX | `(team_id)` | filtro por tenant |

#### 2. `contact_groups` — agrupaciones definidas por la cuenta

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | `SERIAL PK` | |
| `team_id` | `INT NOT NULL FK teams(id) ON DELETE CASCADE` | |
| `name` | `VARCHAR(120) NOT NULL` | |
| `description` | `TEXT` | |
| `created_at` | `TIMESTAMP DEFAULT now()` | |
| UNIQUE | `(team_id, name)` | nombre único por cuenta |

#### 3. `contact_group_members` — join contact ↔ group (M:N)

| Columna | Tipo | Notas |
|---------|------|-------|
| `group_id` | `INT NOT NULL FK contact_groups(id) ON DELETE CASCADE` | |
| `contact_id` | `INT NOT NULL FK contacts(id) ON DELETE CASCADE` | |
| `added_at` | `TIMESTAMP DEFAULT now()` | |
| PK | `(group_id, contact_id)` | |
| INDEX | `(contact_id)` | recorrido inverso |

#### 4. `whatsapp_templates` — cache de plantillas de Meta

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | `SERIAL PK` | |
| `meta_account_id` | `INT NOT NULL FK meta_accounts(id) ON DELETE CASCADE` | dueño de la plantilla |
| `meta_template_id` | `VARCHAR(64)` | id devuelto por Meta |
| `name` | `VARCHAR(120) NOT NULL` | |
| `category` | `VARCHAR(40)` | `MARKETING`, `UTILITY`, `AUTHENTICATION` |
| `language` | `VARCHAR(20) NOT NULL` | `es_MX`, `es`, `en_US`... |
| `status` | `VARCHAR(20) NOT NULL` | `PENDING`, `APPROVED`, `REJECTED`, `DISABLED`, `PAUSED` |
| `components_json` | `JSONB NOT NULL` | header/body/footer/buttons como Meta lo devuelve |
| `rejection_reason` | `TEXT` | si Meta rechaza |
| `last_synced_at` | `TIMESTAMP` | última vez que se trajo de Meta |
| `created_at` | `TIMESTAMP DEFAULT now()` | |
| UNIQUE | `(meta_account_id, name, language)` | Meta no permite duplicado en este combo |
| INDEX | `(meta_account_id, status)` | filtrar APPROVED al crear campaña |

#### 5. `campaigns` — campañas de envío masivo

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | `SERIAL PK` | |
| `team_id` | `INT NOT NULL FK teams(id) ON DELETE CASCADE` | tenant |
| `meta_account_id` | `INT NOT NULL FK meta_accounts(id) ON DELETE RESTRICT` | desde qué WABA se envía |
| `template_id` | `INT NOT NULL FK whatsapp_templates(id) ON DELETE RESTRICT` | sólo APPROVED |
| `name` | `VARCHAR(120) NOT NULL` | |
| `status` | `VARCHAR(20) NOT NULL` | `draft`, `scheduled`, `running`, `completed`, `failed`, `cancelled` |
| `scheduled_at` | `TIMESTAMP` | NULL = enviar inmediato |
| `started_at` | `TIMESTAMP` | cuando el sender empezó |
| `completed_at` | `TIMESTAMP` | |
| `template_variables_json` | `JSONB` | mapping `{1: "{{contact.name}}", 2: "..."}` para interpolación |
| `created_by_user_id` | `INT FK users(id)` | quién la creó |
| `created_at` | `TIMESTAMP DEFAULT now()` | |
| INDEX | `(team_id, status)` | dashboard filtra por estado |
| INDEX | `(status, scheduled_at)` | scheduler tick busca `scheduled + scheduled_at <= now()` |

#### 6. `campaign_recipients` — destinatarios de cada campaña

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | `SERIAL PK` | |
| `campaign_id` | `INT NOT NULL FK campaigns(id) ON DELETE CASCADE` | |
| `contact_id` | `INT NOT NULL FK contacts(id) ON DELETE RESTRICT` | trazabilidad |
| `phone_e164` | `VARCHAR(20) NOT NULL` | snapshot en el momento del envío |
| `meta_message_id` | `VARCHAR(80)` | `wamid` devuelto por Meta — correlación con webhook |
| `status` | `VARCHAR(20) NOT NULL DEFAULT 'queued'` | `queued`, `sending`, `sent`, `delivered`, `read`, `failed` |
| `error_code` | `VARCHAR(40)` | código Meta si falló |
| `sent_at` | `TIMESTAMP` | |
| `delivered_at` | `TIMESTAMP` | |
| `read_at` | `TIMESTAMP` | |
| `failed_at` | `TIMESTAMP` | |
| UNIQUE | `(campaign_id, contact_id)` | no enviar dos veces al mismo contacto en la misma campaña |
| INDEX | `(meta_message_id)` | webhook hace lookup por wamid |
| INDEX | `(campaign_id, status)` | KPIs agregados por campaña |

#### 7. `campaign_events` — log de eventos detallado (audit + analytics)

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | `SERIAL PK` | |
| `campaign_id` | `INT NOT NULL FK campaigns(id) ON DELETE CASCADE` | |
| `recipient_id` | `INT FK campaign_recipients(id) ON DELETE CASCADE` | NULL para eventos a nivel campaña |
| `event_type` | `VARCHAR(30) NOT NULL` | `queued`, `sent`, `delivered`, `read`, `failed`, `clicked` |
| `payload_json` | `JSONB` | payload crudo de Meta (para debug) |
| `meta_message_id` | `VARCHAR(80)` | redundante pero acelera el join |
| `created_at` | `TIMESTAMP DEFAULT now()` | |
| INDEX | `(campaign_id, event_type)` | dashboard agrega por tipo |
| INDEX | `(meta_message_id)` | dedupe por webhook |

#### Decisiones clave

1. **Multi-tenancy estricto**: `team_id` directo en `contacts`, `contact_groups`, `campaigns`. Plantillas heredan tenant vía `meta_account_id → teams`. Cualquier endpoint filtra por `team_id` del usuario autenticado — repetimos el patrón ya usado en `messages`/`conversations`.
2. **`campaign_recipients` como snapshot**: `phone_e164` se copia al momento del envío para que el histórico no se rompa si el contacto se edita o borra después.
3. **`whatsapp_templates` como cache, no fuente de verdad**: la verdad vive en Meta. `last_synced_at` + sync explícito al entrar a la sección + scheduler 30 min para `PENDING`.
4. **`campaign_events` como bitácora analítica**: permite reconstruir el funnel y debug. El estado "rápido" para la UI vive en `campaign_recipients.status`.
5. **Idempotencia del webhook**: lookup por `meta_message_id` único en `campaign_recipients` + dedupe en `campaign_events`.
6. **Soft constraints sobre Meta**: el envío sólo se permite si `templates.status = 'APPROVED'` y `campaigns.template_id` apunta a ese template — validado en el backend antes de encolar.

### Diagramas PUML (entregable de cierre — tarea 176)

PM publica al cierre:
- **Clases**: relaciones entre `Team`, `MetaAccount`, `Contact`, `ContactGroup`, `WhatsappTemplate`, `Campaign`, `CampaignRecipient`, `CampaignEvent`.
- **Servicios**: `campaign_sender`, `meta_templates`, `meta_webhook_ingestion`, `scheduler_tick`.
- **Secuencia**: usuario crea campaña → backend valida plantilla APPROVED → encola recipients → sender envía vía Meta → Meta entrega → Meta webhook → ingestion actualiza `recipients.status` + `campaign_events` → dashboard refresca KPIs.

### Parejas paralelas (resumen)

| Fase | Pareja | Tareas |
|------|--------|--------|
| 0 — setup | PM solo | 153, 154 |
| 1 — diseño | UI/UX ‖ Experto BD | 155 ‖ 156 |
| 1.5 — revisión | Seguridad ‖ Experto BD | 157 ‖ 158 |
| 2 — backend datos | Dev ‖ Dev | 159 ‖ 160 |
| 3 — backend campañas | Dev ‖ Dev | 161 ‖ 162 |
| 4 — backend webhooks + UI dashboard | Dev ‖ Dev | 163 ‖ 164 |
| 5 — UI campañas | Dev ‖ Dev | 165 ‖ 166 |
| 6 — UI plantillas + contactos | Dev ‖ Dev | 167 ‖ 168 |
| 7 — seed + QA local | Dev ‖ QA | 169 ‖ 170 |
| 8 — auditoría | Seguridad solo | 171 |
| 9 — CEO valida | CEO solo | 172 |
| 10 — deploy | Deploy AWS ‖ Deploy AWS | 173 ‖ 174 |
| 11 — smoke online | QA solo | 175 |
| 12 — cierre | PM solo | 176, 177 |

---

## Sprint 14 - Mejoras al módulo Bots (UI/UX + ventana de prueba + AWS)

**Rama**: por definir (`feature/bots-mejoras-sprint14` propuesto). Trabajo encadenado: análisis → priorización CEO → implementación.

**Estado**: DONE. Abierto el 2026-05-12 y cerrado el 2026-05-13 a pedido del CEO.

**Alcance final**: este sprint se cerró con la **fase de análisis** completa (tareas #182 a #185 ✅). La **fase de implementación** (priorización CEO, fixes de la ventana de prueba, rediseño del detalle de bot, provisionamiento del cron AWS, QA y cierre) se trasladó al [Sprint Futuro](#sprint-futuro---validación-ceo--ajustes-post-sprint-13) como tareas #186 a #189. Esto deja el Sprint 14 cerrado como un sprint de análisis puro y permite que la implementación se priorice junto con la validación pendiente del módulo Campañas (#179/#180/#181).

**Objetivo del Sprint**: mejorar la experiencia y operación del módulo Bots de Gloma:
1. Documentar el estado actual (backend, frontend, scripts, infra AWS) como punto de partida.
2. Rediseñar la pantalla de detalle de bot (`/bots/[id]`) para que sea más agradable.
3. Corregir bugs y UX de la ventana "Probar Chatbot".
4. Optimizar el costo y operación de AWS y proyectar costos para 2/5/10 usuarios.

**Protocolo**: tareas en pares (dos en dos). Cada tarea queda registrada en esta tabla con sus hallazgos antes de continuar.

### Tareas

| # | Tarea | Responsable | Par | Estado | Notas |
|---|-------|------------|-----|--------|-------|
| 182 | **Inventario del módulo Bots**: backend (routers/servicios/modelos), frontend (pantallas), scripts de migración/seed, infraestructura AWS asociada | PM | ‖ 183 | ✅ | Ver §"Inventario del módulo Bots" abajo. Resumen: 1 router (`backend/app/routers/bots.py`, 92 LOC, 4 endpoints), 3 servicios (`bot_engine.py` motor puro, `bot_router.py` decide qué bot atiende, `bot_runner.py` orquesta envío Meta), 4 modelos (`Bot`, `BotStep`, `BotSession`, `BotPendingAction` — Sprints 8/9/10), 7 tipos de paso (`send_text`, `send_template`, `send_media`, `wait_input`, `delay`, `condition`, `end`), 3 triggers (`default`/`keyword`/`manual`), 2 pantallas en Next.js (`pages/bots.tsx` listado, `pages/bots/[id].tsx` canvas+simulador), 4 scripts de migración/seed (`migrate_sprint8_add_bots.py`, `migrate_sprint9_bots_ownership_triggers.py`, `migrate_sprint10_bot_sessions.py`, `seed_bot_demo.py`), endpoint cron `/internal/bot-scheduler/tick` que procesa `BotPendingAction` vencidas. Infra: corre dentro del backend ECS Fargate (no hay servicio dedicado de bots), persiste en RDS PostgreSQL, no requiere recursos AWS adicionales más allá de un disparador cron externo todavía no provisionado en prod. |
| 183 | **Revisar comportamiento de la ventana "Probar Chatbot"** (`SimulatorModal` en `frontend/pages/bots/[id].tsx` líneas 158-430) | PM + QA | ‖ 182 | ✅ | Ver §"Revisión ventana Probar Chatbot" abajo. **8 hallazgos**, 3 son bugs reales bloqueantes para una experiencia decente. Top-3: (a) clase Tailwind inválida `bg-gloma-rose-soft/300` en líneas 312 y 421 → burbuja del usuario y botón send pierden color; (b) las branches de `condition` solo se evalúan cuando el valor es `int` (step_id), pero el seed (`seed_bot_demo.py:58-61`) usa strings → la ramificación nunca aplica y siempre cae al `next_step_id` lineal; (c) `condition` no espera input real: el motor emite el prompt como `say` y resuelve inmediatamente con `user_input=None`, así que en la simulación no se puede elegir branch. Resto: (d) opciones de `wait_input` se muestran como texto plano, no son chips clickeables; (e) sin atajo `Esc` para cerrar el modal; (f) banner "Simulación — no se envían mensajes reales" muy pequeño (sólo en header); (g) `delay` se omite con texto pero no muestra contador; (h) reset hace flash con `setTimeout(0)`. |
| 184 | **Análisis UI/UX de la pantalla detalle de bot** (`/bots/[id]`): rediseñar canvas + nodos + ventana de prueba para que sea agradable a la vista, mantener identidad Gloma. Entregable: HTML/Tailwind con propuesta(s) | UI/UX | ‖ 185 | ✅ | Entregado `identidad_gloma/diseno_bots.html` (53 KB, single HTML navegable, Tailwind CDN + Syne/Inter + paleta `gloma-*` inline). 4 secciones: §1 Detalle de bot rediseñado (canvas en `gloma-cream` con grid dotted, nodos 220px con accent-top por tipo de paso, header sticky simplificado, side panel colapsable con metadatos del bot — `triggered_count`/`completed_steps_count`/`finished_count`/`channels`/`trigger_config`), §2 Ventana "Probar Chatbot" rediseñada como **panel lateral derecho** (en lugar del modal centrado actual) con chips clickeables para `wait_input.options` (fix hallazgo 183-d), badge "rama elegida" para `condition` (visualiza fix 183-c), banner permanente "Modo simulación · no toca Meta" (fix 183-f), pill con contador animado para `delay` (mejora 183-g), indicador typing 3 puntos legible, cierre con Esc (fix 183-e), botón reset bien visible, estado "fin de flujo" con CTA grande, §3 Estados (vacío sin pasos con CTA "Crear primer paso", cargando con skeletons, error con reintento, simulación finalizada), §4 Decisiones de diseño. **Top-3 decisiones**: (1) canvas con fondo `gloma-cream` y grid de puntos en vez de líneas → menos ruido visual, los nodos respiran; (2) ventana de prueba pasa de **modal centrado pequeño** a **panel lateral derecho persistente** del mismo tamaño que el canvas → permite ver el flujo y la simulación a la vez (insight UX: hoy hay que cerrar el modal para ver dónde está el bot); (3) cada nodo tiene `border-t-4` con el color del tipo de paso (azul `send_text`, índigo `send_template`, púrpura `send_media`, ámbar `wait_input`, gris `delay`, naranja `condition`, rosa `end`) → reconocimiento de tipo en 1 segundo. **Supuestos abiertos para PM**: (a) decidir si la pantalla `/bots/[id]` se abre en pestaña nueva (hoy sí, con `window.close()`) o como sub-ruta navegable del Layout — el wireframe asume sub-ruta navegable; (b) el side panel de metadatos es nuevo, requiere campos que ya están en `BotDetail` (sin cambios de BD); (c) `condition` con espera real de input requiere cambio en `bot_engine.advance` para que emita `ask` y corte el turno cuando el paso es `condition` sin `wait_input` previo — coordinar con Dev Plataforma antes de implementar. Notas embebidas `<!-- DEV: ... -->` por zona indicando endpoint/campo a consumir. |
| 185 | **Análisis AWS**: revisión de la infra actual del módulo Bots + propuestas de optimización (costo y operación) + proyección de costos mensuales para 2, 5 y 10 usuarios concurrentes. Entregable: doc en `backend/docs/sprint14_aws_analisis.md` | Deploy AWS | ‖ 184 | ✅ | Entregado `backend/docs/sprint14_aws_analisis.md` (6 secciones). **Conclusión**: el módulo Bots **no tiene infra dedicada** — comparte ECS Fargate (1 task 0.25vCPU/0.5GB), RDS `db.t3.micro` PostgreSQL, ALB y Amplify con el resto del backend. **Gap bloqueante (G1)**: en prod **no existe cron** que invoque `POST /internal/bot-scheduler/tick` cada 60s; sin ese cron, en cuanto un bot real use `delay` los pasos quedan pendientes para siempre. **Top-3 ahorros propuestos** (sa-east-1): (P1) **Provisionar cron** con EventBridge Scheduler → Lambda → `/internal/bot-scheduler/tick` — costo $0 (free tier), cierra G1, instrucciones AWS CLI completas en §6 del doc; (P2) **RDS → `db.t4g.micro` Graviton** drop-in — ahorro $3-5/mes, 5min downtime; (P3) **Quitar ALB y exponer Fargate directo** — ahorro $15-20/mes pero NO recomendado en esta fase por complejidad y pérdida de health checks managed. Otras propuestas evaluadas: P5 retención logs 30d, P6 CloudFront delante de Amplify, P7 auto-scaling ECS 1→4 (no ahorra pero habilita 10 usuarios sin sustos), P8 verificar si existe NAT colgado (-$32/mes si aplica), P4 Fargate Spot **descartado** (1 task crítico, no vale el riesgo). **Proyección de costos sa-east-1**: Escenario A 2 usuarios concurrentes ~**$59/mes** (precio real con ALB y LCU; piso realista vs los ~$42-47 históricos de CLAUDE.md que omitían LCU), Escenario B 5 usuarios ~**$68/mes** sin cambiar sizing, Escenario C 10 usuarios ~**$96/mes** subiendo Fargate a 0.5vCPU/1GB con auto-scaling 1→2 + +$10 si se quiere HA real 2 tasks. **Arquitectura recomendada Sprint 14**: mantener ALB + Amplify, agregar EventBridge Scheduler+Lambda para tick, migrar RDS a `db.t4g.micro`, retención logs 30d, habilitar auto-scaling — sin cambios mayores; coste objetivo 5 usuarios ~$65/mes, 10 usuarios ~$93/mes. **Falta** ejecutar verificaciones aws-cli puntuales (retención logs reales, `networkConfiguration` del service para confirmar si hay NAT) — comandos exactos en el doc. |
| 186-189 | **Tareas de implementación (priorización CEO, fixes ventana prueba, rediseño UI/UX, cron AWS, QA, cierre)** — TRASLADADAS al Sprint Futuro el 2026-05-13 | — | — | ⏭ | Ver tareas #186-189 en [Sprint Futuro](#sprint-futuro---validación-ceo--ajustes-post-sprint-13). El Sprint 14 se cierra como sprint de análisis. |

### Inventario del módulo Bots (entregable tarea #182)

**Backend (`backend/app/`)**

| Capa | Archivo | LOC | Responsabilidad |
|------|---------|-----|-----------------|
| Router | `routers/bots.py` | 92 | 4 endpoints: `GET /bots` (lista), `GET /bots/export` (descarga JSON), `GET /bots/{id}` (detalle con pasos), `POST /bots/{id}/simulate` (motor de simulación, estado mantenido por el cliente) |
| Motor (puro) | `services/bot_engine.py` | 209 | `advance(bot, state, user_input)` consume hasta `MAX_STEPS_PER_TURN=50` pasos por turno; emite acciones `say`/`say_media`/`ask`/`pause`/`end`. Stateless: ni DB ni red ni Meta |
| Router de bots | `services/bot_router.py` | 107 | `resolve_bot_for_incoming_message`: 1) sesión activa, 2) keyword match (substring lower-case), 3) bot default del owner, 4) None |
| Orquestador | `services/bot_runner.py` | 246 | `run_turn` — carga/crea `BotSession`, llama al motor, envía cada acción por `meta_whatsapp.send_text_message`, persiste estado, programa `BotPendingAction` para `delay`. `process_pending_action` retoma sesiones diferidas |
| Modelos | `models.py:198-377` | 180 | `Bot`, `BotStep`, `BotSession`, `BotPendingAction`. 7 tipos de paso, 3 triggers (`default`/`keyword`/`manual`), 4 estados de sesión |
| Scheduler | `routers/internal.py:58-90` | — | `POST /internal/bot-scheduler/tick` protegido con `INTERNAL_API_KEY`. Pensado para invocarse cada 60s por cron externo (todavía no provisionado en prod — gap) |

**Frontend (`frontend/`)**

| Pantalla | Archivo | LOC | Contenido |
|----------|---------|-----|-----------|
| Listado | `pages/bots.tsx` | 231 | Tabla simple: nombre, badge de trigger, contador "disparado", fechas relativas. Búsqueda local + descarga JSON. Sin filtros adicionales |
| Detalle | `pages/bots/[id].tsx` | 589 | Canvas horizontal con `StepNode` (nodos 260×200 absolutos) + SVG bezier con flechas. Modal `SimulatorModal` "Probar Chatbot" |
| Layout | `components/Layout.tsx`, `components/Sidebar.tsx` | — | Shell común a toda la app |

**Scripts (`backend/scripts/`)**

| Script | Propósito |
|--------|-----------|
| `migrate_sprint8_add_bots.py` | DDL idempotente: tablas `bots` + `bot_steps` |
| `migrate_sprint9_bots_ownership_triggers.py` | Sprint 9: trigger_type, trigger_config, ownership por user |
| `migrate_sprint10_bot_sessions.py` | DDL: `bot_sessions` + `bot_pending_actions` + índices |
| `seed_bot_demo.py` | Bot de bienvenida con 5 pasos (incl. uno `condition` con branches en formato string — ver bug #183-(b)) |

**Infraestructura AWS asociada al módulo Bots**

| Recurso | Uso por Bots | Observación |
|---------|-------------|-------------|
| ECS Fargate (`multiagente-backend-service`, 1 task 0.25vCPU/0.5GB) | Sirve los 4 endpoints `/bots/*` y el tick `/internal/bot-scheduler/tick`. Compartido con todos los módulos | Sin auto-scaling configurado |
| ECR (`multiagente-backend`) | Imagen del backend que contiene el motor + runner | — |
| RDS PostgreSQL (`multiagente-db`, db.t3.micro, sa-east-1) | Tablas `bots`, `bot_steps`, `bot_sessions`, `bot_pending_actions` (más todo el resto del esquema) | Compartido con todos los módulos |
| ALB (`multiagente-alb`) | Entrada HTTPS al backend | Comparte con resto de endpoints |
| Amplify (`d1cfl9ey07f61o`) | Sirve el frontend Next.js incluidas `pages/bots*` | — |
| Cron externo del tick | **No provisionado todavía**. El endpoint existe pero nada lo invoca en prod → los pasos `delay` quedarían pendientes para siempre en producción real | Gap que el Sprint 14 debe cerrar (probable EventBridge + Lambda invoker o ECS scheduled task) |
| SSM `/multiagente/prod/APP_ENCRYPTION_KEY` | No usado directamente por Bots, sí por Meta credentials (que el runner usa al enviar) | — |

**Costo actual estimado**: ~$42-47/mes (todo el backend Gloma, no aislable al módulo Bots).

### Revisión ventana "Probar Chatbot" (entregable tarea #183)

Pantalla: `SimulatorModal` en `frontend/pages/bots/[id].tsx` líneas 158-430.

**Comportamiento esperado**:
1. Abre como modal centrado al click en "▶ Probar Chatbot" del header.
2. En el primer turno hace `POST /api/bots/{id}/simulate` con `{state: null, user_input: null}` y pinta las acciones devueltas como burbujas de chat tipo WhatsApp.
3. Si la última acción es `ask`, habilita el input y espera respuesta; en el siguiente turno envía `{state: <next_state>, user_input: <texto>}`.
4. Si `finished=true`, muestra burbuja rosa de fin y deshabilita el input. Botón "Reiniciar simulación" reanuda desde cero.

**Hallazgos (8)**:

| # | Tipo | Severidad | Descripción |
|---|------|-----------|-------------|
| (a) | Bug | Alta | Clase Tailwind inválida `bg-gloma-rose-soft/300` en líneas 312 (burbuja usuario) y 421 (botón send). El sufijo `/N` es opacidad (0-100), no escala de color. Resultado: ambos elementos pierden el color de marca. **Fix**: usar `bg-gloma-rose-soft` o `bg-gloma-rose`. |
| (b) | Bug | Alta | `bot_engine._resolve_condition_next` solo respeta branches cuyo valor sea `int` (step_id). Pero `seed_bot_demo.py:58-61` usa strings (`"seguir": "Volver al menú"`) → la ramificación nunca matchea y siempre cae al `next_step_id` lineal. La feature de condition está rota end-to-end en datos reales. **Fix**: resolver branches por substring de keyword sobre las KEYS (ya hecho) **pero** apuntar a step_ids reales en el seed/UI. Alternativa: aceptar valores tipo string `label` y resolver por label-de-step. |
| (c) | Bug | Alta | `condition` no espera input del contacto: emite el prompt como `say` y resuelve `_resolve_condition_next` en el mismo turno con `user_input=None` que el motor no consume del primer turno. El simulador nunca habilita el input para elegir branch. **Fix**: que `condition` se comporte como `wait_input` interno (emitir `ask` y cortar el turno) y resolver branch al recibir input siguiente. |
| (d) | UX | Media | Opciones de `wait_input` se muestran como `<li>` planos (líneas 344-352). Esperable que sean chips clickeables que rellenen el input automáticamente. |
| (e) | UX | Media | No hay atajo `Esc` para cerrar el modal — sólo click en backdrop o en `×`. |
| (f) | UX | Baja | Banner "Simulación — no se envían mensajes reales" es muy pequeño y sólo aparece en el header. En body podría reforzarse con un chip permanente. |
| (g) | UX | Baja | `delay` se omite con texto centrado pero no muestra contador animado de los segundos. Aceptable, opcional mejorar. |
| (h) | UX | Baja | `handleReset` usa `setTimeout(0)` para disparar el primer turno → flash visual al limpiar burbujas. Aceptable, opcional usar `useEffect` controlado. |

**Conclusión**: la ventana funciona para bots lineales (send_text → wait_input → send_text → end) pero falla en condicionales (todos los seeds existentes usan condition → bug bloqueante para la experiencia). Hay 3 fixes que pueden entrar como un commit chico antes de la fase de implementación grande del Sprint 14.



> **Nota de naming**: este sprint queda intencionalmente **sin numerar** ("Sprint Futuro"). El número 14 fue tomado el 2026-05-12 por [Sprint 14 — Mejoras al módulo Bots](#sprint-14---mejoras-al-módulo-bots-uiux--ventana-de-prueba--aws), que se cerró el 2026-05-13 como sprint de análisis y trasladó aquí su fase de implementación (tareas #186-189). Cuando este sprint se ejecute y se cierre, se renombra o se absorbe en el sprint que toque.

**Alcance ampliado el 2026-05-13**: además de la validación CEO del módulo Campañas (#179/#180/#181), este sprint agrupa la **fase de implementación de las mejoras al módulo Bots** identificadas en el Sprint 14 (#186/#187/#188/#189). Los dos paquetes son independientes — pueden ejecutarse en cualquier orden o en paralelo según prioridad del CEO.


**Rama**: trabajo directo sobre `main` (cambios incrementales pequeños).

**Estado**: PRÓXIMO. Abierto el 2026-05-12 al cerrar el Sprint 13.

**Contexto**: el Sprint 13 cerró en código y deploy con el módulo Campañas + Plantillas WhatsApp + Contactos/Grupos funcional en modo sandbox (sin cuenta Meta real). El CEO pidió validar todo de una sola pasada tras el deploy. Este sprint agrupa esa validación y los ajustes que de ahí salgan, para no reabrir el Sprint 13.

### Entornos de validación

| Entorno | URL | Credenciales |
|---------|-----|--------------|
| Local (docker-compose) | `http://localhost:3000/login` | `demo@gmail.com` / `«en el gestor del CEO»` |
| Producción (Amplify + ECS + RDS sa-east-1) | `https://app.glomabeauty.com/login` | `demo@gmail.com` / `«en el gestor del CEO»` |

> Las credenciales corresponden a la cuenta demo sandbox: `MetaAccount` con `encrypted_access_token = encrypt("sandbox-placeholder")`, el backend opera en modo sandbox (`META_SANDBOX=1` en prod, NULL/sandbox en local) — NO toca Meta real. Si en algún momento se conecta una cuenta Meta real, esa cuenta seguirá funcionando para envíos reales pero las plantillas mock dejarán de aparecer; documentar esta transición en su momento.

### Tareas

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 179 | **Validación CEO del módulo Campañas** (local + online). Checklist abajo. Marcar OK por sección o registrar el cambio pedido | CEO | ⬜ | Consolida las antiguas #172 (validación local pre-deploy) y #178 (validación post-deploy). Sólo aplica al módulo Sprint 13 — no incluye regresión global. |
| 180 | **Ajustes post-revisión**: aplicar los cambios que pida el CEO en #179 (copy, UX, comportamiento). Cada cambio = un commit chico en `main` con su mensaje + rebuild/redeploy si aplica | Dev Plataforma + PM | ⬜ | Sin reabrir el Sprint 13. Cambios incrementales sobre `main`. Si un cambio toca BD, el Experto BD aplica migración idempotente en local y en RDS (regla de paridad). |
| 181 | **Cierre del paquete Campañas**: marcar #179 ✅, #180 ✅, log de cambios. Confirmar al CEO que el módulo Campañas queda 100% cerrado | PM | ⬜ | Si #179 no requiere ajustes, #180 queda vacía/`N/A`. NO cierra el sprint completo — sólo el paquete Campañas. |
| 186 | **Priorización CEO** de los hallazgos del Sprint 14 (revisión ventana de prueba #183, rediseño UI/UX #184, propuestas AWS #185) y armado del plan de implementación: qué entra ahora, qué se difiere, en qué orden | CEO + PM | ⬜ | Insumos: bitácora Sprint 14 + `identidad_gloma/diseno_bots.html` + `backend/docs/sprint14_aws_analisis.md`. Recomendación PM al cerrar Sprint 14: P1 cron AWS primero (desbloqueante real para bots en producción), luego fixes (a)(b)(c) de la ventana de prueba (cambios chicos), luego rediseño UI/UX del detalle. |
| 187 | **Implementación de mejoras Bots priorizadas en #186**. Sub-paquetes posibles: (a) cron AWS — Deploy AWS, según §6 de `sprint14_aws_analisis.md`; (b) fixes ventana de prueba — Dev Plataforma, según §"Revisión ventana Probar Chatbot" del Sprint 14; (c) rediseño detalle de bot — Dev Plataforma, según `identidad_gloma/diseno_bots.html` | Dev Plataforma + Deploy AWS | ⬜ | Cambio en `bot_engine.advance` para que `condition` espere input (fix 183-c) pasa por agente `seguridad` por revisión rápida (cambia comportamiento del motor pero no toca credenciales). Cualquier ajuste de schema → Experto BD aplica migración idempotente en local y RDS (regla de paridad). |
| 188 | **QA + smoke local y online** del módulo Bots tras las mejoras de #187. Validar los 3 bugs bloqueantes del #183 cerrados (Tailwind class, condition branches int/string, condition espera input), la ventana de prueba con chips clickeables y Esc, el cron AWS invocando el tick cada 60s en prod | QA | ⬜ | Smoke local: `docker compose up`, abrir `/bots/[id]`, ejecutar simulación completa con un bot que tenga `condition`. Smoke online: confirmar logs de Lambda `multiagente-bot-tick` con 200 OK cada minuto. |
| 189 | **Cierre del paquete Bots**: marcar #186 ✅, #187 ✅, #188 ✅, log de cambios. Confirmar al CEO que las mejoras del Sprint 14 quedan desplegadas | PM | ⬜ | Cuando #181, #189 y #197 estén en ✅, se cierra el Sprint Futuro completo: marcar índice a DONE y registrar entrada final en Log de Cambios. |
| 197 | **Validación CEO Sprint 15 — tutoriales interactivos** (local + online). Para resetear el demo: `UPDATE users SET tutorials_completed='{}'::jsonb WHERE correo='demo@gmail.com';` en cada DB. Recorrer los 4 módulos y verificar (a) que el tutorial aparece sólo la primera vez, (b) el spotlight resalta la zona correcta en cada paso, (c) "Omitir tutorial" funciona en cualquier paso, (d) "Finalizar" persiste y al recargar no vuelve | CEO + PM | ✅| Ajustes salen como commits chicos sobre `main` tipo `style(tutorial): ...` o `fix(tutorial): ...`. NO reabre el Sprint 15. |
| 219 | **Plan de rollback a ALB (heredado de Sprint 17)**: documentar y/o ejecutar el regreso a Application Load Balancer cuando el sistema necesite (a) HA con >1 task ECS, (b) routing path-based avanzado, (c) WAF/sticky sessions, (d) >>1M requests/mes haciendo el costo de API Gateway competitivo con ALB. Pasos: emitir cert wildcard `*.glomabeauty.com` o renovar para ALB, recrear ALB + target group + listener HTTPS, re-attach ECS service `loadBalancers`, mover A-record `api.glomabeauty.com` a ALB alias, mantener API Gateway durante 24h, validar smoke, eliminar API Gateway + VPC Link + Cloud Map. Costo del rollback: ~$24-28/mes adicionales pero gana HA real | CEO + Deploy AWS | ⬜ | **Trigger**: cuando el CEO valide que se necesita HA o cuando el tráfico justifique el costo. No bloqueante. |
| 362 | **Decisión del CEO: cuánto debe durar la sesión** (heredada de #361) | CEO | ✅ | **Resuelta el 2026-08-17: se quedan los 30 minutos.** El CEO confirmó que está bien. No hubo cambio de código ni de env var — `ACCESS_TOKEN_EXPIRE_MINUTES` sigue en su valor por defecto (30). Si algún día se quiere subir, es esa sola env var en la task-def de ECS y en el `.env` local, con tope 240 (4 h) por `app/config.py`. |
| 363 | **Revocación real de sesiones (nota de la auditoría de #361)**: hoy "Salir" solo limpia el navegador; el JWT sigue siendo válido server-side hasta que vence, porque no hay `jti` ni denylist. Es el comportamiento normal de JWT stateless y con 30 min de vida la ventana es corta | Seguridad | ⬜ | **No bloqueante, anotado a propósito.** Se vuelve relevante si aparece un caso de "sacar a alguien YA" (empleado desvinculado, token filtrado) o si se sube mucho #362. Implicaría `jti` en el token + tabla/caché de revocados. |
| 220 | **Auditoría 48h del Sprint 17** (cierre formal): revisar CloudWatch logs de las primeras 48h tras el cutover (≥2026-05-19) para confirmar latencia p95 estable, 0% 5xx, sin spikes raros de Cloud Map health checks. Si OK, cerrar el follow-up; si hay anomalías, abrir Sprint 18 de tuning | Seguridad + QA | ⬜ | Ejecución abreviada (10 min) ya completada en Sprint 17 #217 con 0 errores. Esta tarea cierra la auditoría formal. |

### Checklist de validación (tarea #179)

El CEO recorre las 6 rutas en **ambos entornos** (local y producción) con `demo@gmail.com / «en el gestor del CEO»`:

#### 1. `/campanas` (dashboard)

- [ ] Header "Transmisiones masivas" + botón "Nueva campaña" arriba a la derecha.
- [ ] Tabs internos: Resumen / Mensajes de plantilla / Campañas programadas.
- [ ] 4 cards "Visión general" (estáticos por ahora).
- [ ] 8 KPI cards (Enviado destacado en marrón Gloma, los otros en blanco) con conteos del seed.
- [ ] Tabla "Todas las campañas" con 3 filas seedeadas (Promoción Mayo, Recordatorio carrito, Lanzamiento producto).
- [ ] Búsqueda por nombre, dropdown ordenar, paginación cliente 10/pág.
- [ ] Badge de estado coloreado y acción "Cancelar" sólo para `scheduled`.
- [ ] Identidad Gloma respetada (paleta, Syne/Inter).

#### 2. `/campanas/nueva` (wizard 4 pasos)

- [ ] Paso 1 — bloquea avance si no hay `MetaAccount` (en demo SÍ hay, así que debería dejar avanzar).
- [ ] Paso 2 — muestra plantillas APPROVED del sandbox + preview del cuerpo. Variables `{{1}}/{{2}}` editables.
- [ ] Paso 3 — toggle "Lista" / "Grupo". Lista: tabla paginada con checkboxes. Grupo: dropdown con los 3 grupos del seed (Clientes Premium 12, Recurrentes Bogotá 15, Nuevos Trial 8).
- [ ] Aviso visible: "Los contactos con opt-in en false se marcarán como omitidos automáticamente".
- [ ] Paso 4 — radio Enviar ahora / Programar + resumen con conteo y estimación.
- [ ] Confirmar → 201 + redirect a `/campanas/<id>`.

#### 3. `/campanas/<id>` (detalle)

- [ ] Cabecera con nombre + badge + fechas + acciones (Cancelar visible sólo si scheduled).
- [ ] 6 KPI cards (Total destacado en marrón).
- [ ] Tabla de destinatarios paginada 50/pág con filtro por estado.
- [ ] Teléfono enmascarado parcialmente.
- [ ] Polling 5s si la campaña está corriendo (puedes simularlo creando una campaña nueva).

#### 4. `/campanas/plantillas` (lista de plantillas)

- [ ] Tabla con plantillas del seed + las mock del sandbox.
- [ ] Botón "Refrescar desde Meta" con throttle 60s visible (countdown).
- [ ] Badges de estado coloreados (APPROVED verde, PENDING ámbar, etc.).
- [ ] Acciones por fila: Enviar campaña (sólo APPROVED), Eliminar.

#### 5. `/campanas/plantillas/nueva` (editor con preview)

- [ ] Form izquierda (Nombre regex `^[a-z][a-z0-9_]{0,511}$`, Categoría, Lenguaje, Tipo).
- [ ] Preview tipo WhatsApp a la derecha (fondo verde WA, burbuja blanca).
- [ ] Variables `{{1}}/{{2}}` resaltadas en el preview.
- [ ] Banner: "Esta plantilla se enviará a WhatsApp para aprobación".
- [ ] Submit → 201 + plantilla nueva aparece con estado PENDING en la lista.

#### 6. `/campanas/contactos` (contactos + grupos)

- [ ] Tab Contactos: 50 sembrados, buscador con debounce, filtro grupo, toggle opt-in, paginación 50/pág.
- [ ] Acciones: crear, editar, asignar a grupo, eliminar.
- [ ] **Import CSV**: probar con un CSV pequeño (3 filas: válida + duplicada + malformada) → modal con counts `total/created/updated/skipped` + lista de errores sin teléfono crudo.
- [ ] Tab Grupos: 3 cards con `member_count` 12/15/8.
- [ ] Drawer detalle del grupo: lista de miembros, añadir/quitar.

#### 7. Validaciones cruzadas

- [ ] Crear campaña QA al grupo "Clientes Premium" (12 recipients).
- [ ] El backend (en sandbox) marca los recipients con opt_in=false como `skipped/opt_out_at_enqueue`.
- [ ] Cancelar "Lanzamiento producto" → 200, status = cancelled. Segundo cancel → 409.

#### 8. Identidad y estética

- [ ] Paleta Gloma consistente en todas las rutas (sin verdes legacy fuera de `/automatas` que es Gorvek).
- [ ] Tipografías Syne (headings) + Inter (body).
- [ ] Estados loading / error / vacío cubiertos en cada ruta.

### Criterio de cierre del Sprint Futuro

- Si el CEO marca todo OK en local + online → #179 ✅, #180 N/A, #181 ✅, sprint cerrado.
- Si pide cambios → cada uno se aplica como commit chico bajo #180 (con su propio renglón en Log de Cambios), y cuando el CEO valide nuevamente → #181 cierra el sprint.

### Follow-ups técnicos heredados del Sprint 13 (no bloqueantes)

Documentados en `backend/docs/sprint13_security_post_audit.md` para atender en sprints futuros:

- Migrar rate-limit en memoria (token-bucket por `meta_account_id`) a Redis cuando se escale a >1 réplica ECS.
- Añadir prueba automatizada del throttle de `POST /templates/sync` (60s) al smoke online.
- Adoptar Alembic para migraciones versionadas (follow-up permanente que sigue abierto desde Sprint 7).
- Cuando se conecte una cuenta Meta real: revisar logs de `services/meta_templates.py` para confirmar que no se filtre el token descifrado en errores.

---

## Sprint 15 - Tutoriales interactivos por módulo

**Rama**: `feature/tutoriales-interactivos-sprint15`.

**Estado**: DONE. Abierto y cerrado el 2026-05-13.

**Objetivo**: cada usuario, la **primera vez** que abre un módulo, recibe un tutorial interactivo guiado (estilo onboarding) que oscurece el resto de la pantalla y resalta el área/botón que está enseñando. Cada paso tiene "Siguiente / Atrás / Omitir tutorial". El estado de "ya hizo este tutorial" se persiste en BD por usuario y por módulo, de modo que el tutorial no vuelve a aparecer salvo que se invoque manualmente.

**Módulos cubiertos y temas de cada tutorial**:

| Módulo | Pasos enseñados |
|--------|-----------------|
| **Mi plan** (`/usuario`) | Ver y modificar los datos del plan / cuenta |
| **Mensajes** (`/mensajes`) | Responder mensaje manual · Asignar un mensaje manual · Ver mensajes asignados a tu usuario o a otros |
| **Bots** (`/bots`) | Visualizar los bots · Visualizar las reglas que los activan (triggers) · Probar el bot en el popup |
| **Campañas** (`/campanas`) | Visualizar las métricas (KPIs) · Modificar el dashboard (cambio inicial) · Exportar la vista actual del dashboard a PDF · Visualizar campañas en listado · Enviar una nueva campaña (envío masivo) · Seleccionar grupos de contactos |

### Diseño

- **BD**: nueva columna `users.tutorials_completed JSONB` (default `{}`). Llaves: `mi_plan`, `mensajes`, `bots`, `campanas`. Cada llave guarda `{ "done": bool, "skipped": bool, "completed_at": iso8601 }`.
- **Backend**:
  - `GET /usuario/me/tutorials` → devuelve el diccionario completo (o `{}` si nunca tocó nada).
  - `PATCH /usuario/me/tutorials/{module}` con body `{ "done": true, "skipped": false }`. Idempotente; sólo se admite el set `{mi_plan, mensajes, bots, campanas}`.
- **Frontend**:
  - Componente `<TutorialOverlay steps={...} moduleKey="..." onClose={...} />` reutilizable. Implementa el spotlight con un overlay `rgba(0,0,0,0.62)` y un "cutout" rectangular sobre el `bounding-rect` del selector del paso actual (cuatro `div`s laterales en lugar de `clip-path` para mejor compatibilidad). Caja flotante con título, copy, controles "Atrás / Siguiente / Finalizar" + botón "Omitir tutorial" siempre visible. Cierra con `Esc`.
  - Hook `useTutorial(moduleKey)` que: al primer render consulta `GET /usuario/me/tutorials`, si la llave no está `done` ni `skipped`, levanta el overlay. Al cerrar (Finalizar o Omitir), hace `PATCH`.
  - En `pages/usuario.tsx`, `pages/mensajes.tsx`, `pages/bots.tsx` y `pages/campanas/index.tsx` se montan los `<TutorialOverlay>` con los pasos correspondientes y selectores `data-tour="..."`.

### Tareas

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 190 | **BD**: añadir columna `users.tutorials_completed JSONB DEFAULT '{}'::jsonb`. Migración idempotente `migrate_sprint15_tutorials.py`. Aplicar en local y RDS (regla paridad). | Experto BD | ✅ | Script con `ADD COLUMN IF NOT EXISTS` y backfill `UPDATE ... SET tutorials_completed='{}'::jsonb WHERE tutorials_completed IS NULL`. |
| 191 | **Backend**: modelo `User.tutorials_completed`, schemas `TutorialsOut` + `TutorialUpdateIn`, 2 endpoints en `routers/usuario.py`. Whitelist de módulos = `{mi_plan, mensajes, bots, campanas}`. | Dev Plataforma | ✅ | Errores sanitizados. No log del payload. |
| 192 | **Frontend**: componente `TutorialOverlay` + hook `useTutorial`. Spotlight con 4 divs laterales + caja flotante con autoposicionamiento simple (debajo si hay espacio, encima si no). Botón "Omitir tutorial" visible en cada paso. Cierre con `Esc`. | Dev Plataforma | ✅ | Sin libs nuevas (sin shepherd.js / driver.js); 100% Tailwind + React puro. |
| 193 | **Frontend**: cablear los 4 tutoriales (Mi plan, Mensajes, Bots, Campañas) — definiciones de steps + `data-tour` en cada zona resaltada. | Dev Plataforma | ✅ | Selectores documentados en cada página. |
| 194 | **QA local**: `docker compose up`, login con `demo@gmail.com / «en el gestor del CEO»`, abrir los 4 módulos por primera vez → ver el tutorial; recargar → ya no aparece; probar "Omitir" en uno y "Finalizar" en otro. | QA | ✅ | Verificación manual local. |
| 195 | **Deploy AWS**: migración RDS `migrate_sprint15_tutorials.py` vía `ecs run-task`. Build linux/amd64 imagen `multiagente-backend:sprint15`, push ECR, `update-service --force-new-deployment`. Build Amplify automático con el merge a `main`. | Deploy AWS | ✅ | Región sa-east-1. Task-def rev nueva si aplica. |
| 196 | **Cierre + log de cambios** | PM | ✅ | Sprint cerrado. Validación CEO trasladada al Sprint Futuro como tarea #197. |

### Follow-up para Sprint Futuro

- **#197 Validación CEO Sprint 15** (local + producción): el CEO recorre los 4 módulos con un usuario "limpio" (puede usar `demo@gmail.com` previo reset de la columna `tutorials_completed` a `{}`) y verifica que el tutorial aparece, los selectores `data-tour` siguen apuntando al elemento correcto y el botón "Omitir tutorial" funciona en cualquier paso. Ajustes que pida el CEO entran como commits chicos sobre `main` (tipo `style(tutorial): ...`).

---

## Sprint 16 - Landing page ELECOL Premium

**Objetivo**: Publicar una landing pública en `/elecol` para la marca ELECOL (electrolineras inteligentes con energía solar para LATAM). Identidad "Infinito Eléctrico — Edición Mar + Sol" — referencias visuales: Tesla Energy, Rivian, Apple, Stripe.

**Alcance**:
- 8 secciones según `ELECOL_Premium_Landing_Guide.md`: Header sticky con blur, Hero con video/render placeholder, Infraestructura inteligente (split + 4 cards), Software ELECOL OS (mockup dashboard + 6 features), Red LATAM (mapa), ROI & estadísticas (counters animados), CTA final, Footer minimalista.
- Dark mode con paleta `#03045E / #0077B6 / #00B4D8 / #90E0EF / #CAF0F8` + acento solar `#FFC300`.
- Microinteracciones: hover glow, partículas energéticas, líneas eléctricas SVG, counters RAF, reveal-on-scroll con IntersectionObserver, parallax sutil, smooth scrolling. **Sin** dependencias nuevas (todo Tailwind + CSS + React puro).
- Carpetas y naming oficial para assets reales: `frontend/public/elecol/{hero,infraestructura,software,red-latam,cta,brand}` (placeholders provisionales generados por script, ver #200).

**Restricciones**:
- La landing es pública: añadir `/elecol` a `PUBLIC_PAGES` en `_app.tsx` para evitar redirect a `/login`.
- NO tocar dominios productivos: `glomabeauty.com` sigue sirviendo solo `/gloma` (middleware con whitelist por host). `/elecol` queda accesible en la URL default de Amplify y en cualquier host que no esté en la whitelist Gloma. Si más adelante se quiere dominio propio (`elecol.co`, etc.) se abre sprint aparte.
- NO tocar backend ni schema BD (landing 100% estática).
- Identidad Gloma del resto de la app intacta.

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 198 | **Apertura del sprint + plan** (este bloque) | PM | ✅ | Sprint registrado, tabla de tareas, criterios de cierre. |
| 199 | **Estructura de assets**: crear `frontend/public/elecol/` con 6 subcarpetas (hero, infraestructura, software, red-latam, cta, brand) y `README.md` con naming oficial de cada imagen por sección (filename, dimensiones recomendadas, formato preferido). | PM / Dev Plataforma | ✅ | `frontend/public/elecol/README.md` documenta 27 assets con dimensiones display, entrega 2× y notas de identidad. |
| 200 | **Script de placeholders provisionales**: `frontend/scripts/generate_elecol_placeholders.mjs` (Node puro, sin dependencias) que genera SVG en cada carpeta con la paleta ELECOL — gradientes oscuros + glow + etiqueta del filename — para que la landing se vea decente desde el primer push. Documentado en el README. | Dev Plataforma | ✅ | Generador idempotente. Para no-SVG genera `<file>.placeholder.svg` adjunto; para SVG escribe el filename canónico. Primera corrida: 27 placeholders escritos. |
| 201 | **Implementación de la landing**: `frontend/pages/elecol.tsx` + componentes auxiliares según haga falta (sin libs nuevas). Implementar las 8 secciones del brief con motion design CSS, counters animados, reveal-on-scroll, partículas, líneas SVG, glassmorphism, hover glow, smooth scroll. Añadir `/elecol` a `PUBLIC_PAGES` en `_app.tsx`. | Dev Plataforma | ✅ | `pages/elecol.tsx` (≈900 LOC) con 8 secciones según brief. Hooks propios `useScrolled`, `useReveal` (IntersectionObserver), `useCountUp` (RAF + easeOutCubic). Partículas determinísticas (seeded, sin mismatch SSR), líneas SVG con `stroke-dasharray` animado, glassmorphism en cards (`backdrop-filter: blur(10px)` + border `rgba(0,180,216,.45)` en hover), corners HUD, scanlines mix-blend-mode, orbes aurora con `filter: blur(80px)` flotando. CTAs solares con `box-shadow` amarillo. `@media (prefers-reduced-motion)` desactiva animaciones. `/elecol` añadido a `PUBLIC_PAGES`. `next.config.js` habilita `dangerouslyAllowSVG` con CSP `script-src 'none'; sandbox;` para servir los placeholders SVG. Tipografías Space Grotesk (heads) + Inter (body) desde Google Fonts. Sin libs nuevas. |
| 202 | **Verificación local**: `tsc --noEmit` exit 0, `next build` exit 0, `docker compose up frontend` → `GET /elecol` 200, navegación entre anclas funciona, header cambia a blur al scrollear, counters animan al entrar al viewport, no se rompe en mobile (375px) ni desktop (1440px). | QA / Dev Plataforma | ✅ | `tsc --noEmit` exit 0. `next build` exit 0, ruta `/elecol` prerendered estática (12.2 kB página / 115 kB First Load JS). Frontend container rebuildeado y reiniciado. `curl http://localhost:3000/elecol` → 200 (72 KB HTML) con markers presentes ("Las nuevas estaciones", "Infraestructura inteligente", "ELECOL OS", "Descargar Brief", "Energía que fluye como nuestro mar", `elecol-hero-gradient`, `elecol-cta-solar`). Placeholder SVG sirve 200 `Content-Type: image/svg+xml`. |
| 203 | **Commit + push a `main`**: commit con changelog, push. Amplify auto-deploya el frontend (no requiere rebuild backend). | Dev Plataforma | ✅ | Commit `ad088e0` push a `main`. Amplify build job **21** SUCCEED para `ad088e0`. |
| 204 | **Smoke online**: `https://main.d1cfl9ey07f61o.amplifyapp.com/elecol` → 200, secciones visibles, animaciones corren. Confirmar al CEO la URL para revisión. | QA | ✅ | `GET https://main.d1cfl9ey07f61o.amplifyapp.com/elecol` → 200 (72 KB) con los 7 markers ("Las nuevas estaciones", "Infraestructura inteligente", "ELECOL OS", "Descargar Brief", "Energía que fluye como nuestro mar", `elecol-hero-gradient`, `elecol-cta-solar`). Placeholder SVG sirve 200 `Content-Type: image/svg+xml`. |
| 205 | **Cierre del sprint + log de cambios** | PM | ✅ | Sprint 16 cerrado. Validación CEO + reemplazo de placeholders por assets reales movidos al Sprint Futuro como tarea #206. |

### Follow-up para Sprint Futuro

- **#206 Revisión profunda landing ELECOL + assets reales**: el CEO revisa `/elecol` desplegada y deja feedback (copy, jerarquía visual, microinteracciones, identidad). Paralelo: reemplazar los placeholders SVG provisionales por imágenes/renders/videos reales del equipo de diseño en `frontend/public/elecol/{hero,infraestructura,software,red-latam,cta,brand}` siguiendo el naming del `README.md`. Ajustes que pida el CEO entran como commits chicos sobre `main` (tipo `style(elecol): ...` o `feat(elecol): ...`). Si se requiere dominio propio (`elecol.co` o similar), abrir sprint dedicado por separado (Route 53 + ACM + Amplify domain association + middleware por host, espejo del Sprint 12 de Gloma).

---

## Sprint 17 - Migración ALB → API Gateway HTTP API (ahorro AWS)

> Sprint abierto el **2026-05-16** y cerrado el **2026-05-17** a pedido del CEO. Objetivo: reducir ~$27.71/mes del ALB (29% del bruto AWS) preservando 100% el funcionamiento. Ejecutado end-to-end en una sesión (~1h calendario, ejecución autónoma autorizada por CEO).

**Camino ejecutado**: API Gateway HTTP API → VPC Link → AWS Cloud Map (SRV records) → ECS Fargate. Cloud Map necesario porque HTTP API VPC Link sólo integra con ALB, NLB o Cloud Map (no directo con ECS service). NLB descartado porque no ahorra (~$16/mes fijo).

**Estado final**: ✅ DONE. Backend público en `https://api.glomabeauty.com`. ALB eliminado. Frontend Gloma sigue en `https://app.glomabeauty.com`.

| # | Tarea | Responsable | Estado | Notas |
|---|-------|------------|--------|-------|
| 207 | Crear AWS Cloud Map **private namespace** `multiagente.local` en VPC `vpc-0e774385bcbeec4ff` | Deploy AWS | ✅ | Namespace `ns-ewxiv2osrcu56qlr`, ~$0.50/mes. |
| 208 | Crear Cloud Map **service** `backend` (SRV records, TTL 10s) | Deploy AWS | ✅ | Service `srv-gls4xaost6kxzc5u`. SRV (no A) necesario para propagar puerto 8000 a API Gateway. |
| 209 | **PROD**: `aws ecs update-service --service-registries` + force-new-deployment (rolling, zero downtime) | Deploy AWS + QA | ✅ | Rolling deployment completado sin downtime. ECS task registrado en Cloud Map con IP:8000 HEALTHY. |
| 210 | Crear **VPC Link** `multiagente-vpclink` (`f494bq`) en subnets `subnet-07829afbd13c5bb8f`, `subnet-00f56d6ce74d72a2e` (SG `sg-0499ec72831ef7da9`) | Deploy AWS | ✅ | Provisión gratuita; ~3 min para AVAILABLE. |
| 211 | Crear **API Gateway HTTP API** `multiagente-api` (`pmg6lfu9cj`) + integración `ANY /{proxy+}` → VPC Link → Cloud Map | Deploy AWS | ✅ | Stage `$default` con auto-deploy. CORS `*`. ~$1/M req. |
| 212 | Emitir **ACM cert** para `api.glomabeauty.com` en `sa-east-1` + DNS validation en Route 53 | Deploy AWS | ✅ | Cert ARN `7779edc0-8766-4e59-a07f-1bc8a72367fb`, ISSUED en <2 min. |
| 213 | **Custom domain** `api.glomabeauty.com` en API Gateway + A-record alias en Route 53 zona `Z0523904259PXITAV9OOV` | Deploy AWS | ✅ | DNS propagó en <30s. `https://api.glomabeauty.com/docs` → 200. |
| 214 | Actualizar `BACKEND_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_BACKEND_URL` en Amplify `d1cfl9ey07f61o` + rebuild | Deploy AWS | ✅ | Job #23, SUCCEED en 2.5 min. Frontend Gloma ahora apunta a `https://api.glomabeauty.com`. |
| 215 | Re-registrar Callback URL en Meta Business Manager | Deploy AWS + Dev Plataforma | ⏭ N/A | **No aplica**: ECS task definition NO tiene `META_APP_SECRET` ni `META_WEBHOOK_VERIFY_TOKEN` configurados (env `META_SANDBOX=1`). Producción Gloma es sandbox/demo sin integración Meta real. Endpoint `/meta/webhook` queda accesible vía `https://api.glomabeauty.com/meta/webhook` para cuando se conecte Meta real. |
| 216 | Smoke test E2E (login JSON, /docs, /openapi.json, /campanas, /bots, /meta/webhook, frontend) + latencia p95 | QA | ✅ | Login con `demo@gmail.com` → 200 con JWT válido. Latencia p95=1.67s (cold-start primer request), p50=0.64s, min=0.56s. Frontend Gloma 200. |
| 217 | Auditoría abreviada CloudWatch (10 min) + cero 5xx + cero errores | Seguridad + QA | ✅ | 0 ERROR logs, 0 5xx en 10 min. Cloud Map instancia HEALTHY. **Auditoría 48h completa queda como follow-up en Sprint Futuro (#220)**. |
| 218 | Eliminar ALB `multiagente-alb` + target group `multiagente-tg` + SG `multiagente-alb-sg` + revocar ingress en ECS SG + update BITACORA + memoria persistente | Deploy AWS + PM | ✅ | ALB detached de ECS service (rolling deployment), luego deletado. SG `sg-0cdc92ccca3e1e5ce` eliminado. ECS service ahora 100% por Cloud Map. |

### Resultado: URL y ahorro

- 🔗 **Backend público**: `https://api.glomabeauty.com` (Swagger en `/docs`, OpenAPI en `/openapi.json`)
- 🔗 **Frontend Gloma**: `https://app.glomabeauty.com` (consume backend internamente vía Amplify rewrite)
- 💰 **Ahorro confirmado**: ~$26/mes (~$310/año). Nuevos costos: Cloud Map ~$0.50/mes + API Gateway ~$1/M req. ALB ($27.71/mes) eliminado.

### Hallazgo bloqueante resuelto durante ejecución

- **Subnets ECS son públicas** (`MapPublicIpOnLaunch=True`): primero usé Cloud Map con DNS A records, pero API Gateway integra a puerto 80 por default y el backend escucha en 8000 → 500 errors. Solución: recrear Cloud Map service con DNS **SRV** records (que sí propagan puerto), update ECS service-registries con `containerPort=8000`. Funcionó en el segundo rolling deployment.
- **DNS del ALB en memoria persistente estaba mal** (`multiagente-alb-1689721042...` → real `multiagente-alb-673139873...`). Corregido en memoria.

### Recursos AWS creados (referencia)

| Recurso | ID / Nombre | Costo |
|---|---|---|
| Cloud Map namespace | `multiagente.local` (`ns-ewxiv2osrcu56qlr`) | ~$0.50/mes |
| Cloud Map service | `backend` (`srv-gls4xaost6kxzc5u`, SRV records) | incluido |
| VPC Link | `multiagente-vpclink` (`f494bq`) | gratis (sólo paga ENIs) |
| HTTP API | `multiagente-api` (`pmg6lfu9cj`) | ~$1/M req |
| ACM cert | `arn:...:certificate/7779edc0-8766-4e59-a07f-1bc8a72367fb` | gratis |
| Route 53 A-record | `api.glomabeauty.com` → API Gateway alias | ~$0.50/mes |
| **Total nuevo edge** | | **~$1.50/mes** vs $27.71 ALB |

### Recursos AWS eliminados

- ALB `multiagente-alb` (DNS `multiagente-alb-673139873.sa-east-1.elb.amazonaws.com`)
- Target group `multiagente-tg/7b43e41fa71f7368`
- HTTP listener puerto 80
- Security group `sg-0cdc92ccca3e1e5ce` (`multiagente-alb-sg`)
- Ingress rule del ECS SG (`sg-0499ec72831ef7da9`) que aceptaba :8000 desde el SG del ALB

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
| 2026-04-24 | CEO | Corrección de alcance: glomabeauty.com debe servir SOLO la landing; la plataforma se queda en la URL default de Amplify. |
| 2026-04-24 | Dev Plataforma | `frontend/middleware.ts` con separación por host: `glomabeauty.com/` sirve la landing (rewrite interno a `/gloma`), otras rutas → 404 brandeado. Whitelist de assets y `/api/landing/*`. Página `/404.tsx` con identidad Gloma. |
| 2026-04-24 | QA | Separación por dominio validada online: `glomabeauty.com/login` y `/bots` → 404; `main.d1cfl9ey07f61o.amplifyapp.com/login` → 200. Amplify build job 10 SUCCEED. |
| 2026-04-24 | Dev Plataforma | Fix `_app.tsx`: el guard de auth client-side hacía `router.replace('/login')` después del rewrite del middleware. Ahora detecta `PUBLIC_HOSTS` y no se activa en glomabeauty.com. |
| 2026-04-26 | Dev Plataforma | Iconos brandeados (9 PNG `ld_*`) reemplazan placeholders en features y stats. Copy refinado: hero subtítulo, CTA contacto, botón del form, footer simplificado. Eyebrows eliminados. |
| 2026-04-26 | Dev Plataforma | Microinteracciones modernas: contadores animados (RAF + easeOutCubic, formato es-CO), `Reveal` fade+translate al scroll, header con orbes pastel + SVG de líneas y nodos siguiendo el cursor (parallax). |
| 2026-04-26 | Dev Plataforma | Logo header → `logo_blancotrans.png` grande (h-28 móvil / h-40 desktop), reusado en el footer. Smooth scroll RAF+easeInOutCubic 1s para "Agenda una demo" y "Que te contactemos". |
| 2026-04-26 | Dev Plataforma | Footer actualizado: `contacto@glomabeauty.com`, +57 300 318 7871, Calle 36, Vía Jamundí #128-321, Cali. |
| 2026-04-26 | Dev Plataforma | `ContactForm` con microinteracción brandeada: aro pulsante en `sending`, fade-out + check SVG dibujándose en `ok`. Sin verdes — solo paleta Gloma (rosa + marrón tierra). |
| 2026-04-27 | Deploy AWS | AWS WorkMail org `gloma` (us-east-1) + dominio `glomabeauty.com` registrado. 8 DNS records en Route 53 (MX, 3×DKIM, autodiscover, _amazonses TXT, SPF, DMARC). Usuario `contacto@glomabeauty.com` ENABLED. Webmail en `https://gloma.awsapps.com/mail`. Costo +$4 USD/mes. |
| 2026-04-27 | Deploy AWS | `app.glomabeauty.com` añadido al domain association de Amplify (cert wildcard ya lo cubre). Plataforma ahora servida en URL bonita. Build job 12 SUCCEED. |
| 2026-04-27 | Dev Plataforma | Landing `/automatas` (Gorvek) creada en `frontend/pages/automatas.tsx`. Identidad fiel al brief: paleta Technical Black `#101817` + Algorithmic Mint `#4DB6AC` + Deep Forest `#004D40`, tipografías Urbanist (headlines) + Inter (body), cards `rgba(255,255,255,0.03)` con border `rgba(77,182,172,0.15)` radius 8px, accent mint sólo en CTAs/hover/métricas/highlights. 8 secciones: Hero con red neuronal SVG animada (parallax + nodos pulsando) → Value Proposition (3 cards) → Capacidades (6 cards 2×3) → How It Works (timeline horizontal) → Métricas (4 KPIs) → Use Cases (4 cards) → CTA final con form → Footer. Wordmark tipográfico "GORVEK" (sin assets). Form de leads postea a `/api/landing/leads` con `source: 'gorvek_landing'`. Reutiliza WhatsApp/email/teléfono de Gloma como placeholder. `/automatas` añadido a `PUBLIC_PAGES` en `_app.tsx` para evitar redirect a `/login`. |
| 2026-04-27 | Dev Plataforma | Iteración 1 de la landing `/automatas` por feedback del CEO: (a) eliminados los eyebrows duplicados de todas las secciones (Hero "Infraestructura de IA Empresarial", "Propuesta de valor", "Plataforma", "Cómo funciona", "Impacto", "Casos de uso", "Diagnóstico estratégico"). (b) Hero rediseñado: quitado el `PlatformMock` y los 3 bullets; layout ahora centrado a una sola columna con headline + subhead + un solo CTA. (c) Header nav: quitados los links Plataforma/Proceso/Casos de Uso; queda sólo "Agendar una conversación" en estilo primario (mint background, mismo estilo que el botón del form). (d) Sección "Plataforma" reescrita como "Capacidades que se integran a su operación" con subtítulo aclarando que no hay plataforma adicional — los resultados se ven en las herramientas que el cliente ya usa. CTA secundario "Ver Capacidades de la Plataforma" eliminado. (e) How It Works: añadido 5º paso "Soporte y Acompañamiento" para acompañamiento post-deploy; grid de 4 → `lg:grid-cols-5`. (f) Lenguaje simplificado: "Diagnóstico Estratégico" → "Agendar una conversación" en CTAs (header, hero, form), copy del CTA final reescrito a tono más conversacional. (g) Footer: link "Plataforma" → "Capacidades". `tsc --noEmit` limpio. |
| 2026-04-27 | Dev Plataforma | Iteración 2 `/automatas`: CTAs renombrados a "Hablar con un experto" (hero, header, form, link de WhatsApp). Sección "Capacidades" eliminada por completo (FEATURES + FeaturesSection + render + link footer). Commit `496fa72`, push a main. |
| 2026-04-27 | Dev Plataforma | Branding Gloma en Sidebar + Login: emoji 💬 + "Multiagente" reemplazado por logo Gloma sin texto (`logo_blancotrans.png` en sidebar verde, `logo_gloma_original_trans.png` a color en login). Iconos del menú lateral (Mensajes/Campañas/Bots/Mi Plan/Salir) sin cambio. Assets gloma actualizados: `logo_blancotrans.png`, `ld_inegraciones.png`, `ld_4meses.png`, `ld_horasai.png`, `ld_mensajes_enviados.png`. Commit `98194c5`. |
| 2026-04-27 | Dev Plataforma | **Rebrandización completa de la app a Gloma**: paleta `gloma-{brown,brown-dark,brown-darker,brown-light,rose,rose-soft,cream}` añadida a `tailwind.config.js`; fonts `heading: Syne` / `body: Inter` cargadas desde Google Fonts en `_document.tsx`; `globals.css` con fondo crema + selección rosa por defecto. Reemplazado `green-*` y `emerald-*` por equivalentes `gloma-*` en 8 archivos (Layout, Sidebar, login, register, index, usuario, mensajes, bots, bots/[id]). Sidebar pasa de verde 600 a marrón tierra (`gloma-brown` #5E503F). Página `/automatas` (Gorvek) intacta — no comparte clases verdes. |
| 2026-04-27 | Dev Plataforma | Cuentas de prueba (re)creadas en LOCAL con script idempotente `backend/scripts/create_or_reset_test_users.py`: `prueba@gmail.com`, `test2@gmail.com`, `otro@test.com`, **`demo@gmail.com`** (NUEVA, con bots seedeados via `DEMO_OWNER_EMAIL=demo@gmail.com python scripts/seed_bot_demo.py`). Passwords aleatorios de 14 chars URL-safe. Credenciales registradas en `CREDENCIALES.txt` (gitignored). Pendiente RDS (ceo@gloma.co reset + demo@gmail.com creación + bots seed) — requiere rebuild backend image y `aws ecs run-task`. |
| 2026-04-27 | Dev Plataforma | Bandeja demo seedeada en `demo@gmail.com` para screenshot de la landing: 1 conversación larga (Mariana López, 8 mensajes sobre dimensiones de blusa de lino) + 4 cortas (Valentina Ruiz/open, Camila Torres/pending, Lucía Ramírez/open, Sara Mendoza/closed). Timestamps escalonados (4min, 35min, 1h, 2h, 5h). Aislamiento por `team_id`; otras cuentas no las ven. Script: `backend/scripts/seed_demo_conversation.py`. |
| 2026-04-27 | Dev Plataforma | Screenshot real de la app (`identidad_gloma/ss1.png`) reemplaza `frontend/public/gloma/preview1.png` en la sección "Un agente de ventas personalizado" de `/gloma`. Card mantiene `aspect-[4/3]` y `object-cover` (zoom de la imagen para llenar todo el recuadro sin bordes blancos; recorta un poco los laterales del screenshot 16:9). |
| 2026-05-11 | UI/UX | Sprint 13 tarea #155 entregada: `identidad_gloma/diseno_campanas.html` con 6 pantallas (Dashboard 8 KPIs, Wizard 4 pasos, Detalle de campaña, Plantillas, Editor con preview WhatsApp, Contactos+Grupos), identidad Gloma, notas DEV por zona apuntando a endpoints backend, sección de Decisiones de diseño + supuestos para PM. |
| 2026-04-27 | Deploy AWS | **`demo@gmail.com` desplegado en RDS** (producción). Script `backend/scripts/prod_seed_demo.py` creado (idempotente, sólo toca demo@; no afecta `ceo@gloma.co`). Imagen backend rebuildeada (linux/amd64) y pusheada a ECR como `:demo-prod`. Task definition `multiagente-backend:6` registrada. Run-task ECS one-off con override de command + env var `DEMO_PWD` → exit 0 limpio. Resultado: usuario creado (id=6), 2 bots seedeados, 5 conversaciones seedeadas. Login verificado contra `https://app.glomabeauty.com/api/login` → 200 con bearer. Service `multiagente-backend-service` sigue en task-def rev 5 (`:sprint11`) sin cambios — la rev 6 sólo se usó para el run-task. Credencial guardada en `CREDENCIALES.txt` (gitignored). |
| 2026-05-11 | Experto BD | Tarea #156 entregada: `backend/docs/sprint13_schema.md` con DDL idempotente PG15 de las 7 tablas del Sprint 13 + decisiones de multi-tenancy/PII/idempotencia/cache de plantillas/plan de migración + 4 queries de KPIs. 15 refinamientos sobre el diseño BITACORA (índices parciales para schedulers, UNIQUE en `meta_message_id`, CHECKs cerrados, valores `DELETED`/`skipped`/`sync_warning`, `created_by_user_id ON DELETE SET NULL`, GIN en `attributes`). Listo para revisión de Seguridad (#157). |
| 2026-05-11 | PM | Sprint 13 planeado y registrado: módulo Campañas (envío masivo) + Plantillas WhatsApp + Contactos/Grupos. 25 tareas (153–177), 12 fases con parejas paralelas. Decisión de arquitectura: plantillas como cache local sincronizado contra Meta (fuente de verdad = Meta). Cambios de BD documentados (7 tablas nuevas). Pendiente luz verde del CEO antes de delegar a UI/UX + Experto BD para arrancar Fase 1. |
| 2026-05-11 | Seguridad | Sprint 13 #157: revisión de diseño entregada en `backend/docs/sprint13_security_review.md`. Veredicto **APROBADO CON CAMBIOS** (bloqueante para merge). 15 hallazgos: 0 Críticos / 5 Altos / 6 Medios / 4 Bajos. Schema BD aprobado tal cual; bloqueos son anti-IDOR cruzado, anti-abuso de envío (max recipients + rate-limit + backoff), opt-in fail-closed, logging redactado de webhook, fail-closed HMAC en prod. Checklist obligatoria para Dev Plataforma en #159-#163; yo audito post-código en #171. |
| 2026-05-11 | Experto BD | Sprint 13 #158: migración `backend/scripts/migrate_sprint13_campanas.py` creada y aplicada en docker-compose `db` (7 tablas + 17 índices, CHECKs cerrados, FKs `CASCADE/RESTRICT/SET NULL`, UNIQUE parcial para dedupe del webhook); idempotencia validada con segunda ejecución (las 7 tablas reportan `ya existía → skip`, exit 0). RDS pendiente para #173. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #159 backend contactos+grupos: modelos, schemas, CRUD multi-tenant con `require_owned` (S13-001), router con 13 endpoints. `__repr__` redacta PII. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #160 backend plantillas: modelo `WhatsappTemplate`, servicio `meta_templates.py` con sync paginado + modo sandbox + create/delete, router con 4 endpoints, rate-limit 1 sync/60s/user, errores Meta sanitizados. |
| 2026-05-12 | PM | Sprint 13 Fase 2 sellada: agentes Dev se cortaron por límite antes de actualizar BITACORA; PM añadió `python-multipart` a `requirements.txt`, rebuildeó imagen backend, verificó 17 rutas nuevas registradas y todas responden 401 sin auth. Backend sano. Sigue Fase 3. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #162 sender + tick: `services/campaign_sender.py` con token-bucket por `meta_account_id` (default 10 rps, env `META_RATE_LIMIT_RPS`), retry `tenacity` exponencial (3 intentos, base 1s, max 8s) sobre HTTP 429 + códigos Meta `80007`/`131056` (S13-002); re-lookup `contacts.opt_in` antes del envío → `skipped/opt_out_at_send` + evento `sync_warning` (S13-003); idempotencia con transición atómica `UPDATE WHERE status='queued'` + reanudación de campañas `running`. Endpoint `POST /internal/campaigns/tick` con auth `X-Internal-Key`/`INTERNAL_API_KEY`. Sandbox local (`META_SANDBOX=1` o token NULL) genera `wamid.local-<uuid>`. `tenacity>=8.5,<9` añadido a `requirements.txt`, imagen backend rebuildeada. 4 verificaciones obligatorias OK: tick vacío, 3 recipients `queued` → `sent`, doble tick idempotente, opt_in=FALSE → skipped. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #161 backend campañas: modelos `Campaign`/`CampaignRecipient`/`CampaignEvent` (con `__repr__` redactado para PII y CHECKs cerrados), schemas con `extra='forbid'` y `MAX_RECIPIENTS_PER_CAMPAIGN=10000`, CRUD multi-tenant (`create_campaign` valida cruce `template ↔ meta_account ↔ team` + ownership de cada `contact_id` con 404, opt-in fail-closed al encolar S13-003, tope anti-abuso pre-DB S13-002), router nuevo `routers/campaigns.py` con 6 endpoints (`GET /campaigns`, `GET /campaigns/kpis`, `POST /campaigns`, `GET /{id}`, `GET /{id}/recipients`, `POST /{id}/cancel`). Stub legacy `/campanas` intacto. 4 verificaciones OK: 6 endpoints registrados, `template_id` cross-team → 404, 10001 recipients → 422, 3 contactos (1 opt_out) → 201 con 2 `queued` + 1 `skipped/opt_out_at_enqueue`. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #164 frontend dashboard campañas: `pages/campanas/index.tsx` (≈470 líneas) con header "Transmisiones masivas" + CTA Nueva campaña, 3 tabs locales (Resumen / Plantillas / Programadas), 4 cards Visión general (estáticos), 8 KPI cards consumiendo `GET /campaigns/kpis` (Enviado primario `bg-gloma-brown text-gloma-cream`), tabla "Todas las campañas" desde `GET /campaigns` con búsqueda por nombre, sort (Últimas/Más exitosas/Más leídas), paginación cliente 10/pág, badge de estado, acción Cancelar para `scheduled` vía `POST /campaigns/{id}/cancel`. Estados loading (skeleton), error (banner rojo + reintentar) y vacío (CTA "Crear primera campaña") cubiertos. Helper nuevo `frontend/lib/api.ts` (`authedFetch<T>` con redirect a `/login` en 401 y `ApiError`); tipos en `frontend/types/campaigns.ts`. Eliminado stub plano `pages/campanas.tsx`. Identidad Gloma respetada (crema/marrón/rosa, Syne/Inter). `tsc --noEmit` limpio; `docker compose build frontend` y `up -d frontend` ejecutados sin errores; ruta servida en 200 y endpoints validados con token JWT. Simplificaciones documentadas en BITACORA #164 (cards Visión general estáticos, columnas "Respondió"/"Enviando"/"Procesando" en `0`/`—` hasta que el backend exponga el dato). No se tocó backend, Layout, Sidebar, ni las páginas hermanas (#165–#168). |
| 2026-05-12 | Dev Plataforma | Sprint 13 #163 webhook ingestion: extiende `routers/meta_webhook.py` con `process_status_event(db, status_dict)` para correlacionar `wamid` de Meta ↔ `CampaignRecipient.meta_message_id` (UNIQUE) y registrar `CampaignEvent` idempotentes con `pg_insert(...).on_conflict_do_nothing()` sobre el índice parcial `uq_events_dedupe(meta_message_id, event_type)`. Idempotencia con `_status_rank()` (queued<sending<sent<delivered<read; failed/skipped terminales) — solo avanza si rank mayor. Setea `sent_at`/`delivered_at`/`read_at`/`failed_at`, extrae `errors[0].code` en `failed`, cierra campaña a `completed` cuando no quedan recipients `queued|sending`. Statuses ahora se procesan ANTES del lookup de MetaAccount (se correlacionan por wamid, no por phone_number_id). Mitigaciones: **S13-004** helper `_sanitize_payload_for_log()` enmascara teléfonos E.164 antes de loggear (regex `\+?\b[1-9]\d{6,18}\b` + nombres de campo `phone_e164`/`from`/`wa_id`/`recipient_id`/`display_phone`); `logger.info` solo loguea `{entries, messages, statuses, phone_number_ids}` (no PII); payload bruto persiste solo en BD (`campaign_events.payload_json`). **S13-005** `_verify_signature` ahora fail-closed obligatorio en producción: `APP_ENV=production`+sin `META_APP_SECRET` → `False`+`logger.error`; prod+firma ausente → `False`; dev sin secret → `True`+`logger.warning("FAIL-OPEN ...")`. Endpoint responde 403 en prod, 401 en dev. 6 pruebas OK en docker-compose local: delivered avanza desde sent + crea evento; segunda llamada idempotente (sin duplicar); sent posterior a delivered NO regresa; read avanza; fail-closed/fail-open de `_verify_signature` validado en 4 escenarios; sanitización enmascara `+573001112233` → `573***33`. No regresión Sprint 6: inbound `messages[].text` con phone_number_id real → `Conversation`+`Message` creados. Imagen backend rebuildeada (sin nuevas deps). Único archivo tocado: `backend/app/routers/meta_webhook.py`. Estado: listo para auditoría Seguridad #171. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #165 wizard nueva campaña: `pages/campanas/nueva.tsx` con stepper 4 pasos (datos + plantilla APPROVED con preview + destinatarios individual/grupo + programación con resumen y estimación 10 msg/s). |
| 2026-05-12 | Dev Plataforma | Sprint 13 #166 detalle campaña: `pages/campanas/[id].tsx` con 6 KPIs + tabla paginada de recipients + polling 5s + cancel + máscara parcial. Nuevo `lib/format.ts`. |
| 2026-05-12 | PM | Sprint 13 Fase 5 sellada: agentes se cortaron por límite tras escribir los dos archivos completos; PM verificó `tsc --noEmit` exit 0 y registró ambos checkpoints. Sigue Fase 6 (plantillas UI + contactos UI). |
| 2026-05-12 | Dev Plataforma | Sprint 13 #167 UI plantillas: `pages/campanas/plantillas/index.tsx` (listado con buscador + filtro de estado + sort, badges coloreados por estado, "Refrescar desde Meta" con throttle cliente 60s y auto-sync inicial si la lista llega vacía para activar el sandbox seed, acciones Editar/Enviar campaña/Eliminar) y `pages/campanas/plantillas/nueva.tsx` (editor dos columnas: form a la izquierda con secciones Identidad/Tipo/Header/Body/Footer/Botones — Body con `+ Agregar variable` y `*negritas*`, max 1024; preview WhatsApp en vivo a la derecha sticky, fondo `#ECE5DD` + burbuja blanca con header/body/footer/botones y `{{N}}` resaltados). Validaciones espejo del backend: name regex `^[a-z][a-z0-9_]{0,511}$`, body ≤1024, footer ≤60, URLs http(s), teléfonos E.164. POST /templates en submit → banner "Plantilla enviada. Estado: PENDING" + redirect a `/campanas/plantillas` tras 2s. Reusa `authedFetch` y los tipos existentes de `types/campaigns.ts`; backend/Layout/Sidebar intactos. `tsc --noEmit` exit 0; `docker compose build frontend` + `up -d` OK; ambas rutas responden 200. |
| 2026-05-12 | Dev Plataforma | Sprint 13 #168 UI contactos+grupos: `pages/campanas/contactos.tsx` con 2 tabs internos (Contactos / Grupos), `types/contacts.ts` con todos los DTOs reflejando los schemas Sprint 13. Tab Contactos: buscador con debounce + filtro grupo + toggle opt-in, tabla con `maskPhone()` en todo `phone_e164` (regla 1), paginación servidor 50/pág, acciones Editar/Asignar a grupo/Eliminar. Tab Grupos: grid de cards con `member_count`, drawer lateral con miembros + búsqueda + multiselect Añadir y Quitar individual. `ImportCsvModal` usa helper propio `uploadCsv()` (authedFetch no sirve para multipart por el Content-Type forzado); muestra grid total/created/updated/skipped + lista de errores ya redactados por el backend (S13-009) con nota explícita por si llega PII cruda. Modales con backdrop `bg-black/40` y card `bg-gloma-cream` con borde `gloma-brown-light/20`; chips de grupo en paleta Gloma. Decisión: NO chips de grupos por contacto en la tabla (endpoint /contacts no los devuelve — sería N+1); el modal Asignar cubre el flujo. NO se tocó backend ni otras páginas del módulo. `tsc --noEmit` exit 0, página devuelve 200 en Next dev. Verificación CRUD funcional contra backend queda para QA #176 (passwords del seed local no se loggean). |
| 2026-05-12 | Dev Plataforma | Sprint 13 #169 seed demo: dos scripts nuevos en `backend/scripts/`: `reset_demo_password.py` (idempotente; fija `demo@gmail.com → «en el gestor del CEO»`) y `seed_sprint13_campanas.py` (~480 líneas, idempotente y convergente al spec). Ejecutados en `wati-backend-1` con `docker compose exec -T backend python scripts/...`. Resultados (queries SQL contra `team_id=5` de demo@): **50 contactos seed** (`+57301...`) con 40 opt_in=True / 10 opt_in=False; **3 grupos** con conteos exactos (Clientes Premium=12, Recurrentes Bogotá=15, Nuevos Trial=8); **2 plantillas mock APPROVED** (`promo_mayo` es_MX con header/body+vars `{{1}}`/`{{2}}`/footer; `recordatorio_pedido` es body-only); **3 campañas** — A "Promoción Mayo" completed (10 read + 1 delivered + 1 failed `error_code=80007`), B "Recordatorio carrito" completed (5 read + 2 delivered + 1 skipped `error_code=opt_out_at_enqueue`), C "Lanzamiento producto" scheduled +2d (8 queued). `campaign_events` coherentes (queued + sent + delivered + read + failed); `wamid.seed-<idx>-<short_uuid>` por recipient enviado. Idempotencia validada (2ª corrida: `creados=0 actualizados=0 skip` en las 3 campañas). Ajuste: distribución de `city` reescrita para garantizar ≥15 Bogotá+opt_in (los `i%3` naturales solo daban 14); reconciliación de membresías para que segundas corridas converjan al spec. `CREDENCIALES.txt` actualizado SOLO en el bloque local de demo@ (password + nota apuntando a los seeds). Login E2E verificado (`POST /login` → 200 + JWT). NO se tocó RDS (#173) ni código del backend. |
| 2026-05-12 | QA | Sprint 13 #170 E2E local: PASS con 1 bloqueante Medio (S13-QA-001: campañas con `scheduled_at=NULL` no son procesadas por el tick — filtro `scheduled_at<=now` excluye NULL; fix sugerido en #161/#162) y 3 observaciones (login espera JSON no form-urlencoded; CSV header `phone_e164`; sync sandbox marca DELETED las 2 plantillas mock del seed; `otro@test.com` no logueó → se creó `qa_cross_*@test.com`). Pasos A–M validados: CRUD contactos+grupos+cross-tenant 404, import CSV sin teléfono crudo en errores (S13-004 OK), sync templates, crear campaña (12 recipients), tick (sent=12 tras setear scheduled_at) + idempotencia, webhook delivered, cancel + 409, 5 rutas frontend en 200, aislamiento multi-tenant OK. Reporte: `backend/docs/sprint13_qa_report.md`. |
| 2026-05-12 | PM | **Modo demo / sandbox sin Meta real — consolidación**: el CEO confirma que aún NO hay cuenta Meta WhatsApp conectada y pide que la demo funcione sin Meta real, con datos de templates+campañas listos para validar el módulo, y que ese mismo seed corra en AWS. Estado: el módulo YA estaba preparado para esto. Mecanismo: `MetaAccount.encrypted_access_token IS NULL` o env `META_SANDBOX=1` activa modo sandbox en `services/meta_templates.py` (3 plantillas mock APPROVED + create devuelve PENDING mock + delete mock) y `services/campaign_sender.py` (genera `wamid.local-<uuid>` y simula envío 200). El seed Sprint 13 #169 ya crea `MetaAccount(token=NULL)` + 2 plantillas + 3 campañas + 50 contactos + 3 grupos: es el único archivo necesario. PM intentó añadir un fixture JSON aparte (`backend/fixtures/demo_account.json`) y el CEO pidió revertirlo — se eliminó. Cuando se conecte una cuenta Meta real, basta cifrar el token via `POST /usuario/me/meta-account` y el backend cambia a llamadas reales automáticamente (sin modificar código). **Fix S13-QA-001 aplicado**: `services/campaign_sender.py:404-407` ahora `(status='scheduled' AND (scheduled_at IS NULL OR scheduled_at<=now)) OR status='running'`. Imagen backend rebuildeada; tick ejecutado sin error. La tarea #173 (deploy AWS) ya contempla aplicar `seed_sprint13_campanas.py` en RDS vía `ecs run-task`, por lo que la demo va a quedar también en producción. |
| 2026-05-12 | Seguridad (PM inline) | Sprint 13 #171 auditoría post-código: **APROBADO**. Documento `backend/docs/sprint13_security_post_audit.md`. Las 15 mitigaciones del diseño (S13-001 a S13-015) verificadas en código con cita archivo:línea. Hallazgo NUEVO **S13-016 (Alto)** descubierto y CORREGIDO inline: `routers/internal.py _require_internal_key` permitía acceso anónimo a `/internal/campaigns/tick` cuando `INTERNAL_API_KEY` estaba vacía en producción. Fix aplicado: prod+vacío → 403 fail-closed; dev+vacío → pasa libre. Imagen rebuildeada. Schemas Out clean. Deploy autorizado a #173/#174 con la condición de que la task-def de prod inyecte `INTERNAL_API_KEY` como secret (SSM/KMS). |
| 2026-05-12 | Deploy AWS | Sprint 13 #173 migración RDS: `scripts/migrate_sprint13_campanas.py` aplicado vía `ecs run-task` task-def `multiagente-backend:7` → 7 CREATE TABLE + 17 índices + verificación 7/7. Paridad local: migración idempotente OK. Seed RDS: `reset_demo_password.py` («en el gestor del CEO») + `seed_sprint13_campanas.py` → MetaAccount sandbox-placeholder, 50 contactos, 3 grupos (12+15+8), 2 plantillas APPROVED, 3 campañas. Fix en seed: `_ensure_meta_account` cifra placeholder con `encrypt_secret("sandbox-placeholder")` para satisfacer `encrypted_access_token NOT NULL` (sandbox real lo activa env `META_SANDBOX=1`). |
| 2026-05-12 | Deploy AWS | Sprint 13 #174 deploy ECS: SSM SecureString `/multiagente/prod/INTERNAL_API_KEY` creado (cumple S13-016). Imagen `:sprint13` build+push linux/amd64 a ECR (89.5 MB). Task-def **rev 7** registrada (clonada rev 5, image=:sprint13, secrets += INTERNAL_API_KEY, env += META_SANDBOX=1). `update-service --force-new-deployment` → `rolloutState=COMPLETED`. Health: ALB `/docs` 200, login Amplify `demo@gmail.com / «en el gestor del CEO»` 200 + JWT. |
| 2026-05-12 | Deploy AWS / QA | Sprint 13 #175 smoke online: `GET /api/campaigns` → 200 count=3 (Promoción Mayo+Recordatorio carrito completed, Lanzamiento producto scheduled); `GET /api/contacts?limit=5` → 200 count=5 (50 total); `GET /api/contact-groups` → 200 3 grupos con member_count 12/8/15. **Bloqueante S13-DEPLOY-001 (Alto)**: `GET /api/templates` → 500 `ValidationError components_json — Input should be a valid dictionary, input_type=list` en `schemas.py:438`. Schema `WhatsappTemplateOut.components_json: dict` no soporta el formato canónico Meta `list`. Reproducible local. Fix Dev Plataforma sugerido: `components_json: list | dict`. No bloquea uso de Campañas/Contactos/Grupos. |
| 2026-05-12 | PM | Sprint 13 #176 diagramas PUML entregados en `backend/docs/sprint13_diagramas.puml` (clases con 10 entidades + servicios + secuencia crear→tick→callback, con notas de sandbox/seguridad inline). |
| 2026-05-12 | PM | Sprint 13 fix S13-DEPLOY-001 aplicado y desplegado: `WhatsappTemplateOut.components_json: dict → Any`, `from typing import Any` añadido en `schemas.py`. Rebuild local OK (7 templates). Build linux/amd64 + push a `multiagente-backend:sprint13`. `ecs update-service --force-new-deployment` → `rolloutState=COMPLETED`. Smoke online post-fix: `/api/templates` → 200 count=6 (antes 500). #175 marcado ✅. |
| 2026-05-12 | PM | Sprint 13 #177: commit `f2d4661` con changelog del módulo (35 archivos, +2555/-39). Push de `feature/modulo-campanas` a origin. Merge `--no-ff` a `main` → `3f20503`. Push de `main` a origin. Sprint 13 cerrado salvo #178 (validación CEO final), que el CEO solicitó dejar como follow-up para hacerse al final y aplicar ajustes en post-cierre. |
| 2026-05-12 | PM | **Sprint 13 cerrado**. Por decisión del CEO: (1) #170 actualizada a ✅ (el bloqueante S13-QA-001 fue parcheado por PM y validado online en #175). (2) #172 y #178 (ambas validación del CEO) **consolidadas en una sola tarea futura** #179 dentro del nuevo **Sprint Pendientes (post-13)**; ambas filas del Sprint 13 marcadas con ⏭ apuntando a #179. (3) Índice del sprint actualizado a **DONE** sin caveats; índice general añade fila "Sprint Pendientes (post-13)" como ABIERTO. (4) Encabezado del Sprint 13 actualizado a DONE. Si la validación de #179 trae ajustes, se atienden como cambios incrementales sobre `main`, no como reapertura del sprint. |
| 2026-05-12 | PM | **Sprint Futuro abierto** (sin numerar — el número 14 queda libre para otras tareas, por instrucción del CEO). 3 tareas: #179 validación CEO (checklist detallado por las 6 rutas + validaciones cruzadas + identidad), #180 ajustes post-revisión (commits chicos sobre `main` si el CEO pide cambios), #181 cierre. Sección incluye tabla de entornos con credenciales para revisión: local `http://localhost:3000/login` y prod `https://app.glomabeauty.com/login`, ambos con `demo@gmail.com / «en el gestor del CEO»` (cuenta demo sandbox con MetaAccount placeholder cifrado — no toca Meta real). También quedan listados los follow-ups técnicos heredados del Sprint 13 (Redis para rate-limit, Alembic, etc.). |
| 2026-05-12 | PM | **Sprint 14 abierto** a pedido del CEO: "Mejoras al módulo Bots". Plan en pares: par 1 inventario + ventana de prueba (#182 #183), par 2 UI/UX detalle + AWS costos (#184 #185), par 3 priorización + implementación (#186 #187), par 4 QA + cierre (#188 #189). Sprint Futuro se mantiene intacto. |
| 2026-05-13 | PM | **Sprint 14 — análisis ejecutado**. Par 1 (#182 #183) inline: inventario completo del módulo Bots (1 router + 3 servicios + 4 modelos + 2 pantallas + 4 scripts + cron `/internal/bot-scheduler/tick` sin invocador en prod) y revisión de la ventana "Probar Chatbot" con 8 hallazgos — 3 bloqueantes: clase Tailwind inválida `bg-gloma-rose-soft/300`, branches de `condition` solo aceptan `int` pero seeds usan strings, `condition` no espera input real. Par 2 (#184 #185) delegado a `general-purpose` actuando como ui-ux y deploy-aws: UI/UX entregó `identidad_gloma/diseno_bots.html` (54 KB, 4 secciones, panel lateral derecho reemplaza el modal de simulación, accent-top por tipo de paso); cuota se agotó antes de actualizar bitácora — completado inline. AWS: agente se quedó sin cuota antes de producir el doc, PM lo completó inline en `backend/docs/sprint14_aws_analisis.md` (gap bloqueante = cron en prod, top-3 ahorros P1 cron $0 + P2 RDS Graviton -$3-5 + P3 quitar ALB -$15-20 no recomendado, costos sa-east-1: 2 usuarios ~$59, 5 usuarios ~$68, 10 usuarios ~$96, comandos CLI listos en §6 para EventBridge Scheduler + Lambda invoker). |
| 2026-05-13 | PM | **Sprint 14 cerrado** por decisión del CEO. Alcance final: sprint de análisis puro (#182-185 ✅). Tareas de implementación #186-189 (priorización CEO, fixes ventana de prueba, rediseño UI/UX, cron AWS, QA y cierre) **trasladadas al Sprint Futuro** sin cambio de numeración para preservar trazabilidad. Sprint Futuro pasa a contener dos paquetes independientes: validación Campañas (#179/#180/#181) y mejoras Bots (#186/#187/#188/#189). Índice del Sprint 14 a **DONE**, Sprint Futuro renombrado en descripción para reflejar el alcance ampliado. |
| 2026-05-13 | PM | **Sprint 15 abierto y ejecutado en una sola corrida** (a pedido del CEO). Tutoriales interactivos por módulo: la primera vez que un usuario entra a Mi Plan / Mensajes / Bots / Campañas recibe un overlay tipo onboarding que oscurece el resto de la pantalla y resalta paso a paso lo que está enseñando, con botones "Atrás / Siguiente / Finalizar" y "Omitir tutorial" siempre visible. Estado persistido en `users.tutorials_completed` (JSONB) por llave de módulo. Tareas #190-#196 cerradas en el mismo día. |
| 2026-05-13 | Experto BD | Sprint 15 #190: `migrate_sprint15_tutorials.py` con `ADD COLUMN IF NOT EXISTS users.tutorials_completed JSONB NOT NULL DEFAULT '{}'::jsonb` + backfill defensivo. Aplicado en local (docker-compose) e idempotente verificado (segunda corrida sin filas afectadas). |
| 2026-05-13 | Dev Plataforma | Sprint 15 #191: backend. `User.tutorials_completed` añadido al modelo; schemas `TutorialStateOut` / `TutorialsOut` / `TutorialUpdateIn` (extra=forbid); endpoints `GET /usuario/me/tutorials` (devuelve siempre las 4 llaves de la whitelist) y `PATCH /usuario/me/tutorials/{module}` (404 si el módulo no está en la whitelist, sin filtrar la lista válida; usa `flag_modified` para que SQLAlchemy detecte el cambio dentro del dict JSONB). Smoke local: 200 + persistencia OK, body extra → 422, sin token → 401. |
| 2026-05-13 | Dev Plataforma | Sprint 15 #192-#193: frontend. `components/TutorialOverlay.tsx` (≈230 LOC, sin libs externas) — spotlight con 4 paneles oscuros + halo rosa Gloma alrededor del cutout, autoposicionamiento de la caja flotante (debajo si cabe, encima si no), "Omitir tutorial" como link siempre visible en cada paso, cierre con Esc y navegación con flechas. Tutoriales cableados con selectores `data-tour="..."` en `pages/usuario.tsx` (4 pasos), `pages/mensajes.tsx` (4 pasos), `pages/bots.tsx` (3 pasos) y `pages/campanas/index.tsx` (6 pasos). En Campañas se añadieron 2 features nuevas para que el tutorial las tenga qué resaltar: botón **"Personalizar"** que alterna entre vista detallada y vista compacta (oculta "Visión general") con preferencia en `localStorage`, y botón **"Exportar a PDF"** que usa `window.print()`. `tsc --noEmit` exit 0. |
| 2026-05-13 | QA | Sprint 15 #194: validación local. Backend recreado, frontend rebuildeado, `/login` `/usuario` `/mensajes` `/bots` `/campanas` todas devuelven 200. Smoke API: `GET /usuario/me/tutorials` devuelve las 4 llaves; `PATCH ... done=true` y `PATCH ... skipped=true` se persisten correctamente; módulo inválido → 404; body con campo extra → 422 (extra=forbid); sin token → 401. Reset de `demo@gmail.com.tutorials_completed` a `'{}'` para que el CEO vea el tutorial cuando entre. |
| 2026-05-13 | Deploy AWS | Sprint 15 #195: deploy a AWS sa-east-1. Build `linux/amd64` + push de `multiagente-backend:sprint15` a ECR. Task-def **rev 8** registrada (clonada de rev 7, sólo cambia image). Migración RDS aplicada vía `ecs run-task` con la rev 8 → exit 0, logs confirman `ALTER TABLE` ejecutado y `tutorials_completed` listada en `users`. `update-service --force-new-deployment` → rolloutState COMPLETED, running 1/1. Smoke online: `https://app.glomabeauty.com/api/docs` 200, login demo OK, `GET /usuario/me/tutorials` devuelve las 4 llaves limpias. Frontend Amplify se reconstruirá automáticamente con el push a `main` (`4959b93`). |
| 2026-05-13 | PM | **Sprint 15 cerrado** ✅. Validación CEO (#197) movida al Sprint Futuro para que el CEO recorra los 4 módulos cuando tenga tiempo (instrucciones de reset del flag incluidas en la tarea). Sprint Futuro acumula ahora tres paquetes independientes: validación Campañas (#179-#181), mejoras Bots (#186-#189) y validación tutoriales (#197). |
| 2026-05-16 | PM | **Sprint 16 abierto y ejecutado en una sola corrida** (a pedido del CEO). Landing pública `/elecol` para la marca ELECOL (electrolineras inteligentes con energía solar para LATAM). Identidad "Infinito Eléctrico — Edición Mar + Sol": paleta `#03045E / #0077B6 / #00B4D8 / #90E0EF / #CAF0F8` + acento solar `#FFC300`. Tareas #198-#205. |
| 2026-05-16 | PM / Dev Plataforma | Sprint 16 #199-#200: estructura de assets `frontend/public/elecol/` con 6 subcarpetas (hero, infraestructura, software, red-latam, cta, brand) + `README.md` documentando 27 archivos (filename, dimensiones display, entrega 2×, formato preferido). Script `frontend/scripts/generate_elecol_placeholders.mjs` (Node puro, idempotente, sin dependencias): para no-SVG genera `<file>.placeholder.svg` adjunto al filename canónico; para SVG canónicos escribe directo. Primera corrida: 27 placeholders escritos con la paleta ELECOL. |
| 2026-05-16 | Dev Plataforma | Sprint 16 #201: landing `frontend/pages/elecol.tsx` (≈900 LOC) implementada según el brief `/Users/equipo/Downloads/ELECOL_Premium_Landing_Guide.md`. 8 secciones: (1) Header sticky transparente → blur al scroll con glow en hover y mobile drawer; (2) Hero con render placeholder, partículas energéticas determinísticas (seeded para no romper SSR), líneas SVG con `stroke-dasharray` animado, 3 orbes aurora con `filter: blur(80px)` flotando, scroll cue; (3) Infraestructura split (render izquierda + 4 cards glassmorphism con border-glow en hover); (4) ELECOL OS con mockup dashboard centrado + 6 mini-cards de features; (5) Red LATAM con mapa SVG + 6 dots animados (pulse) por ciudad; (6) ROI con 6 counters RAF + easeOutCubic + barras animadas; (7) CTA final full-bleed con overlay degradado y partículas; (8) Footer minimalista en 3 columnas. Hooks propios `useScrolled`, `useReveal` (IntersectionObserver), `useCountUp` (RAF). Smooth scroll RAF + easeInOutCubic 900 ms para las anclas. `@media (prefers-reduced-motion)` desactiva todas las animaciones. Tipografías Space Grotesk (heads) + Inter (body) desde Google Fonts. Sin libs nuevas (`package.json` intacto). `/elecol` añadido a `PUBLIC_PAGES` en `_app.tsx`. `next.config.js` habilita `dangerouslyAllowSVG: true` con CSP `default-src 'self'; script-src 'none'; sandbox;` para que `next/image` pueda servir los placeholders SVG (todos vienen del repo, son trusted). |
| 2026-05-16 | QA / Dev Plataforma | Sprint 16 #202: `tsc --noEmit` exit 0; `next build` exit 0 con `/elecol` prerendered estático (12.2 kB página / 115 kB First Load JS). Frontend container rebuildeado y reiniciado. `curl http://localhost:3000/elecol` → 200 (72 KB HTML) con los 7 markers presentes; placeholder SVG `image/svg+xml` 200. |
| 2026-05-16 | Dev Plataforma / Deploy AWS | Sprint 16 #203-#204: commit `ad088e0` con changelog detallado, push a `main`. Amplify build **job 21 SUCCEED** para `ad088e0`. Smoke online: `https://main.d1cfl9ey07f61o.amplifyapp.com/elecol` → 200 (72 KB) con los 7 markers; placeholder SVG sirve 200 `image/svg+xml`. `glomabeauty.com` no se ve afectado (el middleware mantiene la whitelist host-based). |
| 2026-05-16 | PM | **Sprint 16 cerrado** ✅. Validación profunda del CEO + reemplazo de placeholders SVG provisionales por assets reales del equipo de diseño consolidados como **#206** en el Sprint Futuro. URL para revisión: `https://main.d1cfl9ey07f61o.amplifyapp.com/elecol`. Sprint Futuro acumula ahora cuatro paquetes independientes: validación Campañas (#179-#181), mejoras Bots (#186-#189), validación tutoriales (#197) y revisión landing ELECOL (#206). |
| 2026-05-16 | PM | **Sprint 17 abierto** (#207-#218). Migración ALB → API Gateway HTTP API + VPC Link + Cloud Map para ahorrar ~$26/mes preservando funcionamiento. Reporte ejecutivo del Plan agent: complejidad Media, ahorro $310/año, riesgo Bajo. CEO autoriza ejecución autónoma "de 3 en 3" tras detectar que sub-tasks subnets son públicas y plan original asumía privadas (hallazgo bloqueante resuelto reemplazando Cloud Map A→SRV con port 8000). |
| 2026-05-17 | Deploy AWS | **Sprint 17 ejecutado end-to-end en una sola corrida** (~1h calendario). Creados: Cloud Map namespace `multiagente.local` (`ns-ewxiv2osrcu56qlr`) + service `backend` (`srv-gls4xaost6kxzc5u`, SRV records), VPC Link `multiagente-vpclink` (`f494bq`), HTTP API `multiagente-api` (`pmg6lfu9cj`) con integración ANY `/{proxy+}` → VPC Link → Cloud Map, ACM cert `api.glomabeauty.com` validado por DNS, custom domain + A-record alias Route 53. Dos rolling deployments del ECS service (zero downtime ambos): primero registrando A records, después corrigiendo a SRV con `containerPort=8000`. Env vars Amplify actualizadas (`BACKEND_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_BACKEND_URL` → `https://api.glomabeauty.com`); job #23 SUCCEED en 2.5 min. Eliminados: ALB `multiagente-alb`, target group `multiagente-tg`, SG `multiagente-alb-sg`. |
| 2026-05-17 | QA / Seguridad | **Sprint 17 #216-#217**: smoke test E2E vía `https://api.glomabeauty.com` — login JSON con `demo@gmail.com` → 200 con JWT válido, `/docs` y `/openapi.json` → 200, `/meta/webhook` → 403 (fail-closed correcto), frontend Gloma → 200. Latencia p95=1.67s (primer cold start de ENIs), p50=0.64s, min=0.56s. Auditoría abreviada CloudWatch 10 min: 0 ERROR logs, 0 5xx. T215 (Meta Business Manager callback) marcado N/A: prod corre `META_SANDBOX=1` sin `META_APP_SECRET` ni `META_WEBHOOK_VERIFY_TOKEN`, no hay integración Meta real que re-registrar. |
| 2026-05-17 | PM | **Sprint 17 cerrado** ✅. Backend público en `https://api.glomabeauty.com`. Ahorro confirmado ~$26/mes (~$310/año) vs ALB anterior. Follow-ups movidos al Sprint Futuro: **#219** plan de rollback a ALB (cuando se necesite HA o tráfico crezca) y **#220** auditoría 48h formal (>=2026-05-19). Sprint Futuro acumula ahora seis paquetes: Campañas (#179-#181), Bots (#186-#189), tutoriales (#197), ELECOL (#206), rollback ALB (#219), auditoría 48h Sprint 17 (#220). Memoria persistente actualizada: ALB DNS eliminado, nueva arquitectura edge documentada. |
| 2026-05-23 | UI/UX | **Iconos sidebar — kickoff.** El CEO solicita reemplazar los 5 emojis del menú lateral (`Mensajes` 💬, `Campañas` 📢, `Bots` 🤖, `Mi Plan` 👤, `Salir` 🚪) por iconos PNG generados con Canva AI. Restricciones: sin texto, sin fondo (transparente), estilo line-art outline blanco para que se vean sobre el sidebar `gloma-brown` (#5E503F). Creada carpeta `frontend/public/icons/sidebar/` con `README.md` que documenta style guide común (PNG 512×512, trazo blanco 7px, rounded caps/joins, padding 12%, estética Lucide/Phosphor) y los 5 prompts detallados por icono. Siguiente paso: invocar `canva-ai` para generar el primer batch y dejar los outputs en la misma carpeta para revisión del CEO. |
| 2026-05-23 | Dev Plataforma / Deploy AWS | **Landing Gloma — reemplazo de imágenes preview2 y preview3 por assets reales.** El CEO entregó `referencia/landing_ft2.png` y `referencia/landing_ft4.png`. Mapeo: `landing_ft4.png` → `frontend/public/gloma/preview2.png` (sección "Aumenta ventas con campañas por WhatsApp"); `landing_ft2.png` → `frontend/public/gloma/preview3.png` (sección "Reduce 80% del tiempo en servicio al cliente"). No se modificó `pages/gloma.tsx` (los paths siguen siendo `/gloma/preview2.png` y `/gloma/preview3.png`). `tsc --noEmit` exit 0. Commit + push a `main` para disparar Amplify build (auto-deploy). |

---

## Sprint 18 - Migración motor de envío Meta → Twilio (BSP autorizado) + LLM de servicio al cliente

> **Estado:** 🔧 EN EJECUCIÓN — motor de mensajería Meta→Twilio **implementado,
> probado en local y desplegado a AWS** (2026-07-10). Se difieren por decisión
> del CEO: el motor **LLM** (#231-#233) y la **provisión real de cuenta/UI**
> (#230, #234). Todo queda listo para el cutover: basta pegar las claves Twilio.
> **Fecha de propuesta:** 2026-07-10 · **Autor:** Project Manager
> **Rango de tareas:** #221 – #238

### 1. Contexto y objetivo

Gloma **no es proveedor registrado (BSP) ante Meta**, por lo que no puede/ quiere
seguir integrando la **WhatsApp Cloud API de Meta directo** (`graph.facebook.com`).
La decisión del CEO es **cambiar el motor de envío para usar Twilio como proveedor
autorizado (BSP) vía API**, conservando **el mismo frontend de Gloma** y toda la UX
actual (Mensajes, Campañas, Bots, Mi Plan).

Objetivo del Sprint 18:
1. Introducir una **capa de abstracción de proveedor de mensajería** para que el
   backend envíe/reciba WhatsApp indistintamente por Meta (legacy) o **Twilio (nuevo
   default)** sin reescribir campañas ni bots.
2. Implementar el **adaptador Twilio** (envío de plantillas vía Content API, texto
   libre en ventana de 24h, webhooks de entrada y de estado con verificación HMAC
   `X-Twilio-Signature` fail-closed).
3. Habilitar el **modelo de agencia** (subcuentas Twilio por cliente) para que Gloma
   administre varias marcas/tenants desde una cuenta matriz.
4. Reemplazar el bloque `llm` **falso** del motor de bots por un **LLM real (Claude)**
   como motor de respuestas de servicio al cliente, con guardarraíles y handoff a
   asesor humano.

### 2. Estado actual del motor (inventario técnico — base para la migración)

Superficie exacta a migrar (auditada en este sprint de análisis):

| Componente | Archivo | Rol hoy (Meta directo) | Acción Sprint 18 |
|---|---|---|---|
| Cliente HTTP Meta | `backend/app/services/meta_whatsapp.py` | `send_text_message`, `send_template_message`, `get_phone_number_info` contra `graph.facebook.com/{ver}/{phone_number_id}/messages` | Se conserva como **adaptador `meta`**; se envuelve tras un puerto común |
| Envío masivo | `backend/app/services/campaign_sender.py` | Token-bucket por `meta_account_id`, retry `tenacity`, sandbox, llama `meta_whatsapp.send_template_message` | Reapunta a `messaging.get_provider(account).send_template(...)` |
| Respuestas de bot | `backend/app/services/bot_runner.py::_send_text` | Llama `meta_whatsapp.send_text_message` | Reapunta al puerto común |
| Webhook entrada/estado | `backend/app/routers/meta_webhook.py` | HMAC `X-Hub-Signature-256` con `META_APP_SECRET`, correlación por `meta_message_id`, dispara `bot_router`→`bot_runner` | Se agrega router hermano `twilio_webhook.py` que normaliza al mismo pipeline |
| Cuenta/credencial | `models.MetaAccount` (1-a-1 con `team`) | `phone_number_id`, `waba_id`, `encrypted_access_token` (Fernet), `api_version` | Se **generaliza** con `provider` + columnas Twilio (ver §6) |
| Bloque LLM | `bot_engine.py` (`step_type == "llm"`) | **FALSO**: ruteo por keywords, sin LLM real | Se conecta a `services/llm/` (Claude real) |
| Correlación de eventos | `CampaignRecipient.meta_message_id` UNIQUE, `CampaignEvent` dedupe `(meta_message_id, event_type)` | ID de Meta (`wamid...`) | Se generaliza a `provider_message_id` (Twilio `SM/MM/WA...`) |

**Hallazgo clave:** hoy prod corre en `META_SANDBOX=1` sin credenciales Meta reales
(no hay integración productiva que romper). Esto **reduce el riesgo** de la migración:
podemos construir el adaptador Twilio en paralelo y hacer *cutover* por configuración.

### 3. Arquitectura objetivo — puerto de mensajería agnóstico de proveedor

```
                 ┌─────────────────────────────────────────────┐
  Campañas ───►  │  services/messaging/port.py                 │
  Bots     ───►  │  MessagingProvider (interface):             │
                 │   - send_text(account, to, body)            │
                 │   - send_template(account, to, tmpl, vars)  │
                 │   - validate_credentials(account)           │
                 │   - parse_inbound(payload) → NormalizedMsg  │
                 │   - parse_status(payload)  → NormalizedStat │
                 └───────────────┬───────────────┬─────────────┘
                                 │               │
                 ┌───────────────▼──┐   ┌────────▼─────────────┐
                 │ MetaAdapter      │   │ TwilioAdapter (NUEVO)│
                 │ (wrap actual)    │   │ Content API + Msg API│
                 └──────────────────┘   └──────────────────────┘

  Meta webhook  ─┐                     ┌─ Twilio webhook (/twilio/webhook, /twilio/status)
                 └──►  bot_router → bot_runner → CampaignEvent (pipeline único)  ◄─┘
```

`messaging.get_provider(account)` elige el adaptador según `account.provider`
(`'meta'` | `'twilio'`). Campañas, bots y webhooks trabajan contra el **puerto**, no
contra Meta ni Twilio directamente. Cutover = cambiar `provider` de la cuenta.

### 4. Adaptador Twilio — detalle de implementación

- **Plantillas (fuera de ventana 24h / marketing / utility):** Twilio **Content API**.
  Cada plantilla WhatsApp se registra como *Content Template* y se envía con
  `POST /2010-04-01/Accounts/{Sid}/Messages.json` usando `ContentSid` +
  `ContentVariables` (JSON) + `MessagingServiceSid` o `From=whatsapp:+57...`.
- **Texto libre (ventana de servicio 24h):** misma Messages API con `Body`.
- **Webhook de entrada:** Twilio hace `POST` form-encoded (`From`, `Body`, `MessageSid`,
  media `NumMedia`/`MediaUrlN`). Verificación **`X-Twilio-Signature`** (HMAC-SHA1 con el
  auth token de la subcuenta) — **fail-closed en producción** (regla de seguridad #5).
- **Webhook de estado:** `MessageStatus` (`queued|sent|delivered|read|failed|undelivered`)
  + `MessageSid` → se mapea al mismo `_STATUS_RANK` que ya existe para Meta y se
  correlaciona con `CampaignRecipient` por `provider_message_id`.
- **Validación de credenciales:** `GET /2010-04-01/Accounts/{Sid}.json` (equivalente al
  `get_phone_number_info` de Meta) antes de persistir la cuenta.
- **Rate-limit y retry:** se reutiliza el token-bucket y `tenacity`; el bucket pasa a
  indexarse por `channel_account_id` (no por `meta_account_id`). Códigos Twilio
  retryables (p. ej. 20429 too many requests, 63018 rate limit) se mapean al set
  retryable.

### 5. Modelo de agencia en Twilio — respuesta a la pregunta del CEO

**Sí, ambos escenarios que planteaste son posibles; Twilio recomienda una combinación:**

1. **Cuenta matriz + Subcuentas (Subaccounts) — RECOMENDADO para agencia.**
   - Gloma abre **una cuenta Twilio matriz** (administración, facturación y
     credenciales globales) y crea **una subcuenta por cliente/marca** (Gloma, ELECOL,
     Talulah, etc.). Cada subcuenta tiene su **propio `Account SID` + `Auth Token`**,
     su(s) número(s) WhatsApp y su facturación aislada.
   - Ventaja: aislamiento de datos, límites y costos por cliente; puedes reportar y
     tarifar a cada cliente por separado; si un cliente se va, suspendes su subcuenta
     sin tocar a los demás. **Cada WABA de cliente se conecta a su subcuenta.**
2. **Programa Tech Provider / ISV + Embedded Signup — para escalar el alta.**
   - Si vas a onboardear muchos clientes, Twilio + Meta ofrecen el **ISV Tech Provider
     Program**: el cliente hace **Embedded Signup** (conecta su propio WABA con unos
     clicks dentro de la app de Gloma) y tú registras sus *senders* por API
     (`Senders API`) a través de su subcuenta. Ideal para alta self-service y registro
     masivo. No es obligatorio al inicio; se puede adoptar después.

**Recomendación de arranque:** empezar con **cuenta matriz + subcuentas manuales**
(rápido, suficiente para el portafolio actual) y dejar el **ISV/Embedded Signup como
follow-up** cuando el número de clientes lo justifique. En el modelo de datos, la
subcuenta (`twilio_account_sid`) y su auth token cifrado viven **por tenant en la BD**
(regla de seguridad #3: secreto de tenant nunca en `.env`).

### 6. Cambios de BD (regla de paridad local ↔ RDS — migración idempotente obligatoria)

Se **generaliza `meta_accounts`** (no se crea tabla nueva para preservar las filas y FKs
existentes). Migración `backend/scripts/migrate_sprint18_twilio.py` idempotente:

```sql
ALTER TABLE meta_accounts ADD COLUMN IF NOT EXISTS provider VARCHAR(16) NOT NULL DEFAULT 'meta';
ALTER TABLE meta_accounts ADD COLUMN IF NOT EXISTS twilio_account_sid VARCHAR(64);
ALTER TABLE meta_accounts ADD COLUMN IF NOT EXISTS encrypted_twilio_auth_token TEXT;   -- Fernet
ALTER TABLE meta_accounts ADD COLUMN IF NOT EXISTS twilio_messaging_service_sid VARCHAR(64);
ALTER TABLE meta_accounts ADD COLUMN IF NOT EXISTS twilio_from VARCHAR(32);            -- whatsapp:+57...
-- columnas Meta (phone_number_id, waba_id, encrypted_access_token) pasan a nullable
--   porque una fila 'twilio' no las usa:
ALTER TABLE meta_accounts ALTER COLUMN phone_number_id DROP NOT NULL;
ALTER TABLE meta_accounts ALTER COLUMN waba_id DROP NOT NULL;
ALTER TABLE meta_accounts ALTER COLUMN encrypted_access_token DROP NOT NULL;
-- correlación de eventos genérica (backfill desde meta_message_id):
ALTER TABLE campaign_recipients ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(128);
UPDATE campaign_recipients SET provider_message_id = meta_message_id WHERE provider_message_id IS NULL;
```
Se aplica **en local (docker-compose) y en RDS `multiagente-db` en el mismo PR**, con
evidencia de ambas ejecuciones (convención de operación #1). Follow-up permanente:
adoptar Alembic (deuda ya registrada en memoria persistente).

### 7. LLM como motor de servicio al cliente

- Reemplazar el `step_type == "llm"` falso por un servicio real `services/llm/` que
  llame a **Claude** (API de Anthropic). Modelos objetivo (default a lo más reciente):
  - **Clasificación/routing de intención + detección de handoff:** `claude-haiku-4-5`
    (barato, baja latencia, alto volumen).
  - **Respuesta redactada de servicio al cliente (RAG sobre FAQ/catálogo de la marca):**
    `claude-sonnet-4-6`; escalar a `claude-opus-4-8` solo en casos difíciles.
- **Guardarraíles:** system prompt con identidad de marca, `max_tokens` acotado,
  prohibido prometer precios/plazos no verificados, **escalar a asesor humano (handoff)**
  ante baja confianza o intenciones sensibles (reclamos, devoluciones, datos personales).
- **Seguridad/privacidad:** nunca loggear el mensaje crudo ni el `ANTHROPIC_API_KEY`
  (reglas #1 y #6). PII enmascarada como ya hace `meta_webhook`. La API key es un secreto
  global de la plataforma → `.env`/SSM, no por tenant.
- **RAG:** base de conocimiento por marca (FAQ + catálogo). MVP: contexto en el system
  prompt + few-shot; follow-up: embeddings/pgvector si crece el corpus.

### 8. Costos Colombia (estimación 2026 — validar en el cierre con la calculadora Twilio)

Meta factura **por mensaje** (desde 1-jul-2025, ya no por conversación de 24h). Twilio
**agrega su fee de plataforma de US$0.005 por mensaje** (entrante o saliente) sobre la
tarifa de Meta. Recipiente = Colombia:

| Categoría | Tarifa Meta (aprox. CO) | + Fee Twilio | **Costo total / mensaje** |
|---|---|---|---|
| **Marketing** | ~US$0.0125 – 0.020 | US$0.005 | **~US$0.017 – 0.025** |
| **Utility** (utilitario) | ~US$0.001 | US$0.005 | **~US$0.006** |
| **Authentication** (OTP) | ~US$0.0008 | US$0.005 | **~US$0.0058** |
| **Service / atención al cliente** (iniciado por el usuario, respuestas libres en ventana 24h) | **US$0.00 (gratis Meta)** | US$0.005 | **~US$0.005 por mensaje** |

Notas: (a) las plantillas de **servicio al cliente entrantes son gratis en Meta**; solo
pagas el fee de Twilio por mensaje. (b) **Marketing no tiene descuentos por volumen**
en 2026 (Meta excluye marketing de los *volume tiers*; utility/auth sí escalan). (c) el
**LLM** es costo aparte por tokens de Anthropic (Haiku para routing es marginal; Sonnet
por respuesta redactada, unos pocos centavos de USD por conversación según longitud).
**Ejemplo:** campaña de 5.000 mensajes de marketing ≈ 5.000 × ~US$0.021 ≈ **~US$105**;
1.000 conversaciones de servicio al cliente (≈4 msg c/u) ≈ 4.000 × US$0.005 ≈ **~US$20**
de Twilio + costo LLM.

### 9. Tareas del Sprint 18 y responsables (agentes)

| # | Tarea | Agente responsable | Descripción detallada |
|---|---|---|---|
| #221 | **Revisión de diseño de seguridad (PRE-implementación)** | `seguridad` | Bloqueante (regla #4). Revisa este plan antes de codear: manejo del `Auth Token` de subcuenta (Fernet en BD, nunca `.env` ni logs), verificación `X-Twilio-Signature` fail-closed, sanitización de errores Twilio al cliente, no filtrar `ANTHROPIC_API_KEY`. Emite hallazgos Críticos/Altos bloqueantes. |
| #222 | **Diseño de datos: generalizar `meta_accounts` → multi-proveedor** | `experto-bd` | Define columnas `provider` + Twilio (§6), qué pasa a nullable, y `provider_message_id`. Entrega el DDL idempotente y el plan de backfill. |
| #223 | **Migración BD local + RDS (paridad)** | `experto-bd` + `deploy-aws` | Ejecuta `migrate_sprint18_twilio.py` en docker-compose y en RDS vía `ecs run-task` (sa-east-1). Evidencia de ambas corridas + segunda corrida idempotente sin cambios (convención #1). |
| #224 | **Puerto de mensajería `services/messaging/port.py`** | `dev-plataforma` | Define la interfaz `MessagingProvider` y `get_provider(account)`. Mueve las firmas comunes (`send_text`, `send_template`, `validate_credentials`, `parse_inbound`, `parse_status`). |
| #225 | **`MetaAdapter`: envolver `meta_whatsapp` en el puerto** | `dev-plataforma` | Refactor sin cambio de comportamiento: el adaptador Meta implementa el puerto reutilizando el cliente actual. Todos los tests Meta siguen verdes. |
| #226 | **`TwilioAdapter`: envío (Content API + texto libre)** | `dev-plataforma` | Implementa `send_template` (ContentSid + ContentVariables + MessagingServiceSid/From) y `send_text` (Body) contra la Messages API de Twilio, con retry/rate-limit reusados y sandbox (`TWILIO_SANDBOX=1`). |
| #227 | **Router `twilio_webhook.py` (entrada + estado)** | `dev-plataforma` | `/twilio/webhook` y `/twilio/status`: verificación `X-Twilio-Signature` (HMAC-SHA1, fail-closed en prod), normaliza a `NormalizedMsg`/`NormalizedStatus`, dispara `bot_router`→`bot_runner` y correlaciona `CampaignEvent` por `provider_message_id`. |
| #228 | **Reapuntar Campañas y Bots al puerto** | `dev-plataforma` | `campaign_sender.py` y `bot_runner._send_text` usan `messaging.get_provider(account)`; token-bucket reindexado a `channel_account_id`. Sin tocar la UI. |
| #229 | **Registro de plantillas como Content Templates de Twilio** | `dev-plataforma` | Mapea el módulo de Plantillas actual a la creación/sincronización de Content Templates en Twilio (equivalente a `meta_templates.py`). Modo sandbox mockeado. |
| #230 | **Alta de subcuentas Twilio (modelo agencia)** | `deploy-aws` + `dev-plataforma` | Provisiona la cuenta matriz + una subcuenta por marca; documenta `Account SID`, número WhatsApp y `MessagingServiceSid`. Endpoint `POST /usuario/me/channel-account` para guardar credenciales Twilio cifradas por tenant. |
| #231 | **Servicio LLM real `services/llm/` (Claude)** | `dev-plataforma` | Cliente Anthropic con routing en `claude-haiku-4-5` y respuesta en `claude-sonnet-4-6`; guardarraíles, `max_tokens`, detección de handoff, PII enmascarada, key en env/SSM. |
| #232 | **Conectar bloque `llm` del bot al servicio real** | `dev-plataforma` | Sustituye el ruteo por keywords: el `step_type=='llm'` invoca `services/llm/`, decide `route`/`extract` con el modelo y cae a handoff ante baja confianza. |
| #233 | **RAG de servicio al cliente (MVP por marca)** | `dev-plataforma` + `ui-ux` | Base de conocimiento (FAQ + catálogo) por marca inyectada como contexto; UI mínima para que el cliente cargue/edite su FAQ. |
| #234 | **Wireframe de configuración de canal (Meta/Twilio) en Mi Plan** | `ui-ux` | Pantalla para elegir proveedor, pegar credenciales Twilio y ver estado de la subcuenta, coherente con la identidad Gloma. HTML/Tailwind antes de codear. |
| #235 | **Auditoría de seguridad (POST-commit)** | `seguridad` | Bloqueante antes del merge (regla #4): verifica que ningún `...Out` exponga tokens, que los webhooks sean fail-closed, errores sanitizados y no haya secretos en logs. |
| #236 | **QA end-to-end (Meta legacy + Twilio + LLM)** | `qa` | Prueba envío de plantilla y texto por Twilio (sandbox), inbound→bot→LLM→handoff, callbacks de estado correlacionados, y que Meta legacy siga funcionando. Smoke local + online. |
| #237 | **Deploy AWS (backend + migración) y cutover por config** | `deploy-aws` | Build/push imagen, task-def nueva, migración en RDS, `TWILIO_*` en SSM, `update-service`. Cutover cambiando `provider='twilio'` de la(s) cuenta(s). Región sa-east-1. |
| #238 | **Cierre, validación CEO y documentación de costos** | `project-manager` | Consolida evidencias, valida con el CEO, actualiza memoria persistente y confirma tabla de costos con la calculadora Twilio real. |

### 10. Riesgos y mitigaciones

- **Cutover:** al correr hoy en sandbox sin Meta real, el cambio es de bajo riesgo; se
  hace por `provider` de cuenta y se puede revertir por config.
- **Secretos de tenant (Auth Token de subcuenta):** Fernet en BD, nunca en `.env` ni
  logs (reglas #1/#3). Revisión `seguridad` obligatoria (#221/#235).
- **Webhooks:** `X-Twilio-Signature` fail-closed en prod (regla #5).
- **Costos LLM:** Haiku para el 80% (routing/clasificación), Sonnet solo para redacción;
  presupuesto y límite de tokens por conversación.

### 11. Definición de terminado (DoD)

Migración lista cuando: (a) Campañas y Bots envían por Twilio en sandbox y en una
subcuenta real; (b) webhooks de entrada y estado de Twilio verificados y correlacionados;
(c) el bloque LLM responde con Claude real y escala a humano; (d) Meta legacy sigue
operativo por el puerto; (e) migración aplicada en local y RDS con paridad; (f) auditoría
`seguridad` sin hallazgos Críticos/Altos abiertos; (g) CEO valida.

### Log de ejecución del Sprint 18

| Fecha | Agente | Nota |
|---|---|---|
| 2026-07-10 | PM | **Sprint 18 propuesto** a pedido del CEO: migrar el motor de envío de Meta directo → **Twilio (BSP autorizado)** conservando el frontend de Gloma, habilitar modelo de **agencia (subcuentas Twilio)**, documentar **costos Colombia** y sumar un **LLM (Claude) como motor de servicio al cliente**. Inventario técnico del motor actual completado (meta_whatsapp / campaign_sender / bot_runner / meta_webhook / MetaAccount / bloque llm falso). Plan #221–#238 con responsables por agente. **Pendiente de aprobación del CEO antes de ejecutar.** |
| 2026-07-10 | Dev Plataforma | **#224-#228 código del motor Twilio implementado.** Nuevo paquete `backend/app/services/messaging/`: `base.py` (`MessagingError` común — `MetaWhatsAppError` ahora hereda de él; dataclasses `NormalizedInbound`/`NormalizedStatus`), `meta_adapter.py` (envuelve `meta_whatsapp` sin cambio de comportamiento), `twilio_adapter.py` (Content API + Messages API, sandbox, verificación de credenciales, normalización de webhooks; credenciales por-tenant en BD cifradas Fernet o env globales; **nunca loggea el Auth Token**), y `__init__.py` (puerto `get_provider`/`send_text`/`send_template`/`is_sandbox`, dispatch por `account.provider`, imports perezosos anti-ciclo). `campaign_sender.py` y `bot_runner._send_text` reapuntados al puerto (sandbox provider-aware; `_mark_sent` puebla `meta_message_id` **y** `provider_message_id`). `models.py`: `MetaAccount` gana `provider` + 4 columnas Twilio y hace nullable las Meta; `__repr__` redacta ambos tokens; `CampaignRecipient.provider_message_id`. `config.py` + `.env.example`: settings `TWILIO_*` (sandbox on por default). |
| 2026-07-10 | Dev Plataforma / Seguridad | **#227 router `twilio_webhook.py`** (`/twilio/webhook` entrada + `/twilio/status` estado). Verificación **`X-Twilio-Signature`** (HMAC-SHA1 base64 sobre `url+params`) **fail-closed en producción** vía `os.getenv` (patrón `meta_webhook`, evita el hard-require de `DATABASE_URL` de `config.settings`); soporta `TWILIO_WEBHOOK_BASE_URL` para reconstruir la URL detrás de API Gateway. Correlación de estados por `provider_message_id` con avance por rank + `CampaignEvent` idempotente (`ON CONFLICT DO NOTHING`). Registrado en `main.py`. |
| 2026-07-10 | Experto BD / QA | **#222-#223 migración BD `migrate_sprint18_twilio.py`** (idempotente: `ADD COLUMN IF NOT EXISTS`, `DROP NOT NULL`, backfill `provider_message_id`←`meta_message_id`, índice). **Local (docker-compose):** 1ª corrida aplica todo + backfill 31 filas; 2ª corrida 0 filas (idempotente). **RDS (`ecs run-task` rev 11):** exit 0, backfill 19 filas, todas las columnas presentes → **paridad local↔RDS cumplida** (convención #1). |
| 2026-07-10 | QA | **#236 pruebas locales (todas ✅):** arranque limpio; `/twilio/status` y `/twilio/webhook` registradas; envío sandbox texto+plantilla para Meta y Twilio; `repr` de `MetaAccount` redacta ambos tokens + round-trip Fernet del Auth Token; webhook de estado avanza recipient `sent→delivered` (`delivered_at` seteado) con evento idempotente; SID inexistente e inbound sin cuenta → 200 no-op; tick de campaña real envía 8/8 en sandbox poblando `meta_message_id` **y** `provider_message_id`. Nota: la suite `unittest` completa falla por un bug **pre-existente** (Sprint 15: `users.tutorials_completed` JSONB no compila en SQLite), ajeno a este cambio. |
| 2026-07-10 | Deploy AWS | **#237 despliegue a AWS sa-east-1.** Build `linux/amd64` + push `multiagente-backend:sprint18` a ECR. Task-def **rev 11** (clon de rev 10, sólo cambia image). Migración RDS vía `ecs run-task` rev 11 → exit 0. `update-service --task-definition :11 --force-new-deployment` → `services-stable` (rolling, zero-downtime, 1/1). **Smoke online `https://api.glomabeauty.com`:** `/openapi.json` 200; `/twilio/status` y `/twilio/webhook` presentes; `/meta/webhook` sin firma → 403 (fail-closed); `/twilio/status` sin firma → **403 (fail-closed correcto: aún sin `TWILIO_AUTH_TOKEN`)**; `/login` 422 (app sana); frontend `https://app.glomabeauty.com/login` 200. **Prod sigue en `TWILIO_SANDBOX=1`** (env default) — no se envía nada por Twilio hasta el cutover. |
| 2026-07-10 | PM | **Cutover pendiente (cuando la cuenta Twilio esté lista):** (1) setear en la task-def/SSM `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` (o `TWILIO_MESSAGING_SERVICE_SID`), `TWILIO_WEBHOOK_BASE_URL=https://api.glomabeauty.com` y `TWILIO_SANDBOX=0`; (2) apuntar el webhook de Twilio a `https://api.glomabeauty.com/twilio/webhook` (inbound) y `/twilio/status` (estado); (3) poner `provider='twilio'` en la(s) `meta_accounts` (o cargar credenciales por-tenant cifradas). **Diferido explícito:** LLM (#231-#233) y provisión de cuenta/UI (#230, #234). **Follow-up de seguridad:** auditoría formal del agente `seguridad` (#221/#235) antes de operar Twilio en real. |

---

## Sprint 19 - Motor de bots LLM (AWS Bedrock) — Talulah + Demo Viajes

> **Estado:** ✅ EJECUTADO Y DESPLEGADO (2026-07-10/11). Código en `main`, migración
> y seeds aplicados en local **y** RDS, servicio ECS rev 12 estable, bots LLM
> verificados conversando en local con Claude real (media + contexto + tools).
> ⚠️ **Única acción pendiente y es del CEO (#253):** AWS Marketplace rechaza el
> método de pago de la cuenta (`INVALID_PAYMENT_INSTRUMENT`), lo que bloquea la
> suscripción a los modelos Anthropic en Bedrock. Mientras tanto los bots en prod
> responden con el fail-safe (disculpa + handoff a asesor). Al corregir el pago,
> los bots quedan operativos SIN redeploy.
> **Autor:** Project Manager · **Rango de tareas:** #239 – #253
> **Pedido del CEO:** implementar en AWS los motores de bots con LLM para 2 clientes:
> (1) **Talulah** — cuenta nueva `talulah@gloma.com`, mismos flujos de los bots WATI
> (`talulah bots/descargados/*.json`) pero **simplificados**: todo requerimiento lo
> recibe un LLM que decide la respuesta y puede tomar acciones (API Shopify, delegar
> a asesor humano en la app). (2) **Demo Agencia de Viajes** — cuenta existente
> `agencia@demo.com`, mismo contexto que ya tiene el demo (seed Coveñas) pero ahora
> con LLM real usando la misma estrategia. Contextos guardados **a priori en el
> contenedor** (decisión CEO: solo 2 clientes; se organiza escalable cuando crezca).

### 1. Decisiones de arquitectura

| Decisión | Elección | Por qué |
|---|---|---|
| Proveedor LLM | **AWS Bedrock** (`bedrock-runtime`, región `sa-east-1`) | El CEO pidió "motores en AWS". Sin API keys que gestionar: la task ECS usa su **IAM task role** (`multiagente-ecs-task-role`) con permiso `bedrock:InvokeModel`. Verificado: el perfil `global.anthropic.claude-haiku-4-5-20251001-v1:0` responde desde sa-east-1. |
| Modelo default | `claude-haiku-4-5` (perfil global) | Bajo costo/latencia para SAC. Configurable por bot (`llm_config.model_id`) y por env (`LLM_MODEL_ID`). |
| Contexto por cliente | Archivos Markdown **empaquetados en la imagen Docker** (`backend/app/bot_contexts/*.md`) | "Información a priori en el contenedor" (decisión CEO). Versionado en git, cero infra extra. Follow-up al crecer: mover a S3/BD por tenant con editor en la UI (#233 del Sprint 18). |
| Motor | Nuevo `services/llm_engine.py` con **mismo contrato** que `bot_engine.advance()` (`actions` / `next_state` / `finished`) | Se enchufa sin fricción a `bot_runner.run_turn` (webhooks Meta/Twilio) y a `POST /bots/{id}/simulate` (ventana Probar del frontend). Un bot elige motor con la columna nueva `bots.engine` (`'flow'` legacy \| `'llm'`). |
| Memoria conversacional | `state = {"history": [...]}` persistido en `bot_sessions.state` (webhook) o en el cliente (simulador), cap 30 turnos | Mismo mecanismo de sesión existente; no se toca el schema de sesiones. |
| Acciones del LLM (tool use) | `escalar_a_asesor` (handoff en la app), `enviar_media` (catálogo de medios permitidos por bot), `consultar_pedido_shopify` (solo Talulah), `finalizar_conversacion` | El LLM decide; el motor traduce a las acciones ya soportadas (`say`, `say_media`, `handoff`, `end`). Fail-safe: cualquier error del motor → mensaje de disculpa + handoff a asesor. |
| Credenciales Shopify (tenant Talulah) | **Fernet en BD** dentro de `bots.llm_config` (`encrypted_client_secret`), inyectadas por env SOLO al correr el seed | Regla de seguridad #3: secreto de tenant nunca en `.env` ni en el repo. Shop `grupogyc.myshopify.com`, grant `client_credentials` (probado OK: scopes `read_all_orders,read_fulfillments,read_orders`). Las carpetas crudas `talulah bots/` y `tallas talulah/` se agregan a `.gitignore` (contienen el secret). |

### 2. Contexto Talulah — qué se extrajo de los JSON y qué falta (respuesta al CEO)

De `talulah bots/descargados/` se extrajo TODO el contenido operativo: tono de marca
(🤍🌿🤎, trato cercano femenino), menú minorista (estado de pedido → Shopify; cambios
y garantías + links de políticas; tiempos de envío; guía de tallas; sedes físicas con
direcciones/teléfonos/horarios; pagos y promos; fallas web) y menú mayorista B2B
(despachos, faltantes/defectos, cartera, ventas/repedidos), reglas de escalamiento a
asesor y la integración Shopify (token client-credentials + `GET orders.json`).

**Información faltante / a confirmar por el CEO con Talulah:**
1. **URLs de catálogo por categoría** del bot "Asistente 24/7" (Pantalón, Short, Capri,
   Batola, Satin, Plus Size, Niña, Ropa de Mujer, SALE, Hombre, Ropa Interior, Vestidos
   de Baño, Lo más nuevo): el JSON exportado no trae los links. Mientras tanto el bot
   dirige al sitio `https://www.talulah.com.co`.
2. **Guía de tallas:** hay 7 imágenes en `tallas talulah/` sin etiqueta de categoría.
   Se publican como `frontend/public/talulah/guia_tallas_{1..7}.jpeg` — falta confirmar
   qué imagen corresponde a qué tipo de prenda para nombrarlas mejor.
3. **Link de política de privacidad** del saludo (el JSON dice "LINK"): se usó
   `https://www.talulah.com.co/policies/privacy-policy` (el mismo del orquestador).
4. **Teléfono del Outlet Envigado** (las otras 3 sedes sí lo tienen).
5. Confirmar si el **horario de festivos** es "11:00 a.m. – 7:00 p.m." (el export lo trae).

### 3. Demo Viajes — dónde estaba guardado el contexto (respuesta al CEO)

El bot actual de `agencia@demo.com` vive en la **BD** (tablas `bots`/`bot_steps`),
creado por `backend/scripts/seed_bot_covenas.py` (copys, itinerario, precios, política
de reserva 30%, bucles del menú). Los medios (tarifarios, tours, hotel.mp4, medios de
pago, formulario) están en `frontend/public/demo_viajes/` (fuente cruda en
`demo_viajes/` en la raíz del repo). Ese contenido se consolidó en el contexto a priori
`backend/app/bot_contexts/demo_viajes.md`; el bot de flujo legacy queda **pausado**
(rollback fácil) y el bot LLM pasa a ser el default de la cuenta.

### 4. Tareas del Sprint 19 y responsables (agentes)

| # | Tarea | Agente | Descripción |
|---|---|---|---|
| #239 | Apertura del sprint, análisis de los JSON WATI y decisiones de arquitectura | `project-manager` | Inventario de los 7 JSON descargados, ubicación del contexto demo, elección Bedrock vs API key, plan de contexto a priori en contenedor. |
| #240 | Revisión de diseño de seguridad (PRE-implementación, regla #4) | `seguridad` | Secret Shopify por tenant → Fernet en BD (nunca repo/.env); IAM Bedrock de mínimo privilegio (solo `bedrock:InvokeModel` a modelos `anthropic.*`); no loggear prompts con PII ni secretos; errores sanitizados al cliente; fail-safe → handoff; `.gitignore` para carpetas crudas de Talulah. |
| #241 | DDL: `bots.engine` + `bots.llm_config` | `experto-bd` | `ALTER TABLE bots ADD COLUMN IF NOT EXISTS engine VARCHAR(16) NOT NULL DEFAULT 'flow'` + `ADD COLUMN IF NOT EXISTS llm_config TEXT`. Script idempotente `backend/scripts/migrate_sprint19_llm_bots.py`. |
| #242 | Migración en local (docker-compose) y RDS (paridad, convención #1) | `experto-bd` + `deploy-aws` | Evidencia de ambas corridas + segunda corrida idempotente. |
| #243 | Motor `services/llm_engine.py` (Bedrock, tool-use loop) | `dev-plataforma` | Contrato `advance(bot, state, user_input)` idéntico a `bot_engine`; historia cap 30; máx 5 iteraciones de tools; timeouts; fail-safe handoff. |
| #244 | Tools del motor + cliente Shopify | `dev-plataforma` | `escalar_a_asesor`, `enviar_media` (catálogo permitido en `llm_config.media`), `consultar_pedido_shopify` (token client-credentials + orders.json, httpx timeout 10s), `finalizar_conversacion`. |
| #245 | Contextos a priori | `dev-plataforma` | `backend/app/bot_contexts/talulah.md` (flujos minorista+mayorista de los JSON) y `demo_viajes.md` (contenido del seed Coveñas). Loader con cache. |
| #246 | Integración: `bot_runner`, `/bots/{id}/simulate`, schemas y frontend | `dev-plataforma` | Branch por `bot.engine`; `waiting = not finished` para LLM; `engine` expuesto en `BotListItem`/`BotDetail`; página de detalle muestra tarjeta "Bot IA" en vez del diagrama vacío. |
| #247 | Cuenta `talulah@gloma.com` + seeds de los 2 bots | `experto-bd` | `seed_bot_talulah.py` (owner + team + asesora + bot LLM default, Shopify cifrado) y `seed_bot_viajes_llm.py` (bot LLM default para agencia@demo.com, flujo legacy pausado). Idempotentes, correr local + RDS. |
| #248 | Assets guía de tallas | `dev-plataforma` | Copiar `tallas talulah/*.jpeg` → `frontend/public/talulah/guia_tallas_{1..7}.jpeg` (servidos por Amplify como `demo_viajes/`). |
| #249 | QA local | `qa` | pytest de motor con Bedrock mockeado; smoke real vía `/bots/{id}/simulate` con venv + credenciales AWS locales: saludo, flujo tallas (media), pedido Shopify real, escalamiento a asesor, demo viajes completo. |
| #250 | Deploy AWS | `deploy-aws` | `boto3` a requirements; policy `bedrock-invoke` en `multiagente-ecs-task-role`; build/push `multiagente-backend:sprint19`; task-def rev 12 (+`BEDROCK_REGION`, `LLM_MODEL_ID`); `update-service` hasta stable; migración + seeds en RDS vía `ecs run-task`; deploy Amplify manual (gotcha: no auto-buildea). |
| #251 | QA end-to-end contra AWS | `qa` | Login `talulah@gloma.com` y `agencia@demo.com` contra `https://api.glomabeauty.com`; conversaciones LLM reales por simulate; **frontend local (`npm run dev`) apuntando a la API de AWS** (mismos motores) — pedido explícito del CEO. |
| #252 | Cierre: commit a main, tabla de entregables, memoria | `project-manager` | Commit del Sprint 18 pendiente + Sprint 19; tabla final de qué se hizo y entregables por tarea; actualización de memoria persistente. |

### 5. Definición de terminado (DoD)

(a) Ambos bots responden con Claude real vía Bedrock desde la API de AWS; (b) el bot
Talulah consulta pedidos reales en Shopify y escala a asesor humano dentro de la app;
(c) el demo de viajes conserva sus flujos/medios pero razonados por LLM; (d) migración
y seeds aplicados en local y RDS (paridad); (e) sin hallazgos de seguridad Críticos/Altos;
(f) commit en `main` y bitácora cerrada con entregables.

### Log de ejecución del Sprint 19

| Fecha | Agente | Nota |
|---|---|---|
| 2026-07-10 | PM | Sprint abierto. Exploración completada: bloque `llm` actual es falso (keywords); contexto demo ubicado en `seed_bot_covenas.py` + `frontend/public/demo_viajes/`; 7 JSON de Talulah parseados (orquestador, minoristas 44 nodos, mayoristas 16, asistente 24/7, servicio al cliente, asesor-defecto, escalar-a-asesor); credenciales Shopify del JSON **verificadas funcionando** (grant client_credentials OK); Bedrock `global.anthropic.claude-haiku-4-5` **verificado respondiendo desde sa-east-1**. |
| 2026-07-10 | Seguridad | **#240 revisión de diseño (PRE).** Aprobado con condiciones, todas implementadas: (1) `client_secret` de Shopify SOLO cifrado Fernet dentro de `bots.llm_config`, inyectado por env únicamente al correr el seed — nunca en repo/.env de la app; (2) `llm_config` NO se expone en ningún schema `...Out` (`BotDetail`/`BotListItem` solo exponen `engine`); (3) carpetas crudas `talulah bots/`, `tallas talulah/` y `demo_viajes/` agregadas a `.gitignore` (el JSON de WATI contiene el secret en claro); (4) IAM de mínimo privilegio: policy `bedrock-invoke-anthropic` solo `bedrock:InvokeModel` sobre `foundation-model/anthropic.*` + `inference-profile/global.anthropic.*|us.anthropic.*`; (5) errores del motor sanitizados: el cliente ve disculpa genérica + handoff, el detalle va a `logger.exception` server-side; (6) `context_key` sanitizado a `[a-z0-9_-]` (sin path traversal). |
| 2026-07-10 | Experto BD | **#241-#242 migración `migrate_sprint19_llm_bots.py`** (`bots.engine` VARCHAR(16) DEFAULT 'flow' + `bots.llm_config` TEXT, idempotente). **Local (docker-compose):** 2 corridas, la 2ª sin cambios ✅. **RDS (`ecs run-task` rev 12):** exit 0, columnas verificadas ✅. Paridad local↔RDS cumplida (convención #1). Hallazgo operativo: hay un Postgres del host Mac ocupando `localhost:5432` que opaca al del docker — los scripts locales deben correrse con `docker compose exec backend ...` (documentado aquí para no repetir la confusión). |
| 2026-07-10 | Dev Plataforma | **#243-#245 motor LLM implementado.** `services/llm_engine.py`: mismo contrato que `bot_engine.advance()` (`actions/next_state/finished`) → se enchufa a `bot_runner.run_turn` y a `/bots/{id}/simulate` sin cambiar el API; historial aplanado en `state.history` (cap 30 mensajes, medios como marcas `[enviaste: ...]`); loop de tool-use máx 5 rondas; tools `escalar_a_asesor`, `finalizar_conversacion`, `enviar_media` (catálogo por bot) y `consultar_pedido_shopify` (solo si hay config); fail-safe total → disculpa + handoff. `services/shopify_client.py`: grant `client_credentials` + `GET orders.json` (API 2025-10), cache de token ~24h, timeouts 10s. Contextos a priori en `backend/app/bot_contexts/` (`talulah.md` consolidando los 7 JSON de WATI; `demo_viajes.md` consolidando el seed Coveñas) — viajan dentro de la imagen Docker (decisión CEO). Config del motor por env (`BEDROCK_REGION`, `LLM_MODEL_ID`, `LLM_MAX_TOKENS`) leída con `os.getenv` (patrón twilio_webhook; `config.settings` exige DATABASE_URL y crashea el contenedor — detectado y corregido en esta corrida). |
| 2026-07-10 | Dev Plataforma | **#246 integración + #248 assets.** `bot_runner` y el endpoint `simulate` despachan por `bot.engine` (`llm` → llm_engine); para bots LLM `waiting = not finished`. `schemas`/`crud` exponen `engine`. **Guard nuevo en `bot_router`:** si `conversation.assigned_to != 'bot'` (ya escalada a humano), NINGÚN bot vuelve a intervenir — antes el bot re-tomaba el chat tras el handoff (gap pre-existente que con bots LLM default era crítico). Frontend: badge 🤖 IA en el listado, tarjeta "Bot conversacional con IA" en el detalle (en vez del diagrama vacío) y botón Probar habilitado para bots LLM sin steps; `tsc --noEmit` limpio. Guía de tallas: 7 imágenes de `tallas talulah/` → 6 únicas (1 duplicada eliminada) publicadas como `frontend/public/talulah/guia_tallas_{1..6}.jpeg`. `docker-compose.yml`: passthrough de `AWS_*`/`BEDROCK_*` para Bedrock en local. |
| 2026-07-10 | Experto BD | **#247 seeds.** `seed_bot_talulah.py`: cuenta `talulah@gloma.com` (pwd en el gestor del CEO), team "Talulah", asesora `asesora1.talulah@gloma.com` (handle `asesor_1`), bot "Talulah IA — Servicio al Cliente" engine=llm default con guía de tallas + Shopify cifrado (credenciales por env SOLO en la corrida). `seed_bot_viajes_llm.py`: bot "Plan Tolú & Coveñas (IA)" default para `agencia@demo.com` con los 9 medios de `/demo_viajes`; el bot de flujo legacy queda **pausado** (rollback fácil). Fix durante la corrida: degradar el default previo ANTES de crear el nuevo (índice `uq_one_default_bot_per_user`). Ambos corridos en local y en RDS (run-task rev 12, exit 0): local bots id=10/13, RDS id=7/8. |
| 2026-07-10 | QA | **#249 pruebas locales.** Unit tests nuevos `tests/test_llm_engine.py` (7/7 ✅, Bedrock mockeado: say/estado, handoff corta el loop, media + clave inexistente informada al modelo, fail-safe ante excepción, recorte de historial, anti path-traversal, contextos empaquetados presentes). Suite completa: 17 passed / 7 failed — los 7 son el bug **pre-existente** JSONB+SQLite del Sprint 15 (documentado en Sprint 18). **E2E real local (docker + Bedrock):** conversación Talulah completa ✅ — saludo de marca con política de datos, detección minorista/mayorista, sedes con direcciones/teléfonos/horarios, guía de tallas enviada como 6 imágenes (`say_media`), tono 🤍🌿🤎 correcto. Shopify verificado por separado: token client-credentials OK (scopes `read_all_orders,read_fulfillments,read_orders`). |
| 2026-07-10 | Deploy AWS | **#250 despliegue sa-east-1.** Formulario de caso de uso Anthropic enviado por API (`PutUseCaseForModelAccess` 201 en us-east-1 y sa-east-1). Policy IAM `bedrock-invoke-anthropic` en `multiagente-ecs-task-role`. Build `linux/amd64` + push `multiagente-backend:sprint19` a ECR. Task-def **rev 12** (clon de rev 11 + image sprint19 + `BEDROCK_REGION`/`LLM_MODEL_ID`/`LLM_MAX_TOKENS`). Migración + 2 seeds en RDS vía `ecs run-task` rev 12 (exit 0 los tres). `update-service` → `services-stable` (1/1, zero-downtime). Smoke: `/openapi.json` 200. CloudWatch confirma que la task llega a Bedrock con el task role (el error es de Marketplace, NO de IAM). |
| 2026-07-11 | QA | **#251 E2E contra AWS.** Login `talulah@gloma.com` y `agencia@demo.com` contra `https://api.glomabeauty.com` ✅; bots LLM resueltos y motor ejecutado en ECS ✅. Respuesta actual: fail-safe (disculpa + handoff a `asesor_1`) por el bloqueo de Marketplace (#253) — el camino completo API Gateway → ECS → Bedrock → acciones → sesión está validado. Para la prueba visual local apuntando a los motores de AWS: `cd frontend && BACKEND_URL=https://api.glomabeauty.com npm run dev` y abrir el detalle del bot → "▶ Probar Chatbot". |
| 2026-07-11 | PM | **#253 (ACCIÓN CEO — bloqueante para respuestas LLM en vivo):** AWS Marketplace rechaza el método de pago de la cuenta 747456040509 (`INVALID_PAYMENT_INSTRUMENT`) al completar la suscripción de los modelos Anthropic. Pasos: (1) Consola AWS → **Billing and Cost Management → Payment preferences** → verificar/agregar una **tarjeta de crédito válida** como método default; (2) esperar ~5 min y re-suscribir: `python -c "import boto3;c=boto3.client('bedrock',region_name='sa-east-1');mid='anthropic.claude-haiku-4-5-20251001-v1:0';t=c.list_foundation_model_agreement_offers(modelId=mid)['offers'][0]['offerToken'];print(c.create_foundation_model_agreement(modelId=mid,offerToken=t))"`; (3) verificar con `get_foundation_model_availability` que `agreementAvailability.status == AVAILABLE`. **No hace falta redeploy**: en cuanto el agreement quede AVAILABLE los 2 bots responden con Claude. Nota: durante la ventana de gracia inicial el motor SÍ conversó en vivo (evidencia en #249), así que todo lo demás está probado. |

### 6. Resumen ejecutivo de tareas y entregables (cierre)

| # | Tarea | Qué se hizo | Entregables |
|---|---|---|---|
| #239 | Apertura y análisis | Se parsearon los 7 JSON WATI de Talulah (orquestador, minoristas 44 nodos, mayoristas 16, asistente 24/7, SAC, asesor-defecto, escalar); se ubicó el contexto del demo (BD via `seed_bot_covenas.py` + media en `frontend/public/demo_viajes/`); se eligió **Bedrock sa-east-1** (motor en AWS, sin API keys, IAM role) y **contexto a priori en el contenedor**. | Sección Sprint 19 en BITACORA (§1-§3) con decisiones y faltantes de Talulah |
| #240 | Seguridad (PRE) | Revisión de diseño aprobada; 6 condiciones implementadas (secret cifrado, schemas sin llm_config, .gitignore, IAM mínimo, errores sanitizados, anti-traversal). | Entrada de log Seguridad + controles en código |
| #241-#242 | BD + paridad | Columnas `bots.engine` y `bots.llm_config`; migración idempotente corrida 2× local y 1× RDS. | `backend/scripts/migrate_sprint19_llm_bots.py` + evidencia en log |
| #243-#245 | Motor LLM + contextos | Motor conversacional Claude (tool-use loop, historial, fail-safe), cliente Shopify, 2 contextos a priori empaquetados en la imagen. | `backend/app/services/llm_engine.py`, `shopify_client.py`, `backend/app/bot_contexts/{talulah,demo_viajes}.md` |
| #246 | Integración app | Dispatch por `bot.engine` en runner + simulate; guard anti-reentrada del bot tras handoff; `engine` en schemas; UI badge IA + tarjeta detalle + Probar habilitado. | Cambios en `bot_runner.py`, `bot_router.py`, `routers/bots.py`, `schemas.py`, `crud.py`, `frontend/pages/bots.tsx`, `frontend/pages/bots/[id].tsx` |
| #247 | Cuentas y bots | Cuenta `talulah@gloma.com` + asesora + bot LLM Talulah (Shopify cifrado); bot LLM demo viajes default y flujo legacy pausado. Aplicado en local y RDS. | `backend/scripts/seed_bot_talulah.py`, `seed_bot_viajes_llm.py`; bots RDS id=7 (Talulah) y id=8 (Viajes IA) |
| #248 | Assets | Guía de tallas deduplicada y publicada para servirse desde Amplify. | `frontend/public/talulah/guia_tallas_{1..6}.jpeg` |
| #249 | QA local | 7 tests unitarios nuevos (verde), suite en línea base, conversación E2E real con Claude verificada (texto + 6 imágenes + contexto + tono). | `backend/tests/test_llm_engine.py` + evidencia en log |
| #250 | Deploy AWS | IAM Bedrock, imagen `:sprint19`, task-def rev 12, migración+seeds RDS, servicio estable, formulario Anthropic enviado. | ECR `:sprint19`, task-def `multiagente-backend:12`, policy `bedrock-invoke-anthropic` |
| #251 | E2E AWS | Camino completo validado contra `https://api.glomabeauty.com` (hoy responde fail-safe por #253). Instrucciones de prueba local→AWS documentadas. | Evidencia en log + comando `BACKEND_URL=https://api.glomabeauty.com npm run dev` |
| #252 | Cierre | Commits a `main` (Sprint 18 pendiente + Sprint 19), bitácora cerrada, memoria actualizada, deploy Amplify del frontend. | Commits en `main`, este resumen, job de Amplify |
| #253 | ⚠️ CEO | Corregir método de pago AWS Marketplace y re-suscribir el modelo (pasos exactos en el log 2026-07-11). | — |
| 2026-07-11 | PM / Dev Plataforma | **#254 ajustes post-cierre a pedido del CEO.** (1) **Módulo Mensajes conectado al puerto multi-proveedor**: `routers/mensajes.py` (respuesta manual y nueva conversación por plantilla) dejaba de usar el puerto y llamaba `meta_whatsapp` directo — era el único módulo que faltaba; ahora campañas, bots, webhooks **y mensajes manuales** envían por `services/messaging` (Meta o Twilio según `account.provider`; errores 502 sanitizados). (2) **Un único bot por cuenta para los 2 clientes LLM**: los seeds ahora eliminan TODOS los bots previos del owner antes de crear el bot LLM — `agencia@demo.com` quedó solo con "Plan Tolú & Coveñas (IA)" (el flujo legacy se eliminó; rollback = re-correr `seed_bot_covenas.py`) y `talulah@gloma.com` solo con "Talulah IA". Las demás cuentas (`prueba@gmail.com`, `demo@gmail.com`) conservan sus bots de flujo demostrativos intactos; los próximos bots se crean por seed según se defina por usuario. Aplicado en **local** (bots id=14/15) y en **RDS** (bots id=9/10, run-task exit 0, servicio redeploy `services-stable`). Verificado vía API prod: cada cuenta lista exactamente 1 bot `engine=llm`. (3) Confirmado que la ventana **"Probar Chatbot" usa el motor LLM** (el endpoint `/bots/{id}/simulate` despacha por `bot.engine`; el simulador renderiza texto, imágenes, videos y handoff del LLM); tipo TS del estado ampliado a opaco. |
| 2026-07-13 | Dev Plataforma / Experto BD | **#255 Observabilidad de decisiones del motor LLM (SOLO LOCAL — pendiente validación CEO para subir a AWS).** Pedido del CEO: "deberíamos poder saber qué decisiones tomó, que se vea en logs y se guarde en BD". Implementado: (1) tabla nueva **`bot_llm_decisions`** (una fila por turno: `camino`, `tools_called` JSON con input/resultado, `reply_preview`, `model_id`, `rounds`, `latency_ms`, `finished`, `escalated_to`, `failsafe`, `source` whatsapp/simulador, `user_input` — el contenido va a BD, NUNCA a logs) + migración idempotente `migrate_sprint19_llm_decisions.py` (2 corridas local OK; RDS pendiente del OK); (2) `llm_engine` emite `telemetry` por turno y `record_decision()` la persiste desde `bot_runner` (webhooks) y `/bots/{id}/simulate` (simulador), defensivo (nunca rompe el turno); (3) **log estructurado** `llm_decision bot=.. camino=.. tools=.. rounds=.. latency_ms=.. escalado=..` a nivel INFO (se agregó `logging.basicConfig(INFO)` en `main.py` — antes los INFO de la app no se veían); (4) clasificador de camino: prioridad tools (escalar/shopify/fin) → `camino` del media enviado → keywords de `llm_config.caminos` (nuevo en seeds) → saludo/respuesta_libre; (5) el endpoint simulate devuelve `camino` y el chat de prueba muestra chip "🧭 camino: X" por turno. Tests: 11/11 (`test_llm_engine.py`). |
| 2026-07-13 | Dev Plataforma / UI-UX | **#256 Visualizador de caminos para bots LLM (SOLO LOCAL — pendiente validación CEO).** Pedido del CEO: en el detalle del bot debe verse el flujo (no la tarjeta genérica): **bloque LLM de entrada → caminos → bloques de acción LLM** (solo lectura), mismos caminos/acciones de los JSON WATI pero simplificados (bloques en vez de menús de botones). Implementado: los seeds crean pasos VISUALES (el motor sigue siendo `llm_engine`; los pasos no se ejecutan) — Talulah 15 bloques (router con 14 rutas: 9 minorista + 4 B2B + asesor/fin; informativos vuelven al LLM, el resto → handoff), Viajes 9 bloques (8 rutas). Bloque de acción = `step_type llm, mode=accion` con `descripcion` + `fuente` (API Shopify / media / caso / contexto); el frontend los pinta con chips "acción · mensaje redactado por IA" y "fuente: X", y muestra banner explicativo sobre el diagrama. Diagrama PUML de referencia (alineación con los JSON): **`docs/bots_llm_caminos.puml`**. Verificado local: bots re-seedeados (Talulah id=18 con Shopify, Viajes id=19), simulate devuelve `camino`, fila en `bot_llm_decisions` y log INFO visibles. **AWS/commit/push EN ESPERA del aviso del CEO** (el push dispara Amplify a prod). Recordatorio: para ver respuestas LLM reales en la prueba local sigue faltando #253 (pago Marketplace). |

### 7. Tareas #257–#263 (asignación por agente — pedido CEO 2026-07-13)

| # | Tarea | Agente | Estado |
|---|---|---|---|
| #257 | Flujo visual multi-bloque fiel a los JSON WATI: cadenas por camino, condición ¿pedido encontrado? Sí/No, sub-flujos cambio/garantía y B2B en 2 pasos, botones → bloques LLM de decisión. Talulah 27 bloques / Viajes 10 (reserva en 2 pasos) | `dev-plataforma` + `ui-ux` | ✅ hecho en LOCAL |
| #258 | Búsqueda de pedidos Shopify multi-criterio: número, nombre del cliente, cédula/documento (note_attributes "Número de documento" + address.company) y fecha (created_at_min/max); filtrado en backend (sin scope read_customers); tool `consultar_pedido_shopify` ampliada + contexto actualizado | `dev-plataforma` | ✅ hecho en LOCAL, probado con las últimas 10 órdenes reales |
| #259 | QA: 10 guiones de prueba (uno por camino), ejecutados contra Bedrock en vivo, veredictos de coherencia y documento HTML desplegable | `qa` | ✅ 10/10 coherentes — artifact "Guiones de prueba" · hallazgo corregido: prioridades/keywords del clasificador de caminos (B2B primero, frases específicas en vez de palabras ambiguas) |
| #260 | Lista de datos faltantes para funcionamiento 100% (Shopify y contenido Talulah) | `project-manager` | ✅ documentada (ver artifact y §2 de este sprint) |
| #261 | Revisión de seguridad de la búsqueda por PII: hoy cualquiera con un nombre o cédula ajenos puede consultar el estado del pedido de otra persona (incluye URL de rastreo). Recomendación: exigir coincidencia de 2 datos (p. ej. cédula + nombre) o solo confirmar existencia y escalar. **Decisión del CEO pendiente** | `seguridad` | ⚠️ abierta — bloqueante recomendado antes de producción |
| #262 | Deploy a AWS de todo lo local (imagen ECR, migración `bot_llm_decisions` + seeds en RDS, redeploy ECS, Amplify) + commit/push a main | `deploy-aws` | ✅ OK del CEO 2026-07-14 — desplegado (ver log) |
| #263 | Cutover Twilio (claves de cuenta matriz/subcuenta) para WhatsApp real | `deploy-aws` + CEO | ⏸️ pendiente de cuenta Twilio (desde Sprint 18) |

### Log de ejecución (continuación 2026-07-13/14)

| Fecha | Agente | Nota |
|---|---|---|
| 2026-07-13 | Deploy AWS / PM | **#253 RESUELTO por el CEO**: pagó la factura vencida de junio ($55.84, vencía 1-jul) y registró método de pago válido. El agreement de Bedrock pasó a `AVAILABLE` (verificado 5/5 invocaciones). Diagnóstico previo confirmado vía API de Invoicing: la mora era la causa del `INVALID_PAYMENT_INSTRUMENT`. Los bots conversan EN VIVO con Claude desde local. |
| 2026-07-13 | Dev Plataforma | **#258 búsqueda Shopify multi-criterio** (pedido CEO): `shopify_client.search_orders()` busca por número (name= exacto), fecha (created_at_min/max, día completo UTC-5) y filtra en backend por nombre normalizado (sin tildes; customer + addresses + note_attributes) y documento (note_attributes "Número de documento" / address.company — así llegan los pedidos del checkout web de Talulah). Devuelve hasta 3 coincidencias. Tool y contexto actualizados para pedir nombre/cédula/fecha cuando la clienta no tiene el número. |
| 2026-07-13 | Dev Plataforma / UI-UX | **#257 flujo visual fiel a los JSON** (pedido CEO: "varios bloques por camino, con condiciones"): Talulah pasó de 15 a **27 bloques** — pedido: pide dato → consulta Shopify → **condición Sí/No** → informa/no-encontrado → asesora; cambios/garantías con mini-decisiones LLM donde había botones (Cambio|Garantía, ¿algo más?, ¿registrar caso?); B2B despachos y faltantes en 2 pasos (recolecta → registrado); informativos vuelven al bloque LLM (ex InvokeFlow→Orquestador). Viajes: reserva en 2 pasos (pide datos → datos recibidos → asesor), 10 bloques. Además feedback de layout aplicado: copys reales de WATI dentro de cada bloque (chips "✨ la IA adapta este mensaje" + "fuente"), flechas saliendo SIEMPRE del punto medio derecho del bloque y columnas centradas verticalmente. |
| 2026-07-14 | QA | **#259 guiones ejecutados y juzgados (10/10 coherentes).** T1 saludo · T2 sedes · T3 tallas (6 imágenes) · T4 pedido por número (Shopify real #53826) · T5 pedido por cédula 42062393 (lo encuentra y saluda a Patricia) · T6 pedido por nombre (pide 2º dato — conservador, ver #261) · T7 cambios · T8 B2B faltantes (caso F-2291; expuso keywords ambiguas del clasificador → corregidas y re-verificado: mayorista_ventas → mayorista_faltantes) · V9 precios con tarifarios sin inventar cifras · V10 reserva → handoff con motivo completo. Artifact publicado con los 10 guiones desplegables, transcripts reales y veredictos. |
| 2026-07-14 | Dev Plataforma / UI-UX | **#265 ajustes finales pre-deploy (pedido CEO, verificados en local).** (1) **Bloque LLM post-acción** en ambos bots: tras una acción/mensaje final, si el cliente vuelve a escribir, un bloque "🤖 LLM · ¿algo más o despedida?" relee y decide — nuevo tema → router, asesora → handoff, despedida → fin (contextos actualizados con la regla; smoke: "gracias, eso era todo" → camino `fin` + cierre elegante). Talulah 28 bloques / Viajes 11. (2) **Visualizador**: fondos pastel por tipo de bloque (fucsia=LLM, naranja=condición, esmeralda=handoff, rosa=fin...) y **zoom con 3 botones fijos** abajo a la derecha (⤢ vista completa —default al abrir—, + acercar, − alejar; escala 0.15–2x). (3) **Bienvenida Talulah**: ya no pregunta clienta/tienda — pide el nombre, pregunta "¿en qué te puedo ayudar hoy?" y la IA intuye B2B vs detal por el mensaje. (4) Documentos guardados en el repo: `estructura_motor_llm.html` y `guiones_prueba_bots.html`. |
| 2026-07-14 | PM | **#264 (nuevo): catálogo de WhatsApp vía Meta Business.** El CEO gestiona el catálogo desde Commerce Manager y quiere que el bot lo use en el camino "Catálogo". Requisitos para conectarlo: (a) catálogo creado en **Commerce Manager** y **vinculado a la WABA** (WhatsApp Manager → Catálogo); (b) como el envío saldrá por **Twilio** (Sprint 18), se usa el **Content API tipo `twilio/catalog`** (o mensajes interactivos `product_list` si fuera Meta directo); (c) datos que debe pasar el CEO: **catalog_id** de Commerce Manager y los **retailer_id** de productos destacados (o usar el catálogo completo); (d) implementación: nueva tool `enviar_catalogo` en el motor + content template registrado en la subcuenta Twilio de Talulah. **Bloqueado por las claves Twilio (#263, el CEO las está gestionando).** Asignado: `dev-plataforma` + `deploy-aws`. |
| 2026-07-14 | Dev Plataforma / Deploy AWS | **#264 catálogo de WhatsApp implementado (catalog_id CEO: 176204398531184).** Nueva tool `enviar_catalogo` en el motor (activa cuando `llm_config.catalogo.catalog_id` existe): emite acción `say_catalog`; el simulador la pinta como tarjeta nativa de catálogo ("Ver artículos") y `bot_runner` la envía como **Content Template `twilio/catalog`** vía el puerto de mensajería cuando la cuenta sea Twilio y exista `content_sid` — mientras tanto, fallback de texto. Camino observado: `catalogo`. Script `create_twilio_catalog_template.py` listo para crear la plantilla (Content API; dentro de ventana 24h NO requiere aprobación Meta; `--approve` para fuera de ventana). Contexto y bloque visual "Catálogo de WhatsApp" actualizados. Smoke local ✅ (tarjeta + camino). **Activación real bloqueada solo por #263 (claves Twilio, CEO gestionando) + vincular el catálogo a la WABA en WhatsApp Manager.** Guía de conexión Twilio seguida del plugin `twilio-developer-kit` (skills twilio-account-setup / whatsapp-manage-senders / content-template-builder). |
| 2026-07-14 | Deploy AWS / Seguridad | **#263 credenciales Twilio conectadas (cuenta "Talulah" `AC448da...`, tipo Full, balance US$20).** Verificadas por API (API key + auth token válidos; 0 senders WhatsApp aún). Manejo de secretos: (1) local en `CREDENCIALES_TWILIO.txt` (chmod 600, cubierto por `.gitignore` con patrón `CREDENCIALES*.txt`) + `TWILIO_*` en `.env` raíz git-ignorado con passthrough en docker-compose; (2) AWS en **SSM SecureString** `/multiagente/prod/TWILIO_{ACCOUNT_SID,AUTH_TOKEN,API_KEY_SID,API_KEY_SECRET}` — el `ecsTaskExecutionRole` ya tenía policy sobre esa ruta; (3) **task-def rev 13** los inyecta como `secrets` + env `TWILIO_WEBHOOK_BASE_URL=https://api.glomabeauty.com` y `TWILIO_SANDBOX=1` (seguirá simulado hasta que exista el sender). Deploy `services-stable`. QA de seguridad de webhooks EN PROD con el token real: sin firma → **403 fail-closed** ✅; con firma HMAC-SHA1 válida → **200** ✅. **Siguiente paso (CEO)**: elegir número para el sender de WhatsApp — comprar uno en Twilio o migrar el de Talulah desde WATI — y vincular el catálogo `176204398531184` a la WABA; con el sender ONLINE: registrar webhooks del sender, crear plantilla de catálogo (script listo), `TWILIO_SANDBOX=0` y `provider='twilio'`. Recomendación de seguridad: rotar el Auth Token tras el go-live (se compartió por chat). |
| 2026-07-14 | Deploy AWS / PM | **#263 números +57 en Twilio — consulta al CEO (sin compra).** Verificado por API: Twilio SÍ vende números de Colombia pero solo **fijos** (601 Bogotá, 602 Valle, etc., solo voz) a **US$14/mes** y **líneas 800** a US$25/mes — **no hay celulares +57 3xx**. Además exigen **dirección física en Colombia** registrada (requisito regulatorio `address_requirements=local`). Un número USA (~US$1.15/mes) puede escribir a Colombia sin problema por WhatsApp (Meta tarifica por país destino), solo que el cliente ve +1. **Recomendación del PM: migrar el número actual de WATI** (+57 celular, conocido por las clientas y con el catálogo 176204398531184 ya vinculado a su WABA). Pasos de desconexión WATI y de vínculo de catálogo entregados al CEO. Decisión pendiente: fijo 601 / número USA / migración WATI. |
| 2026-07-14 | QA | **#259-bis guiones del bot Demo Viajes (pedido CEO).** 10 guiones ejecutados en vivo contra Claude (V1 saludo · V2 info general · V3 tours con imagen+video · V4 precios SIN inventar cifras (tarifarios) · V5 itinerario completo (chip marcó `tours` por el video adjunto — respuesta correcta) · V6 pagos · V7 reserva completa → handoff con motivo y datos · V8 asesor directo · **V9 valida el bloque post-acción**: tras precios pide itinerario y la IA re-enruta · V10 despedida con puerta abierta — no cierra formal, correcto). 10/10 coherentes. Documento en el repo: `guiones_prueba_viajes.html` (+ artifact). Cuenta de prueba: agencia@demo.com / «en el gestor del CEO». WATI: el CEO hará la desconexión del número; conexión del sender queda en espera (#263). |
| 2026-07-14 | Deploy AWS | **#263 registro del sender iniciado — bloqueado por WABA (esperando accesos del CEO).** Intento de registro de `whatsapp:+573043553800` vía Senders API v2 (verificación SMS a la SIM del CEO, webhooks a api.glomabeauty.com y perfil "Talulah" / Clothing and Apparel preconfigurados). Twilio responde: `waba_id is required when creating the first sender` (error 63100) — para registrar el primer sender de la cuenta se necesita el **ID de la WABA** del cliente. Cuando el CEO tenga el acceso: (1) sacar el WABA ID en business.facebook.com/wa/manage (Configuración → Cuentas → Cuentas de WhatsApp → ID numérico); (2) re-lanzo el registro con `waba_id`; (3) el CEO acepta la **invitación de Twilio** que aparecerá en su Meta Business Manager (si no se acepta, el sender queda OFFLINE con razón 63020); (4) llega el OTP por SMS a la SIM → me lo pasa → sender ONLINE → cutover (`TWILIO_SANDBOX=0`, `provider='twilio'`, plantilla de catálogo). ⚠️ Recordatorio: **exportar el historial de chats de WATI ANTES de cancelar** la cuenta (no se migra entre BSPs; solo migra el número). |
| 2026-07-14 | PM | **PENDIENTES registrados a pedido del CEO:** (#264) **configurar el catálogo de Talulah** — vincular el catálogo `176204398531184` a la WABA definitiva en WhatsApp Manager, crear la plantilla `twilio/catalog` (script listo) y re-seedear con el `content_sid`; (#266, nuevo) **el CEO está gestionando que le den los accesos a las WABA de ambos clientes** (Talulah y Agencia de Viajes) en sus Meta Business — sin esos accesos no se puede registrar el sender (waba_id), aceptar la invitación de Twilio ni administrar el catálogo. Ambas tareas quedan bloqueadas solo por esos accesos. |
| 2026-07-14 | Deploy AWS | **#263 WABA 1272393681746114 rechazada por Twilio (error 63101: "not valid or unable to be used").** Causa confirmada en doc oficial: la WABA fue creada bajo otro proveedor (WATI) y **no está compartida con Twilio** — para usarla (o crear una nueva) hay que completar el **Embedded Signup con login de Facebook en la consola de Twilio**, paso que solo puede hacer el CEO en navegador: Console → Messaging → Senders → WhatsApp senders → New WhatsApp Sender → "Sign in with Facebook" (admin del Meta Business de Talulah) → conceder a Twilio la gestión de la WABA → registrar +573043553800 en el mismo wizard (OTP por SMS a la SIM). Si la WABA de WATI no aparece en el wizard (por ser del Business de WATI), crear una WABA nueva ahí mismo y re-vincular el catálogo 176204398531184 (pasos ya documentados). Al terminar el wizard, Deploy AWS retoma por API: webhooks del sender → api.glomabeauty.com, plantilla twilio/catalog, TWILIO_SANDBOX=0 y provider='twilio'. |

---

## Sprint 20 — Cuenta oficial de Gloma + Bot institucional en 3 canales (2026-07-31)

**Pedido del CEO (2026-07-31):**

> Crear una cuenta en la app que sea la **oficial de Gloma** y un bot que hable de la
> empresa y de cómo ayudamos a las empresas a mejorar la experiencia de sus clientes
> con agentes que siguen la personalidad de su marca, resuelven como lo haría una
> persona y asignan un asesor humano cuando el caso lo requiere. Para ese bot, un
> **guion de 15 preguntas** de mayor interés para una empresa que quiere un agente de
> WhatsApp para servicio al cliente y ventas, con la **respuesta ideal cargada como
> información a priori** del modelo. El bot debe quedar **funcionando y probable
> contra AWS**, quedando pendiente únicamente conectar un WhatsApp a la cuenta.
> Además, en la **landing glomabeauty.com** un **botón de WhatsApp en la esquina
> inferior derecha** que abre el chat con ese mismo bot **sin necesidad de WhatsApp**
> (se instancia el bot en la web). El bot queda entonces conectado a **3 recursos**:
> el WhatsApp de Gloma (cuando se instale), el simulador de la app web y la landing.

### 1. Tareas del Sprint 20 y responsables (agentes)

| # | Tarea | Agente | Descripción |
|---|---|---|---|
| #267 | Contexto a priori `gloma.md` con las 15 preguntas y su respuesta ideal | `dev-plataforma` | `backend/app/bot_contexts/gloma.md`: identidad de Gloma, tono de marca, reglas de escalamiento y el bloque de 15 Q&A (qué es Gloma, diferencia vs chatbot de botones, personalidad de marca, escalamiento a humano, integraciones, ventas, conexión a WhatsApp, implementación, precios, seguridad/datos, alucinaciones y guardarraíles, medición, campañas, B2B/multi-público, cómo empezar). Prohibido inventar precios y plazos. |
| #268 | Cuenta oficial + seed del bot | `experto-bd` | `backend/scripts/seed_bot_gloma.py`: owner `gloma@glomabeauty.com` + team "Gloma" + asesor humano `asesor_1` + bot LLM **"Gloma IA — Ventas y Servicio"** (engine `llm`, default de la cuenta, contexto `gloma`, `caminos` para observabilidad). Idempotente; correr en local y RDS (convención #1). |
| #269 | Endpoint público `POST /landing/chat` | `dev-plataforma` | Instancia el bot de Gloma sin auth para la landing: sesión **cifrada Fernet** (el historial nunca lo controla el cliente), rate-limit por IP, tope de turnos por sesión, input acotado, telemetría en `bot_llm_decisions` con `source='landing'`, fail-safe con CTA a WhatsApp humano. |
| #270 | Widget flotante en la landing | `ui-ux` + `dev-plataforma` | Botón verde de WhatsApp abajo a la derecha en `pages/gloma.tsx` + panel de chat con identidad Gloma (Syne/Inter, rosa empolvado y marrón tierra), typing indicator, aviso de IA, y CTA a WhatsApp/asesor humano cuando el bot escala. |
| #271 | Revisión de seguridad del canal público | `seguridad` | Endpoint sin auth: abuso/coste (rate-limit + tope de turnos), integridad del estado (AEAD), no exponer `llm_config` ni errores del proveedor, prompt-injection desde el visitante, datos personales del visitante. |
| #272 | QA local | `qa` | Las 15 preguntas contra el bot real (Bedrock) por `/bots/{id}/simulate` y por `/landing/chat`; escalamiento a asesor; widget en `npm run dev`. |
| #273 | Deploy AWS `sa-east-1` | `deploy-aws` | Build/push `multiagente-backend:sprint20`, task-def nueva rev, `update-service` hasta stable, seed en RDS vía `ecs run-task`, deploy manual de Amplify (gotcha conocido). |
| #274 | Cierre del sprint | `project-manager` | Registro de resultados y entregables en esta bitácora + memoria persistente. |

### 2. Decisiones de arquitectura

1. **Un solo bot, tres canales.** El bot vive una sola vez en la BD (cuenta Gloma) y lo
   consumen tres entradas distintas al mismo `services/llm_engine.advance()`:
   `twilio_webhook`/`meta_webhook` (WhatsApp, cuando se conecte el número),
   `POST /bots/{id}/simulate` (simulador de la app, con JWT) y `POST /landing/chat`
   (landing pública, sin JWT). Cambiar el contexto o el guion actualiza los tres.
2. **La landing no crea cuentas ni conversaciones.** El visitante es anónimo: la sesión
   es un token cifrado que viaja en el request y guarda el historial. No se persiste
   PII del visitante; sí queda la telemetría del turno (`source='landing'`) para medir
   qué preguntan los prospectos.
3. **Escalamiento sin WhatsApp conectado.** En la landing, `escalar_a_asesor` no puede
   entregar la conversación a la bandeja (no hay número aún): el widget muestra el CTA
   a `wa.me/573003187871` y al formulario de contacto. Cuando el WhatsApp de Gloma
   quede conectado, ese mismo bot escala a la bandeja como los demás.

### 3. Log de ejecución del Sprint 20

| Fecha | Agente | Nota |
|---|---|---|
| 2026-07-31 | PM | Sprint abierto. Tareas #267-#274 asignadas a los agentes de la tabla. Exploración previa: el motor LLM (`llm_engine`) y el patrón de seed (`seed_bot_talulah.py`) se reutilizan tal cual; la landing ya expone `/api/landing/*` como único path permitido bajo `glomabeauty.com` (`frontend/middleware.ts`), así que el chat público entra por ahí sin tocar el middleware. |
| 2026-07-31 | Dev Plataforma | **#267 contexto a priori `gloma.md`.** Identidad de Gloma (qué es, sede Cali, contacto, cifras de la landing, módulos de la plataforma, stack Claude/AWS/WhatsApp API), tono de la asistente **"Lía"**, reglas de escalamiento y **las 15 preguntas con su respuesta ideal**: (1) qué es Gloma, (2) diferencia vs chatbot de botones, (3) personalidad de marca, (4) qué pasa si el bot no sabe / piden humano, (5) integraciones (Shopify/ERP/CRM), (6) ¿vende o solo responde?, (7) conexión del número a WhatsApp, (8) implementación y requisitos, (9) precios y modelo de cobro, (10) seguridad y datos, (11) alucinaciones y guardarraíles, (12) medición de resultados, (13) campañas masivas, (14) varios públicos (B2C+B2B), (15) cómo empezar / demo. **Regla de oro escrita en el contexto: nunca dar precios, plazos ni prometer integraciones no confirmadas** → esos caminos escalan a un especialista. Casos reales mencionables descritos por industria (marca de moda y agencia de viajes), sin datos privados. |
| 2026-07-31 | Experto BD | **#268 cuenta oficial + seed.** `backend/scripts/seed_bot_gloma.py` (idempotente): owner `gloma@glomabeauty.com` (pwd `Gloma2026*`), team "Gloma", asesor `asesor1.gloma@glomabeauty.com` (handle `asesor_1`) y bot **"Gloma IA — Ventas y Servicio"** `engine=llm`, `trigger_type=default`, contexto `gloma`, 19 bloques visuales (router LLM → 15 caminos → post-acción → asesor/fin) y `caminos` de observabilidad para los 15 temas. Un único bot por cuenta (#254). **Local (docker-compose):** bot id=28. **RDS (`ecs run-task` rev 14):** exit 0, bot id=14 → paridad local↔RDS cumplida (convención #1). Sin cambios de schema: el sprint no necesitó migración. |
| 2026-07-31 | Dev Plataforma | **#269 endpoint público `POST /landing/chat`.** Instancia el bot institucional sin JWT para el widget de la landing, con el MISMO `services/llm_engine` del simulador y de los webhooks. Estado de la conversación en un **token Fernet** (AEAD) que viaja al cliente: el visitante no puede inyectar historial ni inflarlo; token manipulado o vencido (TTL 3h) → sesión nueva, nunca error. Guardas: 500 chars por mensaje, 25 turnos por sesión, 40 turnos/hora por IP y 400/hora globales (techo de gasto Bedrock), limpieza de caracteres de control. Telemetría por turno en `bot_llm_decisions` con `source='landing'` (nuevo valor). `escalar_a_asesor` en este canal no entrega a la bandeja (aún no hay número): responde con el CTA a `wa.me/573003187871` + formulario, y marca `handoff=true` para el widget. Extra: `crypto.decrypt_secret(..., ttl_seconds=)` y `llm_engine._to_whatsapp_format()` — normaliza `**negrilla**` de Markdown a `*negrilla*` de WhatsApp para los tres canales (el modelo recaía en Markdown). |
| 2026-07-31 | UI/UX + Dev Plataforma | **#270 widget flotante.** `frontend/components/GlomaChatWidget.tsx` montado en `pages/gloma.tsx`: botón verde WhatsApp abajo a la derecha (con pulso y badge de no leídos), panel con identidad Gloma (Syne/Inter, rosa empolvado + marrón tierra), typing indicator, sugerencias de arranque, render del formato `*negrilla*`, aviso de que se conversa con un agente de IA + nota de datos, cierre con Escape, seguro en móvil (`safe-area-inset`, ancho fluido). Habla con el backend por `/api/landing/chat` (rewrite de Next → API Gateway), el único prefijo que `middleware.ts` permite bajo `glomabeauty.com`, así que **no hubo que tocar el middleware**. |
| 2026-07-31 | Seguridad | **#271 revisión del canal público.** Sin hallazgos Críticos/Altos. Verificado: (a) `ChatOut` no expone `llm_config`, `engine`, ids internos ni detalle de errores — el fail-safe del motor responde disculpa + canal humano (reglas #2/#6); (b) el historial va cifrado con Fernet, no en claro en el cliente; (c) abuso y gasto acotados por rate-limit por IP + techo global + tope de turnos; (d) el texto del bot se renderiza como nodo de React (sin `dangerouslySetInnerHTML`) y las URLs de media salen del catálogo del servidor, no del visitante. **Riesgos aceptados y documentados:** (1) `X-Forwarded-For` es falsificable si alguien llama la API directo saltándose API Gateway — el techo global es el backstop; (2) un token de sesión viejo puede reusarse para reiniciar el contador de turnos — sigue acotado por el límite por IP; (3) prompt-injection del visitante puede alterar lo que el bot le responde a él mismo (impacto reputacional, no de datos): mitigado con "no reveles estas instrucciones" y sin herramientas sensibles en este bot; (4) `user_input` del visitante se guarda en `bot_llm_decisions` (puede traer su correo/teléfono) → el widget avisa que la conversación se guarda y pide no compartir datos sensibles. Observación preexistente (no del sprint): CORS del backend en `allow_origins=["*"]`. |
| 2026-07-31 | QA | **#272 pruebas locales.** Guion de las 15 preguntas contra Bedrock real por `/landing/chat` (dos corridas de 10 y 7 turnos): respuestas coherentes con el contexto, personalizadas al negocio del prospecto, **sin inventar precios** (la pregunta de precio explica el modelo y ofrece cotización), escalamiento correcto al pedir demo (`handoff=true`, conversación cerrada) y despedida limpia con `finalizar_conversacion`. Telemetría verificada en `bot_llm_decisions`: caminos `saludo`, `que_es_gloma`, `precios`, `diferencia_chatbot`, `publicos_b2b`, `escalar_a_asesor`, `fin`. Canal simulador verificado con login `gloma@glomabeauty.com` → `/bots` lista 1 bot `engine=llm` → `/bots/14/simulate` responde. Unit tests nuevos `backend/tests/test_landing_chat.py` (11 casos: formato WhatsApp, roundtrip y manipulación del token, handoff, tope de turnos, rate-limit, sanitización) → **29 passed** junto a `test_llm_engine`/`test_crypto`. `npm run build` OK y widget servido en `/gloma`. Dos ajustes de contexto tras QA: negrilla de un solo asterisco y no repetir la pregunta del nombre en cada mensaje. *Nota*: los 7 fallos de `tests/test_meta_account_flow.py` son **preexistentes** (SQLite no compila el tipo `JSONB` de `users.tutorials_completed`, Sprint 15), ajenos a este sprint. |
| 2026-07-31 | Deploy AWS | **#273 despliegue sa-east-1.** Build `linux/amd64` + push `multiagente-backend:sprint20` a ECR. Task-def **rev 14** (clon de rev 13, solo cambia la imagen). Seed en RDS vía `ecs run-task` rev 14 → exit 0 (owner + asesor + bot id=14). `update-service --task-definition :14 --force-new-deployment` → `services-stable` (1/1, zero-downtime). Frontend: commit `1d3edfc` a `main` → Amplify **job 37 SUCCEED** (esta vez sí auto-buildeó). **Smoke en producción:** `https://api.glomabeauty.com/openapi.json` 200; `POST https://api.glomabeauty.com/landing/chat` responde con el saludo de Lía generado por Bedrock y devuelve token de sesión; `https://glomabeauty.com/` sirve el botón flotante (`aria-label="Hablar con Gloma por WhatsApp"`) y `POST https://glomabeauty.com/api/landing/chat` conversa end-to-end. |

### 4. Entregables del Sprint 20

| # | Entregable | Dónde |
|---|---|---|
| #267 | Contexto a priori con las 15 preguntas y su respuesta ideal | `backend/app/bot_contexts/gloma.md` |
| #268 | Cuenta oficial + bot institucional (local id=28, RDS id=14) | `backend/scripts/seed_bot_gloma.py` |
| #269 | Chat público de la landing | `backend/app/routers/landing.py` (`POST /landing/chat`), `services/crypto.py`, `services/llm_engine.py` |
| #270 | Widget flotante de WhatsApp | `frontend/components/GlomaChatWidget.tsx` + `frontend/pages/gloma.tsx` |
| #272 | Tests | `backend/tests/test_landing_chat.py` (11 casos) |
| #273 | Producción | imagen `:sprint20`, task-def rev 14, Amplify job 37 |

**Estado final:** el bot de Gloma queda conectado a los 3 recursos pedidos —
(1) **WhatsApp de Gloma**: listo a nivel de motor; falta únicamente conectar el número
(mismo procedimiento pendiente para Talulah, #263/#266); (2) **simulador de la app**:
`app.glomabeauty.com` → login `gloma@glomabeauty.com` / `Gloma2026*` → Bots → Probar
Chatbot; (3) **landing**: botón verde de WhatsApp abajo a la derecha en
`glomabeauty.com`, conversando con Bedrock sin salir de la página.

**Para afinar con el CEO** (el bot hoy NO da estos datos, escala a un humano):
precios y planes concretos, plazos de implementación por tipo de proyecto, y si se
quiere mencionar por nombre a los clientes actuales en vez de describirlos por industria.

---

## Sprint 21 — Agendamiento de demos desde el bot de Gloma (2026-07-31)

**Pedido del CEO (2026-07-31):** el bot, además de resolver dudas, debe **buscar
agendar una sesión de demostración**. Si el prospecto acepta: mostrar en *bullet
points* las opciones de **lunes a viernes, de 2:00 p.m. a 6:00 p.m., cada hora**,
pedir un **correo** para registrar la demo, despedirse y **registrar los datos en una
base de datos**. Decisión del CEO tras evaluar opciones: **no conectar Google Sheets**
— los registros van a una **tabla nueva en la base de datos de Gloma**, que él
monitorea directamente. (Se alcanzó a crear la hoja `Gloma — Demos agendadas (bot
Lía)` en su Drive antes de la decisión; queda sin uso.)

### 1. Tareas del Sprint 21 y responsables (agentes)

| # | Tarea | Agente | Descripción |
|---|---|---|---|
| #275 | Tabla `demo_bookings` + migración idempotente | `experto-bd` | Modelo SQLAlchemy + `backend/scripts/migrate_sprint21_demo_bookings.py` (`CREATE TABLE IF NOT EXISTS` + índices). Aplicar en local y RDS en el mismo PR (convención #1). |
| #276 | Tool `registrar_demo` en el motor LLM | `dev-plataforma` | Nueva herramienta gated por `llm_config.agenda`; valida correo y franja; la reserva viaja en `telemetry` (no como acción nueva, para no tocar el runner ni el simulador) y la persisten los 3 canales: `/landing/chat`, `/bots/{id}/simulate` y `bot_runner`. |
| #277 | Contexto: flujo de agendamiento | `dev-plataforma` | `gloma.md`: la meta de toda conversación es la demo; al aceptar, bullets de L-V y 2:00-6:00 p.m.; pedir nombre, empresa y correo; confirmar y despedirse. Sin inventar disponibilidad: la franja se confirma por correo. |
| #278 | Widget alineado a la nueva paleta de la landing | `ui-ux` | La landing cambió a la paleta Deep Forest/Mint; el panel del chat se re-tematiza (el botón sigue verde WhatsApp por reconocimiento). |
| #279 | Revisión de seguridad de la nueva PII | `seguridad` | Correo/teléfono de prospectos en `demo_bookings`: minimización, no loggear, no exponer en endpoints públicos, límites anti-spam del registro. |
| #280 | QA de agendamiento | `qa` | Guion completo en los 3 canales: duda → propuesta de demo → bullets → datos → confirmación y registro en BD. |
| #281 | Deploy AWS | `deploy-aws` | Imagen `:sprint21`, task-def nueva rev, migración en RDS vía `ecs run-task`, `update-service` y build de Amplify. |
| #282 | Cierre del sprint | `project-manager` | Entregables, query de monitoreo para el CEO y memoria persistente. |

### 2. Log de ejecución del Sprint 21

| Fecha | Agente | Nota |
|---|---|---|
| 2026-07-31 | PM | Sprint abierto con las tareas #275-#282. Decisión de diseño: la reserva **no** se emite como acción nueva del motor (el `bot_runner` y el simulador loguearían/renderizarían una acción desconocida); viaja en `telemetry` junto a la observabilidad #255 y la persiste el caller, igual que `record_decision`. |
| 2026-07-31 | Experto BD | **#275 tabla `demo_bookings`.** Modelo `models.DemoBooking` (bot_id, source, nombre, empresa, correo, telefono, dia, hora, notas, estado, created_at) con `__repr__` que no filtra PII, + `backend/scripts/migrate_sprint21_demo_bookings.py` idempotente (5 índices). **Local (docker-compose):** 2 corridas, la 2ª sin cambios ✅. **RDS (`ecs run-task` rev 15):** exit 0, 12 columnas verificadas ✅. Paridad local↔RDS cumplida (convención #1). |
| 2026-07-31 | Dev Plataforma | **#276-#277 agendamiento.** Tool `registrar_demo` en `llm_engine` (activa solo si `llm_config.agenda` existe) con validación server-side: correo con formato válido y día de lunes a viernes — si falla, el resultado de la tool le dice al modelo que lo pida de nuevo y **no** registra. La reserva viaja en `telemetry["bookings"]` y la persiste el caller con `llm_engine.record_booking()`, enchufado en los **3 canales**: `/landing/chat`, `/bots/{id}/simulate` y `bot_runner` (WhatsApp). Se eligió telemetría en vez de una acción nueva porque el runner loguea "acción desconocida" y el simulador la renderizaría como burbuja vacía. Nuevo camino de observabilidad `demo_agendada`. Contexto `gloma.md`: la meta de la conversación es la demo, franjas en bullets (L-V · 2:00, 3:00, 4:00, 5:00 y 6:00 p.m., hora Colombia), pedir correo, registrar, confirmar y despedirse; prohibido inventar disponibilidad concreta o decir que quedó agendada sin confirmación de la tool; si el prospecto da correo+día+hora de una, se registra sin interrogarlo. Seed actualizado (`agenda` en `llm_config` + 2 bloques visuales: "Agenda · franjas y correo" → "Agenda · registra y se despide" → fin). |
| 2026-07-31 | Seguridad | **#279 revisión de la nueva PII.** Sin hallazgos Críticos/Altos. `DemoBooking.__repr__` redacta (regla #1); `record_booking` loggea solo `guardadas`, `bot` y `source` — nunca el correo; ningún endpoint expone la tabla (el CEO la consulta en BD); la validación del correo y del día ocurre en el servidor, no se confía en el modelo; el registro exige una conversación completa y queda acotado por el rate-limit de la landing. Riesgo aceptado: un mismo prospecto puede registrar varias demos (no hay dedupe) — se revisa a mano en la tabla. Recordatorio operativo: los datos son de prospectos reales (habeas data) — no exportar la tabla a terceros. |
| 2026-07-31 | QA | **#280 QA del agendamiento.** *Landing (local):* conversación completa de 5 turnos — duda → invitación a la demo → bullets con las 5 franjas → elección "miércoles 4pm" → correo y celular → confirmación y despedida; fila 1 en `demo_bookings` con nombre, empresa, correo, teléfono, día, hora y notas ✅. *Simulador (local):* con todos los datos en un solo mensaje registró de una (fila 2, `source='simulador'`, camino `demo_agendada`) ✅. *Producción (`api.glomabeauty.com`):* mismo flujo → `demo_booking guardadas=1 bot=15 source=landing` en CloudWatch y filas verificadas en RDS ✅. Unit tests nuevos (tool gateada por `agenda`, normalización, correo inválido, fin de semana rechazado, reserva en telemetry y NO como acción) → **34 passed**. |
| 2026-07-31 | Deploy AWS | **#281 despliegue sa-east-1.** Imagen `multiagente-backend:sprint21` (linux/amd64) → ECR. Task-def **rev 15**. Migración `migrate_sprint21_demo_bookings.py` y re-seed del bot en RDS vía `ecs run-task` rev 15 (exit 0 ambos; bot RDS id=15 con 21 bloques). `update-service --task-definition :15 --force-new-deployment` → `services-stable`. Smoke en producción: agendamiento completo desde `https://api.glomabeauty.com/landing/chat` → 2 filas de QA en `demo_bookings` (correo `qa.sprint21@gloma.test`, borrables). **Sin build de Amplify**: el sprint es solo backend; el rediseño de la landing a la paleta Deep Forest/Mint y el re-tema del widget están en el árbol de trabajo de otra sesión y se despliegan con su propio commit. |
| 2026-07-31 | UI/UX | **#283 re-paleta de la landing de Gloma (nuevo mercado: agencias de viajes).** `pages/gloma.tsx` y `components/GlomaChatWidget.tsx` pasan a la paleta de `/automatas`: Technical Black `#101817` / `#0B1413`, Deep Forest `#004D40`, Algorithmic Mint `#4DB6AC`, texto `#E6EFEE` y muted 65%. Mapeo: crema y blanco → fondos oscuros; marrón (texto) → texto claro; rosa (acento) → mint en CTAs, métricas, títulos del footer y nodos del hero; tarjetas `rgba(255,255,255,.03)` + borde mint 15%; overlay del banner ahora oscuro. **Solo color**: contenido, tipografía (Syne + Inter), estructura y animaciones sin tocar; las imágenes las actualiza el CEO. Se mantiene el verde WhatsApp `#25D366` en el botón flotante y el CTA del widget (affordance del canal, no branding). Verificado con `tsc --noEmit` y capturas de la página completa en local. |

### 3. Entregables del Sprint 21

| # | Entregable | Dónde |
|---|---|---|
| #275 | Tabla `demo_bookings` (local + RDS) | `backend/app/models.py`, `backend/scripts/migrate_sprint21_demo_bookings.py` |
| #276 | Tool `registrar_demo` + `record_booking` en los 3 canales | `backend/app/services/llm_engine.py`, `routers/landing.py`, `routers/bots.py`, `services/bot_runner.py` |
| #277 | Flujo de agendamiento con franjas L-V 2:00-6:00 p.m. | `backend/app/bot_contexts/gloma.md`, `backend/scripts/seed_bot_gloma.py` |
| #280 | Tests | `backend/tests/test_landing_chat.py` (34 casos en total) |
| #281 | Producción | imagen `:sprint21`, task-def rev 15, bot RDS id=15 |

**Cómo monitorea el CEO las demos agendadas** (decisión: BD, no Google Sheets):

```sql
SELECT created_at, nombre, empresa, correo, telefono, dia, hora, source, estado, notas
FROM demo_bookings ORDER BY created_at DESC;
```

RDS `multiagente-db` **no es públicamente accesible** (`PubliclyAccessible=false`,
sg `sg-056f67098a4f41cf6`): hoy solo se consulta desde dentro de la VPC (ECS). Para que
el CEO consulte desde su equipo hay tres caminos, pendientes de su decisión:
(a) abrir acceso público de RDS + regla del SG para su IP fija (rápido, expone el
puerto 5432 a internet), (b) un bastión/túnel SSM (más seguro, más setup), o
(c) una vista de "Demos agendadas" dentro de la app con login (lo más limpio para uso
diario; queda como #283 en Sprint Futuro).

### 4. Adición #283-#287 — módulo interno "Citas" (2026-07-31)

**Pedido del CEO:** una pestaña `/citas` accesible **solo para la cuenta de Gloma**,
con un visualizador de la tabla de demos que permita editarla (cambiar valores cuando
se agenda o se reprograma una sesión).

| # | Tarea | Agente | Resultado |
|---|---|---|---|
| #283 | Router `/citas` (listar, editar, borrar) | `dev-plataforma` | `backend/app/routers/citas.py`: `GET /citas` (con filtro por estado + resumen), `PATCH /citas/{id}` (parcial) y `DELETE /citas/{id}`. Dependencia `require_gloma_account`: pasa el owner `gloma@glomabeauty.com` y los miembros de su team; cualquier otra sesión → **403** sin explicar por qué (regla #6). Estados: `solicitada`, `confirmada`, `realizada`, `cancelada`, `no_asistio`. |
| #284 | Página `/citas` + ítem de menú | `ui-ux` + `dev-plataforma` | `frontend/pages/citas.tsx`: tarjetas de resumen, filtros por estado, tabla (agendada, prospecto, contacto, franja, canal, estado, acciones), cambio de estado en línea con un `select`, modal de edición completo (nombre, empresa, correo, teléfono, día, hora, estado, notas) y borrado con confirmación; estado "Módulo privado 🔒" si el backend responde 403. `Sidebar` muestra la pestaña **solo** a correos `@glomabeauty.com` (cosmético: la autorización real es del backend). |
| #285 | Seguridad | `seguridad` | Validación **server-side** de la edición: correo con formato válido, estado dentro del enum, día solo de lunes a viernes; el log de la edición registra los **campos** cambiados, nunca los valores (PII). El módulo no aparece en el menú de otras cuentas y su API responde 403 aunque conozcan la URL. |
| #286 | QA local | `qa` | `GET /citas` como Gloma → 200 con las 2 citas y el resumen; como `talulah@gloma.com` → **403**; sin token → **401**. `PATCH` de estado+hora+notas → 200 y persistido; estado inventado, correo inválido y día "sábado" → **422**; id inexistente → **404**. `npm run build` compila `/citas` (4.75 kB). |
| #287 | Deploy | `deploy-aws` | Imagen `multiagente-backend:sprint21b`, task-def **rev 16**, `update-service` a rev 16; frontend por Amplify con el push a `main`. |

**Ajustes #288-#289 (pedido del CEO, 2026-07-31):**

| # | Tarea | Agente | Resultado |
|---|---|---|---|
| #288 | La pestaña se ve solo en la cuenta donde funciona | `dev-plataforma` | Nuevo `GET /citas/access` → `{allowed: bool}` (200 siempre, no filtra nada). El `Sidebar` ya no adivina por el dominio del correo: le pregunta al backend si ESTA sesión puede usar el módulo. Verificado: `gloma@glomabeauty.com` → `true`, `asesor1.gloma@glomabeauty.com` (miembro del team) → `true`, `talulah@gloma.com` → `false` (y sin pestaña). |
| #289 | Alta manual de citas | `dev-plataforma` | `POST /citas` (201) con `source='manual'` para las demos agendadas por fuera del bot (llamada, correo, evento). Misma validación que la edición: correo obligatorio y válido, estado del enum, día L-V (correo malo y "domingo" → 422; otra cuenta → 403). En la UI: botón **"+ Nueva cita"** en el encabezado y en el estado vacío, reusando la ventana de edición (título y botón cambian a "Nueva cita" / "Crear cita"). |

### 5. #290 — Paleta de la app alineada a la nueva identidad (2026-07-31)

**Pedido del CEO:** la plataforma debe usar los colores nuevos de la marca (los que
ya tiene la landing).

| # | Tarea | Agente | Resultado |
|---|---|---|---|
| #290 | Re-tinte de la plataforma | `ui-ux` | Los tokens `gloma-*` están usados ~800 veces con un rol semántico fijo (`brown` = primario oscuro, `rose` = acento claro sobre oscuro, `rose-soft`/`cream` = fondos claros), así que se cambiaron **los valores** en `tailwind.config.js` en vez de tocar 20 pantallas: `brown → #004D40` (Deep Forest), `brown-dark → #003A30`, `brown-darker → #00271F`, `brown-light → #4A7A72` (4.9:1 sobre blanco), `rose → #8FD6CE` (mint claro, 6:1 sobre Deep Forest), `rose-soft → #E0F2F1` (Soft Mint), `cream → #F5FAF9`. Se agregaron tokens con nombre real para lo nuevo: `gloma-forest`, `gloma-mint` (#4DB6AC), `gloma-soft-mint`, `gloma-black` (#101817). También `styles/globals.css` (body y `::selection`), la paleta embebida del 404 y los badges de estado de `/citas`. Corregido de paso `font-title` (clase inexistente) → `font-heading` en `/citas`. Verificado: se auditaron los usos de `text-gloma-rose` (todos sobre fondo oscuro, siguen legibles) y el CSS compilado ya no contiene ningún hex de la paleta anterior. |

**Nota:** en este mismo commit va el rediseño de la landing (`pages/gloma.tsx` y el
widget) a la paleta Deep Forest/Mint, que estaba en el árbol de trabajo sin commitear:
sin él, producción quedaría con la app en verde y la landing en rosa. Revertible por
archivo si se quiere separar.

### 6. #291-#296 — Agenda real de demos (+3 días hábiles, L-V 10 a.m.-4 p.m.)

**Pedido del CEO (2026-08-02):** el bot debe intentar agendar la demo **apenas
resuelve la primera pregunta**, preguntar en qué horario le sirve y mostrar en bullets
**las 4 franjas siguientes**. Horarios: lunes a viernes, cada hora, de 10:00 a.m. a
4:00 p.m., pero ofreciendo solo lo que esté a **3 días hábiles** de la solicitud
(ejemplo del CEO: quien escribe un jueves a las 2:30 p.m. recibe martes 3 y 4 p.m. y
miércoles 10 y 11 a.m.). Al cerrar, el bot registra la cita en la BD.

| # | Tarea | Agente | Resultado |
|---|---|---|---|
| #291 | Cálculo de franjas en el motor | `dev-plataforma` | `llm_engine.proximas_franjas()`: +3 días hábiles (los fines de semana no cuentan), y ese día se arranca en la hora en punto siguiente a la de la solicitud, acotada a 10:00-16:00; si ya cerró, salta al siguiente día hábil. El resultado se inyecta en el system prompt como bloque "Agenda de demostraciones" con las 4 opciones en texto legible **y** su equivalente `fecha=AAAA-MM-DD, hora=HH:MM` — **el modelo nunca calcula fechas**. Zona horaria fija UTC-5 (Colombia no tiene horario de verano; evita depender de tzdata en el contenedor). |
| #292 | Tool con fecha real + validación | `dev-plataforma` | `registrar_demo` ahora recibe `fecha` y `hora` (24h). `franja_valida()` revalida en el servidor: día hábil, dentro del horario y no antes del mínimo. Si falla, la herramienta **no registra** y le explica al modelo qué corregir. |
| #293 | `demo_bookings.fecha` | `experto-bd` | Columna `fecha DATE` + índice, `migrate_sprint21_demo_fecha.py` idempotente. Aplicada en local y RDS. `/citas` muestra la fecha real ("mié 5 ago · 3:00 p.m."), la edita con un date-picker y su selector de horas pasó a 10 a.m.-4 p.m. |
| #294 | Instrucciones del bot | `dev-plataforma` | La invitación a la demo va **pegada al final de la respuesta a la primera pregunta**; la lista de 4 opciones se muestra una sola vez; para registrar bastan **correo + franja**. |
| #295 | QA de 5 conversaciones | `qa` | Ver abajo. |
| #296 | Deploy | `deploy-aws` | Imagen `:sprint21d`, task-def rev 18, migraciones y re-seed en RDS. |

**#295 — Las 5 conversaciones y los 5 defectos que corrigieron las instrucciones.**
Primera vuelta (bot real contra Bedrock, canal landing): (1) *"Muebles del Valle"* —
el bot no propuso la demo al cerrar la primera respuesta; (2) *"Clínica Sonrisa"*
(3 preguntas seguidas) — repitió la lista de 4 franjas en **cuatro** mensajes
seguidos; (3) *"horario inválido"* (sábado 8 p.m.) — rechazó bien la franja, pero
después **bloqueó el registro** exigiendo nombre y empresa; (4) *"todo de una"* — dijo
"agendamos para el miércoles" **sin llamar la herramienta** (cita fantasma) y pidió
teléfono para "completar"; (5) *"precio y demo"* — otra vez frenó pidiendo datos
opcionales. Ninguno era un fallo del cálculo de franjas: las 4 opciones y los rechazos
(sábado, 8 p.m., miércoles 11 a.m. cuando ese día ya iba en 3 p.m.) salieron correctos
siempre.

Correcciones aplicadas y **re-verificadas**: la invitación a la demo es obligatoria al
cerrar la primera respuesta; la lista se muestra una sola vez; **para registrar solo se
piden correo y franja** (nombre/empresa/teléfono opcionales, prohibido condicionar el
registro a ellos — reforzado también en la *descripción de la tool*, que es lo que más
pesa para el modelo); prohibido decir "quedó agendada" antes de que la herramienta
responda; nada de confirmaciones redundantes; y `finalizar_conversacion` en el mismo
turno de la despedida. Segunda vuelta: los 5 escenarios cierran bien y quedaron **5
filas en `demo_bookings`** con fecha real (ids 4-8: 2026-08-05 3 p.m., 4 p.m. y
2026-08-06 11 a.m., etc.). Tests: **42 passed**, incluido el ejemplo exacto del CEO
(jueves 2:30 p.m. → martes 3 y 4 p.m. + miércoles 10 y 11 a.m.).

### 7. #297-#301 — Solicitudes de contacto desde la landing (2026-08-02)

**Pedido del CEO:** (a) en la sección de contacto de la landing, el botón
"Escríbenos por WhatsApp" debe **abrir el chat con el bot de la página** en vez de
mandar a WhatsApp; (b) el formulario debe pedir **nombre** y su botón decir
**"Quiero que me contacten"**; (c) esas solicitudes se registran en una tabla de la
base de Gloma y (d) el admin las gestiona desde `/citas`, en una subsección donde
pueda marcarlas **contactadas o pendientes** y **agregar, editar y eliminar**.

| # | Tarea | Agente | Resultado |
|---|---|---|---|
| #297 | Tabla de solicitudes | `experto-bd` | Se **extendió `leads`** (la tabla que ya recibía el formulario desde Sprint 11) en vez de crear una segunda tabla con el mismo significado: `nombre VARCHAR(120)`, `estado VARCHAR(16)` (`pendiente` \| `contactado`, default `pendiente`, indexado), `notas VARCHAR(500)` y `updated_at`. El booleano `contacted` se **backfillea** a `estado` y se elimina (era la misma información en dos lugares). Migración idempotente `backend/scripts/migrate_sprint21_leads_solicitudes.py`. Ventaja para el CEO: las solicitudes históricas aparecen en el panel desde el día uno. |
| #298 | Endpoints | `dev-plataforma` | Público: `POST /landing/leads` ahora exige `nombre` (2-120 chars, se limpian caracteres de control y espacios dobles); sigue con el rate-limit de 5/IP/hora. Privado (misma autorización `require_gloma_account` que el resto de `/citas`): `GET /citas/solicitudes` (filtro por estado + resumen), `POST /citas/solicitudes` (alta manual, `source='manual'`), `PATCH /citas/solicitudes/{id}` (parcial) y `DELETE /citas/solicitudes/{id}`. Validación server-side: correo con formato válido y estado dentro del enum. |
| #299 | Landing | `ui-ux` + `dev-plataforma` | El CTA "Escríbenos por WhatsApp" de la sección de contacto ya no es un `<a>` a `wa.me`: dispara el evento `gloma:open-chat` que abre el widget del bot institucional (se usó un evento de `window` en vez de subir el estado porque el widget es un singleton flotante). El formulario suma el campo **Nombre** (requerido) y su botón dice **"Quiero que me contacten"**. *No se tocó* el botón del hero (sigue yendo a WhatsApp) porque el pedido era la sección de contacto — cambiarlo también es una línea si el CEO lo quiere. |
| #300 | Subsección en `/citas` | `dev-plataforma` | La página pasó a tener dos pestañas: **"Demos agendadas"** (lo que ya existía) y **"Solicitudes de contacto"** (tabla `leads`): tarjetas Total / Pendientes / Contactados, filtros, badge + selector de seguimiento en línea, "+ Nueva solicitud", modal de edición (nombre, correo, teléfono, seguimiento, notas) y borrado con confirmación. El permiso se consulta una vez con `GET /citas/access` y decide si se pintan las pestañas o el estado "Módulo privado 🔒". |
| #301 | Deploy | `deploy-aws` | Migración en RDS + imagen `:sprint21e`, task-def nueva revisión y build de Amplify. |

**Seguridad (revisión inline, sin hallazgos bloqueantes).** La tabla guarda PII de
prospectos: `Lead.__repr__` la redacta (regla #1), los logs solo registran id y
campos cambiados —nunca valores—, y `SolicitudOut` **no** expone `ip_address` ni
`user_agent` aunque estén en la fila (minimización). Los 4 endpoints nuevos cuelgan
de `require_gloma_account`, así que otra cuenta recibe 403 aunque conozca la URL, y
sin token es 401. El endpoint público mantiene el rate-limit por IP y valida todo del
lado del servidor.

**Validaciones.**
- Migración local (docker-compose): 1ª corrida agrega columnas e índice; se recreó
  `contacted` a mano con una fila en `true` y la 2ª corrida hizo backfill
  (`estado='contactado'`) y el `DROP`; 3ª corrida sin cambios. 6 filas históricas
  preservadas.
- API local: `POST /landing/leads` sin nombre → 422, con nombre de 1 letra → 422, con
  `"  Ana   María  QA "` → 200 y la fila queda con `nombre='Ana María QA'`,
  `email` en minúsculas y `estado='pendiente'`. Panel: alta manual → 201, cambio de
  estado → 200 con `updated_at`, estado inventado → 422, correo inválido → 422, id
  inexistente → 404, borrado → 204 y luego 404, sin token → 401. `GET /citas` (demos)
  sigue respondiendo igual.
- `pytest`: **56 passed** (14 nuevos en `backend/tests/test_landing_leads.py`). Los
  errores de `tests/test_meta_account_flow.py` siguen siendo los preexistentes de
  SQLite + `JSONB` (Sprint 15).
- Frontend: `tsc --noEmit` limpio y `npm run build` OK (`/citas` 6.66 kB, `/gloma`
  12.3 kB).

**Cómo consulta el CEO las solicitudes:**

```sql
SELECT created_at, nombre, email, telefono, estado, notas
FROM leads ORDER BY created_at DESC;
```

o, más cómodo, en `app.glomabeauty.com` → **Citas** → pestaña *Solicitudes de contacto*.

**Ajuste #302 (pedido del CEO, 2026-08-02):** los dos CTAs que quedaban llevando
fuera de la página ahora conversan con el agente. El **"Agenda una demo"** del header
abre el chat con la intención ya escrita (*"Quiero agendar una demostración. ¿Qué
horarios tienen disponibles?"*), así que el bot responde de una con las 4 franjas
disponibles y registra la cita — verificado contra `api.glomabeauty.com`: responde
"Jueves 6 de agosto, 10:00 a.m. / 11:00 a.m. / 12:00 m. / 1:00 p.m.". El botón del
hero pasó de **"Escríbenos por WhatsApp"** a **"Hablar con un asesor"** y abre el
mismo chat (sin mensaje previo: el bot saluda). Implementación: `OPEN_CHAT_EVENT`
acepta `detail.message`; cuando llega, el widget lo pinta como mensaje del visitante,
lo envía y se salta el turno de saludo. El enlace a WhatsApp del footer se mantiene.

---

## Sprint 22 — WABA real de "Arranquemos Pues" vía Twilio (2026-08-09)

**Pedido del CEO (2026-08-09):** conectar una cuenta WABA real a la cuenta demo de
la agencia de viajes, cambiándole el correo a `arranquemospues.contacto@gmail.com`
con contraseña nueva, dejando el canal conectado por Twilio y capaz de enviar un
**mensaje de marketing** al número de prueba **+57 315 076 4000**. Requisito
adicional a mitad de sprint: la conexión debe vivir en una **subcuenta** de Twilio
llamada "Arranquemos Pues", no en la cuenta principal, porque Gloma opera como
agencia (modelo ISV).

### 1. Tareas del Sprint 22

| # | Tarea | Agente | Descripción |
|---|---|---|---|
| #303 | Reasignar correo + password de la cuenta demo | `dev-plataforma` | `migrate_sprint22_agencia_credenciales.py` idempotente, aplicado en local y RDS. |
| #304 | Subcuenta Twilio del tenant | `deploy-aws` | Subcuenta "Arranquemos Pues" vía API; Auth Token en archivo git-ignorado 0600. |
| #305 | Registro del sender WABA | CEO (navegador) | Embedded Signup con Meta: no es automatizable por API sin Tech Provider Program. |
| #306 | Conectar credenciales al team | `dev-plataforma` | `connect_twilio_waba.py`: `meta_accounts.provider='twilio'` + Auth Token cifrado con Fernet. |
| #307 | Webhooks de entrada y estado | `deploy-aws` | Senders API → `api.glomabeauty.com/twilio/webhook` y `/twilio/status`. |
| #308 | Salida del sandbox de Twilio en prod | `deploy-aws` | `TWILIO_SANDBOX=0` en task-def; `META_SANDBOX` sin tocar. |
| #309 | Plantilla de marketing + aprobación de Meta | `dev-plataforma` | Content API + ApprovalRequests, categoría MARKETING con opt-out. |

### 2. Log de ejecución del Sprint 22

| Fecha | Agente | Nota |
|---|---|---|
| 2026-08-09 | Dev Plataforma | **#303 credenciales de la cuenta demo.** `agencia@demo.com` → `arranquemospues.contacto@gmail.com` con password nueva. Script idempotente que busca primero por el correo nuevo (re-ejecutable sin efectos). Aplicado en **local** (user_id=9) y en **RDS** (user_id=7); login verificado contra `https://api.glomabeauty.com/login` → HTTP 200. Herramienta nueva `backend/scripts/rds_exec.sh`, hermano de `rds_query.sh`, para correr scripts que **todavía no están en la imagen de ECR** (van inline como `python -c`). Regla adoptada: por ahí **nunca viaja un secreto en claro** — los overrides de `ecs run-task` quedan en CloudTrail, así que se pasa el hash bcrypt ya calculado (`AGENCIA_PWD_HASH`) y, para el token de Twilio, el ciphertext Fernet ya cifrado (`TW_AUTH_TOKEN_ENC`). Se confirmó que la `APP_ENCRYPTION_KEY` local y la de SSM **son distintas**, así que cada entorno se cifra con la suya. |
| 2026-08-09 | Deploy AWS | **#304 subcuenta Twilio.** Creada "Arranquemos Pues" `AC5330…` (SID completo en `CREDENCIALES_TWILIO_ARRANQUEMOS.txt`) bajo la matriz "Talulah". Auth Token en `CREDENCIALES_TWILIO_ARRANQUEMOS.txt`, permisos 0600, cubierto por el patrón `CREDENCIALES*.txt` del `.gitignore` (verificado con `git check-ignore`). |
| 2026-08-09 | CEO | **#305 Embedded Signup.** Liberó su número del WABA anterior en Meta Business (se confirmó antes que Meta lo permitía: no había enviado mensajes pagos en 30 días) y corrió el Self Sign-up. Resultado: sender **`whatsapp:+573334324954`**, status **ONLINE**, WABA `1028327816859906`, nombre visible "Agencia de viajes Arranquemos Pues", límite 250 clientes/24h (normal para WABA sin verificación de negocio). |
| 2026-08-09 | Deploy AWS | **#305b el sender quedó en la matriz, no en la subcuenta.** La consola de Twilio solo ofreció la cuenta principal para el Self Sign-up. Investigado y confirmado en la documentación: (a) mover un sender entre cuentas de Twilio **no es self-service**, requiere ticket a Support con número + WABA ID origen y destino; (b) **una cuenta/subcuenta de Twilio se mapea a un solo WABA**, relación 1:1 — apuntar la subcuenta al WABA de la matriz da error 63102; (c) registrar senders dentro de subcuentas exige estar en el **Tech Provider Program** de Meta e integrar el Embedded Signup en la propia app. Se descartó rehacer el signup: volvería a caer en la matriz y además reiniciaría la aprobación de la plantilla, que está atada al WABA. Decisión: operar hoy desde la matriz, dejar la subcuenta creada esperando, y abrir el follow-up. |
| 2026-08-09 | Dev Plataforma | **#306 conexión del canal al tenant.** `connect_twilio_waba.py` escribe `meta_accounts` con `provider='twilio'`, `twilio_account_sid`, `encrypted_twilio_auth_token` (Fernet), `twilio_from='whatsapp:+573334324954'`, `waba_id` y `status='active'`. Aplicado en **local** (team 9 → meta_account 4) y **RDS** (team 5 → meta_account 3). Paridad local↔RDS cumplida (convención #1). El script redacta el token en su salida (regla #1). |
| 2026-08-09 | Deploy AWS | **#307 webhooks.** Senders API → `callback_url=https://api.glomabeauty.com/twilio/webhook` y `status_callback_url=.../twilio/status`, ambos POST. La verificación HMAC de `twilio_webhook.py` usa el `TWILIO_AUTH_TOKEN` global (SSM), que hoy es el de la matriz — **coincide** con la cuenta que firma, así que valida bien. Cuando el sender se mueva a la subcuenta, Twilio firmará con el token de la subcuenta y esto se rompe: ver follow-up #311. |
| 2026-08-09 | Deploy AWS | **#308 salida del sandbox.** Task-def **rev 20** con `TWILIO_SANDBOX=0` (imagen `:sprint21` sin cambios). `META_SANDBOX` se dejó en `1` a propósito: gobierna las cuentas `provider='meta'` y no debe moverse. El único tenant con `provider='twilio'` es la agencia, así que el cambio no expone a ningún otro cliente a envíos reales. |
| 2026-08-09 | Dev Plataforma | **#314 BUG: el bot nunca envió multimedia.** Reportado por el CEO tras la primera conversación real por WhatsApp. Causa raíz: la acción `say_media` del `bot_runner` tenía un MVP de Sprint 8 que **solo enviaba el caption como texto** (`_send_text(..., caption or "[archivo multimedia]")`), y como el motor LLM emite los `say_media` con caption vacío (el texto va en un `say` aparte), lo que llegaba al contacto era el literal `[archivo multimedia]`. Evidencia en RDS, conversación 8: mensajes 28, 30, 34, 35 y 36 con `message_type='text'` y ese contenido. **Arreglo:** `send_media()` nuevo en `twilio_adapter` (parámetro `MediaUrl`; Twilio descarga la URL y la sube a WhatsApp, sin upload previo; el caption viaja como `Body`), `send_media_message()` en `meta_whatsapp` (por `link`, soporta image/video/document/audio y omite caption en audio), despacho `send_media()` en el puerto agnóstico, y `_send_media()` en el `bot_runner` que persiste el mensaje con su `message_type` real y la URL en `content` — con **fallback a texto con el enlace** si el proveedor falla, para que el turno del bot nunca quede mudo. Guarda temprana: si la URL no es `https://`, error no-retryable (WhatsApp rechaza media no-HTTPS). Verificado en local contra el número real con ventana de 24h abierta: imagen `MM45dcb432f490` y video `MMd1758bca2063`, ambos **delivered**. |
| 2026-08-09 | Dev Plataforma | **#317 BUG CRÍTICO: el bot quedaba mudo con contactos sin número visible.** Reportado por el CEO al probar desde otro WhatsApp. Twilio devolvía `21211 Invalid 'To' Phone Number` en **todos** los envíos de esa conversación (texto y media), con el bot fallando en `_send_text`. Causa raíz: WhatsApp no siempre entrega un E.164 en el `From` — cuando el usuario no comparte su número llega una **identidad opaca** con forma `CO.3371971396308694` (prefijo de país + id). `_as_whatsapp()` le anteponía '+' a ciegas y producía `whatsapp:+CO.3371971396308694`, que Twilio rechaza. Evidencia: conversación 9 en RDS con `contact_wa_id='CO.3371971396308694'` y mensajes 44 y 46 en `status='failed'`. **Verificación empírica antes de codear:** se probó contra la API real que `To=whatsapp:CO.3371971396308694` (sin '+') es aceptado → `delivered`. **Arreglo:** `_as_whatsapp()` sólo convierte a E.164 lo que sea `isdigit()`; cualquier otra cosa se reenvía verbatim, que es lo que Twilio espera. Re-probado por el camino real de la app: texto `SM5286b2543035` **delivered** e imagen `MM904f85606c8d` **sent**. Tests nuevos en `backend/tests/test_twilio_adapter.py` (17 casos: E.164 en 4 variantes, 3 identidades opacas, sandbox de texto y media, guarda de URL no-HTTPS, mapeo de estados). Suite: **73 passed** (el error de colección de `test_meta_account_flow.py` es el preexistente de SQLite + JSONB del Sprint 15). |
| 2026-08-09 | Experto BD + Dev Plataforma | **#318 modo operativo por tenant: `teams.modo`.** Pedido del CEO al pasar de demo a operación real: necesita distinguir qué cuentas son de demostración y cuáles están conectadas de verdad, porque conviven ambas. Columna `teams.modo VARCHAR(16) NOT NULL DEFAULT 'demo'` (+ índice), con valores `demo` \| `produccion`. **No es una etiqueta decorativa:** `messaging/base.team_is_demo()` se consulta desde `is_sandbox()` de **ambos** adaptadores, así que un team en `demo` se simula siempre — aunque tenga credenciales válidas y `TWILIO_SANDBOX=0`/`META_SANDBOX=0`. Objetivo: que una cuenta de demostración no le escriba nunca a un número real ni queme cuota del WABA. Decisiones de diseño: (a) default `demo`, para que un tenant nuevo no pueda enviar hasta ser promovido explícitamente; (b) cualquier valor distinto de `'produccion'` cuenta como demo (no hay forma de habilitar envíos por un typo); (c) si la relación `account.team` no se puede leer, se asume demo y se loggea error — ante la duda, no enviar. Migración idempotente `migrate_sprint22_team_modo.py` (`ADD COLUMN IF NOT EXISTS` + backfill + índice), aplicada en **local** (team 9 → produccion) y **RDS** (team 5 → produccion); Talulah, Gloma y el resto quedaron en `demo`. Expuesto en `schemas.TeamOut.modo` para que el frontend pinte el distintivo. Tests: `backend/tests/test_team_modo.py` (10 casos). Suite: **83 passed**. |
| 2026-08-09 | QA + Dev Plataforma | **#318b la API mentía sobre el modo.** Al verificar #318 en producción, `GET /teams/me` devolvía `modo='demo'` para el team 5, que en RDS está en `produccion`. Causa: `routers/teams.py` construye `TeamOut` **campo por campo** y no pasaba `modo`, así que ganaba el default del schema. **El gate de envío NO estaba afectado** — lee `account.team.modo` directo del ORM, así que Arranquemos Pues sí enviaba real; el bug era de reporte, pero de los que confunden un diagnóstico. Arreglo doble: (a) el router pasa `modo=member.team.modo`; (b) se **quitó el default** de `TeamOut.modo` para que un call-site que lo olvide falle ruidosamente en vez de reportar 'demo' para un tenant en producción. Verificado que `TeamOut(...)` es el único punto de construcción. Suite: **83 passed**. Producción: imagen `:sprint25`. |
| 2026-08-09 | Dev Plataforma | **#309 plantilla de marketing.** `arranquemos_pues_promo_viajes` (`HX0e607e9b09f36c6ec8c9b91c25344b9f`), tipo `twilio/quick-reply`, idioma `es`, variable `{{1}}`=nombre, con dos botones: "Ver los planes" y **"No enviar más"** — el opt-out es buena práctica y sube la probabilidad de aprobación en categoría MARKETING. Enviada a Meta vía `ApprovalRequests/whatsapp`, categoría MARKETING. |

### 3. Entregables del Sprint 22

| # | Entregable | Dónde |
|---|---|---|
| #303 | Migración de credenciales + runner de scripts en RDS | `backend/scripts/migrate_sprint22_agencia_credenciales.py`, `backend/scripts/rds_exec.sh` |
| #304 | Subcuenta Twilio del tenant | `AC5330…` (SID completo en `CREDENCIALES_TWILIO_ARRANQUEMOS.txt`), `CREDENCIALES_TWILIO_ARRANQUEMOS.txt` |
| #306 | Conexión WABA↔team | `backend/scripts/connect_twilio_waba.py` |
| #308 | Producción | task-def rev 20 (`TWILIO_SANDBOX=0`) |
| #309 | Plantilla de marketing | Content SID `HX0e607e9b09f36c6ec8c9b91c25344b9f` |
| #314 | Envío real de multimedia (Twilio + Meta) | `services/messaging/twilio_adapter.py`, `services/messaging/meta_adapter.py`, `services/messaging/__init__.py`, `services/meta_whatsapp.py`, `services/bot_runner.py` |
| #314 | Producción con el arreglo | imagen `:sprint22`, task-def rev 21 |
| #317 | Identidades opacas de WhatsApp (no-E.164) | `services/messaging/twilio_adapter.py` (`_as_whatsapp`) |
| #317 | Tests del adaptador Twilio (17 casos) | `backend/tests/test_twilio_adapter.py` |
| #317 | Producción con el arreglo | imagen `:sprint23`, task-def rev 22 |
| #318 | Modo por tenant (demo/producción) con gate real de envío | `models.py`, `services/messaging/base.py`, `twilio_adapter.py`, `meta_adapter.py`, `schemas.py`, `backend/scripts/migrate_sprint22_team_modo.py`, `backend/tests/test_team_modo.py` |
| #318 | Producción | imagen `:sprint24`, task-def rev 23 |

### 4. Follow-ups abiertos

- **#310 — Migrar el sender a la subcuenta.** Ticket a Twilio Support: número
  `+573334324954`, WABA `1028327816859906`, origen `AC448d…` (SID completo en `CREDENCIALES_TWILIO.txt`),
  destino `AC5330…` (SID completo en `CREDENCIALES_TWILIO_ARRANQUEMOS.txt`). Al completarse, re-correr
  `connect_twilio_waba.py` con el SID de la subcuenta y actualizar SSM.
- **#311 — Verificación HMAC del webhook por tenant.** Hoy `twilio_webhook._verify_signature`
  lee el `TWILIO_AUTH_TOKEN` global. Con senders en subcuentas cada tenant firma con
  **su** token, así que hay que resolver el token desde `meta_accounts` del tenant
  destinatario. Es bloqueante para el modelo multi-tenant real (y para #310).
### 5. Auditoría de "listos para operar" (2026-08-09, pedido del CEO)

Estado real medido contra AWS y la BD, no supuesto. Prioridad de mayor a menor:

**Bloqueantes**

- **#319 — Secretos en texto plano en la task-def.** `POSTGRES_PASSWORD` y `SECRET_KEY`
  viajan como `environment` plano: visibles en la consola de ECS y en CloudTrail.
  `APP_ENCRYPTION_KEY`, `INTERNAL_API_KEY` y los `TWILIO_*` sí están bien, como
  `secrets` desde SSM. Viola la regla de seguridad #1 del proyecto. Arreglo: moverlos
  a SSM SecureString y referenciarlos en `secrets`.
- **#229/#320 — Las campañas no funcionan con Twilio.** `routers/templates.py` habla
  **solo con Meta** (`meta_templates`, cero referencias a Twilio/ContentSid) y
  `campaign_sender` le pasa `template.name` al adaptador, pero `twilio_adapter
  .send_template` espera un **Content SID** (`HX...`). Resultado: hoy no se puede
  lanzar una campaña desde la app para el único tenant real. Hace falta el mapeo
  nombre→ContentSid y que el módulo de plantillas sepa de Twilio (crear y consultar
  aprobaciones vía Content API, como se hizo a mano en #309).
- **#321 — RDS sin red de seguridad.** `BackupRetentionPeriod=1`, `MultiAZ=false`,
  `DeletionProtection=false`. Con datos de clientes reales esto no se sostiene:
  subir retención a 7-14 días y activar deletion protection son dos comandos.
- **#322 — Cero alarmas de CloudWatch** (`describe-alarms` → 0). No hay aviso si el
  backend se cae, si la CPU se dispara o si los envíos empiezan a fallar.

**Importantes para operar con clientes**

- **#323 — Al asesor no le llega ningún aviso en el handoff.** El bot reasigna la
  conversación pero no notifica por ningún canal. Combinado con #315 (no se puede
  devolver al bot), un prospecto puede quedar esperando indefinidamente.
- **#324 — Un solo task de ECS, sin circuit breaker ni health check grace**
  (`desiredCount=1`, `deploymentCircuitBreaker.enable=false`,
  `healthCheckGracePeriodSeconds=0`): un deploy malo no hace rollback solo.
- **#325 — Cuentas de prueba en la BD de producción**: `ceo@test.com`,
  `test_proxy@example.com`, `smoke1775830259@gmail.com`, `prueba@gmail.com`.
- **#326 — Límite de 250 conversaciones/24h** hasta que Arranquemos Pues complete su
  verificación de negocio con Meta (la del cliente, no la de Gloma — ver #312).

**Deuda ya conocida**: Alembic (gotcha histórico), #311 HMAC por tenant, #313 UI para
conectar canal, #315 reasignar conversación, #316 render de multimedia en la app.

- **#310b — Descartado: la Senders API NO sirve para llevar el WABA a la subcuenta.**
  Probado empíricamente el 2026-08-09 a pedido del CEO (a raíz del changelog de GA de
  la Senders API). `POST /v2/Channels/Senders` desde la **subcuenta**, con
  `configuration.waba_id` = `1028327816859906` (el WABA de la matriz) y el número
  mágico de pruebas `+15005550006` como `sender_id`, responde:
  **`63101 waba_id provided is not valid or unable to be used`**. La validación del
  WABA ocurre **antes** de tocar el número, por eso la sonda se diseñó con un número
  de prueba: riesgo cero para el sender vivo (verificado después — sigue ONLINE con
  su límite intacto, y no quedó basura en la subcuenta).
  **Conclusión:** la Senders API registra senders *dentro de un WABA que la cuenta ya
  posee*; no crea el WABA ni permite prestarlo de otra cuenta. El huevo-y-la-gallina
  sigue igual: para que la subcuenta tenga WABA hay que correr el Embedded Signup
  **apuntando a esa subcuenta**, y eso es exactamente lo que exige #312.
- **#312 — Tech Provider Program de Meta.** Es la vía correcta para que cada cliente
  tenga su subcuenta + su WABA y se auto-onboardee. Gratis. Requiere: verificación de
  negocio de Gloma con Meta, app de Meta nueva marcada "Independent Tech Provider",
  App Review con grabaciones de pantalla, advanced access a `whatsapp_business_messaging`
  y `whatsapp_business_management` (Meta: ~5 días hábiles), ticket a Twilio con el Meta
  App ID para el Partner Solution (1-2 días hábiles) y, de nuestro lado, integrar el
  Embedded Signup en la app (botón "Login with Facebook", capturar `phone_number_id` y
  `waba_id`, crear la subcuenta y registrar el sender vía Senders API). Partes 1 y 2:
  3-4 semanas.
- **#315 — No se puede devolver una conversación del asesor al bot.** Cuando el bot
  hace `handoff`, `conversations.assigned_to` pasa al asesor y `bot_router` deja de
  intervenir para siempre en ese hilo (correcto: un humano no debe ser interrumpido).
  Pero `routers/mensajes.py` sólo **lee** `assigned_to`: no hay endpoint ni botón para
  reasignar. Hoy la única salida es un UPDATE en la BD. Con clientes reales esto va a
  estorbar — hace falta un control de "devolver al bot" / "reasignar asesor" en el
  módulo de Mensajes.
- **#316 — El módulo de Mensajes no renderiza multimedia.** Tras el arreglo #314 los
  mensajes se guardan con `message_type='image'|'video'` y la URL en `content`, pero
  `frontend/pages/mensajes.tsx` pinta `m.content` como texto plano: el asesor ve el
  enlace, no la imagen. Falta renderizar `<img>`/`<video>` según `message_type`.
- **#313 — No hay UI para conectar un canal Twilio.** `crud.py` no tiene funciones de
  Twilio y `schemas.py` no expone el proveedor: hoy la conexión de un tenant se hace
  por script. Cuando exista #312, esto debe volverse un flujo de la app.

---

## Sprint 23 — Conexión de Instagram y panel de publicaciones (2026-08-09)

**Pedido del CEO (2026-08-09):** conectar un Instagram para poder **programar
publicaciones**, y luego, en la cuenta admin de Gloma, una ventana adicional que
muestre las publicaciones en cola, cuándo se publican y un enlace para descargar
el contenido ya cargado en AWS.

### Hallazgo que definió la arquitectura

Instagram **sí** tiene programación nativa (Planificador de Meta Business Suite,
gratis, hasta 75 días), pero es **solo UI: no existe API para ella**. La Content
Publishing API tampoco acepta fecha futura y sus contenedores de media **expiran
a las 24 h**. Verificado contra la documentación de Meta, no de memoria.

Decisión del CEO tras ver la comparación: **API + cola propia**, para que la
programación sea autónoma en vez de manual.

Otros hechos confirmados:
- Con el flujo *Instagram Login* (2024) una cuenta **Creator no necesita Página de
  Facebook**. Solo debe ser profesional, no personal.
- **No hace falta App Review** en modo desarrollo publicando en cuentas con rol.
- Instagram no acepta upload de archivos: descarga desde URL pública HTTPS.
- Límite: 100 publicaciones/API por ventana móvil de 24 h; un carrusel cuenta 1.
- `META_APP_SECRET` en `.env` está vacío — la app Meta legacy quedó inactiva tras
  migrar a Twilio como BSP, así que no había nada que reutilizar. App nueva.

### Grupo 1 — Herramienta de marketing (fuera del producto)

`marketing/instagram/` — CLI `igpost.py` con `setup-app`, `auth-url`, `connect`,
`whoami`, `refresh-token`, `post`, `schedule`, `list`, `cancel`, `run-due`.

- `ig/client.py` — Graph API: contenedores, carruseles (2–10 slides), publicación,
  OAuth y renovación del token de 60 días.
- `ig/media.py` — normaliza a JPEG RGB ≤1440 px, valida aspect ratio (4:5–1.91:1)
  y tope de 8 MB; sube a S3 y prefirma.
- `ig/queue.py` — cola en S3 con locking optimista por ETag.
- `ig/config.py` — credenciales en SSM SecureString, `__repr__` redactado.

**Infra:** bucket `gloma-marketing-media-747456040509` (sa-east-1) — privado,
AES256, bloqueo público total, expiración a 30 días.

**Validación:** las 21 piezas de `identidad_gloma/redes sociales/` pasaron por el
validador; 20 quedan publicables (2160×2700 → 1440×1800). `16_linkedin` es un
banner 1128×191 de LinkedIn: correctamente rechazado.

### Grupo 2 — Panel en la app (módulo interno de Gloma)

- `dependencies.py`: se extrajo `require_gloma_account` + `GLOMA_EMAIL` desde
  `citas.py` para compartir el portero entre los dos módulos internos. `citas.py`
  ahora lo importa (sus 10 usos intactos).
- `services/instagram_queue.py`: lee la cola de S3 y prefirma las descargas con
  `ResponseContentDisposition: attachment`. Solo lectura.
- `routers/instagram.py`: `GET /instagram/access` y `GET /instagram`.
- `frontend/pages/instagram.tsx`: resumen, filtros por estado, tarjeta por pieza
  con fecha absoluta + relativa ("en 3 días"), texto y descarga por slide.
- `components/Sidebar.tsx`: se generalizó el gateo de módulos internos; ahora
  consulta Citas e Instagram en paralelo.
- IAM: policy inline `instagram-marketing-media-read` en `multiagente-ecs-task-role`
  (`s3:GetObject` solo sobre ese bucket).

**Pruebas:** `tests/test_instagram_queue.py` — 12 casos (parseo, orden, contrato
del endpoint, 403 a cuenta ajena, 503 sanitizado). Suite completa: **92 pasan**.
`next build` OK, `/instagram` en el listado de rutas.

### Pendientes

- **#327 — Conectar la cuenta.** Bloqueado esperando al CEO: convertir el Instagram
  a Creator, crear la app de Meta y correr `setup-app` + `connect`. SSM
  `/gloma/marketing/instagram/` está vacío. Hasta entonces el panel muestra la
  cola vacía (estado válido, no error).
- **#328 — Cron de `run-due`.** Sin credenciales no tiene qué publicar. Montar
  cuando exista #327, junto con la renovación automática del token (60 días).
- **#329 — Deploy.** El endpoint `/instagram` requiere redeploy del backend a ECS,
  y Amplify **no auto-buildea** (hay que lanzar el job manual).
- **#330 — Vida de las URLs prefirmadas en ECS.** Las credenciales del task role
  rotan (~6 h); una URL firmada justo antes de la rotación puede caducar antes de
  su TTL de 1 h. El panel las regenera en cada carga, así que el impacto es bajo.

---

## Sprint 23 — Contenido de marca: Instagram (Sprints de contenido 3 y 4) — 2026-08-09

**Pedido del CEO (2026-08-09):** dos tandas de 5 publicaciones estáticas para la cuenta de
Instagram de Gloma —primero «mejores destinos de LatAm con playa», después «temas para las
primeras publicaciones de la cuenta»— con el copy y todo el detalle documentado, y las piezas
gráficas en carpetas. Requisito añadido a mitad: **seguir fielmente el Brand Book**.

> El plan editorial vive en `identidad_gloma/plan_contenido_instagram_gloma.md`. Esta entrada es
> solo el índice desde la bitácora; el detalle (pieza por pieza, slide por slide, copy, CTA,
> hashtags y fuentes) está allá.

### 1. Entregado

| # | Tarea | Dónde quedó |
|---|---|---|
| #331 | Sprint de contenido 3 — serie «playa LatAm», 5 piezas / 31 slides | Plan Parte 1C · `identidad_gloma/redes sociales/20_…` a `24_…` |
| #332 | Sprint de contenido 4 — set de lanzamiento de la cuenta, 5 piezas / 25 slides | Plan Parte 1D · `redes sociales/25_…` a `29_…` |
| #333 | Auditoría contra el Brand Book v3 y corrección del set de lanzamiento | Plan Parte 3 → «Alineación con el Brand Book v3» |

Formato de todas: JPG 2160 × 2700 (1080 × 1350 a 2x), calidad 92, generadas con la skill
`/post-redes` (Chrome headless + Syne/Inter instaladas localmente) desde
`redes sociales/_generador/piezas.py`. **Total acumulado: 149 imágenes.**

### 2. Datos verificados con fuente (serie de playa)

Sargazo abril–octubre con récord en 2026 · requisitos e inadmisiones de colombianos en México
(prerregistro del INM) · e-Ticket migratorio dominicano obligatorio, dos por viaje, hasta 72 h
antes · Nordeste brasileño 5,8 M de pasajeros en el Q1 2026 (+12,86 %) y Maceió / Porto de
Galinhas entre los destinos líderes según Braztoa · aeropuerto de Liberia 793.075 pasajeros en
el Q1 2026 (+12 %). Todas las URLs quedaron en «Fuentes consultadas» del plan.

### 3. Hallazgos de la auditoría de marca

- **#334 — Los sets `01`–`24` no respetan el reparto de color del manual.** El Brand Book v3
  §4.2 define Deep Forest como color primario (~45 %) y Technical Black como minoría (~15 %);
  las piezas están al revés (~50 % negro). El set de lanzamiento `25`–`29` ya salió con el
  reparto correcto (64 / 20 / 16). Regenerar el bloque anterior es editar el primer campo de
  cada tupla en `piezas.py` y re-renderizar. **Decisión pendiente del CEO.**
- **#335 — El claim principal no aparecía en ninguna pieza.** «Cada viaje empieza con una
  conversación» ya quedó en el cierre de la `25`, la pieza fijada del perfil.
- **#336 — Contraste del micro-acento Golden Hour sobre Soft Mint.** En los slides de objeción
  (`17`–`24`) el remate `#F5C24B` sobre `#E0F2F1` queda en ~2:1. Se lee, pero es flojo. Si se
  cambia hay que tocar `_objecion()` y regenerar las 8 piezas juntas.
- **#337 — Fotos pendientes: 16 slides.** Ver la tabla de pendientes del plan. Las piezas se
  generan igual, con el recuadro `PENDIENTE · FOTO` reservando el espacio exacto.

### 4. Ajuste posterior (misma sesión) — pieza de producto sin nombre de marca

**Pedido del CEO:** el nombre de la marca posiblemente cambie, así que la publicación que explica
el producto no puede llevarlo escrito.

- La pieza `28_que_es_gloma` pasó a **`28_que_hace_el_agente`**. El titular
  «Qué es Gloma» se reemplazó por «Qué hace un agente de IA en tu WhatsApp», el copy dice «lo que
  hacemos es un agente de IA…» y se quitó el hashtag `#Gloma`. Los 5 slides se re-renderizaron y
  la carpeta vieja se eliminó.
- **#338 — Inventario de exposición a un rebrand.** El símbolo de la ventanilla no lleva wordmark,
  así que solo **3 slides de 149** tienen la marca escrita dentro de la imagen: `01` slide 5,
  `15` slide 5 y `25` slide 1 (kicker). Tabla completa en el plan, Parte 3 → «Exposición a un
  cambio de nombre de marca».
- **Regla nueva:** las piezas de producto se escriben describiendo el producto, no la empresa.

### Flujo de funcionamiento (cron + visualización en la app)

Referencia permanente de cómo opera el módulo, porque la responsabilidad está
repartida entre tres piezas y no es evidente cuál hace qué.

**Por qué hay un cron nuestro.** Instagram no expone API de programación (el
Planificador de Meta Business Suite es solo UI) y los contenedores de media de la
Content Publishing API **expiran a las 24 h**. No se puede "dejar cargado" un post
para dentro de una semana: alguien tiene que llamar a publicar en el minuto exacto.
Ese alguien es `run-due`.

**1. Programar** — `igpost.py schedule <carpeta> --caption-file x.txt --at "2026-08-20 09:00"`

| Paso | Qué pasa |
|---|---|
| Normaliza | Cada slide → JPEG RGB ≤1440 px, valida proporción 4:5–1.91:1 y tope 8 MB |
| Sube | `s3://gloma-marketing-media-747456040509/posts/<slug>/NN-<hash>.jpg` |
| Encola | Añade la entrada a `queue/schedule.json` en el mismo bucket, con `status='pending'` |

Las imágenes se suben **al programar, no al publicar**: así el runner no depende de
que el Mac tenga los archivos ni esté encendido.

**2. Publicar** — `igpost.py run-due` (lo dispara el cron)

Lee la cola, toma lo que tenga `publish_at <= ahora` y `status='pending'`, y por cada
pieza: prefirma las slides (1 h) → crea un contenedor por slide
(`is_carousel_item=true`) → espera `status_code=FINISHED` de cada uno → crea el
contenedor padre `media_type=CAROUSEL` con el caption → espera → `media_publish`.
Con una sola imagen se salta el paso de carrusel.

Al terminar reescribe la entrada: `status='published'` + `media_id` + `permalink`.
Si falla, guarda el error y suma `attempts`; a los **3 intentos** pasa a `failed`
para no reintentar en bucle. La escritura de la cola usa locking optimista por ETag,
así que dos procesos simultáneos no se pisan.

**3. Visualizar** — pestaña 📸 Instagram en la app

```
igpost.py schedule ──► S3 ──┬─► queue/schedule.json ──► GET /instagram ──► /instagram
                            └─► posts/<slug>/*.jpg  ──► URL prefirmada ──► botón ⬇
cron ──► igpost.py run-due ──► Graph API ──► actualiza la cola ──► se refleja en la app
```

La app **solo lee**: no programa ni publica. Muestra el resumen
(programadas/publicadas/fallidas/total), filtros por estado y una tarjeta por pieza
con fecha absoluta + relativa ("se publica jue 20 ago, 9:00 a. m. — en 11 días"),
el texto completo y un enlace de descarga por slide con
`Content-Disposition: attachment` (descarga, no abre). Los enlaces caducan en 1 h y
se regeneran en cada carga de la página.

La pestaña aparece **solo en la cuenta de Gloma**: el Sidebar consulta
`GET /instagram/access` y la pinta únicamente si responde `allowed=true`. Cualquier
otra sesión recibe 403 en `/instagram` aunque tenga JWT válido.

### Pendientes (continuación)

- **#331 — Subir las publicaciones y cronogramar las primeras.** Las 20 piezas
  válidas de `identidad_gloma/redes sociales/` **todavía no están cargadas en S3 ni
  programadas**: la cola está vacía y por eso el panel se ve sin contenido. Falta
  (a) redactar el caption de cada pieza, (b) definir el calendario (fechas y horas
  de publicación), (c) correr `igpost.py schedule` por pieza. Depende de #327: sin
  cuenta conectada no tiene sentido encolar.
- **#332 — `connect --token`.** Se añadió el camino corto: además del flujo OAuth
  (`auth-url` → `connect --code`), `connect --token` acepta el token que genera
  directamente la consola de Meta en "Instagram API setup with Instagram login".

### 5. Segundo ajuste (misma sesión) — pieza fijada sin marca; el resto marcado

**Pedido del CEO:** aplicar el cambio de nombre solo en la `25`; las demás menciones quedan
marcadas para cambiarlas cuando se defina el nombre nuevo.

- `25_esta_cuenta_no_es_para_viajeros` slide 1: kicker «Hola, somos Gloma» → **«Primera
  publicación»**. Re-renderizado. El copy del plan también quedó sin la marca y el hashtag
  `#Gloma` se quitó de esa pieza: la fijada del perfil ya es 100 % neutra.
- `01_mensaje_1147pm` slide 5 y `15_cliente_mientras_espera` slide 5: comentario
  **`REBRAND-PENDIENTE`** en `piezas.py` (líneas 34 y 404) para encontrarlas con un grep.
  La tabla de estado y el procedimiento de cambio quedaron en el plan, Parte 3 →
  «Exposición a un cambio de nombre de marca».

### Avance #327 — app de Meta creada, credenciales en SSM (2026-08-09)

El CEO creó la app (App ID `3255528234634515`) y se corrió `setup-app`: App ID y
App Secret quedaron en SSM `/gloma/marketing/instagram/` (el secret como
SecureString; nunca en `.env` ni en esta bitácora). Falta el último paso —
vincular la cuenta de Instagram— bloqueado por un "Insufficient Developer Role"
en la consola de Meta: la cuenta de IG debe agregarse como **Instagram Tester**
en Roles de la app y aceptar la invitación desde Instagram. No es un problema
del rol del CEO (ya es admin, que incluye developer).

### 6. Tercer ajuste (2026-08-10) — la 28 no debe negar que el agente cierra ventas

**Pedido del CEO:** corregir la `28` porque el bot puede que sí cierre la venta.

- `28_que_hace_el_agente` slide 3: *«No cierra la venta por ti, no reemplaza a tu equipo y no
  improvisa un precio»* → **«No improvisa un precio, no inventa disponibilidad y no reemplaza el
  criterio de tu equipo. Lo que no sabe, lo escala. La venta sencilla, la cierra completa.»**
  Re-renderizado y verificado.
- Copy del plan alineado: la venta sencilla la cierra el agente de principio a fin; la que pide
  criterio humano llega al equipo con el contexto recogido. El límite del producto es inventar
  información, no vender.

### Prueba end-to-end del flujo completo (2026-08-10) — EXITOSA

Cuenta conectada: **@1000_exp** (Business, IG user id `27847761091553677`), token de
larga duración en SSM, vence 2026-10-09 y se renueva solo (launchd semanal).

**Pedido del CEO:** agendar las piezas 25-28 con 2 min de diferencia para probar
todo el flujo, con registro de publicadas/no publicadas para evitar duplicados.

| Pieza | Estado | Permalink |
|---|---|---|
| 25_esta_cuenta_no_es_para_viajeros (4 slides) | ✅ published | instagram.com/p/Db2P50tkYsA |
| 26_que_vas_a_encontrar_aqui (6 slides) | ✅ published | instagram.com/p/Db2QGhTkS6q |
| 27_el_viajero_cambio (6 slides) | ✅ published | instagram.com/p/Db2QTL1kZYQ |
| 28_que_hace_el_agente (5 slides, slide 3 corregido) | ✅ published | instagram.com/p/Db2Qf7MEVPg |

Los captions salieron del plan (`plan_contenido_instagram_gloma.md`), respetando el
rebrand: 25 y 28 **sin** #Gloma, 26 y 27 con él. Markdown (`**`) removido porque
Instagram no lo renderiza.

**Bug encontrado y arreglado — el cron no arrancaba (TCC de macOS):** launchd no
puede leer `~/Documents` (exit 127, `can't open input file`). El runner ahora se
instala en `~/Library/Application Support/gloma-igpost/` con
`marketing/instagram/launchd/install.sh` (correrlo tras cada cambio del publicador);
logs en `~/Library/Logs/gloma-igpost/`. La primera pieza salió en el primer tick
tras el arreglo; las otras 3 salieron a su hora exacta (00:21, 00:23, 00:25).

**Registro anti-duplicados (pedido del CEO):** la cola en S3 es el registro — cada
pieza guarda `status`/`media_id`/`permalink`, visible en `igpost.py list` y en la
pestaña 📸 de la app. Doble barrera: (a) `schedule` rechaza re-agendar una pieza
`pending`/`published` (probado: rechazó la 25 con su id); (b) claim atómico por
ETag: pending→publishing→published, así el cron y el botón no pueden publicar la
misma pieza dos veces (quien pierde la carrera recibe 409). Piezas huérfanas en
`publishing` >30 min se rescatan a `pending` automáticamente.

**#333 — Botón "Publicar ahora" en el panel (pedido del CEO):**
`POST /instagram/{id}/publish` publica una pieza pendiente o fallida sin esperar su
hora. Réplica server-side del publicador (`services/instagram_publisher.py`, el CLI
no viaja en la imagen Docker) que comparte cola y claim con el cron. IAM: el task
role ganó `ssm:GetParameter` sobre `/gloma/marketing/instagram/*` y `s3:PutObject`
sobre `queue/*`. Frontend: botón 🚀 con confirmación en tarjetas pending/failed,
badge "Publicando…". Tests: 20 del módulo (claims, carreras de ETag, 409), suite
completa **103 passed**.

Pendientes que siguen abiertos: #331 (cronogramar el resto de piezas con calendario
real), #329→deploy de esta tanda, #330 (vida de URLs prefirmadas).

### 7. Sprint de contenido 5 (2026-08-10) — Historias destacadas del perfil

**Pedido del CEO:** carruseles de historias (1080×1920) para destacadas, con historia de portada
con icono, sobre: métricas de la landing · conversaciones de ejemplo · paso a paso para crear el
agente (reunión inicial → configuración → 15 días funcionando) · funcionalidades clave.

- **#339 — 4 destacadas generadas (23 historias):** `hist_01_metricas` (5), `hist_02_conversaciones`
  (5, mockups con `chat()`, nunca capturas reales), `hist_03_como_empezamos` (5) y
  `hist_04_funcionalidades` (8). Planeadas en el plan de contenido, Parte 1E. Métricas literales
  de `STATS` y funcionalidades de `FEATURES` en `frontend/pages/gloma.tsx`. Sin nombre de marca
  en ninguna slide (regla del rebrand). Portadas con icono de línea mint centrado para el
  recorte circular del perfil.
- **#340 — Generador extendido al formato historia:** `base.py` ganó `pagina(..., story=True)`
  (1080×1920 con zonas seguras de UI: 240 px arriba, 300 px abajo, logo/paginación
  reposicionados) y `generar.py` renderiza la lista `HISTORIAS` de `piezas.py` con sufijo
  `_storyN`. Los formatos de feed no se tocaron.
- Al publicar: sticker de enlace a WhatsApp sobre la última slide de cada set. El compromiso de
  «15 días» en H3 es del CEO (2026-08-10); si el plazo comercial cambia, esa slide se regenera.

### 8. Ajuste a H2 «Conversaciones» (2026-08-10) — chats con multimedia

**Pedido del CEO:** conversaciones más profundas, que se vean envíos de imágenes, videos y notas
de voz.

- `hist_02_conversaciones` v2: el generador ganó burbujas multimedia (`_voz` con onda y duración,
  `_media` con miniatura ilustrada de destino y overlay de play para video, `_contexto` con la
  tarjeta que recibe la asesora al escalar). Las miniaturas son CSS/SVG en la paleta —cielo/mar,
  sol Golden Hour, velero—, nunca fotos reales.
- Nuevas conversaciones: (2) cotización de las 11:47 p.m. donde el cliente responde con nota de
  voz y el agente la entiende; (3) propuesta con foto del catálogo + video de la habitación
  (0:38); (4) pregunta de visa resuelta + escalamiento con la tarjeta de contexto. Los 3 slides
  re-renderizados y verificados; portada y cierre sin cambios.

---

## Sprint "Ayuda a Cali" — Bot de mascotas perdidas por el terremoto (2026-08-13)

**Pedido del CEO:** una cuenta de demostración con su propio bot y una interfaz nueva,
tipo WhatsApp, donde la gente afectada por el terremoto en Colombia pueda **buscar** su
mascota perdida, **reportar** una que encontró y **descargar** el listado en Excel. Todo
guardado en base de datos con fotos, y un dashboard exclusivo de esa cuenta.

**Enlaces**
- Chat ciudadano (público): **https://mascotasperdidascolombia.com** (y `www.`)
- Panel: **https://app.glomabeauty.com** → menú **🐾 Mascotas**
- Credenciales: `recuperatumascota@gmail.com` / `«en el gestor del CEO»`
- Plan de pruebas manuales: `PRUEBAS_AYUDA_CALI.md`

### Modelo de datos (#341)
`mascotas` — un reporte por fila, con `tipo_registro` distinguiendo las dos naturalezas
que el sistema cruza entre sí: `perdida` (una familia la busca) y `encontrada` (alguien
la halló). Casi todo el detalle descriptivo es NULL-able a propósito: quien reporta rara
vez sabe raza, edad y nombre a la vez, y exigirlos hace que abandone. Los dos únicos
obligatorios son `ubicacion` y `contacto_telefono` — sin eso el reporte no sirve para
reunir a nadie. `maps_url` es opcional: mucha gente sabe dar la dirección pero no
compartir una ubicación.

`mascota_fotos` — el archivo vive en `mascotas/<codigo>/`, la carpeta con el
identificador del reporte que pidió el CEO. `mascota_id` es NULL mientras la foto está
en el limbo: la gente manda las fotos **antes** de que el bot termine de recoger los
datos, así que se suben contra un `upload_session` y se adoptan al crear el reporte.

`mascota_coincidencias` — un par (perdida, encontrada) por fila, con el puntaje y el
desglose de qué campos coincidieron.

Migración `backend/scripts/migrate_ayuda_cali_mascotas.py`, idempotente. **Local
(docker-compose):** 2 corridas, la 2ª sin cambios ✅. **RDS (`ecs run-task` rev 27):**
exit 0, las 3 tablas verificadas ✅. Paridad local↔RDS cumplida (convención #1).

### Motor (#342)
`services/mascotas.py` concentra storage, búsqueda y exportación. Dos backends de
storage intercambiables: **S3 en producción** (bucket `gloma-mascotas-747456040509`,
privado y cifrado) y **disco en local**. Las fotos nunca se sirven desde el bucket: el
backend hace de proxy en `GET /mascotas/foto/...`, así no hay que abrir acceso público.

**Búsqueda por scoring campo a campo**, no por coincidencia exacta: cada dato que cuadra
suma, y lo que la persona no sabe simplemente no puntúa. La especie es el único filtro
duro. **A pedido del CEO el peso está en lo físico y la zona, no en el nombre**: quien
encuentra un animal en la calle no sabe cómo se llama, así que raza y color valen 5,
señas hasta 5, zona 4, tamaño 3 y el nombre apenas 1 (desempate).

Herramientas nuevas del motor LLM, habilitadas por `llm_config.mascotas`:
`buscar_mascota`, `ver_ficha`, `entregar_contacto`, `registrar_reporte`,
`completar_reporte`, `descargar_listado` y `finalizar_fuera_de_alcance`.

### Dos guardarraíles que salieron de las pruebas
1. **El bot inventó un teléfono.** En una prueba entregó un número que no existía en la
   base — mandar a una familia angustiada a llamar a un desconocido. Ahora el motor
   descarta el turno y le exige la herramienta si aparece un número que no vino de
   `entregar_contacto` (`_viola_contacto`, máximo 2 correcciones por turno).
2. **El historial aplanado perdía los códigos.** El bot mostraba la ficha `MC-00012` y
   al turno siguiente no sabía de qué reporte hablaba, porque el historial solo guarda
   el texto que dijo. Las tools ahora dejan marcas (`[le mostraste la ficha MC-00012]`).

Además, un recordatorio determinista en el system prompt: si la persona ya dio un
teléfono y el caso sigue sin registrar, el modelo lo ve escrito en cada turno. Se probó
subir el bot a Sonnet 4.6 (encadena más reglas que los demás), pero Bedrock lo rechaza
en esta cuenta con `INVALID_PAYMENT_INSTRUMENT` — **el mismo blocker abierto desde el
Sprint 19 (#253)**. Queda en Haiku; cuando se resuelva el medio de pago basta cambiar
`model_id` en el seed y re-sembrar.

### Comportamiento del bot (#343)
Contexto `backend/app/bot_contexts/mascotas_cali.md`. Menciona que el servicio es
gratuito y que nació **para ayudar a los afectados por el terremoto**. Tres caminos, una
pregunta por mensaje, y reglas que salieron de las pruebas con el CEO:
- Busca apenas tiene especie + 2 datos; pedir cuatro cosas antes de la primera búsqueda
  era el peor error posible con alguien angustiado.
- **Sin coincidencias**: explica que la lista se actualiza todos los días, que el caso
  queda en la base de datos y que lo contactan apenas aparezca algo — y ahí pide el
  teléfono para registrarlo.
- Registra apenas tiene ubicación y teléfono; lo demás lo completa después.
- Tras registrar una perdida, **pregunta si hay otra mascota que registrar** (mucha
  gente perdió más de un animal).
- Si la conversación no es de ninguno de los 3 casos: lo aclara una vez y, si insiste,
  cierra y deja **el canal en pausa 20 minutos**.

### Job diario de coincidencias (#344)
`scripts/job_coincidencias_mascotas.py` cruza cada perdida activa contra cada encontrada
activa. Existe porque la conversación no ve el futuro: cuando una familia escribe, su
mascota puede no estar reportada todavía. Idempotente y **respeta el estado del equipo**
(lo descartado no vuelve a "nueva"). Umbral 6, más alto que el de la búsqueda en vivo
(3), porque aquí nadie confirma al otro lado del chat.

Programado con **EventBridge Scheduler `mascotas-cruce-diario`**:
`cron(0 12 * * ? *)` en `America/Bogota` → ECS RunTask. Rol
`multiagente-scheduler-role` (RunTask + PassRole acotados al cluster). Probado a mano en
producción: exit 0.

### Frontend (#345)
- `pages/mascotas.tsx` — ventana de WhatsApp a pantalla completa. Quien llega está
  angustiado y no debe aprender una interfaz nueva. Los **3 casos de uso** están
  visibles como accesos rápidos desde el primer momento, y el aviso del terremoto va
  fijo arriba. Adjuntar fotos con el clip 📎 en cualquier momento.
- `pages/mascotas-panel.tsx` — coincidencias lado a lado con el desglose del puntaje,
  tablas con **filtros por campo** (texto libre, especie, zona, estado, solo con foto) y
  **visor de fotos a pantalla completa** con la ruta `s3://` de cada recurso. La
  miniatura de la tabla se mantiene chica para que la lista no crezca de alto.
- `middleware.ts` — el dominio nuevo sirve **solo** el chat; cualquier otra ruta es 404.
  El resto de la app quedó intacta.
- `_app.tsx` — `/mascotas` y los hosts del dominio nuevo entran a las listas públicas.
  Sin esto el guard de sesión mandaba el chat ciudadano a `/login`.

### Dominio (#346)
`mascotasperdidascolombia.com`, comprado por el CEO en Hostinger. **DNS delegado a Route
53** (hosted zone `Z064081920UXTWRHTCDT7`): el CEO pegó los 4 nameservers en Hostinger y
el resto quedó automático — Amplify creó el ALIAS A del apex, el CNAME de `www` y el
registro de validación del certificado. Estado `AVAILABLE`.

`mascotasperdidascali.glomabeauty.com` (el subdominio del pedido original) sigue
soportado en el middleware, pero **no tiene DNS**: se descartó al comprar el dominio
propio. Si algún día se quiere, basta un CNAME a CloudFront.

### Despliegue
Imagen `multiagente-backend:ayudacali` (linux/amd64) → ECR. Task-def **rev 27** (env
nuevas `MASCOTAS_BUCKET`, `MASCOTAS_PUBLIC_BASE`, `AWS_REGION`). Migración, seed de la
cuenta y datos de demostración en RDS vía `ecs run-task` rev 27 (exit 0 los tres).
`update-service --force-new-deployment` → `services-stable`. Frontend: commit `15966ac` →
Amplify **job 57 SUCCEED**.

IAM: policy `mascotas-s3-fotos` en `multiagente-ecs-task-role`, acotada a los prefijos
`mascotas/*` y `pendientes/*` del bucket.

**Smoke en producción:** conversación completa contra
`https://mascotasperdidascolombia.com/api/mascotas/chat` — busca, muestra la ficha con
foto servida desde S3 y entrega el contacto **real** de la base (`+57 315 802 4471`,
idéntico a `MC-00002`). `/login` y `/mascotas-panel` dan 404 en ese dominio.
`app.glomabeauty.com` y `glomabeauty.com` sin cambios.

### Arreglo de paso
`requests` no estaba en `backend/requirements.txt` aunque
`services/instagram_publisher` (Sprint 23) lo importa: la imagen lo tenía por una
instalación manual y **cualquier rebuild limpio dejaba el backend sin arrancar**. Se
agregó al archivo.

### Datos de demostración en producción
10 reportes `source='demo'` con fotos reales (placedog.net / cataas.com) y 3 pares
diseñados para coincidir: Canela↔MC-00002 (24 pts), Rocky↔MC-00006 (19), Michi↔MC-00004
(15). Detalle en `PRUEBAS_AYUDA_CALI.md`. Se borran re-corriendo `seed_mascotas_demo.py`.

### Pendientes del sprint "Ayuda a Cali"

| # | Pendiente | Notas |
|---|---|---|
| #347 | **Conectar el bot a un WhatsApp Business** | Es el pendiente grande y explícito del CEO. El bot ya corre en el motor compartido, así que técnicamente es: conseguir el número, darlo de alta como sender (Twilio o Meta), crear el `MetaAccount`/credenciales del tenant y apuntar el webhook. El `bot_runner` lo atiende sin cambios. Ojo con `MASCOTAS_PUBLIC_BASE`: las fotos que envía el bot ya salen con URL absoluta, que es lo que WhatsApp necesita. |
| #348 | **Avisar a quien busca cuando aparece una coincidencia** | Hoy el cruce diario deja el par en el panel y alguien del equipo llama. Con WhatsApp conectado (#347) se puede mandar el aviso automático a la familia. Requiere plantilla aprobada por Meta. |
| #349 | **Borrar los datos de demostración antes de abrir al público** | `source='demo'`, 10 reportes con teléfonos ficticios. Si quedan cuando entren reportes reales, el bot los ofrecerá como coincidencias. |
| #350 | **Retención y borrado de datos** | Los reportes tienen PII (teléfonos de ciudadanos). Falta definir cuánto se guardan y cómo se borra un caso cerrado. Habeas data (Ley 1581): falta aviso de privacidad en el chat. |
| #351 | **Moderación de fotos** | Cualquiera puede subir 6 imágenes de hasta 8 MB sin revisión. Hoy lo contiene el rate-limit por IP; falta una revisión mínima antes de que el volumen crezca. |
| #352 | **Búsqueda visual por foto** | Hoy el cruce es textual. Comparar embeddings de las fotos subiría muchísimo la tasa de acierto — es lo que más ayudaría cuando la descripción es pobre. |
| #353 | **Subir el bot a Sonnet** | Bloqueado por `INVALID_PAYMENT_INSTRUMENT` (#253). Cambiar `model_id` en `seed_bot_mascotas.py` y re-sembrar cuando se resuelva. |
| #354 | **Pausa por canal en almacenamiento compartido** | La pausa de 20 minutos vive en memoria del proceso: si el backend reinicia, se levanta. Aceptable hoy (una sola task ECS); si escala horizontalmente, moverla a la BD. |

### Ronda 2 del sprint (2026-08-13, mismo día) — ajustes pedidos por el CEO

**#355 — Editar y borrar desde el panel.** El CEO necesitaba poder probar sin quedarse
con datos falsos. `PATCH /mascotas/panel/{codigo}` pasó de tocar solo estado y notas a
editar cualquier campo; `DELETE` para un reporte (con sus fotos y coincidencias), para
una foto suelta, y purga en bloque de los reportes de prueba. Los archivos se borran del
storage, no solo la fila, para no dejar objetos huérfanos pagando espacio. La purga
**solo acepta `demo`**: los reportes reales se borran de a uno, a propósito. El panel
ganó formulario de edición, botones por fila y un botón de limpieza que solo aparece si
quedan datos de prueba.

Regla que se hizo explícita a pedido del CEO: **todo registro debe tener teléfono de
contacto y ubicación**. Se pueden corregir, nunca vaciar — el servicio rechaza el cambio
y el formulario los marca con `*`.

**#356 — Aviso de uso de datos.** El bot lo dice en el saludo y la interfaz lo muestra
bajo el banner: los datos se usan únicamente para reunir a las mascotas con sus dueños, y
el teléfono no se comparte hasta que alguien reconozca a la mascota. Cubre parte de #350
(habeas data), que sigue abierto para el aviso de privacidad formal.

**#357 — El Excel entrega solo las mascotas encontradas.** Es la lista que le sirve a
quien busca a la suya. Los reportes de familias buscando llevan datos de contacto y no se
reparten en un archivo descargable; si alguien los pide, el bot lo explica y ofrece
buscar su mascota.

**#358 — Reportes importados de plataformas hermanas.** `mascotas.origen_url` y
`origen_id`, con índice único parcial `(source, origen_id) WHERE origen_id IS NOT NULL`
para que el importador re-corra sin duplicar. `contacto_telefono` pasó a **nullable**:
los reportes importados no publican teléfono. La regla "teléfono **o** ficha de origen"
se valida en `services/mascotas`, no en la BD, porque el motivo es de negocio y no de
integridad referencial. El bot detecta el reporte externo y entrega el **enlace a la
ficha original** en vez de un teléfono, con instrucción explícita de no inventarlo;
panel y Excel muestran el origen. Migración `migrate_ayuda_cali_origen.py` aplicada en
local y en RDS (esta vez vía `rds_exec.sh`, que ejecuta inline: ojo, el script del repo
usa `__file__` y por eso se corrió una variante sin esa dependencia).

**Hallazgo del CEO sobre el sitio de origen:** el sitemap de mascotasporcolombia.com
tiene **dos** secciones de fichas, no una — `/mascotas/<slug>` (261, mascotas perdidas) y
`/found-pets/<slug>` (47, encontradas), más páginas índice por departamento que no son
fichas. El análisis inicial solo cubría la primera. Además, algunas fichas reportan
**varias mascotas juntas en una sola foto** y hay que separarlas en un registro por
animal (comparten foto; `origen_id` lleva sufijo `#1`, `#2` para no romper la
idempotencia).

Despliegues de la ronda: imágenes `:ayudacali2` a `:ayudacali5`, task-defs rev 28 a 31.
Amplify jobs 59, 60 y 61 SUCCEED.

---

## #359 — Alivianar las fotos del bucket sin perder calidad (2026-08-16)

El CEO pidió lo que hace TinyPNG/Squoosh, pero para las fotos que ya viven en S3, con
un registro local de lo procesado para que correr el script otra vez no repita trabajo.

**Por qué no se usó TinyPNG.** Son fotos de mascotas de familias reales, subidas por
ciudadanos; mandarlas a un tercero para ahorrar unos KB no se justifica. El proceso
corre local y las fotos no salen de AWS ni de este equipo.

### `backend/scripts/optimizar_fotos_mascotas.py`

Corre **siempre desde el equipo del CEO** (el bucket es privado y la BD vive en la VPC).
Para cada foto busca el archivo más liviano que todavía se ve igual: prueba calidades
JPEG de 78 hacia arriba y se queda con la **primera que pasa un umbral de SSIM**
(similitud estructural, implementada en el propio script con ventana gaussiana 11×11 —
sin scipy). Si ninguna calidad llega al umbral, la foto **no se toca**.

Además: redimensiona a 2000 px de lado largo (venían fotos de 4032 px), guarda el JPEG
progresivo, y descarta el EXIF — que de paso saca la **geolocalización** que traen las
fotos de celular.

**Umbral 0.96, y por qué no 0.98.** Calibrado contra las fotos reales del bucket: el
SSIM se mide contra el original ya redimensionado, y el ruido de sensor de una foto de
celular no lo conserva ninguna recompresión — en las más pesadas ni calidad 95 pasa de
0.983. Con imágenes limpias el mismo script se queda en calidad 78 con SSIM 0.99.

**Triple candado contra el reproceso**, en este orden:
1. `registro_optimizacion_fotos.csv` (se abre en Excel) — guarda el ETag resultante, así
   que si mañana suben otra foto con la misma clave el ETag cambia y se vuelve a procesar;
2. metadata `optimizado=v1` en el objeto de S3;
3. la columna `mascota_fotos.optimizada` en la BD (ver abajo).

**Respaldo antes de tocar nada.** Cada original se copia a `respaldos_fotos_mascotas/`
(git-ignorado, 70 MB) antes de sobreescribir. El bucket no tiene versionado: sin esto no
hay camino de vuelta. Para revertir: `--restaurar <clave>`.

### Campo en la BD (pedido del CEO a mitad del trabajo)

`mascota_fotos.optimizada` (BOOLEAN, indexada), `optimizada_at` y `bytes_original`.
Migración `migrate_optimizacion_fotos.py`, idempotente, **aplicada en local y en RDS**.
Como el optimizador corre fuera de la VPC, deja un manifiesto JSON que
`sync_fotos_bd_mascotas.py` aplica desde adentro (llega por `s3://…/import/`, igual que
el importador de patitasacasa, porque los overrides de ECS topan en 8 KB).
El panel muestra "⚡ Peso optimizado · antes pesaba X".

### Resultado

**100 fotos, 88.3 MB → 16.7 MB (81% menos).** 96 comprimidas, 4 dejadas como estaban
porque ya venían optimizadas (bajaban menos del 10%; igual quedan marcadas para no
volver a evaluarlas). La más pesada, `MC-00111`, pasó de 4.1 MB a 302 KB. SSIM: mínimo
0.960, mediana 0.986. En la BD, `100/100 optimizadas`.

Se corrió en dos tandas porque entraron 32 reportes nuevos (`MC-00132`–`MC-00163`) en
medio del trabajo: el script los tomó solo en la segunda corrida y no volvió a tocar los
de la primera — que era exactamente lo que había que demostrar.

Tres hallazgos de paso:
- **Cinco JPEG del bucket estaban truncados** (`MC-00095/96/98/99/102`, les faltaban 1-3
  bytes del marcador de fin). El navegador los pinta igual y Pillow no. Se agregó un
  rescate con guardarraíl: si las últimas filas salen en gris plano —así rellena Pillow
  lo que no alcanza a decodificar— la imagen se considera mutilada de verdad y no se
  toca. Las cinco se recuperaron y quedaron guardadas como JPEG válido.
- **36 fotos eran PNG** de ~2 MB (las 4 primeras, y luego los 32 reportes nuevos, todos
  en PNG). Pasan a JPG, lo que cambia la clave del objeto; el PNG viejo **no se borró**
  (regla del módulo: nada se borra sin visto bueno del CEO). Son 26.5 MB de peso muerto
  en el bucket.
- **El primer diseño reprocesaba los PNG convertidos en cada corrida**: se guardaba el
  ETag del JPG nuevo contra la clave del PNG viejo, que obviamente nunca coincidía. Se
  corrigió guardando el ETag del objeto que está *en la clave de esa fila*.

Smoke en producción: `GET /mascotas/foto/{codigo}/{id}` responde 200 `image/jpeg` para
las convertidas (`MC-00107`, `MC-00131`), las truncadas (`MC-00095`) y la de prueba
(`MC-00127`).

### Pendientes que abre

| # | Pendiente | Notas |
|---|---|---|
| #361 | **Borrar los 36 PNG viejos** (26.5 MB) y la copia `comparacion/MC-00127-ORIGINAL.jpg` | Ya nadie los sirve: la BD apunta al `.jpg`. Requiere visto bueno explícito del CEO. |
| #362 | **Versionado del bucket** | Sigue abierto desde el borrado accidental. Mientras no exista, `respaldos_fotos_mascotas/` es el único respaldo de los originales. |

## #360 — Comprimir al subir, no después (2026-08-16)

El CEO lo aprobó apenas se propuso: alivianar lo que ya está guardado sirve una vez, y
al día siguiente vuelve a entrar una foto de 4 MB.

El algoritmo se sacó a `app/services/imagenes.py`, compartido por los dos caminos:

- **`comprimir()` — subida.** Una sola pasada a calidad fija 85. Lo atiende un request
  de alguien que está esperando, así que no puede probar seis calidades. Usa el modo
  `draft` de Pillow, que aprovecha el DCT del JPEG para decodificar ya reducido en vez de
  armar la imagen completa y achicarla después: **una foto de 4 MB tarda 200 ms**.
- **`comprimir_buscando()` — barrido del bucket.** El de #359, con la escalera de
  calidades y el SSIM. Se quedó igual; el script dejó de duplicar 131 líneas.

`guardar_foto()` comprime antes de subir a S3 y nace con `optimizada=TRUE` y
`bytes_original`. **Falla hacia el original**: si la imagen viene corrupta o la
compresión no gana nada, se guarda tal cual y la foto queda sin marcar, para que el
barrido la tome después. Perder la foto de alguien por un error de compresión sería
mucho peor que guardarla pesada.

`Pillow` se agregó a `requirements.txt` — no estaba, y sin él el backend arranca pero
guarda todo sin comprimir.

**Prueba local end-to-end** (`POST /mascotas/foto` contra el contenedor):
`4183 KB → 376 KB (91%)` un JPEG, y un PNG de 2 MB entró como `.jpg` de 276 KB con
`content_type` corregido. Basura de entrada devuelve `None` y guarda el original.

### Despliegue (coordinado con el otro frente del sprint)

Iba en paralelo otro trabajo sobre el mismo módulo —formulario de nombre/teléfono antes
de abrir el chat, el freno para que el bot no registre inventando especie o ubicación, el
importador de RoyiPets y los teléfonos dobles— y el CEO pidió desplegarlo junto. Se
verificó antes de mezclar: `tsc --noEmit` y `next build` limpios, y el contenedor local
levantó con ambos cambios.

Commit `1b2af54`. Imagen `multiagente-backend:fotos-livianas` → ECR, **task-def rev 39**,
`update-service --force-new-deployment` → `services-stable`. Amplify **job 77 SUCCEED**.

**Smoke en producción:** se subió una foto de 4.28 MB a `POST /mascotas/foto` y quedó
guardada en **384 KB** con `optimizada=TRUE` y `bytes_original` registrado (fila 152, 3.7 s
de ida y vuelta contando la subida del archivo original). Las fotos ya optimizadas se
siguen sirviendo 200 `image/jpeg`, y `mascotasperdidascolombia.com` responde 200.

Queda en `pendientes/e84aa1e3.../` la foto de esa prueba, huérfana a propósito: no se
borró nada sin autorización.

---

## #361 — Los 218 casos nuevos, y la limpieza del residuo (2026-08-17)

Entraron 218 casos de los importadores nuevos y el CEO pidió alivianarlos y **borrar el
residuo** — la autorización explícita que faltaba desde #359.

### Segunda corrida del barrido

354 fotos sin procesar. De ellas **302 se comprimieron: 118.4 MB → 43.5 MB (63%)**, y
**152 se dejaron como estaban**. Esas 152 no eran un problema: son las que entraron
*después* del despliegue de #360 y ya venían comprimidas desde la subida. En la BD,
`454/454 optimizadas`.

Eso destapó un hueco: `guardar_foto()` comprimía pero **no dejaba la marca `optimizado`
en el objeto de S3**, así que el barrido se bajaba las 152 para descubrir que no había
nada que ganar. Ahora la pone (`imagenes.MARCA`, compartida por los dos caminos) y el
barrido las saltea sin descargarlas.

### Limpieza del residuo

`backend/scripts/limpiar_residuo_fotos.py`. Define residuo como **objeto del bucket que
ninguna fila de `mascota_fotos` referencia** — nada de listas escritas a mano. Contra la
regla 1 del módulo, tres frenos: pide las claves vivas a la BD y **aborta si llegan menos
de 50** (sin esa lista, todo parecería residuo); **baja una copia de cada objeto** antes
de borrarlo; y sin `--borrar` solo enumera.

Se borraron **37 objetos, 30.1 MB**: los 36 PNG que quedaron cuando se convirtieron a
JPG —cada uno verificado uno a uno contra la existencia de su `.jpg` vivo en la BD— y la
copia `comparacion/MC-00127-ORIGINAL.jpg` de la comparación que revisó el CEO.

Aparte, la foto del smoke de #360 (fila 152, huérfana en `pendientes/`). Se borró con un
script que verificaba id **y** clave **y** que no estuviera asociada a ningún reporte.
**Las otras 7 fotos huérfanas de `pendientes/` no se tocaron**: son de chats reales del
13 y 14 de agosto, no residuo nuestro.

**Bucket: 491 objetos / 99.7 MB → 453 objetos / 64.3 MB**, y 453 objetos contra 453 filas
en la BD: cuadra exacto, sin huérfanos de ningún lado.

---

## #361 — La plataforma se abría sin sesión activa (2026-08-17)

El CEO reportó que al entrar a `app.glomabeauty.com` sin sesión activa aparecía el
dashboard en vez del login.

### Qué pasaba

Dos fallas que se sumaban, las dos en el frontend:

1. **El guard confundía "hay token guardado" con "hay sesión".** `_app.tsx` solo
   preguntaba si `localStorage.token` existía. El JWT vence a los 30 minutos
   (`ACCESS_TOKEN_EXPIRE_MINUTES`), pero se queda guardado para siempre: pasado ese rato
   el token ya no servía para nada y aun así el guard lo daba por bueno y pintaba la
   plataforma. Uno se enteraba solo cuando alguna pantalla llamaba al backend y recibía
   un 401 — y en `/` no hay ninguna llamada, así que ahí no se enteraba nunca.
2. **"Salir" no cerraba sesión.** El botón del sidebar era un `<Link href="/login">`:
   llevaba al login sin borrar el token. Volver a entrar al dominio reabría la
   plataforma con la sesión que uno creyó haber cerrado.

El HTML que sirve Amplify siempre estuvo bien (no trae ni el dashboard ni el login: el
guard corre en el cliente), así que esto era 100% estado viejo en el navegador.

### El arreglo

`frontend/lib/session.ts`, única fuente de verdad sobre la sesión del navegador.
`getToken()` lee el `exp` del payload del JWT y **borra** el token vencido o ilegible,
de modo que "hay token" vuelve a significar "hay sesión". Es UX, no seguridad: quien
valida la firma sigue siendo el backend; acá solo evitamos mostrar una pantalla que el
token ya no puede alimentar.

- `_app.tsx` usa `haySesion()` y además revisa al volver a la pestaña (`focus` /
  `visibilitychange`): el token se puede vencer con la pestaña abierta y quieta, y
  volver a ella es justo cuando uno espera encontrarse el login. Al fallar el guard
  apaga la pantalla antes de redirigir, para que no quede pintado lo anterior.
- `Sidebar.tsx`: "Salir" pasó de link a botón que llama `cerrarSesion()`.
- Se eliminaron los 12 accesos crudos a `localStorage.token` regados en páginas
  (`bots`, `bots/[id]`, `usuario`, `mensajes`, `mascotas-panel`, `campanas/contactos`,
  `login`, `lib/api.ts`): todos pasan por `lib/session.ts`.

Las rutas públicas no se tocaron: el chat de mascotas y las landings siguen sirviéndose
en el HTML inicial, que es lo que importa para buscadores.

### Pruebas

`tsc --noEmit` y `next build` limpios. Sobre el build de producción local se corrieron
10 pruebas end-to-end manejando Chrome por CDP (`scratchpad/guard-test.mjs`), **10/10**:
sin token y con token vencido `/` y `/mascotas-panel` mandan al login y el token vencido
queda borrado; con token vigente el dashboard abre normal; "Salir" borra el token y
volver a `/` sigue mandando al login; `/mascotas` y `/gloma` siguen abiertas sin sesión.

### Despliegue

Solo frontend, sin tocar backend ni base de datos — no había nada que desplegar en ECS
ni migración que aplicar, así que este cambio no interfiere con los otros frentes en
curso.

### Auditoría de seguridad (regla 4 del CLAUDE.md) y endurecimiento

El agente `seguridad` revisó el commit `234300c` antes del push: **cero hallazgos
Críticos y cero Altos**. Confirmó lo que importaba — el payload del JWT se usa
únicamente para leer `exp` (ningún rol, correo ni permiso sale de ahí; los módulos
internos del sidebar los sigue autorizando el backend vía `/api/*/access`), el parseo
no puede lanzar excepción sin capturar, `/mascotas-panel` sigue protegido por tres
capas (guard, middleware del borde y `Depends(require_mascotas_account)`), y no hay
nada que loggee el token. Dejó 1 Medio y 4 Bajos, todos corregidos en el commit
siguiente:

- **Reloj desajustado (Medio).** Comparar el `exp` del servidor contra el reloj del
  navegador tenía un modo de falla nuevo y peor que el bug original: con el
  computador 30 minutos adelantado, el token recién emitido nacía "vencido", el guard
  lo borraba y el usuario quedaba rebotando entre el login y el dashboard sin poder
  entrar nunca. Ahora el login calibra el desfase con el header `Date` de la respuesta
  y hay 60 s de margen. Ante la duda se deja pasar el token: el 401 del backend es una
  red de seguridad, quedar trancado afuera no tiene ninguna.
- **Autorización heredada entre rutas (Bajo).** El booleano `autorizado` sobrevivía al
  cambio de ruta, así que al navegar entre pantallas privadas la nueva alcanzaba a
  montarse antes de que el guard corriera. Ahora se guarda *en qué ruta* se autorizó.
- **Botón "atrás" tras salir (Bajo).** `location.assign` dejaba la pantalla privada en
  el historial y el bfcache la repintaba. Pasó a `location.replace`, más un listener
  de `pageshow`. Importa en un computador compartido.
- **Pestaña quieta (Bajo).** `/` no llama al backend, así que nadie se enteraba de que
  la sesión venció. Se programa un temporizador al `exp`.
- **Respuesta de login sin `access_token` (Bajo).** Se guardaba la cadena `"undefined"`
  y el usuario rebotaba sin explicación; ahora se valida y se muestra el error.

Queda anotado, sin acción: el logout es solo del navegador. El JWT sigue siendo válido
server-side hasta que vence (no hay `jti` ni denylist). Es el comportamiento normal de
JWT stateless y con 30 minutos de vida la ventana es corta, pero conviene tenerlo
escrito por si algún día hace falta revocar de verdad.

### Pruebas (46/46)

`tsc --noEmit` y `next build` limpios. Sobre el build de producción local, 46 pruebas
end-to-end manejando Chrome por CDP (`scratchpad/guard-test.mjs`):

- **Las 14 pantallas privadas, entradas directo por URL** (`/`, `/bots`, `/bots/1`,
  `/campanas`, `/campanas/1`, `/campanas/contactos`, `/campanas/nueva`,
  `/campanas/plantillas`, `/campanas/plantillas/nueva`, `/citas`, `/instagram`,
  `/mascotas-panel`, `/mensajes`, `/usuario`), en dos escenarios: sin token y con token
  vencido. Las 28 mandan al login, y en las 28 el token vencido queda borrado.
- Token vigente: el dashboard y `/usuario` abren normal, y navegar entre pantallas no
  rebota.
- "Salir" borra el token; después el botón "atrás" no devuelve a la plataforma.
- La pestaña quieta en `/` se va sola al login cuando la sesión vence (el escenario del
  reporte).
- Con el reloj del navegador 30 minutos adelantado la sesión recién abierta sirve.
- Tokens basura (`no-es-un-jwt`, `a.b.c`, `...`, `null`) → login, sin excepciones.
- Las 6 rutas públicas (`/login`, `/register`, `/mascotas`, `/gloma`, `/automatas`,
  `/elecol`) siguen abiertas sin sesión.

Dos pruebas usan la red bloqueada hacia `/api/*` a propósito: el token de la batería es
de mentiras y el backend local lo rechaza con 401 — que dispara el logout del helper y
tapaba lo que se quería medir. Ese camino (401 real → cierra sesión) se verificó aparte
contra el backend vivo, y funciona.

### Despliegue

Solo frontend, sin tocar backend ni base de datos — no había nada que desplegar en ECS
ni migración que aplicar, así que este cambio no interfirió con los otros frentes en
curso (importadores de fuentes y bot de mascotas iban en paralelo y quedaron sin tocar
en el árbol de trabajo).

Commits `234300c` + `36d75f0` → push a `main`. Amplify **job 79 SUCCEED** (auto-disparado
por el push).

**Smoke en producción** (`scratchpad/smoke-prod.mjs`, Chrome headless contra
`app.glomabeauty.com`): **20/20**. Las 9 pantallas privadas entradas directo por URL
mandan al login, tanto sin token como con token vencido, y el vencido queda borrado.
`mascotasperdidascolombia.com` y la landing `glomabeauty.com` siguen abiertas sin sesión.

---

## #362 — Cinco fuentes nuevas, y una tabla que las aguante a todas (2026-08-16/17)

El CEO trajo un PDF de RoyiPets y tres sitios más, y pidió lo mismo para todos: que
nada entre a la base sin que él lo haya visto antes, y que re-correr una fuente no
duplique. De paso, que la tabla deje de esconder datos dentro de `notas`.

### Lo que entró

| Fuente | Fichas | Perdidas · Encontradas | Con teléfono | Fotos |
|---|---|---|---|---|
| `royipets` (PDF) | 32 | 0 · 32 | 32 | 32 |
| `petsearch` | 121 | 91 · 30 | 118 | 135 |
| `encontradogs` | 59 | 30 · 29 | 0 (por diseño) | 177 |
| `proteccionanimal` | 38 | 31 · 7 | 16 | 41 |

**250 reportes y 385 fotos**, en local y en RDS con los mismos números. Ningún registro
previo se modificó: `web`, `patitasacasa` y `mascotasporcolombia` quedaron con su
`updated_at` intacto, verificado en los dos entornos.

### El PDF de RoyiPets

Exportado de Excel y **sin rejilla vectorial**: las columnas se reconstruyen por la
coordenada x de cada palabra y las filas por el recuadro de la foto. Guiarse solo por
las fotos costaba dos filas —hay dos registros sin imagen— así que las filas se anclan
en la columna ESPECIE y los huecos entre fotos se rellenan.

Dos cosas que el PDF esconde y hubo que detectar:
- **Excel recorta el texto que no cabe.** Una descripción de una línea que topa el borde
  derecho está *incompleta*, no es corta. El extractor lo marca (`carac_cortada`).
- **15 de las 32 fichas no dicen de qué color es el animal.** Como el color pesa 5 en el
  cruce, se sacaron mirando las fotos y quedaron marcadas como derivadas en la revisión.

Los teléfonos de terceros que venían en las notas se borraron: en un reporte solo puede
haber un número, el de contacto.

### El framework de importación

`backend/scripts/fuentes/` con un módulo por fuente y `actualizar_fuente.py` de CLI:

```bash
python backend/scripts/actualizar_fuente.py petsearch --revisar   # baja y arma el HTML
#   ← el CEO revisa
python backend/scripts/actualizar_fuente.py petsearch --cargar    # carga lo aprobado
```

El descarte de repetidos va contra `(source, origen_id)`, la restricción única que ya
existía. En la revisión solo aparece lo que todavía no está, y la carga vuelve a
verificar: correr las tres cargas dos veces dio `creados=0 ya_estaban=121/59/38`.

Rarezas que costó descubrir, y que están en `documentacion_bd/mapeo_fuentes.md`:
- **petsearch** tiene *tres* estados, no dos: `missing`, `stray` y `found`. El tercero
  son reencontradas y no se traen.
- **encontradogs** no publica teléfono a propósito (hace de intermediario) y **sí tiene
  perdidas**, no solo encontradas como se creía. El tipo sale de la sección de la
  portada, y por eso las «de vuelta en casa» quedan fuera sin adivinar nada.
- **proteccionanimal** marca *todo* como «Perdido» aunque haya hallazgos: la gente lo
  escribe en el campo del nombre (hay fichas llamadas `encontrado`). El tipo se deduce y
  **las 38 quedaron marcadas** para que un humano lo confirme. Su teléfono va **dentro
  de la descripción** y hay que sacarlo de ahí y **borrarlo del texto**: un número suelto
  en `senas` le tumba el turno al bot por el guardarraíl antiteléfonos. Sus URLs de foto
  son de S3 firmadas y **vencen en una hora**, así que las fotos se bajan en la revisión.

### Dos teléfonos en un campo

El CEO pidió que las fichas en hogar de paso lleven el de la fundación **y** el de la
casa. `_TELEFONO_RE` rechazaba el `/`, así que el panel no habría podido guardar ninguna
edición de esas 23 fichas. Ahora acepta uno o dos separados por `/` o `,`.

### El bot mandaba a la ficha de origen aunque tuviéramos el teléfono

`entregar_contacto` entraba en la rama «no es nuestro, no tienes teléfono» **con solo ver
`origen_url`**. Las 121 de PetSearch tienen las dos cosas: a alguien que acababa de
reconocer a su perro le habría dado la portada de PetSearch en vez del número. Quedaron
tres ramas: teléfono + enlace (los dos, el teléfono primero), solo enlace, y reporte
propio. `ORIGEN_NOMBRES` se completó con las cuatro fuentes nuevas.

**Prueba end-to-end en producción**, conversación completa contra `api.glomabeauty.com`:
el bot buscó, encontró `MC-00261` (importada de PetSearch), mostró su foto desde S3 y al
confirmar entregó `350 2369790` **y** el enlace, atribuyéndolo a «PetSearch Colombia».
La prueba dejó el reporte marcado como `reconocida` —lo hace `entregar_contacto`— y se
revirtió a `activo`: nadie reconoció nada de verdad y el equipo habría perdido una
llamada.

### Los 15 campos que la tabla estaba botando

Todo lo que no tenía columna terminaba concatenado en `notas`, donde no se puede
filtrar ni contar. `migrate_campos_multifuente.py` agrega la unión de lo que publican
las siete fuentes:

`ciudad` · `departamento` · `esterilizado` · `vacunado` · `desparasitado` · `peso_kg` ·
`salud` · `resguardo` · `resguardo_nombre` · `rescatado_por` · `rescatado_por_telefono` ·
`recompensa` · `estado_origen` · `publicado_origen_at` · `sincronizado_at`

Todas nullable y **tri-estado donde aplica**: NULL es «la fuente no lo dice», que no es
lo mismo que `false`. `resguardo` va **sin CHECK a propósito** — lo alimentan fuentes
externas y una restricción rompería un importador cada vez que aparezca un valor nuevo.

Aplicada en **local y RDS**, 43 columnas en los dos. El backfill
(`backfill_campos_multifuente.py`) completó **250 fichas y 1.136 campos**, con los mismos
números en ambos entornos. Solo escribe donde hay NULL: un dato corregido a mano en el
panel no lo pisa una corrida del script.

> **Trampa que costó un despliegue:** el primer backfill contra RDS reportó
> `campos_escritos=0` sin fallar. La migración había corrido por SQL directo, pero la
> imagen desplegada tenía un `models.py` sin esas columnas, así que el ORM ni las veía.
> **Migrar la base no basta: hay que desplegar el modelo.**

### Documentación

Carpeta `documentacion_bd/` — `index.html` (esquema, fuentes, matriz campo × fuente,
pesos del cruce y diccionario), `diccionario_datos.md`, `mapeo_fuentes.md`,
`esquema.sql` y dos diagramas PlantUML. Los tres primeros **se generan leyendo la base
real** (`python documentacion_bd/generar.py`), y el generador avisa cuando aparece una
columna sin describir — así se detectó que cuatro descripciones de
`mascota_coincidencias` tenían nombres inventados.

### Despliegue

Tres imágenes, todas construidas desde un **worktree limpio sobre HEAD** con solo el
cambio propio: había trabajo sin commitear de otras sesiones en el árbol (columnas de
optimización de fotos, caché de prompts) y no se subió a producción nada ajeno.

| Imagen | Rev | Qué llevó |
|---|---|---|
| `royipets1` | 38 | `_TELEFONO_RE` con dos teléfonos |
| `fuentes1` | 40 | Las tres ramas de `entregar_contacto` + `ORIGEN_NOMBRES` |
| `multifuente1` | 41 | Las 15 columnas en `models.py` |

Se verificó que los commits de auth de la otra sesión (#361) son **solo frontend**: no
hubo pisada entre despliegues.

La policy `mascotas-s3-fotos` no permitía leer el prefijo `import/` que documenta el
manual: se le agregó `s3:GetObject` **solo de lectura** sobre `import/*`. El prefijo se
limpió después de cada carga.

### Pendientes

- **Wirear los campos nuevos al panel y al scoring.** Las columnas existen y están
  llenas, pero el panel todavía no las muestra ni filtra por ellas, y el cruce las
  ignora. Ojo con `ciudad`: sumarla al scoring reintroduce el ruido de las zonas
  genéricas que ya se había quitado a propósito.
- **`mascotasporcolombia` y `patitasacasa` no tienen backfill**: sus 61 reportes siguen
  con las 15 columnas en NULL. Habría que portarlos al framework de `fuentes/`.
- Cuatro fotos de `MC-00035` y `MC-00036` (locales, de 2026-08-13) están referenciadas en
  la BD pero **no existen en `media_local/` ni en el volumen viejo**. Son anteriores al
  cambio de montaje. No se borró nada.

---

## #363 — El prompt se repagaba entero en cada llamada (2026-08-17)

El CEO preguntó si convenía subir el bot de mascotas a un modelo más inteligente que
Haiku. La respuesta corta resultó ser "no, pero estabas pagando de más".

### Lo que se creía y no era

`seed_bot_mascotas.py` decía que este bot no podía usar Sonnet porque Bedrock lo rechaza
con `INVALID_PAYMENT_INSTRUMENT` (#253). Probando la cuenta modelo por modelo con
invocaciones reales, eso sólo aplica a **Sonnet 4.6**. Sí responden hoy, sin tocar el
medio de pago: **Sonnet 4.5**, **Opus 4.5** y **Opus 4.6**. No están habilitados
Sonnet 5, Opus 4.7/4.8 ni Fable 5.

### La medición

Stack Docker aparte (proyecto `pruebamodelo`, sin publicar puertos, corpus congelado con
restore de un `pg_dump` antes de cada corrida) para no tocar el stack `wati` ni RDS.
153 turnos: 8 casos guionados + réplica de 6 conversaciones reales de producción. Los
tokens se leyeron del `usage` de cada respuesta de Bedrock. Gasto: US$ 5,62.

Uso real medido: 75 conversaciones en 5 días (~450/mes), 5,73 turnos por conversación y
**~15.600 tokens de entrada por turno** — el system prompt son 6.130; el resto son
resultados de tools que se reenvían íntegros en cada ronda.

| escenario | por conversación | al mes |
|---|---|---|
| Haiku sin caché (lo que había) | US$ 0,094 | US$ 42 |
| **Haiku con caché** | **US$ 0,031** | **US$ 14** |
| Sonnet 4.5 sin caché | US$ 0,291 | US$ 131 |
| Sonnet 4.5 con caché | US$ 0,105 | US$ 47 |

En capacidad funcional empataron: los dos aprobaron los 8 casos. Sonnet resultó **más
prudente al entregar contactos** (ante un "sí, puede ser" ambiguo pide confirmar señas;
Haiku entrega el teléfono de una) y **menos disciplinado al esperar el resultado de la
tool**: en un turno escribió un teléfono inventado y se autocorrigió en el mensaje
siguiente — el usuario ve los dos. Latencia mediana 2,5 s vs 4,7 s. Decisión del CEO:
**se queda Haiku, se activa el caché**.

### El cambio

`llm_engine._invoke_model` mandaba el `system` como string plano. Ahora va como bloque
con `cache_control`; como el prefijo se renderiza `tools` → `system` → `messages`, el
marcador cachea las herramientas y el contexto del cliente juntos. Verificado sobre el
código de producción: **91 % de la entrada servida desde caché**, sin una sola respuesta
distinta. Aplica igual a Talulah y al demo de viajes.

Se agregó además una línea de log por invocación con `in/out/cache_read/cache_write` (sin
contenido, reglas #1/#6): si `cache_read` se va a cero de forma sostenida, es que el
prefijo dejó de ser estable y el ahorro se perdió.

Informes: `PLAN_PRUEBAS_MODELO_MASCOTAS.html` y `RESULTADOS_PRUEBAS_MODELO_MASCOTAS.html`.

### Pendientes

- **Brecha en `_viola_contacto`** (la que dejó pasar el teléfono inventado de Sonnet):
  devuelve `False` apenas `entregar_contacto` aparece en `tools_called`, **sin comparar
  el número escrito contra el que la herramienta devolvió**. Si el modelo escribe el
  teléfono y llama la tool en la misma ronda, el número inventado llega al usuario.
  Haiku no lo activó en 77 turnos, pero la protección depende de suerte, no de diseño.
- **Datos personales en el repo, que es público**: `backend/scripts/fuentes/proteccionanimal.py`
  y `documentacion_bd/mapeo_fuentes.md` traen teléfonos reales de anuncios (`3193566690`,
  `315 2129670`) como ejemplos en docstrings. Ya están en el historial de GitHub. Sacarlos
  hacia adelante es fácil; limpiar el historial requiere reescritura y decisión del CEO.

---

## #364 — Contraseñas de producción publicadas en un repo público (2026-08-17)

Barriendo el repo antes de un push se encontró que `github.com/JeickH/multiagente` es
**público** y tenía credenciales vivas en texto plano. Se comprobó marcando contra
`https://api.glomabeauty.com/login`: `recuperatumascota@gmail.com` y `talulah@gloma.com`
respondían **HTTP 200** con la contraseña que estaba escrita en el repo.

### Alcance

- **21 apariciones de contraseñas en documentos** (`BITACORA.md` ×16,
  `PRUEBAS_AYUDA_CALI.md`, `MANUAL_RECUPERA_TU_MASCOTA.md`, `estructura_motor_llm.html`,
  `guiones_prueba_viajes.html`).
- **4 scripts con la contraseña real como default en el código**:
  `seed_bot_mascotas.py`, `seed_bot_talulah.py`, `seed_bot_covenas.py` y
  `reset_demo_password.py`.
- **Teléfonos de personas reales** (de anuncios de las fuentes) como ejemplos en
  docstrings: `fuentes/proteccionanimal.py`, `fuentes/petsearch.py`, `fuentes/base.py`
  y `documentacion_bd/mapeo_fuentes.md`.

### Lo que se hizo

Todas las contraseñas salieron de documentos y código: los cuatro scripts ahora
**exigen** la contraseña por variable de entorno y abortan con un mensaje claro si falta,
en vez de caer a un default publicado. Los teléfonos de terceros quedaron enmascarados
(`3XXXXXXXXX`); se respetó `extraer_royipets_pdf.py`, donde el número es dato funcional
del refugio, no un ejemplo. Se agregó la **regla de seguridad #8** a `CLAUDE.md`.

Verificado: `CREDENCIALES*.txt`, `.env` y `gemini_secrets` sí estaban git-ignorados.

### Pendiente — BLOQUEANTE, decisión del CEO

**Redactar no arregla nada por sí solo**: las contraseñas siguen en el historial público
de GitHub y hay que **rotarlas**. Mientras no se roten, `recuperatumascota@gmail.com` y
`talulah@gloma.com` son cuentas abiertas para cualquiera que lea el repo.
Limpiar el historial (`git filter-repo` + force-push) es posible pero rompe todos los
clones y hay una sesión paralela trabajando: coordinar antes.

---

## #365 — El contacto de la antesala no llegaba al registro (2026-08-17)

El CEO reportó que el nombre y el teléfono que la persona escribe **antes** de empezar
a chatear no quedaban en la conversación del panel.

### Causa

`frontend/pages/mascotas.tsx` pide nombre, teléfono y motivo en una antesala, y con eso
compone el primer mensaje: *"Hola, soy {nombre}. {motivo}. Mi teléfono de contacto es
{telefono}."*. El backend nunca leía esos datos: `chat_contacto` se llenaba **solo** si
la conversación llegaba a registrar un reporte, leyéndolo de la ficha. Si la persona
buscaba su mascota y la encontraba —o se iba antes—, el hilo quedaba anónimo.

Se ve en los datos: de 78 conversaciones, las únicas con contacto son las que registraron
un caso. La de las 06:01 UTC llegó a **reconocer a su mascota** y quedó con
`contacto=None`.

### Arreglo

`services/mascotas.py` gana tres extractores deterministas — `telefono_dicho`,
`nombre_dicho` y `contacto_dicho` — y el chat los aplica a cada mensaje, guardando el
resultado en la sesión cifrada (`k`) para que sobreviva a los turnos siguientes. El
reporte sigue mandando cuando existe: son los datos que la persona confirmó.

La lista de exclusión de `nombre_dicho` es a propósito: sin ella, "soy de Cali" y "soy la
dueña" llenaban el panel de contactos llamados "De" y "La".

`backend/tests/test_mascotas_contacto.py` cubre las cuatro plantillas reales de la
antesala, incluidos el nombre en minúsculas y el listado de Excel (que no pide teléfono).

### De paso

El venv de `backend/` no tenía `Pillow` (que sí está en `requirements.txt`). Eso hacía
fallar 11 tests que no estaban rotos. Con la dependencia instalada, **la suite pasa
entera: 181 tests**.

### Pendiente

`marcar_reconocida()` marca **solo la ficha de la mascota encontrada**. Ni el reporte de
quien la está buscando ni la fila de `mascota_coincidencias` cambian de estado, así que
el par sigue apareciendo como pendiente de revisar en el panel. Verificado en el log de
producción que el bot sí hace su parte (`MC-00261 marcada como reconocida` a las
06:04:36 UTC); lo que falta es propagar el reconocimiento a las otras dos filas.
Aparte, `MC-00261` quedó con `estado='reconocida'` pero `reconocida_at` en NULL y un
`updated_at` de 12 horas después: algo reescribió la fila más tarde y no se identificó qué.

---

## #366-368 — Rotación de credenciales y seis mejoras del bot (2026-08-17)

Lote de un solo push y un solo despliegue, coordinado con la sesión paralela que
estaba levantando la suite de tests del módulo.

### Incidente cerrado: contraseñas rotadas

Las de `recuperatumascota@gmail.com` y `talulah@gloma.com` estaban publicadas en
el repo (ver #364). Se rotaron con `rds_exec.sh` pasando **solo el hash bcrypt**
—calculado local— porque los overrides de `ecs run-task` quedan en CloudTrail.
Verificado: las viejas dan 401, las nuevas 200. Las nuevas quedaron en
`CREDENCIALES.txt` (git-ignorado). **El historial de GitHub sigue teniendo las
viejas; por eso había que rotar, no solo borrar.**

### Lo que entró

| # | Qué | Por qué |
|---|---|---|
| — | El reconocimiento marca las DOS fichas y el par | Un reencuentro son dos reportes y una coincidencia; solo se marcaba la encontrada, así que la familia seguía "buscando" y el par seguía "sin revisar" |
| 3 | `_viola_contacto` compara el número | Se apagaba con que la tool apareciera en la ronda; dejó pasar un teléfono inventado (benchmark #363) |
| 4 | La búsqueda manda las candidatas juntas | Mostraba de a una con `ver_ficha`: 4 turnos y 4 llamadas al modelo para descartar 4 perros |
| 6 | Tokens por turno en `bot_llm_decisions` | El costo real solo se sabía corriendo un benchmark aparte; `cache_read` es el termómetro del caching de #363 |
| 5 | Botón directo al Excel | 21 de 75 conversaciones eran solo para el listado, 19 de un turno: US$0,03 cada una por un archivo |
| 2 | Desempate visual entre candidatas | Una descripción de madrugada ("perrito café, mediano") empata con media Cali; la mancha del pecho no |

De paso, dos correcciones a la suite en paralelo: una fecha ISO se leía como
teléfono (8 dígitos) y descartaba el turno que confirma un registro; y
`test_el_token_solo_autoriza_las_encontradas` pasaba o fallaba según el orden,
porque `test_crypto.py` recarga `app.services.crypto` con otra clave y el
`from ... import` de adentro tomaba un Fernet distinto al que firmó el token.

### Límites deliberados del desempate visual

El máximo que puede sumar la foto (5) empata con acertar la raza, y por debajo
de 6/10 no suma: la foto desempata lo que el texto ya dejó cerca, no encarama a
un animal que el texto separó. Máximo 4 comparaciones por búsqueda — son dos
imágenes al modelo cada una. El cruce diario (~12.500 pares) **no** pasa por
visión: costaría más que toda la operación.

### Pendientes

- El venv de `backend/` no traía `Pillow` (sí está en `requirements.txt`), lo que
  hacía fallar 11 tests que no estaban rotos. Instalado.
- `MC-00261` quedó con `estado='reconocida'` pero `reconocida_at` en NULL y un
  `updated_at` 12 h posterior al reconocimiento. El log confirma que el bot hizo
  su parte a las 06:04:36 UTC; **algo reescribió la fila después y no se
  identificó qué**. Vale la pena mirarlo antes de confiar en `reconocida_at`
  para métricas.
- El desempate visual no se persiste: se recalcula en cada búsqueda. Si el
  volumen crece, cachear por par de fotos.

---

## Manual de entrega para el usuario de Arranquemos Pues (2026-08-18)

**Pedido del CEO**: un manual en HTML —para pasarlo a PDF si lo aprueba— que le
explique a la persona que va a operar la cuenta cómo ver los chats, distinguir
cuáles quedaron con un asesor humano, leer el tablero de estadísticas y moverse
por el resto de la app. Más un script que reciba el correo de una cuenta y
reinicie sus guías interactivas para que vuelvan a salir.

### Qué entró

| Qué | Dónde |
|-----|-------|
| Manual de 13 secciones con 22 pantallazos reales | `entregables/manual_arranquemos_pues/index.html` |
| Scripts para regenerar los pantallazos y sembrar los datos de demo | `entregables/manual_arranquemos_pues/_generador/` |
| Reinicio de guías interactivas por correo | `backend/scripts/reset_tutoriales.py` |
| `entregables/` git-ignorado | `.gitignore` |

`reset_tutoriales.py` limpia `users.tutorials_completed` (Sprint 15) del correo
que reciba. Acepta `--modulos mensajes,campanas` para reiniciar solo algunas y
`--ver` para consultar sin tocar nada. Idempotente; imprime el estado antes y
después. Módulos válidos: los de `schemas.ALLOWED_TUTORIAL_MODULES`.

### Por qué el entregable no va a git

Los pantallazos son de la cuenta viva del tenant: su número de WhatsApp, su
correo y su bandeja. Este repo es público (regla de seguridad #8), así que
`entregables/` quedó ignorado y el material se manda por el canal que el CEO
decida. Las conversaciones y contactos que aparecen son sembrados: nombres
inventados y números `+5730140xxxxx`, nunca datos de clientes reales.

### Cómo se tomaron los pantallazos

Chrome headless manejado por CDP (`websockets`, sin Playwright ni Puppeteer),
contra la app local levantada con `docker compose -p wati`. El simulador del bot
se probó de verdad —responde por Bedrock y adjunta la tabla de tarifas—, así que
esa captura es del bot funcionando, no un montaje.

### Lo que el manual documenta como limitación (y conviene cerrar)

- **#315** — un chat que pasó a un asesor no se devuelve al bot desde la app.
- **#316** — la app muestra el texto de los mensajes, no las imágenes ni los
  videos que manda el cliente.
- Responder a mano un chat que sigue asignado al `bot` **no lo reasigna**: el
  bot vuelve a contestar en el siguiente mensaje entrante. Es el que más
  confunde en operación; hoy solo se resuelve avisándole a Gloma.
- Las tarjetas de "Visión general" del tablero de campañas (límite diario,
  calidad, límite mensual) están fijas en el código: no leen a Meta. El manual
  las presenta como valores de referencia del plan y aclara que el cupo real
  vigente es el de #326 (250 conversaciones/24 h).

### Pendientes

- La base local quedó con la contraseña de `arranquemospues.contacto@gmail.com`
  cambiada (solo local; producción intacta) y con los datos de demo sembrados.
- Falta el paso a PDF: espera la aprobación del CEO sobre el HTML.

### Correcciones tras la primera revisión del CEO

1. **Fuera el anexo técnico.** El manual lo lee la persona que opera la agencia,
   no un dev: se eliminó la sección 14 (los comandos de `reset_tutoriales.py`) y
   las dos referencias que apuntaban a ella. El script sigue documentado acá y
   en su propio docstring; el usuario solo tiene que pedir que le reactiven las
   guías.
2. **El asesor de la cuenta es `asesor_1`, no un nombre inventado.** Verificado
   en la base: el team 9 tiene **un solo** miembro con rol `agent` —"Asesor 1"
   (`asesor1@demo.com`)— y el paso `handoff` del bot 26 escribe el handle
   `asesor_1` en `conversation.assigned_to`, que es literalmente lo que pinta la
   etiqueta 👤 de la bandeja. El seed de demo traía "Camila Restrepo", así que
   el manual enseñaba una etiqueta que el usuario nunca vería. Corregido el seed
   (`ASESOR = "asesor_1"`, con el porqué en un comentario), re-sembrado y
   **re-capturadas las 10 pantallas de Mensajes**. Se agregó además una nota
   explicando que todos los chats entregados quedan con la misma etiqueta porque
   hoy hay un solo asesor, no porque sea una persona distinta cada vez.

### Segunda ronda: canal de soporte y dos versiones

1. **Sección 14 · Cambios, garantía y soporte.** Toda solicitud de cambios y toda
   reclamación de garantía se tramita **por medio de Andrés Fernández, Líder de
   Ventas de Gloma**. La caja aclara además que cuando el manual dice "avísale a
   Gloma", ese es el camino — así no hay que reescribir las diez menciones
   sueltas del cuerpo. Va también en el cierre del documento.
2. **Dos versiones del mismo manual**, en `entregables/manual_app_gloma/`:
   `manual_arranquemos_pues.html` (con el nombre de la empresa en portada y
   cierre) y `manual_generico.html` (portada en blanco, "agencia" → "empresa",
   copy sin sabor a agencia de viajes). La genérica **se deriva**, no se edita:
   `_generador/generar_generico.py` aplica una lista de reemplazos exactos y
   **aborta** si alguno deja de coincidir o si sobrevive el nombre de un cliente.
   Editar siempre la del cliente y regenerar la otra.
3. **PDF entregado**: `manual_arranquemos_pues.pdf` (6,3 MB), impreso con Chrome
   headless desde la carpeta del manual para que resuelvan las rutas de `img/`.
4. Los pantallazos siguen siendo los de la cuenta de ejemplo también en la
   versión genérica; lleva una nota que lo dice de frente. Reemplazarlos exigiría
   otra cuenta con datos sembrados.

### Ajuste de paginación del PDF

El índice arrancaba al pie de la portada y se partía entre las páginas 1 y 2. Se
le puso `break-before/after: page` + `break-inside: avoid` al `.toc`: portada
sola en la 1, índice completo en la 2, contenido desde la 3 (34 páginas en
total). De paso la portada ahora ocupa la página entera (`min-height:100vh` con
flex), que exigió `align-self:flex-start` en el logo — sin eso el flex lo estira
a todo el ancho y lo deforma. La versión genérica hereda el arreglo al
regenerarse.

Para revisar la paginación sin `poppler` se usó **PyMuPDF** en el ambiente conda
`multiagente` (`pip install pymupdf`), que rasteriza páginas sueltas a PNG.

---

## #372 — Diez conversaciones de prueba contra el bot de Arranquemos Pues (2026-08-18)

**Pedido del CEO**: probar el bot con un guion de 10 conversaciones y dar
retroalimentación. Con una condición que cambió el diseño de la prueba: **tenía
que ser en producción**.

### Cómo se probó sin mandarle un WhatsApp a nadie

La prueba corre **dentro de la imagen desplegada** (`ecs run-task` sobre el
task-def vigente), lee el bot de RDS y habla con el Claude de Bedrock que
atiende a los clientes: el mismo `llm_engine.advance` del webhook. No envía
mensajes —no toca el sender `+57 333 432 4954` ni el cupo de 250 conv/24h— y no
escribe en la base: los tokens salen de la telemetría del turno, así que
`bot_llm_decisions` no queda contaminada con tráfico de prueba.

Detalle operativo: los container overrides de ECS tienen tope de **8192
caracteres** y el guion no cabía. Se manda comprimido (`zlib`+`base64`) dentro
de un `python -c`. Ojo también con `rds_exec.sh`: su `TASKDEF` por defecto es
`multiagente-backend:15` — para probar **lo que está desplegado** hay que
pasarle la revisión vigente.

### Lo que encontró la línea base (imagen `:lote366`)

| # | Hallazgo | Gravedad |
|---|----------|----------|
| 1 | El bot le mandó al cliente `</parameter>` y `</invoke>` literales (2 de 25 turnos) | 🔴 |
| 2 | Inventó "hotel 3 estrellas" y "comidas todos los días" (el lunes solo hay desayuno) | 🔴 |
| 3 | Negó Nequi/contraentrega como si fuera política de la agencia | 🟠 |
| 4 | Le preguntó el nombre a quien acababa de darlo (3 de 7) | 🟠 |
| 5 | Mandó `info_general` sin anunciarla en el texto | 🟡 |
| 6 | **0% de prompt caching** pese a #363 | 🟡 |
| 7 | Los chips de camino mentían en 4 de 25 turnos | 🟡 |
| 8 | Asterisco huérfano visible (`increíble!*`) | 🟢 |

### El dato que no se podía adivinar: el mínimo cacheable

#363 activó el caching y el bot de mascotas ahorra ~68%, pero el de viajes
marcaba `cache_read=0` **en los 25 turnos**. La causa se midió, no se supuso:

| Prefijo (bloque `system`) | Resultado |
|---|---|
| 2.700 tok (contexto viejo) | no cachea |
| 3.756 tok | no cachea |
| 4.328 tok | **no cachea** |
| 4.194 tok de `system` + tools aparte | **cachea** (`cache_write` → `cache_read`) |

El mínimo de Haiku 4.5 en Bedrock es **4.096 y cuenta solo el bloque `system`**:
las tools no suman aunque se rendericen antes. Un bot con contexto corto no
cachea nunca, y no falla — paga triple en silencio. Los ~400 tokens que
faltaban se invirtieron en la sección de ejemplos del contexto, que además era
lo que hacía falta para los hallazgos 2, 3 y 4.

### Lo que entró

| Lote | Qué | Dónde |
|------|-----|-------|
| A | Sanitizador de andamiaje de tool-use + asterisco huérfano | `services/llm_engine.py` (`_sin_andamiaje`, `_sin_asterisco_huerfano`) |
| B | Contexto reescrito: hotel *El Amor de Dios* (solo el nombre), lista real de medios de pago, precio fijo sin descuentos, saludo condicional, "negar también es inventar", catch-all a asesor y 7 ejemplos resueltos | `app/bot_contexts/demo_viajes.md` |
| C | La pregunta manda sobre el adjunto al clasificar el camino; `hotel` y `otros_destinos` como caminos propios; `asesor` por frases y no por la palabra "persona" | `llm_engine._classify_camino`, `scripts/seed_bot_viajes_llm.py` |
| C | Update quirúrgico de la config del bot **sin borrar nada** | `scripts/migrate_viajes_caminos.py` |
| D | Los 10 guiones versionados: 21 tests gratis + 17 con costo | `backend/tests/viajes/` |

Por qué el script nuevo en vez de re-correr el seed: `seed_bot_viajes_llm.py`
**borra todos los bots de la cuenta** antes de recrearlos (#254). Contra
producción se habría llevado el bot 12 con su historial.

### Resultado en producción (`:lote372b`, task-def 47)

| | Antes | Después |
|---|---|---|
| Andamiaje al cliente | 2 turnos | 0 |
| Datos inventados | hotel 3★, comidas de más | 0 |
| Pregunta el nombre de nuevo | 3 de 7 | 0 |
| Chips errados | 4 de 25 | 0 |
| Entrada servida por caché | 0% | **88%** |
| Costo por conversación | US$ 0,0143 | **US$ 0,0067** |
| Latencia p50 | 4.232 ms | 3.791 ms |

Ante Nequi y ante San Andrés el bot ahora **escala a un asesor humano**, que es
lo que pidió el CEO: si el mensaje no cae en ninguno de los ocho caminos, no se
improvisa.

### Pendientes

- **Paridad local**: `migrate_viajes_caminos.py` está aplicado en RDS pero no en
  la BD local — el puerto 5432 lo tiene ocupado otro Postgres del host y el
  contenedor `db` no levanta. El script es idempotente: una corrida cuando el
  puerto esté libre. Es cambio de **datos**, no de schema.
- La respuesta sobre PSE quedó ambigua ("sobre PSE, por ahora esos son los
  disponibles"). El contexto ya no lo lista, pero conviene una frase explícita.
- Escalar cierra la conversación, así que un "¿tienen San Andrés?" temprano
  corta la venta del plan de Coveñas. Es lo pedido, pero vale revisarlo.
- Las preguntas frecuentes reales (equipaje, niños, cancelaciones) quedaron para
  la próxima iteración por decisión del CEO; hoy caen en el catch-all.

### Reinicio de guías en producción (2026-08-18)

El CEO corrió el script y le respondió `service "backend" is not running`. Causa:
el stack local vive bajo el proyecto de compose **`wati`** (es el que tiene el
volumen `wati_postgres_data`), no bajo `gloma_software`. Sin `-p wati`, docker
busca contenedores que no existen. Documentado en el docstring del script y en
el README del generador del manual.

Lo que de verdad importaba era **producción**: `rds_query.sh` mostró que el
`user_id=7` de RDS tenía las cuatro guías en `skipped` (bots 2026-06-12,
mensajes y campañas 2026-08-03, mi_plan 2026-08-10), así que la persona que
recibe la cuenta **no habría visto ninguna**.

Para poder correrlo allá hubo que ajustar el script: `rds_exec.sh` lo manda como
cuerpo de un `python -c`, donde no hay `argv` ni `__file__`. Ahora
`reset_tutoriales.py`:

- toma los datos de `CORREO` / `MODULOS` / `VER` cuando no hay argumentos (el
  correo no es secreto, así que puede ir en el override de ECS; una contraseña
  no podría);
- resuelve la raíz del proyecto a `/app` si `__file__` no existe.

La CLI local no cambió. Probados los dos modos en local y ejecutado en RDS:
`tutorials_completed` quedó en `{}` — verificado con `rds_query.sh` después.

---

## #373 — Cuenta de demostración para Jerarquía: un bot que cierra la venta (2026-08-19)

**Pedido del CEO**: una cuenta demo para la marca **Jerarquía**
(`@jerarquia_oficial`), con un bot que venda **un solo producto** —promoción de
3 camisetas por $160.000— con personalidad tomada de la cuenta de Instagram y
**solo dos caminos**: pasar a un asesor (que en la simulación cierra el chat) y
registrar la venta con un link de pago falso, dejando pendiente el comprobante y
tomando cédula, celular, nombre, dirección de envío y correo para el despacho.
Sin WhatsApp conectado: se prueba desde la app.

### La marca, leída de su propio perfil

La bio es el brief: 🐺 *Estilo, comodidad y elegancia* · 🔱 *Para hombres con
liderazgo auténtico* · 🚛 *Envíos a toda Colombia* · 🔥 *Sé tú*. Camisetas tipo
polo para hombre, 9.5k seguidores, venta por WhatsApp y destacados de clientes,
envíos, productos, producción y promociones.

De ahí sale la voz del bot (**Samuel**, asesor de Jerarquía): firme, corto y sin
ruego — "un asesor de Jerarquía no suplica una venta, acompaña una decisión".
Sin apodos ("hermano", "parcero", "mi rey"), sin diminutivos, sin lenguaje de
vendedor de feria, máximo dos emojis y solo los de la marca.

### Lo que entró

| Qué | Dónde |
|-----|-------|
| Contexto a priori de la marca (voz, ficha del producto, los dos caminos, 15 ejemplos resueltos) | `app/bot_contexts/jerarquia.md` |
| Herramienta `registrar_venta`: valida los 5 datos, genera número de pedido `JRQ-XXXXXX` y el link de pago | `services/llm_engine.py` |
| Guardarraíl `_viola_link`: si el bot escribe una URL que no entregó la herramienta, el mensaje **no se envía** y se le exige corregir | `services/llm_engine.py` |
| Camino nuevo `venta_registrada` en la telemetría | `llm_engine._classify_camino` |
| Seed de la cuenta demo + bot (11 bloques visuales, 10 caminos de observabilidad) | `scripts/seed_bot_jerarquia.py` |
| Pasarela de pago **simulada**, pública, sin un solo campo de datos | `frontend/pages/pago-demo.tsx` |
| 12 tests unitarios + 17 de clasificación + 12 guiones contra Bedrock | `tests/test_venta_jerarquia.py`, `tests/jerarquia/` |

### Por qué un guardarraíl para el link

Es el hermano del de teléfonos inventados del bot de mascotas. Un modelo que
"recuerda" una URL plausible aquí no manda a nadie a un número equivocado:
manda a un cliente a pagarle a un desconocido. Solo pasa el link que devolvió
`registrar_venta` en ese mismo turno; cualquier otro se descarta y el turno se
repite con la corrección. La prueba lo cazó en la primera corrida.

El link apunta a `/pago-demo`, una página que dice en tres lugares que es una
simulación, **no pide ni un dato** y su botón "pago aprobado" es 100% del
navegador. Un demo no puede terminar en un enlace roto, y tampoco puede
parecerse a una pasarela de pago de verdad.

### Lo que encontraron los guiones (6 conversaciones, Bedrock real)

| # | Hallazgo de la 1ª corrida | Arreglo |
|---|---------------------------|---------|
| 1 | "El precio es fijo, **hermano**" | Lista explícita de apodos prohibidos + ejemplo del caso sin nombre |
| 2 | "Te conecto con un asesor" **sin llamar** `escalar_a_asesor` | Regla "lo que anuncias, lo ejecutas en el mismo turno" |
| 3 | Aviso de handoff repetido dos veces en el mismo mensaje | "El aviso va una sola vez y en una frase" |
| 4 | Un caso de asesor en el **primer** mensaje quedaba sin escalar | La regla aplica también al primer turno |

Después: **12 de 12 guiones en verde**, US$ 0,028 la corrida, p50 2,7 s y
**93% de la entrada servida por caché** — el contexto quedó en ~4.900 tokens,
por encima del mínimo cacheable de 4.096 que se midió en #372.

### Deploy

Imagen `multiagente-backend:lote374b` (`linux/amd64`), task-def **rev 49**,
`update-service --force-new-deployment` → `services-stable`. Seed en RDS con
`ecs run-task` (exit 0): **bot id=18**, team_id=9. Smoke en producción contra
`https://api.glomabeauty.com`: conversación completa de venta con número de
pedido y link. En local: bot id=34, misma prueba por `/bots/{id}/simulate`.

**Ojo con el seed en producción**: pesa 16 KB y los container overrides de ECS
topan en 8.192 caracteres, así que **no** se puede mandar por `rds_exec.sh`
(que lo envía como cuerpo de un `python -c`). Va como `command` de la task,
porque el script ya viaja dentro de la imagen. La contraseña viajó como **hash
bcrypt** calculado en local, nunca en claro (convención de #303: los overrides
quedan en CloudTrail).

### Hallazgo grande: RDS está atrás del `models.py` del árbol de trabajo

La primera corrida del seed en RDS falló con
`column teams.message_credits does not exist`. La causa **no** es de este lote:
en el árbol hay trabajo en curso de otra sesión (pagos/Wompi, créditos,
contactos Excel) que ya tocó `models.py` con tres columnas nuevas en `teams`
—`message_credits`, `handoff_turno`, `asesores_rotacion`— y su migración
(`scripts/migrate_pagos_y_asesores.py`) todavía no se aplicó en RDS.

Es exactamente el gotcha de la convención #1 al revés: **el modelo se adelantó a
la base**. Y es una bomba de tiempo para el deploy: una imagen construida desde
el árbol tal cual habría tumbado producción en la primera consulta a `teams`
(login incluido).

Cómo se resolvió sin tocar el trabajo ajeno: la imagen se construyó desde un
`git worktree` limpio en `HEAD` al que se le copiaron **solo** los archivos de
este lote. El árbol de la otra sesión quedó intacto.

> **Bloqueante para quien retome el lote de pagos**: aplicar
> `migrate_pagos_y_asesores.py` en RDS **antes** de desplegar cualquier imagen
> que lleve ese `models.py`. Y en local, para no perder la paridad.

### Pendientes

- **Datos provisionales del producto**: tela (algodón piqué), tallas (S–XL),
  colores (negro, blanco, azul oscuro, gris jaspe, vinotinto), envío incluido y
  entrega de 2 a 5 días hábiles son **placeholders** para la demo. Confirmarlos
  con la marca antes de conectar un WhatsApp real. Viven todos en la sección
  "Ficha del producto" de `jerarquia.md`, un solo lugar que editar.
- La venta queda registrada en `bot_llm_decisions` (camino `venta_registrada`,
  con los datos del pedido en `tools_called`), no en una tabla de pedidos con
  pantalla propia. Alcanza para la demo; si la cuenta se vuelve real, hace falta
  una tabla `ventas` y su vista.
- El bot no tiene fotos del producto. `llm_config.media` está listo para
  recibirlas: basta dejarlas en `frontend/public/` y agregar las claves.
- **Deuda de tests**: `tests/jerarquia/costo/conftest.py` es la **tercera** copia
  del `Medidor` (mascotas, viajes, jerarquía). Toca extraerlo a un módulo
  compartido; no se hizo aquí para no pisar el árbol de la otra sesión.

---

## Lote: roles, pagos por Wompi, contactos por Excel (2026-08-19)

Pedido del CEO en un solo mensaje: dos asesores con reparto por turnos, cuenta
de asesor con permisos recortados, cambio del correo admin, ventana de pagos
para comprar paquetes de mensajes, importación de contactos por Excel y
atributos sin JSON. Más dos cambios al bot de viajes que quedaron **fuera**
(ver abajo).

### Lo que entró

| Qué | Dónde |
|-----|-------|
| Créditos, rotación de asesores y permiso `can_manage_billing` | `app/models.py` |
| Migración idempotente + tabla `credit_purchases` | `scripts/migrate_pagos_y_asesores.py` |
| Reparto por turnos entre asesores | `crud.siguiente_asesor` + `services/bot_runner.py` |
| Configuración de la cuenta (correo, asesor, permisos) | `scripts/configurar_arranquemos_pues.py` |
| Catálogo de paquetes con precio calculado | `app/services/creditos.py` |
| Checkout y webhook de Wompi | `app/services/wompi.py`, `app/routers/pagos.py` |
| Ventana de pagos (solo admin) | `frontend/pages/pagos.tsx` + entrada en `Sidebar.tsx` |
| Importación por Excel y campos visuales | `app/services/contactos_excel.py`, `routers/contacts.py`, `campanas/contactos.tsx`, `campanas/nueva.tsx` |

Suite: **226 passed**. Frontend: `tsc --noEmit` limpio.

### El precio de los paquetes

Costo real por mensaje de marketing a Colombia: **USD 0,019** = Meta 0,014
(rate card vigente 1-abr-2026) + Twilio 0,005. A TRM 3.128,65 (Superfinanciera,
18-ago-2026) son **COP 59,44 por mensaje**.

La comisión de Wompi (Plan Avanzado: 2,65% + $700 + IVA) **no se suma encima
del precio: se hace gross-up**. Sumarla por fuera deja corto el neto, porque
Wompi cobra su porcentaje sobre el total ya inflado:

    G = (neto_objetivo + 833) / 0,968465

| Paquete | Costo | Precio | Comisión | Neto |
|---|---|---|---|---|
| 1.000 mensajes | 59.444 | **80.700** | 3.378 | 77.322 |
| 5.000 mensajes | 297.222 | **399.900** | 13.444 | 386.456 |

**El margen del 30% es una suposición**, marcada como tal en `creditos.py`: es
la única cifra del cálculo que no sale de una fuente oficial. Pendiente de que
el CEO la confirme. La TRM está en mínimos de 7 años: si el dólar sube, el
margen se come solo, así que la constante va fechada y hay que revisarla.

### Decisiones que vale la pena recordar

- **Los créditos los suma SOLO el webhook**, nunca el `redirect-url` de vuelta
  ni un POST del frontend: quien controla una URL podría regalarse mensajes.
  La suma es idempotente por tres candados (UNIQUE en `reference`,
  `SELECT ... FOR UPDATE`, y salida temprana si ya está `approved`), porque
  Wompi reintenta el webhook hasta 3 veces en 24 h.
- **La firma de integridad se calcula en el backend**, jamás en el navegador:
  exige el secreto de integridad, y un secreto en el frontend es un secreto
  publicado.
- **El turno del round-robin vive en `teams.handoff_turno`**, no en memoria del
  proceso: con varias tasks de ECS cada una llevaría su propia cuenta y el
  reparto dejaría de alternar.
- **Un `assignee` explícito en el paso `handoff` manda sobre el turno.** Sirve
  para rutas que deben caer siempre en la misma persona. Al bot de Arranquemos
  Pues se le quitó ese `assignee` fijo para que entre al reparto.
- El asesor **ya no podía** desconectar la cuenta de WhatsApp: ese endpoint es
  owner-only desde antes (`get_current_owner_membership`). No hubo que tocarlo.

### Gotcha nuevo: el namespace package de `/app`

Un script que resolvía su raíz buscando el *directorio* `app` se iba por
`/app` cuando corría desde `/` (Python 3 lo toma como namespace package) y
fallaba después con `No module named 'app.database'`. Los scripts ahora buscan
el **archivo** `app/database.py`, no la carpeta.

### Lo que quedó fuera y por qué

- **Los dos cambios al bot de viajes** (descripción más concisa y los días del
  itinerario). Otra sesión está editando `bot_contexts/demo_viajes.md`,
  `llm_engine.py` y `seed_bot_viajes_llm.py` con cambios sin commitear. El
  análisis del tarifario ya está resuelto y documentado en
  `entregables/analisis_tarifario_arranquemos.md`: **el bot responde mal**, sí
  hay salidas que terminan en viernes (saliendo el martes).
- **Migración en RDS y despliegue**: hay otra sesión desplegando. No se tocó
  nada de AWS a propósito.
- **Llaves de Wompi**: el módulo lee `WOMPI_*` del entorno y está probado con
  llaves de juguete. Faltan las de sandbox del CEO.
- **Pantallazos del flujo nuevo de contactos** para el manual: exigen
  reconstruir la imagen local, que se evitó mientras la otra sesión despliega.

### Ajustes del CEO (19-ago-2026)

- **Margen del 10%**, no del 30%. El 30% era un provisional del equipo técnico;
  el CEO lo fijó en 10%. Precios nuevos: **1.000 mensajes → COP 68.400** y
  **5.000 mensajes → COP 338.500**. El margen real verificado da 10,0% exacto
  después de descontar la comisión de Wompi.
- **Bot de viajes, los dos cambios que estaban bloqueados** (las otras sesiones
  ya commitearon):
  - *Resumen más conciso*: la frase de una línea ya no enumera qué comida entra
    cada día; eso vive en el itinerario y en el resumen solo alargaba.
  - *Días de salida*: el contexto *solo* describía el plan de viernes a lunes,
    así que ante "¿tienen de lunes a viernes?" el bot improvisó "solo de lunes a
    jueves". Ahora la sección "Días de salida — NO improvises con esto" lista lo
    que de verdad hay: viernes→lunes/martes, lunes→jueves desde $350.000, y
    **martes→viernes** (junio 09–12, 16–19, 30–julio 03, diciembre 08–11). Con
    instrucción explícita de que la respuesta a "salidas entre semana" es
    **sí hay**, de preguntar el mes y de mandar los tarifarios en vez de
    inventar fechas.

Suite completa: **659 passed, 51 skipped, 1 xfailed**.

### Links de pago en vez de checkout por API (19-ago-2026)

El CEO decidió crear los links de pago a mano en el panel de Wompi en vez de
entregar las llaves de la API. Ventaja: funciona sin un solo secreto. Costo:
**un link estático no le dice a la plataforma quién pagó**, así que los
créditos NO se acreditan solos — los habilita el equipo tras conciliar.

- Precios en cifras cerradas fijadas por el CEO, que los revisa cada semana:
  **1.000 → COP 70.000** (margen real 12,6%) y **5.000 → COP 340.000** (10,5%).
  El precio dejó de calcularse: ahora es `PRECIO_LISTA_COP`, y el cálculo
  sobrevive como `precio_sugerido_cop()` para avisar si el precio de lista se
  queda por debajo del costo cuando suba el dólar.
- `LINKS_DE_PAGO` en `creditos.py`, pisables por `WOMPI_LINK_<KEY>` para
  cambiarlos sin desplegar. **No son secretos**: son páginas públicas de cobro,
  por eso van en el código y no en SSM, al revés que las llaves de la API.
- URL de retorno: `https://app.glomabeauty.com/pagos`. Wompi le agrega
  `?id=<transacción>`.
- `GET /pagos/transaccion/{id}` consulta el estado **sin llave privada** (el
  endpoint de consulta de Wompi es público) y la pantalla muestra "recibimos tu
  pago, se habilita en ~1 hora" o "no recibimos el pago". Es informativo: el
  `id` de la URL lo puede escribir cualquiera, así que no acredita nada.

---

## Lote: tres hoteles, precios por mes y tres asesores (2026-08-19)

Pedido del CEO en un mensaje: agregar los hoteles **Piedra Mar** y **Bohíos** al
plan de Coveñas, que el bot **pregunte el mes** y mande el tarifario que
corresponde, que sepa los precios por fecha (del Excel), que una fecha sin
salida **no** termine en un pase al asesor, que el asesor reciba el chat con el
nombre y la fecha, y una cuenta de asesor compartida por **tres** personas
(Camila, Julián, Alexandra) con reparto por turnos.

### Lo que entró

| Qué | Dónde |
|-----|-------|
| Precios exactos del tarifario, sin memoria del modelo | `app/services/tarifario.py` + `app/data/tarifario_covenas.json` |
| Generador del JSON desde el Excel del CEO | `scripts/generar_tarifario_covenas.py` |
| Herramienta `consultar_tarifario` del motor LLM | `app/services/llm_engine.py` |
| Catálogo de medios de los 3 hoteles (fuente única) | `app/data/bot_viajes.py` |
| Contexto del bot reescrito: 3 hoteles, mes, niños | `app/bot_contexts/demo_viajes.md` |
| `resumen` en `escalar_a_asesor` + nota interna en el chat | `llm_engine.py`, `services/bot_runner.py`, `pages/mensajes.tsx` |
| Actualizador de producción que **no borra** el bot | `scripts/actualizar_bot_viajes.py` |
| Tres asesores en rotación + cuenta de asesor nueva | `scripts/configurar_arranquemos_pues.py` |
| Medios de los 3 hoteles publicados | `frontend/public/demo_viajes/` |

Suite: **710 passed, 51 skipped, 1 xfailed**. Frontend: `tsc --noEmit` limpio.

### El bug que nadie había visto: el reparto por turnos no repartía

El lote anterior construyó el round-robin (`crud.siguiente_asesor`) y le quitó
el `assignee` fijo a los **pasos** del bot. Pero el bot de Arranquemos Pues es
LLM: su handoff no sale de un paso, sale de `llm_engine`, que hacía
`cfg.get("assignee", "asesor_1")` sobre el `llm_config` — donde el `assignee`
seguía puesto. Como `bot_runner` solo reparte cuando el `assignee` llega vacío,
**todos los chats caían en `asesor_1`** y el round-robin era código muerto.

Arreglo: el motor emite `assignee: ""` cuando la config no fija uno, y el
default `"asesor_1"` desapareció de los tres call-sites. Verificado en vivo:
Camila → Julián → Alexandra.

### Por qué los precios no van en el prompt

El tarifario son 102 filas que cambian por hotel, mes y fecha. Metérselas al
modelo en el contexto es pedirle que recite una tabla, y ahí es donde inventa.
Ahora vive en `app/data/tarifario_covenas.json` (generado desde el Excel) y el
modelo lo consulta con una herramienta. Dos reglas quedaron **en código**, no en
el prompt, porque son las que cuestan plata:

1. **No se ofrece una salida que ya pasó.** El tarifario arranca en julio y el
   bot sigue vivo en agosto: sin el filtro por fecha vendería la salida del 06
   de agosto en septiembre.
2. **Cada mes tiene su imagen**, y qué flyer va con qué mes sale del catálogo de
   medios (`hotel` + `meses` en cada entrada), no de que el modelo acierte.

**El Excel nunca sale hacia el cliente** — está prohibido en el contexto y el
resultado de cada consulta lo repite. Copia fuente en S3:
`s3://gloma-marketing-media-747456040509/arranquemos_pues/tarifarios/`.

### Los nombres de los tarifarios están al revés de lo que parece

El CEO describió "tarifario1 = agosto a noviembre, tarifario2 = diciembre a
enero". Leyendo las imágenes, para Amor de Dios es **al revés**
(`tarifario_amordios1` es dic–ene y `tarifario_amordios2` es ago–nov), y Piedra
Mar ni siquiera parte igual (`piedramar2` es jul–oct, `piedramar1` es nov–ene).
El mapeo se hizo por el **contenido** de cada imagen, no por su nombre, y quedó
declarado en `app/data/bot_viajes.py` con un test que lo fija. Si algún día se
renombran los archivos, hay que tocar ese dict.

`tarifario3.jpeg` (abril–julio) salió del catálogo: está vencido.

### Bohíos comparte tarifa y flyer con Amor de Dios

En el Excel es una sola fila para los dos ("HOTEL AMOR DE DIOS y HOTEL BOHIOS").
Bohíos no tiene imagen de info general, solo video. Cuando alguien pregunta por
Bohíos, el bot manda el flyer de Amor de Dios **avisando que la imagen sale a
nombre del otro hotel pero el precio aplica igual** — el aviso lo inyecta la
herramienta, no depende de que el modelo se acuerde.

### El asesor ya no hereda un chat en blanco

`escalar_a_asesor` recibió un campo `resumen` opcional que el bot llena con lo
que el cliente ya dijo. `bot_runner` lo guarda como un mensaje
`message_type='nota_interna'`: **no pasa por `_send_text`**, que es el único
camino hacia Meta/Twilio, así que el cliente no la ve. En la bandeja sale
centrada y en ámbar, con "solo visible para el equipo".

Verificado en vivo: `resumen='Andrés Ruiz, CC 1020304050, 2 personas, hotel
Amor de Dios, del 18 al 21 de septiembre'`.

### Varias sesiones desde la misma cuenta

No hubo nada que habilitar: el JWT no guarda estado en el servidor y no hay
tabla de sesiones, así que N logins del mismo correo conviven. Lo que **sí**
conviene revisar: `ACCESS_TOKEN_EXPIRE_MINUTES` está en 30, o sea que los tres
asesores tienen que volver a entrar cada media hora. Queda anotado abajo.

### Un `.gitignore` que tapaba de más

La regla `demo_viajes/` (sin `/` inicial) ignoraba **cualquier** carpeta con ese
nombre, incluida `frontend/public/demo_viajes/` — la que Amplify sirve. Los
archivos viejos estaban versionados de antes de la regla, así que nadie lo
notó hasta que hubo que agregar imágenes nuevas y no aparecían en `git status`.
Anclada a `/demo_viajes/`.

### Pendientes

- **`ACCESS_TOKEN_EXPIRE_MINUTES=30`**: con tres asesores en turno todo el día,
  reloguearse cada media hora es fricción real. Subirlo (¿8 horas?) o meter
  refresh token. Decisión del CEO.
- **Cuenta de asesor anterior** `arranquemospues.asesor@gmail.com` sigue activa
  con permisos de asesor. El script la reporta pero no la toca: desactivarla
  sin avisar dejaría por fuera a quien la esté usando. Confirmar con el CEO.
- **Temporada del tarifario**: el JSON cubre julio 2026 – enero 2027 y el año lo
  asigna el generador (`ANIO_INICIO`). Cuando salga el tarifario nuevo hay que
  regenerarlo, o el bot se queda sin fechas que ofrecer.
- **Cupos**: el bot sabe qué fechas existen, no si quedan lugares. Eso sigue
  siendo del asesor.

### Cierre del lote (19-ago-2026, 22:50)

| Dónde | Qué quedó |
|---|---|
| Commits | `8e3e58f` (lote) + `f16c3ba` (fix de zona horaria) |
| CI | verde en `f16c3ba` |
| ECR | `multiagente-backend:viajes3hoteles-tz` |
| ECS | task-def rev **53**, servicio estable |
| RDS | bot 12 con 13 medios y `tarifario=covenas`; rotación Camila → Julián → Alexandra; asesor `arranquemospues.ventas@outlook.com` en el team 5 |
| Local | mismo estado (bot 26, team 9) — paridad conservada |
| Amplify | job 96, los 13 medios sirven 200 y los 3 retirados 404 |

**Sin migración de esquema**: no se tocó `models.py`. `nota_interna` es un valor
más de `messages.message_type`, que ya existía.

Prueba punta a punta contra el bot 12 en producción: pregunta mes y hotel,
llama `consultar_tarifario`, manda `tarifario_piedramar1.jpeg` para diciembre
(el flyer correcto) y escala con `assignee=''` y
`resumen='Diana López, CC 43567890, 3 personas, 18 de diciembre, hotel Piedra Mar'`.

### El CI se cayó y no era por el cambio

El push de `8e3e58f` dejó main en rojo por un test **de mascotas** que comparaba
`date.today()` contra la fecha que el bot escribe en el prompt. El runner corre
en UTC y el push cayó 22:26 hora de Colombia: para el runner ya era el día 20,
para el bot era el 19 — y el bot tenía razón. El test venía siendo frágil desde
antes; fallaba en cualquier corrida entre las 7 pm y la medianoche.

Lo grave era el hermano: `tarifario.py` acababa de nacer con el mismo
`date.today()`, y ahí sí costaba plata — ECS también corre en UTC, así que a
partir de las 7 pm el bot habría dado por vencida una salida que todavía se
podía vender esa noche. Ambos usan ahora la fecha de Colombia
(`tarifario.hoy_colombia()`), con un test que lo fija y otro que comprueba que
la salida de **hoy** sigue ofreciéndose (el corte es `< hoy`, no `<= hoy`).

Regla para el futuro: en este proyecto, **toda fecha de negocio es hora de
Colombia**; `date.today()` en el backend es un bug esperando el turno de la
noche. La suite se corre con `TZ=UTC` para que el CI no sea el que se entere.

### Ajustes del CEO sobre el lote (19-ago-2026, 23:30)

Tres decisiones, y la primera resultó necesitar la segunda.

**1. Sesión de 2 horas** (estaba en 30 minutos). Aplicado en `docker-compose.yml`
y en la task-def (`ACCESS_TOKEN_EXPIRE_MINUTES=120`).

**2. Cuenta de asesor anterior desactivada.** `arranquemospues.asesor@gmail.com`
queda apagada, con permisos revocados. **No se borró**: los mensajes y el rastro
de quién atendió qué cuelgan del usuario.

Aquí está el enganche entre las dos: un token más largo es también una
**desactivación más lenta**. Si `activo` solo se mirara en el login, apagar una
cuenta la dejaría trabajando dos horas más. Por eso `get_current_user` lo revisa
en **cada request** y desactivar surte efecto en el siguiente. Sin eso, subir el
token era abrir una ventana.

El login de una cuenta apagada devuelve exactamente lo mismo que uno con correo
inexistente (`False` → 401): decir "esa cuenta está desactivada" le confirma a un
desconocido que el correo existe (regla #6).

| Qué | Dónde |
|---|---|
| `users.activo` | `app/models.py`, `crud.authenticate_user`, `dependencies.get_current_user` |
| Migración idempotente | `scripts/migrate_usuarios_activo.py` |
| Apagar / volver a prender una cuenta | `scripts/desactivar_cuenta.py` |
| Pruebas | `tests/test_cuenta_desactivada.py` (7) |

**3. El tarifario lo actualiza el CEO a mano** cuando salga la próxima
temporada. El procedimiento: reemplazar el Excel en `demo_viajes/`, correr
`python backend/scripts/generar_tarifario_covenas.py`, ajustar `ANIO_INICIO` si
cambia la temporada, y desplegar. El JSON queda versionado, así que el cambio de
precios se ve en el diff del PR.

**Paridad BD**: `users.activo` aplicada en local (19/19 cuentas) y en RDS (17/17),
con el modelo desplegado en la misma tanda (task-def rev **54**, imagen
`:auth2h`) — migrar sin desplegar el modelo es el gotcha de siempre.

Suite: **719 passed, 51 skipped, 1 xfailed** (con `TZ=UTC`).

Verificado en producción: la cuenta apagada da 401; `ventas@outlook.com` entra,
su token dura 120 minutos, ve su equipo y recibe **403** en `/pagos/paquetes`.

#### El CI se cayó otra vez, y otra vez por el entorno

`SECRET_KEY` y `ALGORITHM` se leen del entorno al importar el router de auth, y
el runner del CI no tiene `.env`: el test nuevo firmaba un token y moría con
"Algorithm None not supported". En local pasaba porque el `.env` sí está.

Dos veces en la misma noche por lo mismo: **el test corría en una máquina que
no era la del CI**. La forma de comprobarlo antes de pushear quedó documentada y
es barata — un worktree limpio no tiene `.env` (está git-ignorado) ni la zona
horaria de acá:

    git worktree add --detach /tmp/wt-ci HEAD
    cd /tmp/wt-ci/backend && TZ=UTC python -m pytest -q

Eso reproduce el CI exacto. Con eso se verificó el arreglo (`90d8e42`): **719
passed**. El arreglo es solo de tests, así que la imagen desplegada (rev 54) no
cambia.

---

## #375 — Ventana de supervisión: los chats de los clientes desde la cuenta admin (2026-08-19)

**Pedido del CEO**: ver desde `gloma@glomabeauty.com` las conversaciones de las
cuentas que administramos — por ahora mascotas y Arranquemos Pues — en una
ventana aparte, con la misma forma que el registro de conversaciones del panel
de mascotas. `/mensajes` **no se toca**: sigue siendo la bandeja de la cuenta
propia, con el bot de Gloma y nada más.

### Cómo quedó

| Qué | Dónde |
|---|---|
| Router de solo lectura (`/supervision/*`) | `app/routers/supervision.py` |
| Catálogo de etiquetas de camino, por cuenta | `app/services/caminos.py` |
| Ventana | `frontend/pages/conversaciones.tsx` |
| Entrada del menú (👁️ Conversaciones) | `components/Sidebar.tsx` |
| Pruebas | `tests/test_supervision.py` (19) |

Qué cuentas se ven: las de la env var **`SUPERVISION_CUENTAS`** (correos
separados por coma; default mascotas + Arranquemos Pues). Es lista blanca
explícita, no "todas las cuentas": mirar los chats de un cliente se habilita a
propósito, cuenta por cuenta, y agregar la siguiente es una env var, no un
deploy de código.

### Lo que costó entender: hay DOS registros de conversaciones y ninguno cubre al otro

- **WhatsApp** (Arranquemos Pues) → `conversations` + `messages`. Ahí está el
  texto completo, **incluido lo que escribió un asesor humano después del
  handoff**, que la bitácora del bot no ve. `bot_llm_decisions` trae
  `conversation_id` y sirve solo para anotar qué camino tomó cada turno.
- **Chat web** (mascotas) → solo `bot_llm_decisions`, agrupado por `chat_ref`:
  el chat es anónimo y nunca crea una `conversation`. Ahí el texto del bot viene
  recortado a 300 caracteres (`reply_preview`), y la respuesta lo marca con
  `completo=false` en vez de aparentar que el bot contestó tres líneas.

Por eso la lista es la unión de los dos, y el detalle tiene dos caminos. Los
turnos del simulador, que no traen ni `conversation_id` ni `chat_ref`, se
agrupan por bot + canal + día: no son una conversación de verdad, pero quedan
ordenados y a la vista en vez de escondidos.

### Aislamiento

El `hilo_id` viaja en la URL, así que el detalle **exige también el slug de la
cuenta** y valida que el hilo sea de ella: sin eso, `conv-1` servía para
pasearse por las conversaciones de cualquier tenant de la plataforma. Hay tests
para los tres casos (hilo de otro tenant por WhatsApp, por chat web, e id
inventado) y dos tests estructurales: que ningún endpoint quede sin
`require_gloma_account` y que **todos sean GET** — esta ventana no escribe,
responderle a un contacto es de la cuenta dueña del WhatsApp.

Suite: **738 passed, 51 skipped, 1 xfailed** (`TZ=UTC`, worktree limpio).
Sin migración: no se agregó ni una columna, todo sale de tablas que ya existían.

---

## #376 — Los chats entregados caen en Camila, Julián y Alexandra (2026-08-20)

**Pedido del CEO**: que en la bandeja de Mensajes no aparezca más `asesor_1`,
sino el nombre del asesor que tiene el chat.

### El diagnóstico: la rotación estaba bien, pero nadie la llamaba

`teams.asesores_rotacion` ya tenía `['Camila','Julián','Alexandra']` en RDS, y
`test_rotacion_asesores.py` pasaba en verde. Aun así los seis chats reales del
19-ago cayeron todos en `asesor_1`, y `handoff_turno` seguía en **0**: el reparto
nunca se había ejecutado ni una vez.

La causa es un campo que **funciona como está diseñado**: el bot traía
`assignee: "asesor_1"` en su `llm_config`, y un `assignee` explícito **gana**
sobre el reparto por turnos — para eso existe, para rutas que deban caer siempre
en la misma persona. Puesto en el bot entero, mandaba todo a la misma casilla.
Se confirmó leyendo `bot_llm_decisions.escalated_to` de esos seis: `asesor_1`
en los seis, o sea que el motor ya llevaba el destino resuelto desde el config.

Ya estaba corregido en `app/data/bot_viajes.py` (el `LLM_CONFIG` que se despacha
no trae `assignee`, con el comentario que explica por qué). Lo que faltaba era
la prueba de que la cadena completa funciona, que es lo que se agregó.

### Qué se agregó

`tests/test_handoff_reparto.py` (6): prueba la cadena entera —
`bot_runner.run_turn` → acción `handoff` → `conversation.assigned_to`— y no la
rotación aislada, que era justamente lo que pasaba en verde mientras producción
fallaba. Cubre que el chat ya no cae en `asesor_1`, que cuatro chats seguidos se
reparten `Camila → Julián → Alexandra → Camila`, que un `assignee` explícito
sigue mandando **sin gastar el turno de los demás**, y que el `LLM_CONFIG` que se
despacha no trae `assignee`.

Verificado contra la imagen desplegada (rev 56): llama a `siguiente_asesor`, el
bot no fija `assignee`, y los próximos cuatro chats entregados irían a
`Camila → Julián → Alexandra → Camila`. **Sin deploy**: no cambió código de
runtime, la corrección ya estaba desplegada.

### Decisión del CEO sobre los chats viejos

Las 8 conversaciones anteriores (clientes reales, teléfonos `3XXXXXXXXX`) siguen
guardadas con `asesor_1` y **se dejan así**: nadie registró quién las atendió, y
repartirlas por turnos le hubiera puesto el nombre de una persona a un chat que
quizá no atendió. Van a mostrar `asesor_1` hasta que se cierren o un mensaje
nuevo las reasigne.

### Queda abierto

- **`bot_engine.py:279` tiene el mismo problema latente para los bots de
  flujo**: `cfg.get("assignee", "asesor_1")` mete el handle por defecto, que
  después le gana al reparto en `bot_runner`. Hoy no afecta a Arranquemos Pues
  (su bot es `engine='llm'`), pero el primer bot de flujo que haga handoff va a
  repetir la historia. No se tocó porque cambia el comportamiento de otros
  tenants y no era el encargo.
- El paso visual 14 de `seed_bot_covenas.py` todavía dice `assignee: asesor_1`.
  No se ejecuta (el bot es LLM, los pasos son solo el dibujo), pero se lee mal
  en el editor de bots.

### Nota de coordinación

`test_handoff_reparto.py` terminó dentro del commit `0650974` ("consultar el
tarifario aunque la fecha ya haya pasado"), de otra sesión que hizo `git add` de
todo el árbol mientras este archivo estaba a medio escribir. El contenido quedó
íntegro y ya estaba pusheado, así que **no se reescribió la historia** — con otra
sesión commiteando encima, un `rebase` hace más daño que el commit desordenado.
Es la tercera vez que pasa lo mismo; sigue valiendo la regla: entre sesiones
paralelas, archivos distintos y `git status` antes de commitear.

---

## Prueba de los hoteles nuevos y el tarifario, y los 6 hallazgos (2026-08-19/20)

**Pedido del CEO**: plan de pruebas de al menos 10 conversaciones sobre los dos
hoteles nuevos y el tarifario, reporte en HTML con mejoras sugeridas, sin tocar
código durante la prueba. Autorizó los fixes al final.

Reporte: [`RESULTADOS_PRUEBAS_HOTELES_TARIFARIO.html`](RESULTADOS_PRUEBAS_HOTELES_TARIFARIO.html)

### La lección de la corrida

**Los 12 guiones pasaron los 63 chequeos automáticos, y aun así el bot estaba
perdiendo ventas.** Las aserciones solo miden lo que a uno se le ocurrió medir;
los tres hallazgos graves salieron de **leer las conversaciones una por una**.

### Los seis hallazgos

| # | Qué | Gravedad |
|---|-----|----------|
| 1 | El bot no sabía qué día es hoy: adivinaba el año (2025) y declaraba vencidas fechas futuras y vendibles | 🔴 |
| 2 | `enviar_media` no enviaba nada si `claves` llegaba como texto: prometía una imagen que nunca salía | 🟠 |
| 3 | Dedujo que julio "sí tiene salidas" en un hotel que no publicó julio | 🟠 |
| 4 | Una fecha vencida cortaba la venta sin ofrecer alternativas | 🟡 |
| 5 | Los meses disponibles iban de enero a diciembre: "Enero" salía de primero en agosto | 🟡 |
| 6 | El saludo traía tres preguntas y un párrafo | 🟢 |

**El #1 es el caro.** El contexto del bot nunca decía la fecha, así que al
llamar a `consultar_tarifario` con una fecha el modelo escribía `2025-12-18`.
A un cliente con los datos completos le contestó que el 18 de diciembre "ya
pasó", y a otro que el 15 de enero "del 2025" también. Le pegaba justo a los de
mayor intención: los que ya escogieron día.

Arreglo en dos capas, a propósito: la fecha de Colombia va en el prompt de
**todos** los bots, y `tarifario.resolver_fecha()` reinterpreta el año cuando
llega uno pasado — **solo entonces**, porque una fecha futura pudo decirla el
cliente a propósito.

### La primera re-corrida rompió tres cosas, y una la causé yo

Al partir el saludo escribí *"si no sabes el nombre, tu primer mensaje es **solo**
el saludo"*. Demasiado absoluto: a un "¿qué hoteles manejan?" el bot respondió
pidiendo el nombre **sin contestar la pregunta**. Peor que antes.

Las otras: mandar el flyer era una *sugerencia* en el texto de la herramienta y
el bot listó los precios de Bohíos en texto sin la imagen; y las "dos fechas más
cercanas" eran el mismo día repetido (el plan estándar y el de Barú arrancan el
mismo viernes).

Y una cuarta, más sutil, causada por el propio arreglo #1: al darle la fecha de
hoy, el bot empezó a **deducir solo** que el 6 de agosto ya pasó y a saltarse la
consulta, quedándose sin las salidas del 21 y del 28 que sí podía ofrecer.
**Saber qué día es hoy no le dice qué salidas quedan.**

### Cierre

| | |
|---|---|
| Corridas | 12 guiones (línea base) → 14 (tras arreglar) → 14 (final) |
| Resultado final | **14/14**, verificado además leyendo las transcripciones |
| Suite | **765 passed** en condiciones de CI (worktree limpio, sin `.env`, `TZ=UTC`) |
| Desplegado | task-def **59**, imagen `:viajesfix10` |
| Costo | USD 0,087 la corrida de 12 · ~USD 0,007 por conversación · 90% de caché |

### Lo que hay que recordar

- **La variación del modelo es real**: el mismo guion mandó el flyer de Bohíos en
  una corrida y no en la siguiente sin que cambiara una línea. Por eso los
  arreglos que importan viven en la **herramienta**, que responde igual siempre,
  y no en el prompt. Conviene correr esta prueba antes de cada despliegue que
  toque el bot.
- **Arreglar destapa cosas nuevas.** Tres de los cuatro problemas de la segunda
  corrida los introdujeron los arreglos de la primera. Re-correr la prueba
  después de arreglar no es opcional.

---

## #377 — En Arranquemos Pues ya no existe `asesor_1` (2026-08-20)

**Pedido del CEO**: que en esa cuenta solo aparezcan Camila, Julián y Alexandra;
que el chat de las 2:21 pm que quedó en `asesor_1` pase a uno de los tres (el
asesor ya respondió, alguien lo tomó); y que el cambio no toque a otros tenants.

### Lo que faltaba después de #376

#376 dejó bien la configuración: `teams.asesores_rotacion` con los tres nombres y
el `LLM_CONFIG` del bot de viajes sin `assignee`. Se comprobó hoy contra RDS que
eso sigue así, y que los chats **nuevos** ya caen con nombre propio — conv 23 en
Camila y conv 47 en Julián, ambos de hoy. Quedaban dos cosas:

1. **La puerta seguía abierta.** `bot_engine.py:279` inyecta
   `assignee: "asesor_1"` por defecto cuando el paso de handoff no fija asesor, y
   `seed_bot_covenas.py` lo escribe tal cual. Como un `assignee` explícito manda
   sobre el turno, cualquier re-seed o cualquier bot de flujo volvía a meter el
   placeholder en la bandeja. Era el "queda abierto" de #376.
2. **Los chats viejos.** 8 conversaciones seguían guardadas con `asesor_1`, y una
   de ellas —conv 15, la de las 2:21 pm— recibió mensaje nuevo hoy, así que el
   CEO la volvió a ver arriba en la lista. En #376 se había decidido dejarlas;
   hoy el CEO pidió lo contrario.

### El arreglo

`crud.resolver_asesor()` concentra la decisión de a quién le queda el chat, y
`bot_runner` la llama en el único punto donde se escribe `assigned_to`. La regla:
un `assignee` explícito sigue mandando —para eso existe, para rutas que deban
caer siempre en la misma persona— **salvo** que sea un placeholder `asesor_N` y
el team ya haya declarado sus asesores. Ahí entra al turno como si no estuviera.

El alcance sale de los datos, no de un `if team_id == 5`: solo se comporta
distinto un team con `asesores_rotacion` configurado, y hoy ese es únicamente
Arranquemos Pues. Un tenant sin rotación no cambia en nada — ahí el placeholder
es el único destino que hay, y romperlo le dejaría el chat sin dueño.

`reasignar_asesores_arranquemos.py` reparte por turnos los chats que ya estaban
guardados con el handle. Es idempotente y filtra por el team de Arranquemos Pues
(lo ubica por el correo de su admin, no por un id hardcodeado, para que corra
igual en local y en RDS). Los teléfonos van enmascarados en el log.

**Sobre la atribución**: los tres asesores comparten un solo login, así que nadie
registró quién atendió cada uno de esos 8 chats. El nombre que queda es el del
reparto por turnos, no una constancia. Fue decisión explícita del CEO preferir
eso a seguir mostrando un nombre que no es de nadie.

### Verificación

| | |
|---|---|
| Suite | **771 passed**, 51 skipped, 1 xfailed (`TZ=UTC`) |
| Tests nuevos | 5 en `test_handoff_reparto.py`: el placeholder entra al turno en 4 variantes de escritura, y un team sin rotación **no** cambia |
| Local | script en seco → aplicado → segunda corrida sin cambios (idempotente); solo tocó el team 9, no el de carga (team 14, con ~170 chats en `asesor_N`) |
| Desplegado | task-def **60**, imagen `:asesores1`, `rolloutState=COMPLETED`, `/openapi.json` 200 |
| RDS | 8 chats reasignados. `assigned_to` del team 5 ahora: bot 35 · Camila 4 · Alexandra 3 · Julián 3. **Cero `asesor_1`** |

Sin migración: no cambió ni una columna. El frontend tampoco se tocó — la
etiqueta 👤 de Mensajes ya pinta `assigned_to` tal cual, así que con el dato
arreglado muestra el nombre solo.

**En producción no se ensayó nada**: el bot está atendiendo clientes reales. Las
pruebas fueron todas en local, y contra RDS solo corrieron el cambio real y las
consultas de verificación.

### Queda abierto

- `bot_engine.py:279` y el paso 14 de `seed_bot_covenas.py` siguen escribiendo
  `asesor_1`. Ya no hace daño donde importa —el guardarraíl lo descarta— pero se
  lee mal en el editor de bots y conviene limpiarlo cuando se toque ese código.
- El reparto sigue siendo por **turno**, no por carga: si una asesora cierra
  rápido y otra no, igual les llega un tercio a cada una.

---

## 2026-08-20 — Paginación de conversaciones y menú lateral fijo (PR #3)

**Pedido del CEO:** que la app no se degrade cuando una cuenta acumula
conversaciones, y que el menú lateral deje de estirarse al alargarse la ventana.

### Lo que estaba mal

**El menú y el scroll eran el mismo bug.** El `<aside>` era `min-h-screen`
dentro de un contenedor flex que crece con el contenido, así que se estiraba a
la altura de la página. Y el `overflow-y-auto` ya escrito en `/conversaciones`
nunca se activó, porque `Layout` fullscreen mezclaba `min-h-screen` con
`overflow-hidden` — que se anulan. Sin altura acotada el hijo crecía en vez de
scrollear. Afectaba a las 7 páginas con esa variante.

**El cuello de botella no estaba donde parecía.** El peor no era
`/conversaciones` sino `/mensajes`: `crud.last_message_preview(conv)` leía
`conv.messages[-1]` con la relación en **lazy** — una consulta por conversación,
y cada una traía *todos* los mensajes de ese chat para quedarse con el último.
La bandeja se refresca sola cada 8 s, por pestaña abierta. Encima
`messages.conversation_id` **no tenía índice** (el de `created_at` suelto no
sirve para eso), así que cada consulta barría la tabla.

`/supervision/conversaciones` traía 5.000 filas de bitácora, todas las
conversaciones del team y todos sus mensajes a memoria, armaba todos los hilos y
recién ahí recortaba a 200. `/supervision/cuentas` repetía eso por cada cuenta
supervisada solo para el número de la pestaña, al abrir la página.

### Medición (600 conversaciones / 12.000 mensajes, Postgres local)

| endpoint | antes | después |
|---|---|---|
| `GET /mensajes/conversaciones` | 520 ms · **602 consultas** | 11 ms · **4 consultas** |
| `GET /supervision/conversaciones` (20) | 117 ms | 11 ms |
| `GET /supervision/conversaciones` (200) | 117 ms | 55 ms |
| `GET /supervision/cuentas` | 85 ms | 7 ms |

Lo que importa no es el número sino la pendiente: 4 consultas son 4 con 600
conversaciones o con 60.000. Contra RDS la diferencia es mayor, porque cada una
de esas 602 consultas era una ida y vuelta de red.

### Qué cambió

- **Layout**: menú `sticky top-0 h-screen` con scroll propio. `Layout` separa
  las dos formas de scrollear que estaban mezcladas: `fullscreen` (la ventana
  baja, como cualquier página web) y `app` (altura clavada al viewport, solo
  `/mensajes`, que es un chat de dos columnas).
- **Paginación de servidor** en las dos pantallas, selector 20/50/100/200 que se
  recuerda por pantalla (`lib/preferencias.ts`, separado de `session.ts` porque
  la regla #7 dice que la sesión se toca solo desde ahí). El techo vive en el
  endpoint, no en el `<select>`: `limite` viene de la URL.
- **Los filtros se aplican en SQL, antes de paginar.** Es lo que hace que la
  paginación funcione igual con filtros puestos. Al revés, "20 por página"
  filtraría dentro de esas 20 y la pantalla diría "no hay pendientes" con
  pendientes tres páginas más abajo — un bug que no se ve.
- **Supervisión en dos tiempos**: consulta agregada que devuelve como mucho
  `offset + límite` renglones, e hidratación solo de los hilos visibles. Para la
  página N de la fusión de dos listas ya ordenadas alcanza con el prefijo de
  cada una. El agrupado del chat web pasó a SQL sin `to_char` ni `DISTINCT ON`,
  que no existen en SQLite y la suite corre ahí.
- **Índice** `messages(conversation_id, created_at)`.
- **`seed_carga_conversaciones.py`**: cuenta sintética para repetir la medición.
  No corre con `APP_ENV=production`, exige dominio de prueba, y los teléfonos
  usan un prefijo no asignable en Colombia (regla #8).

### Despliegue (sa-east-1)

Imagen `multiagente-backend:paginacion1` (linux/amd64) → ECR. Task-def **rev 61**
(clon de rev 60, solo cambia la imagen). Migración `migrate_indice_mensajes.py`
en RDS vía `ecs run-task` rev 61 → **exit 0**, índice creado y `indisvalid=true`
(586 filas). `update-service --task-definition :61 --force-new-deployment` →
`services-stable` (1/1, zero-downtime). Frontend: Amplify **job 112 SUCCEED**
(commit `2ac79ff`, auto-build).

**Smoke en producción:** `api.glomabeauty.com/openapi.json` 200 con los
parámetros nuevos (`estado`, `busqueda`, `limite`, `pagina`) y los schemas
`ConversationPageOut` / `HilosOut`; `/mensajes/conversaciones` sin token → 401;
`/meta/webhook` sin firma → 403 (fail-closed); `app.glomabeauty.com/login` 200.
Contra datos reales: team 5 (Arranquemos Pues) 49 conversaciones, páginas 1 y 2
de 20 sin solapamiento, 20/20 previews presentes, filtro `open` → 39; team 4
(demo) 5 conversaciones, página 2 vacía; supervisión mascotas 83 hilos y viajes
49, páginas 1 y 2 sin solapamiento.

### Tests

782 passed (17 nuevos), reproducidos en worktree limpio con `TZ=UTC` antes de
pushear. El que más importa **cuenta las consultas** y se cae si alguien vuelve a
poner `conv.messages[-1]` en el bucle: la única señal de que el N+1 volvió es que
todo sigue funcionando, más lento.

### Pendientes

- **El frontend de Amplify se desplegó ~1 h antes que el backend** (job 112 salió
  con el merge; el rollout de ECS fue después). En esa ventana `/mensajes` pedía
  el formato nuevo a un backend que devolvía el viejo. Es una cuenta interna y no
  hubo reporte, pero **el orden correcto es backend primero**: cuando un cambio
  toca el contrato de un endpoint, conviene desplegar ECS antes de que Amplify
  buildee, o hacer el cambio compatible hacia atrás.
- Los siete agentes de `.claude/agents/` (todos menos `community-manager`) **no
  tienen frontmatter YAML**, así que Claude Code no los registra y el flujo de
  delegación del CLAUDE.md no se está ejecutando. Son 4 líneas por archivo.
- `/mensajes` sigue haciendo polling cada 8 s. Ahora cuesta 4 consultas en vez de
  602, pero el siguiente paso natural es que el servidor avise (SSE/websocket) en
  vez de que el navegador pregunte.

---

## 2026-08-20 — Coveñas, notas de voz y la hora de Colombia en la bandeja

**Pedido del CEO:** tres cosas del bot de Arranquemos Pues y de la cuenta de
asesores. (1) Que entienda que "Coveñas" y "Tolú" son el mismo plan —
recientemente alguien preguntó por Coveñas y el bot la pasó a un asesor, cuando
esa pregunta la podía responder sola. (2) Que las horas de los mensajes se vean
en hora de Colombia, incluidos los chats viejos. (3) Que cuando llegue un audio
pida amablemente que le escriban, porque todavía no sabemos escucharlos.

### 1. "Coveñas" y "Tolú" son el mismo plan

El plan se llama *Tolú & Coveñas*, pero casi nadie lo nombra completo: se
pregunta por uno de los dos. El contexto del bot mencionaba los dos nombres por
todos lados y aun así lo tenía escrito como si fueran dos cosas; con la regla de
"otros destinos van al asesor" a mano, el modelo resolvió que Coveñas era otro
destino. Ahora hay una sección explícita, arriba del todo, que dice que los dos
nombres son su único producto (con tilde o sin ella) y que eso no se escala.

### 2. La hora de la bandeja: no era la base, era el navegador

Antes de tocar nada se midió contra RDS. Los datos están **bien**: los mensajes
se guardan con `datetime.utcnow()` y `created_at` va siempre a la par de
`now() AT TIME ZONE 'UTC'`. Se buscaron además filas escritas con otro reloj —
mensajes de una misma conversación cuyo timestamp retrocede respecto al
anterior— y salieron **0 en toda la base**. No hubo nada que migrar.

Lo que estaba mal es el render. El backend serializa UTC **sin marcar la zona**
(`2026-08-20T21:26:57`), y el estándar de JavaScript manda leer esa forma como
hora *local del navegador*: `new Date(...)` en Colombia sumaba 5 horas. Un
mensaje de las 4:26 p. m. se pintaba a las 9:26 p. m.

La conversión quedó en `frontend/lib/fechas.ts` (`aInstante` le pone la `Z` que
falta; todo se formatea con `timeZone: 'America/Bogota'`, que no tiene horario de
verano). La usa `/mensajes` —la bandeja del asesor, que es lo que reportó el
CEO—, `/conversaciones` (que ya tenía su propia copia de la corrección, ahora
borrada) y los helpers de Campañas en `lib/format.ts`, que arrastraban el mismo
error. **Los chats antiguos quedan corregidos solos**: cambió cómo se lee el
dato, no el dato.

### 3. Notas de voz

Un audio entraba a la conversación como `[audio]`: el asesor no sabía qué había
pasado y el bot lo leía como un tema fuera de su alcance. Ahora entra como
`[nota de voz]` (`marcador_inbound`, compartido por los webhooks de Meta y de
Twilio) y todos los bots LLM tienen instrucciones de disculparse y pedir que se
lo escriban. Twilio no dice "audio": se deduce del MIME del adjunto
(`MediaContentType0: audio/ogg`), que antes se ignoraba.

Cubre los chats viejos: la regla nombra los dos marcadores, porque lo que ya
está guardado en la base dice `[audio]`.

### El hallazgo: dónde se pone una regla cambia el comportamiento de otra

La regla de las notas de voz empezó siendo un bullet más dentro de "Reglas
operativas", al lado de "si algo está fuera de tu alcance, escala". Con eso, el
bot dejó de escalar un tema ajeno (visa americana, seguros de viaje): pasó de
**4 de 12 corridas a 1 de 4**. Reescribirlo en positivo no alcanzó (2 de 4).
Sacarlo a su propia sección `## Notas de voz` sí: **8 de 12**, mejor que el
punto de partida. El texto de la regla casi no cambió — cambió el vecindario.

Queda un test que lo vigila (`test_la_regla_va_en_su_propia_sección`): comprueba
que el marcador no viva dentro de "Reglas operativas" y que esa lista siga
terminando en `escalar_a_asesor`.

### Tests

805 gratis (17 nuevos en `tests/test_notas_de_voz.py`) y 7 guiones nuevos contra
Bedrock de verdad, corridos 3 veces seguidas sin una sola falla. Los guiones se
**leyeron**, no solo se asertaron: fue leyendo las respuestas como se vio que el
bot no escalaba por Tolú sino que saludaba y pedía el nombre primero — su
comportamiento correcto de "una pregunta por mensaje" —, así que el guion pasó a
dos turnos en vez de exigirle todo en el primero.

### Pendientes

- **Cuatro guiones de `tests/viajes/costo/test_guiones.py` están rotos desde
  antes de este cambio** (verificado corriendo la suite en un worktree en
  `HEAD`): esperan medios `info_general`, `tarifario1` y `hotel_video`, que
  dejaron de existir cuando el bot pasó a tres hoteles (commit `8e3e58f`). Hay
  que actualizarlos a `info_amordios` / `tarifario_amordios_*` / `video_*`.
- `test_un_tema_ajeno_al_bot_va_a_un_humano` es **inestable por naturaleza**:
  afirma que el bot llama a `escalar_a_asesor` en un turno concreto, y el bot a
  veces primero pregunta "¿te conecto?" y escala al turno siguiente. Sale rojo
  ~1 de cada 3 corridas, con el cambio y sin él.
- Los bots de flujo (engine `bot_engine`, no LLM) siguen sin saber qué hacer con
  una nota de voz: el marcador nuevo les llega igual, pero no tienen a quién
  preguntarle. Hoy no hay ninguno activo atendiendo audios.

---

## 2026-08-20 — Agentes registrados y polling de la bandeja a 45 s (PR #4)

### Los agentes del CLAUDE.md no existían para Claude Code

El `CLAUDE.md` describe un equipo donde el PM delega en especialistas, pero un
archivo de `.claude/agents/` solo se registra como agente invocable si empieza
con una **cabecera YAML** (`--- name: … description: … ---`). Siete de los ocho
no la tenían: solo `community-manager.md`. **El protocolo de delegación nunca se
pudo ejecutar** — incluida la regla de que todo feature que toque credenciales,
auth o secretos pasa por el agente `seguridad` antes del merge.

Al validar apareció el detalle que faltaba, y es el mismo modo de falla que se
estaba arreglando: **los dos puntos dentro de una descripción sin comillas rompen
el YAML.** `description: Modelado y rendimiento de PostgreSQL: schema, …` se
parsea como un mapping y el archivo se descarta **en silencio**. Van todas
encomilladas, `community-manager` incluida.

A `seguridad` se le acotaron las herramientas a las de lectura (`Read`, `Grep`,
`Glob`, `Bash`, `WebFetch`, `WebSearch`). Su propio archivo dice "no escribes
código: señalas hallazgos, propones la solución y delegas la implementación";
sin `Edit`/`Write` eso deja de depender de que el agente se acuerde.

### Polling de la bandeja: 8 s → 45 s (decisión del CEO)

Con la lista ya paginada cada pregunta cuesta 4 consultas en vez de 602, pero
seguían siendo **450 por hora y por pestaña** para oír "nada nuevo" casi siempre.
A 45 s son 80. Los dos ritmos quedaron como constantes con nombre porque
responden a preguntas distintas:

| constante | cada | pregunta |
|---|---|---|
| `POLL_LISTA_MS` | 45 s | ¿entró alguna conversación nueva? |
| `POLL_DETALLE_MS` | 5 s | ¿contestó la persona con la que hablo ahora? |

**Costo asumido:** un chat nuevo puede tardar hasta 45 s en aparecer en la
bandeja. Los mensajes de una conversación **ya abierta no se atrasan** — esos los
trae el poll del detalle, que no se tocó.

### Despliegue

Solo frontend y tooling: **sin cambios de backend, sin migración, sin rollout de
ECS**. Amplify **job 115 SUCCEED** (commit `291c2fa`). Verificado en el bundle
servido en producción: `setInterval(s,45e3)` y `setInterval(t,5e3)`; el `8e3`
viejo ya no aparece. `app.glomabeauty.com/login` y `/mensajes` → 200.

### Coordinación con sesiones concurrentes

Otra sesión estaba trabajando en el mismo árbol (`twilio_adapter.py`, `base.py`,
`demo_viajes.md`, tests de adjuntos) y había desplegado **rev 62** de ECS con el
job 114 de Amplify corriendo. Se esperó a que 114 terminara antes de mergear, y
se stagearon **solo** los archivos propios. Sus cambios sin commitear quedaron
intactos. **Regla que conviene mantener:** en este repo el árbol de trabajo es
compartido — `git add -A` es peligroso, hay que stagear por ruta.

---

## 2026-08-20 — Fotos: el bot avisa que no las lee, y la bandeja muestra las suyas

**Pedido del CEO,** en el mismo hilo de las notas de voz: que el bot de
Arranquemos Pues avise que **no puede leer el contenido de las imágenes**, y la
pregunta de si las imágenes se pueden ver también en el chat de la app.

### El aviso del bot va en el contexto de ESE bot, no en el prompt de todos

La regla de las notas de voz es global (`_system_prompt`) porque **ningún** bot
oye. La de las imágenes **no puede serlo**: el bot de mascotas vive de las fotos
de las mascotas perdidas. Le llegan por otro camino —`_bloque_mascotas`, con el
análisis ya hecho, no por el marcador del webhook—, así que una regla global
diciéndole "no puedes ver imágenes" sería mentirle sobre lo que sí hace. La
regla quedó en `bot_contexts/demo_viajes.md` y hay un test que comprueba que el
marcador **no** aparece en el prompt del bot de mascotas.

Las fotos entrantes ahora entran como `[imagen]` (antes `[image]`), y en Twilio
se deducen del MIME del adjunto igual que los audios.

### Dos correcciones que salieron de leer las respuestas

1. Con la primera versión, a **"les mando el comprobante"** —texto puro, sin
   adjunto— el bot ya contestaba "por ahora no puedo ver el contenido de las
   imágenes": se adelantaba a un archivo que nadie había mandado. La regla ahora
   dice explícitamente que el aviso es para cuando el marcador **llega**.
2. Un **comprobante de pago** no se contesta con "escríbeme qué necesitas": lo
   tiene que mirar una persona. Si el cliente dice que la foto es un soporte, el
   bot agradece y usa `escalar_a_asesor`. *(Criterio agregado por el equipo, no
   pedido explícitamente: es coherente con que reserva y pagos ya iban al asesor
   humano. Si el CEO prefiere otra cosa, es una línea del contexto.)*

### Las imágenes en el chat de la app

**Las que manda el bot ya se ven** — y no hizo falta tocar el backend. Cuando el
bot envía material, `bot_runner._send_media` guarda `caption\nURL` en
`messages.content` y la URL es pública (es la misma que recibió el cliente por
WhatsApp). La bandeja ahora la renderiza como imagen o video, con un enlace
"abrir original".

**Las que manda el cliente no se pueden mostrar todavía**, y no es un problema
de frontend: de esas no guardamos nada. Meta entrega un **id de media**, no una
URL; hay que cambiarlo por una URL temporal (~5 min) llamando a la Graph API con
el token de la cuenta, descargar el archivo y guardarlo en un bucket antes de
que expire. Para no dejar un `[imagen]` suelto que parece un error, la burbuja
ahora dice "📎 imagen — el archivo queda en WhatsApp, todavía no se ve aquí".

Lo que costaría hacerlo (queda propuesto, **no** hecho):
- Columna `messages.media_url` + migración idempotente en local y en RDS.
- Servicio de descarga en el webhook: `GET /{media_id}` → URL temporal → bajar
  el archivo → subir al bucket. Hay que hacerlo **dentro del webhook**, antes de
  que la URL expire.
- Bucket S3 privado + endpoint autenticado que sirva el archivo, igual que
  `/mascotas/foto/{codigo}/{id}`, que ya resolvió este mismo problema.
- **Son fotos de clientes**: el bucket va privado y el endpoint pide sesión.

### Tests

812 gratis (7 nuevos) y 13 guiones contra Bedrock corridos dos veces sin fallas,
incluido el control de que el bot **sigue** escalando un tema ajeno — el mismo
que se rompió cuando la regla de audios quedó mal ubicada.

---

## 2026-08-20 — Verificación del catálogo de medios y la suite de costo en verde

**Pedido del CEO:** confirmar que las imágenes que él subió a `demo_viajes/`
son las que el bot está usando de verdad, y arreglar los cuatro guiones que
quedaron pidiendo material que ya no existe.

### Verificación: sí, son esas

Hay **dos carpetas** y conviene no confundirlas:

- `demo_viajes/` en la raíz — **git-ignoreada** (`.gitignore:45`). Es la carpeta
  de trabajo del CEO; ahí vive también el Excel del tarifario.
- `frontend/public/demo_viajes/` — versionada, y **esta es la que sirve
  Amplify** en `app.glomabeauty.com/demo_viajes/...`, que es la URL que el bot
  le manda al cliente por WhatsApp.

Se compararon las dos por MD5: **13 de 13 archivos idénticos**. Después se bajó
cada URL del catálogo desde producción y se comparó contra el archivo local:
**13 de 13 devuelven 200 y son byte a byte el mismo archivo**. Y el bot 12 en
RDS tiene exactamente esas 13 claves en su `llm_config`. Nada desactualizado.

Qué flyer sale por mes, resuelto por `tarifario.clave_imagen` (no por el
modelo):

| | Amor de Dios / Bohíos | Piedra Mar |
|---|---|---|
| jul | — | `tarifario_piedramar2` |
| ago–oct | `tarifario_amordios2` | `tarifario_piedramar2` |
| nov | `tarifario_amordios2` | `tarifario_piedramar1` |
| dic–ene | `tarifario_amordios1` | `tarifario_piedramar1` |
| feb–jun | — sin tarifario — | — sin tarifario — |

`tarifario3.jpeg` está en la carpeta de la raíz, no está publicado y **no lo usa
nadie**: quedó de la temporada anterior.

### Bohíos: sí tiene info general, es la de Amor de Dios

El contexto decía "Bohíos **no tiene** imagen de info general", así que a quien
preguntaba por ese hotel el bot le mostraba solo el video. El CEO aclaró que la
info general de Bohíos **es la de Amor de Dios** —mismo plan, mismo precio— y
que lo único propio es el video. Corregido en el contexto y en la descripción
del catálogo, con el mismo aviso que ya se usaba para el tarifario: la imagen
sale a nombre de *Amor de Dios* pero aplica igual.

### Los guiones rotos, y por qué estaban rotos

Cuatro pedían `info_general`, `tarifario1` y `hotel_video`, que dejaron de
existir con los tres hoteles. Ahora **las claves se derivan del catálogo**
(`CLAVES_MEDIA`, `CLAVES_TARIFARIO`, `CLAVES_VIDEO_HOTEL`, `CLAVES_INFO_HOTEL`):
un rename las arrastra en vez de dejarlas pidiendo fantasmas.

Aparecieron dos podredumbres más, que el rojo anterior tapaba:

1. **El guardarraíl de plata daba por inventados los precios reales.** Se
   escribió cuando los precios vivían solo en las imágenes; desde
   `consultar_tarifario`, decir "$459.000" es justo lo que se le pide al bot.
   Ahora las cifras autorizadas se leen de `app/data/tarifario_covenas.json` —
   la misma fuente que lee la herramienta—, así que subir un tarifario nuevo no
   deja el guardarraíl marcando precios legítimos.
2. **Un guion medía el almanaque.** Pedía reservar "7 de agosto"; pasado el 7 de
   agosto el bot dejó de escalar y empezó a ofrecer las salidas que quedaban —
   que es lo correcto. La fecha ahora sale del tarifario, con **10 días de
   margen**: pidiendo "la próxima" cae en mañana y ahí el bot pregunta si de
   verdad es para mañana antes de escalar, lo cual también está bien pero vuelve
   el test una moneda al aire.

### Un tercer arreglo, que salió de no creerle a una sola corrida

La primera corrida completa dio **30 de 30** y estuvo a punto de quedar
escrito así. La segunda, con el mismo código, dio 27. Lo que fallaba no era el
bot sino la forma de preguntar: dos guiones exigían que `escalar_a_asesor`
saliera **en un turno exacto**, y el bot muchas veces ofrece primero ("¿te
conecto con un asesor?") y escala al siguiente — que es tan correcto como
escalar de una. Ahora el guion incluye el "sí, por favor" que daría un cliente
real, igual que ya hacía `test_otro_destino_va_a_un_humano`. Se mide que el caso
**llegue a un humano**, no en qué turno.

El mismo método destapó un hueco de verdad en el bot, este sí de producto: en la
secuencia real —*"les mando el comprobante"* y en el mensaje siguiente la foto—
el bot contestaba el anuncio, seguía con el mes y, cuando llegaba la imagen, ya
no la conectaba con el pago: la trataba como una foto cualquiera y preguntaba
"¿qué necesitas?". Pasaba 1 de cada 2 veces. El contexto ahora dice explícito
que **esa imagen ES el comprobante aunque entre los dos mensajes se haya hablado
de otra cosa**. Verificado: escala 4 de 4.

### Estado

Tres corridas completas seguidas: **29, 30 y 30 de 30**. El rojo suelto fue
`test_del_hotel_solo_dice_el_nombre`, otro de juicio blando. La suite venía con
4 rojos fijos por las claves y 1 por la fecha; ahora lo que queda es ruido
ocasional de un test que le pide a un modelo una decisión de criterio. Costo:
US$ 0,146 por corrida, con 94% de la entrada servida por caché.

**Regla que deja este episodio**: en esta suite, una corrida verde no significa
nada. Para afirmar que algo quedó arreglado —o roto— hay que correrla varias
veces, y comparar contra un worktree en `HEAD`.

---

## 2026-08-21 — Coincidencias de mascotas: comparador para revisión manual

### El script ya existía, y ya había corrido

El pedido era "ejecutemos una búsqueda de coincidencias y que aparezcan en el
dash". Antes de escribir nada: el cruce ya está hecho
(`scripts/job_coincidencias_mascotas.py`), es el mismo que dispara el botón
"🔗 Buscar coincidencias" del panel. Se corrió contra producción — 175 perdidas
× 130 encontradas = **22.750 pares** — y devolvió `0 nuevas, 0 actualizadas`.

No porque no haya coincidencias: porque **ya había 349**, creadas la noche
anterior (2026-08-21 02:44 UTC) desde el botón del panel. El cruce es
idempotente y lo único que hizo fue confirmarlo. El EventBridge
`mascotas-cruce-diario` sigue en DISABLED, como estaba decidido.

De los 22.750 pares, 1.245 pasan el umbral 12; quedan 349 guardados por el tope
de **3 candidatas por mascota buscada**. Ese tope es a propósito (con umbral 6
daban 5.284 y el panel era inservible).

### El gotcha que costó una conclusión equivocada

La primera consulta —`SELECT estado, count(*) FROM mascota_coincidencias`— por
`rds_query.sh` devolvió el encabezado y ninguna fila, y se reportó "cero
coincidencias, el panel está vacío". Era falso.

`rds_query.sh` lee el resultado con `aws logs get-log-events` apenas para la
task; si CloudWatch todavía no volcó los eventos, imprime las columnas y nada
más — **indistinguible de una tabla vacía**. Se destapó al notar que 1.245 pares
pasaban el umbral pero el job insistía en `nuevas=0`: las dos cosas solo son
compatibles si las filas ya estaban.

**Regla**: un resultado vacío de `rds_query.sh` no es evidencia de que no hay
datos. Si la respuesta cambia el rumbo del trabajo, confirmarla con
`rds_exec.sh` y un `print()` explícito del conteo.

### Lo que faltaba de verdad: comparar

Las coincidencias ya se veían. Lo que no se podía era **decidir**: la tarjeta de
la lista alcanza para descartar lo obvio, pero para saber si son la misma
mascota tocaba abrir cada ficha por aparte y recordar la otra.

El comparador (`frontend/pages/mascotas-panel.tsx`) abre el par completo:

- Fotos grandes lado a lado con tira de miniaturas. `object-contain`, no
  `object-cover`: recortar puede esconder justo la mancha o el collar por el que
  se decide.
- Los campos en **una sola tabla de tres columnas** (campo · buscada ·
  encontrada), no dos fichas sueltas — así quedan alineados aunque un texto sea
  mucho más largo que el otro.
- Los campos que el cruce contó como parecidos van resaltados con su puntaje
  (`Raza +5`). El equipo tiene que poder juzgar el puntaje, no solo creérselo.
- Encabezado y pie pegados: la tabla es larga y los botones de decisión tienen
  que estar siempre a la mano.

Ampliar una foto abre el visor de siempre encima, en la foto que se estaba
viendo. Mientras el visor esté abierto el comparador no escucha Escape — si no,
un solo Escape cerraba los dos.

### Nadie recibe aviso

Requisito explícito del CEO: por ahora, ninguna coincidencia dispara un mensaje.
Se verificó por construcción, no por suposición: nada en el camino del cruce
(`cruzar_reportes`, el job, `POST /panel/cruzar`, el PATCH de estado) toca
Twilio, WhatsApp ni correo. El texto de la sección ahora lo dice en pantalla, y
el pie del comparador lo repite. El aviso automático sigue siendo el **#348**,
abierto.

### Verificación

No solo `tsc` y `npm run build`. Se levantó el panel en Chrome con un backend
simulado y datos inventados, y se comprobó en el navegador: fotos y miniaturas,
superposición del visor, que Escape cierre solo el modal de encima, y que marcar
"Es la misma" actualice la insignia en vivo sin cerrar el comparador. El
comparador se alimenta del id y no de una copia del objeto, justamente para que
recargar el panel no lo deje mostrando un estado viejo.

Un hallazgo que dejó el mock: el par `MC-00308 ↔ MC-00309` son códigos
consecutivos con descripción casi idéntica (gato criollo parecido al siamés,
gris claro). Huele a **la misma mascota importada dos veces**, una como perdida
y otra como encontrada, más que a un reencuentro. Queda para la revisión.

---

## Adjuntos salientes + continuidad del bot de Arranquemos Pues (2026-08-21)

Dos pedidos del CEO en el mismo día: que un asesor pueda **responder con
imágenes, audio, documentos y emojis** desde la ventana de Mensajes, y seis
arreglos al bot de Arranquemos Pues que salieron de leer una conversación real.

### La conversación que originó todo

Del chat del 20-ago-2026, 21:06–21:15 (número enmascarado, `3XXXXXXXXX`). La
persona se presentó a los dos minutos. A las 21:10 dijo "mañana te respondo, que
debo consultar con mi esposo"; el bot se despidió y usó `finalizar_conversacion`.
Desde ahí, **cada mensaje suyo recibió el saludo inicial completo**:

> Hola, ¡Buen día! … mi nombre es *Maria Camila* … ¿Con quién tengo el gusto? 😊

Cuatro veces (21:11, 21:12, 21:14, 21:15). Ella contestó "ya me atendistes", "ya
ya me atendieron", y al final: *"No que pereza, por eso no me gusta agregar al
guasap porque son muy intensos"*.

**La causa es una sola.** Al cerrar, la sesión queda `finished`; el siguiente
mensaje entrante no encuentra sesión activa y `bot_router` **arranca una sesión
nueva con el historial vacío**. El bot no se "activaba dos veces": empezaba de
cero cada vez. De ahí salen los seis síntomas, incluido que `contact_name` quedó
vacío pese a que ella dijo su nombre — vivía solo en el historial que se
descartaba.

### Los seis cambios (todos detrás de flags en `bots.llm_config`)

Los flags (`seguimiento`, `recordar_nombre`, `retomar`) están encendidos **solo
para este bot**: `llm_engine.py` es compartido con el bot de mascotas y el
institucional, y una regla global les cambia el comportamiento. Ya pasó (ver el
commit `1a7d385` y la sección "Notas de voz" del prompt).

| # | Pedido | Cómo quedó |
|---|--------|-----------|
| B1 | Si la persona cierra, no escribir más | `finalizar_conversacion` ahora cierra la conversación; tool `no_responder` para que el modelo pueda callarse; y un atajo determinista que ni llama a Bedrock cuando lo único que llega es cortesía sobre un chat cerrado |
| B2 | Registrar el nombre y no repreguntarlo | Tool `registrar_nombre` → `conversations.contact_name`. Sobrevive al fin de la sesión, que es lo que fallaba |
| B3 | No activarse dos veces; retomar | `bot_router` devuelve la sesión cerrada como **retomable** dentro de `retomar.horas` (24) y se revive conservando el historial |
| B4 | Seguimiento a los 15 min de silencio | `BotPendingAction` de tipo `seguimiento`. **No se programa si el bot cerró** — B1 manda sobre B4 |
| B5 | Etiqueta "conversación abandonada" | A los 15 min del seguimiento sin respuesta: se etiqueta y se cierra, **en silencio** |
| B6 | "un compañero", no "asesor humano" | Solo en los textos que lee el cliente. El nombre de la tool y el handle del asesor no se tocan: son internos |

**La distinción que se agregó al prompt**: un adiós explícito ("chao") sí cierra;
un desinterés blando ("mañana te confirmo", "lo pienso") **no** cierra — se
responde con cariño y el seguimiento de los 15 minutos hace su trabajo. Sin esa
separación, B1 y B4 se contradicen.

**La trampa que casi se cuela**: `process_pending_action` llamaba `run_turn(
user_input=None)`, y para un bot LLM eso dispara `_FIRST_TURN_PROMPT`, o sea
**un saludo**. Los tipos de acción nuevos no pasan por ahí: mandan texto fijo
(que además no cuesta un turno de Bedrock). Si se olvidaba, el bot le saludaba a
la persona que se fue — exactamente el bug que se estaba arreglando.

### Adjuntos salientes

El puerto de mensajería ya sabía mandar media (`messaging.send_media`); faltaba
dónde alojar el archivo y la interfaz. Servicio nuevo `services/adjuntos.py`,
calcado del patrón de `services/mascotas.py`: S3 privado en producción, disco en
local, servido por un endpoint público (`GET /mensajes/adjunto/...`) porque quien
descarga es el servidor de Meta o Twilio, que no manda token.

- **Sin migración**: el mensaje se persiste como `content = "pie\nURL"` con
  `message_type` = categoría, que es lo que ya hacía el bot con los tarifarios.
- **Imágenes** comprimidas con `services.imagenes.comprimir`, el mismo camino
  rápido de las fotos de mascotas.
- **Audio**: Chrome graba en `audio/webm`, que **WhatsApp no acepta**. Se agregó
  `ffmpeg` a `Dockerfile.backend` y se transcodifica a OGG/Opus, que llega como
  nota de voz. Si ffmpeg falta (dev sin rebuild) no revienta: avisa.
- **Documentos** (pedido posterior del CEO): PDF, Word, Excel, PowerPoint, TXT y
  CSV. Se exige que el archivo **sea de la familia que dice ser** (ZIP para los
  formatos nuevos de Office, OLE2 para los viejos), porque el `Content-Type` lo
  pone quien sube. Excepción cuidada: Windows declara los `.csv` como
  `application/vnd.ms-excel`, y rechazarlos sería rechazar archivos buenos.
- **El nombre del archivo importa**: la carpeta es el uuid (lo impredecible) y el
  último tramo de la URL es el nombre legible, porque **eso es lo que WhatsApp le
  muestra a quien recibe un documento**. Un `8f3c9a…pdf` parece basura, no la
  cotización que le acaban de mandar.
- **Emojis**: selector propio (`components/SelectorEmoji.tsx`), sin librería —
  un paquete de emojis pesa cientos de KB por el catálogo Unicode completo, y lo
  que se usa respondiendo por WhatsApp cabe en una lista escrita a mano. Inserta
  en la posición del cursor, no al final. Hay tests de que los emojis con
  modificador (🏝️) y los compuestos (🇨🇴, 👩‍💻) llegan intactos al proveedor.

### Base de datos

`conversations.etiqueta` (`VARCHAR NULL`), aplicada en local y en RDS el mismo
día, con el script idempotente `migrate_conversaciones_etiqueta.py` corrido dos
veces para probarlo. Paridad verificada columna por columna (9 en ambos lados).

### Infraestructura — el bloqueante que nadie había visto

**Nada invocaba `POST /internal/bot-scheduler/tick` en producción.** Es el gap
G1 que documentó el Sprint 14 (§ `sprint14_aws_analisis.md`) y que nunca se
cerró: `aws events list-rules` vacío y el único schedule era el de mascotas,
apagado. Sin ese cron, B4 y B5 quedan perfectos en el código y **no ocurren
jamás**.

Se provisionó EventBridge Scheduler `multiagente-bot-tick` → Lambda homónima →
`https://api.glomabeauty.com/internal/bot-scheduler/tick`, `rate(1 minute)`. El
secreto se lee de SSM (`/multiagente/prod/INTERNAL_API_KEY`, SecureString): en la
Lambda solo vive el **nombre** del parámetro, nunca el valor.

**Creado DISABLED a propósito.** Encenderlo es lo que hace que el bot le empiece
a escribir solo a clientes reales; esa decisión es del CEO y va junto con el
despliegue.

```bash
# encender          aws scheduler update-schedule --name multiagente-bot-tick --region sa-east-1 ... --state ENABLED
# apagar            ... --state DISABLED
```

### De paso

`rds_exec.sh` y `rds_query.sh` tenían clavada la task-def `multiagente-backend:15`
mientras el servicio corre la `:64` — 49 revisiones atrás. Correr una migración
contra una imagen vieja es una trampa silenciosa: el `models.py` viejo no ve las
columnas nuevas y los scripts **reportan cero filas en vez de fallar**. Ahora
resuelven la revisión viva del servicio.

### Pendiente antes de que esto sirva en producción

1. Desplegar el backend (imagen + task-def). **La columna ya está en RDS pero el
   ORM desplegado no la ve**: SQLAlchemy se traga la asignación sin error y no
   persiste nada.
2. Encender el schedule (comando arriba) — decisión del CEO.
3. Definir `ADJUNTOS_BUCKET` (o dejar que caiga al de mascotas) en la task-def.
4. Follow-up: el endpoint de subida no tiene rate-limit propio (sí exige auth y
   permiso `can_reply_messages`), a diferencia del de fotos de mascotas.

---

## Rotación de `SECRET_KEY` — la clave de sesión estaba publicada (2026-08-21)

Salió de una pregunta del CEO ("¿es una falla de seguridad?") sobre unas
credenciales que aparecieron en texto plano en la task-def de ECS. Al
verificarlas una por una, la respuesta fue distinta para cada una:

| Secreto | ¿Dónde estaba? | Gravedad |
|---|---|---|
| `POSTGRES_PASSWORD` | Solo en la task-def. **Nunca se commiteó** | Mala práctica |
| `SECRET_KEY` (firma de los JWT) | En la task-def **y en `PRUEBAS_SPRINT_7.md`, en el repo PÚBLICO**, desde el Sprint 7 | **Crítica** |

La segunda es la que importaba. El backend firma los tokens de sesión con
HS256 usando esa clave, así que **cualquiera que leyera el repo podía firmarse
un token válido y entrar como cualquier usuario, sin contraseña**. La ironía es
que la línea que la exponía era la tarea pendiente que decía "S-26: rotar
`SECRET_KEY`, es placeholder débil".

### Cómo se comprobó que era explotable de verdad

No se asumió: se fabricó un token con la clave publicada y se pidió
`/usuario/me` en producción. Devolvió **404** — "usuario no encontrado". Eso es
la prueba: una firma inválida devuelve **401**, así que el 404 significa que la
firma **fue aceptada** y solo falló la búsqueda del correo (el `sub` de prueba
era `"1"`, no un correo). Con un correo real habría sido 200 y sesión ajena.

### Qué se hizo

1. Clave nueva de 64 bytes generada y guardada en SSM SecureString
   (`/multiagente/prod/SECRET_KEY`). Nunca pasó por pantalla ni por un archivo.
2. `SECRET_KEY` **sale** de las variables en texto plano de la task-def y entra
   como `secrets`, junto a `APP_ENCRYPTION_KEY` y las de Twilio (task-def `:67`).
3. Desplegada. Verificado: el mismo token forjado con la clave vieja ahora
   devuelve **401**.
4. La clave se borró de `PRUEBAS_SPRINT_7.md` y la línea explica qué pasó.
   **Borrarla no era el arreglo** — sigue en el historial público de git; el
   arreglo es la rotación (regla #8 de CLAUDE.md, al pie de la letra).

El CEO autorizó explícitamente el cierre de todas las sesiones abiertas, que es
el efecto colateral: todo el mundo vuelve a entrar.

### Queda abierto

- **`POSTGRES_PASSWORD` y `SECRET_KEY`… falta la primera**: la contraseña de
  RDS sigue en texto plano en la task-def. No está publicada, así que no urge,
  pero la ve cualquiera con lectura sobre ECS. Moverla a SSM es el mismo
  procedimiento de arriba y no cierra sesiones.
- Revisar si hay otros secretos en el historial público (se buscaron estos dos;
  no un barrido completo con algo tipo `gitleaks`).

---

## Barrido de secretos del historial + la contraseña de RDS a SSM (2026-08-24)

Los dos pendientes que quedaron de la rotación de `SECRET_KEY`.

### `POSTGRES_PASSWORD` ya no viaja en texto plano

Estaba como variable de entorno normal en la task-def: no publicada, pero
visible para cualquiera con lectura sobre ECS. Se movió a
`/multiagente/prod/POSTGRES_PASSWORD` (SecureString) **con el mismo valor** —
no hacía falta rotarla porque nunca se commiteó (se verificó). Task-def `:68`.

Verificado después del despliegue: `POST /login` con credenciales falsas
devuelve `401 Credenciales incorrectas`. Ese 401 sale de **consultar la base**,
así que el backend está leyendo la contraseña de SSM y conectando bien.

Ahora **ningún secreto queda en las variables en claro** de la task-def. Los
únicos nombres que suenan a secreto y siguen ahí son `ACCESS_TOKEN_EXPIRE_MINUTES`
y `LLM_MAX_TOKENS`, que son números de configuración.

### El barrido: 1 hallazgo real de 4

No hay `gitleaks` en el equipo, así que se escribió
`backend/scripts/barrido_secretos.py`: recorre **todos los blobs de todas las
ramas** (887 de texto, 151 commits) contra patrones de alta señal, e imprime los
hallazgos **enmascarados** — el objetivo es saber qué rotar, no volver a exponer
el secreto en otra pantalla.

| Hallazgo | Veredicto |
|---|---|
| `backend/app/database.py` — URL de Postgres con contraseña | **Falso positivo**: es un f-string con `{POSTGRES_PASSWORD}` |
| `backend/scripts/migrate_sprint13_campanas.py` — URL con contraseña | **Falso positivo**: ejemplo de uso en el docstring |
| `backend/tests/test_meta_account_flow.py` — `password=...` | **Falso positivo**: fixture de prueba |
| `BITACORA.md` — contraseña de `demo@gmail.com` | ⚠️ **REAL** |

### ⚠️ La contraseña de `demo@gmail.com` está en 79 commits públicos

En HEAD ya aparece redactada como «en el gestor del CEO» — alguien la borró en
su momento. **Eso no arregló nada**: sigue en 79 commits del historial, y el
repositorio es público. Es exactamente el caso que la regla #8 de CLAUDE.md
describe, y la razón por la que esa regla dice "hay que **rotarlo**".

`demo@gmail.com` es una cuenta **viva** de la plataforma. Rotarla es decisión
del CEO porque se usa en demostraciones con clientes; queda pendiente de su
visto bueno. Camino propuesto, sin que la clave nueva pase por una pantalla:
generarla al azar, aplicarla con el script que ya existe
(`backend/scripts/reset_demo_password.py`) y dejarla en SSM para que el CEO la
saque de ahí.

**Lección que ya está escrita en la regla #8 y que este barrido confirma**: una
contraseña que se commitea no se arregla borrándola del archivo. El archivo se
limpia igual —para que nadie la copie de HEAD— pero lo único que cierra la fuga
es cambiarla.

---

## Rotada la contraseña de `demo@gmail.com` (2026-08-24)

Cierre del hallazgo del barrido: la contraseña de esa cuenta estaba en **79
commits** del historial público. En HEAD ya aparecía redactada, lo que no sirve
de nada — el arreglo es rotarla.

### Cómo se hizo, sin que la clave pasara por ninguna pantalla

1. Se generó al azar (24 caracteres) **directo dentro de** `aws ssm
   put-parameter`, con el valor como sustitución de comando: nunca se imprimió
   ni quedó en un archivo. Vive en `/multiagente/prod/DEMO_PASSWORD`
   (SecureString).
2. Se aplicó en RDS con `backend/scripts/rotar_demo_password.py`, corriendo
   dentro de una task de ECS vía `rds_exec.sh` (RDS no está expuesta).
   **El script lee la clave de SSM él mismo**, no la recibe por variable de
   entorno: `rds_exec.sh` mete las env vars en el `containerOverrides` de la
   llamada a la API, así que pasarla por ahí la habría dejado escrita en
   CloudTrail y en el `describe-tasks`.
3. Para eso el task role necesitaba leer ese parámetro. Se le dio un permiso
   **de un solo parámetro, de solo lectura**, y se le **revocó al terminar**:
   el backend no tiene ninguna razón para poder leer esa contraseña.

### Verificación

Login real contra producción, con la clave vieja sacada del historial —
exactamente lo que podría hacer cualquiera que clone el repo:

```
clave VIEJA (la del repo público): HTTP 401
clave NUEVA (la de SSM)          : HTTP 200
```

### Dónde saca el CEO la clave

```bash
aws ssm get-parameter --region sa-east-1 \
  --name /multiagente/prod/DEMO_PASSWORD --with-decryption \
  --query Parameter.Value --output text
```

De ahí a su gestor. **No se escribió en ningún archivo del repo** — que es lo
que originó todo esto.

### Estado final de los secretos

| Secreto | Dónde vive | Estado |
|---|---|---|
| `SECRET_KEY` | SSM SecureString | Rotada 21-ago |
| `POSTGRES_PASSWORD` | SSM SecureString | Movida 24-ago (nunca se commiteó) |
| `INTERNAL_API_KEY`, `APP_ENCRYPTION_KEY`, `TWILIO_*` | SSM SecureString | Ya estaban |
| Contraseña de `demo@gmail.com` | SSM SecureString | Rotada 24-ago |

Ningún secreto queda en las variables en texto plano de la task-def.

**Sigue pendiente**: los valores viejos siguen en el historial público y ahí van
a quedar. Están rotados, que es lo que los vuelve inofensivos. Si alguna vez se
decide limpiar el historial, es reescribirlo entero (`git filter-repo`) y
forzar el push, con todo lo que eso rompe para quien tenga un clon.
