"""encontradogs — https://www.encontradogs.co

Sitio renderizado en el servidor, sin API. La portada trae dos secciones
("Mascotas que alguien encontró" y "Mascotas perdidas") y de ahí sale el tipo
de cada ficha; el detalle vive en `/pet/<id>` con los campos ya separados.

Las que ya volvieron a casa no aparecen en la portada, así que salir de ahí
—en vez de recorrer los ids— es lo que las deja fuera sin tener que adivinar.

**No publica teléfonos**: el sitio hace de intermediario entre quien busca y
quien encontró. Sus fichas entran con `origen_url` como única vía de contacto,
igual que las de patitasacasa.
"""
from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import base

FUENTE = "encontradogs"
TITULO = "encontradogs → mascotas encontradas y perdidas"
URL = "https://www.encontradogs.co/"
DERIVADOS = ("edad",)

COMO_SE_LLENO = [
    "<b>tipo_registro</b>: la sección de la portada donde aparece la ficha — "
    "«Mascotas que alguien encontró» → encontrada, «Mascotas perdidas» → perdida.",
    "<b>contacto_telefono</b>: <b>vacío a propósito</b>. El sitio no publica el teléfono; "
    "hace de intermediario. La vía de contacto es <code>origen_url</code>, que lleva a la "
    "ficha original — el bot ya sabe manejar ese caso.",
    "<b>especie, tamano, color, raza, sexo, senas</b>: vienen como campos separados en la "
    "ficha, se copian tal cual.",
    "<b>ubicacion / barrio</b>: el campo «Dónde» de la ficha.",
    "<b>Las 9 «de vuelta en casa» no se traen</b>: no aparecen listadas en la portada.",
]

_ETIQUETAS = {
    "especie": "especie", "tamaño": "tamano", "tamano": "tamano", "color": "color",
    "raza": "raza", "sexo": "sexo", "señas": "senas", "senas": "senas",
    "dónde": "donde", "donde": "donde",
}


def _texto(fragmento: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", fragmento or "")).strip()


def _secciones(portada: str) -> Dict[str, str]:
    """Devuelve {id de ficha: tipo_registro} leyendo los dos bloques de la portada."""
    tipos: Dict[str, str] = {}
    for bloque in re.split(r"<h2>", portada)[1:]:
        titulo = base.sin_tildes(_texto(bloque.split("</h2>")[0]))
        if "alguien encontro" in titulo:
            tipo = "encontrada"
        elif "perdidas" in titulo:
            tipo = "perdida"
        else:
            continue
        for pid in re.findall(r'href="/pet/(\d+)"', bloque):
            tipos.setdefault(pid, tipo)
    return tipos


def _ficha(pid: str, tipo: str) -> Optional[Dict[str, Any]]:
    pagina = base.bajar_html(f"{URL}pet/{pid}")
    principal = re.search(r"<main>(.*?)</main>", pagina, re.S)
    if not principal:
        return None
    principal = principal.group(1)

    datos: Dict[str, str] = {}
    for dt, dd in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", principal, re.S):
        clave = _ETIQUETAS.get(base.sin_tildes(_texto(dt)))
        if clave:
            datos[clave] = _texto(dd)

    titulo = _texto((re.search(r"<h1>(.*?)</h1>", principal, re.S) or [None, ""])[1])
    mensaje = _texto((re.search(r'<p class="msg">(.*?)</p>', principal, re.S) or [None, ""])[1])
    fecha = (re.search(r'<time class="ts" datetime="([^"]+)"', principal) or [None, ""])[1][:10]
    fotos = [
        f"{URL.rstrip('/')}/photo/{f}"
        for f in re.findall(r'src="/photo/(\d+)/(?:face|thumb)', principal)
    ]

    especie = base.normalizar_especie(datos.get("especie")) or "otra"
    donde = datos.get("donde") or ""
    # El título es autogenerado ("Perro mediano Café con ojos miel") cuando la
    # mascota no tiene nombre: en ese caso no sirve como nombre.
    nombre = None if base.sin_tildes(titulo).startswith(("perro ", "gato ", "gata ")) else titulo
    senas = " ".join(t for t in (datos.get("senas"), mensaje) if t)

    return {
        "origen_id": pid,
        "tipo_registro": tipo,
        "especie": especie,
        "raza": base.limpiar(datos.get("raza"), 80),
        "color": base.limpiar(datos.get("color"), 80),
        "nombre": base.limpiar(nombre, 80),
        "sexo": base.normalizar_sexo(datos.get("sexo")),
        "edad": base.edad_desde_texto(senas),
        "tamano": base.limpiar(datos.get("tamano"), 24),
        "senas": base.limpiar(base.quitar_telefonos(senas), 2000),
        "ubicacion": base.limpiar(donde or "Colombia", 255),
        "barrio": base.limpiar(donde, 120),
        "maps_url": None,
        "contacto_nombre": None,
        "contacto_telefono": None,          # el sitio no lo publica, a propósito
        "origen_url": f"{URL}pet/{pid}",
        "fecha_evento": fecha or None,
        "notas": base.limpiar(
            f"Importado de encontradogs (ficha /pet/{pid}). El sitio no publica el "
            f"teléfono: el contacto se resuelve en su ficha original.", 2000),
        "_fotos": fotos,
        "_crudo": {"id": pid, "titulo": titulo, "seccion": tipo, **datos,
                   "mensaje": mensaje, "fecha": fecha},
        "_alertas": [],
    }


def bajar() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    portada = base.bajar_html(URL)
    tipos = _secciones(portada)
    reunidas = re.search(r"(\d+)\s*de vuelta en casa", portada)
    descartados = {
        "🎉 de vuelta en casa (no listadas en la portada)":
            int(reunidas.group(1)) if reunidas else 0
    }

    registros: List[Dict[str, Any]] = []
    for i, (pid, tipo) in enumerate(sorted(tipos.items(), key=lambda kv: int(kv[0]))):
        try:
            ficha = _ficha(pid, tipo)
            if ficha:
                registros.append(ficha)
        except Exception as exc:
            print(f"  aviso: /pet/{pid} no se pudo leer ({exc})")
        if i % 10 == 9:
            print(f"  ... {i + 1}/{len(tipos)} fichas")
        time.sleep(0.35)          # el sitio es chico: no lo atropellamos
    return registros, descartados
