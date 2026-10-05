#!/usr/bin/env python3
"""Construye los carruseles de un mes a partir de sus guiones.

Uso:
    python3 content_machine_gloma/carruseles/construir.py content_machine_gloma/guiones/2026-10.md
    python3 content_machine_gloma/carruseles/construir.py <guion.md> --solo D1-A1   # uno solo
    python3 content_machine_gloma/carruseles/construir.py <guion.md> --sin-render   # solo HTML

Qué hace, por carrusel (carpeta AAAA-MM-DD_<ficha>):
  slide-01.html   portada: titular en Syne 800 y fondo vacío (PNG transparente); la imagen se
                  monta aparte. Si la imagen ya está en imagenes/, además arma
                  slide-01-con-imagen.html/.png con la imagen detrás.
  slide-02..05    cuerpo con el generador de las piezas (_generador/base.py) en modo sólido:
                  2 y 4 en Deep Forest, 3 y 5 en Soft Mint; un ícono de línea elegido por el
                  VISUAL del guion; si la slide trae una cifra, la cifra es el protagonista.
  slide-06        cierre con diseño fijo (línea mint, titular, cuerpo y CTA en píldora mint).
  index.html      las 6 slides juntas para revisarlas en pantalla.
Después renderiza los PNG con post-redes/render.sh y corre validar.py.
Se saltan los guiones con FALTA (sin material).
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

GEN = Path("/Users/equipo/Documents/gloma_software/identidad_gloma/redes sociales/_generador")
sys.path.insert(0, str(GEN))
import base  # noqa: E402  (generador de las piezas)

CM = Path(__file__).resolve().parents[1]
CARR = CM / "carruseles"
IMG = CM / "imagenes"
RENDER = Path.home() / ".claude/skills/post-redes/scripts/render.sh"
VALIDAR = CARR / "validar.py"
SIMB = base.SIMB
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8,
         "sep": 9, "oct": 10, "nov": 11, "dic": 12}

FOREST, BLACK, SOFT, MINT, WHITE = "#004D40", "#101817", "#E0F2F1", "#4DB6AC", "#FFFFFF"

# ------------------------------------------------------------------ íconos de línea (SVG)
# Trazo uniforme y bordes redondeados (Brand Book 4.4). Sin texto ni números.


def _i(c, cuerpo):
    return (f"<svg viewBox='0 0 120 120' fill='none' stroke='{c}' stroke-width='7' "
            f"stroke-linecap='round' stroke-linejoin='round'>{cuerpo}</svg>")


ICONOS = {
    "chat": lambda c: _i(c, "<rect x='12' y='20' width='96' height='64' rx='20'/><path d='M32 84 L22 104 L50 84'/>"
                            f"<circle cx='40' cy='52' r='4' fill='{c}'/><circle cx='60' cy='52' r='4' fill='{c}'/><circle cx='80' cy='52' r='4' fill='{c}'/>"),
    "celular": lambda c: _i(c, "<rect x='34' y='8' width='52' height='104' rx='12'/><path d='M52 20 H68'/><path d='M54 98 H66'/>"),
    "persona": lambda c: _i(c, "<circle cx='60' cy='40' r='20'/><path d='M22 108 C22 80 40 68 60 68 C80 68 98 80 98 108'/>"),
    "lista": lambda c: _i(c, "<rect x='16' y='10' width='88' height='100' rx='14'/><path d='M32 38 l6 6 l10 -12'/><path d='M58 38 H88'/>"
                             "<path d='M32 64 l6 6 l10 -12'/><path d='M58 64 H88'/><rect x='32' y='84' width='14' height='12' rx='3'/><path d='M58 90 H88'/>"),
    "flecha": lambda c: _i(c, "<path d='M16 60 H100'/><path d='M74 34 L100 60 L74 86'/>"),
    "flecha_abajo": lambda c: _i(c, "<path d='M60 14 V100'/><path d='M34 74 L60 100 L86 74'/>"),
    "ciclo": lambda c: _i(c, "<path d='M96 60 A36 36 0 1 1 84 33'/><path d='M86 12 V34 H64'/>"),
    "reloj": lambda c: _i(c, "<circle cx='60' cy='60' r='46'/><path d='M60 32 V60 L80 72'/>"),
    "reloj_arena": lambda c: _i(c, "<path d='M30 12 H90'/><path d='M30 108 H90'/><path d='M36 12 C36 44 84 44 84 60 C84 76 36 76 36 108'/>"
                                   "<path d='M84 12 C84 44 36 44 36 60 C36 76 84 76 84 108'/>"),
    "maleta": lambda c: _i(c, "<rect x='14' y='38' width='92' height='66' rx='12'/><path d='M44 38 V26 Q44 18 52 18 H68 Q76 18 76 26 V38'/><path d='M14 66 H106'/>"),
    "calendario": lambda c: _i(c, "<rect x='12' y='20' width='96' height='88' rx='14'/><path d='M12 46 H108'/><path d='M38 10 V28'/><path d='M82 10 V28'/>"
                                  f"<circle cx='38' cy='68' r='4' fill='{c}'/><circle cx='60' cy='68' r='4' fill='{c}'/><circle cx='82' cy='68' r='4' fill='{c}'/>"
                                  f"<circle cx='38' cy='88' r='4' fill='{c}'/><circle cx='60' cy='88' r='4' fill='{c}'/>"),
    "balanza": lambda c: _i(c, "<path d='M60 14 V104'/><path d='M36 104 H84'/><path d='M18 32 H102'/><path d='M18 32 L6 66 H30 Z'/><path d='M102 32 L90 66 H114 Z'/>"),
    "embudo": lambda c: _i(c, "<path d='M10 18 H110 L72 64 V100 L48 110 V64 Z'/>"),
    "candado": lambda c: _i(c, "<rect x='22' y='52' width='76' height='58' rx='12'/><path d='M38 52 V38 A22 22 0 0 1 82 38 V52'/><path d='M60 74 V88'/>"),
    "entrega": lambda c: _i(c, "<circle cx='26' cy='60' r='16'/><circle cx='94' cy='60' r='16'/><path d='M46 50 H74'/><path d='M66 42 L74 50 L66 58'/>"
                               "<path d='M74 72 H46'/><path d='M54 64 L46 72 L54 80'/>"),
    "estrella": lambda c: _i(c, "<path d='M60 10 L74 42 L108 46 L82 68 L90 102 L60 84 L30 102 L38 68 L12 46 L46 42 Z'/>"),
    "carpeta": lambda c: _i(c, "<path d='M10 28 Q10 20 18 20 H48 L58 32 H102 Q110 32 110 40 V96 Q110 104 102 104 H18 Q10 104 10 96 Z'/><path d='M30 64 H90'/><path d='M30 82 H70'/>"),
    "silla": lambda c: _i(c, "<path d='M34 14 H86 V60 H34 Z'/><path d='M26 60 H94'/><path d='M60 60 V86'/><path d='M36 104 L60 86 L84 104'/>"),
    "bifurcacion": lambda c: _i(c, "<path d='M60 110 V64'/><path d='M60 64 L26 26'/><path d='M60 64 L94 26'/><path d='M26 44 V26 H44'/><path d='M94 44 V26 H76'/>"),
    "calculadora": lambda c: _i(c, "<rect x='24' y='8' width='72' height='104' rx='12'/><rect x='36' y='20' width='48' height='22' rx='4'/>"
                                   f"<circle cx='44' cy='60' r='4' fill='{c}'/><circle cx='60' cy='60' r='4' fill='{c}'/><circle cx='76' cy='60' r='4' fill='{c}'/>"
                                   f"<circle cx='44' cy='78' r='4' fill='{c}'/><circle cx='60' cy='78' r='4' fill='{c}'/><circle cx='76' cy='78' r='4' fill='{c}'/>"
                                   f"<circle cx='44' cy='96' r='4' fill='{c}'/><circle cx='60' cy='96' r='4' fill='{c}'/><circle cx='76' cy='96' r='4' fill='{c}'/>"),
    "botones": lambda c: _i(c, "<rect x='14' y='14' width='92' height='24' rx='12'/><rect x='14' y='48' width='92' height='24' rx='12'/><rect x='14' y='82' width='92' height='24' rx='12'/>"),
    "comillas": lambda c: (f"<svg viewBox='0 0 120 120' fill='{c}'><circle cx='36' cy='44' r='20'/><path d='M56 44 C56 74 40 88 18 92 L20 80 C32 76 40 68 40 56 Z'/>"
                           f"<circle cx='84' cy='44' r='20'/><path d='M104 44 C104 74 88 88 66 92 L68 80 C80 76 88 68 88 56 Z'/></svg>"),
    "lupa": lambda c: _i(c, "<circle cx='50' cy='50' r='34'/><path d='M76 76 L106 106'/>"),
    "grafica": lambda c: _i(c, "<path d='M14 12 V106 H110'/><path d='M28 88 L54 64 L72 76 L102 34'/><path d='M82 34 H102 V54'/>"),
    "hoja": lambda c: _i(c, "<rect x='10' y='18' width='100' height='84' rx='10'/><path d='M10 46 H110'/><path d='M10 74 H110'/><path d='M44 18 V102'/><path d='M78 18 V102'/>"),
    "columnas": lambda c: _i(c, "<rect x='10' y='16' width='100' height='88' rx='12'/><path d='M60 16 V104'/><path d='M22 38 H48'/><path d='M72 38 H98'/>"),
    "enlace": lambda c: _i(c, "<rect x='8' y='44' width='56' height='32' rx='16'/><rect x='56' y='44' width='56' height='32' rx='16'/>"),
    "planta": lambda c: _i(c, "<path d='M60 110 V50'/><path d='M60 78 C38 78 26 64 24 46 C44 46 58 58 60 78 Z'/><path d='M60 60 C82 60 94 46 96 28 C76 28 62 40 60 60 Z'/>"),
    "tres_puntos": lambda c: (f"<svg viewBox='0 0 120 120' fill='{c}'><circle cx='28' cy='60' r='12'/><circle cx='60' cy='60' r='12'/><circle cx='92' cy='60' r='12'/></svg>"),
}

# Palabra del VISUAL -> ícono. El primero que coincide gana: de lo específico a lo general.
MAPA = [
    ("reloj de arena", "reloj_arena"), ("hoja de cálculo", "hoja"), ("calculadora", "calculadora"),
    ("dos columnas", "columnas"), ("columnas", "columnas"), ("tabla", "columnas"),
    ("balanza", "balanza"), ("embudo", "embudo"), ("candado", "candado"), ("lupa", "lupa"),
    ("gráfica", "grafica"), ("estrella", "estrella"), ("reseña", "estrella"),
    ("carpeta", "carpeta"), ("documento", "carpeta"), ("tarifario", "carpeta"),
    ("silla", "silla"), ("bifurcación", "bifurcacion"), ("caminos", "bifurcacion"),
    ("flechas", "bifurcacion"), ("botones", "botones"), ("botón", "botones"), ("menú", "botones"),
    ("laberinto", "botones"), ("comillas", "comillas"), ("maleta", "maleta"), ("etiqueta", "maleta"),
    ("vitrina", "maleta"), ("calendario", "calendario"), ("agenda", "calendario"),
    ("reloj", "reloj"), ("cabeza", "persona"), ("silueta", "persona"), ("personaje", "persona"),
    ("mano", "entrega"), ("lista", "lista"), ("casillas", "lista"), ("plantilla", "lista"),
    ("libreta", "lista"), ("planta", "planta"), ("cable", "enlace"), ("unidos", "enlace"),
    ("flecha circular", "ciclo"), ("flecha mint hacia abajo", "flecha_abajo"),
    ("hacia abajo", "flecha_abajo"), ("flecha", "flecha"), ("puntos suspensivos", "tres_puntos"),
    ("celular", "celular"), ("pantalla", "celular"), ("burbuja", "chat"), ("chat", "chat"),
    ("pregunta", "chat"), ("interrogación", "chat"),
]


def icono(visual: str, color: str) -> str:
    """El ícono del objeto que el VISUAL nombra primero (el protagonista de la frase)."""
    v = visual.lower()
    hallados = [(v.find(clave), -len(clave), nombre) for clave, nombre in MAPA if clave in v]
    nombre = min(hallados)[2] if hallados else "chat"
    return ICONOS[nombre](color)


# ------------------------------------------------------------------ lectura del guion


def leer(guion: Path) -> list[dict]:
    carruseles, cur = [], None
    for linea in guion.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## \w+ (\d{1,2})-(\w{3}) · (.+)$", linea)
        if m:
            anio = re.search(r"(\d{4})-(\d{2})", guion.stem)
            ficha = re.sub(r"[^\w\- ]", "", m.group(3)).strip()
            cur = {"fecha": f"{anio.group(1)}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}",
                   "ficha": ficha, "carpeta_ficha": ficha.replace(" ", ""), "slides": {}}
            carruseles.append(cur)
            continue
        m = re.match(r"^\| (\d) \| ([^|]+) \| (.+?) \| (.+?) \|$", linea)
        if m and cur is not None:
            cur["slides"][int(m.group(1))] = {"rol": m.group(2).strip(), "texto": m.group(3).strip(),
                                              "visual": m.group(4).strip()}
    return carruseles


def partir(texto: str) -> dict:
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", texto)
    titulo, resto = (m.group(1), m.group(2)) if m else ("", texto)
    cta = fuente = None
    if "CTA: " in resto:
        resto, cta = resto.split("CTA: ", 1)
    if "Fuente:" in resto:
        resto, f = resto.split("Fuente:", 1)
        fuente = "Fuente:" + f
    return {"lineas": [x.strip() for x in titulo.split(" / ") if x.strip()],
            "cuerpo": resto.strip(), "cta": cta.strip() if cta else None,
            "fuente": fuente.strip() if fuente else None}


def fmt(t: str) -> str:
    t = html.escape(t, quote=False)
    return t.replace("“", "<span class='q'>“</span>").replace("”", "<span class='q'>”</span>")


def tam_titulo(lineas: list[str], base_px=(88, 76, 64, 56)) -> int:
    n = max((len(x) for x in lineas), default=0)
    size = base_px[0] if n <= 18 else base_px[1] if n <= 26 else base_px[2] if n <= 34 else base_px[3]
    # Syne 800 es ancha (~0,8 em por letra): una palabra larga no puede pasarse de los 900 px útiles.
    palabra = max((len(w) for x in lineas for w in x.split()), default=1)
    return min(size, int(900 / (0.92 * palabra)))


def tipos_portada() -> dict:
    """Tipo de portada (cara / forma / no lleva) desde el registro de imágenes."""
    tipos = {}
    reg = IMG / "registro.md"
    if reg.exists():
        for m in re.finditer(r"^\| (\d{4}-\d{2}-\d{2}) \| ([^|]+?) \| (cara|forma|no lleva) \|",
                             reg.read_text(encoding="utf-8"), re.M):
            tipos[f"{m.group(1)}_{m.group(2).replace(' ', '')}"] = m.group(3)
    return tipos


# ------------------------------------------------------------------ slides


def portada(s: dict, color: str, fondo_css: str, con_imagen: bool = False) -> str:
    p = partir(s["texto"])
    # Con imagen detrás, el bloque de texto tiene que caber en la franja libre de arriba.
    size = tam_titulo(p["lineas"], (84, 72, 62, 54) if con_imagen else (96, 84, 72, 62))
    sub = f"<div class='sub'>{fmt(p['cuerpo'])}</div>" if p["cuerpo"] else ""
    q = MINT if color == WHITE else FOREST
    # El símbolo es blanco: sobre fondo claro se oscurece a Deep Forest (mismo filtro que base.py).
    logofx = ("filter:brightness(0) saturate(100%) invert(19%) sepia(35%) saturate(2000%) "
              "hue-rotate(140deg);") if color == FOREST else ""
    return f"""<!doctype html><meta charset='utf-8'><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;position:relative;overflow:hidden;{fondo_css}
  font-family:Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased;color:{color}}}
