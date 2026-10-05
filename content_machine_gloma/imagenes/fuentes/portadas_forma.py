# -*- coding: utf-8 -*-
"""Portadas de tipo "forma": ilustración vectorial plana, 3:4, sin sombras ni degradados.

Solo dos colores, copiados del design system (identidad_gloma/design_system_gloma.md):
fondo Deep Forest #004D40 y relleno Algorithmic Mint #4DB6AC. Sin texto dentro de la imagen.
El tercio superior queda libre para el titular del carrusel (va en HTML).
Uso: python3 portadas_forma.py  -> escribe los .svg y un .html por portada en esta carpeta.
"""
from pathlib import Path

BG, M = "#004D40", "#4DB6AC"
W, H = 1080, 1440
AQUI = Path(__file__).resolve().parent


def svg(cuerpo: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<rect width="{W}" height="{H}" fill="{BG}"/>'
            f'<g stroke-linecap="round" stroke-linejoin="round">{cuerpo}</g></svg>')


def comilla(cx, cy, r):
    """Comilla geométrica: círculo lleno + cola curva hacia abajo a la izquierda."""
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{M}"/>'
            f'<path d="M {cx + r} {cy} C {cx + r} {cy + 1.9*r} {cx} {cy + 2.6*r} {cx - 1.1*r} {cy + 2.7*r} '
            f'L {cx - 0.9*r} {cy + 2.1*r} C {cx - 0.1*r} {cy + 1.9*r} {cx + 0.35*r} {cy + 1.3*r} {cx + 0.2*r} {cy + 0.6*r} Z" fill="{M}"/>')


def celular(x, y, w=300, h=560, sw=14):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="48" fill="none" stroke="{M}" stroke-width="{sw}"/>'
            f'<line x1="{x + w/2 - 40}" y1="{y + 38}" x2="{x + w/2 + 40}" y2="{y + 38}" stroke="{M}" stroke-width="{sw}"/>')


def burbuja(x, y, w, h, lleno=True, cola="izq", sw=14, extra=""):
    fill = M if lleno else "none"
    stroke = "none" if lleno else M
    if cola == "izq":
        t = f'M {x + 40} {y + h - 10} L {x - 10} {y + h + 50} L {x + 110} {y + h - 10} Z'
    else:
        t = f'M {x + w - 40} {y + h - 10} L {x + w + 10} {y + h + 50} L {x + w - 110} {y + h - 10} Z'
    return (f'<path d="{t}" fill="{M}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{min(h/2, 60)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def puntos(cx, cy, color, r=18, sep=58):
    return "".join(f'<circle cx="{cx + (i-1)*sep}" cy="{cy}" r="{r}" fill="{color}"/>' for i in range(3))


def maleta(x, y, color):
    return (f'<rect x="{x}" y="{y}" width="100" height="80" rx="14" fill="{color}"/>'
            f'<path d="M {x + 32} {y} V {y - 18} Q {x + 32} {y - 28} {x + 42} {y - 28} H {x + 58} '
            f'Q {x + 68} {y - 28} {x + 68} {y - 18} V {y}" fill="none" stroke="{color}" stroke-width="10"/>')


def flecha(x1, y1, x2, y2, sw=12):
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    p1 = (x2 - 34*math.cos(a - 0.5), y2 - 34*math.sin(a - 0.5))
    p2 = (x2 - 34*math.cos(a + 0.5), y2 - 34*math.sin(a + 0.5))
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{M}" stroke-width="{sw}"/>'
            f'<polyline points="{p1[0]:.0f},{p1[1]:.0f} {x2},{y2} {p2[0]:.0f},{p2[1]:.0f}" fill="none" stroke="{M}" stroke-width="{sw}"/>')


P = {}

# 11-oct · D1-A1 — dos comillas geométricas, abajo a la derecha, con aire.
P["2026-10-11_D1-A1"] = comilla(560, 900, 120) + comilla(840, 900, 120)

# 13-oct · D4-A1 — un celular al que entran dos burbujas desde lados opuestos.
P["2026-10-13_D4-A1"] = (
    celular(390, 640)
    + burbuja(90, 700, 250, 170, True, "der") + maleta(165, 770, BG)
    + flecha(345, 830, 380, 830)
    + burbuja(740, 960, 250, 150, False, "izq") + puntos(865, 1035, M)
    + flecha(735, 1035, 700, 1035)
)

