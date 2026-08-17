"""PetSearch Colombia — https://petsearch.neuralync.dev

Tiene API JSON pública y sin autenticación. Trae los tres estados en el mismo
endpoint, cambiando `status`:

    missing  familias buscando a su mascota      -> perdida
    stray    alguien la tiene y busca al dueño   -> encontrada
    found    ya volvió a casa                    -> NO se trae

Es la única de las tres fuentes que publica el teléfono de quien reportó, así
que sus fichas entran con contacto directo y no dependen de `origen_url`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import base

FUENTE = "petsearch"
TITULO = "PetSearch Colombia → mascotas perdidas y encontradas"
URL = "https://petsearch.neuralync.dev/"
API = "https://api.neuralync.dev/api/petsearch/pets"

# Los estados que sí traemos, y a qué tipo de reporte nuestro corresponden.
ESTADOS = {"missing": "perdida", "stray": "encontrada"}
DERIVADOS = ("color", "sexo", "tamano", "edad")

COMO_SE_LLENO = [
    "<b>tipo_registro</b>: <code>missing</code> → perdida, <code>stray</code> → encontrada. "
    "Las <code>found</code> (ya volvieron a casa) no se traen.",
    "<b>contacto_telefono</b>: el que publica la fuente, normalizado a formato local "
    "(llegan como <code>573147530915</code> y como <code>3178340390</code>).",
    "<b>ubicacion</b>: el barrio más la ciudad, porque la ubicación es obligatoria.",
    "<b>senas</b>: el campo <code>features</code> tal cual.",
    "<b>color, sexo, tamano, edad</b>: la fuente no los tiene como campo aparte; se leen "
    "de la descripción y quedan en NULL si no la mencionan. Van marcados en cada ficha.",
    "<b>origen_url</b>: la fuente no tiene página por mascota, así que apunta a su portada.",
]


def bajar() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    registros: List[Dict[str, Any]] = []
    descartados: Dict[str, int] = {}

    crudos = base.bajar_json(f"{API}?status=found")
    descartados["🎉 reencontradas (found)"] = len(crudos)

    for estado, tipo in ESTADOS.items():
        for c in base.bajar_json(f"{API}?status={estado}"):
            especie = base.normalizar_especie(c.get("species"))
            if not especie:
                descartados[f"especie no reconocida ({c.get('species')})"] = (
                    descartados.get(f"especie no reconocida ({c.get('species')})", 0) + 1
                )
                continue

            features = c.get("features") or ""
            breed = c.get("breed") or ""
            # `location` a veces trae un estado en vez de un lugar ("RESCATADO"):
            # como zona no sirve, y guardarla ensuciaría el cruce.
            location = base.valor_real(c.get("location"), 120) or ""
            city = (c.get("city") or "").strip()
            department = (c.get("department") or "").strip()

            # La ubicación es obligatoria: barrio + ciudad, y si no hay barrio,
            # al menos la ciudad o el departamento.
            partes = [p for p in (location, city) if p]
            ubicacion = ", ".join(partes) or department or "Colombia"

            fecha = (c.get("created_at") or "")[:10] or None
            notas = [f"Importado de PetSearch Colombia (estado en la fuente: {estado})."]
            if department:
                notas.append(f"Departamento: {department}.")
            if city:
                notas.append(f"Ciudad: {city}.")
            if c.get("created_at"):
                notas.append(f"Publicado en la fuente el {c['created_at'][:10]}.")

            registros.append({
                "origen_id": str(c["id"]),
                "tipo_registro": tipo,
                "especie": especie,
                "raza": base.limpiar(breed, 80),
                "color": base.color_desde_texto(features, breed),
                "nombre": base.valor_real(c.get("name"), 80),
                "sexo": base.sexo_desde_texto(features, c.get("name")),
                "edad": base.edad_desde_texto(features),
                "tamano": base.tamano_desde_texto(features, breed),
                "senas": base.limpiar(base.quitar_telefonos(features), 2000),
                "ubicacion": base.limpiar(ubicacion, 255),
                "barrio": base.limpiar(location or city, 120),
                "maps_url": None,
                "contacto_nombre": None,
                "contacto_telefono": base.telefono_colombiano(c.get("phone")),
                "origen_url": URL,
                "fecha_evento": fecha,
                "notas": base.limpiar(" ".join(notas), 2000),
                # Multi-fuente: PetSearch separa ciudad y departamento, que es
                # más de lo que dan las otras.
                "ciudad": base.valor_real(city, 120),
                "departamento": base.valor_real(department, 120),
                "estado_origen": estado,
                "publicado_origen_at": c.get("created_at"),
                "_fotos": [u for u in (c.get("photo_urls") or []) if u],
                "_crudo": c,
                "_alertas": [],
            })
    return registros, descartados
