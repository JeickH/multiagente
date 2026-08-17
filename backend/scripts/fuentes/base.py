"""Piezas comunes de los importadores de mascotas con revisión manual.

Todas las fuentes siguen el mismo camino, y ninguna escribe en la base sin que
un humano haya mirado antes:

    bajar()  ->  filtrar_nuevos()  ->  escribir_revision()  ->  [CEO aprueba]  ->  cargar()

`filtrar_nuevos` descarta lo que ya está en la base por `(source, origen_id)`,
que es la restricción única de la tabla. Por eso una fuente se puede volver a
correr las veces que sea: en la revisión solo aparece lo que todavía no existe.

Cada scraper devuelve dicts con los campos de `models.Mascota` más tres claves
privadas que no llegan a la base:

    _fotos    URLs de las fotos a descargar
    _crudo    el registro original de la fuente, para poder auditarlo
    _alertas  lo que un humano tiene que confirmar antes de aprobar
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

# Las fuentes se bajan desde el equipo del CEO, no desde ECS: el WAF de algunos
# sitios bloquea las IPs de AWS (lección de patitasacasa, ver el manual).
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Gloma-RecuperaTuMascota/1.0"
TIMEOUT = 30


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


ESPECIES = {
    "dog": "perro", "perro": "perro", "perra": "perro", "canino": "perro",
    "cat": "gato", "gato": "gato", "gata": "gato", "felino": "gato",
}
SEXOS = {
    "male": "macho", "macho": "macho", "m": "macho",
    "female": "hembra", "hembra": "hembra", "f": "hembra",
}

# Vocabulario alineado con `_SINONIMOS` del matcher (services/mascotas.py): si
# aquí se escribe "marrón" y allá se canoniza a "cafe", el cruce igual acierta.
COLORES = (
    "negro", "negra", "blanco", "blanca", "cafe", "marron", "chocolate",
    "carmelito", "dorado", "amarillo", "amarilla", "beige", "crema", "mostaza",
    "rubio", "rubia", "gris", "plateado", "atigrado", "rayado", "tigrillo",
    "naranja", "canela", "miel", "rojizo", "tricolor", "manchado", "manchas",
    "moteado", "pintado", "arena", "carey", "siames", "calico",
)
TAMANOS = {
    "pequeno": "pequeño", "chico": "pequeño", "chiquito": "pequeño",
    "small": "pequeño", "mini": "pequeño", "mediano": "mediano",
    "medium": "mediano", "grande": "grande", "big": "grande", "gigante": "grande",
}
EDADES = ("cachorro", "cachorra", "bebe", "puppy", "joven", "adulto", "viejo", "anciano")


def normalizar_especie(valor: Any) -> Optional[str]:
    return ESPECIES.get(sin_tildes(str(valor or "")).strip())


def normalizar_sexo(valor: Any) -> str:
    return SEXOS.get(sin_tildes(str(valor or "")).strip(), "desconocido")


def color_desde_texto(*textos: Optional[str]) -> Optional[str]:
    """Saca los colores que se nombran en un texto libre.

    Es una lectura, no una adivinanza: solo devuelve palabras que están escritas
    en la descripción. Aun así el HTML de revisión lo marca como derivado,
    porque «manchas» no es un color y el humano tiene que poder corregirlo.
    """
    texto = sin_tildes(" ".join(t for t in textos if t))
    vistos: List[str] = []
    for palabra in re.findall(r"[a-z]+", texto):
        if palabra in COLORES and palabra not in vistos:
            vistos.append(palabra)
    if not vistos:
        return None
    return " con ".join(vistos[:3])


def tamano_desde_texto(*textos: Optional[str]) -> Optional[str]:
    texto = sin_tildes(" ".join(t for t in textos if t))
    for palabra in re.findall(r"[a-z]+", texto):
        if palabra in TAMANOS:
            return TAMANOS[palabra]
    return None


def edad_desde_texto(*textos: Optional[str]) -> Optional[str]:
    texto = sin_tildes(" ".join(t for t in textos if t))
    m = re.search(r"\b(\d{1,2})\s*(anos?|meses|mes)\b", texto)
    if m:
        unidad = "año" if m.group(2).startswith("ano") else "mes"
        n = int(m.group(1))
        return f"{n} {unidad}{'es' if unidad == 'mes' and n != 1 else 's' if n != 1 else ''}"
    for palabra in re.findall(r"[a-z]+", texto):
        if palabra in EDADES:
            return palabra
    return None


def sexo_desde_texto(*textos: Optional[str]) -> str:
    """`macho`/`hembra` si el texto lo dice; si no, `desconocido`.

    Varias fuentes no tienen campo de sexo pero la gente lo escribe en la
    descripción ("Perrito macho", "Machito", "es una gata").
    """
    texto = sin_tildes(" ".join(t for t in textos if t))
    if re.search(r"\b(macho|machito|perrito|gatito|el perro|el gato)\b", texto):
        macho = True
    else:
        macho = False
    if re.search(r"\b(hembra|hembrita|perrita|gatica|gatita|la perra|la gata|una gata|una perra)\b", texto):
        return "hembra"
    return "macho" if macho else "desconocido"


# Un número de 7 a 10 dígitos suelto en un texto libre es, en estas fuentes,
# siempre un teléfono de contacto.
_TEL_EN_TEXTO = re.compile(r"(?<!\d)(?:\+?57[\s-]?)?([13]\d{2}[\s.-]?\d{3}[\s.-]?\d{4}|\d{7})(?!\d)")


def telefono_de_texto(*textos: Optional[str]) -> Optional[str]:
    """Rescata el teléfono que la gente escribe dentro de la descripción."""
    for texto in textos:
        if not texto:
            continue
        m = _TEL_EN_TEXTO.search(texto)
        if m:
            tel = telefono_colombiano(m.group(0))
            if tel:
                return tel
    return None


# Rótulos que quedan colgando cuando se le quita el número al texto
# ("Teléfonos de contacto: / "). Sin esto las señas terminan en basura.
_ROTULO_TEL = re.compile(
    r"\b(tel[eé]fonos?|cel(ular)?(es)?|whatsapp|wpp|contacto|informes?)\s*"
    r"(de\s+contacto)?\s*[:.-]*\s*[/,y\s-]*$",
    re.IGNORECASE,
)


def quitar_telefonos(texto: Optional[str]) -> Optional[str]:
    """Saca los números de un texto que va a leer el bot.

    Obligatorio antes de guardar en `senas` o `notas`: el guardarraíl
    `_viola_contacto` descarta el turno completo si el bot escribe un número
    que no vino de `entregar_contacto`. Un teléfono metido en la descripción
    haría que el bot se quedara mudo justo cuando encontró a la mascota.
    """
    if not texto:
        return texto
    limpio = _TEL_EN_TEXTO.sub("", texto)
    limpio = re.sub(r"\s{2,}", " ", limpio).strip()
    for _ in range(3):          # "…contacto: / y" necesita varias pasadas
        nuevo = _ROTULO_TEL.sub("", limpio).strip()
        nuevo = re.sub(r"[\s.,;:_/-]+$", "", nuevo)
        if nuevo == limpio:
            break
        limpio = nuevo
    return limpio or None


# Lo que la gente escribe cuando no hay nombre o no hay zona. Guardarlos sería
# peor que dejarlos vacíos: el cruce puntúa el nombre y la zona, y "Anonimo"
# contra "Anonimo" daría un parecido que no existe.
_SIN_VALOR = {
    "anonimo", "anonima", "anonimos", "anonimas", "sin nombre", "no tiene nombre",
    "desconocido", "desconocida", "n/a", "na", "no se sabe", "ninguno", "-", "?",
    "rescatado", "rescatada", "rescatados", "rescatadas", "encontrado", "encontrada",
    "perdido", "perdida", "me perdi", "sin datos", "no aplica",
}


def valor_real(texto: Any, limite: int) -> Optional[str]:
    """Devuelve el texto, o None si es uno de esos rellenos que no dicen nada."""
    limpio = limpiar(texto, limite)
    if not limpio or sin_tildes(limpio).strip(" .") in _SIN_VALOR:
        return None
    return limpio


def telefono_colombiano(valor: Any) -> Optional[str]:
    """Deja el número en formato local. Devuelve None si no parece un teléfono.

    Las fuentes lo publican de todas las formas: `57XXXXXXXXXX`, `+57 3XX…`,
    `3XX-XXX-XXXX`. El bot lo va a leer en voz alta a alguien angustiado.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if digitos.startswith("57") and len(digitos) == 12:
        digitos = digitos[2:]
    if len(digitos) == 10 and digitos.startswith("3"):
        return f"{digitos[:3]} {digitos[3:]}"
    if len(digitos) in (7, 8):          # fijo sin indicativo
        return digitos
    return None


