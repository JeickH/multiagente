"""¿Son el mismo animal? Comparación visual de dos fotos con Claude (Bedrock).

POR QUÉ EXISTE
--------------
El cruce puntúa texto: raza, color, tamaño, zona. Eso funciona cuando quien
reporta describe bien, pero una descripción escrita por alguien angustiado a las
2 de la mañana ("perrito café, mediano") empata con media Cali. La foto tiene la
información que la descripción pierde: la mancha del pecho, la oreja partida, el
patrón atigrado.

CÓMO SE USA (y cómo NO)
-----------------------
Esto **no reemplaza** al puntaje de texto: lo desempata. El texto es gratis y
filtra miles de pares; la visión cuesta una llamada al modelo por par, así que
solo se aplica a los pocos candidatos que el texto ya dejó arriba. Un cruce
completo son ~12.500 pares: pasarlos todos por visión costaría más que el resto
de la operación junta.

El resultado es una PISTA, no un veredicto. Nadie recibe un teléfono porque el
modelo dijo "9/10": la persona sigue confirmando en el chat y el equipo sigue
llamando a las dos partes antes de dar un reencuentro por bueno.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tope de comparaciones por búsqueda. Son llamadas al modelo con dos imágenes
# cada una —lo más caro que hace este bot—, y a partir de la cuarta candidata el
# texto ya ordenó bastante bien. Si algún día sube, que sea con números medidos.
MAX_COMPARACIONES = 4

_PROMPT = (
    "Compara las dos fotos. La PRIMERA es la mascota que una familia está "
    "buscando; la SEGUNDA es una que alguien encontró.\n\n"
    "Decide si podrían ser el mismo animal fijándote en lo que no cambia: "
    "especie, patrón y distribución del color, manchas, largo y textura del "
    "pelo, forma de las orejas y del hocico, proporciones, y señas como "
    "cicatrices o collares.\n\n"
    "Ignora lo que cambia con la foto: iluminación, ángulo, fondo, qué tan "
    "sucio o mojado está el animal, y lo grande que se vea.\n\n"
    "Responde SOLO un JSON: {\"parecido\": 0-10, \"motivo\": \"…\"}\n"
    "- 0-2: claramente distintos (otra especie, otro color, otro pelaje).\n"
    "- 3-5: mismo tipo de animal, sin señas que lo confirmen ni lo descarten.\n"
    "- 6-8: varias señas coinciden.\n"
    "- 9-10: hay una seña inconfundible que coincide.\n"
    "El motivo va en español, máximo 15 palabras, y nombra la seña concreta "
    "en la que te fijaste. Ante la duda, puntúa BAJO: mandar a una familia "
    "tras una pista falsa cuesta más que dejarla pasar."
)

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _media_type(content_type: Optional[str]) -> str:
    ct = (content_type or "").lower().strip()
    return ct if ct in ("image/jpeg", "image/png", "image/gif", "image/webp") else "image/jpeg"


def _bloque_imagen(data: bytes, content_type: Optional[str]) -> Dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _media_type(content_type),
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def comparar(
    foto_perdida: Tuple[bytes, Optional[str]],
    foto_encontrada: Tuple[bytes, Optional[str]],
    model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """`{"parecido": 0-10, "motivo": "..."}` o None si no se pudo comparar.

    Nunca levanta: si el proveedor falla, el cruce sigue con el puntaje de
    texto, que es exactamente como funcionaba antes de existir esta función.
    """
    from .llm_engine import _bedrock_client, _env_model_id

    try:
        cuerpo = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "messages": [{
                "role": "user",
                "content": [
                    _bloque_imagen(*foto_perdida),
                    _bloque_imagen(*foto_encontrada),
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        }
        resp = _bedrock_client().invoke_model(
            modelId=model_id or _env_model_id(),
            body=json.dumps(cuerpo, ensure_ascii=False),
        )
        data = json.loads(resp["body"].read())
        texto = "".join(
            b.get("text", "") for b in (data.get("content") or [])
            if b.get("type") == "text"
        )
        crudo = _JSON_RE.search(texto)
        if not crudo:
            return None
        salida = json.loads(crudo.group(0))
        parecido = int(salida.get("parecido", 0))
        return {
            "parecido": max(0, min(10, parecido)),
            "motivo": str(salida.get("motivo") or "")[:120],
        }
    except Exception:
        # Regla #6: el detalle se queda aquí; arriba solo se pierde el desempate.
        logger.exception("vision_mascotas: no se pudo comparar las fotos")
        return None


def puntos_por_parecido(parecido: int) -> int:
    """Cuánto suma la foto al puntaje de texto.

    Deliberadamente modesto: el máximo (5) empata con lo que vale acertar la
    raza. La foto desempata entre candidatos que el texto ya dejó cerca; no
    puede por sí sola encaramar a un animal que no se parece en nada. Por debajo
    de 6 no suma: "podrían ser" no es información.
    """
    if parecido >= 9:
        return 5
    if parecido >= 7:
        return 3
    if parecido >= 6:
        return 1
    return 0


def reordenar_candidatas(
    foto_persona: Optional[Tuple[bytes, Optional[str]]],
    candidatas: List[Dict[str, Any]],
    leer_foto,
    model_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Reordena las candidatas del texto usando la foto que trajo la persona.

    `leer_foto(codigo)` devuelve `(bytes, content_type)` de la candidata, o None
    si no tiene foto. Las que no tengan foto conservan su puntaje de texto y
    quedan detrás de las que sí pudieron compararse — no se penalizan, solo no
    ganan el desempate.

    Si no hay foto de la persona, devuelve la lista tal cual: sin nada que
    comparar, el orden del texto es el mejor que hay.
    """
    if not foto_persona or not candidatas:
        return candidatas

    for candidata in candidatas[:MAX_COMPARACIONES]:
        try:
            otra = leer_foto(candidata["codigo"])
        except Exception:
            logger.exception("vision_mascotas: no se pudo leer la foto de %s",
                             candidata.get("codigo"))
            otra = None
        if not otra:
            continue
        veredicto = comparar(foto_persona, otra, model_id=model_id)
        if not veredicto:
            continue
        candidata["parecido_foto"] = veredicto["parecido"]
        candidata["motivo_foto"] = veredicto["motivo"]
        candidata["score"] = (candidata.get("score") or 0) + puntos_por_parecido(
            veredicto["parecido"]
        )

    return sorted(
        candidatas,
        key=lambda c: (c.get("score") or 0, c.get("parecido_foto") or 0),
        reverse=True,
    )
