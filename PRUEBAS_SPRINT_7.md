# Guía de pruebas — Sprint 7 (Seguridad + Credenciales Meta cifradas)

> Fecha: 2026-04-10
> Branch: `main` (mergeado desde `feature/seguridad-meta-credentials`)
> PR: https://github.com/JeickH/multiagente/pull/2
> Commit merge en main: `41b0a9a`

Este documento explica **cómo probar el módulo de envío manual de mensajes**
(y el flujo completo de conexión de Meta) en los dos entornos desplegados:
producción en AWS y desarrollo local con Docker Compose.

---

## 1. URLs y referencias rápidas

| Recurso | URL |
|---|---|
| Frontend producción (Amplify) | https://main.d1cfl9ey07f61o.amplifyapp.com |
| Backend producción (ALB) | http://multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com |
| Backend Swagger docs | http://multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com/docs |
| Frontend local | http://localhost:3000 |
| Backend local | http://localhost:8000 |
| Swagger local | http://localhost:8000/docs |

> El frontend de Amplify es HTTPS y el backend es HTTP. Para evitar *mixed
> content* el frontend hace todas las llamadas a `/api/…` y Next.js las
> proxea al ALB en el server-side (SSR). Tú no ves el backend directamente,
> solo los endpoints `/api/*` detrás del dominio de Amplify.

---

## 2. Credenciales reales que vas a necesitar

Del Sprint 6 (valores del CEO):

| Campo | Valor |
|---|---|
| Phone Number ID (prod) | `1036567489546838` |
| WABA ID (prod) | `1272393681746114` |
| Número visible | +57 300 318 7871 |
| Phone Number ID (test) | `988594284346297` |
| WABA ID (test) | `758411907207213` |
| Token permanente | `EAAXJ9jEBv8w…wZDZD` (guardado en tu 1Password) |

> **Importante**: el token ya **no vive en `.env`**. Ahora se pide en la UI
> cuando haces clic en “Conectar cuenta de Meta”, se valida contra Graph API
> (`/v22.0/{phone_number_id}`) y solo si Meta responde OK se cifra con Fernet
> y se guarda en la tabla `meta_accounts.encrypted_access_token`. Ningún
> endpoint lo devuelve después.

---

## 3. Pruebas en PRODUCCIÓN (AWS)

### 3.1 Smoke test de infra (30 segundos)

```bash
# Backend vivo
curl -s -o /dev/null -w "backend /docs: HTTP %{http_code}\n" \
  http://multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com/docs

# Frontend vivo
curl -s -o /dev/null -w "amplify main: HTTP %{http_code}\n" \
  https://main.d1cfl9ey07f61o.amplifyapp.com

# Proxy funcionando (HTTPS Amplify -> HTTP ALB via Next.js rewrites)
curl -s -o /dev/null -w "rewrite /api/login: HTTP %{http_code}\n" \
  -X POST -H "Content-Type: application/json" \
  -d '{"correo":"x@x.com","password":"x"}' \
  https://main.d1cfl9ey07f61o.amplifyapp.com/api/login
```

Lo esperado: 200 / 200 / 401 (credenciales inválidas, sanitizado).

### 3.2 Flujo manual por la web (Amplify)

1. Abre https://main.d1cfl9ey07f61o.amplifyapp.com en Chrome/Safari.
2. **Registro** (si no tienes usuario todavía):
   - Clic en “Crear cuenta”.
   - Llena nombre, tipo_documento (CC), documento, correo (dominio real, `@gmail.com`), contraseña ≥ 6 caracteres.
   - Debe redirigirte al login. El correo queda en `users`.
3. **Login**:
   - Con el correo y la contraseña que registraste.
   - Al entrar ves el sidebar con Mensajes / Campañas / Bots / Mi Plan.
4. **Ir a “Mi Plan”** (`/usuario`):
   - La sección “Cuenta de WhatsApp Business” debe decir *“Sin cuenta de Meta registrada”* y mostrar el botón **Conectar cuenta de Meta**.