def limpiar(texto: Any, limite: int) -> Optional[str]:
    if texto is None:
        return None
    t = re.sub(r"\s+", " ", str(texto)).strip()
    return t[:limite] or None


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def bajar_json(url: str) -> Any:
    import requests

    r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def bajar_html(url: str) -> str:
    import requests

    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def bajar_fotos(registros: List[Dict[str, Any]], carpeta: str, max_por_registro: int = 3) -> int:
    """Baja las fotos a disco y deja en cada registro el nombre de archivo.

    Se bajan ahora y no en la carga porque hay fuentes (Protección Animal) que
    firman las URLs con vencimiento de una hora: si se esperara a la aprobación,
    ya no servirían.
    """
    import requests

    os.makedirs(carpeta, exist_ok=True)
    total = 0
    for reg in registros:
        reg["fotos"] = []
        for i, url in enumerate(reg.get("_fotos", [])[:max_por_registro]):
            try:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
                r.raise_for_status()
                tipo = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                ext = {"image/png": ".png", "image/webp": ".webp"}.get(tipo, ".jpg")
                nombre = f"{re.sub(r'[^A-Za-z0-9_.-]', '_', reg['origen_id'])}_{i}{ext}"
                with open(os.path.join(carpeta, nombre), "wb") as fh:
                    fh.write(r.content)
                reg["fotos"].append({"archivo": nombre, "content_type": tipo})
                total += 1
            except Exception as exc:
                reg.setdefault("_alertas", []).append(
                    f"No se pudo bajar una foto de la fuente: {exc}"
                )
    return total


