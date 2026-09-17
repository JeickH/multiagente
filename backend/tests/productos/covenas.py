"""El tarifario de Coveñas, cargado como producto en la base de prueba.

Esto existe para una sola cosa: poder poner el texto de `services/tarifario.py`
y el de `services/productos.py` uno al lado del otro y exigir que sean
**idénticos** (ver `test_paridad_tarifario.py`). Mientras esa prueba esté verde,
la migración no cambió nada de lo que el bot lee.

Es el embrión del importador de la fase 4, y vive en los tests a propósito: no
es un script todavía, y lo que aprendamos acá —sobre todo dónde cuesta que el
texto quede igual— se lleva para allá.

Cómo se traduce el JSON al esquema
----------------------------------
  * Cada hotel es una **variante**. Bohíos no duplica la tabla de precios: la
    toma de Amor de Dios con `precios_de_variante_id`, que es exactamente para
    lo que existe esa columna.
  * Cada fila del Excel es una **fila** del producto, con `inicio` en la
    columna (que es por donde se filtra la vigencia) y todo lo demás en
    `valores`. El `orden` es el índice en el JSON: con dos planes que arrancan
    el mismo día, es lo que conserva el orden en que los publicó la agencia.
  * Los doce nombres con los que la gente escribe un hotel son **alias**, que
    es lo que reemplaza el diccionario cableado de `tarifario.py`.
  * Los cuatro flyers de tarifario son **medios** de su variante, con los meses
    que cubren en `aplica`. Bohíos no tiene flyer propio y se cae al de Amor de
    Dios por la misma auto-FK de los precios.
  * **El texto con el que se le responde al modelo son plantillas** en
    `atributos["presentacion"]`. Es la parte que más sorprende de la migración:
    `productos.py` no puede nombrar un hotel ni una acomodación, así que cada
    frase de `tarifario.py` que hable del negocio tiene que viajar como dato.
    Lo que quedó en el código es la estructura (qué bloque va antes de cuál,
    cuándo hay que escalar, qué se calcula sobre qué filas).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from app import models

_JSON = (
    Path(__file__).resolve().parents[2] / "app" / "data" / "tarifario_covenas.json"
)

#: Hotel del JSON -> (slug, nombre, orden). El orden es el de la frase «los
#: hoteles del plan son: Amor de Dios, Piedra Mar y Bohíos».
HOTELES = {
    "amor_de_dios": ("amor_de_dios", "Amor de Dios", 1),
    "piedra_mar": ("piedra_mar", "Piedra Mar", 2),
    "bohios": ("bohios", "Bohíos", 3),
}

#: Los mismos doce nombres que hoy están cableados en `tarifario._HOTELES`, en
#: el mismo orden: la resolución por contención depende de él.
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

#: Cómo se le habla al modelo. Cada string de acá sale tal cual de
#: `services/tarifario.py`; lo único que cambia son los `{campos}`.
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
    #: La columna contra la que se compara y se ordena. En el prompt del bot es
    #: la acomodación más económica, la que manda cotizar por defecto.
    "precio": "multiple",
}

#: Lo que Bohíos tiene que decir cuando manda un flyer que no es suyo. Sin este
#: aviso el cliente cree que le mandaron el hotel equivocado.
NOTA_MEDIO_BOHIOS = (
    "  Y al mandarla, avísale que el flyer sale a nombre de *{origen}* pero "
    "los precios aplican igual para {variante} — si no se lo dices, va a creer "
    "que le mandaste el hotel equivocado."
)

#: Piedra Mar sí tiene salidas entre semana, pero no cuando el lunes es festivo.
COLETILLA_PIEDRA_MAR = " No aplica para lunes festivos."


def datos() -> Dict[str, Any]:
    return json.loads(_JSON.read_text(encoding="utf-8"))


def medios_del_bot() -> Dict[str, Dict[str, Any]]:
    """Los flyers de tarifario del catálogo de medios del bot de viajes.

    Se leen de `llm_config` y no se inventan: cuál flyer corresponde a cuál mes
    es justamente lo que el modelo no puede adivinar.
    """
    from app.data.bot_viajes import LLM_CONFIG

    return {
        clave: item
        for clave, item in (LLM_CONFIG.get("media") or {}).items()
        if isinstance(item, dict) and item.get("hotel") and item.get("meses")
    }


def cargar(
    db,
    *,
    team_id: int,
    bot_id: Optional[int] = None,
    slug: str = "covenas_temporada",
    estado: str = models.PRODUCTO_ESTADO_PUBLICADO,
) -> models.BotProducto:
    """Deja el tarifario completo como producto de esa cuenta y devuelve el producto."""
    fuente = datos()

    producto = models.BotProducto(
        team_id=team_id,
        slug=slug,
        tipo=models.PRODUCTO_TIPO_PLAN,
        nombre="Plan Coveñas",
        estado=estado,
        resumen="Plan a Coveñas con salidas semanales y dos hoteles.",
        atributos={"presentacion": PRESENTACION},
    )
    db.add(producto)
    db.flush()

    variantes = {}
    for clave, (slug_v, nombre, orden) in HOTELES.items():
        atributos: Dict[str, Any] = {}
        if clave == "bohios":
            atributos["nota_medio_prestado"] = NOTA_MEDIO_BOHIOS
        if clave == "piedra_mar":
            atributos["coletilla_desde"] = COLETILLA_PIEDRA_MAR
        variante = models.BotProductoVariante(
            producto_id=producto.id,
            slug=slug_v,
            nombre=nombre,
            atributos=atributos,
            orden=orden,
        )
        db.add(variante)
        variantes[clave] = variante
    db.flush()

    # Bohíos no duplica la tabla: la toma de Amor de Dios.
    variantes["bohios"].precios_de_variante_id = variantes["amor_de_dios"].id

    for alias, clave in ALIAS:
        db.add(
            models.BotProductoAlias(
                producto_id=producto.id,
                nivel=models.ALIAS_NIVEL_VARIANTE,
                ref_id=variantes[clave].id,
                alias=alias,
            )
        )

    for i, plan in enumerate(fuente["planes"]):
        # La fila es de quien pone el precio: Bohíos la lee por la auto-FK.
        dueña = "amor_de_dios" if "amor_de_dios" in plan["hoteles"] else "piedra_mar"
        db.add(
            models.BotProductoFila(
                producto_id=producto.id,
                variante_id=variantes[dueña].id,
                tipo=models.FILA_TIPO_SALIDA,
                etiqueta=plan["fecha"],
                inicio=date.fromisoformat(plan["inicio"]),
                valores={k: v for k, v in plan.items() if k not in _ESTRUCTURA},
                orden=i,
                externo_id=f"{plan['inicio']}|{plan['fecha']}|{dueña}",
            )
        )

    for clave, item in medios_del_bot().items():
        db.add(
            models.BotProductoMedio(
                producto_id=producto.id,
                variante_id=variantes[item["hotel"]].id,
                clave=clave,
                url=item["url"],
                tipo=item.get("media_type", "image"),
                descripcion=item.get("descripcion"),
                aplica={"meses": list(item["meses"])},
            )
        )

    if bot_id is not None:
        db.add(
            models.BotProductoBot(
                bot_id=bot_id, producto_id=producto.id, activo=True, orden=1
            )
        )
    db.commit()
    return producto