# 14-oct · D1-A4b — menú de tres botones vacíos y una burbuja que no cabe en ninguno.
P["2026-10-14_D1-A4b"] = (
    "".join(f'<rect x="250" y="{y}" width="480" height="104" rx="52" fill="none" stroke="{M}" stroke-width="14"/>'
            for y in (900, 1040, 1180))
    + f'<g transform="rotate(-8 740 700)">{burbuja(560, 590, 380, 230, True, "izq")}{puntos(750, 705, BG, 22, 70)}</g>'
)

# 15-oct · D3-A1 — columna de chats en mint y uno, solo contorno, que se va hundiendo.
P["2026-10-15_D3-A1"] = (
    "".join(f'<rect x="340" y="{y}" width="400" height="100" rx="30" fill="{M}"/>' for y in (560, 690, 820, 950))
    + f'<rect x="340" y="1150" width="400" height="100" rx="30" fill="none" stroke="{M}" stroke-width="12" stroke-dasharray="28 22"/>'
    + f'<line x1="540" y1="1080" x2="540" y2="1128" stroke="{M}" stroke-width="12" stroke-dasharray="2 22"/>'
    + flecha(820, 1120, 820, 1300)
)

# 19-oct · D3-A4 — un celular quieto con reloj de arena y otro que envía una burbuja con documento.
P["2026-10-19_D3-A4"] = (
    celular(170, 700)
    + f'<path d="M 260 860 H 380 L 320 960 L 380 1060 H 260 L 320 960 Z" fill="none" stroke="{M}" stroke-width="14"/>'
    + f'<path d="M 290 1040 H 350 L 320 1000 Z" fill="{M}"/>'
    + celular(610, 700)
    + burbuja(700, 560, 260, 170, True, "izq")
    + f'<path d="M 800 590 H 850 L 875 615 V 700 H 800 Z" fill="{BG}"/>'
    + "".join(f'<line x1="{x}" y1="{y}" x2="{x + 40}" y2="{y - 40}" stroke="{M}" stroke-width="12"/>'
              for x, y in ((600, 640), (635, 675)))
)

# 21-oct · D4-A4 — dos comillas sobre una etiqueta de equipaje con visto bueno.
P["2026-10-21_D4-A4"] = (
    f'<g transform="rotate(8 560 1000)">'
    f'<path d="M 420 740 L 490 670 H 630 L 700 740 V 1290 Q 700 1330 660 1330 H 460 Q 420 1330 420 1290 Z" fill="{M}"/>'
    f'<circle cx="560" cy="740" r="30" fill="{BG}"/>'
    f'<polyline points="470,1060 540,1140 660,980" fill="none" stroke="{BG}" stroke-width="34"/>'
    f'</g>'
    + f'<path d="M 575 710 C 600 600 700 560 760 590" fill="none" stroke="{M}" stroke-width="10"/>'
    + comilla(250, 640, 70) + comilla(410, 640, 70)
)

# 22-oct · D2-A5 — burbuja de contorno punteado unida a una carpeta de documentos.
P["2026-10-22_D2-A5"] = (
    f'<path d="M 250 930 L 210 1000 L 330 930 Z" fill="{M}"/>'
    f'<rect x="170" y="600" width="520" height="330" rx="80" fill="none" stroke="{M}" stroke-width="14" stroke-dasharray="40 28"/>'
    + puntos(430, 765, M, 22, 72)
    + f'<path d="M 690 800 C 800 820 820 900 800 980" fill="none" stroke="{M}" stroke-width="12"/>'
    + f'<path d="M 560 1000 H 690 L 730 1050 H 920 Q 940 1050 940 1070 V 1300 Q 940 1320 920 1320 H 580 Q 560 1320 560 1300 Z" fill="{M}"/>'
    + f'<line x1="620" y1="1150" x2="880" y2="1150" stroke="{BG}" stroke-width="16"/>'
    + f'<line x1="620" y1="1220" x2="800" y2="1220" stroke="{BG}" stroke-width="16"/>'
)