.wrap{{position:absolute;inset:0;padding:{base.PAD}px {base.PAD}px {base.PAD + base.BANDA}px {base.PAD}px}}
h1{{font-family:Syne;font-weight:800;letter-spacing:-.02em;line-height:1.06;text-wrap:balance;font-size:{size}px}}
.sub{{font:400 {30 if con_imagen else 34}px/1.4 Inter;margin-top:26px;max-width:88%;text-wrap:pretty}}
.q{{color:{q}}}
.pag{{position:absolute;left:{base.PAD}px;bottom:{base.PAD}px;font:500 26px Inter;letter-spacing:.14em}}
.logo{{position:absolute;right:{base.PAD}px;bottom:{base.PAD}px;width:78px;height:auto;{logofx}}}
</style>
<div class='wrap'><h1>{'<br>'.join(fmt(x) for x in p['lineas'])}</h1>{sub}</div>
<div class='pag'>01/06</div><img class='logo' src='file://{SIMB}'>"""


# ------------------------------------------------------------------ portadas de meme
# El CEO trajo las imágenes de los memes (2026-09-29). Van completas, sin recorte ni capa
# verde (romperían el chiste), sobre Deep Forest, con el titular arriba. Los textos van en
# HTML encima de la imagen: nunca se escribe texto nuevo dentro de la imagen.
# MM1: "funcoinando" corregido a "funcionando" por pedido del CEO (2026-09-29), solo en esta pieza;
# en voz-del-cliente la cita sigue textual.
MEMES = {
    "MM1": {"img": "2026-10-17_MM1_portada.png", "tipo": "columna",
            "titulo": ["Expectativa", "vs. realidad"],
            "textos": ["“me gustaria abrir nuevos canales sin descuidar el que ya tengo de whatsapp funcionando”",
                       "“si no estoy yo no funciona el negocio”"]},
    "MM2": {"img": "2026-10-20_MM2_portada.png", "tipo": "salida",
            "titulo": ["El dilema", "de todos los meses"],
            "textos": ["“un sueldo para alguien”", "que lo repetido lo conteste un agente", "tú"]},
    "MM3": {"img": "2026-10-24_MM3_portada.png", "tipo": "drake",
            "titulo": ["“A cuanto", "podriamos aspirar?”"],
            "textos": ["Un porcentaje prometido", "Subir la tasa que ya tienes"]},
}
CAJA_W, CAJA_TOP = 900, 300                      # zona del meme: bajo el titular, sobre la banda
CAJA_H = 1350 - base.PAD - base.BANDA - CAJA_TOP  # 864 px


def _tam(ruta: Path) -> tuple[int, int]:
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(ruta)],
                         capture_output=True, text=True).stdout
    w = int(re.search(r"pixelWidth: (\d+)", out).group(1))
    h = int(re.search(r"pixelHeight: (\d+)", out).group(1))
    return w, h


def portada_meme(m: dict) -> str:
    ruta = IMG / m["img"]
    w0, h0 = _tam(ruta)
    t = m["textos"]
    if m["tipo"] == "columna":                   # dos paneles apilados: citas a la izquierda
        h = CAJA_H
        w = round(h * w0 / h0)
        x, y = CAJA_W - w, 0
        col = CAJA_W - w - 30
        extra = (f"<div class='lbl' style='left:0;top:20px;width:{col}px'>{fmt(t[0])}</div>"
                 f"<div class='lbl' style='left:0;top:{h // 2 + 20}px;width:{col}px'>{fmt(t[1])}</div>")
    elif m["tipo"] == "salida":                  # Left Exit 12: rótulos sobre el letrero y el carro
        w = CAJA_W
        h = round(w * h0 / w0)
        x, y = 0, 0
        s = w / w0
        extra = (f"<div class='lbl sign' style='left:{round(172*s)}px;top:{round(84*s)}px;width:{round(112*s)}px'>{fmt(t[0])}</div>"
                 f"<div class='lbl sign' style='left:{round(378*s)}px;top:{round(84*s)}px;width:{round(160*s)}px'>{fmt(t[1])}</div>"
                 f"<div class='lbl yo' style='left:{round(360*s)}px;top:{round(418*s)}px'>{fmt(t[2])}</div>")
    else:                                        # Drake: textos en la columna blanca de la derecha
        h = w = CAJA_H
        x, y = (CAJA_W - w) // 2, 0
        mitad = w // 2
        extra = (f"<div class='lbl dk' style='left:{x + mitad}px;top:0;width:{mitad}px;height:{mitad}px'>{fmt(t[0])}</div>"
                 f"<div class='lbl dk' style='left:{x + mitad}px;top:{mitad}px;width:{mitad}px;height:{mitad}px'>{fmt(t[1])}</div>")
    return f"""<!doctype html><meta charset='utf-8'><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1080px;height:1350px;position:relative;overflow:hidden;background:{FOREST};
  font-family:Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased;color:{WHITE}}}
