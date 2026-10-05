#!/usr/bin/env python3
"""Lista de verificación de un carrusel antes de darlo por bueno.

Uso:  python3 content_machine_gloma/carruseles/validar.py content_machine_gloma/carruseles/<carpeta>

La carpeta tiene slide-01.html … slide-06.html (la 01 es la portada). La imagen de portada se
busca en content_machine_gloma/imagenes/ por el nombre de la carpeta (AAAA-MM-DD_<ficha>).

Las cinco preguntas:
  1. ¿Los slides de contenido se ven todos iguales entre sí?  (misma plantilla: deben serlo)
  2. ¿Las portadas se ven distintas entre ellas?                (deben diferenciarse)
  3. ¿Hay texto generado por IA dentro de alguna imagen?        (a ojo: lista qué revisar)
  4. ¿Los colores son los códigos exactos de marca?             (no parecidos)
  5. ¿Cada dato mostrado tiene su fuente visible en el slide?
Además revisa el tope de 40 palabras por slide. Sale con código 1 si algo falla.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

EXACTOS = {"#004D40", "#101817", "#E0F2F1", "#4DB6AC", "#FFFFFF"}
RAIZ_CM = Path(__file__).resolve().parents[1]          # content_machine_gloma/
IMAGENES = RAIZ_CM / "imagenes"


def visible(html: str) -> str:
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"</?span[^>]*>", "", html)             # las comillas en color no son palabras aparte
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\b\d{2}\s*/\s*\d{2}\b", " ", html)   # paginación 01/06
    return re.sub(r"\s+", " ", html).strip()


def css(html: str) -> str:
    bloques = "".join(re.findall(r"<style>(.*?)</style>", html, flags=re.S | re.I))
    return re.sub(r"#[0-9A-Fa-f]{6}\b", "#C", bloques)    # el color cambia por la alternancia


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    carpeta = Path(sys.argv[1]).resolve()
    slides = sorted(carpeta.glob("slide-0[1-6].html"))
    if len(slides) != 6:
        print(f"FALLA: se esperaban 6 slides y hay {len(slides)} en {carpeta}")
        return 1
    html = {p.name: p.read_text(encoding="utf-8") for p in slides}
    fallas, avisos = [], []

    # 1 · consistencia del contenido (slides 2 a 5, misma plantilla)
    # Alternan oscuro (2 y 4) y claro (3 y 5): cada par tiene que ser idéntico en plantilla.
    cuerpo = [html[f"slide-0{i}.html"] for i in range(2, 6)]
    for a_, b_ in ((2, 4), (3, 5)):
        if css(html[f"slide-0{a_}.html"]) != css(html[f"slide-0{b_}.html"]):
            fallas.append(f"1 · los slides {a_} y {b_} no usan la misma plantilla (CSS distinto)")
    if css(cuerpo[0]).replace(".kicker{color:#C}", "") [:400] != css(cuerpo[1])[:400]:
        avisos.append("1 · los slides oscuros y claros difieren más allá del color: revisar a ojo")
    sin_logo = [f"slide-0{i}" for i, h in zip(range(2, 6), cuerpo) if "simbolo.png" not in h]
    if sin_logo:
        fallas.append(f"1 · sin símbolo de marca: {', '.join(sin_logo)}")

    # 2 · portadas distintas entre carruseles
    portada = next(iter(sorted(IMAGENES.glob(f"{carpeta.name}_portada.*"))), None)
    if portada is None:
        avisos.append(f"2 · no hay imagen de portada en imagenes/ ({carpeta.name}_portada.*): pendiente")
    else:
        mia = hashlib.md5(portada.read_bytes()).hexdigest()
        gemelas = [p.name for p in IMAGENES.glob("*_portada.*")
                   if p != portada and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
                   and hashlib.md5(p.read_bytes()).hexdigest() == mia]
        if gemelas:
            fallas.append(f"2 · la portada es idéntica a: {', '.join(gemelas)}")
        avisos.append("2 · comparar a ojo con las demás portadas del mes (hoja de contacto)")

    # 3 · texto dentro de imágenes: se revisa a ojo
    imgs = sorted({m for h in html.values() for m in re.findall(r"(?:src=['\"]|url\([\"']?)([^'\")]+)", h)
                   if "simbolo.png" not in m})
    if portada:
        imgs.append(str(portada))
    if imgs:
        avisos.append("3 · abrir y revisar que no tengan texto: " + " · ".join(Path(i).name for i in imgs))

    # 4 · colores exactos
    for nombre, h in html.items():
        translucidos = re.findall(r"rgba?\([^)]*\)|hsla?\([^)]*\)", h)
        raros = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", h)} - EXACTOS
        cortos = re.findall(r"#[0-9A-Fa-f]{3}\b", h)
        if translucidos or raros or cortos:
            fallas.append(f"4 · {nombre}: colores fuera del design system "
                          f"{sorted(set(translucidos) | raros | set(cortos))}")

    # 5 · cifras con fuente visible · y tope de 40 palabras
    for nombre, h in html.items():
        texto = visible(h)
        palabras = len(texto.split())
        if palabras > 40:
            fallas.append(f"40 palabras · {nombre}: tiene {palabras}")
        if re.search(r"\d", texto) and "Fuente" not in texto:
            avisos.append(f"5 · {nombre}: tiene números y no dice 'Fuente:'. Si es un dato, falta la "
                          f"fuente; si es una hora o una instrucción, está bien. Texto: «{texto[:90]}…»")

    print(f"Carrusel: {carpeta.name}")
    for f in fallas:
        print("  FALLA  ", f)
    for a in avisos:
        print("  REVISAR", a)
    if not fallas:
        print("  OK      preguntas 1, 2, 4 y 40 palabras sin fallas automáticas; "
              "cerrar a ojo la 3 y los avisos de la 5.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
