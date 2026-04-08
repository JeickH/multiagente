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

## Log de Cambios

| Fecha | Agente | Acción |
|-------|--------|--------|
| 2026-04-08 | PM | Creación del proyecto, estructura base, CLAUDE.md y BITACORA.md |
| 2026-04-08 | Dev Plataforma | Adaptación frontend (Sidebar, Login, Register, módulos) y backend (auth, routers, CORS) |
| 2026-04-08 | Deploy AWS | Dockerfiles, docker-compose.yml, .env.example |
