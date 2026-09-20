"""Receta del tarifario de Coveñas: el JSON de temporada → un producto.

El archivo de origen es `app/data/tarifario_covenas.json`, que es lo que
`generar_tarifario_covenas.py` saca del Excel del CEO. Mientras dure la ventana
de fallback el JSON sigue siendo la fuente que lee el motor viejo; cuando la
fase 8 lo retire, esta receta pasará a leer el Excel directamente (el conversor
ya existe y no cambia de forma).

Cómo se traduce, en una línea por tabla
---------------------------------------
  * **producto**   `covenas_temporada`, un plan.
  * **variantes**  un hotel cada una. Bohíos no duplica la tabla de precios:
    la toma de Amor de Dios con `precios_de`.
  * **filas**      una por salida del JSON. `inicio` en la columna (es por
    donde se filtra la vigencia) y el resto en `valores`. El `externo_id` es
    `inicio|fecha|hotel`: lo que identifica a la salida en el archivo del
    cliente, y lo que hace que reimportar no duplique.
  * **alias**      los doce nombres con los que la gente escribe un hotel.
  * **medios**     las 13 piezas del catálogo del bot. Las cuatro de tarifario
    cuelgan de su hotel y llevan los meses que cubren; las otras nueve
    (info, videos, tours, pagos, formulario) son del producto entero.
  * **presentación** el texto con el que se le responde al modelo viaja como
    dato en `atributos["presentacion"]`: la capa nueva no puede nombrar un
    hotel ni una acomodación.

Sobre el texto de `PRESENTACION`: está escrito acá y **otra vez** en
`tests/productos/covenas.py`. No es un descuido — la prueba de paridad compara
las dos construcciones, y si compartieran el diccionario compararía una cosa
consigo misma. La que manda es esta; el día que se toque una frase, la prueba
avisa que la otra copia quedó atrás.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Dict, List

from app import models

from . import base

SLUG = "covenas_temporada"
TITULO = "Tarifario de Coveñas"
NOMBRE = "Plan Coveñas"
RESUMEN = "Plan a Coveñas con salidas semanales y dos hoteles."

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARCHIVO_POR_DEFECTO = os.path.join(RAIZ, "app", "data", "tarifario_covenas.json")

COMO_SE_LLENO = [
    "Cada salida del JSON es una fila, con `inicio` en columna y el resto "
    "(multiple, doble, noches, dias, plan) en `valores`.",
    "El `externo_id` de cada fila es `inicio|fecha|hotel`: es lo que hace que "
    "cargar el mismo archivo dos veces no duplique nada.",
    "La fila es del hotel que pone el precio. Bohíos no tiene filas propias: "
    "lee las de Amor de Dios por `precios_de_variante_id`.",
    "Los medios salen del catálogo del bot de viajes (`app/data/bot_viajes.py`), "
    "que es donde está escrito qué flyer corresponde a qué mes.",
    "El texto con el que se le habla al modelo viaja en "
    "`atributos['presentacion']`, no en el código.",
]

#: Hotel del JSON -> (slug, nombre, orden). El orden es el de la frase «los
#: hoteles del plan son: Amor de Dios, Piedra Mar y Bohíos».
HOTELES = {
    "amor_de_dios": ("amor_de_dios", "Amor de Dios", 1),
    "piedra_mar": ("piedra_mar", "Piedra Mar", 2),
    "bohios": ("bohios", "Bohíos", 3),
}

#: Los doce nombres con los que la gente escribe un hotel, en orden: la
#: resolución por contención depende de él.
ALIAS = [
    ("amor_de_dios", "amor_de_dios"),
    ("amor de dios", "amor_de_dios"),
    ("el amor de dios", "amor_de_dios"),
    ("hotel amor de dios", "amor_de_dios"),
    ("hotel el amor de dios", "amor_de_dios"),
    ("amordios", "amor_de_dios"),
    ("bohios", "bohios"),
    ("hotel bohios", "bohios"),
    ("los bohios", "bohios"),
    ("piedra_mar", "piedra_mar"),
    ("piedra mar", "piedra_mar"),
    ("piedramar", "piedra_mar"),
]

#: Columnas del JSON que son estructura (van a columnas de la tabla) y no
#: `valores`. `hoteles` define de quién es la fila; `mes` es `inicio.month`.
_ESTRUCTURA = {"hoteles", "inicio", "fecha", "mes"}

#: Lo que Bohíos tiene que decir cuando manda un flyer que no es suyo.
NOTA_MEDIO_BOHIOS = (
    "  Y al mandarla, avísale que el flyer sale a nombre de *{origen}* pero "
    "los precios aplican igual para {variante} — si no se lo dices, va a creer "
    "que le mandaste el hotel equivocado."
)

#: Piedra Mar sí tiene salidas entre semana, pero no cuando el lunes es festivo.
COLETILLA_PIEDRA_MAR = " No aplica para lunes festivos."

#: Cómo se le habla al modelo. Cada string sale de `services/tarifario.py`; lo
#: único que cambia son los `{campos}`.
PRESENTACION: Dict[str, Any] = {
    "encabezado": [
        "Tarifario de Coveñas — valores POR PERSONA (hoy es {hoy}; solo se "
        "listan salidas que todavía no han pasado).",
        "DURACIÓN: cada salida de abajo trae la suya entre paréntesis (noches / "
        "días) y no todas duran lo mismo. Cópiala tal cual de la salida que "
        "estés ofreciendo. NO la cuentes de los bloques del itinerario: el "
        "viernes es el viaje de noche en bus y no cuenta como día de plan.",
    ],
    "cierre": [
        "Recuerda: NUNCA le mandes el Excel ni un archivo de datos al cliente, "
        "solo la imagen del tarifario que corresponde al mes.",
    ],
    "sin_periodo": (
        "No entendí para qué mes. Pregúntale al cliente en qué mes piensa "
        "viajar y vuelve a consultar."
    ),
    "variante_desconocida": (
        "No reconozco el hotel '{texto}'. Los hoteles del plan son: {variantes}."
    ),
    "aviso_vencido": (
        "OJO: el {fecha} ya pasó, no se puede vender. Dile que esa fecha ya "
        "salió y ofrécele de una las que siguen disponibles — NO le preguntes "
        "«¿para cuál otra fecha?» sin darle opciones."
    ),
    "duracion": "{noches} noches / {dias} días",
    "nota_fila": ", {plan}",
    "fila": (
        "  · {etiqueta} — múltiple {multiple_pesos} · doble {doble_pesos} "
        "({duracion}{obs}){marca}"
    ),
    "fila_marcada": "  <-- la fecha que pidió",
    "bloque_titulo": "{variante} — {periodo} ({n} salidas):",
    "vacio": (
        "{variante} — {periodo}: NO hay NADA publicado para ese mes en este "
        "hotel: ni fines de semana ni salidas entre semana. La promoción de "
        "«lunes a jueves» NO aplica a un mes sin fechas publicadas — no se la "
        "ofrezcas para {periodo}."
    ),
    "vacio_periodos": (
        "  Meses que SÍ tienen salidas en {variante}, del más próximo al más "
        "lejano: {periodos}."
    ),
    "vacio_cierre": (
        "  Dile con qué meses SÍ hay y ofrécele el otro hotel; no escales "
        "todavía."
    ),
    "fecha_sin_fila": (
        "  OJO: no hay salida que arranque el {fecha} en {variante}. Las más "
        "cercanas son: {cercanas}. Ofrécele esas con su precio y su duración — "
        "NO escales por esto."
    ),
    "fila_cercana": "{etiqueta} ({duracion})",
    "medio": (
        "  OBLIGATORIO: en esta misma respuesta envía `{clave}` con "
        "`enviar_media`. No basta con listar los precios en texto."
    ),
    "nota_precios_compartidos": (
        "{variante} cobra exactamente lo mismo que {origen} (misma tabla)."
    ),
    "ambito_global": "los meses publicados",
    "desde_periodo": (
        "{grupo} — «desde» de {ambito}: {precio} por persona en múltiple "
        "({etiqueta}, {duracion}). Es el valor MÁS BAJO que queda publicado en "
        "{ambito}: no cites un «desde» más barato para ese mes, ni el de otro "
        "mes."
    ),
    "desde_global": (
        "{grupo} — «desde» de TODOS {ambito} (ojo: NO es de un mes en "
        "particular): {precio} por persona en múltiple, y cae en {etiqueta} "
        "({duracion}). Si el cliente ya dijo un mes, este valor NO le sirve: "
        "vuelve a consultar con ese mes, que tiene su propio «desde»."
    ),
    # Las salidas de «lunes con jueves»: el JSON no trae una columna que lo
    # diga, y la etiqueta del plan mezcla nombres. Lo inequívoco es el día de
    # arranque, que es calendario y no negocio.
    "subgrupo": {"dias_semana": [0, 1, 2, 3]},
    "subgrupo_con": (
        "  Entre semana (lunes con jueves) en {ambito}: {n} salida(s), desde "
        "{precio} por persona en múltiple ({etiqueta}, {duracion}).{coletilla}"
    ),
    "subgrupo_sin": (
        "  Entre semana (lunes con jueves) en {ambito}: no hay ninguna "
        "publicada. Sí existen salidas entre semana y puedes decirlo, pero "
        "para {ambito} NO les pongas precio ni «desde»: el único valor que "
        "puedes citar es el de la línea de arriba."
    ),
    "presupuesto_ambito_global": "toda la temporada publicada",
    "presupuesto_titulo": (
        "PRESUPUESTO de {tope} por persona — búsqueda sobre {ambito} (se "
        "compara contra la acomodación múltiple, que es la más económica)."
    ),
    "presupuesto_nada": (
        "  Con {tope} NO alcanza para ninguna salida de {ambito}. NO le digas "
        "«no hay nada» ni escales: ofrécele lo más económico que sí existe."
    ),
    "presupuesto_nada_mejor": "  Lo más económico de {ambito}:",
    "presupuesto_otros": (
        "  PERO en otros meses sí le alcanza: {periodos}. La más económica de "
        "todas es {precio} en {periodo} ({etiqueta}, {duracion}). Pregúntale "
        "si puede mover el viaje a alguno de esos meses — si dice que sí, "
        "vuelve a consultar con ese mes."
    ),
    "presupuesto_si": (
        "  Sí le alcanza: {total} salida(s), de la más económica a la que más "
        "aprovecha su presupuesto:"
    ),
    "presupuesto_si_tope": (
        "  Sí le alcanza: {total} salida(s). Van las {n} MÁS ECONÓMICAS (hay "
        "más, sin listar):"
    ),
    "fila_presupuesto": (
        "  · {variante} — {etiqueta}: múltiple {multiple_pesos} · doble "
        "{doble_pesos}{doble_cabe} ({noches} noches / {dias} días)"
    ),
    "cabe_si": " (también cabe)",
    "cabe_no": " (se pasa del presupuesto)",
    "presupuesto_restantes": (
        "  (y {n} más, hasta {precio}, en {periodos}. Si quiere ver esas, "
        "pregúntale por el mes y vuelve a consultar.)"
    ),
    "presupuesto_cierre_sin_periodo": (
        "  Cada fecha de arriba dice a qué mes pertenece: dilo cuando la "
        "ofrezcas. Cuando escoja mes, vuelve a consultar con ese mes para "
        "mandarle el flyer que le corresponde."
    ),
    #: La columna contra la que se compara y se ordena.
    "precio": "multiple",
}


def _medios() -> List[base.Medio]:
    """Las 13 piezas del catálogo del bot de viajes.

    Se leen de `llm_config` y no se inventan: cuál flyer corresponde a cuál mes
    es justamente lo que el modelo no puede adivinar. Las que traen `hotel`
    cuelgan de esa variante; las demás ilustran al producto entero.
    """
    from app.data.bot_viajes import LLM_CONFIG

    medios: List[base.Medio] = []
    for clave, item in (LLM_CONFIG.get("media") or {}).items():
        if not isinstance(item, dict) or not item.get("url"):
            continue
        aplica: Dict[str, Any] = {}
        if item.get("meses"):
            aplica["meses"] = list(item["meses"])
        if item.get("camino"):
            aplica["camino"] = item["camino"]
        medios.append(
            base.Medio(
                clave=clave,
                url=item["url"],
                variante=item.get("hotel") or None,
                tipo=item.get("media_type", "image"),
                descripcion=(item.get("descripcion") or None),
                aplica=aplica,
            )
        )
    return medios


def leer(ruta: str) -> base.Catalogo:
    """El archivo del cliente, convertido en catálogo. No toca la base."""
    with open(ruta, encoding="utf-8") as fh:
        fuente = json.load(fh)

    cat = base.Catalogo(
        slug=SLUG,
        nombre=NOMBRE,
        tipo=models.PRODUCTO_TIPO_PLAN,
        estado=models.PRODUCTO_ESTADO_PUBLICADO,
        resumen=RESUMEN,
        atributos={"presentacion": PRESENTACION},
    )

    for clave, (slug_v, nombre, orden) in HOTELES.items():
        atributos: Dict[str, Any] = {}
        if clave == "bohios":
            atributos["nota_medio_prestado"] = NOTA_MEDIO_BOHIOS
        if clave == "piedra_mar":
            atributos["coletilla_desde"] = COLETILLA_PIEDRA_MAR
        cat.variantes.append(
            base.Variante(
                slug=slug_v,
                nombre=nombre,
                orden=orden,
                atributos=atributos,
                # Bohíos no duplica la tabla: la toma de Amor de Dios.
                precios_de="amor_de_dios" if clave == "bohios" else None,
            )
        )

    for alias, clave in ALIAS:
        cat.alias.append(
            base.Alias(alias=alias, nivel=models.ALIAS_NIVEL_VARIANTE, variante=clave)
        )

    for i, plan in enumerate(fuente["planes"]):
        # La fila es de quien pone el precio: Bohíos la lee por la auto-FK.
        duena = "amor_de_dios" if "amor_de_dios" in plan["hoteles"] else "piedra_mar"
        cat.filas.append(
            base.Fila(
                externo_id=f"{plan['inicio']}|{plan['fecha']}|{duena}",
                variante=duena,
                tipo=models.FILA_TIPO_SALIDA,
                etiqueta=plan["fecha"],
                inicio=date.fromisoformat(plan["inicio"]),
                valores={k: v for k, v in plan.items() if k not in _ESTRUCTURA},
                orden=i,
            )
        )

    cat.medios = _medios()
    return cat