h1{{position:absolute;left:{base.PAD}px;top:{base.PAD}px;right:{base.PAD}px;font-family:Syne;font-weight:800;
  letter-spacing:-.02em;line-height:1.06;white-space:nowrap;
  font-size:{min(72, int(900 / (0.85 * max(len(x) for x in m['titulo']))))}px}}
.q{{color:{MINT}}}
.caja{{position:absolute;left:{base.PAD}px;top:{CAJA_TOP}px;width:{CAJA_W}px;height:{CAJA_H}px}}
.meme{{position:absolute;display:block;border-radius:24px}}
.lbl{{position:absolute;font:400 30px/1.35 Inter;color:{WHITE}}}
.sign{{font:700 22px/1.2 Inter;text-align:center}}
.yo{{font:800 46px Syne}}
.dk{{display:flex;align-items:center;justify-content:center;text-align:center;padding:24px;
  font:700 40px/1.15 Syne;color:{BLACK}}}
.dk .q{{color:{FOREST}}}
.pag{{position:absolute;left:{base.PAD}px;bottom:{base.PAD}px;font:500 26px Inter;letter-spacing:.14em}}
.logo{{position:absolute;right:{base.PAD}px;bottom:{base.PAD}px;width:78px;height:auto}}
</style>
<h1>{'<br>'.join(fmt(x) for x in m['titulo'])}</h1>
<div class='caja'><img class='meme' src='file://{ruta}' style='left:{x}px;top:{y}px;width:{w}px;height:{h}px'>{extra}</div>
<div class='pag'>01/06</div><img class='logo' src='file://{SIMB}'>"""


def cuerpo_slide(n: int, s: dict) -> str:
    tema = "forest" if n in (2, 4) else "mint"
    oscuro = tema == "forest"
    acento = MINT if oscuro else FOREST
    txt = WHITE if oscuro else BLACK
    p = partir(s["texto"])
    cifra = re.search(r"(\d[\d.]*)\s*horas", p["cuerpo"])
    # Con cifra, la cifra es lo principal (arriba y grande). Sin cifra, el ícono del VISUAL
    # va grande abajo a la derecha como elemento decorativo que capta la atención.
    arriba = f"<div class='cifra'>{cifra.group(1)} h</div>" if cifra else ""
    deco = "" if cifra else f"<div class='ico'>{icono(s['visual'], acento)}</div>"
    fuente = f"<div class='fuente'>{fmt(p['fuente'])}</div>" if p["fuente"] else ""
    size = tam_titulo(p["lineas"])
    cuerpo = (f"{arriba}<h2 class='tit' style='font-size:{size}px'>"
              f"{'<br>'.join(fmt(x) for x in p['lineas'])}</h2>"
              f"<div class='txt'>{fmt(p['cuerpo'])}</div>{fuente}{deco}")
    css = f"""
