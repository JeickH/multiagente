#!/usr/bin/env python
"""Publicador y programador de Instagram para las marcas del portafolio.

Uso típico (ver README.md para el setup inicial):

    ./igpost.py whoami
    ./igpost.py schedule "identidad_gloma/redes sociales/01_mensaje_1147pm" \\
        --caption-file copy.txt --at "2026-08-06 09:00"
    ./igpost.py list
    ./igpost.py run-due          # lo corre el cron; publica lo que ya venció

Recordatorio: Instagram no tiene programación por API. `schedule` guarda en la
cola y sube las imágenes; `run-due` es quien realmente publica a la hora.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ig import client as ig_client  # noqa: E402
from ig import config, media, queue  # noqa: E402

# Zona horaria de operación: el CEO y la audiencia están en Colombia.
TZ = ZoneInfo("America/Bogota")

# Debe estar registrada como "OAuth redirect URI" en la app de Meta. La página
# puede no existir: solo necesitamos leer el `code` de la barra de direcciones.
DEFAULT_REDIRECT = "https://glomabeauty.com/ig-auth/"

MAX_ATTEMPTS = 3

logger = logging.getLogger("igpost")


# ── utilidades ────────────────────────────────────────────────────────────────

def slides_from(paths: list[str]) -> list[Path]:
    """Resuelve una carpeta de pieza (o una lista de archivos) a slides ordenadas."""
    if len(paths) == 1 and Path(paths[0]).is_dir():
        folder = Path(paths[0])
        found = sorted(
            [p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        )
        if not found:
            sys.exit(f"error: no hay imágenes en {folder}")
        return found
    resolved = [Path(p) for p in paths]
    missing = [p for p in resolved if not p.is_file()]
    if missing:
        sys.exit("error: no existen estos archivos: " + ", ".join(str(m) for m in missing))
    return resolved


def read_caption(args: argparse.Namespace) -> str:
    if args.caption_file:
        return Path(args.caption_file).read_text(encoding="utf-8").strip()
    if args.caption:
        return args.caption
    sys.exit("error: falta --caption o --caption-file")


def parse_when(raw: str) -> datetime:
    """Interpreta 'YYYY-MM-DD HH:MM' en hora de Bogotá."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    sys.exit(f"error: no entiendo la fecha {raw!r}. Usa 'YYYY-MM-DD HH:MM'.")


def get_client() -> tuple[ig_client.InstagramClient, config.Credentials]:
    creds = config.load()
    if creds.needs_refresh:
        print(f"aviso: el token vence en {creds.days_left} días. Corre: igpost.py refresh-token")
    return ig_client.InstagramClient(creds.access_token, creds.ig_user_id), creds


# ── comandos ──────────────────────────────────────────────────────────────────

def cmd_setup_app(args: argparse.Namespace) -> None:
    config.put_param("APP_ID", args.app_id)
    config.put_param("APP_SECRET", args.app_secret, secret=True)
    bucket = media.ensure_bucket()
    print("Credenciales de la app guardadas cifradas en SSM (sa-east-1).")
    print(f"Bucket de medios listo: s3://{bucket} (privado)")
    print("\nSiguiente paso:  igpost.py auth-url")


def cmd_auth_url(args: argparse.Namespace) -> None:
    app_id, _ = config.load_app()
    url = ig_client.authorization_url(app_id, args.redirect_uri)
    print("1. Abre este enlace con la sesión de Instagram de la marca:\n")
    print(f"   {url}\n")
    print("2. Autoriza. Te va a redirigir a una página que puede dar 404: es normal.")
    print("3. Copia el valor de `code=` de la barra de direcciones (sin el `#_` final).")
    print("4. Corre:  igpost.py connect --code <CODE>")


def cmd_connect(args: argparse.Namespace) -> None:
    """Guarda el token. Dos caminos:

    --code   el del flujo OAuth (`auth-url`).
    --token  el que genera directamente la consola de Meta en el panel
             "Instagram API setup with Instagram login". Es el camino corto.
    """
    app_id, app_secret = config.load_app()

    if args.token:
        token = args.token.strip()
        expires_in = 60 * 24 * 3600
        # El de la consola suele venir ya de larga duración. Si es de corta, el
        # canje lo convierte; si ya era largo, Meta responde error y seguimos
        # con el original, que es válido igual.
        try:
            canjeado = ig_client.to_long_lived(app_secret, token)
            token = canjeado["access_token"]
            expires_in = int(canjeado.get("expires_in", expires_in))
            print("Token canjeado a larga duración (60 días).")
        except ig_client.IGError:
            print("El token ya era de larga duración; se usa tal cual.")
    else:
        code = args.code.split("#")[0]
        short = ig_client.exchange_code(app_id, app_secret, code, args.redirect_uri)
        long_lived = ig_client.to_long_lived(app_secret, short["access_token"])
        token = long_lived["access_token"]
        expires_in = int(long_lived.get("expires_in", 60 * 24 * 3600))

    probe = ig_client.InstagramClient(token, "me")
    account = probe.me()

    expires_at = config.save_token(
        token, expires_in, account["id"], account["username"]
    )
    print(f"Conectado a @{account['username']} ({account.get('account_type')})")
    print(f"IG user id: {account['id']}")
    print(f"Token de larga duración guardado en SSM. Vence: {expires_at:%Y-%m-%d}")