5. **Conectar la cuenta de Meta**:
   - Clic en “Conectar cuenta de Meta”.
   - En el modal pon:
     - **Phone Number ID**: `1036567489546838`
     - **WABA ID**: `1272393681746114`
     - **Access Token**: pega el token permanente del 1Password (≥ 20 caracteres, empieza con `EAA`).
   - Clic en **Conectar**.
   - **Si el token es válido**: el backend llama `/v22.0/{phone_number_id}` con Bearer, recibe `display_phone_number` y `verified_name`, los guarda en DB, cifra el token con Fernet y el modal se cierra. La pantalla de “Mi Plan” ahora muestra el teléfono visible (+57 300 318 7871) y el nombre (“Tienda Zeniv”) y aparece el botón **Desconectar**.
   - **Si el token es inválido o formateas mal los IDs**: ves un error rojo genérico “No se pudo validar el token con Meta. Revisa phone_number_id, waba_id y access_token.” No se persiste nada. No hay detalles del request ni del error de Graph API (eso solo va a logs del servidor).
6. **Ir a “Mensajes”** (`/mensajes`):
   - Debería cargar la inbox vacía (si nadie te ha escrito todavía).
   - En la esquina superior derecha verás el botón **Nueva conversación**.
7. **Enviar mensaje con template** (única forma de iniciar conversación fuera de la ventana de 24h de Meta):
   - Clic en **Nueva conversación**.
   - Destinatario: un número al que puedas recibir mensajes de WhatsApp (con código de país, sin `+`, ejemplo `573001234567`).
   - Template: selecciona un template aprobado en tu Business Manager (por defecto `hello_world`).
   - Idioma: `en_US` si usas `hello_world`.
   - Clic en **Enviar**.
   - El modal se cierra y vuelve a la inbox, ahora con la conversación nueva abierta.
   - El mensaje del template aparece como *outbound* en el panel de chat.
   - Debería llegar el WhatsApp físicamente al número destino.
8. **Responder manualmente**:
   - Cuando el destinatario conteste (entra por el webhook `/meta/webhook` y se guarda como `inbound`), verás el nuevo mensaje en el panel de chat.
   - En la ventana de 24h puedes escribir texto libre en el composer de la parte inferior y darle Enter o “Enviar”.
   - El mensaje va por Meta Graph API (`/messages`) y aparece como *outbound* en el chat.
   - Si el permiso `can_reply_messages` de tu `TeamMember` está en `false`, el composer no aparece y el botón queda oculto (ahora mismo, como owner, lo tienes en `true`).
9. **Desconectar la cuenta de Meta** (opcional):
   - Vuelve a “Mi Plan”, clic en **Desconectar**.
   - Confirma. La fila de `meta_accounts` se borra. Los endpoints de envío vuelven a devolver 400 “No hay cuenta de Meta usable”.

### 3.3 Mismas pruebas con `curl` (CI-friendly)

```bash
BASE=http://multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com
EMAIL="ceotest$(date +%s)@gmail.com"
PASS="TuPassSegura1"

# 1. Registro
curl -sS -X POST $BASE/register -H 'Content-Type: application/json' -d "{
  \"nombre\":\"CEO Test\",
  \"tipo_documento\":\"CC\",
  \"documento\":\"C$(date +%s)\",
  \"correo\":\"$EMAIL\",
  \"password\":\"$PASS\"
}"

# 2. Login → JWT
TOKEN=$(curl -sS -X POST $BASE/login -H 'Content-Type: application/json' \
  -d "{\"correo\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. Estado inicial (sin cuenta Meta)
curl -sS -H "Authorization: Bearer $TOKEN" $BASE/usuario/me/meta-account

# 4. Conectar Meta (usa un token REAL o te devuelve 400)
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "phone_number_id":"1036567489546838",
    "waba_id":"1272393681746114",
    "access_token":"EAAXJ9jEBv8w..."
  }' \
  $BASE/usuario/me/meta-account

# 5. Iniciar conversación con template
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "wa_id":"573001234567",
    "template_name":"hello_world",
    "template_language":"en_US"
  }' \
  $BASE/mensajes/conversaciones/nueva

# 6. Listar conversaciones
curl -sS -H "Authorization: Bearer $TOKEN" $BASE/mensajes/conversaciones

# 7. Enviar respuesta a la conversación (reemplaza {id})
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"Hola, ¿en qué puedo ayudarte?"}' \
  $BASE/mensajes/conversaciones/1/enviar

# 8. Desconectar cuenta Meta
curl -sS -X DELETE -H "Authorization: Bearer $TOKEN" $BASE/usuario/me/meta-account
```

