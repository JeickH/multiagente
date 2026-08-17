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
| **Experto en UI/UX** | `.claude/agents/ui-ux.md` | Wireframes HTML/Tailwind de cada módulo nuevo antes de codear |
| **QA** | `.claude/agents/qa.md` | Testing, validación, revisión |

Consultar cada archivo de agente para ver sus responsabilidades detalladas, herramientas y reglas.

### Reglas de delegación del Project Manager

El PM debe delegar según el tipo de tarea:

- **Infraestructura, Docker, CI/CD, AWS** → `deploy-aws`
- **Frontend/backend, endpoints, UI, integraciones externas** → `dev-plataforma`
- **Schema, migraciones, queries, índices** → `experto-bd`
- **Wireframes / diseño visual antes de codear UI** → `ui-ux`
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
7. **La sesión del navegador se toca SOLO por `frontend/lib/session.ts`**: prohibido
   `localStorage.getItem('token')` / `setItem` / `removeItem` suelto en una página o
   componente. Se usan `getToken()`, `haySesion()`, `guardarToken()` y `cerrarSesion()`.
   El motivo (#361): cuando cada página leía el token por su cuenta, "hay token guardado"
   se confundió con "hay sesión" y la plataforma se abría con una sesión vencida; y
   "Salir" era un link que no borraba nada. Del payload del JWT se lee **únicamente
   `exp`** — nunca rol, correo, tenant ni permisos: esas decisiones son del backend,
   que es el único que verifica la firma. Al agregar una pantalla nueva, si es privada
   **no** se agrega a `PUBLIC_PAGES` en `pages/_app.tsx`.
8. **Este repositorio es PÚBLICO** (`github.com/JeickH/multiagente`). Nunca se escribe
   en un archivo versionado: contraseñas de cuentas (ni de prueba — son cuentas vivas
   en producción), tokens, ni **teléfonos o correos de personas reales**. Los teléfonos
   que llegan de las fuentes son datos de terceros: en docstrings y documentación van
   enmascarados (`3XXXXXXXXX`), nunca el número real. Las credenciales viven en el
   gestor del CEO o en SSM; en los documentos de prueba se referencian, no se copian.
   Un secreto commiteado **no se arregla borrándolo**: queda en el historial público y
   hay que **rotarlo**.

---

---

## Recupera Tu Mascota (cuenta `recuperatumascota@gmail.com`)

Iniciativa solidaria por el terremoto en Colombia, con su propio sitio público
(`mascotasperdidascolombia.com`), su bot y su panel privado.

> **Antes de tocar cualquier cosa de este módulo, lee
> [`MANUAL_RECUPERA_TU_MASCOTA.md`](MANUAL_RECUPERA_TU_MASCOTA.md).** Está al inicio de
> cada sesión por una razón: concentra las reglas del módulo, cómo funciona el matching,
> los importadores y el procedimiento de recuperación ante desastre.

Las tres que más duelen si se olvidan:
1. **Nunca borrar datos sin confirmación explícita del CEO** — ya se perdieron fotos
   irrecuperables por un borrado hecho sobre una interpretación.
2. **El bot jamás inventa un teléfono**: solo sale de `entregar_contacto`, y hay un
   guardarraíl que lo hace cumplir. Corolario para los importadores: **ningún número
   puede quedar en `senas` ni en `notas`**, o el guardarraíl le tumba el turno al bot.
3. Los cambios de marca de ese sitio (hoy el footer "Tecnología de **Gloma App**") viven
   solo ahí; la app y la landing de Gloma no se tocan sin aviso.

**El esquema de la base está documentado en [`documentacion_bd/`](documentacion_bd/)**
(empieza por `index.html`): diccionario de datos, matriz de qué publica cada fuente y
diagramas. Se regenera leyendo la base con `python documentacion_bd/generar.py`.

**Fuentes externas**: se importan con `backend/scripts/actualizar_fuente.py <fuente>
--revisar` → el CEO aprueba el HTML → `--cargar`. **Ninguna fuente entra a la base sin
esa revisión.** El descarte de repetidos va por `(source, origen_id)`.

---

## Convenciones de operación

1. **Paridad BD local ↔ AWS (regla permanente del CEO)**: la base de datos
   local (`docker-compose` servicio `db`) y la base de producción (RDS
   `multiagente-db` en sa-east-1) **deben tener siempre el mismo schema**.
   Toda migración / `ALTER TABLE` / `DROP` / índice nuevo se aplica en ambos
   entornos en el mismo PR. Esto garantiza que siempre exista una copia local
   fiel a producción para desarrollo y debugging.
   - Regla operativa: cada vez que se modifique `models.py`, el PR debe
     incluir (a) el script de migración idempotente en `backend/scripts/`,
     (b) evidencia de ejecución local (docker-compose), (c) evidencia de
     ejecución en RDS (run-task ECS o equivalente).
   - Follow-up permanente: adoptar Alembic para migraciones versionadas.
     Mientras no exista Alembic, scripts manuales con `IF NOT EXISTS` /
     `ADD COLUMN IF NOT EXISTS` son obligatorios para ser idempotentes.
   - **Migrar la base no basta: hay que desplegar el modelo.** Si se agregan
     columnas por SQL pero la imagen en ECS lleva un `models.py` viejo, el ORM
     ni las ve y los scripts que las escriben **no fallan** — reportan cero
     filas tocadas, que es peor. Toda migración va con su despliegue.
2. **Ambiente Python**: nunca instalar dependencias del backend en el
   intérprete del sistema. Siempre `conda activate multiagente` o
   `source backend/.venv/bin/activate` antes de `pip install` o `pytest`.
3. **Región AWS = `sa-east-1`**. Cualquier comando `aws` debe incluir
   explícitamente `--region sa-east-1`. Nunca us-east-1.