def cmd_whoami(args: argparse.Namespace) -> None:
    client, creds = get_client()
    account = client.me()
    print(f"Cuenta:      @{account['username']} ({account.get('account_type')})")
    print(f"IG user id:  {account['id']}")
    print(f"Publicaciones: {account.get('media_count', '?')}  |  Seguidores: {account.get('followers_count', '?')}")
    if creds.expires_at:
        print(f"Token vence: {creds.expires_at:%Y-%m-%d} ({creds.days_left} días)")
    try:
        used = client.published_today()
        print(f"Cuota usada: {used}/{ig_client.DAILY_PUBLISH_LIMIT} en las últimas 24 h")
    except ig_client.IGError:
        pass


def cmd_refresh_token(args: argparse.Namespace) -> None:
    creds = config.load()
    result = ig_client.refresh(creds.access_token)
    expires_at = config.save_token(
        result["access_token"],
        int(result.get("expires_in", 60 * 24 * 3600)),
        creds.ig_user_id,
        creds.username or "",
    )
    print(f"Token renovado. Nueva expiración: {expires_at:%Y-%m-%d}")


def _upload_slides(slides: list[Path], slug: str) -> list[str]:
    media.ensure_bucket()
    keys = []
    for i, path in enumerate(slides, start=1):
        try:
            keys.append(media.upload(path, slug, i))
        except media.MediaError as exc:
            sys.exit(f"error: {exc}")
        print(f"  subida slide {i}/{len(slides)}: {path.name}")
    return keys


def _publish_keys(client: ig_client.InstagramClient, keys: list[str], caption: str) -> str:
    """Crea contenedores y publica. Devuelve el media_id."""
    urls = [media.presign(k) for k in keys]

    if len(urls) == 1:
        container = client.create_image(urls[0], caption=caption)
    else:
        children = []
        for i, url in enumerate(urls, start=1):
            children.append(client.create_image(url, carousel_item=True))
            print(f"  contenedor {i}/{len(urls)} creado")
        for child in children:
            client.wait_ready(child)
        container = client.create_carousel(children, caption)

    client.wait_ready(container)
    return client.publish(container)


def cmd_post(args: argparse.Namespace) -> None:
    slides = slides_from(args.paths)
    caption = read_caption(args)
    slug = args.slug or Path(args.paths[0]).name

    print(f"Pieza: {slug} — {len(slides)} slide(s)")
    if args.dry_run:
        for i, p in enumerate(slides, 1):
            data, size = media.prepare(p)
            print(f"  {i}. {p.name} → {size[0]}x{size[1]}, {len(data)//1024} KB")
        print(f"\nCaption ({len(caption)} chars):\n{caption}")
        print("\n(dry-run: no se subió ni publicó nada)")
        return

    client, _ = get_client()
    keys = _upload_slides(slides, slug)
    media_id = _publish_keys(client, keys, caption)
    link = client.permalink(media_id) or "(sin permalink)"
    print(f"\nPublicado. media_id={media_id}\n{link}")


def cmd_schedule(args: argparse.Namespace) -> None:
    slides = slides_from(args.paths)
    caption = read_caption(args)
    slug = args.slug or Path(args.paths[0]).name
    when = parse_when(args.at)

    if when <= datetime.now(TZ):
        sys.exit(f"error: {when:%Y-%m-%d %H:%M} ya pasó. Para publicar ahora usa `post`.")

    print(f"Pieza: {slug} — {len(slides)} slide(s) → {when:%Y-%m-%d %H:%M} (Bogotá)")
    keys = _upload_slides(slides, slug)
    post = queue.add(slug, caption, keys, when)
    print(f"\nProgramada. id={post.id}")
    print("La publica `run-due` a la hora indicada.")