---

## 4. Pruebas en LOCAL (Docker Compose)

### 4.1 Prerrequisitos

1. Docker Desktop corriendo.
2. Archivo `.env` en la raíz con, al menos:
   ```
   POSTGRES_DB=multiagente_db
   POSTGRES_USER=multiagente_user
   POSTGRES_PASSWORD=multiagente_pass
   SECRET_KEY=cambia-este-secreto-en-produccion
   APP_ENCRYPTION_KEY=<clave Fernet válida>
   ```
   Para generar la clave Fernet:
   ```bash
   # OPCIÓN A: venv dedicado (no toques el Python del sistema)
   python3 -m venv backend/.venv
   source backend/.venv/bin/activate
   pip install cryptography
   python backend/scripts/gen_encryption_key.py
   # copia la clave al .env como APP_ENCRYPTION_KEY=...

   # OPCIÓN B: one-liner
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

### 4.2 Levantar el stack

```bash
docker compose up -d db backend frontend
docker compose ps
# espera ~20 segundos a que backend diga "Application startup complete"

curl -s -o /dev/null -w "backend /docs: HTTP %{http_code}\n" http://localhost:8000/docs
# esperado: HTTP 200
```

### 4.3 Aplicar migración de schema (regla de paridad BD local ↔ AWS)

```bash
docker compose exec -T backend python scripts/migrate_sprint7_add_columns.py
# esperado:
#   Conectando a host: db
#     -> ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at ...
#   Columnas actuales de users: [..., 'created_at']
#   OK: migración Sprint 7 aplicada (o ya estaba aplicada).
```

El script es **idempotente**: puedes correrlo cuantas veces quieras, usa
`ADD COLUMN IF NOT EXISTS`. Esta es la misma migración que se aplicó en RDS.

### 4.4 Smoke test del frontend local

1. Abre http://localhost:3000.
2. Mismo flujo que en producción: registro → login → Mi Plan → Conectar cuenta Meta → Mensajes.
3. El `.env` local por defecto usa `APP_ENV=development`, por lo que:
   - El webhook `/meta/webhook` acepta requests sin HMAC con un *warning*
     en logs (en producción fail-closed es obligatorio).
   - Los errores 500 muestran más detalle por stdout del container.

### 4.5 Parar y limpiar

```bash
# Parar sin borrar datos
docker compose down

