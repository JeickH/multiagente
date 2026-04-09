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