def cmd_list(args: argparse.Namespace) -> None:
    posts = queue.load()
    if args.status:
        posts = [p for p in posts if p.status == args.status]
    if not posts:
        print("La cola está vacía.")
        return
    print(f"{'ID':<10}{'ESTADO':<12}{'CUANDO (Bogotá)':<20}{'SLIDES':<8}PIEZA")
    for p in posts:
        when = p.due_at.astimezone(TZ)
        print(f"{p.id:<10}{p.status:<12}{when:%Y-%m-%d %H:%M}     {len(p.media_keys):<8}{p.slug}")
        if p.error:
            print(f"{'':<10}└─ {p.error}")
        if p.permalink:
            print(f"{'':<10}└─ {p.permalink}")


def cmd_cancel(args: argparse.Namespace) -> None:
    try:
        post = queue.update(args.id, status="cancelled")
    except KeyError as exc:
        sys.exit(f"error: {exc}")
    print(f"Cancelada {post.id} ({post.slug}).")


def cmd_run_due(args: argparse.Namespace) -> None:
    """Punto de entrada del cron: publica todo lo que ya venció."""
    pending = queue.due()
    if not pending:
        print("Nada por publicar.")
        return

    print(f"{len(pending)} publicación(es) vencida(s).")
    if args.dry_run:
        for p in pending:
            print(f"  {p.id} {p.slug} — programada {p.due_at.astimezone(TZ):%Y-%m-%d %H:%M}")
        return

    client, _ = get_client()
    failures = 0
    for post in pending:
        print(f"\n→ {post.id} {post.slug}")
        try:
            media_id = _publish_keys(client, post.media_keys, post.caption)
            queue.update(
                post.id,
                status="published",
                media_id=media_id,
                permalink=client.permalink(media_id),
                published_at=datetime.now(timezone.utc).astimezone().isoformat(),
                error=None,
            )
            print(f"  publicado: {media_id}")
        except (ig_client.IGError, media.MediaError) as exc:
            failures += 1
            attempts = post.attempts + 1
            # Tras MAX_ATTEMPTS se marca failed para que no reintente en bucle.
            queue.update(
                post.id,
                attempts=attempts,
                error=str(exc),
                status="failed" if attempts >= MAX_ATTEMPTS else "pending",
            )
            logger.exception("Falló la publicación %s", post.id)
            print(f"  ERROR (intento {attempts}/{MAX_ATTEMPTS}): {exc}")

    if failures:
        sys.exit(1)


# ── parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="igpost", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true", help="log detallado")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup-app", help="guarda las credenciales de la app de Meta")
    p.add_argument("--app-id", required=True)
    p.add_argument("--app-secret", required=True)
    p.set_defaults(func=cmd_setup_app)

    p = sub.add_parser("auth-url", help="genera el enlace de autorización")
    p.add_argument("--redirect-uri", default=DEFAULT_REDIRECT)
    p.set_defaults(func=cmd_auth_url)

    p = sub.add_parser("connect", help="guarda el token de la cuenta")
    origen = p.add_mutually_exclusive_group(required=True)
    origen.add_argument("--code", help="el code que devuelve `auth-url`")
    origen.add_argument(
        "--token", help="token generado directamente en la consola de Meta (camino corto)"
    )
    p.add_argument("--redirect-uri", default=DEFAULT_REDIRECT)
    p.set_defaults(func=cmd_connect)

    sub.add_parser("whoami", help="valida el token y muestra la cuenta").set_defaults(
        func=cmd_whoami
    )
    sub.add_parser("refresh-token", help="renueva el token 60 días más").set_defaults(
        func=cmd_refresh_token
    )

    for name, help_text, fn in (
        ("post", "publica ahora mismo", cmd_post),
        ("schedule", "programa para una fecha futura", cmd_schedule),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("paths", nargs="+", help="carpeta de la pieza o lista de imágenes")
        p.add_argument("--caption")
        p.add_argument("--caption-file")
        p.add_argument("--slug", help="nombre corto de la pieza (por defecto, el de la carpeta)")
        if name == "schedule":
            p.add_argument("--at", required=True, help="'YYYY-MM-DD HH:MM' hora de Bogotá")
        else:
            p.add_argument("--dry-run", action="store_true")
        p.set_defaults(func=fn)

    p = sub.add_parser("list", help="muestra la cola")
    p.add_argument("--status", choices=["pending", "published", "failed", "cancelled"])
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("cancel", help="cancela una publicación programada")
    p.add_argument("id")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("run-due", help="publica lo vencido (punto de entrada del cron)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run_due)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        args.func(args)
    except config.ConfigError as exc:
        sys.exit(f"error: {exc}")
    except ig_client.IGError as exc:
        sys.exit(f"error: {exc}")
    except queue.QueueConflict as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
