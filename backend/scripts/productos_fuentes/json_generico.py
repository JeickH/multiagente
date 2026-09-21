"""Una receta que no sabe de ningún negocio: el catálogo **es** el archivo JSON.

`covenas.py` es la receta modelo de una fuente que llega con la forma del
cliente (el Excel de la agencia, convertido a JSON por su conversor): hay que
traducirla, y esa traducción es código. Las cinco cuentas de la fase 7 son el
otro caso, y es el mayoritario: **no hay archivo del cliente**. Lo que vende
Jerarquía vive hoy en un `.md` del repositorio y en el `llm_config` del bot, y
escribir cinco módulos de Python para copiar eso a mano sería mover el problema
de sitio — seguiría habiendo que desplegar para cambiar un precio.

Así que la receta de esas cuentas es un JSON con la forma de `base.Catalogo`, y
este módulo es el único código que hace falta: lo lee, lo valida y lo entrega.
El archivo es el que se edita, el que se hashea y el que se aprueba en el HTML
de revisión, exactamente igual que el tarifario de Coveñas.

    {
      "slug": "promo_manada",
      "titulo": "Promo Manada",             # el título del HTML de revisión
      "nombre": "Promo Manada",
      "tipo": "producto",                   # plan | producto | catalogo_externo | ficha
      "estado": "publicado",
      "resumen": "…",                       # máx. 240: entra al prompt
      "instrucciones": "…",                 # nivel 3, lo que hay que saber para venderlo
      "atributos": {"presentacion": {…}},   # cómo se le redacta al modelo
      "vigencia_desde": null, "vigencia_hasta": null,
      "como_se_lleno": ["…"],               # qué le explica el HTML a quien aprueba
      "variantes": [{"slug": …, "nombre": …, "orden": 1, "precios_de": …}],
      "filas":     [{"externo_id": …, "tipo": "precio", "valores": {…}}],
      "medios":    [{"clave": …, "url": …}],
      "alias":     [{"alias": "negro", "nivel": "variante", "variante": "negro"}]
    }

Tres cosas que este módulo hace y conviene saber
------------------------------------------------
1. **Las fechas se leen con `date.fromisoformat`**, así que una fecha mal
   escrita revienta acá y no seis pasos después con un `TypeError` del ORM.
2. **Ningún campo se inventa.** Lo que el JSON no trae queda con el valor por
   defecto de `base.Catalogo`, que es el mismo que usa la base.
3. **Una clave desconocida es un error, no un campo que se ignora en silencio.**
   Un `"varinates"` mal escrito produciría un producto sin variantes y una
   revisión que dice "todo bien": el fallo más caro de este importador es el que
   no se ve en el HTML.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from . import base

#: Carpeta donde viven los archivos. Se resuelve desde este módulo y no desde
#: el directorio de trabajo: el importador se corre tanto desde la raíz del
#: repo como desde dentro del contenedor, donde no hay carpeta `backend/`.
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")

_CAT = {
    "slug", "titulo", "nombre", "tipo", "estado", "resumen", "instrucciones",
    "atributos", "vigencia_desde", "vigencia_hasta", "como_se_lleno",
    "variantes", "filas", "medios", "alias",
}
_VAR = {"slug", "nombre", "orden", "atributos", "instrucciones", "precios_de", "activo"}
_FIL = {
    "externo_id", "variante", "tipo", "etiqueta", "inicio", "fin", "valores",
    "nota", "orden", "activo",
}
_MED = {"clave", "url", "variante", "tipo", "descripcion", "aplica"}
_ALI = {"alias", "nivel", "variante"}


def _revisar(dato: Dict[str, Any], permitidas: Sequence[str], donde: str) -> None:
    sobran = sorted(set(dato) - set(permitidas))
    if sobran:
        raise ValueError(
            f"{donde}: clave(s) que este importador no conoce: {', '.join(sobran)}. "
            "Si es un dato del negocio va dentro de `valores` o de `atributos`; "
            "si es un typo, el producto se cargaría incompleto sin que el HTML "
            "de revisión lo diga."
        )


def _fecha(valor: Any) -> Optional[date]:
    return date.fromisoformat(valor) if valor else None


def leer_catalogo(ruta: str) -> base.Catalogo:
    """El archivo, convertido en catálogo. No toca la base."""
    with open(ruta, encoding="utf-8") as fh:
        crudo = json.load(fh)
    _revisar(crudo, _CAT, os.path.basename(ruta))

    cat = base.Catalogo(
        slug=crudo["slug"],
        nombre=crudo["nombre"],
        tipo=crudo.get("tipo", base.models.PRODUCTO_TIPO_PRODUCTO),
        estado=crudo.get("estado", base.models.PRODUCTO_ESTADO_BORRADOR),
        resumen=crudo.get("resumen"),
        instrucciones=crudo.get("instrucciones"),
        atributos=crudo.get("atributos") or {},
        vigencia_desde=_fecha(crudo.get("vigencia_desde")),
        vigencia_hasta=_fecha(crudo.get("vigencia_hasta")),
    )

    for i, v in enumerate(crudo.get("variantes") or []):
        _revisar(v, _VAR, f"variantes[{i}]")
        cat.variantes.append(
            base.Variante(
                slug=v["slug"],
                nombre=v["nombre"],
                orden=int(v.get("orden", i + 1)),
                atributos=v.get("atributos") or {},
                instrucciones=v.get("instrucciones"),
                precios_de=v.get("precios_de"),
                activo=bool(v.get("activo", True)),
            )
        )

    for i, f in enumerate(crudo.get("filas") or []):
        _revisar(f, _FIL, f"filas[{i}]")
        cat.filas.append(
            base.Fila(
                externo_id=f["externo_id"],
                variante=f.get("variante"),
                tipo=f.get("tipo", base.models.FILA_TIPO_PRECIO),
                etiqueta=f.get("etiqueta"),
                inicio=_fecha(f.get("inicio")),
                fin=_fecha(f.get("fin")),
                valores=f.get("valores") or {},
                nota=f.get("nota"),
                orden=int(f.get("orden", i)),
                activo=bool(f.get("activo", True)),
            )
        )

    for i, m in enumerate(crudo.get("medios") or []):
        _revisar(m, _MED, f"medios[{i}]")
        cat.medios.append(
            base.Medio(
                clave=m["clave"],
                url=m["url"],
                variante=m.get("variante"),
                tipo=m.get("tipo", "image"),
                descripcion=m.get("descripcion"),
                aplica=m.get("aplica") or {},
            )
        )

    for i, a in enumerate(crudo.get("alias") or []):
        _revisar(a, _ALI, f"alias[{i}]")
        cat.alias.append(
            base.Alias(
                alias=a["alias"],
                nivel=a.get("nivel", base.models.ALIAS_NIVEL_PRODUCTO),
                variante=a.get("variante"),
            )
        )

    cat.validar()
    return cat


class Receta:
    """Lo que `importar_producto.py` espera de una receta, sobre un JSON.

    Misma superficie que `covenas`: `SLUG`, `TITULO`, `COMO_SE_LLENO`,
    `ARCHIVO_POR_DEFECTO` y `leer(ruta)`. El importador no distingue una de
    otra, que es justamente la prueba de que la capa genérica alcanza.
    """

    def __init__(self, archivo: str) -> None:
        self.ARCHIVO_POR_DEFECTO = archivo
        with open(archivo, encoding="utf-8") as fh:
            cabecera = json.load(fh)
        self.SLUG: str = cabecera["slug"]
        self.TITULO: str = cabecera.get("titulo") or cabecera["nombre"]
        self.COMO_SE_LLENO: List[str] = list(cabecera.get("como_se_lleno") or [])

    def leer(self, ruta: str) -> base.Catalogo:
        return leer_catalogo(ruta)

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f"<Receta {self.SLUG} {os.path.basename(self.ARCHIVO_POR_DEFECTO)}>"


def recetas(carpeta: str = DATOS) -> Dict[str, Receta]:
    """Una receta por archivo de la carpeta, indexada por su slug.

    Agregar una cuenta es dejar un JSON acá: no hay que tocar este módulo, ni
    `base.py`, ni el motor. Dos archivos con el mismo slug son un error — el
    slug es lo que el importador recibe por la línea de comandos.
    """
    fuera: Dict[str, Receta] = {}
    for nombre in sorted(os.listdir(carpeta)):
        if not nombre.endswith(".json") or nombre.startswith("_"):
            continue
        receta = Receta(os.path.join(carpeta, nombre))
        if receta.SLUG in fuera:
            otro = os.path.basename(fuera[receta.SLUG].ARCHIVO_POR_DEFECTO)
            raise ValueError(
                f"el slug {receta.SLUG!r} está en dos archivos ({otro} y "
                f"{nombre}): el importador no sabría cuál cargar."
            )
        fuera[receta.SLUG] = receta
    return fuera