# ---------------------------------------------------------------------------
# Deduplicación contra la base
# ---------------------------------------------------------------------------

def origen_ids_existentes(source: str) -> set:
    """Los `origen_id` que esta fuente ya tiene cargados.

    Dos caminos porque hay dos contextos: dentro del contenedor / de ECS la
    conexión directa funciona, pero los scrapers corren en el equipo del CEO,
    donde el Postgres del host tapa al de docker y las credenciales del `.env`
    no son las del contenedor. Ahí se pregunta por `docker compose exec`.
    """
    try:
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        try:
            filas = (
                db.query(models.Mascota.origen_id)
                .filter(models.Mascota.source == source,
                        models.Mascota.origen_id.isnot(None))
                .all()
            )
            return {f[0] for f in filas}
        finally:
            db.close()
    except Exception:
        return _origen_ids_por_docker(source)


def _origen_ids_por_docker(source: str) -> set:
    import subprocess

    sql = (
        "SELECT origen_id FROM mascotas "
        f"WHERE source = '{source}' AND origen_id IS NOT NULL;"
    )
    salida = subprocess.run(
        ["docker", "compose", "-p", "wati", "exec", "-T", "db",
         "psql", "-U", os.getenv("POSTGRES_USER", "equipo"),
         "-d", os.getenv("POSTGRES_DB", "multiagente_db"), "-tAc", sql],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    return {linea.strip() for linea in salida.splitlines() if linea.strip()}


def filtrar_nuevos(registros: List[Dict[str, Any]], source: str) -> tuple:
    """Devuelve (nuevos, ya_estaban). Nunca se propone cargar dos veces lo mismo."""
    try:
        existentes = origen_ids_existentes(source)
    except Exception as exc:
        print(f"  aviso: no pude consultar la base para deduplicar ({exc}).")
        print("  el HTML va a mostrar TODO; la carga igual salta lo repetido.")
        existentes = set()
    nuevos = [r for r in registros if r["origen_id"] not in existentes]
    return nuevos, len(registros) - len(nuevos)


# ---------------------------------------------------------------------------
# Validación previa (lo mismo que exigirá `crear_reporte`)
# ---------------------------------------------------------------------------

def revisar(registros: List[Dict[str, Any]], derivados: Iterable[str] = ()) -> None:
    """Marca en cada registro lo que un humano tiene que confirmar."""
    por_clave: Dict[tuple, List[Dict]] = {}
    for reg in registros:
        reg.setdefault("_alertas", [])
        if not reg.get("ubicacion"):
            reg["_alertas"].append(
                "<b>Sin ubicación</b>, que es obligatoria. La base lo va a rechazar."
            )
        if not reg.get("contacto_telefono") and not reg.get("origen_url"):
            reg["_alertas"].append(
                "<b>Sin teléfono ni enlace de origen</b>: nadie podría contactar a quien "
                "reportó. La base lo va a rechazar."
            )
        if not reg.get("fotos"):
            reg["_alertas"].append("Sin foto: la ficha entra, pero sirve mucho menos.")
        # Los campos leídos de la descripción no son un problema, solo un dato de
        # segunda mano: se marcan en la fila del campo, no como alerta. Si fueran
        # alerta, todas las fichas tendrían una y el contador dejaría de servir.
        reg["_derivados"] = [c for c in derivados if reg.get(c)]
        clave = (reg.get("especie"), (reg.get("nombre") or "").lower(),
                 reg.get("barrio"))
        if clave[1]:
            por_clave.setdefault(clave, []).append(reg)
    for clave, grupo in por_clave.items():
        if len(grupo) > 1:
            ids = ", ".join(g["origen_id"] for g in grupo)
            for g in grupo:
                g["_alertas"].append(
                    f"<b>Posible duplicado dentro de la fuente</b>: {len(grupo)} fichas con "
                    f"el mismo nombre, especie y zona ({ids})."
                )


# ---------------------------------------------------------------------------
# Informe de revisión
# ---------------------------------------------------------------------------

CAMPOS = (
    "tipo_registro", "especie", "raza", "color", "nombre", "sexo", "edad",
    "tamano", "senas", "ubicacion", "barrio", "maps_url", "contacto_nombre",
    "contacto_telefono", "origen_url", "origen_id", "fecha_evento", "notas",
)


def _esc(v: Any) -> str:
    if v is None or v == "":
        return '<span class="nulo">NULL</span>'
    return html.escape(str(v))


def _miniatura(ruta: str, ancho: int = 420) -> Optional[str]:
    try:
        from PIL import Image

        with Image.open(ruta) as im:
            im = im.convert("RGB")
            if im.width > ancho:
                im = im.resize((ancho, round(im.height * ancho / im.width)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def escribir_revision(
    registros: List[Dict[str, Any]],
    *,
    salida: str,
    carpeta_fotos: str,
    fuente: str,
    titulo: str,
    url_fuente: str,
    como_se_lleno: List[str],
    ya_estaban: int = 0,
    descartados: Optional[Dict[str, int]] = None,
) -> None:
    con_alerta = sum(1 for r in registros if r["_alertas"])
    por_tipo: Dict[str, int] = {}
    for r in registros:
        por_tipo[r["tipo_registro"]] = por_tipo.get(r["tipo_registro"], 0) + 1

    tarjetas = []
    for i, reg in enumerate(registros, 1):
        fotos_html = ""
        for foto in reg.get("fotos", []):
            src = _miniatura(os.path.join(carpeta_fotos, foto["archivo"]))
            if src:
                fotos_html += f'<img src="{src}" alt="{_esc(reg.get("nombre"))}">'
        if not fotos_html:
            fotos_html = '<div class="sin-foto">sin foto</div>'
        alertas = "".join(f"<li>{a}</li>" for a in reg["_alertas"])
        alertas = f'<ul class="alertas">{alertas}</ul>' if alertas else ""
        derivados_reg = set(reg.get("_derivados") or ())
        campos = "".join(
            f"<tr><th>{c}</th><td>{_esc(reg.get(c))}"
            + ('<span class="derivado">leído de la descripción</span>'
               if c in derivados_reg else "")
            + "</td></tr>"
            for c in CAMPOS
        )
        crudo = json.dumps(reg.get("_crudo", {}), ensure_ascii=False, indent=1)
        tarjetas.append(f"""
        <article class="ficha{' con-alerta' if reg['_alertas'] else ''}">
          <div class="col-foto"><span class="num">{i:03d}</span>{fotos_html}</div>
          <div class="col-datos">
            <h2>{_esc(reg.get('nombre') or '(sin nombre)')}
              <span class="chip {reg['tipo_registro']}">{reg['tipo_registro']}</span></h2>
            {alertas}
            <table class="campos">{campos}</table>
            <details><summary>Registro original de la fuente</summary>
              <pre>{html.escape(crudo)}</pre></details>
          </div>
        </article>""")

    filas_desc = "".join(
        f"<tr><td>{_esc(k)}</td><td>{v}</td></tr>"
        for k, v in sorted((descartados or {}).items(), key=lambda kv: -kv[1])
    )
    bloque_desc = (
        f'<h3 style="margin-top:16px">No se traen</h3><table class="mini">{filas_desc}</table>'
        if filas_desc else ""
    )
    tipos = " · ".join(f"{v} {k}s" for k, v in sorted(por_tipo.items()))

    with open(salida, "w", encoding="utf-8") as fh:
        fh.write(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)} · revisión previa</title>
<style>
  :root {{ --tinta:#12211c; --suave:#5d726a; --linea:#dfe7e3; --fondo:#f6f8f7;
           --acento:#0f5c46; --alerta:#b4530a; --alerta-bg:#fff6ec; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--fondo); color:var(--tinta);
         font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  header {{ background:#fff; border-bottom:1px solid var(--linea); padding:32px 28px; }}
  .wrap {{ max-width:1080px; margin:0 auto; }}
  h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:-.3px; }}
  .sub {{ color:var(--suave); margin:0 0 22px; }}
  .kpis {{ display:flex; flex-wrap:wrap; gap:10px; }}
  .kpi {{ background:var(--fondo); border:1px solid var(--linea); border-radius:10px;
          padding:10px 16px; min-width:120px; }}
  .kpi b {{ display:block; font-size:24px; line-height:1.2; }}
  .kpi span {{ color:var(--suave); font-size:12.5px; }}
  main {{ padding:28px; }}
  .aviso {{ background:#fff; border:1px solid var(--linea); border-left:4px solid var(--acento);
            border-radius:10px; padding:18px 22px; margin-bottom:26px; }}
  .aviso h3 {{ margin:0 0 8px; font-size:15px; }}
  .aviso ul {{ margin:0; padding-left:20px; color:var(--suave); }}
  .aviso li {{ margin:4px 0; }}
  table.mini {{ border-collapse:collapse; margin-top:10px; font-size:13.5px; }}
  table.mini td {{ border:1px solid var(--linea); padding:4px 12px; }}
  .ficha {{ display:grid; grid-template-columns:190px 1fr; gap:26px; background:#fff;
            border:1px solid var(--linea); border-radius:12px; padding:20px; margin-bottom:18px; }}
  .ficha.con-alerta {{ border-color:#e8c9a4; }}
  .col-foto {{ position:relative; display:flex; flex-direction:column; gap:8px; }}
  .col-foto img {{ width:100%; border-radius:8px; display:block; background:#eee; }}
  .sin-foto {{ background:#f0f4f2; color:var(--suave); border-radius:8px; padding:36px 0;
               text-align:center; font-size:13px; }}
  .num {{ position:absolute; top:6px; left:6px; background:rgba(0,0,0,.62); color:#fff;
          border-radius:6px; padding:2px 8px; font-size:12px; font-weight:600; z-index:1; }}
  h2 {{ margin:0 0 12px; font-size:19px; display:flex; align-items:center; gap:10px;
        flex-wrap:wrap; }}
  .chip {{ font-size:11.5px; font-weight:600; padding:3px 9px; border-radius:999px;
           text-transform:uppercase; letter-spacing:.03em; }}
  .chip.encontrada {{ background:#e3f2ec; color:#0f5c46; }}
  .chip.perdida {{ background:#fdeceb; color:#a6301f; }}
  .alertas {{ background:var(--alerta-bg); border:1px solid #f0d7b8; border-radius:8px;
              margin:0 0 14px; padding:10px 10px 10px 28px; color:var(--alerta); font-size:13.5px; }}
  .alertas li {{ margin:3px 0; }}
  table.campos {{ border-collapse:collapse; width:100%; font-size:14px; }}
  table.campos th {{ text-align:left; font-weight:600; color:var(--suave); width:160px;
                     vertical-align:top; padding:5px 12px 5px 0;
                     font-family:ui-monospace,monospace; font-size:12.5px; }}
  table.campos td {{ padding:5px 0; border-bottom:1px solid #f0f4f2; }}
  .nulo {{ color:#b9c5c0; font-style:italic; }}
  .derivado {{ margin-left:8px; font-size:11px; color:#8a7a5e; background:#fdf7ec;
               border:1px solid #f0e2c8; border-radius:5px; padding:1px 6px;
               white-space:nowrap; }}
  details {{ margin-top:14px; }}
  summary {{ cursor:pointer; color:var(--acento); font-size:13px; }}
  pre {{ background:#f6f8f7; border:1px solid var(--linea); border-radius:8px; padding:12px;
         font-size:12px; overflow-x:auto; }}
  @media (max-width:720px) {{ .ficha {{ grid-template-columns:1fr; }} }}
</style></head><body>
<header><div class="wrap">
  <h1>{html.escape(titulo)}</h1>
  <p class="sub">Revisión previa de la carga a <code>mascotasperdidascolombia.com</code>.
     Fuente: <a href="{html.escape(url_fuente)}">{html.escape(url_fuente)}</a> ·
     <code>source = {html.escape(fuente)}</code> ·
     {datetime.now().strftime('%Y-%m-%d %H:%M')}.
     <b>Nada se ha escrito en la base todavía.</b></p>
  <div class="kpis">
    <div class="kpi"><b>{len(registros)}</b><span>se cargarían</span></div>
    <div class="kpi"><b>{tipos or '—'}</b><span>por tipo</span></div>
    <div class="kpi"><b>{ya_estaban}</b><span>ya estaban en la base</span></div>
    <div class="kpi"><b>{con_alerta}</b><span>con algo por revisar</span></div>
  </div>
</div></header>
<main><div class="wrap">
  <div class="aviso">
    <h3>Cómo se llenó cada campo</h3>
    <ul>{''.join(f'<li>{c}</li>' for c in como_se_lleno)}</ul>
    {bloque_desc}
  </div>
  {''.join(tarjetas)}
</div></main></body></html>""")


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def guardar_pendientes(registros: List[Dict[str, Any]], ruta: str) -> None:
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(
            [{k: v for k, v in r.items() if k != "_fotos"} for r in registros],
            fh, ensure_ascii=False, indent=1,
        )


def ejecutar(
    fuente: str,
    titulo: str,
    url_fuente: str,
    bajar: Callable[[], tuple],
    como_se_lleno: List[str],
    derivados: Iterable[str],
    carpeta: str,
) -> None:
    """Paso 1 del flujo: baja, deduplica, arma el HTML. No toca la base."""
    os.makedirs(carpeta, exist_ok=True)
    print(f"[{fuente}] bajando de {url_fuente} ...")
    registros, descartados = bajar()
    print(f"[{fuente}] {len(registros)} candidatos")

    nuevos, ya_estaban = filtrar_nuevos(registros, fuente)
    print(f"[{fuente}] {ya_estaban} ya estaban en la base, {len(nuevos)} nuevos")
    if not nuevos:
        print(f"[{fuente}] nada nuevo que revisar.")
        return

    carpeta_fotos = os.path.join(carpeta, "fotos")
    n = bajar_fotos(nuevos, carpeta_fotos)
    print(f"[{fuente}] {n} fotos descargadas")

    revisar(nuevos, derivados)
    guardar_pendientes(nuevos, os.path.join(carpeta, "pendientes.json"))
    salida = os.path.join(carpeta, "revision.html")
    escribir_revision(
        nuevos, salida=salida, carpeta_fotos=carpeta_fotos, fuente=fuente,
        titulo=titulo, url_fuente=url_fuente, como_se_lleno=como_se_lleno,
        ya_estaban=ya_estaban, descartados=descartados,
    )
    con_alerta = sum(1 for r in nuevos if r["_alertas"])
    print(f"[{fuente}] revisión lista: {salida}")
    print(f"[{fuente}] {len(nuevos)} para cargar, {con_alerta} con algo por revisar")
