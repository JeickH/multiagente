"""Extrae el reporte de RoyiPets (PDF) a los campos de la tabla `mascotas`.

Entrada:  testdata/REPORTE MASCOTAS - DATOS.pdf
Salidas:  fotos/<ref>.png      una por fila del PDF
          rows_raw.json        la tabla del PDF tal cual, celda por celda
          registros.json       ya mapeado a los campos de `models.Mascota`
          revision.html        el informe para que el CEO valide antes de cargar

El PDF no trae rejilla vectorial: las columnas se reconstruyen por la x de cada
palabra y las filas por el recuadro de la foto (las dos filas sin foto se
resuelven por el hueco que dejan las fotos vecinas).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil

import pymupdf
from PIL import Image

# El script vive en el repo, pero el material crudo (PDF de la fundación) y lo
# que produce (fotos, revisión) viven en `testdata/`, que está git-ignorado: son
# ~113 MB de insumo, y fotos de gente real.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.getenv("ROYIPETS_DIR", os.path.join(REPO, "testdata", "royipets_import"))
PDF = os.getenv("ROYIPETS_PDF", os.path.join(REPO, "testdata", "REPORTE MASCOTAS - DATOS.pdf"))
FOTOS = os.path.join(BASE, "fotos")

# Datos que el CEO fijó para toda la carga.
UBICACION = "RoyiPets, Cali"
CONTACTO_NOMBRE = "RoyiPets"
CONTACTO_TELEFONO = "310 4261293"
SOURCE = "royipets"
LOTE = "reporte-2026-08-16"

# (x_desde, x_hasta, columna). Salen de las x reales de los datos, no del
# encabezado: los títulos están centrados y los valores alineados a la izquierda.
BOUNDS = [
    (100, 132, "esterilizado"), (132, 152, "fecha_recepcion"), (152, 172, "nombre"),
    (172, 212, "especie"), (212, 255, "genero"), (255, 298, "raza"),
    (298, 345.5, "caracteristicas"), (345.5, 400, "quien_trajo"), (400, 424, "numero"),
    (424, 472, "donde_encontrado"), (472, 500, "lesiones"), (500, 575, "estado_adopcion"),
    (575, 612, "fecha_cambio"), (612, 665, "ubicacion"), (665, 722, "responsable"),
    (722, 748.5, "contacto"), (748.5, 900, "notas"),
]


def columna(x: float) -> str | None:
    for desde, hasta, nombre in BOUNDS:
        if desde <= x < hasta:
            return nombre
    return None


def extraer_filas() -> list[dict]:
    shutil.rmtree(FOTOS, ignore_errors=True)
    os.makedirs(FOTOS)
    doc = pymupdf.open(PDF)
    filas = []
    for pno, page in enumerate(doc):
        palabras = [w for w in page.get_text("words") if w[1] > 62]   # sin encabezado
        # Cada fila tiene exactamente un valor en ESPECIE (PERRO/GATO): sirve de ancla.
        anclas = sorted((w[1] + w[3]) / 2 for w in palabras if 172 <= w[0] < 212)
        if not anclas:
            continue
        recuadros = sorted(
            (r.y0, r.y1, img[0])
            for img in page.get_images(full=True)
            for r in page.get_image_rects(img[0])
        )
        bandas = []
        for ancla in anclas:
            foto = next((b for b in recuadros if b[0] - 1 <= ancla <= b[1] + 1), None)
            bandas.append(list(foto) if foto else [None, None, None])
        for i, banda in enumerate(bandas):   # fila sin foto: ocupa el hueco vecino
            if banda[0] is None:
                banda[0] = next(
                    (bandas[j][1] for j in range(i - 1, -1, -1) if bandas[j][1]), 62.0
                )
                banda[1] = next(
                    (bandas[j][0] for j in range(i + 1, len(bandas)) if bandas[j][0]),
                    float(page.rect.y1),
                )

        celdas: list[dict] = [{} for _ in bandas]
        for w in palabras:
            cy = (w[1] + w[3]) / 2
            idx = next(
                (i for i, (y0, y1, _) in enumerate(bandas) if y0 - 1 <= cy <= y1 + 1), None
            )
            if idx is None:   # texto que se desborda de su celda: a la fila más cercana
                idx = min(
                    range(len(bandas)),
                    key=lambda i: min(abs(cy - bandas[i][0]), abs(cy - bandas[i][1])),
                )
            col = columna(w[0])
            if col:
                celdas[idx].setdefault(col, []).append((round(w[1], 1), round(w[0], 1), w[4], w[2]))

        for i, (y0, y1, xref) in enumerate(bandas):
            fila = {"ref": f"p{pno + 1}r{i + 1}", "pagina": pno + 1}
            for col, ws in celdas[i].items():
                ws.sort()
                fila[col] = " ".join(t for _, _, t, _ in ws)
            # Excel recorta el texto que no cabe: una sola línea que topa el borde
            # derecho de la celda es descripción incompleta, no descripción corta.
            desc = celdas[i].get("caracteristicas", [])
            fila["carac_cortada"] = (
                bool(desc)
                and len({y for y, _, _, _ in desc}) == 1
                and max(e for *_, e in desc) > 343
            )
            fila["foto"] = None
            if xref:
                img = doc.extract_image(xref)
                fila["foto"] = f"{fila['ref']}.{img['ext']}"
                with open(os.path.join(FOTOS, fila["foto"]), "wb") as fh:
                    fh.write(img["image"])
            filas.append(fila)
    return filas


# --------------------------------------------------------------------------
# Mapeo a la tabla `mascotas`
# --------------------------------------------------------------------------

ESPECIE = {"PERRO": "perro", "GATO": "gato"}
SEXO = {"MACHO": "macho", "HEMBRA": "hembra"}
RAZA = {"CRIOLLO": "criollo", "MESTIZO": "mestizo", "BASTOR BELGA": "pastor belga",
        "BULL DOG FRANCES": "bulldog francés"}

# Color / tamaño / edad salen de leer CARACTERISTICAS una por una. Se dejan
# explícitos porque el color pesa 5 en el scoring y una heurística lo llenaría mal.
DERIVADOS = {
    "p1r2":  {"color": "blanco"},
    "p1r3":  {"color": "blanco con negro"},
    "p1r5":  {"color": "negro"},
    "p2r6":  {"color": "blanco"},
    "p2r8":  {"color": "blanco con manchas cafés y negras"},
    "p2r9":  {"color": "café claro"},
    "p2r10": {"color": "negro"},
    "p2r11": {"tamano": "grande"},
    "p2r12": {"color": "blanco"},
    "p3r1":  {"tamano": "pequeño"},
    "p3r2":  {"color": "gris con blanco"},
    "p3r3":  {"color": "negro con blanco"},
    "p3r4":  {"edad": "cachorro"},
    "p3r7":  {"color": "atigrado"},
    "p5r2":  {"color": "negro con blanco"},
    "p5r3":  {"color": "amarillo, hocico negro"},
    "p5r7":  {"color": "negro", "tamano": "grande"},
    "p6r1":  {"color": "blanco con amarillo"},
}

# Las fichas cuya descripción no dice de qué color es el animal: el color se
# sacó mirando la foto, no el documento. Se marca aparte para que en la revisión
# quede claro de dónde salió cada dato.
COLOR_FOTO = {
    "p1r11": "negro con blanco",
    "p1r13": "blanco con negro",
    "p2r1":  "café atigrado con blanco",
    "p2r2":  "blanco con gris atigrado",
    "p2r3":  "negro",
    "p2r4":  "negro",
    "p2r5":  "beige con pecho blanco",
    "p2r11": "negro con blanco",
    "p3r1":  "blanco con negro",
    "p3r4":  "blanco con canela",
    "p3r5":  "café con blanco",
    "p3r6":  "blanco con negro",
    "p3r8":  "café atigrado con blanco",
    "p3r11": "naranja con blanco",
    "p4r11": "negro con canela",
    "p4r12": "atigrado oscuro",
    "p5r1":  "negro con blanco",
}

ZONA_VACIA = {"?", "NA", "N/A", "NO SE SABE"}
RE_TELEFONO = re.compile(r"\b\d[\d\s\-]{6,}\d\b")


def _titulo(texto: str) -> str:
    """Baja el TODO-MAYÚSCULAS del Excel, dejando las siglas (CBA) como están.

    Solo para lugares: en un nombre de persona un apellido corto ("GIL", "RUA")
    no es una sigla y quedaría gritando. Para eso está `_nombre`.
    """
    return " ".join(
        p.capitalize() if p.isupper() and len(p) > 3 else p for p in texto.split()
    )


def _nombre(texto: str) -> str:
    """Nombre de persona: todo en Capitalizado, sin excepción de siglas."""
    return " ".join(p.capitalize() if p.isupper() else p for p in texto.split())


def _fecha(valor: str | None) -> str | None:
    """'14-08-26' (dd-mm-aa) -> '2026-08-14'."""
    if not valor:
        return None
    m = re.search(r"\b(\d{2})-(\d{2})-(\d{2})\b", valor)
    return f"20{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def mapear(fila: dict) -> dict:
    ref = fila["ref"]
    extra = DERIVADOS.get(ref, {})
    donde = (fila.get("donde_encontrado") or "").strip()
    zona = None if donde.upper() in ZONA_VACIA or not donde else _titulo(donde)

    # Un animal en hogar de paso tiene dos vías de contacto: RoyiPets y la casa
    # donde está durmiendo. Van las dos en el mismo campo, que es lo que
    # `entregar_contacto` le pasa a quien lo está buscando.
    telefono, contacto_nombre = CONTACTO_TELEFONO, CONTACTO_NOMBRE
    tel_hogar = (fila.get("contacto") or "").strip()
    if tel_hogar:
        telefono = f"{CONTACTO_TELEFONO} / {tel_hogar}"
        if fila.get("responsable"):
            contacto_nombre = (
                f"{CONTACTO_NOMBRE} / {_nombre(fila['responsable'])} (hogar de paso)"
            )

    notas = [f"Reporte RoyiPets (fila {ref} del PDF del 2026-08-16)."]
    notas.append(f"Estado en RoyiPets: {fila.get('estado_adopcion')}.")
    if fila.get("ubicacion"):
        notas.append(f"Ubicación interna: {fila['ubicacion']}.")
    notas.append(f"Esterilizado: {fila.get('esterilizado') or 'sin dato'}.")
    notas.append(f"Lesiones: {fila.get('lesiones') or 'sin dato'}.")
    if fila.get("responsable"):
        notas.append(f"Responsable del hogar de paso: {_nombre(fila['responsable'])}.")
    if fila.get("notas"):
        # Se borran los teléfonos de terceros: el único número que puede existir
        # en un reporte es el de contacto (regla 2 del manual).
        notas.append(f"Nota del reporte: {RE_TELEFONO.sub('[teléfono omitido]', fila['notas'])}")

    # Campos multi-fuente (2026-08-17): antes esto vivía solo dentro de `notas`,
    # donde no se puede filtrar. La columna «UBICACIÓN» del PDF es dónde está
    # durmiendo el animal, no una dirección.
    resguardo = {
        "HOSPITAL": "hospital", "HOSPITAL ROYI": "hospital",
        "HOGAR DE PASO": "hogar_de_paso", "TERCERO": "con_quien_la_encontro",
        "DUEÑOS": "con_su_familia", "ADOPTADO": "con_su_familia",
    }.get((fila.get("ubicacion") or "").strip().upper())
    lesiones = (fila.get("lesiones") or "").strip().upper()

    return {
        "ref": ref,
        "tipo_registro": "encontrada",
        "ciudad": "Cali",
        "departamento": "Valle del Cauca",
        "esterilizado": fila.get("esterilizado"),   # `_booleano` filtra "NO SE SABE"
        "vacunado": None,
        "desparasitado": None,
        "peso_kg": None,
        "salud": "Con lesiones" if lesiones == "SI" else None,
        "resguardo": resguardo,
        "resguardo_nombre": _nombre(fila["responsable"]) if fila.get("responsable") else None,
        # Quien llevó el animal a RoyiPets: una tercera persona, distinta de
        # quien lo cuida hoy y de quien atiende el teléfono.
        "rescatado_por": _nombre(fila["quien_trajo"]) if fila.get("quien_trajo") else None,
        "rescatado_por_telefono": (fila.get("numero") or "").strip() or None,
        "recompensa": None,
        "estado_origen": fila.get("estado_adopcion"),
        "publicado_origen_at": None,
        "especie": ESPECIE.get(fila.get("especie", ""), "otra"),
        "raza": RAZA.get(fila.get("raza", ""), (fila.get("raza") or "").lower() or None),
        "color": extra.get("color") or COLOR_FOTO.get(ref),
        "nombre": f"{fila.get('nombre', '').strip()} (temporal)",
        "sexo": SEXO.get(fila.get("genero", ""), "desconocido"),
        "edad": extra.get("edad"),
        "tamano": extra.get("tamano"),
        "senas": fila.get("caracteristicas"),
        "ubicacion": UBICACION,
        "maps_url": None,
        "barrio": zona,
        "contacto_nombre": contacto_nombre,
        "contacto_telefono": telefono,
        "fecha_evento": _fecha(fila.get("fecha_recepcion") or fila.get("esterilizado")),
        "estado": "activo",
        "notas": " ".join(notas),
        "source": SOURCE,
        "origen_id": f"{LOTE}-{ref}",
        "foto": fila["foto"],
        "_alertas": [],
        "_pdf": fila,
    }


def revisar(registros: list[dict]) -> None:
    """Marca lo que un humano tiene que mirar antes de cargar."""
    por_nombre: dict[tuple, list[dict]] = {}
    for r in registros:
        if r["_pdf"]["carac_cortada"]:
            r["_alertas"].append(
                "La descripción viene <b>cortada en el PDF</b> (Excel recortó lo que no "
                "cabía en la celda). Hay que completarla a mano."
            )
        nota = (r["_pdf"].get("notas") or "").upper()
        if re.search(r"APAREC(IÓ|IO)\s+(LA\s+DUEÑA|EL\s+DUEÑO)", nota):
            r["_alertas"].append(
                "La nota del reporte dice que <b>ya apareció el dueño</b>, pero el estado "
                "sigue en DISPONIBLE. Confirmar antes de publicarla como encontrada."
            )
        if r["ref"] in COLOR_FOTO:
            r["_alertas"].append(
                f"El <b>color</b> (<i>{r['color']}</i>) no está en el documento: lo saqué "
                "mirando la foto, porque pesa 5 en el cruce. Verifícalo."
            )
        elif not r["color"]:
            r["_alertas"].append(
                "Sin <b>color</b>: ni la descripción ni la foto permiten definirlo."
            )
        clave = (r["_pdf"].get("nombre"), r["especie"], r["sexo"])
        por_nombre.setdefault(clave, []).append(r)
    for clave, grupo in por_nombre.items():
        if len(grupo) > 1:
            refs = ", ".join(g["ref"] for g in grupo)
            for g in grupo:
                g["_alertas"].append(
                    f"<b>Posible duplicado</b>: hay {len(grupo)} filas con el mismo nombre, "
                    f"especie y sexo ({refs})."
                )


# --------------------------------------------------------------------------
# Informe
# --------------------------------------------------------------------------

CAMPOS = [
    ("codigo", "se asigna solo al insertar (MC-000NN)"),
    ("tipo_registro", ""), ("especie", ""), ("raza", ""), ("color", ""),
    ("nombre", ""), ("sexo", ""), ("edad", ""), ("tamano", ""), ("senas", ""),
    ("ubicacion", ""), ("barrio", ""), ("maps_url", ""),
    ("contacto_nombre", ""), ("contacto_telefono", ""),
    ("fecha_evento", ""), ("estado", ""), ("source", ""), ("origen_id", ""),
    ("notas", ""),
]


def miniatura(nombre: str, ancho: int = 460) -> str:
    with Image.open(os.path.join(FOTOS, nombre)) as im:
        im = im.convert("RGB")
        if im.width > ancho:
            im = im.resize((ancho, round(im.height * ancho / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def esc(v) -> str:
    if v is None or v == "":
        return '<span class="nulo">NULL</span>'
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def html(registros: list[dict], todas: list[dict]) -> str:
    descartadas: dict[str, int] = {}
    for f in todas:
        estado = f.get("estado_adopcion") or "(sin estado)"
        if "DISPONIBLE" not in estado:
            descartadas[estado] = descartadas.get(estado, 0) + 1
    con_alerta = sum(1 for r in registros if r["_alertas"])

    tarjetas = []
    for i, r in enumerate(registros, 1):
        alertas = "".join(f'<li>{a}</li>' for a in r["_alertas"])
        alertas = f'<ul class="alertas">{alertas}</ul>' if alertas else ""
        campos = "".join(
            f'<tr><th>{c}</th><td>{esc(r.get(c))}'
            f'{f"<span class=nota>{n}</span>" if n else ""}</td></tr>'
            for c, n in CAMPOS
        )
        tarjetas.append(f"""
        <article class="ficha{' con-alerta' if r['_alertas'] else ''}">
          <div class="col-foto">
            <span class="num">{i:02d}</span>
            <img src="{miniatura(r['foto'])}" alt="{esc(r['nombre'])}">
            <p class="ref">{r['ref']} · pág. {r['_pdf']['pagina']} del PDF</p>
            <p class="ref">{r['foto']}</p>
          </div>
          <div class="col-datos">
            <h2>{esc(r['nombre'])}</h2>
            {alertas}
            <table class="campos">{campos}</table>
            <details><summary>Fila original del PDF</summary>
              <table class="crudo">{''.join(
                  f'<tr><th>{k}</th><td>{esc(v)}</td></tr>'
                  for k, v in r['_pdf'].items() if k not in ('foto', 'carac_cortada'))}</table>
            </details>
          </div>
        </article>""")

    filas_desc = "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in sorted(descartadas.items(), key=lambda kv: -kv[1])
    )

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RoyiPets → mascotas encontradas · revisión previa</title>
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
          padding:10px 16px; min-width:130px; }}
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
  .ficha {{ display:grid; grid-template-columns:200px 1fr; gap:26px; background:#fff;
            border:1px solid var(--linea); border-radius:12px; padding:20px;
            margin-bottom:18px; }}
  .ficha.con-alerta {{ border-color:#e8c9a4; }}
  .col-foto {{ position:relative; }}
  .col-foto img {{ width:100%; border-radius:8px; display:block; background:#eee; }}
  .num {{ position:absolute; top:6px; left:6px; background:rgba(0,0,0,.62); color:#fff;
          border-radius:6px; padding:2px 8px; font-size:12px; font-weight:600; }}
  .ref {{ color:var(--suave); font-size:12px; margin:6px 0 0; font-family:ui-monospace,monospace; }}
  h2 {{ margin:0 0 12px; font-size:19px; }}
  .alertas {{ background:var(--alerta-bg); border:1px solid #f0d7b8; border-radius:8px;
              margin:0 0 14px; padding:10px 10px 10px 28px; color:var(--alerta);
              font-size:13.5px; }}
  .alertas li {{ margin:3px 0; }}
  table.campos {{ border-collapse:collapse; width:100%; font-size:14px; }}
  table.campos th {{ text-align:left; font-weight:600; color:var(--suave); width:170px;
                     vertical-align:top; padding:5px 12px 5px 0; font-family:ui-monospace,monospace;
                     font-size:12.5px; }}
  table.campos td {{ padding:5px 0; border-bottom:1px solid #f0f4f2; }}
  .nulo {{ color:#b9c5c0; font-style:italic; }}
  .nota {{ color:var(--suave); font-size:12px; margin-left:8px; }}
  details {{ margin-top:14px; }}
  summary {{ cursor:pointer; color:var(--acento); font-size:13px; }}
  table.crudo {{ border-collapse:collapse; margin-top:10px; font-size:12.5px; width:100%; }}
  table.crudo th {{ text-align:left; color:var(--suave); font-weight:500; width:170px;
                    padding:3px 12px 3px 0; }}
  table.crudo td {{ padding:3px 0; }}
  @media (max-width:720px) {{ .ficha {{ grid-template-columns:1fr; }} }}
</style></head><body>
<header><div class="wrap">
  <h1>RoyiPets → mascotas encontradas</h1>
  <p class="sub">Revisión previa de la carga a <code>mascotasperdidascolombia.com</code>.
     Fuente: <code>REPORTE MASCOTAS - DATOS.pdf</code>. Nada se ha escrito en la base todavía.</p>
  <div class="kpis">
    <div class="kpi"><b>{len(registros)}</b><span>se cargarían</span></div>
    <div class="kpi"><b>{len(todas)}</b><span>filas en el PDF</span></div>
    <div class="kpi"><b>{len(todas) - len(registros)}</b><span>descartadas (no DISPONIBLE)</span></div>
    <div class="kpi"><b>{con_alerta}</b><span>con algo por revisar</span></div>
  </div>
</div></header>
<main><div class="wrap">
  <div class="aviso">
    <h3>Cómo se llenó cada campo</h3>
    <ul>
      <li><b>nombre</b>: el del PDF + <code>(temporal)</code>, porque es un nombre provisional.</li>
      <li><b>ubicacion</b>: <code>{UBICACION}</code> para todas — es donde están hoy.</li>
      <li><b>contacto_telefono</b>: <code>{CONTACTO_TELEFONO}</code> ({CONTACTO_NOMBRE}) y, en las
          que están en hogar de paso, <b>también el teléfono de esa casa</b>, separados por
          <code>/</code>.</li>
      <li><b>barrio</b>: la columna «DONDE LO ENCONTRARON», que es lo que el cruce usa como zona.</li>
      <li><b>senas</b>: la columna «CARACTERISTICAS» completa.</li>
      <li><b>color / tamano / edad</b>: leídos de esa descripción; quedan en NULL si no la menciona.</li>
      <li><b>notas</b>: el contexto interno (estado en RoyiPets, hogar de paso, esterilización,
          lesiones). <b>Los teléfonos de terceros se borraron</b>: el único número de un
          reporte es el de contacto.</li>
      <li><b>tipo_registro</b> = <code>encontrada</code>, <b>estado</b> = <code>activo</code>,
          <b>source</b> = <code>{SOURCE}</code> (para poder deshacer el lote si hace falta).</li>
    </ul>
    <h3 style="margin-top:16px">Filas descartadas</h3>
    <table class="mini">{filas_desc}</table>
  </div>
  {''.join(tarjetas)}
</div></main></body></html>"""


def main() -> None:
    filas = extraer_filas()
    with open(os.path.join(BASE, "rows_raw.json"), "w", encoding="utf-8") as fh:
        json.dump(filas, fh, ensure_ascii=False, indent=1)

    disponibles = [f for f in filas if "DISPONIBLE" in (f.get("estado_adopcion") or "")]
    registros = [mapear(f) for f in disponibles]
    revisar(registros)

    with open(os.path.join(BASE, "registros.json"), "w", encoding="utf-8") as fh:
        json.dump(
            [{k: v for k, v in r.items() if k != "_pdf"} for r in registros],
            fh, ensure_ascii=False, indent=1,
        )
    with open(os.path.join(BASE, "revision.html"), "w", encoding="utf-8") as fh:
        fh.write(html(registros, filas))

    print(f"filas en el PDF: {len(filas)}")
    print(f"disponibles:     {len(registros)}")
    print(f"con alertas:     {sum(1 for r in registros if r['_alertas'])}")
    for r in registros:
        for a in r["_alertas"]:
            print(f"  {r['ref']:6} {r['nombre']:22} {re.sub('<[^>]+>', '', a)[:88]}")


if __name__ == "__main__":
    main()
