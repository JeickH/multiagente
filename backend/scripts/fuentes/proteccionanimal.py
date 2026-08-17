"""Protección y Bienestar Animal del Valle del Cauca — tab «Ayúdanos a llegar a casa»

    https://proteccionanimal.valledelcauca.gov.co/ayudanos-llegar-casa

API .NET pública. El listado (`GetListAnimalesPerdidos`) es pobre y el detalle
(`GetAnimalDetail?AnimalId=`) trae la descripción y las fotos, así que hay que
pedir las dos cosas.

Dos rarezas de esta fuente, y las dos importan:

1. **Todos los registros dicen `estadoname: "Perdido"`**, incluso los que son
   hallazgos. Quien reporta lo escribe en el campo del nombre: hay fichas que se
   llaman literalmente "encontrado", "perdido" o "Me perdí". El tipo se deduce
   de ahí y **cada deducción queda marcada en la revisión**.
2. **El teléfono va escrito dentro de la descripción** ("…mancha blanca en
   pecho-3XXXXXXXXX", "Informes al: 3XX XXXXXXX"). Se extrae al campo de
   contacto y se BORRA del texto: si quedara en `senas`, el guardarraíl
   antiteléfonos del bot le tumbaría el turno al mostrar la ficha.

Las URLs de las fotos son de S3 **firmadas y con vencimiento de una hora**: por
eso las fotos se bajan durante la revisión y no al momento de cargar.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from . import base

FUENTE = "proteccionanimal"
TITULO = "Protección Animal del Valle → amigos perdidos y encontrados"
URL = "https://proteccionanimal.valledelcauca.gov.co/ayudanos-llegar-casa"
API = "https://api-proteccion.valledelcauca.gov.co/api"
DERIVADOS = ("color", "tamano", "edad")

COMO_SE_LLENO = [
    "<b>tipo_registro</b>: <b>deducido</b>. La fuente marca todo como «Perdido», así que "
    "se lee el nombre y la descripción: «encontrado/encontrada/hallado» → encontrada, "
    "el resto → perdida. <b>Cada ficha dice de dónde salió la deducción.</b>",
    "<b>contacto_telefono</b>: extraído de la descripción, donde la gente lo escribe. "
    "El número se <b>borra</b> del texto de señas — si se quedara ahí, el guardarraíl "
    "antiteléfonos del bot descartaría el turno al mostrar la ficha.",
    "<b>nombre</b>: se deja vacío cuando el campo trae «encontrado», «perdido» o «Me perdí», "
    "que no son nombres sino el estado.",
    "<b>ubicacion</b>: el municipio, que es lo único que da la fuente (no hay barrio).",
    "<b>color, tamano, edad</b>: los campos numéricos de la fuente vienen todos en 0 "
    "(sin usar), así que se leen de la descripción.",
    "<b>origen_url</b>: la ficha real en el sitio, con <code>id_animal</code> e "
    "<code>id_owner</code>.",
]

# Palabras con las que la gente marca un hallazgo en el nombre o la descripción.
_ENCONTRADA = ("encontrad", "hallad", "me encontre", "lo encontre", "la encontre",
               "esta en mi casa", "lo tengo", "la tengo", "aparecio")


def _resguardo(tipo_owner: str | None) -> str | None:
    """Quién tiene al animal, según el tipo de cuenta que lo reportó.

    "Voluntario Albergue (Hogar de Paso o Centro PYBA)" es literalmente lo que
    devuelve la API; un ciudadano que reporta lo tiene en su casa.
    """
    t = base.sin_tildes(tipo_owner or "")
    if "albergue" in t or "hogar de paso" in t or "pyba" in t:
        return "albergue"
    if "ciudadano" in t:
        return "con_quien_la_encontro"
    return None


def _clasificar(nombre: str, descripcion: str) -> Tuple[str, str]:
    """Devuelve (tipo_registro, por qué). El porqué se muestra en la revisión."""
    n, d = base.sin_tildes(nombre), base.sin_tildes(descripcion)
    for palabra in _ENCONTRADA:
        if palabra in n:
            return "encontrada", f"el nombre de la ficha dice «{nombre.strip()}»"
        if palabra in d:
            return "encontrada", f"la descripción dice «{palabra}»"
    return "perdida", "no dice lo contrario y la fuente la marca como «Perdido»"


def bajar() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    listado = base.bajar_json(f"{API}/Animales/GetListAnimalesPerdidos")["data"]
    registros: List[Dict[str, Any]] = []
    descartados: Dict[str, int] = {}

    for i, item in enumerate(listado):
        animal_id = item["id"]
        try:
            detalle = base.bajar_json(
                f"{API}/Animales/GetAnimalDetail?AnimalId={animal_id}")["data"]
        except Exception as exc:
            print(f"  aviso: detalle {animal_id} falló ({exc})")
            detalle = []
        d = detalle[0] if detalle else {}

        especie = base.normalizar_especie(item.get("especie") or d.get("especie_animal"))
        if not especie:
            clave = f"especie no reconocida ({item.get('especie')})"
            descartados[clave] = descartados.get(clave, 0) + 1
            continue

        nombre_crudo = (d.get("nombre_animal") or item.get("nombre") or "").strip()
        descripcion = (d.get("description") or "").strip()
        personalidad = (d.get("personality") or "").strip()
        tipo, porque = _clasificar(nombre_crudo, descripcion)

        nombre = base.valor_real(nombre_crudo, 80)
        senas_crudas = " ".join(t for t in (descripcion, personalidad) if t)
        municipio = (item.get("ubicacion") or d.get("ubicacion_animal") or "").strip()

        notas = [
            f"Importado de Protección Animal del Valle (ficha {animal_id}).",
            f"Reportado por: {item.get('owner') or d.get('albergue') or 'sin dato'}"
            f" ({d.get('owner_type_name') or 'sin tipo'}).",
            f"Tipo deducido: {porque}.",
        ]
        if d.get("sterilized"):
            notas.append("La fuente la marca esterilizada.")

        fotos = [img["url"] for img in (d.get("imgs") or []) if img.get("url")]
        if not fotos and item.get("Img1_URL"):
            fotos = [item["Img1_URL"]]

        registros.append({
            "origen_id": str(animal_id),
            "tipo_registro": tipo,
            "especie": especie,
            "raza": None,                       # la fuente no tiene raza
            "color": base.color_desde_texto(senas_crudas),
            "nombre": base.limpiar(nombre, 80),
            "sexo": base.normalizar_sexo(item.get("sexo") or d.get("sexo_animal")),
            "edad": base.edad_desde_texto(senas_crudas),
            "tamano": base.tamano_desde_texto(senas_crudas),
            "senas": base.limpiar(base.quitar_telefonos(senas_crudas), 2000),
            "ubicacion": base.limpiar(municipio or "Valle del Cauca", 255),
            "barrio": base.limpiar(municipio, 120),
            "maps_url": None,
            "contacto_nombre": base.limpiar(item.get("owner"), 120),
            "contacto_telefono": base.telefono_de_texto(descripcion, personalidad),
            "origen_url": (
                f"https://proteccionanimal.valledelcauca.gov.co/detalles-animal"
                f"?id_animal={animal_id}&id_owner={item.get('id_owner', '')}"
            ),
            "fecha_evento": None,               # la fuente no publica fecha
            "notas": base.limpiar(" ".join(notas), 2000),
            # Multi-fuente: es la única que da estado sanitario. Los numéricos
            # (edad, peso, tamaño) vienen todos en 0 = sin usar, y `_decimal`
            # ya descarta el 0, así que se mandan tal cual.
            "ciudad": base.valor_real(municipio, 120),
            "departamento": "Valle del Cauca",   # es la gobernación del Valle
            "esterilizado": d.get("sterilized"),
            "vacunado": d.get("vaccinated"),
            "desparasitado": d.get("dewormed"),
            "peso_kg": d.get("peso_animal"),
            "resguardo": _resguardo(d.get("owner_type_name")),
            "resguardo_nombre": base.limpiar(
                d.get("albergue") or item.get("owner"), 120),
            "estado_origen": item.get("estadoname"),
            "publicado_origen_at": None,
            "_fotos": fotos,
            "_crudo": {**item, "detalle": {k: v for k, v in d.items() if k != "imgs"}},
            "_alertas": [
                f"<b>Tipo deducido</b> como <i>{tipo}</i> porque {porque}. "
                "La fuente no distingue perdidas de encontradas: confírmalo."
            ],
        })
        if i % 10 == 9:
            print(f"  ... {i + 1}/{len(listado)} fichas")
        time.sleep(0.35)
    return registros, descartados