.ico{{position:absolute;right:{base.PAD}px;bottom:{base.PAD + base.BANDA + 10}px}}
.ico svg{{width:290px;height:290px;display:block}}
.cifra{{font-family:Syne;font-weight:800;font-size:230px;line-height:.9;letter-spacing:-.03em;color:{acento};margin-bottom:40px}}
.tit{{margin-top:0}}
.txt{{font:400 42px/1.42 Inter;margin-top:36px;color:{txt};text-wrap:pretty;max-width:96%}}
.fuente{{font:400 24px/1.3 Inter;margin-top:30px;color:{txt}}}
.q{{color:{acento}}}
"""
    return base.pagina(tema, cuerpo, extra_css=css, pag=f"0{n}/06", solido=True)


def cierre(s: dict) -> str:
    p = partir(s["texto"])
    size = tam_titulo(p["lineas"], (84, 74, 64, 56))
    cta = base.cta_boton(fmt(p["cta"]), centrado=False) if p["cta"] else ""
    cuerpo = (f"<div class='linea'></div><h1 style='font-size:{size}px;margin-top:48px'>"
              f"{'<br>'.join(fmt(x) for x in p['lineas'])}</h1>"
              f"<div class='txt'>{fmt(p['cuerpo'])}</div>{cta}")
    css = f"""
