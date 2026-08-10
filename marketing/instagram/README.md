# Publicador de Instagram — marketing

Herramienta interna para publicar y **programar** carruseles e imágenes en el
Instagram de las marcas del portafolio. Vive fuera del producto: no toca la base
de datos de clientes ni el backend de la app.

## Por qué existe (y qué NO hace Meta)

Instagram **sí** tiene programación nativa —el Planificador de Meta Business
Suite, gratis, hasta 75 días—, pero es **solo interfaz web: no hay API para
ella**. La Content Publishing API tampoco acepta fecha futura, y sus contenedores
de media **expiran a las 24 h**.

Por eso la programación la llevamos nosotros:

| Comando | Qué hace |
|---|---|
| `schedule` | Sube las imágenes a S3 y deja la publicación en una cola |
| `run-due` | Corre por cron, revisa la cola y **publica** lo que ya venció |

Las imágenes se suben al *programar* (no al publicar) para que el runner no
dependa de que el Mac tenga los archivos.

## Arquitectura

```
igpost.py schedule ──► S3 (privado)  ─┬─► cola: queue/schedule.json
                                      └─► imágenes: posts/<slug>/NN-<hash>.jpg
                                                      │
cron ──► igpost.py run-due ──► URL prefirmada (1 h) ──┘
                            └─► Graph API: contenedores → media_publish
```

- **Credenciales**: AWS SSM Parameter Store (`SecureString`) en `sa-east-1`,
  bajo `/gloma/marketing/instagram/`. Nunca en `.env` ni en el repo.
- **Imágenes**: bucket `gloma-marketing-media-747456040509`, privado, cifrado
  (AES256), bloqueo público total, expiración automática a 30 días. Instagram
  las descarga con una **URL prefirmada de 1 h** — no hace falta bucket público.
- **Normalización**: cada slide se convierte a JPEG RGB y se reescala a máximo
  1440 px de ancho (una pieza de 2160×2700 queda en 1440×1800). Se valida el
  aspect ratio contra el rango que acepta Instagram (4:5 a 1.91:1) y el tope de
  8 MB.

## Setup inicial (una sola vez)

### 1. La cuenta debe ser profesional

Instagram **no permite publicar por API desde una cuenta personal**. En la app:
`Configuración → Tipo de cuenta → Cambiar a cuenta profesional` y elige
**Creador** o **Empresa**.

> Con el flujo *Instagram Login* que usa esta herramienta, una cuenta **Creador
> no necesita Página de Facebook vinculada**. Es el camino más corto.

### 2. Crear la app de Meta

En [developers.facebook.com/apps](https://developers.facebook.com/apps):

1. **Crear app** → caso de uso **"Otro"** → tipo **Empresa**.
2. Agregar el producto **Instagram** → *API setup with Instagram login*.
3. Copiar **Instagram App ID** e **Instagram App Secret**.
4. En *Business login settings*, registrar como **OAuth redirect URI**:
   `https://glomabeauty.com/ig-auth/`
   La página puede no existir: solo necesitamos leer el `code` de la barra de
   direcciones.
5. En **Roles**, agregar la cuenta de Instagram de la marca.

> **No hace falta App Review** mientras la app esté en modo desarrollo y solo
> publiques en cuentas con rol asignado en la app. App Review solo se necesita
> para publicar en cuentas de terceros.

### 3. Guardar credenciales y conectar

```bash
cd marketing/instagram
PY=/opt/anaconda3/envs/multiagente/bin/python

$PY igpost.py setup-app --app-id <APP_ID> --app-secret <APP_SECRET>
$PY igpost.py auth-url            # abre el enlace, autoriza, copia el code
$PY igpost.py connect --code <CODE>
$PY igpost.py whoami              # valida
```

## Uso diario

```bash
# Ver qué quedaría publicado, sin tocar nada
$PY igpost.py post "../../identidad_gloma/redes sociales/01_mensaje_1147pm" \
    --caption-file copy.txt --dry-run

# Publicar ya
$PY igpost.py post "…/01_mensaje_1147pm" --caption-file copy.txt

# Programar (hora de Bogotá)
$PY igpost.py schedule "…/01_mensaje_1147pm" \
    --caption-file copy.txt --at "2026-08-06 09:00"

$PY igpost.py list                # estado de la cola
$PY igpost.py cancel <id>
$PY igpost.py run-due             # lo dispara el cron
```

Pasarle una **carpeta** toma todas sus imágenes ordenadas como carrusel; pasarle
archivos sueltos usa exactamente esos, en ese orden.

## Mantenimiento

- **El token vence a los 60 días.** `whoami` avisa cuando quedan 10 o menos.
  Renovar con `igpost.py refresh-token` (Meta exige que el token tenga al menos
  24 h de vida). Renovar reinicia el contador a 60 días.
- **Límite de Meta**: 100 publicaciones por API en una ventana móvil de 24 h.
  Un carrusel cuenta como una sola. `whoami` muestra la cuota usada.
- **Carrusel**: entre 2 y 10 slides. Todas se recortan según la proporción de la
  primera.

## Seguridad

Cumple las reglas del proyecto (`CLAUDE.md`):

- El access token y el app secret **nunca** se imprimen ni se loggean;
  `Credentials` e `InstagramClient` tienen `__repr__` redactado.
- Los secretos viven cifrados en SSM, nunca en `.env` ni en el repo.
- Los errores de Meta van completos a `logger.exception`; al usuario le llega un
  mensaje corto.
- El bucket es privado con bloqueo público total: el acceso de Instagram es por
  URL prefirmada de vida corta.
