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
| **QA** | `.claude/agents/qa.md` | Testing, validación, revisión |

Consultar cada archivo de agente para ver sus responsabilidades detalladas, herramientas y reglas.

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