.linea{{width:64px;height:6px;border-radius:3px;background:{MINT}}}
.txt{{font:400 42px/1.42 Inter;margin-top:36px;color:{WHITE};text-wrap:pretty}}
.q{{color:{MINT}}}
"""
    return base.pagina("forest", cuerpo, extra_css=css, pag="06/06", solido=True)


def indice(c: dict, dest: Path, tipo: str, con_imagen: bool) -> str:
    uno = "slide-01-con-imagen.png" if con_imagen else "slide-01.png"
    fondo1 = "" if con_imagen else ("background:repeating-conic-gradient(#ccc 0 25%,#eee 0 50%) 0 0/40px 40px;")
    imgs = [f"<figure><img src='{uno}' style='{fondo1}'><figcaption>01 · portada</figcaption></figure>"]
    imgs += [f"<figure><img src='slide-0{i}.png'><figcaption>0{i}</figcaption></figure>" for i in range(2, 7)]
    estado = ("portada con imagen" if con_imagen else
              "portada SIN imagen todavía (ver imagenes/registro.md)" if tipo != "no lleva" else
              "portada tipográfica (no lleva imagen)")
    return f"""<!doctype html><meta charset='utf-8'><title>{c['fecha']} · {c['ficha']}</title>
<style>body{{margin:0;padding:24px;background:#1b1f1e;color:#eee;font:15px Inter,sans-serif}}
.g{{display:grid;grid-template-columns:repeat(3,360px);gap:18px}}figure{{margin:0}}
img{{width:360px;height:450px;display:block;border-radius:6px}}figcaption{{margin-top:6px;opacity:.7}}</style>
<h2 style='font-family:Syne'>{c['fecha']} · {c['ficha']}</h2><p>{estado}</p><div class='g'>{''.join(imgs)}</div>"""


def render(html_path: Path) -> None:
    """Chrome headless a veces se cuelga: límite de 60 s por slide y un reintento."""
    cmd = [str(RENDER), "--html", str(html_path), "--out", str(html_path.with_suffix("")),
           "--width", "1080", "--height", "1350", "--scale", "2", "--format", "png"]
    for intento in (1, 2):
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, timeout=60)
            return
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-f", f"file://{html_path}"], check=False)
            if intento == 2:
                raise RuntimeError(f"Chrome no terminó de renderizar {html_path.name} (2 intentos)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("guion")
    ap.add_argument("--solo", help="ficha a construir (p. ej. D1-A1)")
    ap.add_argument("--sin-render", action="store_true")
    a = ap.parse_args()

    tipos = tipos_portada()
    hechos, saltados, resumen = [], [], []
    for c in leer(Path(a.guion)):
        if a.solo and c["ficha"] != a.solo and c["carpeta_ficha"] != a.solo:
            continue
        sl = c["slides"]
        if len(sl) != 6 or any(v["texto"].startswith("FALTA") for v in sl.values()):
            saltados.append(f"{c['fecha']} {c['ficha']} (guion incompleto: FALTA material)")
            continue
        nombre = f"{c['fecha']}_{c['carpeta_ficha']}"
        dest = CARR / nombre
        dest.mkdir(parents=True, exist_ok=True)
        tipo = tipos.get(nombre, "cara")
        imagen = next(iter(sorted(IMG.glob(f"{nombre}_portada.*"))), None)

        meme = MEMES.get(c["carpeta_ficha"])
        es_meme = bool(meme and (IMG / meme["img"]).exists())
        if es_meme:                         # portada de meme: la composición ya es la pieza final
            html_meme = portada_meme(meme)
            (dest / "slide-01.html").write_text(html_meme, encoding="utf-8")
            (dest / "slide-01-con-imagen.html").write_text(html_meme, encoding="utf-8")
        elif tipo == "no lleva":            # portada tipográfica: Soft Mint sólido, titular Deep Forest
            (dest / "slide-01.html").write_text(portada(sl[1], FOREST, f"background:{SOFT};"), encoding="utf-8")
        else:                               # fondo vacío; titular blanco (forma = fondo Deep Forest)
            (dest / "slide-01.html").write_text(portada(sl[1], WHITE, "background:transparent;"), encoding="utf-8")
        if imagen and not es_meme:
            (dest / "slide-01-con-imagen.html").write_text(
                # La ilustración tiene el mismo fondo #004D40 que la slide: se reduce y se ancla
                # abajo sin que se note el borde, y el titular queda con aire arriba.
                # Foto (cara): va a sangre completa; ya trae recortado el 3:4 y la capa Deep Forest.
                portada(sl[1], WHITE, f"background:{FOREST} url('file://{imagen}') center center/cover no-repeat;")
                if tipo == "cara" else
                portada(sl[1], WHITE, f"background:{FOREST} url('file://{imagen}') center bottom/74% auto no-repeat;",
                        con_imagen=True),
                encoding="utf-8")
        for n in (2, 3, 4, 5):
            (dest / f"slide-0{n}.html").write_text(cuerpo_slide(n, sl[n]), encoding="utf-8")
        (dest / "slide-06.html").write_text(cierre(sl[6]), encoding="utf-8")
        (dest / "index.html").write_text(indice(c, dest, tipo, bool(imagen)), encoding="utf-8")

        if not a.sin_render:
            for h in sorted(dest.glob("slide-*.html")):
                render(h)
        v = subprocess.run([sys.executable, str(VALIDAR), str(dest)], capture_output=True, text=True)
        resumen.append((nombre, v.returncode, v.stdout))
        hechos.append(nombre)

    # índice general: todas las carpetas con index.html (incluye las piezas antiguas enlazadas)
    malos = {n for n, rc, _ in resumen if rc != 0}
    todas = sorted(d.name for d in CARR.iterdir() if d.is_dir() and (d / "index.html").exists())
    filas = "".join(f"<li><a href='{n}/index.html'>{n}</a>{' — <b>revisar validación</b>' if n in malos else ''}</li>"
                    for n in todas)
    if True:
        (CARR / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>Carruseles</title>"
            "<body style='font:16px Inter,sans-serif;padding:24px'><h1 style='font-family:Syne'>Carruseles</h1>"
            f"<ul>{filas}</ul></body>", encoding="utf-8")
    for n, rc, out in resumen:
        print(out.strip())
    print(f"\nConstruidos: {len(hechos)} · saltados: {len(saltados)}")
    for s in saltados:
        print("  saltado:", s)
    return 0 if all(rc == 0 for _, rc, _ in resumen) else 1


if __name__ == "__main__":
    sys.exit(main())
