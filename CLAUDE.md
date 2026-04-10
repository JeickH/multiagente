# Multiagente - Sistema de Gestión WhatsApp (WATI)

## Arquitectura de Agentes

Todo mensaje que llegue a Claude Code debe ser procesado primero por el **Project Manager**, quien analiza la solicitud y delega al agente apropiado. Los agentes se comunican entre sí a través de la BITACORA.md y pueden invocarse mutuamente cuando necesiten apoyo de otra especialidad.

### Flujo de comunicación
```
Usuario (CEO) → Project Manager → Agente(s) asignado(s) → BITACORA.md → PM reporta resultado
```

### Protocolo de delegación
1. PM recibe el mensaje y lo clasifica por tipo (infraestructura, desarrollo, BD, testing)
2. PM actualiza BITACORA.md con la tarea asignada
3. PM invoca al agente usando el Task tool con subagent_type apropiado
4. El agente ejecuta, documenta en BITACORA.md y retorna resultado
5. PM valida y reporta al CEO

---

## Agentes (definidos en `.claude/agents/`)

Los agentes están configurados como archivos `.md` en `.claude/agents/` para ser invocados como subagentes de Claude Code:

| Agente | Archivo | Cuándo se activa |
|--------|---------|-----------------|
| **Project Manager** | `.claude/agents/project-manager.md` | Siempre (punto de entrada) |
| **Deploy AWS** | `.claude/agents/deploy-aws.md` | Infraestructura, Docker, CI/CD |
| **Desarrollador de Plataforma** | `.claude/agents/dev-plataforma.md` | Desarrollo frontend/backend, WATI |
| **Experto en Bases de Datos** | `.claude/agents/experto-bd.md` | Modelado, migraciones, PostgreSQL |
| **Experto en Seguridad** | `.claude/agents/seguridad.md` | Auditoría de diseño/código, secretos, cifrado, autenticación/autorización |
| **QA** | `.claude/agents/qa.md` | Testing, validación, revisión |

Consultar cada archivo de agente para ver sus responsabilidades detalladas, herramientas y reglas.

### Reglas de delegación del Project Manager

El PM debe delegar según el tipo de tarea:

- **Infraestructura, Docker, CI/CD, AWS** → `deploy-aws`
- **Frontend/backend, endpoints, UI, integraciones externas** → `dev-plataforma`
- **Schema, migraciones, queries, índices** → `experto-bd`
- **Testing, validación, QA manual y automatizado** → `qa`
- **Seguridad, auditoría, manejo de secretos, cifrado, revisión de diseño por riesgos** → `seguridad`

> Cualquier feature nuevo que toque credenciales, autenticación, autorización o manejo de secretos **debe pasar por el agente `seguridad` antes del merge**.

---

## Stack Tecnológico

| Componente | Tecnología |
|------------|-----------|
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind CSS |
| Backend | FastAPI + Python 3.11+ |
| Base de datos | PostgreSQL 15 (local) / RDS PostgreSQL (AWS) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| API externa | WATI WhatsApp API |
| Containers | Docker + docker-compose |
| CI/CD | GitHub Actions |
| Cloud | AWS (ECS Fargate, Amplify, RDS, ALB, Route 53) |

## Servicios AWS (para ~10 usuarios concurrentes)

| Servicio | Uso | Costo estimado |
|----------|-----|----------------|
| ECS Fargate (1 task, 0.25vCPU, 0.5GB) | Backend containerizado | ~$10/mes |
| ECR | Registry de imágenes Docker | ~$1/mes |
| Amplify | Frontend Next.js | ~$0-5/mes |
| RDS PostgreSQL (db.t3.micro) | Base de datos | ~$15/mes |
| ALB | Load balancer | ~$16/mes |
| Route 53 | DNS y dominio | ~$0.50/mes |
| **Total** | | **~$42-47/mes** |

## Módulos de la Aplicación

| # | Módulo | Estado | Ruta |
|---|--------|--------|------|
| 1 | Atención a mensajes (manual) | Próximamente | /mensajes |
| 2 | Campañas de envío masivo | Próximamente | /campanas |
| 3 | Bots de servicio WhatsApp | Próximamente | /bots |
| 4 | Plan actual y datos de usuario | Activo | /usuario |

## Estructura del Proyecto
```
multiagente/
├── .claude/
│   └── agents/            # Agentes personalizados de Claude Code
│       ├── project-manager.md
│       ├── deploy-aws.md
│       ├── dev-plataforma.md
│       ├── experto-bd.md
│       ├── seguridad.md
│       └── qa.md
├── frontend/              # Next.js app
│   ├── components/        # Componentes reutilizables
│   ├── pages/             # Páginas/rutas
│   ├── styles/            # Estilos globales
│   └── public/            # Assets estáticos
├── backend/               # FastAPI app
│   └── app/
│       ├── routers/       # Endpoints por módulo
│       ├── models.py      # Modelos SQLAlchemy
│       ├── schemas.py     # Schemas Pydantic
│       ├── crud.py        # Operaciones CRUD
│       └── database.py    # Conexión PostgreSQL
├── CLAUDE.md              # Documentación del proyecto y stack
├── BITACORA.md            # Log de tareas del proyecto
├── docker-compose.yml     # Desarrollo local
├── Dockerfile.backend     # Container del backend
├── Dockerfile.frontend    # Container del frontend
└── .gitignore
```

---

## Seguridad

Reglas permanentes que debe respetar todo el equipo. Violaciones de estas reglas son
**bloqueantes para merge** y requieren intervención del agente `seguridad`:

1. **Nunca loggear secretos descifrados**: prohibido `print`, `logger.info`, `logger.debug`
   o `f"..."` sobre tokens, passwords, claves de cifrado, cookies de sesión o cualquier
   credencial, aunque sea "solo para debug local". Si un modelo tiene un campo sensible,
   define un `__repr__` que lo redacte.
2. **Nunca incluir secretos en schemas Pydantic de respuesta**: `UserOut`, `MetaAccountOut`,
   `TeamMemberOut`, etc. NO pueden contener `hashed_password`, `encrypted_access_token`,
   `app_secret` ni equivalentes. Revisa cualquier nuevo `...Out` con esta lista en mente.
3. **Secretos multi-tenant siempre en DB cifrados, nunca en `.env`**: credenciales que
   pertenecen a un cliente específico (tokens de Meta, claves de API de terceros que paga
   el cliente, etc.) van en la base de datos cifradas con Fernet (o equivalente AEAD).
   La clave maestra de cifrado (`APP_ENCRYPTION_KEY`) sí va en env var, pero **nunca** un
   secreto perteneciente a un tenant.
4. **Todo feature que toque credenciales, auth, autorización o secretos pasa por el
   agente `seguridad`**: el PM debe delegarle la revisión del diseño **antes** de que el
   Dev Plataforma implemente, y una auditoría de código **después** del commit, antes del
   merge. Hallazgos Críticos o Altos son bloqueantes.
5. **Webhooks externos fail-closed en producción**: verificación HMAC obligatoria con
   secreto compartido; si falta la firma o el secreto, rechazar con 403. Fail-open solo
   se permite con warning explícito en logs y solo durante desarrollo local.
6. **Errores al cliente siempre sanitizados**: el detalle completo (stack trace, respuesta
   de APIs externas, SQL) va únicamente a `logger.exception` server-side. El cliente recibe
   mensajes genéricos (`"credenciales inválidas"`, `"error temporal al conectar con el
   proveedor"`).