# Parar y borrar también el volumen de Postgres (empezar desde cero)
docker compose down -v
```

---

## 5. Verificar que el módulo de mensajes está funcionando

Checklist (marca cada uno cuando lo validas):

- [ ] `GET /usuario/me/meta-account` responde 200 con `registered: true`
      después de conectar.
- [ ] La DB tiene **exactamente 1** fila en `meta_accounts` con
      `encrypted_access_token` en formato Fernet (texto largo base64), y el
      `status` en `'active'`.
- [ ] `POST /mensajes/conversaciones/nueva` con un template aprobado devuelve
      201 y el mensaje llega al WhatsApp destino.
- [ ] La conversación aparece en `GET /mensajes/conversaciones` con el
      último mensaje cómo `outbound`.
- [ ] `POST /mensajes/conversaciones/{id}/enviar` con texto libre devuelve
      200 dentro de la ventana de 24h desde el último inbound del contacto
      (Meta lo rechaza fuera de esa ventana, lo cual genera un 400
      sanitizado).
- [ ] Al desconectar la cuenta (`DELETE /usuario/me/meta-account`), los
      endpoints de envío devuelven 400 “No hay cuenta de Meta usable”.
- [ ] Ningún endpoint devuelve **nunca** el token o campos con “token” en
      el nombre (buscar en DevTools Network).

---

## 6. Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `/login` devuelve 500 `column users.xxx does not exist` | RDS tiene una versión antigua de `users` sin alguna columna del Sprint 7 | Correr `migrate_sprint7_add_columns.py` en RDS vía `aws ecs run-task` |
| `POST /usuario/me/meta-account` 400 “No se pudo validar el token” | El token de Meta está expirado, revocado, no tiene permisos, o phone_number_id/waba_id no coinciden | Ir al Business Manager, generar token con permisos `whatsapp_business_messaging` y `whatsapp_business_management` |
| El template manda pero no llega | El template no está aprobado o el idioma no coincide (`en_US` vs `es_CO`) | Verificar estado del template en Meta Business Manager |
| Mixed content warning en el navegador | El frontend Amplify intenta llegar directo a `http://ALB/...` en vez de `/api/...` | Todas las llamadas deben ser `/api/*`. `next.config.js` tiene el rewrite que proxea al ALB |
| Local: backend no arranca `APP_ENCRYPTION_KEY requerida` | Falta o está vacía en `.env` | Generar clave con `gen_encryption_key.py` y ponerla en `.env` |
| Local: backend no arranca `APP_ENCRYPTION_KEY no tiene formato Fernet válido` | La clave no es base64 url-safe de 32 bytes | Regenerar, no editarla a mano |

---

## 7. Resumen del cierre de Sprint 7

| Item | Estado |
|---|---|
| Agente `seguridad` registrado y auditoría completada (3 críticos + 8 altos + 11 medios + 6 bajos) | ✅ |
| Tokens Meta cifrados con Fernet en DB, nunca en `.env` | ✅ |
| Validación contra Graph API antes de persistir | ✅ |
| Endpoints owner-only con mensajes sanitizados | ✅ |
| Frontend: modal seguro (`type=password`, `autocomplete=off`, sin `localStorage`) | ✅ |
| Tests 17/17 OK (8 crypto + 9 integración) | ✅ |
| Migración idempotente en RDS y local | ✅ |
| Regla paridad BD local↔AWS documentada en CLAUDE.md | ✅ |
| PR #2 mergeado a main (`41b0a9a`) | ✅ |
| Amplify auto-deploy main (job 6 SUCCEED) | ✅ |
| Backend ALB validado end-to-end | ✅ |
| Frontend Amplify validado con proxy Next.js | ✅ |

### Follow-ups abiertos (NO bloqueantes de este sprint)

- **S-13**: rate limiting en `POST /register` y `POST /usuario/me/meta-account` (slowapi o contador en memoria).
- **S-14**: importar `app.config.settings` desde `main.py` para fail-fast al arranque del backend (hoy solo se valida cuando algún módulo importa `config`).
- **S-26**: rotar `SECRET_KEY` del backend en ECS (actual es placeholder “multiagente-aws-secret-key-2026”, débil).
- **S-28**: añadir reintentos + timeout a `get_phone_number_info` en `services/meta_whatsapp.py`.
- **Alembic**: adoptar migraciones versionadas. Mientras tanto, cada PR que toque `models.py` debe traer su propio script idempotente en `backend/scripts/`.
- **AWS Secrets Manager**: migrar `APP_ENCRYPTION_KEY` de SSM Parameter Store a Secrets Manager (S-06).
- **HTTPS en ALB**: sacar certificado ACM y poner listener 443 en el ALB para no depender del proxy de Next.js para evitar mixed content.