# 23-oct · EA3 — reloj de línea con una planta que crece desde el centro.
import math
_ticks = "".join(
    f'<line x1="{540 + 250*math.cos(a):.0f}" y1="{980 + 250*math.sin(a):.0f}" '
    f'x2="{540 + 285*math.cos(a):.0f}" y2="{980 + 285*math.sin(a):.0f}" stroke="{M}" stroke-width="14"/>'
    for a in [i*math.pi/6 for i in range(12)])
P["2026-10-23_EA3"] = (
    f'<circle cx="540" cy="980" r="320" fill="none" stroke="{M}" stroke-width="16"/>' + _ticks
    + f'<path d="M 540 1000 C 540 900 540 820 540 760" fill="none" stroke="{M}" stroke-width="16"/>'
    + f'<path d="M 540 880 C 470 880 420 830 410 760 C 480 760 530 800 540 880 Z" fill="{M}"/>'
    + f'<path d="M 540 820 C 610 820 660 770 670 700 C 600 700 550 740 540 820 Z" fill="{M}"/>'
    + f'<circle cx="540" cy="1000" r="26" fill="{M}"/>'
)

# 28-oct · MM4 — starter pack: hoja de cálculo, libreta de contactos, base de datos y tablero.
def celda(x, y):
    return f'<rect x="{x}" y="{y}" width="370" height="370" rx="40" fill="none" stroke="{M}" stroke-width="12"/>'
hoja = (celda(150, 560)
        + f'<rect x="220" y="640" width="230" height="210" rx="16" fill="{M}"/>'
        + "".join(f'<line x1="220" y1="{y}" x2="450" y2="{y}" stroke="{BG}" stroke-width="10"/>' for y in (710, 780))
        + "".join(f'<line x1="{x}" y1="640" x2="{x}" y2="850" stroke="{BG}" stroke-width="10"/>' for x in (297, 373)))
libreta = (celda(560, 560)
           + f'<rect x="650" y="630" width="190" height="240" rx="20" fill="{M}"/>'
           + f'<circle cx="745" cy="705" r="34" fill="{BG}"/>'
           + f'<path d="M 685 840 Q 685 760 745 760 Q 805 760 805 840 Z" fill="{BG}"/>'
           + "".join(f'<line x1="634" y1="{y}" x2="662" y2="{y}" stroke="{M}" stroke-width="12"/>' for y in (670, 750, 830)))
base = (celda(150, 970)
        + f'<ellipse cx="335" cy="1060" rx="110" ry="36" fill="{M}"/>'
        + f'<path d="M 225 1060 V 1230 Q 335 1290 445 1230 V 1060" fill="none" stroke="{M}" stroke-width="14"/>'
        + f'<path d="M 225 1120 Q 335 1170 445 1120" fill="none" stroke="{M}" stroke-width="12"/>'
        + f'<path d="M 225 1175 Q 335 1225 445 1175" fill="none" stroke="{M}" stroke-width="12"/>')
tablero = (celda(560, 970)
           + "".join(f'<rect x="{x}" y="{y}" width="80" height="{hh}" rx="12" fill="{M}"/>'
                     for x, y, hh in ((620, 1040, 60), (620, 1115, 60), (620, 1190, 60),
                                      (705, 1040, 60), (705, 1115, 60),
                                      (790, 1040, 60))))
P["2026-10-28_MM4"] = hoja + libreta + base + tablero

# 29-oct · EA1 — conversación detenida: el último mensaje, a medio escribir.
P["2026-10-29_EA1"] = (
    burbuja(140, 580, 420, 130, False, "izq", 12)
    + burbuja(520, 780, 420, 130, True, "der")
    + burbuja(140, 990, 520, 220, False, "izq", 12)
    + puntos(400, 1100, M, 26, 90)
)

for nombre, cuerpo in P.items():
    (AQUI / f"{nombre}_portada.svg").write_text(svg(cuerpo), encoding="utf-8")
    (AQUI / f"{nombre}_portada.html").write_text(
        f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:{BG}}}'
        f'img{{display:block;width:{W}px;height:{H}px}}</style></head>'
        f'<body><img src="{nombre}_portada.svg"></body></html>', encoding="utf-8")
print(len(P), "portadas escritas")
