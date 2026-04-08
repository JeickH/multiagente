# Oráculo 3 Frontend

Frontend construido con Next.js, Tailwind CSS, shadcn/ui y Auth.js.

## Scripts principales
- `npm install` — Instala dependencias
- `npm run dev` — Ejecuta el servidor de desarrollo

## Variables de entorno
Configura las variables en `.env.local` (ver `.env.example`).

## Estructura
- `pages/` — Páginas principales (login, registro, dashboard y pestañas)
- `components/` — Componentes reutilizables (Sidebar, Layout)
- `styles/` — Estilos globales (Tailwind)

---

# Oráculo 3 Backend

Backend construido con FastAPI y PostgreSQL.

## Scripts principales
- `pip install -r requirements.txt` — Instala dependencias
- `uvicorn app.main:app --reload` — Ejecuta el servidor FastAPI

## Variables de entorno
Configura las variables en `.env` (ver `.env.example`).

## Estructura
- `app/` — Código fuente principal
  - `routers/` — Endpoints (auth, ventas, analisis_demanda, sop, integraciones, usuario)
  - `models.py` — Modelos ORM
  - `schemas.py` — Esquemas Pydantic
  - `database.py` — Conexión a Postgres
  - `crud.py` — Lógica de base de datos

---

## Primeros pasos
1. Copia `.env.example` a `.env` (backend) y `.env.local` (frontend) y edítalos según tu entorno.
2. Instala dependencias y ejecuta ambos servidores.
3. Accede a `/login` y `/register` en el frontend para probar el flujo de autenticación.
